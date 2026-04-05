# JATAYU — Agent 1: Monitoring Agent
## File: `agents/monitoring_agent.py`

---

## Purpose

The Monitoring Agent is the **first stage** in the JATAYU pipeline. It:
1. Consumes service health records from `jatayu.telemetry.service_health`
2. Classifies services as `info`, `warning`, or `critical` based on severity scores
3. Publishes **monitoring alerts** to `jatayu.agent.monitoring.alerts`
4. Builds and publishes **rich incidents** with 5 telemetry snapshots to `jatayu.agent.monitoring.incidents`
5. Tracks run context (run_id, scenario) from `jatayu.snapshot.context`

---

## Key Design Decisions

- **Rolling buffer per service**: Keeps last 5 health records using `deque(maxlen=5)` to build incident context
- **Incident deduplication**: Only one incident per `(service, run_id)` pair — prevents alert storms
- **Severity classification**: `score >= 0.8 → critical`, `>= 0.4 → warning`, else `info`
- **Incident type detection**: Classifies from anomaly flags (pod_killed, cpu_high, latency_spike, etc.)

---

## Data Flow

```
jatayu.telemetry.service_health  ──▶  build_alert_from_health()
                                          │
                                          ▼
                                 jatayu.agent.monitoring.alerts
                                          │
                                 _build_incident_from_history()
                                          │
                                          ▼
                                 jatayu.agent.monitoring.incidents
```

---

## Full Source Code

