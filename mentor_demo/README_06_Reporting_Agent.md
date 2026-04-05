# JATAYU — Agent 6: Reporting Agent
## File: `agents/reporting_agent.py`

---

## Purpose

The Reporting Agent is the **final stage** in the JATAYU pipeline. It:
1. Consumes remediation results from `jatayu.agent.remediation.results`
2. Generates comprehensive, structured **incident post-mortems**
3. Produces a full **human-readable incident report** with runbook steps
4. Publishes incident reports to `jatayu.agent.reporting.incidents`

---

## Key Features

- **Incident ID generation**: Format `INC-YYYYMMDD-NNNN` (e.g. `INC-20240115-0001`)
- **Severity classification**: SEV-1 (critical), SEV-2 (high), SEV-3 (medium)
- **6-phase timeline**: Detection → Prediction → RCA → Decision → Remediation → Reporting
- **Impact assessment narratives**: Contextual descriptions per failure type
- **Future prevention recommendations**: 4-6 actionable items based on failure type
- **Runbook generation**: Step-by-step numbered recovery guide including kubectl commands
- **Resolution status tracking**: `RESOLVED`, `PENDING APPROVAL`, or `FAILED — MANUAL INTERVENTION REQUIRED`

---

## Data Flow

```
jatayu.agent.remediation.results  ──▶  _generate_incident_report()
                                           │
                               ┌───────────┼─────────────────┐
                               ▼           ▼                 ▼
                        Timeline     Impact Assessment   Runbook Steps
                               └───────────┼─────────────────┘
                                           ▼
                              human_report (text) + structured JSON
                                           │
                                           ▼
                             jatayu.agent.reporting.incidents
```

---

## Full Source Code

