# JATAYU — Autonomous AIOps Platform
## Document 1 of 10: Project Overview, Configuration & Data Files

---

## What is JATAYU?

JATAYU is an **autonomous AIOps (AI for IT Operations) platform** for Kubernetes microservices. It runs a **6-agent AI pipeline** that detects anomalies, predicts failures, identifies root causes, decides on remediation, executes fixes, and generates incident reports — all in real time via Apache Kafka.

---

## System Architecture

```
Dataset Replay (Snapshot Publisher)
        │
        ▼  7 telemetry topics
┌────────────────────────────────────────────────────┐
│               Apache Kafka (KRaft)                 │
└────────────┬───────────────────────────────────────┘
             │
    ┌────────▼────────┐
    │  [1] Monitoring │── monitoring.alerts ──▶ [3] RCA ──▶ [4] Decision ──▶ [5] Remediation ──▶ [6] Reporting
    │  [2] Prediction │── prediction.risks ──▶ dashboard
    └─────────────────┘
             │
    FastAPI Web Dashboard (http://localhost:8000)
```

**Message topics:**
- 7 telemetry input topics (`jatayu.telemetry.*`, `jatayu.snapshot.context`)
- 6 agent output topics (`jatayu.agent.*`)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agents | Python 3.11 |
| Web Control Plane | FastAPI + Uvicorn |
| Message Bus | Apache Kafka 4.1.2 (KRaft — no ZooKeeper) |
| ML | scikit-learn (Isolation Forest), NumPy |
| Frontend | Jinja2 + Vanilla JS + Chart.js + D3.js |
| Container | Docker + Docker Compose |
| Orchestration | Kubernetes + Helm + Kustomize |
| Cloud IaC | Terraform (GCP) |
| CI/CD | GitHub Actions + Cloud Build |

---

## Quick Start

```bash
# 1. Start Kafka
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start FastAPI dashboard
uvicorn app.main:app --reload --port 8000

# 4. Start all 6 agents (separate terminals)
python -m agents.monitoring_agent
python -m agents.prediction_agent
python -m agents.rca_agent
python -m agents.decision_agent
python -m agents.remediation_agent
python -m agents.reporting_agent

# 5. Open http://localhost:8000
# 6. Select a chaos scenario and click "Pub All" to replay it
```

---

## FILE: `docker-compose.yml`

```yaml
services:
  kafka:
    image: apache/kafka:4.1.2
    container_name: jatayu-kafka
    hostname: kafka
    restart: unless-stopped
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
      KAFKA_LOG_RETENTION_HOURS: 24
```

---

## FILE: `requirements.txt`

```
# Control plane + agents runtime deps
fastapi==0.115.4
uvicorn==0.30.6
jinja2==3.1.6
aiofiles==24.1.0
kafka-python==2.0.2

# Optional ML support for prediction agent
numpy==1.26.4
scikit-learn==1.4.2
```

---

## FILE: `dependency_graph.json`

This file defines the upstream dependencies for each microservice. Used by the RCA Agent for graph traversal to distinguish root causes from cascading symptoms.

```json
{
  "frontend": ["cartservice", "checkoutservice", "recommendationservice", "productcatalogservice"],
  "cartservice": ["redis-cart"],
  "checkoutservice": ["paymentservice", "shippingservice", "emailservice", "currencyservice", "cartservice", "productcatalogservice"],
  "recommendationservice": ["productcatalogservice"],
  "paymentservice": [],
  "shippingservice": [],
  "emailservice": [],
  "currencyservice": [],
  "productcatalogservice": [],
  "redis-cart": []
}
```

**Reading the graph:** If `cartservice` depends on `redis-cart` and both fail, `redis-cart` is the root cause. The RCA Agent traverses this graph using BFS to find the earliest-failing upstream service.

---

## FILE: `registry/service_registry.json`

The service registry defines metadata, criticality, remediation policies, and auto-remediation flags for each service. Used by the Decision Agent to apply safety guards.