```python
"""Monitoring Agent: consume service health and publish monitoring alerts + incidents."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS


# Rolling history buffer: last 5 health records per service
_SNAPSHOT_BUFFER_SIZE = 5

# Track which services have active incidents to avoid duplicate publishing
_active_incidents: Dict[str, str] = {}  # service -> incident_id


def build_alert_from_health(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build an alert dict from a service_health record. Return None if no alert."""
    if not isinstance(record, dict):
        return None

    status = (record.get("status") or "").lower()
    if status == "healthy":
        return None
    if status not in {"degraded", "failed"}:
        return None

    service = record.get("service")
    if not service:
        return None

    severity_score = record.get("severity_score", 0) or 0
    try:
        score_val = float(severity_score)
    except (TypeError, ValueError):
        score_val = 0.0

    if score_val >= 0.8:
        severity = "critical"
    elif score_val >= 0.4:
        severity = "warning"
    else:
        severity = "info"

    return {
        "event_type": "monitoring_alert",
        "service": service,
        "snapshot_time": record.get("snapshot_time"),
        "status": status,
        "severity": severity,
        "severity_score": score_val,
        "anomaly_flags": record.get("anomaly_flags", []),
        "evidence": record.get("evidence", []),
    }


def _detect_incident_type(record: Dict[str, Any]) -> str:
    """Classify incident type from anomaly flags and status."""
    flags = record.get("anomaly_flags", [])
    if "pod_killed" in flags:
        return "pod_kill"
    if "cpu_high" in flags:
        return "cpu_spike"
    if "latency_spike" in flags:
        return "network_delay"
    if record.get("service") in ("redis-cart", "redis"):
        return "redis_failure"
    if "readiness_probe_failed" in flags or "high_restarts" in flags:
        return "pod_instability"
    return "service_degradation"


def _build_incident_from_history(
    service: str,
    current: Dict[str, Any],
    history: List[Dict[str, Any]],
    run_id: Optional[str],
    scenario: Optional[str],
) -> Dict[str, Any]:
    """
    Create a structured incident object with 5 telemetry snapshots around
    the incident time, as required by the system specification.
    """
    incident_id = f"INC-{int(time.time())}-{str(uuid.uuid4())[:8].upper()}"

    severity_score = float(current.get("severity_score", 0) or 0)
    if severity_score >= 0.8:
        severity = "critical"
    elif severity_score >= 0.4:
        severity = "warning"
    else:
        severity = "info"

    incident_type = _detect_incident_type(current)

    # Build 5 telemetry snapshots from history (oldest to newest)
    snapshot_window = list(history)[-5:] if len(history) >= 5 else list(history)
    if current not in snapshot_window:
        snapshot_window.append(current)
    snapshot_window = snapshot_window[-5:]

    metrics_snapshots = []
    logs_snapshots = []
    traces_snapshots = []

    for i, snap in enumerate(snapshot_window):
        ts = snap.get("snapshot_time", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        metrics_snapshots.append({
            "snapshot_index": i,
            "timestamp": ts,
            "cpu_millicores": snap.get("cpu_millicores", 0),
            "memory_mib": snap.get("memory_mib", 0),
            "restart_count": snap.get("restart_count", 0),
            "pod_status": snap.get("pod_status", "unknown"),
            "severity_score": snap.get("severity_score", 0),
            "anomaly_flags": snap.get("anomaly_flags", []),
        })
        logs_snapshots.append({
            "snapshot_index": i,
            "timestamp": ts,
            "log_error_count": snap.get("log_error_count", 0),
            "log_warning_count": snap.get("log_warning_count", 0),
            "http_error_count": snap.get("http_error_count", 0),
            "evidence": snap.get("evidence", [])[:3],
        })
        traces_snapshots.append({
            "snapshot_index": i,
            "timestamp": ts,
            "avg_latency_ms": snap.get("avg_latency_ms"),
            "warning_event_count": snap.get("warning_event_count", 0),
            "unhealthy_event_count": snap.get("unhealthy_event_count", 0),
        })

    return {
        "event_type": "incident",
        "incident_id": incident_id,
        "service": service,
        "incident_type": incident_type,
        "severity": severity,
        "severity_score": severity_score,
        "anomaly_flags": current.get("anomaly_flags", []),
        "evidence": current.get("evidence", []),
        "metrics_snapshot": metrics_snapshots,
        "logs_snapshot": logs_snapshots,
        "traces_snapshot": traces_snapshots,
        "snapshot_count": len(metrics_snapshots),
        "run_id": run_id,
        "scenario": scenario,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshot_time": current.get("snapshot_time"),
    }


def run() -> None:
    if not check_kafka_connection():
        return

    health_topic = TOPICS["telemetry_service_health"]
    context_topic = TOPICS["snapshot_context"]
    alerts_topic = TOPICS["agent_monitoring_alerts"]
    incidents_topic = "jatayu.agent.monitoring.incidents"

    consumer = get_consumer(
        health_topic,
        context_topic,
        group_id="jatayu-monitoring-agent",
        auto_offset_reset="latest",
    )
    producer = get_producer()

    print(
        f"[Monitoring] Starting agent | consume=[{health_topic}, {context_topic}] | "
        f"publish={alerts_topic} + {incidents_topic}"
    )

    last_run_id: Optional[str] = None
    last_scenario: Optional[str] = None

    # Rolling history per service
    service_history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
        lambda: deque(maxlen=_SNAPSHOT_BUFFER_SIZE)
    )
    # Track incidents per service per run to avoid duplicates
    incident_published: Dict[str, str] = {}  # service+run_id -> incident_id

    try:
        for msg in consumer:
            # Track snapshot context
            if msg.topic == context_topic:
                ctx = msg.value
                if isinstance(ctx, dict):
                    new_run_id = ctx.get("run_id") or last_run_id
                    new_scenario = ctx.get("scenario") or last_scenario
                    # Reset incident tracking on new run
                    if new_run_id != last_run_id:
                        incident_published.clear()
                        service_history.clear()
                    last_run_id = new_run_id
                    last_scenario = new_scenario
                continue

            record = msg.value
            if not isinstance(record, dict):
                continue

            service = record.get("service")
            if not service:
                continue

            # Always update rolling history
            service_history[service].append(record)

            # Build and publish alert
            alert = build_alert_from_health(record)
            if not alert:
                continue

            if last_run_id:
                alert["run_id"] = last_run_id
            if last_scenario:
                alert["scenario"] = last_scenario

            try:
                future = producer.send(alerts_topic, value=alert, key=service)
                future.get(timeout=10)
                print(
                    f"[Monitoring] Alert published for {service} ({alert['severity']}) "
                    f"run={last_run_id} scenario={last_scenario}"
                )
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[ERROR] Kafka broker unavailable when publishing alert: {exc}")
                break
            except KafkaError as exc:
                print(f"[Monitoring][ERROR] Failed to publish alert for {service}: {exc}")
                continue

            # Build and publish incident (with 5 snapshots) — once per service per run
            incident_key = f"{service}:{last_run_id}"
            if incident_key not in incident_published:
                history_list = list(service_history[service])
                incident = _build_incident_from_history(
                    service=service,
                    current=record,
                    history=history_list,
                    run_id=last_run_id,
                    scenario=last_scenario,
                )
                try:
                    future = producer.send(incidents_topic, value=incident, key=service)
                    future.get(timeout=10)
                    incident_published[incident_key] = incident["incident_id"]
                    print(
                        f"[Monitoring] Incident created: {incident['incident_id']} "
                        f"for {service} (type={incident['incident_type']}, "
                        f"snapshots={incident['snapshot_count']})"
                    )
                except KafkaError as exc:
                    print(f"[Monitoring][ERROR] Failed to publish incident for {service}: {exc}")

    except KeyboardInterrupt:
        print("[Monitoring] Stopping agent (keyboard interrupt)")
    finally:
        try:
            producer.flush()
        finally:
            producer.close()
            consumer.close()


if __name__ == "__main__":
    run()
```

---

## Alert Schema (Output)

```json
{
  "event_type": "monitoring_alert",
  "service": "cartservice",
  "snapshot_time": "2024-01-15T10:30:00Z",
  "status": "degraded",
  "severity": "critical",
  "severity_score": 0.92,
  "anomaly_flags": ["cpu_high", "high_restarts"],
  "evidence": ["CPU at 950 millicores", "Restart count: 7"],
  "run_id": "run_001",
  "scenario": "cpu_spike"
}
```

## Incident Schema (Output)

```json
{
  "event_type": "incident",
  "incident_id": "INC-1705312200-A1B2C3D4",
  "service": "cartservice",
  "incident_type": "cpu_spike",
  "severity": "critical",
  "severity_score": 0.92,
  "metrics_snapshot": [...],
  "logs_snapshot": [...],
  "traces_snapshot": [...],
  "snapshot_count": 5,
  "run_id": "run_001",
  "scenario": "cpu_spike"
}
```
