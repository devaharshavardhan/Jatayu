"""RCA Agent: correlate alerts + service health + dependency graph to identify root cause."""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS

# Dependency graph
_GRAPH_PATH = Path(__file__).resolve().parent.parent / "dependency_graph.json"
_STATUS_RANK = {"healthy": 0, "degraded": 1, "failed": 2}

# Failure type detection rules (chaos scenario patterns)
_FAILURE_PATTERNS = {
    "pod_killed": {"failure_type": "pod_killed", "base_confidence": 0.90, "recommendation": "rollout_restart"},
    "cpu_high": {"failure_type": "cpu_saturation", "base_confidence": 0.85, "recommendation": "scale_out"},
    "readiness_probe_failed": {"failure_type": "readiness_failure", "base_confidence": 0.80, "recommendation": "restart_pod"},
    "high_restarts": {"failure_type": "pod_instability", "base_confidence": 0.75, "recommendation": "rollout_restart"},
    "latency_spike": {"failure_type": "network_degradation", "base_confidence": 0.70, "recommendation": "traffic_shift"},
    "http_error_spike": {"failure_type": "service_error", "base_confidence": 0.65, "recommendation": "rollout_restart"},
}


def _load_graph() -> Dict[str, List[str]]:
    try:
        with open(_GRAPH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_upstream_dependencies(service: str, graph: Dict[str, List[str]]) -> List[str]:
    """Get all upstream (dependency) services for a given service using BFS."""
    visited: Set[str] = set()
    queue = list(graph.get(service, []))
    while queue:
        dep = queue.pop(0)
        if dep in visited:
            continue
        visited.add(dep)
        queue.extend(graph.get(dep, []))
    return list(visited)


def _get_downstream_dependents(service: str, graph: Dict[str, List[str]]) -> List[str]:
    """Get services that depend ON this service (reverse graph)."""
    dependents = []
    for svc, deps in graph.items():
        if service in deps:
            dependents.append(svc)
    return dependents


def _find_root_cause(
    health_snapshot: Dict[str, Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    graph: Dict[str, List[str]],
) -> Optional[Dict[str, Any]]:
    """
    Core RCA algorithm:
    1. Find all degraded/failed services
    2. For each, traverse upstream dependency chain
    3. Prefer earliest-failing upstream over symptom-propagation
    4. Score by: status rank + severity + anomaly flags + upstream position
    """
    if not health_snapshot:
        return None

    # Build health map
    failed_services = {
        svc: rec for svc, rec in health_snapshot.items()
        if rec.get("status") in ("degraded", "failed")
    }
    if not failed_services:
        return None

    # Build alert map (latest alert per service)
    alert_map: Dict[str, Dict[str, Any]] = {}
    for a in alerts:
        svc = a.get("service", "")
        if svc:
            alert_map[svc] = a

    # Find the most-likely root cause candidate
    candidates: List[Dict[str, Any]] = []

    for affected_svc, health_rec in failed_services.items():
        upstream_deps = _get_upstream_dependencies(affected_svc, graph)

        # Check upstream dependencies for failures (they're root cause, not symptoms)
        upstream_failures = [
            dep for dep in upstream_deps
            if health_snapshot.get(dep, {}).get("status") in ("degraded", "failed")
        ]

        if upstream_failures:
            # There are upstream failures -> affected_svc is a SYMPTOM
            for dep in upstream_failures:
                dep_health = health_snapshot[dep]
                dep_flags = dep_health.get("anomaly_flags", [])
                dep_alert = alert_map.get(dep, {})

                # Determine failure type from anomaly flags
                failure_info = _classify_failure(dep_flags, dep_health, dep_alert)

                # Calculate confidence: upstream failures have higher confidence
                dep_status_rank = _STATUS_RANK.get(dep_health.get("status", "healthy"), 0)
                dep_severity = float(dep_health.get("severity_score", 0) or 0)
                upstream_count = len(_get_upstream_dependencies(dep, graph))

                # Root services (no further upstream deps) with failures = likely root cause
                has_no_failed_upstream = not any(
                    health_snapshot.get(d, {}).get("status") in ("degraded", "failed")
                    for d in graph.get(dep, [])
                )

                confidence = failure_info["base_confidence"]
                if has_no_failed_upstream:
                    confidence = min(0.99, confidence + 0.10)
                if dep_severity >= 0.75:
                    confidence = min(0.99, confidence + 0.05)

                # Build evidence list
                evidence = _build_evidence(dep, dep_health, dep_alert, affected_svc)

                # Determine impact scope
                downstream = _get_downstream_dependents(dep, graph)
                impacted = [svc for svc in downstream if svc in failed_services]

                candidates.append({
                    "root_cause_service": dep,
                    "failure_type": failure_info["failure_type"],
                    "confidence_score": round(confidence, 3),
                    "evidence": evidence,
                    "impacted_services": list(set([affected_svc] + impacted)),
                    "remediation_recommendation": failure_info["recommendation"],
                    "propagation_path": [dep, affected_svc],
                    "root_cause_status": dep_health.get("status", "unknown"),
                    "root_cause_severity": dep_severity,
                })
        else:
            # No upstream failures -> this service itself might be the root cause
            flags = health_rec.get("anomaly_flags", [])
            alert_rec = alert_map.get(affected_svc, {})
            failure_info = _classify_failure(flags, health_rec, alert_rec)

            status_rank = _STATUS_RANK.get(health_rec.get("status", "healthy"), 0)
            severity = float(health_rec.get("severity_score", 0) or 0)

            confidence = failure_info["base_confidence"] * 0.9  # slightly lower without upstream confirmation
            if status_rank == 2:  # failed
                confidence = min(0.99, confidence + 0.10)

            downstream = _get_downstream_dependents(affected_svc, graph)
            impacted = [svc for svc in downstream if svc in failed_services]
            evidence = _build_evidence(affected_svc, health_rec, alert_rec)

            candidates.append({
                "root_cause_service": affected_svc,
                "failure_type": failure_info["failure_type"],
                "confidence_score": round(confidence, 3),
                "evidence": evidence,
                "impacted_services": list(set(impacted)),
                "remediation_recommendation": failure_info["recommendation"],
                "propagation_path": [affected_svc] + [s for s in downstream if s in failed_services][:2],
                "root_cause_status": health_rec.get("status", "unknown"),
                "root_cause_severity": severity,
            })

    if not candidates:
        return None

    # Pick best candidate: highest confidence, then highest severity
    best = max(candidates, key=lambda c: (c["confidence_score"], c["root_cause_severity"]))

    # Remove duplicates and enrich
    best["impacted_services"] = list(set(best["impacted_services"]))
    return best


def _classify_failure(
    flags: List[str],
    health_rec: Dict[str, Any],
    alert_rec: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify failure type from anomaly flags. Return type + confidence + recommendation."""
    for flag, info in _FAILURE_PATTERNS.items():
        if flag in flags:
            return info

    # Fallback: classify from status/severity
    status = health_rec.get("status", "healthy")
    severity = float(health_rec.get("severity_score", 0) or 0)

    if status == "failed" and severity >= 0.8:
        return {"failure_type": "critical_failure", "base_confidence": 0.70, "recommendation": "rollout_restart"}
    elif status == "degraded":
        return {"failure_type": "service_degradation", "base_confidence": 0.60, "recommendation": "restart_pod"}
    else:
        return {"failure_type": "unknown_failure", "base_confidence": 0.50, "recommendation": "investigate"}


def _build_evidence(
    service: str,
    health_rec: Dict[str, Any],
    alert_rec: Dict[str, Any],
    affected_svc: Optional[str] = None,
) -> List[str]:
    """Build a human-readable evidence list."""
    evidence = []

    flags = health_rec.get("anomaly_flags", [])
    if flags:
        evidence.append(f"Anomaly flags detected: {', '.join(flags)}")

    status = health_rec.get("status", "unknown")
    severity = float(health_rec.get("severity_score", 0) or 0)
    evidence.append(f"Service {service} status={status} (severity={severity:.2f})")

    existing_evidence = health_rec.get("evidence", [])
    evidence.extend(existing_evidence[:3])

    if affected_svc:
        evidence.append(f"Downstream service {affected_svc} showing symptoms")

    if alert_rec.get("severity") in ("critical", "warning"):
        evidence.append(f"Alert raised: {alert_rec.get('severity')} severity")

    return evidence[:8]  # limit evidence list


def _build_rca_result(
    rca: Dict[str, Any],
    snapshot_time: Optional[str],
    scenario: Optional[str],
    run_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "event_type": "rca_result",
        "snapshot_time": snapshot_time,
        "scenario": scenario,
        "run_id": run_id,
        "root_cause_service": rca["root_cause_service"],
        "failure_type": rca["failure_type"],
        "confidence_score": rca["confidence_score"],
        "evidence": rca["evidence"],
        "impacted_services": rca["impacted_services"],
        "remediation_recommendation": rca["remediation_recommendation"],
        "propagation_path": rca.get("propagation_path", []),
        "root_cause_status": rca.get("root_cause_status", "unknown"),
        "root_cause_severity": rca.get("root_cause_severity", 0.0),
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def run() -> None:
    if not check_kafka_connection():
        return

    consume_topic = TOPICS["agent_monitoring_alerts"]
    health_topic = TOPICS["telemetry_service_health"]
    publish_topic = TOPICS["agent_rca_results"]

    print(f"[RCA] Starting agent | consume={consume_topic} | publish={publish_topic}")

    graph = _load_graph()
    print(f"[RCA] Loaded dependency graph: {len(graph)} services")

    # Alert accumulator: buffer alerts by snapshot_time
    pending_alerts: List[Dict[str, Any]] = []
    # Health snapshot accumulator: latest health per service
    health_snapshot: Dict[str, Dict[str, Any]] = {}
    last_snapshot_time: Optional[str] = None
    last_scenario: Optional[str] = None
    last_run_id: Optional[str] = None

    # Subscribe to both monitoring alerts and snapshot context (for run_id/scenario)
    consumer = get_consumer(
        consume_topic,
        TOPICS["snapshot_context"],
        group_id="jatayu-rca-agent",
        auto_offset_reset="latest",
    )
    # Separate consumer for health data correlation
    health_consumer = get_consumer(
        health_topic,
        group_id="jatayu-rca-health-reader",
        auto_offset_reset="latest",
    )
    producer = get_producer()

    # Pre-load any existing health data using poll() — avoids blocking forever
    # when the topic is empty (agents start before data is published).
    health_consumer.poll(timeout_ms=1000)
    for tp in health_consumer.assignment():
        end_offset = health_consumer.end_offsets([tp])[tp]
        if end_offset > 0:
            health_consumer.seek(tp, max(0, end_offset - 50))

    deadline = time.time() + 3.0
    while time.time() < deadline:
        batch = health_consumer.poll(timeout_ms=500)
        if not batch:
            break  # No messages available right now — stop pre-loading
        for tp_msgs in batch.values():
            for hm in tp_msgs:
                rec = hm.value
                if isinstance(rec, dict) and rec.get("service"):
                    health_snapshot[rec["service"]] = rec
                    last_snapshot_time = rec.get("snapshot_time") or last_snapshot_time
        if len(health_snapshot) >= 15:
            break
    health_consumer.close()
    print(f"[RCA] Pre-loaded {len(health_snapshot)} health records")

    # Open a new health consumer for ongoing updates (starts at latest, sees all new health data)
    health_consumer2 = get_consumer(
        health_topic,
        group_id="jatayu-rca-health-live",
        auto_offset_reset="latest",
    )

    try:
        alert_count = 0
        for msg in consumer:
            # Handle snapshot context messages — keep track of run_id/scenario
            if msg.topic == TOPICS["snapshot_context"]:
                ctx = msg.value
                if isinstance(ctx, dict):
                    last_scenario = ctx.get("scenario") or last_scenario
                    last_run_id = ctx.get("run_id") or last_run_id
                continue

            alert = msg.value
            if not isinstance(alert, dict):
                continue

            service = alert.get("service", "")
            print(f"[RCA] Received alert for {service} ({alert.get('severity')})")

            # Pull run_id/scenario from the alert itself (monitoring agent now embeds it)
            last_scenario = alert.get("scenario") or last_scenario
            last_run_id = alert.get("run_id") or last_run_id
            last_snapshot_time = alert.get("snapshot_time") or last_snapshot_time

            # Update health snapshot with any new data (non-blocking poll, longer window)
            new_health_msgs = health_consumer2.poll(timeout_ms=500)
            for tp_msgs in new_health_msgs.values():
                for hm in tp_msgs:
                    rec = hm.value
                    if isinstance(rec, dict) and rec.get("service"):
                        health_snapshot[rec["service"]] = rec
                        last_snapshot_time = rec.get("snapshot_time") or last_snapshot_time

            pending_alerts.append(alert)
            alert_count += 1

            # Run RCA on every alert (or batch every N)
            rca = _find_root_cause(health_snapshot, pending_alerts, graph)
            if rca is None:
                print(f"[RCA] No root cause found yet (health snapshot: {len(health_snapshot)} services)")
                continue

            result = _build_rca_result(
                rca, last_snapshot_time, last_scenario, last_run_id
            )

            key = result["root_cause_service"]
            try:
                future = producer.send(publish_topic, value=result, key=key)
                future.get(timeout=10)
                print(f"[RCA] Result published: root_cause={key}, failure={result['failure_type']}, confidence={result['confidence_score']}")
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[RCA][ERROR] Kafka unavailable: {exc}")
                break
            except KafkaError as exc:
                print(f"[RCA][ERROR] Failed to publish: {exc}")

            # Clear processed alerts periodically
            if len(pending_alerts) > 30:
                pending_alerts = pending_alerts[-10:]

    except KeyboardInterrupt:
        print("[RCA] Stopping agent (keyboard interrupt)")
    finally:
        try:
            producer.flush()
        finally:
            producer.close()
            consumer.close()
            health_consumer2.close()


if __name__ == "__main__":
    run()
