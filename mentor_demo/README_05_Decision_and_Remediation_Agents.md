# JATAYU — Agent 4 & 5: Decision Agent + Remediation Agent
## Files: `agents/decision_agent.py` · `agents/remediation_agent.py`

---

## Agent 4: Decision Agent

### Purpose

The Decision Agent maps RCA results to concrete, safe remediation actions. It is the **policy engine** of the pipeline:
1. Consumes RCA results from `jatayu.agent.rca.results`
2. Looks up service metadata from the **service registry** (criticality, allowed policies, namespace)
3. Applies **4 safety guards** before authorising any action
4. Publishes decision intents to `jatayu.agent.decision.intents`

### Safety Guards (in order)

| Guard | Condition | Outcome |
|---|---|---|
| Guard 1 | Critical service (`paymentservice`, `checkoutservice`) or `auto_remediate=false` | `manual_approval` required |
| Guard 2 | RCA confidence < 0.50 | `investigate` only |
| Guard 3 | ≥ 3 remediations already attempted for this service | `escalate` to on-call |
| Guard 4 | Action not in service's allowed policy list | Fall back to first allowed policy |

### Failure → Action Mapping

```
pod_killed        → rollout_restart
pod_instability   → rollout_restart
readiness_failure → restart_pod
cpu_saturation    → scale_out
service_degradation → restart_pod
network_degradation → mark_degraded
service_error     → rollout_restart
critical_failure  → rollout_restart
unknown_failure   → investigate
```

---

### Decision Agent Full Source Code

```python
"""Decision Agent: map RCA results to remediation action intents."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS
from registry.registry_loader import (
    get_criticality,
    get_k8s_resource,
    get_namespace,
    get_remediation_policies,
    is_safe_to_auto_remediate,
)

# Safety thresholds
CRITICAL_SERVICES_REQUIRE_APPROVAL = {"paymentservice", "checkoutservice"}
MAX_AUTO_REMEDIATIONS_PER_SERVICE = 3

# Failure type -> preferred action mapping
_FAILURE_ACTION_MAP = {
    "pod_killed": "rollout_restart",
    "pod_instability": "rollout_restart",
    "readiness_failure": "restart_pod",
    "cpu_saturation": "scale_out",
    "service_degradation": "restart_pod",
    "network_degradation": "mark_degraded",
    "service_error": "rollout_restart",
    "critical_failure": "rollout_restart",
    "unknown_failure": "investigate",
}

# Track remediation counts per service per session
_remediation_counts: Dict[str, int] = {}


def _decide_action(rca: Dict[str, Any]) -> Dict[str, Any]:
    """Map RCA result to a concrete remediation action intent."""
    service = rca.get("root_cause_service", "unknown")
    failure_type = rca.get("failure_type", "unknown_failure")
    confidence = float(rca.get("confidence_score", 0) or 0)

    preferred_action = _FAILURE_ACTION_MAP.get(failure_type, "investigate")

    policies = get_remediation_policies(service)
    criticality = get_criticality(service)
    safe_auto = is_safe_to_auto_remediate(service)
    k8s_resource = get_k8s_resource(service)
    namespace = get_namespace(service)

    reason = "auto_remediation"
    action = preferred_action
    auto_execute = True

    # Guard 1: critical services need human approval
    if service in CRITICAL_SERVICES_REQUIRE_APPROVAL or not safe_auto:
        action = "manual_approval"
        reason = f"critical_service_requires_approval ({criticality})"
        auto_execute = False

    # Guard 2: low confidence -> investigate only
    elif confidence < 0.50:
        action = "investigate"
        reason = "low_confidence_rca"
        auto_execute = False

    # Guard 3: too many remediations for this service
    elif _remediation_counts.get(service, 0) >= MAX_AUTO_REMEDIATIONS_PER_SERVICE:
        action = "escalate"
        reason = f"remediation_limit_exceeded ({_remediation_counts.get(service, 0)} attempts)"
        auto_execute = False

    # Guard 4: action not in allowed policies
    elif policies and action not in policies and preferred_action not in policies:
        action = policies[0] if policies else "investigate"
        reason = "policy_fallback"

    action_params = {
        "k8s_resource": k8s_resource or f"deployment/{service}",
        "namespace": namespace,
        "target_service": service,
    }
    if action == "scale_out":
        action_params["scale_to"] = 2

    return {
        "event_type": "decision_intent",
        "service": service,
        "action": action,
        "reason": reason,
        "auto_execute": auto_execute,
        "action_params": action_params,
        "criticality": criticality,
        "confidence_score": confidence,
        "failure_type": failure_type,
        "remediation_recommendation": rca.get("remediation_recommendation"),
        "impacted_services": rca.get("impacted_services", []),
        "evidence_summary": (rca.get("evidence") or [])[:3],
        "snapshot_time": rca.get("snapshot_time"),
        "scenario": rca.get("scenario"),
        "run_id": rca.get("run_id"),
        "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def run() -> None:
    if not check_kafka_connection():
        return

    consume_topic = TOPICS["agent_rca_results"]
    publish_topic = TOPICS["agent_decision_intents"]

    print(f"[Decision] Starting agent | consume={consume_topic} | publish={publish_topic}")

    consumer = get_consumer(
        consume_topic,
        group_id="jatayu-decision-agent",
        auto_offset_reset="latest",
    )
    producer = get_producer()

    try:
        for msg in consumer:
            rca = msg.value
            if not isinstance(rca, dict):
                continue

            service = rca.get("root_cause_service", "unknown")
            print(f"[Decision] Processing RCA for {service} (failure={rca.get('failure_type')})")

            intent = _decide_action(rca)

            key = intent.get("service")
            try:
                future = producer.send(publish_topic, value=intent, key=key)
                future.get(timeout=10)
                print(f"[Decision] Intent published: service={key}, action={intent['action']}, auto={intent['auto_execute']}")

                if intent["auto_execute"]:
                    _remediation_counts[service] = _remediation_counts.get(service, 0) + 1

            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[Decision][ERROR] Kafka unavailable: {exc}")
                break
            except KafkaError as exc:
                print(f"[Decision][ERROR] Failed to publish: {exc}")

    except KeyboardInterrupt:
        print("[Decision] Stopping agent (keyboard interrupt)")
    finally:
        try:
            producer.flush()
        finally:
            producer.close()
            consumer.close()


if __name__ == "__main__":
    run()
```

