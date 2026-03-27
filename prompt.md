Act as a senior enterprise AI architect, distributed systems engineer, Kubernetes platform engineer, AIOps architect, backend engineer, and production-grade Python system designer.

I want you to build a production-ready hackathon-grade Agentic IT Orchestrator / Autonomous AIOps Platform that simulates enterprise-scale monitoring, root cause analysis, decisioning, and remediation across Kubernetes and multi-cloud-style environments.

This is not a toy demo. Design it as a realistic, modular, extensible system that would impress enterprise project reviewers, hackathon judges, and platform engineering teams.

==================================================

1. # PROJECT GOAL

Build an intelligent orchestration platform that can:

- monitor distributed microservices and infrastructure signals
- ingest logs, metrics, traces/events, and cluster state
- normalize telemetry into structured events
- detect anomalies
- perform root cause analysis (RCA)
- make remediation decisions
- execute self-healing actions
- generate incident summaries and remediation reports
- support a service registry so remediation adapters know exactly which service/resource to target and how

The platform should be positioned as an:

- Agentic AIOps Platform
- Autonomous IT Orchestrator
- Self-Healing Infrastructure Control Plane
- SaaS-style Multi-Cloud Infrastructure Management Prototype

# ================================================== 2. PROBLEM STATEMENT / USE CASE

Problem Statement:
Enterprises struggle to manage complex IT infrastructure across multi-cloud environments in real time. Traditional monitoring tools fail to coordinate auto-remediation and predictive maintenance.

Description:
Multiple AI agents autonomously monitor servers, cloud instances, network, Kubernetes workloads, and application health, coordinate fixes, predict failures, and optimize resource allocation.

Why Agentic AI:
A single AI component cannot effectively handle multi-domain monitoring, incident triage, RCA, remediation decisioning, execution, and reporting simultaneously. Multiple specialized agents should collaborate through structured event exchange and A2A-style communication.

Workflow:
Monitoring Agents → Predictive Failure Agents → RCA Agents → Remediation & Deployment Agents → Reporting Agent

IMPORTANT:
Also include a Service Registry in the workflow so adapters and remediation agents can use service metadata, ownership, deployment target, namespace, dependencies, and remediation rules to correctly identify and apply changes.

Required improved workflow:
Telemetry Ingestion → Telemetry Normalizer → Service Registry Lookup → Monitoring Agent → Prediction Agent → RCA Agent → Decision Agent → Remediation/Execution Agent → Reporting Agent → Feedback Loop

# ================================================== 3. CURRENT IMPLEMENTATION CONTEXT TO BUILD AROUND

The orchestrator must work FIRST on a dataset-based telemetry pipeline, not only live streaming.

Current source format:
I already have a telemetry dataset generated from chaos experiments on the Google microservices demo app deployed in Kubernetes.

Target environment:
Google microservices demo:

- frontend
- cartservice
- checkoutservice
- currencyservice
- emailservice
- paymentservice
- productcatalogservice
- recommendationservice
- redis-cart
- shippingservice
- adservice
- loadgenerator

Chaos scenarios already used:

- c_pod_kill
- c_cpu_spike
- c_network_delay
- c_redis_failure

Dataset structure:
dataset/
c_cpu_spike/
RUN_ID/
snapshot_0/
snapshot_1/
snapshot_2/
c_network_delay/
c_pod_kill/
c_redis_failure/

Each snapshot contains:

- pod_metrics.txt
- pods.txt
- events.txt
- logs/
  - frontend.log
  - checkoutservice.log
  - cartservice.log
  - redis-cart.log
- time.txt
  IMPORTANT CONSTRAINT:
  The first version of the orchestrator MUST work directly on this dataset format.
  Do not assume only live Prometheus/OpenTelemetry ingestion.
  Instead, design the system so that dataset mode and streaming mode can share the same normalized internal schemas.

# ================================================== 4. DESIGN PRINCIPLES

Build this as realistic engineering, not fake agent hype.

The system should primarily rely on:

- rule-based reasoning
- graph-based dependency analysis
- timestamp correlation
- anomaly scoring
- simple ML where useful
- optional lightweight prediction module

