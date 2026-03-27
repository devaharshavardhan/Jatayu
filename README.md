# JATAYU — Agentic IT Orchestrator

An autonomous AIOps platform that detects, diagnoses, and remediates Kubernetes microservice failures using a 6-agent AI pipeline powered by Kafka.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Docker + Docker Compose | Latest |
| Python | 3.10+ |
| (Optional) kubectl | For real K8s remediation |

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd Jatayu

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start everything (Kafka + FastAPI + all 6 agents)
bash start_platform.sh
```

Open **http://localhost:8000** in your browser.

> **Note:** Pressing Ctrl+C stops FastAPI and the agents but **keeps Kafka running**.
> To also stop Kafka: `docker compose down`

---

## Manual Startup (step by step)

### 1. Start Kafka

```bash
docker compose up -d
```

Verify it is up:
```bash
docker ps | grep jatayu-kafka
# should show STATUS: Up
```

Check Kafka logs:
```bash
docker logs jatayu-kafka --tail 30
```

### 2. Start FastAPI

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start the Agent Pipeline

Open 6 separate terminals (or run as background jobs) and start each agent:

```bash
python -m agents.monitoring_agent
python -m agents.prediction_agent
python -m agents.rca_agent
python -m agents.decision_agent
python -m agents.remediation_agent
python -m agents.reporting_agent
```

Or run them all in the background and tail logs:

```bash
mkdir -p logs
python -m agents.monitoring_agent  > logs/agent_monitoring.log  2>&1 &
python -m agents.prediction_agent  > logs/agent_prediction.log  2>&1 &
python -m agents.rca_agent         > logs/agent_rca.log         2>&1 &
python -m agents.decision_agent    > logs/agent_decision.log    2>&1 &
python -m agents.remediation_agent > logs/agent_remediation.log 2>&1 &
python -m agents.reporting_agent   > logs/agent_reporting.log   2>&1 &
```

Watch agent activity:
```bash
tail -f logs/agent_monitoring.log
tail -f logs/agent_rca.log
```

---

## How to Check if New Snapshots Are Being Generated

Snapshots are pre-collected telemetry stored in `/normalized/`. They are **not generated at runtime** — they are replayed through Kafka into the agent pipeline. Here is how to verify the pipeline is working end-to-end:

### Step 1 — Check snapshot files exist

```
normalized/
  c_cpu_spike/
    1774439669/
      snapshot_0/
        snapshot_context.json
        service_health.json
        service_features.json
        pod_metrics.json
        pod_status.json
        k8s_events.json
        log_events.json
      snapshot_1/ ...
      snapshot_2/ ...
  c_pod_kill/
  c_network_delay/
  c_redis_failure/
```

Each scenario has 3 runs × 5 snapshots = **15 snapshots per scenario**, **60 total**.

### Step 2 — Publish a snapshot to Kafka

Use the dashboard or the API directly:

```bash
curl -s -X POST http://localhost:8000/api/publish/snapshot \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"c_cpu_spike","run_id":"1774439669","snapshot_id":"snapshot_0"}' | python -m json.tool
```

Expected response:
```json
{
  "summary": {
    "snapshot_context.json": {"sent": 1,  "failed": 0},
    "service_health.json":   {"sent": 11, "failed": 0},
    "service_features.json": {"sent": 11, "failed": 0},
    "pod_metrics.json":      {"sent": 11, "failed": 0},
    "k8s_events.json":       {"sent": 5,  "failed": 0},
    "log_events.json":       {"sent": 8,  "failed": 0}
  }
}
```

### Step 3 — Verify messages arrived in Kafka topics

```bash
curl -s "http://localhost:8000/api/topic/jatayu.telemetry.service_health?max_messages=5" | python -m json.tool
curl -s "http://localhost:8000/api/topic/jatayu.agent.monitoring.alerts?max_messages=5" | python -m json.tool
curl -s "http://localhost:8000/api/topic/jatayu.agent.rca.results?max_messages=3" | python -m json.tool
```

### Step 4 — Verify agents are processing

Check agent log files for activity:

```bash
# Monitoring agent received health events and generated alerts
grep "ALERT\|INCIDENT\|published" logs/agent_monitoring.log | tail -20

# RCA agent found root causes
grep "root_cause\|confidence\|RCA" logs/agent_rca.log | tail -20