### Decision Intent Schema (Output)

```json
{
  "event_type": "decision_intent",
  "service": "cartservice",
  "action": "rollout_restart",
  "reason": "auto_remediation",
  "auto_execute": true,
  "action_params": {
    "k8s_resource": "deployment/cartservice",
    "namespace": "default",
    "target_service": "cartservice"
  },
  "criticality": "medium",
  "confidence_score": 0.90,
  "failure_type": "pod_killed"
}
```

---

## Agent 5: Remediation Agent

### Purpose

The Remediation Agent **executes** (or simulates) the Kubernetes remediation actions decided by the Decision Agent:
1. Consumes decision intents from `jatayu.agent.decision.intents`
2. Simulates execution using `hash(service + action)` for deterministic demo results
3. Builds kubectl-style command strings for display
4. Publishes execution results to `jatayu.agent.remediation.results`

### Supported Actions

| Action | Method | Est. Duration | Success Rate |
|---|---|---|---|
| `restart_pod` | kubectl rollout restart | 30s | 92% |
| `rollout_restart` | kubectl rollout restart deployment | 45s | 95% |
| `scale_out` | kubectl scale deployment --replicas | 20s | 98% |
| `mark_degraded` | annotate deployment | 5s | 99% |
| `verify_endpoints` | kubectl get endpoints | 10s | 99% |
| `manual_approval` | PENDING HUMAN APPROVAL | — | — |
| `escalate` | page_oncall_engineer | — | — |
| `investigate` | gather_diagnostics | 60s | 99% |

---

### Remediation Agent Full Source Code

