# JATAYU — Agent 3: RCA Agent (Root Cause Analysis)
## File: `agents/rca_agent.py`

---

## Purpose

The RCA Agent is the **third stage** in the JATAYU pipeline. It:
1. Consumes monitoring alerts from `jatayu.agent.monitoring.alerts`
2. Correlates health telemetry with a **service dependency graph**
3. Uses **graph traversal** (BFS) to distinguish root causes from propagated symptoms
4. Optionally calls an **LLM API** (Groq/OpenAI) for natural language reasoning
5. Publishes RCA results to `jatayu.agent.rca.results`

---

## Key Design Decisions

- **Dependency graph**: Loaded from `dependency_graph.json` — maps each service to its upstream dependencies
- **Root cause vs. symptom**: If service A depends on service B and both fail, B is more likely the root cause
- **LLM integration**: Falls back gracefully — Groq → OpenAI → template-based reasoning
- **Confidence scoring**: Upstream services with no further failed dependencies get +0.10 confidence boost
- **Pre-loading health data**: At startup, pre-loads last 50 health records so RCA has context immediately

---

## Graph Traversal Algorithm

```
For each degraded/failed service S:
  upstream_deps = BFS(dependency_graph, S)
  upstream_failures = [dep for dep in upstream_deps if dep is also degraded/failed]

  if upstream_failures exist:
    → S is a SYMPTOM, upstream failures are candidates for root cause
  else:
    → S itself is a candidate root cause

Pick best candidate by: max(confidence_score, root_cause_severity)
```

---

## Data Flow

```
jatayu.agent.monitoring.alerts  ──▶  _find_root_cause()
jatayu.telemetry.service_health ──▶  health_snapshot (correlation)
dependency_graph.json           ──▶  _get_upstream_dependencies()
                                           │
                                   _generate_llm_reasoning()
                                    (Groq/OpenAI/template)
                                           │
                                           ▼
                                  jatayu.agent.rca.results
```

---

## Full Source Code

