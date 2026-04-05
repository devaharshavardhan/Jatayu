# JATAYU — Frontend Dashboard
## Files: `app/templates/` · `app/static/app.js` · `app/static/style.css`

---

## Purpose

The JATAYU dashboard is a **real-time single-page web UI** built with:
- **Jinja2** HTML templates rendered server-side by FastAPI
- **Vanilla JavaScript** for API polling, DOM updates, and chart rendering
- **Chart.js** for time-series metric charts (CPU, memory, latency, error rate)
- **D3.js** for the service dependency graph visualisation

The dashboard auto-refreshes every few seconds to show the live state of all Kafka topics, giving a real-time view of the entire 6-agent pipeline.

---

## Dashboard Layout (Panels)

```
┌─────────────────────────────────────────────────────────────────┐
│ JATAYU Control Plane                                            │
├──────────────────┬──────────────────┬───────────────────────────┤
│  Scenario Panel  │  Pipeline Panel  │     Alerts Panel          │
│  (select &       │  (all 10 Kafka   │  (monitoring alerts +     │
│   replay)        │   topics live)   │   incidents)              │
├──────────────────┼──────────────────┼───────────────────────────┤
│  Prediction      │  RCA + Decision  │    Remediation Panel      │
│  Panel           │  Panel           │  (results + approvals)    │
├──────────────────┴──────────────────┴───────────────────────────┤
│                     Telemetry Panel                             │
│       (time-series charts: CPU, Memory, Latency, Errors)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Template Structure

```
app/templates/
├── base.html                     ← base layout, CDN imports
├── dashboard.html                ← main dashboard page
└── partials/
    ├── alerts_panel.html         ← real-time alerts display
    ├── pipeline_panel.html       ← 10-topic pipeline visualisation
    ├── prediction_panel.html     ← ML predictions per service
    ├── scenario_panel.html       ← scenario launcher controls
    ├── snapshot_panel.html       ← snapshot telemetry viewer
    └── telemetry_panel.html      ← raw telemetry/metrics charts
```

---

## `base.html` — Base Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>JATAYU — AIOps Control Plane</title>
    <link rel="stylesheet" href="/static/style.css" />
    <!-- Chart.js for time-series metrics -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <!-- D3.js for dependency graph -->
    <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
    <header class="navbar">
        <div class="brand">
            <span class="brand-icon">⚡</span>
            <span class="brand-name">JATAYU</span>
            <span class="brand-sub">Autonomous AIOps Platform</span>
        </div>
        <div class="status-bar" id="status-bar">
            <span class="status-dot" id="kafka-dot"></span>
            <span id="kafka-status">Connecting...</span>
        </div>
    </header>

    <main class="container">
        {% block content %}{% endblock %}
    </main>

    <script src="/static/app.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

---

## `app/static/app.js` — Frontend JavaScript

The JavaScript handles all API calls, auto-refresh, and DOM updates.

### Key Functions

```javascript
// ── Configuration ──────────────────────────────────────────────

const API_BASE = "/api";
const REFRESH_INTERVAL_MS = 3000;  // Poll every 3 seconds

// ── State ──────────────────────────────────────────────────────

let currentScenario = null;
let currentRunId = null;
let currentSnapshotId = null;
let metricsChart = null;

// ── Scenario Panel ─────────────────────────────────────────────

async function loadScenarios() {
    const resp = await fetch(`${API_BASE}/scenarios`);
    const data = await resp.json();
    const select = document.getElementById("scenario-select");
    select.innerHTML = '<option value="">-- Select Scenario --</option>';
    (data.scenarios || []).forEach(s => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s.replace(/_/g, " ").toUpperCase();
        select.appendChild(opt);
    });
}

async function loadRuns(scenario) {
    const resp = await fetch(`${API_BASE}/runs/${scenario}`);
    const data = await resp.json();
    const select = document.getElementById("run-select");
    select.innerHTML = '<option value="">-- Select Run --</option>';
    (data.runs || []).forEach(r => {
        const opt = document.createElement("option");
        opt.value = r;
        opt.textContent = r;
        select.appendChild(opt);
    });
}