```json
{
  "services": {
    "frontend": {
      "namespace": "default", "team": "platform", "deployment": "frontend",
      "k8s_resource": "deployment/frontend", "criticality": "high",
      "dependencies": ["cartservice", "checkoutservice", "recommendationservice", "productcatalogservice"],
      "remediation_policies": ["restart_pod", "rollout_restart"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 3, "min_replicas": 1
    },
    "cartservice": {
      "namespace": "default", "team": "cart", "deployment": "cartservice",
      "k8s_resource": "deployment/cartservice", "criticality": "high",
      "dependencies": ["redis-cart"],
      "remediation_policies": ["restart_pod", "rollout_restart"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 2, "min_replicas": 1
    },
    "checkoutservice": {
      "namespace": "default", "team": "checkout", "deployment": "checkoutservice",
      "k8s_resource": "deployment/checkoutservice", "criticality": "critical",
      "dependencies": ["paymentservice", "shippingservice", "emailservice", "currencyservice", "cartservice", "productcatalogservice"],
      "remediation_policies": ["restart_pod", "scale_out", "manual_approval"],
      "adapter": "kubernetes", "safe_to_auto_remediate": false,
      "max_replicas": 3, "min_replicas": 1
    },
    "paymentservice": {
      "namespace": "default", "team": "payments", "deployment": "paymentservice",
      "k8s_resource": "deployment/paymentservice", "criticality": "critical",
      "dependencies": [],
      "remediation_policies": ["manual_approval"],
      "adapter": "kubernetes", "safe_to_auto_remediate": false,
      "max_replicas": 2, "min_replicas": 1
    },
    "productcatalogservice": {
      "namespace": "default", "team": "catalog", "deployment": "productcatalogservice",
      "k8s_resource": "deployment/productcatalogservice", "criticality": "high",
      "dependencies": [],
      "remediation_policies": ["restart_pod", "rollout_restart", "scale_out"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 3, "min_replicas": 1
    },
    "recommendationservice": {
      "namespace": "default", "team": "discovery", "deployment": "recommendationservice",
      "k8s_resource": "deployment/recommendationservice", "criticality": "medium",
      "dependencies": ["productcatalogservice"],
      "remediation_policies": ["restart_pod", "scale_out"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 3, "min_replicas": 1
    },
    "shippingservice": {
      "namespace": "default", "team": "logistics", "deployment": "shippingservice",
      "k8s_resource": "deployment/shippingservice", "criticality": "medium",
      "dependencies": [],
      "remediation_policies": ["restart_pod", "rollout_restart"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 2, "min_replicas": 1
    },
    "emailservice": {
      "namespace": "default", "team": "notifications", "deployment": "emailservice",
      "k8s_resource": "deployment/emailservice", "criticality": "low",
      "dependencies": [],
      "remediation_policies": ["restart_pod"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 2, "min_replicas": 1
    },
    "currencyservice": {
      "namespace": "default", "team": "finance", "deployment": "currencyservice",
      "k8s_resource": "deployment/currencyservice", "criticality": "high",
      "dependencies": [],
      "remediation_policies": ["restart_pod", "rollout_restart"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 2, "min_replicas": 1
    },
    "redis-cart": {
      "namespace": "default", "team": "infrastructure", "deployment": "redis-cart",
      "k8s_resource": "deployment/redis-cart", "criticality": "high",
      "dependencies": [],
      "remediation_policies": ["restart_pod", "rollout_restart", "verify_endpoints"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 1, "min_replicas": 1
    },
    "adservice": {
      "namespace": "default", "team": "ads", "deployment": "adservice",
      "k8s_resource": "deployment/adservice", "criticality": "low",
      "dependencies": [],
      "remediation_policies": ["restart_pod"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 2, "min_replicas": 1
    },
    "loadgenerator": {
      "namespace": "default", "team": "testing", "deployment": "loadgenerator",
      "k8s_resource": "deployment/loadgenerator", "criticality": "low",
      "dependencies": ["frontend"],
      "remediation_policies": ["restart_pod"],
      "adapter": "kubernetes", "safe_to_auto_remediate": true,
      "max_replicas": 1, "min_replicas": 0
    }
  }
}
```

---

## Service Criticality Summary

| Service | Criticality | Auto-Remediate | Team |
|---|---|---|---|
| checkoutservice | CRITICAL | No — manual approval | checkout |
| paymentservice | CRITICAL | No — manual approval | payments |
| frontend | HIGH | Yes | platform |
| cartservice | HIGH | Yes | cart |
| productcatalogservice | HIGH | Yes | catalog |
| currencyservice | HIGH | Yes | finance |
| redis-cart | HIGH | Yes | infrastructure |
| recommendationservice | MEDIUM | Yes | discovery |
| shippingservice | MEDIUM | Yes | logistics |
| emailservice | LOW | Yes | notifications |
| adservice | LOW | Yes | ads |
| loadgenerator | LOW | Yes | testing |

---

## Chaos Scenarios in `dataset/`

| Scenario | Description | Affected Service |
|---|---|---|
| `c_cpu_spike` | CPU resource exhaustion | recommendationservice |
| `c_network_delay` | Network latency injection | frontend (200ms delay) |
| `c_redis_failure` | Pod killed chaos | redis-cart |
| `c_pod_kill` | Pod forcible termination | frontend |

Each scenario contains multiple `run_*` subdirectories, each with 5 numbered snapshot directories. Each snapshot contains: `snapshot_context.json`, `pod_metrics.json`, `pod_status.json`, `service_health.json`, `service_features.json`, `k8s_events.json`, `log_events.json`.
