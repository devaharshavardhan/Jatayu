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

    # Determine execution outcome
    auto_execute = intent.get("auto_execute", False)

    if not auto_execute:
        status = "deferred"
        message = f"Action deferred: {intent.get('reason', 'manual approval required')}"
        success = False
    else:
        success_rate = sim.get("success_rate") or 0.90
        # Simulate success (deterministic for demo based on service+action)
        hash_val = (hash(service + action) % 100) / 100.0
        success = hash_val < success_rate

        if success:
            status = "success"
            message = f"Executed {action} on {params.get('k8s_resource', service)} in namespace {params.get('namespace', 'default')}"
        else:
            status = "failed"
            message = f"Execution failed: {action} on {service} - resource temporarily unavailable"

    # Build kubectl-style command
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