async function publishAllSnapshots() {
    if (!currentScenario || !currentRunId) {
        alert("Please select a scenario and run first.");
        return;
    }
    const btn = document.getElementById("publish-all-btn");
    btn.textContent = "Publishing...";
    btn.disabled = true;

    const resp = await fetch(`${API_BASE}/publish/all`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({scenario: currentScenario, run_id: currentRunId}),
    });
    const data = await resp.json();
    btn.textContent = "Publish All Snapshots";
    btn.disabled = false;

    const summary = data.summary || {};
    showToast(`Published ${summary.sent || 0} records (${summary.failed || 0} failed)`);
}

async function publishNextSnapshot() {
    if (!currentScenario || !currentRunId) return;
    const resp = await fetch(`${API_BASE}/publish/next`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            scenario: currentScenario,
            run_id: currentRunId,
            current_snapshot_id: currentSnapshotId,
        }),
    });
    const data = await resp.json();
    if (data.next_snapshot) {
        currentSnapshotId = data.next_snapshot;
        document.getElementById("current-snapshot").textContent = currentSnapshotId;
    } else {
        showToast("No more snapshots in this run.");
    }
}

// ── Pipeline Panel ─────────────────────────────────────────────

async function refreshPipelineState() {
    const resp = await fetch(`${API_BASE}/pipeline/state`);
    const data = await resp.json();

    const stages = [
        {key: "ingestion", label: "Ingestion", icon: "📥"},
        {key: "telemetry_health", label: "Health Telemetry", icon: "🏥"},
        {key: "telemetry_features", label: "Feature Vectors", icon: "📊"},
        {key: "monitoring_alerts", label: "Monitoring Alerts", icon: "🚨"},
        {key: "monitoring_incidents", label: "Incidents", icon: "🔥"},
        {key: "prediction_risks", label: "Prediction Risks", icon: "🔮"},
        {key: "rca_results", label: "RCA Results", icon: "🔍"},
        {key: "decision_intents", label: "Decision Intents", icon: "⚖️"},
        {key: "remediation_results", label: "Remediation", icon: "🔧"},
        {key: "incidents", label: "Reports", icon: "📋"},
    ];

    const container = document.getElementById("pipeline-stages");
    container.innerHTML = "";

    stages.forEach(stage => {
        const stageData = data[stage.key] || {};
        const messages = stageData.messages || [];
        const count = stageData.count || messages.length;
        const hasData = count > 0;

        const div = document.createElement("div");
        div.className = `pipeline-stage ${hasData ? "active" : "idle"}`;
        div.innerHTML = `
            <div class="stage-icon">${stage.icon}</div>
            <div class="stage-label">${stage.label}</div>
            <div class="stage-count">${count} msgs</div>
        `;
        if (hasData && messages[0]) {
            div.title = JSON.stringify(messages[0], null, 2).substring(0, 300);
        }
        container.appendChild(div);
    });
}

// ── Alerts Panel ───────────────────────────────────────────────

async function refreshAlerts() {
    const resp = await fetch(`${API_BASE}/incidents/monitoring?max=10`);
    const data = await resp.json();
    const messages = data.messages || [];

    const container = document.getElementById("alerts-list");
    if (messages.length === 0) {
        container.innerHTML = '<div class="empty-state">No alerts yet. Publish a scenario to begin.</div>';
        return;
    }

    container.innerHTML = messages.map(msg => {
        const sev = msg.severity || "info";
        const sevClass = sev === "critical" ? "sev-critical" : sev === "warning" ? "sev-warning" : "sev-info";
        return `
        <div class="alert-card ${sevClass}">
            <div class="alert-header">
                <span class="alert-service">${msg.service || "unknown"}</span>
                <span class="alert-severity">${sev.toUpperCase()}</span>
                <span class="alert-type">${msg.incident_type || msg.event_type || ""}</span>
            </div>
            <div class="alert-body">
                <span>Score: ${(msg.severity_score || 0).toFixed(2)}</span>
                <span>Snapshots: ${msg.snapshot_count || 0}</span>
                <span>${(msg.anomaly_flags || []).join(", ")}</span>
            </div>
        </div>`;
    }).join("");
}