```python
"""RCA Agent: correlate alerts + service health + dependency graph to identify root cause.

Uses parallel analysis:
- Dependency graph traversal (graph-based reasoning)
- Telemetry correlation (metric-based reasoning)
- LLM-based natural language reasoning (via OpenAI/Groq API if key available,
  otherwise uses sophisticated template-based reasoning)
"""
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

# Optional LLM imports
try:
    import urllib.request
    _HTTP_AVAILABLE = True
except ImportError:
    _HTTP_AVAILABLE = False

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

                failure_info = _classify_failure(dep_flags, dep_health, dep_alert)

                dep_severity = float(dep_health.get("severity_score", 0) or 0)

                has_no_failed_upstream = not any(
                    health_snapshot.get(d, {}).get("status") in ("degraded", "failed")
                    for d in graph.get(dep, [])
                )

                confidence = failure_info["base_confidence"]
                if has_no_failed_upstream:
                    confidence = min(0.99, confidence + 0.10)
                if dep_severity >= 0.75:
                    confidence = min(0.99, confidence + 0.05)

                evidence = _build_evidence(dep, dep_health, dep_alert, affected_svc)

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

            severity = float(health_rec.get("severity_score", 0) or 0)
            status_rank = _STATUS_RANK.get(health_rec.get("status", "healthy"), 0)

            confidence = failure_info["base_confidence"] * 0.9
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
    best["impacted_services"] = list(set(best["impacted_services"]))
    return best


def _classify_failure(
    flags: List[str],
    health_rec: Dict[str, Any],
    alert_rec: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify failure type from anomaly flags."""
    for flag, info in _FAILURE_PATTERNS.items():
        if flag in flags:
            return info

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
    return evidence[:8]


def _generate_llm_reasoning(rca, health_snapshot, graph) -> str:
    """Generate LLM-based or template-based reasoning about the root cause."""
    groq_key = os.environ.get("GROQ_API_KEY")
    api_key = os.environ.get("OPENAI_API_KEY")

    if groq_key and _HTTP_AVAILABLE:
        try:
            return _call_groq_api(groq_key, rca, health_snapshot, graph)
        except Exception as exc:
            print(f"[RCA][LLM] Groq API call failed: {exc} — falling back to template")
    elif api_key and _HTTP_AVAILABLE:
        try:
            return _call_openai_api(api_key, rca, health_snapshot, graph)
        except Exception as exc:
            print(f"[RCA][LLM] OpenAI API call failed: {exc} — falling back to template")

    return _template_reasoning(rca, health_snapshot, graph)


def _build_llm_prompt(rca, health_snapshot, graph) -> str:
    service = rca.get("root_cause_service", "unknown")
    failure_type = rca.get("failure_type", "unknown")
    confidence = rca.get("confidence_score", 0)
    impacted = rca.get("impacted_services", [])
    evidence = rca.get("evidence", [])
    propagation = rca.get("propagation_path", [])
    deps = graph.get(service, [])
    svc_health = health_snapshot.get(service, {})
    health_info = (
        f"Status: {svc_health.get('status', 'unknown')}, "
        f"Severity: {svc_health.get('severity_score', 0):.2f}, "
        f"Flags: {svc_health.get('anomaly_flags', [])}"
    ) if svc_health else ""

    return (
        f"You are an SRE expert performing root cause analysis on a Kubernetes microservices incident.\n\n"
        f"Root Cause Service: {service}\n"
        f"Failure Type: {failure_type}\n"
        f"Confidence: {confidence:.0%}\n"
        f"Service Health: {health_info}\n"
        f"Dependencies: {deps}\n"
        f"Propagation Path: {' → '.join(propagation)}\n"
        f"Impacted Services: {impacted}\n"
        f"Evidence: {evidence}\n\n"
        f"Provide a concise 3-4 sentence technical analysis explaining:\n"
        f"1. Why this service is the root cause\n"
        f"2. How the failure is propagating\n"
        f"3. The most likely underlying reason\n"
        f"Be specific and technical."
    )


def _call_groq_api(api_key, rca, health_snapshot, graph) -> str:
    import json as json_lib, urllib.request
    prompt = _build_llm_prompt(rca, health_snapshot, graph)
    payload = json_lib.dumps({
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200, "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json_lib.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()


def _template_reasoning(rca, health_snapshot, graph) -> str:
    service = rca.get("root_cause_service", "unknown")
    failure_type = rca.get("failure_type", "unknown")
    confidence = rca.get("confidence_score", 0)
    impacted = rca.get("impacted_services", [])
    evidence = rca.get("evidence", [])
    propagation = rca.get("propagation_path", [])
    svc_health = health_snapshot.get(service, {})
    flags = svc_health.get("anomaly_flags", [])
    severity = svc_health.get("severity_score", 0)
    status = svc_health.get("status", "unknown")

    failure_context = {
        "cpu_saturation": f"The {service} service is experiencing CPU saturation with resource utilization exceeding safe thresholds.",
        "pod_killed": f"The {service} pod was forcibly terminated by the Kubernetes scheduler due to OOM conditions or chaos injection.",
        "pod_instability": f"The {service} pod is exhibiting crash-loop behavior with repeated restarts.",
        "readiness_failure": f"The {service} service is failing readiness probe checks, not ready to serve traffic.",
        "network_degradation": f"The {service} service is experiencing network-level degradation with increased latency.",
        "service_degradation": f"The {service} service is in a degraded state with elevated error rates.",
    }

    context = failure_context.get(failure_type,
        f"The {service} service is experiencing {failure_type.replace('_', ' ')}, status={status}, severity={severity:.2f}.")

    if len(propagation) > 1:
        prop_text = f"Failure propagating: {' → '.join(propagation)}. Downstream services {impacted} are experiencing cascading failures."
    elif impacted:
        prop_text = f"The failure in {service} is causing degradation in {len(impacted)} dependent service(s): {', '.join(impacted[:3])}."
    else:
        prop_text = f"The failure appears isolated to {service} with no confirmed downstream propagation."

    ev_text = f"Key evidence: {evidence[0]}" if evidence else f"Anomaly flags: {', '.join(flags[:3])}." if flags else ""
    conf_text = (f"Analysis confidence is high ({confidence:.0%}), with strong causal evidence." if confidence >= 0.85
        else f"Analysis confidence is moderate ({confidence:.0%}); additional monitoring recommended.")

    return f"{context} {prop_text} {ev_text} {conf_text}".strip()


def run() -> None:
    if not check_kafka_connection():
        return

    consume_topic = TOPICS["agent_monitoring_alerts"]
    health_topic = TOPICS["telemetry_service_health"]
    publish_topic = TOPICS["agent_rca_results"]

    print(f"[RCA] Starting agent | consume={consume_topic} | publish={publish_topic}")

    graph = _load_graph()
    print(f"[RCA] Loaded dependency graph: {len(graph)} services")

    pending_alerts: List[Dict[str, Any]] = []
    health_snapshot: Dict[str, Dict[str, Any]] = {}
    last_snapshot_time: Optional[str] = None
    last_scenario: Optional[str] = None
    last_run_id: Optional[str] = None

    consumer = get_consumer(
        consume_topic, TOPICS["snapshot_context"],
        group_id="jatayu-rca-agent", auto_offset_reset="latest",
    )
    health_consumer = get_consumer(
        health_topic, group_id="jatayu-rca-health-reader", auto_offset_reset="latest",
    )
    producer = get_producer()

    # Pre-load last 50 health records at startup
    health_consumer.poll(timeout_ms=1000)
    for tp in health_consumer.assignment():
        end_offset = health_consumer.end_offsets([tp])[tp]
        if end_offset > 0:
            health_consumer.seek(tp, max(0, end_offset - 50))
    deadline = time.time() + 3.0
    while time.time() < deadline:
        batch = health_consumer.poll(timeout_ms=500)
        if not batch:
            break
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

    health_consumer2 = get_consumer(
        health_topic, group_id="jatayu-rca-health-live", auto_offset_reset="latest",
    )

    try:
        for msg in consumer:
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

            last_scenario = alert.get("scenario") or last_scenario
            last_run_id = alert.get("run_id") or last_run_id
            last_snapshot_time = alert.get("snapshot_time") or last_snapshot_time

            new_health_msgs = health_consumer2.poll(timeout_ms=500)
            for tp_msgs in new_health_msgs.values():
                for hm in tp_msgs:
                    rec = hm.value
                    if isinstance(rec, dict) and rec.get("service"):
                        health_snapshot[rec["service"]] = rec

            pending_alerts.append(alert)

            rca = _find_root_cause(health_snapshot, pending_alerts, graph)
            if rca is None:
                print(f"[RCA] No root cause found yet (health snapshot: {len(health_snapshot)} services)")
                continue

            reasoning = _generate_llm_reasoning(rca, health_snapshot, graph)

            result = {
                "event_type": "rca_result",
                "snapshot_time": last_snapshot_time,
                "scenario": last_scenario,
                "run_id": last_run_id,
                "root_cause_service": rca["root_cause_service"],
                "failure_type": rca["failure_type"],
                "confidence_score": rca["confidence_score"],
                "confidence": rca["confidence_score"],
                "evidence": rca["evidence"],
                "impacted_services": rca["impacted_services"],
                "affected_services": rca["impacted_services"],
                "remediation_recommendation": rca["remediation_recommendation"],
                "propagation_path": rca.get("propagation_path", []),
                "root_cause_status": rca.get("root_cause_status", "unknown"),
                "root_cause_severity": rca.get("root_cause_severity", 0.0),
                "reasoning": reasoning,
                "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

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
```

