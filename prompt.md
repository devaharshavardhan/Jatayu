# Dynamic IT Orchestrator – Production Grade System Build Prompt

You are a senior AI engineer, senior distributed systems architect, DevOps architect, and full stack engineer.  
Your task is to design and build a production-grade Dynamic IT Orchestrator system with multi-agent architecture for monitoring, prediction, root cause analysis, decision making, remediation, and reporting.

This system will operate on Kubernetes microservices and chaos engineering scenarios.

---

# SYSTEM OVERVIEW

The system must include the following agents and pipeline:

Telemetry → Normalizer → Kafka → Monitoring Agent → Prediction Agent → RCA Agent → Decision Agent → Remediation Agent → Reporting Agent → Dashboard

The system must support chaos scenarios:

- cpu_spike
- network_delay
- pod_kill
- redis_failure

Chaos scenarios are triggered using Chaos Mesh YAML files.

---

# REQUIRED SYSTEM PIPELINE

When a user triggers a scenario:

1. Chaos scenario runs.
2. Telemetry is generated (metrics, logs, events, traces).
3. Telemetry is sent to Normalizer.
4. Normalizer converts telemetry into unified schema.
5. Normalized data is pushed to Kafka topics.
6. Monitoring agent detects anomaly and creates incident.
7. Prediction agent predicts failure probability.
8. RCA agent analyzes service dependency graph + telemetry.
9. Decision agent selects remediation action.
10. Remediation agent suggests steps but requires manual approval flag.
11. Reporting agent generates human-readable report.
12. Dashboard updates visualizations and incident reports.

---

# DATA PIPELINE REQUIREMENTS

Normalizer should output unified telemetry schema:

{
timestamp,
service,
cpu,
memory,
latency,
error_rate,
log_errors,
trace_latency,
pod_restarts,
network_delay,
event_type,
incident_type
}

Kafka Topics Required:

- telemetry_topic
- incident_topic
- prediction_topic
- rca_topic
- decision_topic
- remediation_topic
- reporting_topic

---

# MONITORING AGENT REQUIREMENTS

Monitoring agent must:

- Consume normalized telemetry from Kafka
- Detect anomalies (cpu spike, latency spike, error spike, pod kill)
- Create incident
- When incident is created, generate 5 telemetry snapshots around incident time
- Snapshots must be stored and shown when user clicks incident
- Publish incident to Kafka

Incident object must contain:
{
incident_id,
service,
incident_type,
severity,
metrics_snapshot,
logs_snapshot,
traces_snapshot,
timestamp
}

---

# PREDICTION AGENT REQUIREMENTS

Prediction agent must:

- Analyze telemetry time series
- Predict probability of failure
- Detect patterns before crashes
- Output:
  {
  service,
  predicted_failure,
  probability,
  trend,
  time_to_failure
  }

Models to use:

- Isolation Forest
- Random Forest
- ARIMA or Prophet for time series

---

# RCA AGENT REQUIREMENTS

RCA agent must:

- Use service dependency graph
- Parse telemetry from Kafka topics
- Analyze dependency graph
- Identify root cause service
- Use OpenAI API or free LLM API for reasoning
- Perform graph + telemetry reasoning in parallel

RCA Output:
{
root_cause_service,
failure_type,
affected_services,
reasoning,
confidence
}

---

# DECISION AGENT REQUIREMENTS

Decision agent must:

- Use policy engine
- Map root cause to remediation action
- Send action to remediation agent

Policy examples:

- cpu_spike → scale deployment
- network_delay → restart pod
- pod_kill → redeploy pod
- redis_failure → restart redis pod

---

# REMEDIATION AGENT REQUIREMENTS

Remediation agent must:

- Generate remediation steps
- Show steps to user
- Provide two buttons:
  - Accept
  - Reject
- Only apply changes if Accept flag is true
- Execute Kubernetes or Terraform commands

---

# REPORTING AGENT REQUIREMENTS

Reporting agent must generate human readable report including:

- Incident summary
- Root cause
- Effects on system
- Timeline
- Remediation steps taken
- Resolution status
- Future prevention recommendation

Example report format:

Incident Summary:
Root Cause:
Affected Services:
Impact:
Resolution Steps:
System Recovery

Time:
Recommendations:

---

# UI REQUIREMENTS

Dashboard must include:

1. Incident Reports (must not be blank)
2. Service Dependency Graph Viewer
3. Incident Snapshots Viewer
4. Remediation Approval Panel
5. Prediction Panel
6. Graphs and Visualizations:
   - CPU usage over time
   - Memory usage
   - Latency
   - Error rate
   - Incident timeline
7. Remove any "Hackathon Demo" text from UI
8. When clicking incident → show 5 snapshots
9. Button to view Service Dependency Graph

---

# VISUALIZATIONS REQUIRED

Include graphs:

- CPU usage graph
- Memory usage graph
- Latency graph
- Error rate graph
- Incident frequency graph
- Failure prediction probability graph
- Service dependency graph visualization

Use:

- Grafana
- Plotly
- Chart.js
- D3.js

---

# CHAOS SCENARIO INTEGRATION

System must detect and handle these scenarios:

1. CPU Stress
2. Network Delay
3. Pod Kill
4. Redis Failure

When scenario runs:
Telemetry → Normalizer → Kafka → Agents → Remediation → Reporting

---

# ARCHITECTURE IMPROVEMENTS (IMPORTANT)

Improve system architecture by including:

- Telemetry Normalizer Service
- Incident Snapshot Service
- Service Graph Builder (from traces)
- Incident Database
- Feedback Learning System
- Policy Engine
- Event-driven agent communication
- Manual remediation approval flag
- LLM-based RCA reasoning
- Prediction agent using ML models
- Reporting agent generating natural language reports

---

# FINAL SYSTEM COMPONENTS

The system should include:

- Microservices Demo App
- OpenTelemetry
- Prometheus
- Loki
- Tempo
- Kafka
- Telemetry Normalizer
- Monitoring Agent
- Prediction Agent
- RCA Agent
- Decision Agent
- Remediation Agent
- Reporting Agent
- Dashboard UI
- Incident Database
- Service Dependency Graph Builder
- Chaos Mesh scenarios
- Visualization dashboard

---

# FINAL GOAL

Build a production-grade Dynamic IT Orchestrator that:

- Detects incidents
- Predicts failures
- Finds root cause
- Suggests remediation
- Applies remediation after approval
- Generates reports
- Shows graphs and dependency graph
- Stores incident history
- Works for chaos scenarios
