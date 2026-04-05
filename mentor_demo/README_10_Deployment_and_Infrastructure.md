# JATAYU — Deployment & Infrastructure
## Files: `docker-compose.yml` · `requirements.txt` · `kubernetes-manifests/` · `helm-chart/` · `terraform/`

---

## Overview

JATAYU supports three deployment modes:

| Mode | Description | Files |
|---|---|---|
| **Local (Docker Compose)** | Single machine dev/demo | `docker-compose.yml` |
| **Kubernetes** | Production cluster | `kubernetes-manifests/`, `helm-chart/`, `kustomize/` |
| **Google Cloud Platform** | Fully managed GKE | `terraform/`, `cloudbuild.yaml` |

---

## 1. Local Development (Docker Compose)

### `docker-compose.yml`

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

**Key points:**
- Uses **Apache Kafka 4.1.2 in KRaft mode** (no ZooKeeper required)
- Single-node broker on `localhost:9092`
- Auto-creates topics (no manual setup needed)
- 24-hour log retention

### Start local Kafka
```bash
docker-compose up -d
```

### Verify Kafka is running
```bash
docker logs jatayu-kafka
# Look for: "Kafka Server started"
```

---

## 2. Python Dependencies

### `requirements.txt`

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

### Installation
```bash
pip install -r requirements.txt
```

### Dependency Breakdown

| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.115.4 | Web framework for the control plane |
| uvicorn | 0.30.6 | ASGI server to run FastAPI |
| jinja2 | 3.1.6 | HTML template rendering |
| aiofiles | 24.1.0 | Async file I/O for FastAPI |
| kafka-python | 2.0.2 | Kafka producer/consumer client |
| numpy | 1.26.4 | Numerical arrays for ML |
| scikit-learn | 1.4.2 | Isolation Forest anomaly detection |

---

## 3. Running the Full Platform Locally

### Step-by-step

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_ORG/Jatayu.git
cd Jatayu

# 2. Start Kafka (KRaft mode, no ZooKeeper)
docker-compose up -d

# 3. Create and activate Python virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux/Mac
# .venv\Scripts\activate        # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Start the FastAPI control plane
uvicorn app.main:app --reload --port 8000

# 6. Start all 6 AI agents (new terminal for each, or background)
python -m agents.monitoring_agent &
python -m agents.prediction_agent &
python -m agents.rca_agent &
python -m agents.decision_agent &
python -m agents.remediation_agent &
python -m agents.reporting_agent &

# 7. Open the dashboard
# Navigate to: http://localhost:8000
```

---

## 4. Kubernetes Deployment

### Kubernetes Manifests

The `kubernetes-manifests/` directory contains raw Kubernetes YAML for deploying JATAYU to any K8s cluster.

```
kubernetes-manifests/
├── namespace.yaml           # jatayu namespace
├── kafka-deployment.yaml    # Kafka StatefulSet
├── kafka-service.yaml       # Kafka Service (ClusterIP)
├── webapp-deployment.yaml   # FastAPI Deployment
├── webapp-service.yaml      # FastAPI Service (LoadBalancer)
├── agents/
│   ├── monitoring-agent.yaml
│   ├── prediction-agent.yaml
│   ├── rca-agent.yaml
│   ├── decision-agent.yaml
│   ├── remediation-agent.yaml
│   └── reporting-agent.yaml
└── configmap.yaml           # Kafka broker config
```

### Apply to cluster
```bash
kubectl apply -f kubernetes-manifests/namespace.yaml
kubectl apply -f kubernetes-manifests/
```

---

## 5. Helm Chart

The `helm-chart/` directory provides a production-ready Helm package.

```
helm-chart/
├── Chart.yaml              # Chart metadata (name: jatayu, version: 0.1.0)
├── values.yaml             # Default values
├── templates/
│   ├── deployment-webapp.yaml
│   ├── deployment-kafka.yaml
│   ├── deployment-agents.yaml
│   ├── service-webapp.yaml
│   ├── service-kafka.yaml
│   ├── configmap.yaml
│   └── ingress.yaml
└── charts/                 # Sub-chart dependencies
```

### Install with Helm
```bash
# Development
helm install jatayu ./helm-chart --namespace jatayu --create-namespace

# Production with custom values
helm install jatayu ./helm-chart \
  --namespace jatayu \
  --create-namespace \
  --set webapp.replicas=2 \
  --set kafka.storage=10Gi \
  --set groqApiKey=YOUR_GROQ_KEY