// ── Prediction Panel ───────────────────────────────────────────

async function refreshPredictions() {
    const resp = await fetch(`${API_BASE}/prediction/summary`);
    const data = await resp.json();
    const predictions = data.predictions || [];

    const container = document.getElementById("predictions-list");
    if (predictions.length === 0) {
        container.innerHTML = '<div class="empty-state">No predictions yet.</div>';
        return;
    }

    container.innerHTML = predictions.map(p => {
        const levelClass = p.risk_level === "critical" ? "risk-critical"
            : p.risk_level === "high" ? "risk-high"
            : p.risk_level === "medium" ? "risk-medium" : "risk-low";
        const pct = Math.round((p.risk_score || 0) * 100);
        return `
        <div class="prediction-card ${levelClass}">
            <div class="pred-header">
                <span class="pred-service">${p.service}</span>
                <span class="pred-level">${p.risk_level?.toUpperCase()}</span>
            </div>
            <div class="risk-bar-bg">
                <div class="risk-bar-fill" style="width:${pct}%"></div>
            </div>
            <div class="pred-details">
                <span>${pct}% risk</span>
                <span>Trend: ${p.trend}</span>
                <span>ETA: ${p.time_to_failure}</span>
            </div>
            <div class="pred-type">${(p.predicted_failure_type || "").replace(/_/g, " ")}</div>
        </div>`;
    }).join("");
}

// ── Remediation Approval ───────────────────────────────────────

async function approveRemediation(incidentId, action, approved) {
    const resp = await fetch(`${API_BASE}/remediation/approve`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            incident_id: incidentId,
            action: action,
            approved: approved,
            reason: approved ? "Operator approved via dashboard" : "Operator rejected via dashboard",
        }),
    });
    const data = await resp.json();
    showToast(`Remediation ${data.status}: ${incidentId}`);
    refreshIncidents();
}

// ── Time-Series Chart ──────────────────────────────────────────

async function loadMetricsChart(scenario, runId) {
    if (!scenario || !runId) return;
    const resp = await fetch(`${API_BASE}/metrics/timeseries?scenario=${scenario}&run_id=${runId}`);
    const data = await resp.json();

    const ctx = document.getElementById("metrics-chart")?.getContext("2d");
    if (!ctx) return;

    const colors = [
        "#ff6384","#36a2eb","#ffce56","#4bc0c0","#9966ff",
        "#ff9f40","#ff6384","#c9cbcf","#7fff00","#ff4500","#00bfff",
    ];

    const services = data.services || [];
    const labels = data.labels || [];

    if (metricsChart) metricsChart.destroy();

    metricsChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: services.map((svc, i) => ({
                label: svc,
                data: (data.cpu || {})[svc] || [],
                borderColor: colors[i % colors.length],
                backgroundColor: colors[i % colors.length] + "22",
                tension: 0.3,
                pointRadius: 3,
            })),
        },
        options: {
            responsive: true,
            plugins: {
                legend: {position: "bottom"},
                title: {display: true, text: `CPU Usage (millicores) — ${scenario}/${runId}`},
            },
            scales: {
                y: {beginAtZero: true, title: {display: true, text: "CPU (millicores)"}},
            },
        },
    });
}

// ── Utility ────────────────────────────────────────────────────

function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// ── Auto-refresh Loop ──────────────────────────────────────────

function startAutoRefresh() {
    setInterval(() => {
        refreshPipelineState();
        refreshAlerts();
        refreshPredictions();
        refreshIncidents();
    }, REFRESH_INTERVAL_MS);
}