```python
"""Reporting Agent: generate comprehensive human-readable incident reports."""
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
    critical_types = {"pod_killed", "critical_failure", "readiness_failure", "pod_kill"}
    high_types = {"pod_instability", "cpu_saturation", "service_error", "deployment_failure"}
    if failure_type in critical_types:
        return "SEV-1"
    if failure_type in high_types:
        return "SEV-2"
    return "SEV-3"


def _failure_type_human(failure_type: str) -> str:
    mapping = {
        "pod_killed": "Pod Termination",
        "pod_instability": "Pod Crash Loop",
        "readiness_failure": "Readiness Probe Failure",
        "cpu_saturation": "CPU Resource Exhaustion",
        "service_degradation": "Service Degradation",
        "network_degradation": "Network Latency Spike",
        "service_error": "Service Error Rate Spike",
        "critical_failure": "Critical Service Failure",
        "deployment_failure": "Deployment Failure",
        "latency_degradation": "Latency Degradation",
        "generic_service_risk": "Service Anomaly",
    }
    return mapping.get(failure_type, failure_type.replace("_", " ").title())


def _generate_impact_assessment(
    service: str,
    failure_type: str,
    impacted: List[str],
    confidence: float,
) -> str:
    """Generate a detailed impact assessment narrative."""
    impact_desc = {
        "pod_killed": f"Complete service outage for {service}. All requests to this service will fail until the pod is restarted and passes health checks.",
        "pod_instability": f"{service} is in crash-loop state, causing intermittent unavailability. Users may experience sporadic errors and increased latency.",
        "readiness_failure": f"{service} is not serving traffic due to readiness probe failures. Traffic may be routing to unhealthy endpoints.",
        "cpu_saturation": f"{service} CPU is saturated, causing response time degradation and potential request timeouts. Under high load, the service may become unresponsive.",
        "service_degradation": f"{service} is partially functional with elevated error rates. Some requests may succeed while others fail.",
        "network_degradation": f"Network latency to {service} is elevated, causing cascading timeout errors in dependent services.",
        "service_error": f"{service} is returning elevated HTTP error responses, impacting all dependent services.",
    }
    base_impact = impact_desc.get(
        failure_type,
        f"{service} is experiencing service degradation affecting request processing."
    )

    if impacted:
        cascade = f" Additionally, {len(impacted)} downstream service(s) are affected: {', '.join(impacted[:5])}."
        base_impact += cascade

    if confidence < 0.70:
        base_impact += " Note: Root cause confidence is below 70%; impact assessment may be incomplete."

    return base_impact


def _generate_prevention_recommendations(failure_type: str, service: str) -> List[str]:
    """Generate future prevention recommendations based on failure type."""
    base_recommendations = [
        "Configure appropriate resource requests and limits for all containers",
        "Set up automated alerting with PagerDuty/OpsGenie integration for SEV-1/2 incidents",
        "Implement circuit breakers between dependent services using Istio or Resilience4j",
        "Schedule regular chaos engineering exercises to validate system resilience",
    ]

    specific_recommendations = {
        "cpu_saturation": [
            f"Implement Horizontal Pod Autoscaler (HPA) for {service} with CPU threshold at 70%",
            "Set CPU limits to prevent resource starvation of other pods on the node",
            "Profile application for CPU-intensive hot paths and optimize critical loops",
            "Consider implementing request rate limiting to prevent traffic spikes",
        ],
        "pod_killed": [
            f"Add pod disruption budgets (PDB) for {service} to prevent simultaneous pod terminations",
            "Implement graceful shutdown handlers to complete in-flight requests before termination",
            "Configure liveness probe parameters to allow sufficient startup time",
            "Use pod anti-affinity rules to distribute replicas across availability zones",
        ],
        "pod_instability": [
            "Investigate application startup logs for initialization failures",
            "Configure appropriate JVM heap sizes or memory limits to prevent OOM kills",
            "Review and fix any missing environment variables or configuration issues",
            "Implement exponential backoff for external dependency connections at startup",
        ],
        "readiness_failure": [
            "Tune readiness probe initialDelaySeconds and periodSeconds for slow-starting services",
            "Ensure dependency health checks pass before marking the pod as ready",
            "Review application initialization sequence and fix any blocking startup tasks",
        ],
        "network_degradation": [
            "Implement service mesh-level timeout and retry policies",
            "Add network policies to limit inter-service traffic and reduce noisy neighbor issues",
            "Consider deploying services in the same availability zone to reduce network hops",
            "Configure client-side load balancing to route around slow endpoints",
        ],
    }

    recs = specific_recommendations.get(failure_type, [])
    return (recs + base_recommendations)[:6]


def _generate_runbook_steps(action: str, service: str, kubectl_cmd: str) -> List[str]:
    """Generate detailed runbook steps for the remediation action."""
    pre_steps = [
        f"1. Acknowledge incident and notify on-call team via incident channel",
        f"2. Verify current pod state: kubectl get pods -n default -l app={service}",
        f"3. Review recent events: kubectl describe deployment/{service} -n default",
        f"4. Check recent logs: kubectl logs -l app={service} --tail=100 -n default",
    ]

    action_steps = {
        "rollout_restart": [
            f"5. Execute rolling restart: {kubectl_cmd}",
            f"6. Monitor rollout progress: kubectl rollout status deployment/{service} -n default",
            f"7. Verify all pods are Running: kubectl get pods -l app={service} -n default",
            f"8. Confirm service health by checking application endpoints",
        ],
        "restart_pod": [
            f"5. Execute pod restart: {kubectl_cmd}",
            f"6. Wait for pod to reach Running state (typically 30-60s)",
            f"7. Verify readiness: kubectl get pods -l app={service} -n default",
            f"8. Monitor error rates for 5 minutes post-restart",
        ],
        "scale_out": [
            f"5. Scale deployment: {kubectl_cmd}",
            f"6. Monitor new pod scheduling: kubectl get pods -l app={service} -w -n default",
            f"7. Verify load distribution across replicas",
            f"8. Monitor CPU utilization across new replicas",
        ],
        "manual_approval": [
            f"5. ESCALATION REQUIRED — Do not proceed without approval",
            f"6. Assess full blast radius with service owner team",
            f"7. Create change request in ITSM tool",
            f"8. Execute approved remediation in maintenance window",
            f"9. Post-action validation and sign-off",
        ],
    }

    specific = action_steps.get(action, [
        f"5. Execute: {kubectl_cmd}",
        f"6. Monitor service recovery",
        f"7. Validate all health checks pass",
    ])

    post_steps = [
        f"{len(pre_steps) + len(specific) + 1}. Update incident timeline with resolution notes",
        f"{len(pre_steps) + len(specific) + 2}. Close incident after 15-minute stability window",
        f"{len(pre_steps) + len(specific) + 3}. Schedule post-mortem within 48 hours (SEV-1/2)",
    ]

    return pre_steps + specific + post_steps


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
    reasoning = result.get("reasoning", "")
    reported_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    severity = _severity_from_failure_type(failure_type)
    failure_human = _failure_type_human(failure_type)
    impact_assessment = _generate_impact_assessment(service, failure_type, impacted, confidence)
    prevention_recs = _generate_prevention_recommendations(failure_type, service)

    detection_time = result.get("snapshot_time") or reported_at
    timeline = [
        {"phase": "Detection", "agent": "Monitoring Agent",
         "action": f"Anomaly detected in {service} — status={result.get('status', 'degraded')}",
         "outcome": "Alert raised and incident created", "timestamp": detection_time},
        {"phase": "Prediction", "agent": "Prediction Agent",
         "action": "Risk analysis using heuristic scoring + Isolation Forest ML model",
         "outcome": f"Failure risk predicted for {service}", "timestamp": detection_time},
        {"phase": "Root Cause Analysis", "agent": "RCA Agent",
         "action": "Dependency graph traversal + telemetry correlation + LLM reasoning",
         "outcome": f"Root cause identified: {service} ({failure_type}), confidence {confidence:.0%}",
         "timestamp": detection_time},
        {"phase": "Decision", "agent": "Decision Agent",
         "action": f"Policy engine evaluation + safety checks for {service}",
         "outcome": f"Remediation action decided: {action}", "timestamp": reported_at},
        {"phase": "Remediation", "agent": "Remediation Agent",
         "action": f"Execute: {action} on {service}",
         "outcome": f"Status: {status.upper()}", "timestamp": reported_at},
        {"phase": "Reporting", "agent": "Reporting Agent",
         "action": "Generate comprehensive incident report",
         "outcome": f"Incident {incident_id} created ({severity})", "timestamp": reported_at},
    ]

    if status == "success":
        summary = (
            f"[{severity}] {incident_id}: {failure_human} detected in {service} "
            f"(confidence: {confidence:.0%}). "
            f"Autonomous remediation via '{action}' completed successfully. "
            f"System recovery time: ~{result.get('estimated_duration_s', 30)}s. "
            f"Scenario: {scenario}."
        )
        resolution_status = "RESOLVED"
        system_recovery_time = f"~{result.get('estimated_duration_s', 30)} seconds"
    elif status == "deferred":
        summary = (
            f"[{severity}] {incident_id}: {failure_human} detected in {service} "
            f"(confidence: {confidence:.0%}). "
            f"Remediation PENDING MANUAL APPROVAL — action '{action}' requires operator sign-off. "
            f"Scenario: {scenario}."
        )
        resolution_status = "PENDING APPROVAL"
        system_recovery_time = "Pending manual remediation"
    else:
        summary = (
            f"[{severity}] {incident_id}: {failure_human} detected in {service} "
            f"(confidence: {confidence:.0%}). "
            f"Automated remediation '{action}' failed — manual intervention required. "
            f"Scenario: {scenario}."
        )
        resolution_status = "FAILED — MANUAL INTERVENTION REQUIRED"
        system_recovery_time = "Unknown — manual recovery in progress"

    runbook = _generate_runbook_steps(action, service, kubectl_cmd)

    human_report = f"""
INCIDENT REPORT
═══════════════════════════════════════════════════════════
Incident ID:     {incident_id}
Severity:        {severity}
Status:          {resolution_status}
Generated:       {reported_at}
═══════════════════════════════════════════════════════════

INCIDENT SUMMARY
──────────────────────────────────────────────────────────
{summary}

ROOT CAUSE
──────────────────────────────────────────────────────────
Root Cause Service:  {service}
Failure Type:        {failure_human} ({failure_type})
Confidence:          {confidence:.0%}
Scenario:            {scenario}
{f"Analysis: {reasoning}" if reasoning else ""}

AFFECTED SERVICES
──────────────────────────────────────────────────────────
Primary:    {service}
Downstream: {', '.join(impacted) if impacted else 'None confirmed'}

IMPACT ASSESSMENT
──────────────────────────────────────────────────────────
{impact_assessment}

EVIDENCE
──────────────────────────────────────────────────────────
{chr(10).join(f"• {e}" for e in (evidence or ['No evidence captured'])[:5])}

RESOLUTION STEPS
──────────────────────────────────────────────────────────
Action Taken:    {action}
Command:         {kubectl_cmd}
Execution:       {result.get('execution_method', 'N/A')}

SYSTEM RECOVERY
──────────────────────────────────────────────────────────
Recovery Time:   {system_recovery_time}
Final Status:    {resolution_status}

FUTURE PREVENTION RECOMMENDATIONS
──────────────────────────────────────────────────────────
{chr(10).join(f"{i+1}. {r}" for i, r in enumerate(prevention_recs))}
""".strip()

    return {
        "event_type": "incident_report",
        "incident_id": incident_id,
        "severity": severity,
        "service": service,
        "failure_type": failure_type,
        "failure_type_human": failure_human,
        "confidence_score": confidence,
        "scenario": scenario,
        "run_id": result.get("run_id"),
        "snapshot_time": result.get("snapshot_time"),
        "impacted_services": impacted,
        "evidence": evidence,
        "timeline": timeline,
        "remediation_action": action,
        "remediation_status": status,
        "resolution_status": resolution_status,
        "kubectl_command": kubectl_cmd,
        "execution_method": result.get("execution_method"),
        "system_recovery_time": system_recovery_time,
        "summary": summary,
        "impact_assessment": impact_assessment,
        "runbook_steps": runbook,
        "prevention_recommendations": prevention_recs,
        "human_report": human_report,
        "reasoning": reasoning,
        "reported_at": reported_at,
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
                print(
                    f"[Reporting] Incident report published: id={report['incident_id']}, "
                    f"severity={report['severity']}, status={report['resolution_status']}"
                )
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
```