```

---

## 6. Kustomize Overlays

The `kustomize/` directory provides environment-specific overlays.

```
kustomize/
├── base/                   # Base configuration
│   ├── kustomization.yaml
│   └── ...
├── overlays/
│   ├── development/        # Dev: single replica, debug logging
│   ├── staging/            # Staging: reduced resources
│   └── production/         # Prod: HPA, resource limits, PDB
```

### Apply overlays
```bash
kubectl apply -k kustomize/overlays/production/
```

---

## 7. Google Cloud Platform (Terraform)

The `terraform/` directory provisions the full GCP infrastructure.

```
terraform/
├── main.tf                 # Root module
├── variables.tf            # Input variables
├── outputs.tf              # Output values
└── modules/
    ├── gke/                # Google Kubernetes Engine cluster
    ├── vpc/                # VPC network + subnets
    ├── alloydb/            # AlloyDB PostgreSQL (optional)
    ├── memorystore/        # Redis Memorystore (optional)
    └── iam/                # Service accounts + IAM bindings
```

### GCP Infrastructure Provisioned

| Resource | Purpose |
|---|---|
| GKE Autopilot Cluster | Run all JATAYU workloads |
| VPC Network | Isolated network for cluster |
| Cloud NAT | Outbound internet for private nodes |
| AlloyDB | Persistent incident history (optional) |
| Memorystore (Redis) | Session/cache layer (optional) |
| IAM Service Accounts | Workload identity bindings |

### Deploy to GCP
```bash
cd terraform/
terraform init
terraform plan -var="project_id=your-gcp-project"
terraform apply -var="project_id=your-gcp-project"
```

---

## 8. CI/CD Pipelines

### GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci-main.yaml` | Push to `main` | Run tests, lint, build image |
| `ci-pr.yaml` | Pull Request | Validate code, run unit tests |
| `helm-chart-ci.yaml` | Helm changes | Lint and validate Helm chart |
| `terraform-validate-ci.yaml` | Terraform changes | Validate and plan Terraform |

### `cloudbuild.yaml` (Google Cloud Build)

```yaml
steps:
  # Build Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/jatayu:$COMMIT_SHA', '.']

  # Push to Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/jatayu:$COMMIT_SHA']

  # Deploy to GKE
  - name: 'gcr.io/cloud-builders/kubectl'
    args:
      - 'set'
      - 'image'
      - 'deployment/jatayu-webapp'
      - 'webapp=gcr.io/$PROJECT_ID/jatayu:$COMMIT_SHA'
      - '-n'
      - 'jatayu'

images:
  - 'gcr.io/$PROJECT_ID/jatayu:$COMMIT_SHA'
```

---

## 9. Istio Service Mesh

The `istio-manifests/` directory configures Istio for advanced traffic management.

```
istio-manifests/
├── gateway.yaml            # Istio Gateway for external traffic
├── virtual-services/       # Traffic routing rules
├── destination-rules/      # Load balancing + circuit breakers
├── peer-authentication/    # mTLS configuration
└── telemetry.yaml          # Metrics/tracing config
```

### Key Istio features used
- **mTLS** between all services
- **Circuit breakers** to isolate failing services
- **Traffic mirroring** for canary analysis
- **Distributed tracing** with Jaeger

---

## 10. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `GROQ_API_KEY` | _(none)_ | Groq API key for LLM reasoning in RCA Agent |
| `OPENAI_API_KEY` | _(none)_ | OpenAI API key (fallback if no Groq key) |
| `PORT` | `8000` | FastAPI server port |

---

## 11. Service Registry (`registry/service_registry.json`)

The service registry defines metadata for all 11 microservices:

```json
{
  "services": {
    "cartservice": {
      "criticality": "high",
      "namespace": "default",
      "k8s_resource": "deployment/cartservice",
      "auto_remediate": true,
      "remediation_policies": ["rollout_restart", "scale_out", "restart_pod"]
    },
    "paymentservice": {
      "criticality": "critical",
      "namespace": "default",
      "k8s_resource": "deployment/paymentservice",
      "auto_remediate": false,
      "remediation_policies": ["manual_approval"]
    },
    "checkoutservice": {
      "criticality": "critical",
      "namespace": "default",
      "k8s_resource": "deployment/checkoutservice",
      "auto_remediate": false,
      "remediation_policies": ["manual_approval"]
    },
    "redis-cart": {
      "criticality": "high",
      "namespace": "default",
      "k8s_resource": "deployment/redis-cart",
      "auto_remediate": true,
      "remediation_policies": ["rollout_restart", "restart_pod"]
    }
  }
}
```

### Criticality Levels

| Level | Services | Auto-Remediate |
|---|---|---|
| `critical` | paymentservice, checkoutservice | No — requires human approval |
| `high` | cartservice, redis-cart, frontend | Yes |
| `medium` | recommendationservice, productcatalogservice | Yes |
| `low` | emailservice, adservice, currencyservice | Yes |