Do NOT make LLMs the core incident solver.
LLMs are optional only for:

- incident summaries
- remediation explanations
- runbook-style human-readable reports
- optional RAG over past incidents or runbooks

RCA must be based on:

- service dependency graph
- telemetry correlation
- logs + metrics + events + pod state
- identifying the earliest probable failing upstream dependency
- distinguishing root cause from symptom propagation

# ================================================== 5. WHAT TO BUILD

Generate the complete architecture and codebase blueprint for a production-style but hackathon-feasible system with the following components.

A. Ingestion Layer

- dataset reader for snapshot folders
- optional future Kafka/live ingestion abstraction
- parsers for pod_metrics.txt, pods.txt, events.txt, logs, time.txt

B. Telemetry Normalizer
Convert raw snapshot files into normalized structured objects such as:

- ServiceMetric
- PodState
- ClusterEvent
- LogSignal
- SnapshotTelemetry
- IncidentSignal

C. Service Registry
Design and implement a service registry module that stores:

- service name
- namespace
- team/owner
- deployment type
- Kubernetes resource names
- dependency list
- criticality
- remediation policies
- health check metadata
- rollout/restart capability
- scaling rules
- adapter mapping
- command templates or action templates

This registry should be used by:

- RCA engine
- decision engine
- remediation/execution agent
- Kubernetes/cloud adapters

D. Dependency Graph Engine
Build a dependency graph for microservices.
Must support:

- service-to-service dependencies
- impact propagation modeling
- upstream/downstream traversal
- finding earliest anomalous dependency
- graph-based root cause ranking

E. Monitoring Agent
Responsibilities:

- consume normalized snapshot telemetry
- compute health states per service
- detect anomalies from metrics, pod states, logs, events
- emit structured alert/anomaly events

F. Prediction Agent
Responsibilities:

- optional lightweight predictive scoring
- detect risk signals such as rising CPU, restart trend, degradation trend
- forecast possible failure risk from telemetry trends
- emit prediction events
  Keep this lightweight and hackathon-feasible.

G. RCA Agent
Responsibilities:

- correlate anomalies, events, pod states, logs, and dependency graph
- distinguish symptom vs root cause
- score candidate root causes
- output structured RCA result with confidence and evidence

H. Decision Agent
Responsibilities:

- map RCA output to remediation strategies
- enforce rules/policies/safety guards
- decide whether to:
  - restart pod
  - roll out deployment restart
  - scale replicas
  - isolate service
  - mark for manual approval
  - no-op
- produce action intent objects

I. Remediation / Execution Agent
Responsibilities:

- read action intents
- use service registry + adapters to locate actual target resources
- execute remediation against Kubernetes adapter layer
- simulate multi-cloud extensibility via adapter interface
- return execution result and status

J. Reporting Agent
Responsibilities:

- generate incident timeline
- summarize detected issue
- show RCA explanation
- show remediation action taken
- show before/after status
- generate judge-friendly and operator-friendly reports
  K. FastAPI Control Plane
  Build a FastAPI backend exposing APIs such as:

- upload/read dataset run
- process snapshot
- process full run
- get anomalies
- get RCA result
- get remediation plan
- trigger remediation
- get incident summary
- get service registry entries
- get dependency graph

# ================================================== 6. ARCHITECTURE REQUIREMENTS

Use a modular, clean architecture with separation of concerns.

Preferred architecture layers:

- api
- application/services
- domain/models
- agents
- parsers
- registry
- graph
- rca
- decisioning
- execution
- adapters
- reporting
- storage
- config
- utils

The code should be:

- production-oriented
- Python 3.11 compatible
- type hinted
- testable
- extensible
- cleanly structured
- suitable for running in WSL Ubuntu
- hackathon-feasible

# ================================================== 7. KAFKA / EVENT-DRIVEN DESIGN

Even if the first implementation runs offline on folders, design the internal contracts so Kafka can be added later.

Define:

- normalized event schemas
- topic design
- producer/consumer responsibilities
- A2A communication pattern using structured event messages

