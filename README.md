# JATAYU — Agentic IT Orchestrator

An autonomous AIOps platform that detects, diagnoses, and remediates Kubernetes microservice failures using a 6-agent AI pipeline powered by Apache Kafka.

---

## Table of Contents

1. [What Is Jatayu?](#1-what-is-jatayu)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Project Structure](#3-project-structure)
4. [Kafka Topics and Message Flow](#4-kafka-topics-and-message-flow)
5. [The 6 Agents — Deep Dive](#5-the-6-agents--deep-dive)
   - [Monitoring Agent](#51-monitoring-agent)
   - [Prediction Agent](#52-prediction-agent)
   - [RCA Agent](#53-rca-agent)
   - [Decision Agent](#54-decision-agent)
   - [Remediation Agent](#55-remediation-agent)
   - [Reporting Agent](#56-reporting-agent)
6. [Dashboard — Every Tab and Button](#6-dashboard--every-tab-and-button)
   - [Scenario Launcher Bar](#61-scenario-launcher-bar)
   - [Run Controls](#62-run-controls)
   - [Tab: Agent Pipeline](#63-tab-agent-pipeline)
   - [Tab: Overview](#64-tab-overview)
   - [Tab: Graphs](#65-tab-graphs)
   - [Tab: Service Graph](#66-tab-service-graph)
   - [Tab: Prediction](#67-tab-prediction)
   - [Tab: Data Explorer](#68-tab-data-explorer)
   - [Tab: Incidents](#69-tab-incidents)
   - [Tab: Approval Panel](#610-tab-approval-panel)
   - [Tab: Registry](#611-tab-registry)
7. [API Endpoints — Complete Reference](#7-api-endpoints--complete-reference)
8. [Normalized Dataset Structure](#8-normalized-dataset-structure)
9. [Chaos Scenarios](#9-chaos-scenarios)
10. [Service Registry](#10-service-registry)
11. [Messaging Layer](#11-messaging-layer)
12. [Running the System](#12-running-the-system)

---

## 1. What Is Jatayu?

Jatayu is a fully autonomous **incident management and self-healing platform** for Kubernetes microservices. It watches live telemetry, detects anomalies, performs root cause analysis, decides on a remediation action, executes or escalates it, and generates a full incident report — all without human intervention (unless the service is too critical to auto-remediate).

The system is built around a **Kafka event bus**. Each stage of the pipeline is a separate Python process that reads from one topic and writes to another. The dashboard shows every message flowing through every stage in real time.

### Core capabilities

| Capability | How |
|---|---|
| Anomaly detection | Monitoring Agent compares severity scores and anomaly flags per service |
| Failure prediction | Prediction Agent uses Isolation Forest + trend regression + heuristic scoring |
| Root cause analysis | RCA Agent traverses the dependency graph and optionally calls an LLM |
| Remediation decision | Decision Agent applies safety policies from the service registry |
| Remediation execution | Remediation Agent simulates kubectl commands (or executes real ones) |
| Incident reporting | Reporting Agent generates structured post-mortems with timelines and runbooks |
| Manual approval gate | Critical services pause at the Approval Panel and require a human click |
| Chaos replay | Pre-recorded telemetry snapshots can be re-published to replay any incident |

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SCENARIO LAUNCHER                            │
│  (loads normalized snapshots and publishes them to Kafka topics)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    Apache Kafka      │
                    │   localhost:9092     │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
   ┌──────▼──────┐    ┌────────▼────────┐   ┌──────▼──────┐
   │  Monitoring  │    │   Prediction    │   │     RCA     │
   │    Agent     │    │     Agent       │   │    Agent    │
   └──────┬───────┘    └────────┬────────┘   └──────┬──────┘
          │  alerts+incidents   │  risks             │  rca_results
          └──────────────┐      │             ┌──────┘
                         │      │             │
                  ┌──────▼──────▼─────────────▼──────┐
                  │           Decision Agent           │
                  └──────────────────┬────────────────┘
                                     │  decision_intents
                              ┌──────▼──────┐
                              │ Remediation  │
                              │    Agent    │
                              └──────┬──────┘
                                     │  remediation_results
                              ┌──────▼──────┐
                              │  Reporting   │
                              │    Agent    │
                              └──────┬──────┘
                                     │  incident_reports
                              ┌──────▼──────┐
                              │  Dashboard   │
                              │  (FastAPI)   │
                              └─────────────┘
```

---

## 3. Project Structure

```
Jatayu/
├── agents/                        # The 6 autonomous pipeline agents
│   ├── monitoring_agent.py        # Detects anomalies, creates incidents
│   ├── prediction_agent.py        # ML-based failure risk scoring
│   ├── rca_agent.py               # Root cause analysis + LLM reasoning
│   ├── decision_agent.py          # Maps RCA to remediation actions
│   ├── remediation_agent.py       # Executes or simulates kubectl actions
│   └── reporting_agent.py        # Generates post-mortem reports
│
├── app/                           # FastAPI web application
│   ├── main.py                    # App entrypoint and router registration
│   ├── routers/
│   │   ├── api.py                 # All REST API endpoints
│   │   └── dashboard.py          # HTML page routes
│   ├── services/
│   │   ├── dataset_service.py    # Reads normalized snapshot files
│   │   ├── publish_service.py    # Wraps snapshot publisher
│   │   └── kafka_view_service.py # Reads recent messages from Kafka topics
│   ├── templates/
│   │   ├── base.html             # HTML shell with CSS + script tags
│   │   └── dashboard.html        # Full dashboard UI (all tabs + JS)
│   └── static/
│       └── app.js                # All frontend JavaScript (~1300 lines)
│
├── messaging/                     # Kafka abstraction layer
│   ├── config.py                  # Bootstrap server config
│   ├── topics.py                  # Topic name constants
│   ├── producer.py               # KafkaProducer factory
│   ├── consumer.py               # KafkaConsumer factory
│   ├── publisher.py              # Snapshot-to-Kafka publisher
│   └── healthcheck.py            # Kafka connectivity check
│
├── normalized/                    # Pre-recorded telemetry snapshots
│   ├── c_cpu_spike/
│   │   └── {run_id}/
│   │       ├── snapshot_0/       # 7 JSON files per snapshot
│   │       ├── snapshot_1/
│   │       └── ...
│   ├── c_network_delay/
│   ├── c_pod_kill/
│   └── c_redis_failure/
│
├── registry/
│   └── service_registry.json     # Per-service metadata and policies
│
├── graph/
│   └── dependency_graph.json     # Service → dependencies mapping
│
├── scenarios/                     # Chaos Mesh YAML definitions
│   ├── c_cpu_spike.yaml
│   ├── c_network_delay.yaml
│   ├── c_pod_kill.yaml
│   └── c_redis_failure.yaml
│
├── logs/                          # Agent runtime logs
│   ├── agent_monitoring.log
│   ├── agent_prediction.log
│   ├── agent_rca.log
│   ├── agent_decision.log
│   ├── agent_remediation.log
│   └── agent_reporting.log
│
├── docker-compose.yml            # Kafka (KRaft, single-node)
└── requirements.txt
```

---

## 4. Kafka Topics and Message Flow

### All topics

| Topic | Direction | Publisher | Consumer(s) |
|---|---|---|---|
| `jatayu.snapshot.context` | Telemetry | Snapshot Publisher | Monitoring, RCA |
| `jatayu.telemetry.k8s_events` | Telemetry | Snapshot Publisher | — |
| `jatayu.telemetry.log_events` | Telemetry | Snapshot Publisher | — |
| `jatayu.telemetry.pod_metrics` | Telemetry | Snapshot Publisher | — |
| `jatayu.telemetry.pod_status` | Telemetry | Snapshot Publisher | — |
| `jatayu.telemetry.service_features` | Telemetry | Snapshot Publisher | Prediction |
| `jatayu.telemetry.service_health` | Telemetry | Snapshot Publisher | Monitoring, RCA |
| `jatayu.agent.monitoring.alerts` | Agent output | Monitoring | RCA |
| `jatayu.agent.monitoring.incidents` | Agent output | Monitoring | Dashboard |
| `jatayu.agent.prediction.risks` | Agent output | Prediction | Dashboard |
| `jatayu.agent.rca.results` | Agent output | RCA | Decision |
| `jatayu.agent.decision.intents` | Agent output | Decision | Remediation |
| `jatayu.agent.remediation.results` | Agent output | Remediation | Reporting |
| `jatayu.agent.reporting.incidents` | Agent output | Reporting | Dashboard |

### Complete message flow

```
Snapshot files (filesystem)
        │
        ▼  POST /api/publish/snapshot
Kafka Topics (telemetry)
        │
        ├──► jatayu.telemetry.service_health
        │           │
        │           ▼
        │    MONITORING AGENT
        │    - Creates alert per service (severity: info/warning/critical)
        │    - Creates incident with 5 telemetry snapshots (once per service per run)
        │           │
        │           ├──► jatayu.agent.monitoring.alerts ──────► RCA AGENT
        │           └──► jatayu.agent.monitoring.incidents ───► Dashboard
        │
        ├──► jatayu.telemetry.service_features
        │           │
        │           ▼
        │    PREDICTION AGENT
        │    - Heuristic risk scoring (CPU, memory, restarts, latency, events)
        │    - Isolation Forest anomaly detection (if scikit-learn available)
        │    - Linear regression trend analysis (rising / stable / falling)
        │           │
        │           └──► jatayu.agent.prediction.risks ────────► Dashboard
        │
        └──► jatayu.snapshot.context ────────────────────────► Context metadata
                                                                (run_id, scenario)

jatayu.agent.monitoring.alerts
        │
        ▼
RCA AGENT
- Loads dependency_graph.json
- BFS traversal to find root service
- Cross-correlates with service_health history
- Classifies failure type from anomaly flags
- Generates LLM reasoning (Groq/OpenAI if keys set, else template)
        │
        └──► jatayu.agent.rca.results
                    │
                    ▼
            DECISION AGENT
            - Maps failure_type → remediation action
            - Applies safety guards (critical services → manual_approval)
            - Validates action against registry policies
            - Sets auto_execute flag
                    │
                    └──► jatayu.agent.decision.intents
                                │
                                ▼
                        REMEDIATION AGENT
                        - Simulates kubectl execution
                        - Defers if auto_execute = false
                        - Returns success/deferred/failed + command
                                │
                                └──► jatayu.agent.remediation.results
                                            │
                                            ▼
                                    REPORTING AGENT
                                    - Assigns SEV-1/2/3
                                    - Builds timeline, runbook, impact assessment
                                    - Generates human-readable report
                                            │
                                            └──► jatayu.agent.reporting.incidents
                                                        │
                                                        ▼
                                                   Dashboard
                                                (Incidents Tab)
```

---

## 5. The 6 Agents — Deep Dive

### 5.1 Monitoring Agent

**File**: `agents/monitoring_agent.py`
**Consumes**: `jatayu.telemetry.service_health`, `jatayu.snapshot.context`
**Publishes**: `jatayu.agent.monitoring.alerts`, `jatayu.agent.monitoring.incidents`
**Group ID**: `jatayu-monitoring-agent`

#### What it does step by step

1. Starts a KafkaConsumer on service_health and snapshot_context topics.
2. As records arrive, it classifies each service's severity:
   - `severity_score >= 0.8` → **critical**
   - `severity_score >= 0.4` → **warning**
   - else → **info**
3. Publishes an **alert** event immediately for every service health record received.
4. Maintains a rolling window of the last 5 health records per service (`_service_history`).
5. The first time a service fires an alert in a given run, it builds a **rich incident** object containing:
   - The last 5 health records as `metrics_snapshot` (CPU, memory, restart count, pod status, severity score, anomaly flags)
   - The last 5 records as `logs_snapshot` (log_error_count, log_warning_count, http_error_count, evidence)
   - The last 5 records as `traces_snapshot` (avg_latency_ms, warning/unhealthy event counts)
6. Publishes the incident to `jatayu.agent.monitoring.incidents`.
7. Tracks `incident_published[service:run_id]` to avoid duplicate incidents per run.

#### Alert event structure

```json
{
  "event_type": "monitoring_alert",
  "service": "recommendationservice",
  "severity": "critical",
  "severity_score": 0.9,
  "status": "failed",
  "anomaly_flags": ["cpu_high", "pod_killed"],
  "evidence": ["CPU millicores exceeded threshold", "Pod termination event detected"],
  "snapshot_time": "2026-03-25T11:54:30Z",
  "run_id": "1774439669",
  "scenario": "c_cpu_spike"
}
```

#### Incident event structure

```json
{
  "event_type": "incident",
  "incident_id": "INC-1774687041-F4DD2610",
  "service": "recommendationservice",
  "incident_type": "cpu_saturation",
  "severity": "critical",
  "severity_score": 0.9,
  "anomaly_flags": ["cpu_high"],
  "evidence": ["CPU millicores exceeded threshold"],
  "metrics_snapshot": [
    {
      "snapshot_index": 0,
      "timestamp": "...",
      "cpu_millicores": 820,
      "memory_mib": 112,
      "restart_count": 0,
      "pod_status": "Running",
      "severity_score": 0.85,
      "anomaly_flags": ["cpu_high"]
    }
    // ... up to 5 entries
  ],
  "logs_snapshot": [
    {
      "snapshot_index": 0,
      "timestamp": "...",
      "log_error_count": 3,
      "log_warning_count": 8,
      "http_error_count": 0,
      "evidence": ["CPU threshold exceeded"]
    }
  ],
  "traces_snapshot": [
    {
      "snapshot_index": 0,
      "timestamp": "...",
      "avg_latency_ms": 450.2,
      "warning_event_count": 2,
      "unhealthy_event_count": 0
    }
  ],
  "snapshot_count": 5,
  "run_id": "1774439669",
  "scenario": "c_cpu_spike",
  "timestamp": "2026-03-25T11:54:31Z"
}
```

---

### 5.2 Prediction Agent

**File**: `agents/prediction_agent.py`
**Consumes**: `jatayu.telemetry.service_features`, `jatayu.snapshot.context`
**Publishes**: `jatayu.agent.prediction.risks`
**Group ID**: `jatayu-prediction-agent`

#### What it does step by step

1. Consumes service_features records (aggregated per-service metrics per snapshot).
2. Maintains a rolling history of the last 10 feature records per service.
3. Runs three risk scoring methods and combines results:

**Method 1 — Heuristic Scoring** (always active):

| Signal | Condition | Added Risk |
|---|---|---|
| CPU rising | >25% increase over last 2 snapshots | +0.35 |
| CPU high | >= 800 millicores | +0.20 |
| Restarts increasing | Count went up | +0.25 |
| Restarts high | >= 5 | +0.15 |
| Warning events | > 0 | +0.15 |
| Unhealthy events | > 0 | +0.20 |
| Log/HTTP errors | > 0 | +0.20 |
| Latency spike | >30% rise | +0.20 |
| Anomaly flag: high_restarts | Present | +0.10 |
| Anomaly flag: readiness_failed | Present | +0.10 |
| Anomaly flag: pod_killed | Present | +0.10 |
| Anomaly flag: cpu_high | Present | +0.10 |
| Pod not Running | Non-Running status | +0.25 |

Score is capped at 0.99.

**Method 2 — Isolation Forest** (requires scikit-learn, activates after 3+ history records):
- Feature vector: `[cpu_millicores, memory_mib, restart_count, log_error_count, log_warning_count, http_error_count, avg_latency_ms, warning_event_count, unhealthy_event_count, failed_create_count]`
- Trains a fresh IsolationForest on the history window.
- Adds up to +0.25 to the heuristic score based on the anomaly score.

**Method 3 — Trend Analysis** (activates after 3+ history records):
- Runs linear regression on `cpu_millicores` and `restart_count` over time.
- Classifies trend as: `rising` (slope > 5), `falling` (slope < -5), or `stable`.
- Rising trend also affects `time_to_failure` estimate (shorter window).

4. Only publishes if `risk_score >= 0.35` (filters low-noise readings).

#### Risk event structure

```json
{
  "event_type": "prediction_risk",
  "service": "recommendationservice",
  "risk_score": 0.87,
  "risk_level": "critical",
  "predicted_failure_type": "cpu_saturation",
  "probability": 0.87,
  "trend": "rising",
  "time_to_failure": "imminent (<5 min)",
  "rationale": [
    "CPU rising sharply: 820m (was 350m)",
    "Anomaly flag detected: cpu_high",
    "ML anomaly detected (score: 0.82)"
  ],
  "ml_enabled": true,
  "run_id": "1774439669",
  "scenario": "c_cpu_spike",
  "snapshot_time": "2026-03-25T11:54:30Z"
}
```

**Risk levels**:
- `critical`: score >= 0.75
- `high`: score >= 0.55
- `medium`: score >= 0.35
- `low`: score < 0.35 (not published)

---

### 5.3 RCA Agent

**File**: `agents/rca_agent.py`
**Consumes**: `jatayu.agent.monitoring.alerts`, `jatayu.telemetry.service_health`, `jatayu.snapshot.context`
**Publishes**: `jatayu.agent.rca.results`
**Group ID**: `jatayu-rca-agent`

#### What it does step by step

1. On startup, pre-loads:
   - `graph/dependency_graph.json` — a map of `service → [upstream dependencies]`
   - Last 50 messages from `jatayu.telemetry.service_health` for context
2. Continuously ingests live service_health records to keep a rolling health snapshot.
3. When an alert arrives, performs multi-stage analysis:

**Stage 1 — Dependency graph traversal**:
- Uses BFS from the alerted service upward through its dependency chain.
- If an upstream dependency is also failing or degraded, it becomes the suspected root cause.
- Prioritizes the earliest-failing upstream service over downstream symptom services.
- Detects propagation paths (e.g., redis-cart → cartservice → checkoutservice → frontend).

**Stage 2 — Health correlation**:
- Cross-references the current health snapshot for all services in the propagation path.
- Calculates a confidence score based on:
  - Severity scores of root candidate and alerted service
  - Number of upstream dependencies that are also degraded
  - How recently the root candidate started failing

**Stage 3 — Failure type classification**:
From anomaly flags:

| Flag | Failure Type | Confidence |
|---|---|---|
| `pod_killed` | pod_killed | 0.90 |
| `cpu_high` | cpu_saturation | 0.85 |
| `readiness_probe_failed` | readiness_failure | 0.80 |
| `high_restarts` | pod_instability | 0.75 |
| `latency_spike` | network_degradation | 0.70 |
| `http_error_spike` | service_error | 0.65 |

**Stage 4 — LLM reasoning**:
- Checks environment for `GROQ_API_KEY` or `OPENAI_API_KEY`.
- **With API key**: Sends a structured prompt to the LLM (Groq preferred, 200-token budget).
- **Without API key**: Generates a detailed template-based reasoning string with:
  - Failure type narrative (e.g., "CPU saturation causes thread pool exhaustion, leading to request queuing")
  - Propagation chain description
  - Confidence explanation
  - Manual investigation recommendations

#### RCA result structure

```json
{
  "event_type": "rca_result",
  "alerted_service": "checkoutservice",
  "root_cause_service": "redis-cart",
  "failure_type": "pod_killed",
  "confidence_score": 0.87,
  "evidence": [
    "redis-cart is in failed state (severity: 0.9)",
    "cartservice depends on redis-cart and is degraded",
    "Pod termination event detected for redis-cart"
  ],
  "impacted_services": ["cartservice", "checkoutservice"],
  "remediation_recommendation": "rollout_restart",
  "propagation_path": ["redis-cart", "cartservice", "checkoutservice"],
  "root_cause_status": "failed",
  "root_cause_severity": 0.9,
  "reasoning": "redis-cart pod was forcibly terminated. cartservice depends on redis-cart for session storage...",
  "run_id": "1774439669",
  "scenario": "c_pod_kill",
  "analyzed_at": "2026-03-25T11:54:35Z"
}
```

---

### 5.4 Decision Agent

**File**: `agents/decision_agent.py`
**Consumes**: `jatayu.agent.rca.results`
**Publishes**: `jatayu.agent.decision.intents`
**Group ID**: `jatayu-decision-agent`

#### What it does step by step

1. Loads `registry/service_registry.json` on startup (criticality, policies, auto-remediate flag).
2. For each RCA result, maps the failure type to a preferred action:

| Failure Type | Default Action |
|---|---|
| pod_killed | rollout_restart |
| pod_instability | rollout_restart |
| readiness_failure | restart_pod |
| cpu_saturation | scale_out |
| service_degradation | restart_pod |
| network_degradation | mark_degraded |
| service_error | rollout_restart |
| critical_failure | rollout_restart |

3. Applies safety guards in priority order:
   - **Guard 1 — Critical service**: If the service's registry `criticality` is `critical` OR `safe_to_auto_remediate` is false → override action to `manual_approval`, `auto_execute = false`
   - **Guard 2 — Low confidence**: If `confidence_score < 0.50` → override action to `investigate`, `auto_execute = false`
   - **Guard 3 — Remediation storm**: If 3 or more remediations have already been triggered this session → override to `escalate`, `auto_execute = false`
   - **Guard 4 — Policy check**: If the mapped action is not in the service's `remediation_policies` list → fallback to the first allowed policy

4. Sets `auto_execute = true` only when all guards pass.
5. Attaches action parameters (`k8s_resource`, `namespace`, `scale_to` for scale_out).

#### Decision intent structure

```json
{
  "event_type": "decision_intent",
  "service": "redis-cart",
  "action": "rollout_restart",
  "reason": "auto_remediation",
  "auto_execute": true,
  "action_params": {
    "k8s_resource": "deployment/redis-cart",
    "namespace": "default"
  },
  "criticality": "medium",
  "confidence_score": 0.87,
  "failure_type": "pod_killed",
  "impacted_services": ["cartservice", "checkoutservice"],
  "evidence_summary": ["Pod termination detected", "cascading failure to cartservice"],
  "decided_at": "2026-03-25T11:54:36Z"
}
```

---

### 5.5 Remediation Agent

**File**: `agents/remediation_agent.py`
**Consumes**: `jatayu.agent.decision.intents`
**Publishes**: `jatayu.agent.remediation.results`
**Group ID**: `jatayu-remediation-agent`

#### What it does step by step

1. For every decision intent received, checks `auto_execute`:
   - If `false` → immediately publishes a `deferred` result (human must approve via the Approval Panel).
   - If `true` → simulates kubectl execution and publishes a result.

2. Execution simulation per action type:

| Action | kubectl Command | Est. Duration | Success Rate |
|---|---|---|---|
| restart_pod | `kubectl rollout restart ...` | 30s | 92% |
| rollout_restart | `kubectl rollout restart deployment/...` | 45s | 95% |
| scale_out | `kubectl scale --replicas=2 ...` | 20s | 98% |
| mark_degraded | `kubectl annotate ...` | 5s | 99% |
| verify_endpoints | `kubectl get endpoints ...` | 10s | 99% |
| manual_approval | — | 0s | — (deferred) |
| escalate | page_oncall_engineer | 0s | — (deferred) |
| investigate | gather_diagnostics | 60s | 99% |

3. Success is deterministically computed: `hash(service + action) % 100 < success_rate` — so the same service+action always produces the same outcome in a simulation run.

#### Remediation result structure

```json
{
  "event_type": "remediation_result",
  "service": "redis-cart",
  "action": "rollout_restart",
  "status": "success",
  "success": true,
  "message": "rollout_restart applied for redis-cart via kubectl rollout restart",
  "kubectl_command": "kubectl rollout restart deployment/redis-cart -n default",
  "execution_method": "kubectl rollout restart",
  "estimated_duration_s": 45,
  "side_effects": "Brief pod restart, ~45s downtime",
  "auto_execute": true,
  "confidence_score": 0.87,
  "failure_type": "pod_killed",
  "run_id": "1774439669",
  "scenario": "c_pod_kill",
  "snapshot_time": "2026-03-25T11:54:30Z",
  "executed_at": "2026-03-25T11:54:37Z"
}
```

---

### 5.6 Reporting Agent

**File**: `agents/reporting_agent.py`
**Consumes**: `jatayu.agent.remediation.results`
**Publishes**: `jatayu.agent.reporting.incidents`
**Group ID**: `jatayu-reporting-agent`

#### What it does step by step

1. Receives each remediation result and compiles a full incident report.
2. Assigns severity:
   - **SEV-1**: pod_killed, critical_failure, readiness_failure, pod_kill
   - **SEV-2**: pod_instability, cpu_saturation, service_error, deployment_failure
   - **SEV-3**: all others
3. Determines resolution status:
   - `status = "success"` → `RESOLVED`
   - `status = "deferred"` → `PENDING APPROVAL`
   - `status = "failed"` → `FAILED — MANUAL INTERVENTION REQUIRED`
4. Builds the following sections:

**Timeline** — 6 phases, each attributed to an agent:
- `Detection` (Monitoring Agent) — "Alert triggered for service"
- `Prediction` (Prediction Agent) — "Risk scored"
- `RCA` (RCA Agent) — "Root cause identified"
- `Decision` (Decision Agent) — "Remediation action selected"
- `Remediation` (Remediation Agent) — "Action executed / deferred"
- `Reporting` (Reporting Agent) — "Incident report generated"

**Impact Assessment** — service-specific narrative. For example, checkoutservice failure gets: "Users cannot complete purchases. Revenue impact is direct. Downstream notifications to emailservice may also fail."

**Runbook Steps** — step-by-step for the chosen action:
1. Acknowledge the incident
2. Verify current pod/deployment state via kubectl
3. Review recent logs (kubectl logs -f ...)
4. Execute the action
5. Monitor rollout (kubectl rollout status ...)
6. Validate recovery (curl healthcheck)
7. Close the incident

**Prevention Recommendations** — 6 items tailored to failure type:
- For cpu_saturation: Set up HPA, configure resource limits/requests, enable CPU throttling alerts, load test regularly
- For pod_killed: Set pod disruption budgets, review resource requests, configure liveness/readiness probes

**Human Report** — a formatted multi-section text document:
```
INCIDENT REPORT
═══════════════
Incident ID:    INC-20260328-0001
Severity:       SEV-1
Status:         RESOLVED
...
SUMMARY
AFFECTED SERVICES
ROOT CAUSE ANALYSIS
EVIDENCE
REMEDIATION ACTIONS
TIMELINE
PREVENTION RECOMMENDATIONS
```

#### Incident report structure

```json
{
  "event_type": "incident_report",
  "incident_id": "INC-20260328-0001",
  "severity": "SEV-1",
  "service": "redis-cart",
  "failure_type": "pod_killed",
  "failure_type_human": "Pod Termination",
  "confidence_score": 0.87,
  "scenario": "c_redis_failure",
  "run_id": "1774439669",
  "snapshot_time": "2026-03-25T11:54:30Z",
  "impacted_services": ["cartservice", "checkoutservice"],
  "evidence": ["Pod termination event detected", "cascading failure to cartservice"],
  "timeline": [
    {"phase": "Detection", "agent": "Monitoring Agent", "action": "alert_raised", "outcome": "Alert triggered for redis-cart", "timestamp": "..."}
  ],
  "remediation_action": "rollout_restart",
  "remediation_status": "success",
  "resolution_status": "RESOLVED",
  "kubectl_command": "kubectl rollout restart deployment/redis-cart -n default",
  "execution_method": "kubectl rollout restart",
  "system_recovery_time": "~45 seconds",
  "summary": "[SEV-1] INC-20260328-0001: Pod Termination detected in redis-cart — rollout_restart applied successfully",
  "impact_assessment": "redis-cart handles session storage for cartservice...",
  "runbook_steps": ["1. Acknowledge the incident...", "2. Verify current state..."],
  "prevention_recommendations": ["1. Set pod disruption budgets...", "2. Review resource requests..."],
  "human_report": "INCIDENT REPORT\n═══════════════\n...",
  "reasoning": "LLM or template-based root cause narrative",
  "reported_at": "2026-03-25T11:54:40Z"
}
```

---

## 6. Dashboard — Every Tab and Button

The dashboard is a single-page application served by FastAPI. It polls `/api/pipeline/state` every 5 seconds to keep all panels live. All JavaScript is in `app/static/app.js`.

### 6.1 Scenario Launcher Bar

The top bar is always visible regardless of which tab is active.

#### Scenario Buttons (4 buttons)

| Button | Scenario ID | Fault Injected |
|---|---|---|
| ⚡ CPU Spike | `c_cpu_spike` | 2-worker CPU stress on recommendationservice for 1 min |
| 🌐 Network Delay | `c_network_delay` | 200ms latency on frontend for 45s |
| 🗄️ Redis Failure | `c_redis_failure` | Pod kill on redis-cart for 30s |
| 💀 Pod Kill | `c_pod_kill` | Pod kill on frontend for 30s |

**Clicking a scenario button**:
1. Calls `selectScenario(scenario_id)`
2. `GET /api/runs/{scenario}` → populates the Run selector dropdown
3. Auto-selects the first available run
4. Calls `selectRun(run_id)` → `GET /api/snapshots/{scenario}/{run_id}`
5. Loads and displays the first snapshot (snapshot_0)
6. Updates the Snapshot Indicator ("Snapshot 1 / 5 — snapshot_0")

#### Run Selector (dropdown)

- Lists all recorded run IDs for the selected scenario (e.g., `1774439669`, `1774440166`)
- Changing the dropdown calls `selectRun(runId)` which reloads the snapshot list for that run

#### Snapshot Indicator

- Displays: `Snapshot X / Y — snapshot_id`
- X = current 1-based index, Y = total count, snapshot_id = directory name

#### ◀ Prev button

- Calls `stepPrev()`
- If not at the first snapshot, decrements the index and calls `loadSnapshot(idx - 1)`
- `loadSnapshot` calls `GET /api/snapshot/{scenario}/{run_id}/{snapshot_id}` and updates all panels

#### Next ▶ button

- Calls `stepNext()`
- If not at the last snapshot, increments the index and calls `loadSnapshot(idx + 1)`

#### ▶ Play button / ⏹ Stop button

- Clicking **▶ Play** starts `toggleAutoPlay()`:
  - Publishes the current snapshot to Kafka immediately
  - Advances to the next snapshot every 3 seconds
  - Publishes each snapshot as it advances
  - Button label changes to **⏹ Stop**
- Clicking **⏹ Stop** calls `stopAutoPlay()` and halts the timer

Each advance during auto-play calls `POST /api/publish/next` with the current snapshot ID, which publishes the next snapshot's 7 files to their respective Kafka topics.

#### ⬆ Pub All button

- Calls `publishAll()`
- `POST /api/publish/all` with `{scenario, run_id}`
- Publishes all snapshots in the current run sequentially
- Logs each result to the Publish Log (right side of Kafka Inspector)

#### Pipeline Badge

- Shows `● Idle`, `● Publishing`, or `● Error`
- Updates during publish operations
- Dot color: grey (idle), green (active), red (error)

---

### 6.2 Run Controls

The controls between the scenario buttons and the tab bar. Described above in section 6.1.

---

### 6.3 Tab: Agent Pipeline

**Default tab**. Shows the real-time state of all 6 agents.

#### Pipeline Flow Bar

A horizontal strip at the top showing 7 stages:
```
Ingestion → Monitoring → Prediction → RCA → Decision → Remediation → Reporting
```
Each stage has:
- A **dot** that lights up green when that stage has processed data
- A **label** (stage name)
- A **sub-label** (e.g., "Health → Alerts", "Features → Risks")

The dots reflect whether the corresponding Kafka topic has any messages in it. Updated every 5 seconds via `GET /api/pipeline/state`.

#### 6 Agent Cards

Each card shows one agent's current input and output. They are updated live from the pipeline state poll.

**Common card structure**:
- **Header**: Agent icon, name, description, status badge
- **Status badge**: `IDLE` (grey), `ACTIVE` (green), `WARNING` (yellow), `CRITICAL` (red)
  - Badge text is taken from the latest output message's `severity`, `risk_level`, or `status` field
- **Input pane** (left half):
  - Arrow label showing `↓ INPUT`
  - The input Kafka topic name
  - Last received input message formatted as JSON
- **Output pane** (right half):
  - Arrow label showing `↑ OUTPUT`
  - The output Kafka topic name
  - Last produced output message formatted as JSON

| Card | Input Topic | Output Topic |
|---|---|---|
| 📡 Monitoring Agent | `jatayu.telemetry.service_health` | `monitoring.alerts + monitoring.incidents` |
| 🔮 Prediction Agent | `jatayu.telemetry.service_features` | `jatayu.agent.prediction.risks` |
| 🔍 RCA Agent | `jatayu.agent.monitoring.alerts` | `jatayu.agent.rca.results` |
| ⚖️ Decision Agent | `jatayu.agent.rca.results` | `jatayu.agent.decision.intents` |
| 🔧 Remediation Agent | `jatayu.agent.decision.intents` | `jatayu.agent.remediation.results` |
| 📋 Reporting Agent | `jatayu.agent.remediation.results` | `jatayu.agent.reporting.incidents` |

#### Kafka Topic Inspector

A wide panel at the bottom of the Pipeline tab.

**Topic selector** (dropdown):
Choosing a topic immediately calls `refreshTopic()` which calls `GET /api/topic/{topic_name}?max_messages=20` and displays the last 20 messages as formatted JSON in the left pane.

Available topics:
- `jatayu.snapshot.context`
- `jatayu.telemetry.service_health`
- `jatayu.telemetry.service_features`
- `jatayu.agent.monitoring.alerts`
- `jatayu.agent.monitoring.incidents`
- `jatayu.agent.prediction.risks`
- `jatayu.agent.rca.results`
- `jatayu.agent.decision.intents`
- `jatayu.agent.remediation.results`
- `jatayu.agent.reporting.incidents`

**↻ Refresh button**:
- Re-fetches the currently selected topic and updates the JSON pane.

**✕ Clear Log button**:
- Clears the Publish Log panel on the right side (the chronological log of all publish operations performed during this session).

---

### 6.4 Tab: Overview

A summary dashboard for quick situational awareness.

#### Service Health panel

- Calls `GET /api/dashboard/state` to load the latest health records.
- Renders one chip per service with a colored status indicator:
  - Green: `healthy`
  - Yellow: `degraded`
  - Red: `failed`
  - Grey: `unknown`
- Shows service name + severity score as a percentage.
- The timestamp of the last health snapshot appears in the panel header.

#### Monitoring Alerts panel

- Shows the last N alerts from `jatayu.agent.monitoring.alerts` as cards.
- Each card shows: severity badge, service name, score, anomaly flags.
- Updates live every 5 seconds from the pipeline state poll.

#### Prediction Risks panel

- Shows the latest prediction risk events from `jatayu.agent.prediction.risks`.
- Each card shows: risk level, service, predicted failure type, first 2 rationale lines.

#### Stats Row

Six stat cards that update every 5 seconds:

| Stat | Source |
|---|---|
| Alerts | Count of messages in `monitoring.alerts` |
| Risks | Count of messages in `prediction.risks` |
| RCA Results | Count of messages in `rca.results` |
| Actions | Count of messages in `decision.intents` |
| Remediated | Count of messages in `remediation.results` |
| Incidents | Count of messages in `reporting.incidents` |

---

### 6.5 Tab: Graphs

Time-series charts for telemetry data across snapshots. Requires clicking **↻ Load Charts** to populate.

#### Service Filter (dropdown)

- Options: All Services, frontend, cartservice, checkoutservice, recommendationservice, paymentservice, productcatalogservice, redis-cart
- Filters all charts to show only the selected service's data

#### ↻ Load Charts button

- Calls `GET /api/metrics/timeseries?scenario={s}&run_id={r}` with the current scenario/run
- Populates 6 Chart.js charts:
  1. **CPU Usage (millicores)** — line chart, one line per service, x-axis = snapshots
  2. **Memory Usage (MiB)** — line chart
  3. **HTTP Error Rate** — bar chart
  4. **Average Latency (ms)** — line chart
  5. **Failure Prediction Probability** — line chart (from pipeline prediction data)
  6. **Incident Severity Timeline** — line chart (from pipeline incident data)

---

### 6.6 Tab: Service Graph

An interactive visualization of the service dependency graph.

#### ↻ Load Graph button

- Calls `GET /api/graph` to get the dependency map
- Calls `GET /api/dashboard/state` to get current health status
- Renders an SVG graph where:
  - Each node is a service circle, sized by criticality
  - Arrows point from dependent → dependency
  - Node color reflects current health (green/yellow/red/grey)
  - Dragging nodes repositions them

#### Tooltips

Hovering a node shows a tooltip with service name, health status, and severity score.

#### Click a node

Clicking a node expands a detail pane at the bottom of the tab showing: service name, health status, criticality, team, dependencies list, anomaly flags.

#### Legend

- Green circle = Healthy
- Yellow circle = Degraded
- Red circle = Failed
- Grey circle = Unknown
- Node size = criticality (critical = largest)

---

### 6.7 Tab: Prediction

A dedicated panel for the Prediction Agent's risk assessments.

#### ● LIVE pill

Indicates this panel auto-updates.

#### ↻ Refresh button

- Calls `GET /api/prediction/summary`
- The summary endpoint deduplicates predictions per service (keeps the latest per service) and sorts by risk_score descending.

#### Prediction cards

One card per at-risk service showing:
- Risk level badge (CRITICAL / HIGH / MEDIUM in matching colors)
- Service name
- Risk score (0.00 – 0.99)
- Predicted failure type
- Trend (rising / stable / recovering)
- Time to failure estimate ("imminent (<5 min)", "5–15 minutes", etc.)
- Up to 3 rationale lines (e.g., "CPU rising sharply: 820m (was 350m)")

---

### 6.8 Tab: Data Explorer

A file browser and log viewer for the raw snapshot data.

#### Snapshot Data panel — File Tabs

Seven buttons that each load a different JSON file from the currently selected snapshot:

| Tab | File | Content |
|---|---|---|
| Context | `snapshot_context.json` | run_id, scenario, snapshot time, index |
| K8s Events | `k8s_events.json` | Pod kills, probe failures, restarts |
| Pod Metrics | `pod_metrics.json` | CPU, memory per pod |
| Pod Status | `pod_status.json` | Ready status, restart counts |
| Features | `service_features.json` | Aggregated per-service features |
| Health | `service_health.json` | Status, severity, anomaly flags, evidence |

Clicking a tab calls `GET /api/snapshot/{scenario}/{run_id}/{snapshot_id}` and renders the corresponding file as formatted JSON.

#### ⎘ Copy button

Copies the currently displayed JSON to the clipboard. Shows a ✓ confirmation for 2 seconds.

#### Log Viewer panel

Displays `log_events.json` records in a human-friendly format.

**Service filter** (dropdown):
- Auto-populated with all unique service names from the log
- Selecting a service shows only that service's logs

**Severity filter** (dropdown):
- Options: All Levels, Error, Warning, Info
- Filters by log record severity

Each log entry shows:
- Severity badge (ERROR in red, WARNING in yellow, INFO in blue)
- Service name
- Log message
- If available: status code, latency, HTTP method, path

---

### 6.9 Tab: Incidents

Shows all finalized incident reports from the Reporting Agent, plus monitoring incidents with their 5 embedded snapshots.

#### ● LIVE pill

Indicates the incident list auto-updates when new incidents arrive.

#### ↻ Refresh button

- Calls `GET /api/incidents?max=20`
- Re-renders the full incident list

#### Load Snapshot Incidents button

- Calls `GET /api/incidents/monitoring?max=20`
- Loads monitoring agent incidents (which contain 5 telemetry snapshots each)
- Prepends a section header `📸 Snapshot Incidents (N) — 5 telemetry snapshots per incident`
- Renders one card per monitoring incident with:
  - Severity badge and color-coded border
  - Incident ID, service name, incident type
  - Anomaly flags as tags
  - Evidence list (up to 3 items)
  - 5-column mini-snapshot grid showing T1–T5 with CPU, memory, restart count, error count, pod status

#### Incident Badge (red dot on tab)

- Shows the count of reporting incidents
- Increments whenever the pipeline poll detects new incidents
- The badge persists until you dismiss (not explicitly dismissable — just shows the count)

#### Reporting Incident Cards

Each card corresponds to one message from `jatayu.agent.reporting.incidents`:

**Card header row**:
- Severity badge (`SEV-1` in red, `SEV-2` in orange, `SEV-3` in blue)
- Incident ID (e.g., `INC-20260328-0001`)
- Service name
- Remediation status badge (`RESOLVED` in green, `PENDING APPROVAL` in yellow, `FAILED` in red)
- **📸 5 Snapshots button** — only visible when a scenario and run are loaded in the launcher. Clicking it opens the Incident Snapshot Viewer.
- Relative timestamp (e.g., "2 minutes ago")

**Card body**:
- One-line summary (e.g., "[SEV-1] INC-20260328-0001: Pod Termination detected in redis-cart — rollout_restart applied successfully")
- RCA reasoning paragraph (if present)
- Detail grid: Failure Type, Confidence %, Action Taken, Impacted Services, Recovery Time, Impact Assessment

**kubectl command** (if present):
- Highlighted code block: `kubectl rollout restart deployment/redis-cart -n default`

**Collapsible sections** (click to expand):
- **Agent Timeline**: Phase-by-phase log of what each agent did
- **Evidence (N)**: List of evidence strings that triggered the alert
- **Runbook Steps**: Step-by-step remediation guide
- **Prevention Recommendations**: 3–6 recommendations to prevent recurrence
- **Full Incident Report**: The complete human-readable post-mortem text

#### Incident Snapshot Viewer

Appears when clicking **📸 5 Snapshots** on any incident card.

- Calls `GET /api/incidents/snapshots?scenario={s}&run_id={r}`
- Loads the first 5 snapshot directories for the current run
- Renders a 5-column grid, one column per snapshot:
  - **Snapshot N** header
  - CPU (millicores)
  - Memory (MiB)
  - Restart Count
  - Status (colored green/yellow/red)
  - Error Count
  - Anomaly flags as tags

The viewer floats above the incident list. **✕ Close** hides it.

---

### 6.10 Tab: Approval Panel

For remediations that were deferred because `auto_execute = false` (critical services or low-confidence RCA).

#### ● LIVE pill + ↻ Refresh button

- Refresh calls `GET /api/remediation/approvals` and re-renders the queue

#### Approval Queue

Each pending item shows:
- Incident ID
- Action (e.g., `manual_approval` or `rollout_restart`)
- Service name
- Failure type and confidence
- `auto_execute = false` reason
- Proposed kubectl command

**✓ Approve button**:
- Calls `POST /api/remediation/approve` with `{incident_id, action, approved: true}`
- Moves the item from the queue to the Approval History section
- Records approver timestamp

**✗ Reject button**:
- Calls `POST /api/remediation/approve` with `{incident_id, action, approved: false}`
- Moves the item to Approval History as rejected

**Warning bar**:
`⚠ Critical and high-risk remediations require explicit operator approval before execution.`

#### Approval History

Scroll log of all decisions made this session, showing: incident_id, action, service, approved/rejected, time.

#### Approval Badge (yellow dot on tab)

Increments when new items appear in the approval queue. Decrements as items are actioned.

---

### 6.11 Tab: Registry

Read-only view of the service registry.

**Loaded automatically** on first visit via `GET /api/registry`.

#### Registry Cards

One card per service, sorted by criticality (critical first). Each card shows:

| Field | Description |
|---|---|
| Service name | e.g., `frontend` |
| Team | Owning team |
| Criticality badge | CRITICAL / HIGH / MEDIUM / LOW in matching colors |
| K8s Resource | e.g., `deployment/frontend` |
| Namespace | e.g., `default` |
| Adapter | e.g., `kubernetes` |
| Auto Remediate | ✓ Yes (green) or ✗ Manual (red) |
| Dependencies | Comma-separated list of upstream services |
| Remediation policies | Tags: `restart_pod`, `scale_out`, `manual_approval`, etc. |

---

## 7. API Endpoints — Complete Reference

All endpoints are prefixed with `/api`.

### Dataset & Snapshot

| Method | Path | Description |
|---|---|---|
| `GET` | `/scenarios` | List available scenarios |
| `GET` | `/runs/{scenario}` | List run IDs for a scenario |
| `GET` | `/snapshots/{scenario}/{run_id}` | List snapshot directory names |
| `GET` | `/snapshot/{scenario}/{run_id}/{snapshot_id}` | Load all 7 JSON files for a snapshot |

### Publishing Snapshots to Kafka

| Method | Path | Body | Description |
|---|---|---|---|
| `POST` | `/publish/snapshot` | `{scenario, run_id, snapshot_id}` | Publish one snapshot |
| `POST` | `/publish/next` | `{scenario, run_id, current_snapshot_id}` | Publish next snapshot in sequence |
| `POST` | `/publish/all` | `{scenario, run_id}` | Publish every snapshot in a run |

### Kafka Inspection

| Method | Path | Description |
|---|---|---|
| `GET` | `/topic/{topic_name}?max_messages=20` | Last N messages from a whitelisted topic |

### Pipeline & Agent Data

| Method | Path | Description |
|---|---|---|
| `GET` | `/pipeline/state` | Latest messages from all 10 topics |
| `GET` | `/dashboard/state` | Alerts, risks, features, health (legacy) |
| `GET` | `/rca/results?max=10` | Latest RCA results |
| `GET` | `/decisions?max=10` | Latest decision intents |
| `GET` | `/remediation?max=10` | Latest remediation results |
| `GET` | `/incidents?max=10` | Latest reporting incidents |
| `GET` | `/incidents/monitoring?max=20` | Monitoring incidents (with 5 snapshots) |
| `GET` | `/incidents/snapshots?scenario=&run_id=` | File-based snapshot data for incident viewer |
| `GET` | `/prediction/summary` | Deduplicated latest risk per service |

### Registry & Graph

| Method | Path | Description |
|---|---|---|
| `GET` | `/registry` | All service registry entries |
| `GET` | `/registry/{service_name}` | Single service metadata |
| `GET` | `/graph` | Service dependency graph |

### Metrics

| Method | Path | Description |
|---|---|---|
| `GET` | `/metrics/timeseries?scenario=&run_id=` | Time-series arrays for all charts |

### Remediation Approvals

| Method | Path | Body | Description |
|---|---|---|---|
| `POST` | `/remediation/approve` | `{incident_id, action, approved, reason}` | Submit approval/rejection |
| `GET` | `/remediation/approvals` | — | All approval decisions this session |

---

## 8. Normalized Dataset Structure

Each scenario has one or more recorded runs. Each run has 5 snapshots captured at regular intervals during the chaos experiment.

```
normalized/
├── c_cpu_spike/
│   └── 1774439669/          ← run_id (Unix timestamp of the run)
│       ├── snapshot_0/      ← earliest snapshot
│       │   ├── snapshot_context.json
│       │   ├── k8s_events.json
│       │   ├── log_events.json
│       │   ├── pod_metrics.json
│       │   ├── pod_status.json
│       │   ├── service_features.json
│       │   └── service_health.json
│       ├── snapshot_1/
│       ├── snapshot_2/
│       ├── snapshot_3/
│       └── snapshot_4/      ← latest snapshot
├── c_network_delay/
├── c_pod_kill/
└── c_redis_failure/
```

### JSON file schemas

**`snapshot_context.json`**
```json
{
  "run_id": "1774439669",
  "scenario": "c_cpu_spike",
  "snapshot_time": "2026-03-25T11:54:30Z",
  "snapshot_index": 0
}
```

**`service_health.json`** (array — one record per service)
```json
[
  {
    "service": "frontend",
    "snapshot_time": "2026-03-25T11:54:30Z",
    "status": "healthy | degraded | failed",
    "severity_score": 0.0,
    "anomaly_flags": ["pod_killed", "high_restarts", "cpu_high", "latency_spike", "http_error_spike", "readiness_probe_failed"],
    "evidence": ["Pod termination event detected", "9 restarts detected"]
  }
]
```

**`service_features.json`** (array — one record per service)
```json
[
  {
    "service": "frontend",
    "snapshot_time": "2026-03-25T11:54:30Z",
    "cpu_millicores": 29,
    "memory_mib": 13,
    "pod_status": "Running | Pending | CrashLoopBackOff | Terminating",
    "ready": "1/1",
    "restart_count": 0,
    "warning_event_count": 3,
    "unhealthy_event_count": 0,
    "failed_create_count": 0,
    "log_error_count": 0,
    "log_warning_count": 2,
    "http_error_count": 0,
    "avg_latency_ms": 104.9,
    "anomaly_flags": [],
    "evidence": []
  }
]
```

**`pod_metrics.json`** (array — one record per pod)
```json
[
  {
    "service": "frontend",
    "pod": "frontend-7d5f5c6b4-xk9p2",
    "cpu_millicores": 29,
    "memory_mib": 13,
    "snapshot_time": "2026-03-25T11:54:30Z"
  }
]
```

**`k8s_events.json`** (array — K8s events during this snapshot window)
```json
[
  {
    "service": "frontend",
    "event_type": "Pod Killed | Pod Created | Readiness Probe Failed | OOMKilled",
    "timestamp": "2026-03-25T11:54:28Z",
    "reason": "Killing",
    "message": "Stopping container frontend"
  }
]
```

**`log_events.json`** (array — application log entries)
```json
[
  {
    "service": "frontend",
    "timestamp": "2026-03-25T11:54:29Z",
    "severity": "ERROR | WARNING | INFO",
    "message": "connection timeout to cartservice",
    "status_code": 503,
    "latency_ms": 5000,
    "method": "GET",
    "path": "/api/cart"
  }
]
```

---

## 9. Chaos Scenarios

### c_cpu_spike — CPU Saturation

**Chaos Mesh type**: `StressChaos`
**Target**: `recommendationservice`
**Fault**: 2 CPU stressor workers for 1 minute

**What you see in snapshots**:
- `recommendationservice` CPU → 800+ millicores
- `service_health.status` → degraded or failed
- `anomaly_flags` → `["cpu_high"]`
- Downstream: `frontend` may show increased latency (depends on recommendations)
- Prediction Agent fires a `cpu_saturation` risk with trend = `rising`

**Expected pipeline output**:
- Monitoring: alert + incident for recommendationservice
- Prediction: high/critical risk for recommendationservice
- RCA: root cause = recommendationservice, failure_type = cpu_saturation
- Decision: action = scale_out (increase replicas to 2)
- Remediation: `kubectl scale deployment/recommendationservice --replicas=2`

---

### c_network_delay — Network Latency

**Chaos Mesh type**: `NetworkChaos`
**Target**: `frontend`
**Fault**: 200ms latency added to all egress traffic for 45 seconds

**What you see in snapshots**:
- `frontend` avg_latency_ms → 300+ ms
- `service_features` may show `http_error_count` increasing as timeouts occur
- Downstream services appear healthy (problem is in frontend's calls)
- Prediction Agent fires a `network_degradation` risk with trend = `rising` or `stable`

**Expected pipeline output**:
- Monitoring: warning-level alert for frontend
- Prediction: medium/high risk, predicted_failure_type = network_degradation
- RCA: root cause = frontend, failure_type = network_degradation
- Decision: action = mark_degraded (no restart can fix added latency)
- Remediation: `kubectl annotate deployment/frontend degraded=true`

---

### c_pod_kill — Frontend Pod Termination

**Chaos Mesh type**: `PodChaos`
**Target**: `frontend`
**Fault**: Pod kill for 30 seconds (pod is deleted, K8s will reschedule)

**What you see in snapshots**:
- `frontend` pod_status → Terminating or Pending (while rescheduling)
- `service_health.status` → failed, severity_score → 0.9
- `anomaly_flags` → `["pod_killed", "readiness_probe_failed"]`
- All services depending on frontend show degraded health
- Evidence: "Pod termination event detected", "Readiness probe failure observed"

**Expected pipeline output**:
- Monitoring: critical alert + incident for frontend (SEV-1)
- RCA: root cause = frontend, failure_type = pod_killed, confidence = 0.90
- Decision: action = rollout_restart (frontend is high criticality, safe to auto-remediate)
- Remediation: `kubectl rollout restart deployment/frontend -n default`

---

### c_redis_failure — Redis Pod Kill

**Chaos Mesh type**: `PodChaos`
**Target**: `redis-cart`
**Fault**: Pod kill for 30 seconds

**What you see in snapshots**:
- `redis-cart` status → failed
- `cartservice` → degraded (depends on redis for session storage)
- `checkoutservice` → degraded (depends on cartservice)
- Evidence chains: "Pod termination event detected" (redis-cart) → "connection refused" logs in cartservice
- This is the most complex scenario because it demonstrates dependency propagation

**Expected pipeline output**:
- Monitoring: critical alerts for redis-cart, cartservice, checkoutservice
- RCA: root cause = redis-cart (BFS traversal finds it is the upstream dependency that is failed), propagation_path = [redis-cart, cartservice, checkoutservice], failure_type = pod_killed
- Decision: redis-cart is medium criticality, safe to auto-remediate → rollout_restart, auto_execute = true
- Remediation: `kubectl rollout restart deployment/redis-cart -n default`

---

## 10. Service Registry

Location: `registry/service_registry.json`

The registry is the central policy database used by the Decision Agent and displayed in the Registry tab.

### Fields per service

| Field | Type | Description |
|---|---|---|
| `namespace` | string | Kubernetes namespace (typically "default") |
| `team` | string | Owning team name |
| `deployment` | string | Kubernetes deployment name |
| `k8s_resource` | string | Full resource path (e.g., `deployment/frontend`) |
| `criticality` | `low\|medium\|high\|critical` | Governs whether auto-remediation is allowed |
| `dependencies` | list | Upstream services this service calls |
| `remediation_policies` | list | Allowed remediation actions for this service |
| `adapter` | string | Execution adapter (currently always `kubernetes`) |
| `safe_to_auto_remediate` | bool | If false, Decision Agent always forces `manual_approval` |
| `max_replicas` | int | Upper bound for scale_out action |
| `min_replicas` | int | Lower bound for scale_in |

### Key services

| Service | Criticality | Auto-Remediate | Notes |
|---|---|---|---|
| `frontend` | high | yes | Entry point; restarts are safe |
| `cartservice` | high | yes | Stateless; restart is safe |
| `checkoutservice` | critical | **no** | Payment path; always requires approval |
| `paymentservice` | critical | **no** | Financial transactions |
| `redis-cart` | medium | yes | Session store; restart recovers cleanly |
| `recommendationservice` | low | yes | Non-critical; scale_out preferred |
| `productcatalogservice` | medium | yes | Read-only catalog |
| `emailservice` | low | yes | Best-effort delivery |

---

## 11. Messaging Layer

Location: `messaging/`

### topics.py

Central registry of all Kafka topic names. Any agent imports `TOPICS` dict and uses keys like `TOPICS["agent_monitoring_alerts"]` instead of hardcoding strings. This ensures consistency and makes topic renaming a one-file change.

### producer.py

`get_producer()` returns a singleton `KafkaProducer` configured with:
- `acks="all"` — wait for all in-sync replicas before acknowledging
- `retries=3` — automatic retry on transient errors
- `linger_ms=5` — batch messages for up to 5ms for throughput
- `request_timeout_ms=15000`
- JSON serialization for values, UTF-8 string serialization for keys (service names)

### consumer.py

`get_consumer(*topics, group_id, auto_offset_reset)` returns a `KafkaConsumer`:
- `enable_auto_commit=True` — offsets committed automatically
- `consumer_timeout_ms=2000` — iteration stops after 2s of no messages
- `request_timeout_ms=30000`, `session_timeout_ms=10000`
- JSON deserialization for values

### publisher.py

`publish_snapshot(snapshot_dir: Path)` — maps each of the 7 JSON files to its topic:

| File | Topic |
|---|---|
| `snapshot_context.json` | `jatayu.snapshot.context` |
| `k8s_events.json` | `jatayu.telemetry.k8s_events` |
| `log_events.json` | `jatayu.telemetry.log_events` |
| `pod_metrics.json` | `jatayu.telemetry.pod_metrics` |
| `pod_status.json` | `jatayu.telemetry.pod_status` |
| `service_features.json` | `jatayu.telemetry.service_features` |
| `service_health.json` | `jatayu.telemetry.service_health` |

Each record in the array is sent as a separate Kafka message keyed by the `service` field (or a UUID for context records). Returns a summary with sent/failed counts per file.

### healthcheck.py

`check_kafka_connection(timeout_seconds=5)` — All agents call this on startup. Creates a short-lived consumer and attempts a metadata fetch. Returns `True` if Kafka is reachable, `False` otherwise. Agents exit cleanly if Kafka is unreachable rather than crashing.

---

## 12. Running the System

### Prerequisites

- Docker (for Kafka)
- Python 3.10+
- `pip install -r requirements.txt`

### Step 1 — Start Kafka

```bash
docker-compose up -d
```

This starts a single-node Kafka in KRaft mode on `localhost:9092` with auto-topic creation enabled.

### Step 2 — Start the Dashboard

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` in your browser.

### Step 3 — Start the Agents

Each agent runs as a separate process. Open a terminal for each:

```bash
python -m agents.monitoring_agent
python -m agents.prediction_agent
python -m agents.rca_agent
python -m agents.decision_agent
python -m agents.remediation_agent
python -m agents.reporting_agent
```

All agents check Kafka connectivity on startup and will exit with an error if Kafka is not reachable.

### Step 4 — Run a Scenario

1. Open `http://localhost:8000`
2. Click a scenario button (e.g., ⚡ CPU Spike)
3. The run selector populates automatically
4. Click **▶ Play** to auto-play through all 5 snapshots (or **Next ▶** to step manually)
5. Watch the Agent Pipeline tab light up as data flows through each stage
6. Check the Incidents tab for the final post-mortem report
7. If a critical service was involved, check the Approval Panel tab

### Optional — LLM-enhanced RCA

Set one of these environment variables before starting the RCA agent for real LLM reasoning:

```bash
export GROQ_API_KEY=your_key_here    # Preferred (faster, free tier)
export OPENAI_API_KEY=your_key_here  # Alternative
python -m agents.rca_agent
```

Without a key, the RCA agent uses template-based reasoning which is still detailed and context-aware.

---

*JATAYU — Named after the eagle-king in the Ramayana who fought fearlessly to protect what he guarded.*