// ── Init ───────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    loadScenarios();
    refreshPipelineState();
    refreshAlerts();
    refreshPredictions();
    startAutoRefresh();
});
```

---

## `app/static/style.css` — Key Styling

```css
/* ── Variables ─────────────────────────────── */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-card: #21262d;
    --border: #30363d;
    --text-primary: #f0f6fc;
    --text-secondary: #8b949e;
    --accent-blue: #58a6ff;
    --accent-green: #3fb950;
    --sev-critical: #f85149;
    --sev-warning: #d29922;
    --sev-info: #58a6ff;
    --risk-critical: #f85149;
    --risk-high: #d29922;
    --risk-medium: #f0a500;
    --risk-low: #3fb950;
}

/* ── Layout ────────────────────────────────── */
body { background: var(--bg-primary); color: var(--text-primary); font-family: 'Inter', monospace; margin: 0; }
.container { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; padding: 16px; }

/* ── Navbar ────────────────────────────────── */
.navbar { background: var(--bg-secondary); border-bottom: 1px solid var(--border);
    padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; }
.brand-name { font-size: 1.4rem; font-weight: 700; color: var(--accent-blue); }
.brand-sub { font-size: 0.8rem; color: var(--text-secondary); margin-left: 8px; }

/* ── Cards ─────────────────────────────────── */
.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.card-title { font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }

/* ── Pipeline Stages ───────────────────────── */
.pipeline-stages { display: flex; flex-wrap: wrap; gap: 8px; }
.pipeline-stage { padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);
    text-align: center; min-width: 80px; cursor: pointer; transition: all 0.2s; }
.pipeline-stage.active { border-color: var(--accent-green); background: rgba(63, 185, 80, 0.1); }
.pipeline-stage.idle { opacity: 0.5; }
.stage-count { font-size: 0.75rem; color: var(--text-secondary); }

/* ── Alert Cards ───────────────────────────── */
.alert-card { padding: 10px 12px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid; }
.sev-critical { border-left-color: var(--sev-critical); background: rgba(248,81,73,0.08); }
.sev-warning { border-left-color: var(--sev-warning); background: rgba(210,153,34,0.08); }
.sev-info { border-left-color: var(--sev-info); background: rgba(88,166,255,0.08); }

/* ── Risk Bars ─────────────────────────────── */
.risk-bar-bg { background: var(--border); border-radius: 4px; height: 6px; margin: 6px 0; }
.risk-bar-fill { height: 6px; border-radius: 4px; background: var(--accent-blue); transition: width 0.3s; }
.risk-critical .risk-bar-fill { background: var(--risk-critical); }
.risk-high .risk-bar-fill { background: var(--risk-high); }
.risk-medium .risk-bar-fill { background: var(--risk-medium); }
.risk-low .risk-bar-fill { background: var(--risk-low); }

/* ── Toast ─────────────────────────────────── */
.toast { position: fixed; bottom: 20px; right: 20px; background: var(--bg-card);
    border: 1px solid var(--border); border-radius: 8px; padding: 12px 20px;
    color: var(--text-primary); z-index: 9999; animation: slideIn 0.3s ease; }
@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

/* ── Buttons ───────────────────────────────── */
.btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.875rem; font-weight: 500; }
.btn-primary { background: var(--accent-blue); color: #0d1117; }
.btn-success { background: var(--accent-green); color: #0d1117; }
.btn-danger { background: var(--sev-critical); color: white; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Empty State ───────────────────────────── */
.empty-state { text-align: center; padding: 24px; color: var(--text-secondary); font-style: italic; }
```

---

## Real-Time Update Strategy

The dashboard uses **client-side polling** (not WebSockets) at a 3-second interval:
1. `refreshPipelineState()` → fetches `/api/pipeline/state` for all 10 Kafka topics
2. `refreshAlerts()` → fetches `/api/incidents/monitoring`
3. `refreshPredictions()` → fetches `/api/prediction/summary`
4. `refreshIncidents()` → fetches `/api/incidents`

All functions use `async/await` with the Fetch API and update the DOM directly.
