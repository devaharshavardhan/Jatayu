---
name: JATAYU Project State
description: AIOps platform - full pipeline built with 6 agents, service registry, and complete UI
type: project
---

JATAYU is an Agentic IT Orchestrator / Autonomous AIOps Platform built for hackathon demo on the Google microservices dataset with Kubernetes chaos scenarios.

**Architecture:** FastAPI + Kafka + 6 specialized agents + React-style dark-theme dashboard

**Agents built (all in /agents/):**
- monitoring_agent.py: service_health → monitoring.alerts (pre-existing)
- prediction_agent.py: service_features → prediction.risks (pre-existing)
- rca_agent.py: monitoring.alerts + service_health → rca.results (NEW)
- decision_agent.py: rca.results → decision.intents (NEW)
- remediation_agent.py: decision.intents → remediation.results (NEW)
- reporting_agent.py: remediation.results → reporting.incidents (NEW)

**Service Registry:** /registry/service_registry.json + registry_loader.py (NEW)

**API Endpoints (all at /api/):**
- /pipeline/state - full pipeline state (all 9 topics)
- /rca/results, /decisions, /remediation, /incidents
- /registry, /registry/{service}, /graph

**UI Tabs:** Agent Pipeline (default), Overview, Data Explorer, Incidents, Registry

**Agent Pipeline Tab:** Shows 7-stage flow bar + 6 agent cards each with I/O panels (input topic + last message, output topic + last message)

**Run command:** ./start_platform.sh (starts Kafka via docker compose + FastAPI + all 6 agents)

**Why:** Built for hackathon demo to show enterprise-grade AIOps platform
**How to apply:** When user asks about JATAYU, agents, or wants to run/demo the platform, reference this architecture.
