"""Topic constants for JATAYU messaging."""

JATAYU_SNAPSHOT_CONTEXT = "jatayu.snapshot.context"
JATAYU_TELEMETRY_K8S_EVENTS = "jatayu.telemetry.k8s_events"
JATAYU_TELEMETRY_LOG_EVENTS = "jatayu.telemetry.log_events"
JATAYU_TELEMETRY_POD_METRICS = "jatayu.telemetry.pod_metrics"
JATAYU_TELEMETRY_POD_STATUS = "jatayu.telemetry.pod_status"
JATAYU_TELEMETRY_SERVICE_FEATURES = "jatayu.telemetry.service_features"
JATAYU_TELEMETRY_SERVICE_HEALTH = "jatayu.telemetry.service_health"

JATAYU_AGENT_MONITORING_ALERTS = "jatayu.agent.monitoring.alerts"
JATAYU_AGENT_PREDICTION_RISKS = "jatayu.agent.prediction.risks"
JATAYU_AGENT_RCA_RESULTS = "jatayu.agent.rca.results"
JATAYU_AGENT_DECISION_INTENTS = "jatayu.agent.decision.intents"
JATAYU_AGENT_REMEDIATION_RESULTS = "jatayu.agent.remediation.results"
JATAYU_AGENT_REPORTING_INCIDENTS = "jatayu.agent.reporting.incidents"

TOPICS = {
    "snapshot_context": JATAYU_SNAPSHOT_CONTEXT,
    "telemetry_k8s_events": JATAYU_TELEMETRY_K8S_EVENTS,
    "telemetry_log_events": JATAYU_TELEMETRY_LOG_EVENTS,
    "telemetry_pod_metrics": JATAYU_TELEMETRY_POD_METRICS,
    "telemetry_pod_status": JATAYU_TELEMETRY_POD_STATUS,
    "telemetry_service_features": JATAYU_TELEMETRY_SERVICE_FEATURES,
    "telemetry_service_health": JATAYU_TELEMETRY_SERVICE_HEALTH,
    "agent_monitoring_alerts": JATAYU_AGENT_MONITORING_ALERTS,
    "agent_prediction_risks": JATAYU_AGENT_PREDICTION_RISKS,
    "agent_rca_results": JATAYU_AGENT_RCA_RESULTS,
    "agent_decision_intents": JATAYU_AGENT_DECISION_INTENTS,
    "agent_remediation_results": JATAYU_AGENT_REMEDIATION_RESULTS,
    "agent_reporting_incidents": JATAYU_AGENT_REPORTING_INCIDENTS,
}