---

## Sample Incident Report Output

```
INCIDENT REPORT
═══════════════════════════════════════════════════════════
Incident ID:     INC-20240115-0001
Severity:        SEV-1
Status:          RESOLVED
Generated:       2024-01-15T10:31:00Z
═══════════════════════════════════════════════════════════

INCIDENT SUMMARY
──────────────────────────────────────────────────────────
[SEV-1] INC-20240115-0001: Pod Termination detected in redis-cart
(confidence: 95%). Autonomous remediation via 'rollout_restart'
completed successfully. System recovery time: ~45s. Scenario: redis_failure.

ROOT CAUSE
──────────────────────────────────────────────────────────
Root Cause Service:  redis-cart
Failure Type:        Pod Termination (pod_killed)
Confidence:          95%
Scenario:            redis_failure

FUTURE PREVENTION RECOMMENDATIONS
──────────────────────────────────────────────────────────
1. Add pod disruption budgets (PDB) for redis-cart
2. Implement graceful shutdown handlers
3. Configure liveness probe parameters
4. Use pod anti-affinity rules across availability zones
5. Configure appropriate resource requests and limits
6. Set up automated alerting with PagerDuty/OpsGenie integration
```

---

## Severity Classification

| Failure Type | Severity |
|---|---|
| pod_killed, critical_failure, readiness_failure, pod_kill | SEV-1 |
| pod_instability, cpu_saturation, service_error, deployment_failure | SEV-2 |
| network_degradation, service_degradation, latency_degradation | SEV-3 |