Suggested event flow:
normalized.telemetry
→ monitoring.alerts
→ prediction.risks
→ rca.results
→ decision.intents
→ remediation.results
→ reporting.incidents

Include sample JSON messages for each.

# ================================================== 8. RCA LOGIC REQUIREMENTS

Design a practical RCA algorithm that works on my available dataset.

It should use:

- pod restarts
- pod not ready / crash states
- abnormal CPU or resource patterns
- Kubernetes events
- log signatures
- dependency graph traversal
- timestamp correlation
- service criticality
- upstream failure precedence

For example:
If frontend fails but cartservice and redis-cart show prior errors, the RCA engine should avoid blaming frontend and instead identify redis-cart or cartservice if evidence supports that.

The RCA engine should output:

- root cause service
- failure type
- confidence score
- evidence list
- impacted services
- remediation recommendation

# ================================================== 9. REMEDIATION ENGINE REQUIREMENTS

Build a rule-based remediation engine first.

Examples:

- pod crashloop → restart/redeploy
- CPU saturation → scale out
- redis unreachable → restart redis / verify service endpoints / rollout restart dependent service if needed
- network delay → mark degraded and recommend traffic shift or retry policy action
- repeated failures → escalate / require human approval

IMPORTANT:
Use Service Registry data so remediation agent knows:

- which Kubernetes resource maps to which logical service
- which namespace to operate in
- which actions are safe
- what command/action template to execute
- what fallback strategy applies

# ================================================== 10. USER EXPERIENCE / REVIEWER IMPACT

This project must look impressive to reviewers.

So design it with:

- strong architecture clarity
- realistic enterprise vocabulary
- visible agent collaboration
- structured RCA output
- explainable remediation decisions
- modular extensibility
- clean APIs
- operational dashboards or JSON outputs that can be demoed clearly

Make the final solution feel like:
“an enterprise-grade autonomous AIOps control plane prototype”

# ================================================== 11. REQUIRED OUTPUT FORMAT

Provide the solution in the following order:

1. Final architecture overview
2. End-to-end workflow
3. Service registry design
4. Module/folder structure
5. Domain models / Pydantic schemas
6. Dataset parser design
7. Telemetry normalization design
8. Dependency graph design
9. Monitoring agent design
10. Prediction agent design
11. RCA agent design
12. Decision agent design
13. Remediation/execution agent design
14. Adapter layer design
15. FastAPI endpoint design
16. Kafka topic and event schema design
17. Step-by-step implementation order
18. Production-ready Python code skeletons for each module
19. Example JSON inputs/outputs
20. Demo flow for hackathon judges
21. README-style explanation of how to run it

# ================================================== 12. CODE GENERATION INSTRUCTIONS

Generate actual code files, not just theory.

Start by producing:

- project folder tree
- core domain models
- parsers for dataset files
- telemetry normalizer
- service registry loader
- dependency graph builder
- monitoring agent
- RCA engine
- decision engine
- remediation executor interface
- FastAPI main app
- example config files
- example service registry file
- example dependency graph config
- example sample outputs

Use:

- Python 3.11
- FastAPI
- Pydantic
- NetworkX for dependency graph
- clean dataclasses or Pydantic models
- structured logging
- uvicorn
- optional Kafka abstraction interface
- no unnecessary complexity

# ================================================== 13. IMPORTANT ENGINEERING CONSTRAINTS

- Keep the system production-style but hackathon-feasible
- Do not overcomplicate with unnecessary distributed infrastructure
- Do not require LLM training
- Do not make tracing mandatory in v1
- Build for dataset-first execution
- Make streaming/Kafka an extensible layer, not a hard dependency
- Use rule-based + graph-based RCA first
- Use service registry centrally in remediation workflow
- Make outputs explainable and demo-friendly
- Prefer correctness, clarity, and modularity over buzzwords

# ================================================== 14. EXECUTION STYLE

When generating the solution:

- think like a principal engineer
- make practical design decisions
- avoid generic filler
- explain why each component exists
- generate code that can actually be implemented
- include comments where useful
- choose realistic defaults
- ensure the folder structure and code modules align with each other

Now generate the complete production-ready orchestrator blueprint and starter implementation for Cursor AI.
