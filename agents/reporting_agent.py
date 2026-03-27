"""Reporting Agent: generate incident summaries and operational reports."""
from __future__ import annotations

import time
from typing import Any, Dict, List

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS

_INCIDENT_COUNTER = 0


def _severity_from_failure_type(failure_type: str) -> str:
    critical_types = {"pod_killed", "critical_failure", "readiness_failure"}
    high_types = {"pod_instability", "cpu_saturation", "service_error"}
    if failure_type in critical_types:
        return "SEV-1"
    if failure_type in high_types:
        return "SEV-2"
    return "SEV-3"


def _generate_runbook_steps(action: str, service: str, kubectl_cmd: str) -> List[str]:
    base = [
        f"1. Verify current state: kubectl get pods -n default -l app={service}",
        f"2. Check recent events: kubectl describe deployment/{service} -n default",
        f"3. Execute remediation: {kubectl_cmd}",
    ]
    if action in ("rollout_restart", "restart_pod"):
        base.append(f"4. Monitor rollout: kubectl rollout status deployment/{service} -n default")
        base.append(f"5. Verify health: kubectl get pods -l app={service} -n default")
    elif action == "scale_out":
        base.append(f"4. Check new pods: kubectl get pods -l app={service} -n default")
        base.append(f"5. Verify load distribution across replicas")
    elif action == "manual_approval":
        base = [
            f"1. ESCALATION REQUIRED: Review incident details",
            f"2. Assess blast radius: check {service} and downstream dependencies",
            f"3. Coordinate with service owner team",
            f"4. Execute approved remediation with change management",
        ]
    base.append(f"6. Update incident timeline and close ticket if resolved")
    return base


def _generate_incident_report(result: Dict[str, Any]) -> Dict[str, Any]:
    global _INCIDENT_COUNTER
    _INCIDENT_COUNTER += 1

    incident_id = f"INC-{time.strftime('%Y%m%d')}-{_INCIDENT_COUNTER:04d}"

    service = result.get("service", "unknown")
    action = result.get("action", "investigate")
    status = result.get("status", "unknown")
    failure_type = result.get("failure_type", "unknown")
    confidence = float(result.get("confidence_score") or 0)
    impacted = result.get("impacted_services", [])
    evidence = result.get("evidence_summary", [])
    kubectl_cmd = result.get("kubectl_command", "N/A")
    scenario = result.get("scenario", "unknown")

    severity = _severity_from_failure_type(failure_type)

    # Generate timeline
    timeline = [
        {"phase": "Detection", "agent": "Monitoring Agent", "action": f"Anomaly detected in {service}", "outcome": "Alert raised"},
        {"phase": "Prediction", "agent": "Prediction Agent", "action": f"Risk scored for {service}", "outcome": "Failure risk predicted"},
        {"phase": "Root Cause Analysis", "agent": "RCA Agent", "action": f"Dependency graph traversal", "outcome": f"Root cause: {service} ({failure_type})"},
        {"phase": "Decision", "agent": "Decision Agent", "action": f"Policy evaluation + safety checks", "outcome": f"Action decided: {action}"},
        {"phase": "Remediation", "agent": "Remediation Agent", "action": f"Execute: {action}", "outcome": f"Status: {status.upper()}"},
    ]

    # Generate summary text
    if status == "success":
        summary = (
            f"Incident {incident_id}: {failure_type.replace('_', ' ').title()} detected in "
            f"{service} (confidence {confidence:.0%}). "
            f"Autonomous remediation via '{action}' completed successfully. "
            f"Impacted services: {', '.join(impacted) if impacted else 'none'}. "
            f"Scenario: {scenario}."
        )
    elif status == "deferred":
        summary = (
            f"Incident {incident_id}: {failure_type.replace('_', ' ').title()} detected in "
            f"{service} (confidence {confidence:.0%}). "
            f"Remediation DEFERRED -- manual approval required for {action}. "
            f"Impacted services: {', '.join(impacted) if impacted else 'none'}."
        )
    else:
        summary = (
            f"Incident {incident_id}: {failure_type.replace('_', ' ').title()} detected in "
            f"{service} (confidence {confidence:.0%}). "
            f"Remediation '{action}' failed -- escalation required. "
            f"Impacted services: {', '.join(impacted) if impacted else 'none'}."
        )

    runbook = _generate_runbook_steps(action, service, kubectl_cmd)

    return {
        "event_type": "incident_report",
        "incident_id": incident_id,
        "severity": severity,
        "service": service,
        "failure_type": failure_type,
        "confidence_score": confidence,
        "scenario": scenario,
        "run_id": result.get("run_id"),
        "snapshot_time": result.get("snapshot_time"),
        "impacted_services": impacted,
        "evidence": evidence,
        "timeline": timeline,
        "remediation_action": action,
        "remediation_status": status,
        "kubectl_command": kubectl_cmd,
        "execution_method": result.get("execution_method"),
        "summary": summary,
        "runbook_steps": runbook,
        "reported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def run() -> None:
    if not check_kafka_connection():
        return

    consume_topic = TOPICS["agent_remediation_results"]
    publish_topic = TOPICS["agent_reporting_incidents"]

    print(f"[Reporting] Starting agent | consume={consume_topic} | publish={publish_topic}")

    consumer = get_consumer(
        consume_topic,
        group_id="jatayu-reporting-agent",
        auto_offset_reset="latest",
    )
    producer = get_producer()

    try:
        for msg in consumer:
            result = msg.value
            if not isinstance(result, dict):
                continue

            service = result.get("service", "unknown")
            print(f"[Reporting] Generating incident report for {service}")

            report = _generate_incident_report(result)

            key = report.get("service")
            try:
                future = producer.send(publish_topic, value=report, key=key)
                future.get(timeout=10)
                print(f"[Reporting] Incident report published: id={report['incident_id']}, severity={report['severity']}")
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[Reporting][ERROR] Kafka unavailable: {exc}")
                break
            except KafkaError as exc:
                print(f"[Reporting][ERROR] Failed to publish: {exc}")

    except KeyboardInterrupt:
        print("[Reporting] Stopping agent (keyboard interrupt)")
    finally:
        try:
            producer.flush()
        finally:
            producer.close()
            consumer.close()


if __name__ == "__main__":
    run()