# Remediation agent executed actions
grep "EXEC\|restart\|scale" logs/agent_remediation.log | tail -20
```

### Step 5 — Check the full pipeline state via API

```bash
curl -s http://localhost:8000/api/pipeline/state | python -m json.tool
```

This returns the latest messages from all Kafka topics in one call.

---

## How Snapshots Flow Through the UI

### 1. Select a Scenario (top bar)

Click one of the 4 scenario buttons:

| Button | Scenario | Affected Service |
|--------|----------|-----------------|
| CPU Spike | `c_cpu_spike` | `recommendationservice` CPU stress |
| Network Delay | `c_network_delay` | `frontend` 200ms latency |
| Redis Failure | `c_redis_failure` | `redis-cart` pod kill |
| Pod Kill | `c_pod_kill` | `frontend` pod termination |

This loads the available runs into the **Run** dropdown.

### 2. Navigate Snapshots

| Control | Action |
|---------|--------|
| **◀ Prev / Next ▶** | Step through snapshots one at a time |
| **▶ Play** | Auto-play all snapshots every 3 seconds, publishing each to Kafka |
| **⬆ Pub All** | Publish all 5 snapshots for the selected run to Kafka at once |

The indicator shows: `Snapshot 2 / 5 — snapshot_1`

### 3. Service Health Grid (Overview tab)

When a snapshot loads, the Service Health Grid renders colored chips for all 11 services:

- **Red chip** — `failed` (severity ≥ 0.8, e.g., pod killed)
- **Yellow chip** — `degraded` (severity ≥ 0.4, e.g., high CPU)
- **Green chip** — `healthy`

Each chip shows the service name and severity score. Hover for evidence details.

### 4. Agent Pipeline Tab (default tab)

Shows the live pipeline flow:

```
Ingestion → Telemetry → Monitoring → Prediction → RCA → Decision → Remediation → Reporting
```

Each stage has a dot that pulses green when new messages arrive. The cards below show the latest messages from each Kafka topic in real-time.

### 5. Data Explorer Tab

Browse raw snapshot JSON files:
- Select any of the 7 JSON files per snapshot from the sidebar
- View formatted JSON in the code panel
- Filter log events by service using the dropdown

### 6. Graphs Tab

Time-series charts for CPU, memory, latency, error rate, and restart counts — plotted per service across all snapshots in the selected run.

### 7. Incidents Tab

Lists all generated incident reports from the Reporting agent:
- Incident ID and severity (SEV-1 / SEV-2 / SEV-3)
- Root cause service and failure type
- Confidence score
- Impact assessment
- Remediation actions taken
- Prevention recommendations

### 8. Approval Panel Tab

Shows remediation actions that require human approval (for critical services like `paymentservice`, `checkoutservice`). Click **Approve** or **Reject** for each pending action.

### 9. Prediction Tab

ML-based risk forecasts per service:
- Risk score (0–1)
- Risk level (low / medium / high / critical)
- Predicted failure type
- Trend direction

### 10. Service Graph Tab

Interactive dependency graph showing upstream/downstream relationships. The RCA agent uses this to trace failure propagation across services.

---

## Kafka Topics Reference

| Topic | Published By | Consumed By |
|-------|-------------|-------------|
| `jatayu.snapshot.context` | Publisher | — |
| `jatayu.telemetry.service_health` | Publisher | Monitoring, RCA |
| `jatayu.telemetry.service_features` | Publisher | Prediction |
| `jatayu.telemetry.pod_metrics` | Publisher | — |
| `jatayu.telemetry.pod_status` | Publisher | — |
| `jatayu.telemetry.k8s_events` | Publisher | — |
| `jatayu.telemetry.log_events` | Publisher | — |
| `jatayu.agent.monitoring.alerts` | Monitoring | RCA, Reporting |
| `jatayu.agent.prediction.risks` | Prediction | — |
| `jatayu.agent.rca.results` | RCA | Decision |
| `jatayu.agent.decision.intents` | Decision | Remediation |
| `jatayu.agent.remediation.results` | Remediation | Reporting |
| `jatayu.agent.reporting.incidents` | Reporting | Dashboard |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scenarios` | List chaos scenarios |
| GET | `/api/runs/{scenario}` | List runs for a scenario |
| GET | `/api/snapshots/{scenario}/{run_id}` | List snapshots in a run |
| GET | `/api/snapshot/{scenario}/{run_id}/{snapshot_id}` | Load snapshot JSON files |
| POST | `/api/publish/snapshot` | Publish one snapshot to Kafka |
| POST | `/api/publish/all` | Publish all snapshots for a run |
| GET | `/api/pipeline/state` | Full pipeline state (all topics) |
| GET | `/api/topic/{topic_name}` | Inspect a Kafka topic |
| GET | `/api/incidents` | Incident reports |
| GET | `/api/rca/results` | RCA results |
| GET | `/api/decisions` | Decision intents |
| GET | `/api/remediation` | Remediation results |
| GET | `/api/prediction/summary` | ML prediction summary |
| GET | `/api/metrics/timeseries?scenario=&run_id=` | Time-series metrics |
| GET | `/docs` | Interactive Swagger UI |

---

## Troubleshooting

### Kafka stops unexpectedly

`docker-compose.yml` has `restart: unless-stopped` so Docker will auto-restart the container if it crashes. If Kafka is not running:

```bash
# Check container status
docker ps -a | grep jatayu-kafka

# Restart it
docker compose up -d

# View logs for errors
docker logs jatayu-kafka --tail 50
```

### Agents not processing messages

```bash
# Check if Kafka is reachable via the API
curl http://localhost:8000/api/topic/jatayu.telemetry.service_health

# Restart a specific agent
python -m agents.monitoring_agent
```

### No data in the dashboard

1. Click a scenario button and select a run
2. Click **Pub All** to publish all snapshots to Kafka
3. Wait 5–10 seconds for agents to process
4. Check the **Agent Pipeline** tab for activity dots

### Port 8000 already in use

```bash
# Linux / Mac
lsof -ti :8000 | xargs kill -9

# Windows (PowerShell)
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process
```

---

## Project Structure

```
Jatayu/
├── agents/                  # 6 AI agents
│   ├── monitoring_agent.py  # Health → alerts
│   ├── prediction_agent.py  # ML risk forecasting
│   ├── rca_agent.py         # Root cause analysis
│   ├── decision_agent.py    # RCA → remediation action
│   ├── remediation_agent.py # Execute K8s actions
│   └── reporting_agent.py   # Incident reports
├── app/
│   ├── main.py              # FastAPI app
│   ├── routers/api.py       # REST endpoints
│   ├── services/            # Business logic
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS + JS
├── messaging/               # Kafka producer/consumer/publisher
├── normalized/              # Pre-collected telemetry snapshots
│   └── {scenario}/{run_id}/{snapshot_id}/  (7 JSON files each)
├── registry/                # Service registry + dependency graph
├── logs/                    # Agent log files
├── docker-compose.yml       # Kafka (KRaft, single-node)
└── start_platform.sh        # One-command startup script
```
