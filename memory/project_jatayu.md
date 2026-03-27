---
name: JATAYU Project State
description: Production-grade Dynamic IT Orchestrator — 6-agent AIOps pipeline with Kafka, ML prediction, LLM RCA, charts, D3 dependency graph
type: project
---

JATAYU is a production-grade Dynamic IT Orchestrator / Autonomous AIOps Platform on the Google microservices dataset with Kubernetes chaos scenarios.

**Architecture:** FastAPI + Kafka + 6 specialized agents + dark-theme dashboard with Chart.js + D3.js

**Pipeline:** Telemetry → Normalizer → Kafka → Monitoring → Prediction → RCA → Decision → Remediation → Reporting → Dashboard

**Agents (all in /agents/):**
- monitoring_agent.py: service_health → monitoring.alerts + monitoring.incidents (with 5 snapshots)
- prediction_agent.py: service_features → prediction.risks (Isolation Forest ML + trend + time_to_failure)
- rca_agent.py: monitoring.alerts + service_health → rca.results (LLM reasoning via Groq/OpenAI or template)
- decision_agent.py: rca.results → decision.intents (policy engine + safety guards)
- remediation_agent.py: decision.intents → remediation.results (manual approval required flag)
- reporting_agent.py: remediation.results → reporting.incidents (full human-readable reports)

**Dashboard tabs (at http://localhost:8000):**
- Agent Pipeline (default) — 7-stage flow bar + 6 agent cards with I/O
- Overview — service health grid, alerts list, risks list, stats
- Graphs — Chart.js charts: CPU, Memory, Latency, Error Rate, Prediction Probability, Incident Frequency
- Service Graph — D3.js force-directed service dependency graph with health status colors
- Prediction — probability gauges, trend indicators, time-to-failure per service
- Data Explorer — JSON file viewer + log viewer
- Incidents — incident cards with 5-snapshot viewer, reasoning, prevention recommendations
- Approval Panel — Accept/Reject buttons for pending remediations
- Registry — service registry with criticality and policies

**API Endpoints:**
- /api/pipeline/state, /api/metrics/timeseries, /api/prediction/summary
- /api/remediation/approve (POST), /api/remediation/approvals
- /api/incidents, /api/incidents/monitoring, /api/incidents/snapshots
- /api/rca/results, /api/decisions, /api/graph, /api/registry

**LLM:** Set GROQ_API_KEY or OPENAI_API_KEY for real LLM reasoning in RCA agent.

**Run:** ./start_platform.sh (Kafka + FastAPI :8000 + all 6 agents)
**Why:** Production-grade showcase of enterprise AIOps with chaos engineering.
