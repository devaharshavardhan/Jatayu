"""Decision Agent: map RCA results to remediation action intents."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

# Add parent to path for registry import
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

    # Get preferred action from failure type
    preferred_action = _FAILURE_ACTION_MAP.get(failure_type, "investigate")

    # Check service registry
    policies = get_remediation_policies(service)
    criticality = get_criticality(service)
    safe_auto = is_safe_to_auto_remediate(service)
    k8s_resource = get_k8s_resource(service)
    namespace = get_namespace(service)

    # Apply safety guards
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
        # Fall back to first available policy
        action = policies[0] if policies else "investigate"
        reason = "policy_fallback"

    # Build action parameters
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

                # Track remediation count
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