---

## RCA Result Schema (Output)

```json
{
  "event_type": "rca_result",
  "root_cause_service": "redis-cart",
  "failure_type": "pod_killed",
  "confidence_score": 0.95,
  "evidence": [
    "Anomaly flags detected: pod_killed",
    "Service redis-cart status=failed (severity=0.95)",
    "Downstream service cartservice showing symptoms"
  ],
  "impacted_services": ["cartservice", "checkoutservice"],
  "remediation_recommendation": "rollout_restart",
  "propagation_path": ["redis-cart", "cartservice"],
  "reasoning": "The redis-cart pod was forcibly terminated... (LLM or template text)",
  "scenario": "redis_failure",
  "run_id": "run_001"
}
```

---

## Failure Pattern Table

| Anomaly Flag | Failure Type | Confidence | Recommendation |
|---|---|---|---|
| `pod_killed` | pod_killed | 0.90 | rollout_restart |
| `cpu_high` | cpu_saturation | 0.85 | scale_out |
| `readiness_probe_failed` | readiness_failure | 0.80 | restart_pod |
| `high_restarts` | pod_instability | 0.75 | rollout_restart |
| `latency_spike` | network_degradation | 0.70 | traffic_shift |
| `http_error_spike` | service_error | 0.65 | rollout_restart |