```python
"""Remediation/Execution Agent: simulate Kubernetes remediation actions."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS

# Simulated execution results for each action type
_ACTION_SIMULATORS: Dict[str, Dict[str, Any]] = {
    "restart_pod": {
        "method": "kubectl rollout restart",
        "estimated_duration_s": 30,
        "side_effects": "Brief pod restart, ~30s downtime",
        "success_rate": 0.92,
    },
    "rollout_restart": {
        "method": "kubectl rollout restart deployment",
        "estimated_duration_s": 45,
        "side_effects": "Rolling restart, minimal downtime",
        "success_rate": 0.95,
    },
    "scale_out": {
        "method": "kubectl scale deployment --replicas",
        "estimated_duration_s": 20,
        "side_effects": "New pod scheduling, increased resource usage",
        "success_rate": 0.98,
    },
    "mark_degraded": {
        "method": "annotate deployment jatayu/status=degraded",
        "estimated_duration_s": 5,
        "side_effects": "Service marked as degraded, alerts generated",
        "success_rate": 0.99,
    },
    "verify_endpoints": {
        "method": "kubectl get endpoints | validate connectivity",
        "estimated_duration_s": 10,
        "side_effects": "Read-only verification, no service impact",
        "success_rate": 0.99,
    },
    "manual_approval": {
        "method": "PENDING_HUMAN_APPROVAL",
        "estimated_duration_s": 0,
        "side_effects": "Waiting for operator acknowledgment",
        "success_rate": None,
    },
    "escalate": {
        "method": "page_oncall_engineer",
        "estimated_duration_s": 0,
        "side_effects": "Incident escalated to on-call team",
        "success_rate": None,
    },
    "investigate": {
        "method": "gather_diagnostics",
        "estimated_duration_s": 60,
        "side_effects": "Read-only diagnostics, no changes",
        "success_rate": 0.99,
    },
}


def _simulate_execution(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate executing a Kubernetes remediation action."""
    action = intent.get("action", "investigate")
    service = intent.get("service", "unknown")
    params = intent.get("action_params", {})

    sim = _ACTION_SIMULATORS.get(action, _ACTION_SIMULATORS["investigate"])
    auto_execute = intent.get("auto_execute", False)

    if not auto_execute:
        status = "deferred"
        message = f"Action deferred: {intent.get('reason', 'manual approval required')}"
        success = False
    else:
        success_rate = sim.get("success_rate") or 0.90
        # Simulate success (deterministic for demo based on service+action hash)
        hash_val = (hash(service + action) % 100) / 100.0
        success = hash_val < success_rate

        if success:
            status = "success"
            message = f"Executed {action} on {params.get('k8s_resource', service)} in namespace {params.get('namespace', 'default')}"
        else:
            status = "failed"
            message = f"Execution failed: {action} on {service} - resource temporarily unavailable"

    kubectl_cmd = _build_kubectl_command(action, service, params)

    return {
        "event_type": "remediation_result",
        "service": service,
        "action": action,
        "status": status,
        "success": success,
        "message": message,
        "kubectl_command": kubectl_cmd,
        "execution_method": sim["method"],
        "estimated_duration_s": sim["estimated_duration_s"],
        "side_effects": sim["side_effects"],
        "action_params": params,
        "failure_type": intent.get("failure_type"),
        "impacted_services": intent.get("impacted_services", []),
        "confidence_score": intent.get("confidence_score"),
        "snapshot_time": intent.get("snapshot_time"),
        "scenario": intent.get("scenario"),
        "run_id": intent.get("run_id"),
        "evidence_summary": intent.get("evidence_summary", []),
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _build_kubectl_command(action: str, service: str, params: Dict[str, Any]) -> str:
    ns = params.get("namespace", "default")
    resource = params.get("k8s_resource", f"deployment/{service}")

    commands = {
        "restart_pod": f"kubectl rollout restart {resource} -n {ns}",
        "rollout_restart": f"kubectl rollout restart {resource} -n {ns}",
        "scale_out": f"kubectl scale {resource} --replicas={params.get('scale_to', 2)} -n {ns}",
        "mark_degraded": f"kubectl annotate {resource} jatayu/status=degraded -n {ns}",
        "verify_endpoints": f"kubectl get endpoints {service} -n {ns}",
        "manual_approval": f"# MANUAL APPROVAL REQUIRED: {resource} -n {ns}",
        "escalate": f"# ESCALATE: {resource} -n {ns} - contact on-call team",
        "investigate": f"kubectl describe {resource} -n {ns}",
    }
    return commands.get(action, f"kubectl describe {resource} -n {ns}")


def run() -> None:
    if not check_kafka_connection():
        return

    consume_topic = TOPICS["agent_decision_intents"]
    publish_topic = TOPICS["agent_remediation_results"]

    print(f"[Remediation] Starting agent | consume={consume_topic} | publish={publish_topic}")

    consumer = get_consumer(
        consume_topic,
        group_id="jatayu-remediation-agent",
        auto_offset_reset="latest",
    )
    producer = get_producer()

    try:
        for msg in consumer:
            intent = msg.value
            if not isinstance(intent, dict):
                continue

            service = intent.get("service", "unknown")
            action = intent.get("action", "investigate")
            print(f"[Remediation] Executing: service={service}, action={action}, auto={intent.get('auto_execute')}")

            result = _simulate_execution(intent)

            key = result.get("service")
            try:
                future = producer.send(publish_topic, value=result, key=key)
                future.get(timeout=10)
                print(f"[Remediation] Result published: service={key}, status={result['status']}, cmd={result['kubectl_command'][:60]}...")
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[Remediation][ERROR] Kafka unavailable: {exc}")
                break
            except KafkaError as exc:
                print(f"[Remediation][ERROR] Failed to publish: {exc}")

    except KeyboardInterrupt:
        print("[Remediation] Stopping agent (keyboard interrupt)")
    finally:
        try:
            producer.flush()
        finally:
            producer.close()
            consumer.close()


if __name__ == "__main__":
    run()
```

### Remediation Result Schema (Output)

```json
{
  "event_type": "remediation_result",
  "service": "cartservice",
  "action": "rollout_restart",
  "status": "success",
  "success": true,
  "message": "Executed rollout_restart on deployment/cartservice in namespace default",
  "kubectl_command": "kubectl rollout restart deployment/cartservice -n default",
  "execution_method": "kubectl rollout restart deployment",
  "estimated_duration_s": 45,
  "side_effects": "Rolling restart, minimal downtime",
  "executed_at": "2024-01-15T10:30:45Z"
}
```
