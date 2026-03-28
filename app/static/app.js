/* =====================================================================
   JATAYU Dashboard — app.js  (Full Pipeline Edition)
   ===================================================================== */

// ── API helpers ─────────────────────────────────────────────────────────
const api = {
  runs:              (s)          => fetch(`/api/runs/${s}`).then(r => r.json()),
  snapshots:         (s, r)       => fetch(`/api/snapshots/${s}/${r}`).then(r => r.json()),
  snapshot:          (s, r, n)    => fetch(`/api/snapshot/${s}/${r}/${n}`).then(r => r.json()),
  publishSnapshot:   (p)          => fetch('/api/publish/snapshot', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) }).then(r => r.json()),
  publishAll:        (p)          => fetch('/api/publish/all', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) }).then(r => r.json()),
  topic:             (t, n=20)    => fetch(`/api/topic/${encodeURIComponent(t)}?max_messages=${n}`).then(r => r.json()),
  pipelineState:     ()           => fetch('/api/pipeline/state').then(r => r.json()),
  incidents:         (n=10)       => fetch(`/api/incidents?max=${n}`).then(r => r.json()),
  monitoringIncidents: (n=20)     => fetch(`/api/incidents/monitoring?max=${n}`).then(r => r.json()),
  registry:          ()           => fetch('/api/registry').then(r => r.json()),
  graph:             ()           => fetch('/api/graph').then(r => r.json()),
  timeseries:        (s, r)       => fetch(`/api/metrics/timeseries?scenario=${encodeURIComponent(s)}&run_id=${encodeURIComponent(r)}`).then(r => r.json()),
  predictionSummary: ()           => fetch('/api/prediction/summary').then(r => r.json()),
  approveRemediation:(p)          => fetch('/api/remediation/approve', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) }).then(r => r.json()),
  approvals:         ()           => fetch('/api/remediation/approvals').then(r => r.json()),
  incidentSnapshots: (s, r)       => fetch(`/api/incidents/snapshots?scenario=${encodeURIComponent(s)}&run_id=${encodeURIComponent(r)}`).then(r => r.json()),
};

// ── App state ────────────────────────────────────────────────────────────
const state = {
  scenario: null,
  run: null,
  snapshots: [],
  snapIdx: -1,
  data: {},
  activeFile: 'snapshot_context.json',
  autoTimer: null,
  logEntries: [],
  pipelineData: {},
  incidentCount: 0,
  activeTab: 'pipeline',
};

// ── DOM helpers ──────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ── Utility ──────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function fmtJson(obj, maxLines = 18) {
  if (!obj) return '—';
  const str = JSON.stringify(obj, null, 2);
  const lines = str.split('\n');
  if (lines.length <= maxLines) return str;
  return lines.slice(0, maxLines).join('\n') + '\n  … (' + (lines.length - maxLines) + ' more lines)';
}

function timeAgo(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const diff = Math.floor((Date.now() - d) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
    return d.toLocaleTimeString();
  } catch { return ''; }
}

// ══════════════════════════════════════════════════════════════════════════
//  TAB NAVIGATION
// ══════════════════════════════════════════════════════════════════════════
$$('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    switchTab(tab);
  });
});

function switchTab(tab) {
  state.activeTab = tab;
  $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  $$('.tab-content').forEach(c => c.classList.toggle('active', c.id === `tab-${tab}`));

  // Lazy load tab data
  if (tab === 'incidents')   loadIncidentsTab();
  if (tab === 'registry')    loadRegistryTab();
  if (tab === 'depgraph')    loadDepGraph();
  if (tab === 'prediction')  loadPredictionPanel();
  if (tab === 'remediation') loadApprovalPanel();
  if (tab === 'graphs')      { /* charts load on button click */ }
}

// ══════════════════════════════════════════════════════════════════════════
//  SCENARIO SELECTION
// ══════════════════════════════════════════════════════════════════════════
async function selectScenario(scenario) {
  state.scenario = scenario;
  state.run = null; state.snapshots = []; state.snapIdx = -1; state.data = {};

  $$('.scn-btn').forEach(b => b.classList.toggle('active', b.dataset.scenario === scenario));
  stopAutoPlay();
  setStatus('Loading runs…', 'active');

  try {
    const { runs } = await api.runs(scenario);
    $('run-sel').innerHTML = runs.length
      ? runs.map(r => `<option value="${r}">${r}</option>`).join('')
      : '<option value="">No runs found</option>';
    if (runs.length) await selectRun(runs[0]);
  } catch { setStatus('Error loading runs', 'error'); }
}

async function selectRun(runId) {
  state.run = runId; state.snapshots = []; state.snapIdx = -1; state.data = {};
  try {
    const { snapshots } = await api.snapshots(state.scenario, runId);
    state.snapshots = snapshots || [];
    updateSnapIndicator();
    if (state.snapshots.length) await loadSnapshot(0);
    setStatus(`Run ${runId}`, 'active');
  } catch { setStatus('Error loading snapshots', 'error'); }
}

// ══════════════════════════════════════════════════════════════════════════
//  SNAPSHOT NAVIGATION
// ══════════════════════════════════════════════════════════════════════════
async function loadSnapshot(idx) {
  if (!state.scenario || !state.run) return;
  if (idx < 0 || idx >= state.snapshots.length) return;
  state.snapIdx = idx;
  updateSnapIndicator();
  const snapId = state.snapshots[idx];
  setStatus(`Loading ${snapId}…`, 'active');
  try {
    const res = await api.snapshot(state.scenario, state.run, snapId);
    state.data = res.data || {};
    renderHealthGrid(state.data['service_health.json']);
    renderLogFeed(state.data['log_events.json']);
    renderActiveFile();
    setStatus(`Snapshot ${idx+1}/${state.snapshots.length}`, 'active');
  } catch (e) {
    $('snap-json').textContent = `Error: ${e.message}`;
    setStatus('Error', 'error');
  }
}

function updateSnapIndicator() {
  const total = state.snapshots.length;
  const cur   = state.snapIdx + 1;
  $('snap-indicator').textContent = total
    ? `Snapshot ${cur} / ${total} — ${state.snapshots[state.snapIdx] || ''}`
    : 'Snapshot — / —';
}

async function stepPrev() { if (state.snapIdx > 0) await loadSnapshot(state.snapIdx - 1); }
async function stepNext() { if (state.snapIdx < state.snapshots.length - 1) await loadSnapshot(state.snapIdx + 1); }

function toggleAutoPlay() { state.autoTimer ? stopAutoPlay() : startAutoPlay(); }

function startAutoPlay() {
  if (!state.snapshots.length) return;
  const autoBtn = $('btn-auto');
  autoBtn.textContent = '⏹ Stop'; autoBtn.classList.add('playing');
  if (state.snapIdx < 0) loadSnapshot(0);
  state.autoTimer = setInterval(async () => {
    const next = state.snapIdx + 1;
    if (next >= state.snapshots.length) { stopAutoPlay(); return; }
    await loadSnapshot(next);
    const snapId = state.snapshots[next];
    if (snapId) {
      api.publishSnapshot({ scenario: state.scenario, run_id: state.run, snapshot_id: snapId })
        .then(res => logPublish(snapId, res.summary));
    }
  }, 3000);
}

function stopAutoPlay() {
  if (state.autoTimer) { clearInterval(state.autoTimer); state.autoTimer = null; }
  const autoBtn = $('btn-auto');
  autoBtn.textContent = '▶ Play'; autoBtn.classList.remove('playing');
}

// ── Publish All ───────────────────────────────────────────────────────────
async function publishAll() {
  if (!state.scenario || !state.run) return;
  setStatus('Publishing all…', 'active');
  try {
    const res = await api.publishAll({ scenario: state.scenario, run_id: state.run });
    logPublish('ALL', res.summary);
    setStatus('Published all', 'active');
  } catch { setStatus('Publish error', 'error'); }
}

function logPublish(snapId, summary) {
  const ts = new Date().toLocaleTimeString();
  const sent   = summary?.sent ?? summary?.total_sent ?? '?';
  const failed = summary?.failed ?? summary?.total_failed ?? 0;
  const cls    = failed > 0 ? 'pub-err' : 'pub-ok';
  const status = `<span class="${cls}">✓ ${sent} sent${failed > 0 ? `, ${failed} failed` : ''}</span>`;
  const plog = $('publish-log');
  const placeholder = plog.querySelector('.muted');
  if (placeholder) placeholder.remove();
  const entry = document.createElement('div');
  entry.className = 'pub-entry';
  entry.innerHTML = `<span class="pub-ts">${ts}</span> ${snapId} — ${status}`;
  plog.insertBefore(entry, plog.firstChild);
  while (plog.children.length > 20) plog.lastChild.remove();
}

// ══════════════════════════════════════════════════════════════════════════
//  RENDER: SERVICE HEALTH GRID
// ══════════════════════════════════════════════════════════════════════════
function renderHealthGrid(healthData) {
  const grid = $('health-grid');
  if (!healthData || !healthData.length) {
    grid.innerHTML = '<div class="muted small" style="padding:10px 14px">No health data.</div>';
    return;
  }
  const sorted = [...healthData].sort((a, b) => {
    const order = { failed: 0, degraded: 1, healthy: 2 };
    return (order[a.status] ?? 3) - (order[b.status] ?? 3);
  });
  const realServices = new Set(['frontend','cartservice','checkoutservice','recommendationservice',
    'productcatalogservice','paymentservice','shippingservice','emailservice',
    'currencyservice','adservice','redis-cart','loadgenerator']);
  const chips = sorted
    .filter(h => realServices.has(h.service) || h.status !== 'healthy')
    .map(h => {
      const score = h.severity_score != null ? ` ${(h.severity_score*100).toFixed(0)}%` : '';
      return `<div class="health-chip chip-${h.status||'unknown'}" title="${escHtml((h.evidence||[]).join('\n')||h.service)}">
        <span class="status-dot dot-${h.status||'unknown'}"></span>
        <span class="svc-name">${h.service}</span>
        <span class="svc-score">${score}</span>
      </div>`;
    }).join('');
  grid.innerHTML = chips || '<div class="muted small" style="padding:10px 14px">All services healthy.</div>';
  const snapTime = healthData[0]?.snapshot_time;
  $('health-time').textContent = snapTime ? new Date(snapTime).toLocaleTimeString() : '';
}

// ══════════════════════════════════════════════════════════════════════════
//  RENDER: LOG VIEWER
// ══════════════════════════════════════════════════════════════════════════
function renderLogFeed(logData) {
  state.logEntries = logData || [];
  const services = [...new Set((logData||[]).map(e => e.service).filter(Boolean))].sort();
  const prevSvc = $('log-svc-filter').value;
  $('log-svc-filter').innerHTML = '<option value="">All Services</option>' +
    services.map(s => `<option value="${s}"${s===prevSvc?' selected':''}>${s}</option>`).join('');
  applyLogFilter();
}

function applyLogFilter() {
  const svcFilter = $('log-svc-filter').value;
  const sevFilter = $('log-sev-filter').value;
  const filtered  = state.logEntries.filter(e => {
    if (svcFilter && e.service !== svcFilter) return false;
    if (sevFilter && (e.severity||'').toLowerCase() !== sevFilter) return false;
    return true;
  });
  $('log-count').textContent = `${filtered.length} entries`;
  if (!filtered.length) {
    $('log-feed').innerHTML = '<div class="muted small log-empty" style="padding:10px 14px">No entries match filters.</div>';
    return;
  }
  $('log-feed').innerHTML = filtered.map(e => {
    const sev = (e.severity||'info').toLowerCase();
    let meta = '';
    if (e.status_code) meta += ` [${e.status_code}]`;
    if (e.latency_ms)  meta += ` ${e.latency_ms}ms`;
    if (e.method && e.path) meta += ` ${e.method} ${e.path}`;
    return `<div class="log-line">
      <span class="log-sev sev-${sev}">${sev}</span>
      <span class="log-svc">${e.service||'—'}</span>
      <span class="log-msg">${escHtml(e.message||e.raw||'—')}</span>
      <span class="log-meta">${escHtml(meta)}</span>
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  RENDER: JSON FILE VIEWER
// ══════════════════════════════════════════════════════════════════════════
function renderActiveFile() {
  const content = state.data[state.activeFile];
  $('json-file-label').textContent = state.activeFile;
  $('snap-json').textContent = content !== undefined
    ? JSON.stringify(content, null, 2)
    : `File "${state.activeFile}" not found in this snapshot.`;
}

$$('.ftab').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.ftab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.activeFile = btn.dataset.file;
    renderActiveFile();
  });
});

$('btn-copy-json').addEventListener('click', () => {
  const content = state.data[state.activeFile];
  if (content !== undefined) {
    navigator.clipboard.writeText(JSON.stringify(content, null, 2))
      .then(() => { $('btn-copy-json').textContent = '✓ Copied'; setTimeout(() => $('btn-copy-json').textContent = '⎘ Copy', 1500); });
  }
});

// ══════════════════════════════════════════════════════════════════════════
//  RENDER: ALERTS & RISKS (Overview Tab)
// ══════════════════════════════════════════════════════════════════════════
function renderAlerts(items) {
  const el = $('alerts-list');
  if (!items.length) { el.innerHTML = '<div class="muted small">No alerts yet.</div>'; return; }
  el.innerHTML = items.slice(0, 15).map(a => {
    const sev = (a.severity||'info').toLowerCase();
    const flags = (a.anomaly_flags||[]).join(', ');
    return `<div class="alert-card alert-${sev}">
      <div class="card-top">
        <span class="sev-badge badge-${sev}">${sev}</span>
        <span class="card-svc">${a.service||'—'}</span>
        <span class="card-score">${a.severity_score??''}</span>
      </div>
      <div class="card-body">Status: ${a.status||'—'}</div>
      ${flags ? `<div class="card-flags">${flags}</div>` : ''}
    </div>`;
  }).join('');
}

function renderRisks(items) {
  const el = $('risks-list');
  if (!items.length) { el.innerHTML = '<div class="muted small">No predictions yet.</div>'; return; }
  el.innerHTML = items.slice(0, 15).map(r => {
    const lvl = (r.risk_level||'medium').toLowerCase();
    const rat = (r.rationale||[]).slice(0,2).join(' · ');
    return `<div class="risk-card risk-${lvl}">
      <div class="card-top">
        <span class="sev-badge badge-${lvl}">${lvl}</span>
        <span class="card-svc">${r.service||'—'}</span>
        <span class="card-score">${r.risk_score!=null?r.risk_score.toFixed(2):''}</span>
      </div>
      <div class="card-body">${r.predicted_failure_type||'—'}</div>
      ${rat ? `<div class="card-flags">${rat}</div>` : ''}
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  PIPELINE STATE REFRESH
// ══════════════════════════════════════════════════════════════════════════
async function refreshPipeline() {
  try {
    const ps = await api.pipelineState();
    state.pipelineData = ps;
    updateAgentCards(ps);
    updateStageIndicators(ps);
    updateStats(ps);
    // Also update overview panels if on overview tab
    renderAlerts(ps.monitoring_alerts?.messages || []);
    renderRisks(ps.prediction_risks?.messages   || []);
  } catch { /* silent */ }
}

function getLatest(messages) {
  if (!messages || !messages.length) return null;
  return messages[messages.length - 1];
}

function updateAgentCards(ps) {
  // Monitoring Agent
  updateCard('monitoring',
    getLatest(ps.telemetry_health?.messages),
    getLatest(ps.monitoring_alerts?.messages)
  );
  // Prediction Agent
  updateCard('prediction',
    getLatest(ps.telemetry_features?.messages),
    getLatest(ps.prediction_risks?.messages)
  );
  // RCA Agent
  updateCard('rca',
    getLatest(ps.monitoring_alerts?.messages),
    getLatest(ps.rca_results?.messages)
  );
  // Decision Agent
  updateCard('decision',
    getLatest(ps.rca_results?.messages),
    getLatest(ps.decision_intents?.messages)
  );
  // Remediation Agent
  updateCard('remediation',
    getLatest(ps.decision_intents?.messages),
    getLatest(ps.remediation_results?.messages)
  );
  // Reporting Agent
  updateCard('reporting',
    getLatest(ps.remediation_results?.messages),
    getLatest(ps.incidents?.messages)
  );
}

function updateCard(agent, inputMsg, outputMsg) {
  const inEl  = $(`in-${agent}`);
  const outEl = $(`out-${agent}`);
  const badge = $(`status-${agent}`);

  if (inEl && inputMsg) {
    inEl.textContent = fmtJson(inputMsg);
    inEl.classList.add('has-data');
  }

  if (outEl && outputMsg) {
    outEl.textContent = fmtJson(outputMsg);
    outEl.classList.add('has-data');
    // Update status badge
    if (badge) {
      const sev = outputMsg.severity || outputMsg.risk_level || outputMsg.status || 'active';
      badge.textContent = sev.toUpperCase();
      badge.className = 'agent-status-badge status-' + mapSeverityClass(sev);
    }
  } else if (badge && badge.textContent === 'IDLE') {
    // still idle
  }
}

function mapSeverityClass(s) {
  const v = (s||'').toLowerCase();
  if (['critical','failed','error','sev-1'].includes(v)) return 'critical';
  if (['warning','degraded','high','sev-2'].includes(v)) return 'warning';
  if (['success','healthy','active'].includes(v)) return 'success';
  return 'idle';
}

function updateStageIndicators(ps) {
  const check = (msgs) => msgs && msgs.length > 0;
  const dot = (id, active) => {
    const el = $(`dot-${id}`);
    if (el) el.className = 'stage-dot ' + (active ? 'stage-active' : 'stage-idle');
  };
  const hasIngestion = check(ps.ingestion?.messages);
  const hasMonitor   = check(ps.monitoring_alerts?.messages);
  const hasPredict   = check(ps.prediction_risks?.messages);
  const hasRca       = check(ps.rca_results?.messages);
  const hasDecision  = check(ps.decision_intents?.messages);
  const hasRemediate = check(ps.remediation_results?.messages);
  const hasReport    = check(ps.incidents?.messages);

  dot('ingestion',    hasIngestion);
  dot('monitoring',   hasMonitor);
  dot('prediction',   hasPredict);
  dot('rca',          hasRca);
  dot('decision',     hasDecision);
  dot('remediation',  hasRemediate);
  dot('reporting',    hasReport);
}

function updateStats(ps) {
  $('stat-alerts').textContent     = (ps.monitoring_alerts?.messages||[]).length;
  $('stat-risks').textContent      = (ps.prediction_risks?.messages||[]).length;
  $('stat-rca').textContent        = (ps.rca_results?.messages||[]).length;
  $('stat-decisions').textContent  = (ps.decision_intents?.messages||[]).length;
  $('stat-remediated').textContent = (ps.remediation_results?.messages||[]).length;

  const incLen = (ps.incidents?.messages||[]).length;
  $('stat-incidents').textContent = incLen;

  // Badge on incidents tab
  if (incLen > state.incidentCount) {
    state.incidentCount = incLen;
    const badge = $('incident-badge');
    badge.textContent = incLen;
    badge.classList.remove('hidden');
    if (state.activeTab === 'incidents') loadIncidentsTab();
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  INCIDENTS TAB
// ══════════════════════════════════════════════════════════════════════════
async function loadIncidentsTab() {
  try {
    const res = await api.incidents(20);
    renderIncidents(res.messages || []);
  } catch { /* silent */ }
}

function renderIncidents(items) {
  const el = $('incidents-list');
  if (!items.length) {
    el.innerHTML = '<div class="muted small" style="padding:24px;text-align:center">No incidents yet. Publish a snapshot and let the agent pipeline run.</div>';
    return;
  }
  el.innerHTML = [...items].reverse().map(inc => {
    const sev = inc.severity || 'SEV-3';
    const sevCls = sev === 'SEV-1' ? 'sev-critical' : sev === 'SEV-2' ? 'sev-warning' : 'sev-info-cls';
    const status = inc.remediation_status || inc.resolution_status || 'unknown';
    const statusCls = (status.toLowerCase().includes('resolv') || status === 'success') ? 'rem-success'
      : (status.toLowerCase().includes('pending') || status === 'deferred') ? 'rem-deferred' : 'rem-failed';
    const timeline = (inc.timeline || []).map(t =>
      `<div class="tl-step">
        <span class="tl-phase">${t.phase}</span>
        <span class="tl-agent">${t.agent}</span>
        <span class="tl-arrow">→</span>
        <span class="tl-outcome">${escHtml(t.outcome)}</span>
      </div>`
    ).join('');
    const runbook = (inc.runbook_steps || []).slice(0,8).map(s =>
      `<div class="rb-step">${escHtml(s)}</div>`
    ).join('');
    const impacted = (inc.impacted_services || []).join(', ') || '—';
    const evidence = (inc.evidence || []).slice(0,4).map(e => `<li>${escHtml(e)}</li>`).join('');
    const prevention = (inc.prevention_recommendations || []).slice(0,3).map((r, i) =>
      `<li>${escHtml(r)}</li>`).join('');
    const hasMonSnapshots = state.scenario && state.run;
    const incId = inc.incident_id || '';

    return `<div class="incident-card" id="inc-${incId}">
      <div class="inc-header">
        <div class="inc-id-group">
          <span class="inc-sev ${sevCls}">${sev}</span>
          <span class="inc-id">${incId || '—'}</span>
          <span class="inc-service">${inc.service || '—'}</span>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="rem-badge ${statusCls}">${status.toUpperCase()}</span>
          ${hasMonSnapshots ? `<button class="inc-snap-btn" onclick="loadIncidentSnapshots('${escHtml(incId)}','${escHtml(inc.service||'')}')">📸 5 Snapshots</button>` : ''}
          <span class="inc-time muted small">${timeAgo(inc.reported_at)}</span>
        </div>
      </div>

      <div class="inc-summary">${escHtml(inc.summary || '—')}</div>

      ${inc.reasoning ? `<div class="inc-reasoning">🔍 RCA Analysis: ${escHtml(inc.reasoning)}</div>` : ''}

      <div class="inc-details-grid">
        <div class="inc-detail-block">
          <div class="detail-label">Failure Type</div>
          <div class="detail-value">${inc.failure_type_human || inc.failure_type || '—'}</div>
        </div>
        <div class="inc-detail-block">
          <div class="detail-label">Confidence</div>
          <div class="detail-value">${inc.confidence_score != null ? (inc.confidence_score*100).toFixed(0)+'%' : '—'}</div>
        </div>
        <div class="inc-detail-block">
          <div class="detail-label">Action Taken</div>
          <div class="detail-value">${inc.remediation_action || '—'}</div>
        </div>
        <div class="inc-detail-block">
          <div class="detail-label">Impacted Services</div>
          <div class="detail-value">${escHtml(impacted)}</div>
        </div>
        ${inc.system_recovery_time ? `<div class="inc-detail-block">
          <div class="detail-label">Recovery Time</div>
          <div class="detail-value">${escHtml(inc.system_recovery_time)}</div>
        </div>` : ''}
        ${inc.impact_assessment ? `<div class="inc-detail-block" style="grid-column:1/-1">
          <div class="detail-label">Impact Assessment</div>
          <div class="detail-value" style="font-size:11px;color:#94a3b8">${escHtml(inc.impact_assessment)}</div>
        </div>` : ''}
      </div>

      ${inc.kubectl_command ? `
      <div class="inc-kubectl">
        <span class="kubectl-label">kubectl</span>
        <code>${escHtml(inc.kubectl_command)}</code>
      </div>` : ''}

      <details class="inc-collapsible">
        <summary>Agent Timeline</summary>
        <div class="tl-container">${timeline}</div>
      </details>

      ${evidence ? `<details class="inc-collapsible">
        <summary>Evidence (${(inc.evidence||[]).length})</summary>
        <ul class="evidence-list">${evidence}</ul>
      </details>` : ''}

      ${runbook ? `<details class="inc-collapsible">
        <summary>Runbook Steps</summary>
        <div class="rb-container">${runbook}</div>
      </details>` : ''}

      ${prevention ? `<details class="inc-collapsible">
        <summary>Prevention Recommendations</summary>
        <ul class="evidence-list">${prevention}</ul>
      </details>` : ''}

      ${inc.human_report ? `<details class="inc-collapsible">
        <summary>Full Incident Report</summary>
        <div class="inc-human-report">${escHtml(inc.human_report)}</div>
      </details>` : ''}
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  INCIDENT SNAPSHOT VIEWER
// ══════════════════════════════════════════════════════════════════════════
async function loadIncidentSnapshots(incidentId, service) {
  if (!state.scenario || !state.run) return;
  const viewer = $('incident-snapshot-viewer');
  viewer.style.display = 'block';
  $('snap-viewer-title').textContent = `Snapshots for ${incidentId}`;
  $('snap-viewer-subtitle').textContent = `Service: ${service} | 5 telemetry snapshots around incident time`;
  $('incident-snapshots-grid').innerHTML = '<div style="padding:12px;color:#4a6080;font-size:11px;grid-column:1/-1">Loading snapshots…</div>';

  // Scroll to viewer
  viewer.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const data = await api.incidentSnapshots(state.scenario, state.run);
    renderIncidentSnapshotGrid(data.snapshots || [], service);
  } catch (e) {
    $('incident-snapshots-grid').innerHTML = `<div style="padding:12px;color:#ef4444;font-size:11px;grid-column:1/-1">Error: ${e.message}</div>`;
  }
}

function renderIncidentSnapshotGrid(snapshots, service) {
  const grid = $('incident-snapshots-grid');
  if (!snapshots.length) {
    grid.innerHTML = '<div style="padding:12px;color:#4a6080;font-size:11px;grid-column:1/-1">No snapshot data available.</div>';
    return;
  }
  grid.innerHTML = snapshots.map((snap, i) => {
    const metrics = (snap.metrics || []).find(m => m.service === service) || snap.metrics?.[0] || {};
    const logs = (snap.logs || []).find(l => l.service === service) || {};
    const events = snap.events || [];
    const health = (snap.health || []).find(h => h.service === service) || {};
    const flags = health.anomaly_flags || [];

    return `<div class="inc-snap-cell">
      <div class="inc-snap-header">Snapshot ${i+1}</div>
      <div class="inc-snap-metric"><span>CPU</span><span class="val">${metrics.cpu_millicores ?? '—'}m</span></div>
      <div class="inc-snap-metric"><span>Memory</span><span class="val">${metrics.memory_mib ?? '—'}MiB</span></div>
      <div class="inc-snap-metric"><span>Restarts</span><span class="val">${health.restart_count ?? metrics.restart_count ?? '—'}</span></div>
      <div class="inc-snap-metric"><span>Status</span><span class="val" style="color:${health.status==='failed'?'#ef4444':health.status==='degraded'?'#f59e0b':'#10b981'}">${health.status ?? '—'}</span></div>
      <div class="inc-snap-metric"><span>Errors</span><span class="val">${health.log_error_count ?? '0'}</span></div>
      ${flags.length ? `<div class="inc-snap-flags">${flags.map(f=>`<span class="snap-flag">${f}</span>`).join('')}</div>` : ''}
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  REGISTRY TAB
// ══════════════════════════════════════════════════════════════════════════
async function loadRegistryTab() {
  try {
    const data = await api.registry();
    renderRegistry(data.services || {});
  } catch { $('registry-grid').innerHTML = '<div class="muted small" style="padding:24px">Failed to load registry.</div>'; }
}

const CRITICALITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

function renderRegistry(services) {
  const el = $('registry-grid');
  const sorted = Object.entries(services).sort((a, b) =>
    (CRITICALITY_ORDER[a[1].criticality] ?? 9) - (CRITICALITY_ORDER[b[1].criticality] ?? 9)
  );
  el.innerHTML = sorted.map(([name, svc]) => {
    const critCls = `crit-${svc.criticality || 'low'}`;
    const policies = (svc.remediation_policies || []).map(p =>
      `<span class="policy-tag">${p}</span>`).join('');
    const deps = (svc.dependencies || []).length
      ? svc.dependencies.join(', ')
      : '<span class="muted">none</span>';
    return `<div class="registry-card">
      <div class="reg-header">
        <div>
          <span class="reg-name">${name}</span>
          <span class="reg-team muted small">· ${svc.team || '—'}</span>
        </div>
        <span class="reg-crit ${critCls}">${(svc.criticality||'?').toUpperCase()}</span>
      </div>
      <div class="reg-row"><span class="reg-key">K8s Resource</span><code class="reg-val">${svc.k8s_resource || '—'}</code></div>
      <div class="reg-row"><span class="reg-key">Namespace</span><span class="reg-val">${svc.namespace || '—'}</span></div>
      <div class="reg-row"><span class="reg-key">Adapter</span><span class="reg-val">${svc.adapter || '—'}</span></div>
      <div class="reg-row"><span class="reg-key">Auto Remediate</span>
        <span class="reg-val ${svc.safe_to_auto_remediate?'auto-yes':'auto-no'}">
          ${svc.safe_to_auto_remediate ? '✓ Yes' : '✗ Manual'}
        </span>
      </div>
      <div class="reg-row"><span class="reg-key">Dependencies</span><span class="reg-val">${deps}</span></div>
      <div class="reg-policies">${policies}</div>
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  KAFKA INSPECTOR
// ══════════════════════════════════════════════════════════════════════════
async function refreshTopic() {
  const topic = $('topic-select').value;
  try {
    const data = await api.topic(topic, 20);
    $('kafka-json').textContent = JSON.stringify(data.messages || data, null, 2);
  } catch (e) {
    $('kafka-json').textContent = `Error: ${e.message}`;
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  PIPELINE STATUS
// ══════════════════════════════════════════════════════════════════════════
function setStatus(text, mode='idle') {
  $('pipeline-status-text').textContent = text;
  const dot = document.querySelector('.dot');
  if (dot) dot.className = 'dot dot-' + (mode==='active'?'active':mode==='error'?'error':'idle');
}

// ══════════════════════════════════════════════════════════════════════════
//  GRAPHS TAB — Chart.js
// ══════════════════════════════════════════════════════════════════════════
const _charts = {};
const CHART_COLORS = [
  '#22d3ee','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6',
  '#ec4899','#14b8a6','#f97316','#84cc16','#06b6d4','#a78bfa',
];

function _makeChartOptions(title, yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: {
      legend: { labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 }, position: 'top' },
      tooltip: { backgroundColor: '#0d1a32', titleColor: '#e2e8f0', bodyColor: '#94a3b8', borderColor: '#243658', borderWidth: 1 },
    },
    scales: {
      x: { ticks: { color: '#4a6080', font: { size: 9 } }, grid: { color: '#1a2840' } },
      y: { ticks: { color: '#4a6080', font: { size: 9 } }, grid: { color: '#1a2840' }, title: { display: !!yLabel, text: yLabel, color: '#4a6080', font: { size: 9 } } },
    },
  };
}

function _renderLineChart(canvasId, labels, datasets, yLabel) {
  const canvas = $(canvasId);
  if (!canvas) return;
  if (_charts[canvasId]) _charts[canvasId].destroy();
  _charts[canvasId] = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: datasets.map((d, i) => ({
        label: d.label,
        data: d.data,
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + '22',
        borderWidth: 1.5,
        pointRadius: 2,
        tension: 0.3,
        fill: false,
      })),
    },
    options: _makeChartOptions(canvasId, yLabel),
  });
}

function _renderBarChart(canvasId, labels, datasets, yLabel) {
  const canvas = $(canvasId);
  if (!canvas) return;
  if (_charts[canvasId]) _charts[canvasId].destroy();
  _charts[canvasId] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: datasets.map((d, i) => ({
        label: d.label,
        data: d.data,
        backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + '88',
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        borderWidth: 1,
      })),
    },
    options: _makeChartOptions(canvasId, yLabel),
  });
}

async function loadGraphsTab() {
  if (!state.scenario || !state.run) {
    $('graphs-status').textContent = 'No scenario/run selected.';
    return;
  }
  $('graphs-status').textContent = 'Loading…';
  const svcFilter = $('graph-svc-filter')?.value || 'all';
  try {
    const [tsData, predData, incData] = await Promise.all([
      api.timeseries(state.scenario, state.run),
      api.predictionSummary(),
      api.incidents(30),
    ]);

    const labels = (tsData.labels || []).map((l, i) => `S${i+1}`);
    let services = tsData.services || [];
    if (svcFilter !== 'all') services = services.filter(s => s === svcFilter);

    // CPU chart
    _renderLineChart('chart-cpu', labels,
      services.map(s => ({ label: s, data: tsData.cpu?.[s] || [] })), 'millicores');

    // Memory chart
    _renderLineChart('chart-memory', labels,
      services.map(s => ({ label: s, data: tsData.memory?.[s] || [] })), 'MiB');

    // Error rate chart
    _renderBarChart('chart-errors', labels,
      services.map(s => ({ label: s, data: tsData.error_rate?.[s] || [] })), 'errors');

    // Latency chart
    _renderLineChart('chart-latency', labels,
      services.map(s => ({ label: s, data: tsData.latency?.[s] || [] })), 'ms');

    // Prediction probability chart
    const preds = predData.predictions || [];
    if (preds.length) {
      _renderBarChart('chart-prediction',
        preds.map(p => p.service),
        [{
          label: 'Failure Probability',
          data: preds.map(p => Math.round(p.probability * 100)),
        }],
        'probability %'
      );
    }

    // Incident severity chart
    const incs = incData.messages || [];
    const sevCounts = { 'SEV-1': 0, 'SEV-2': 0, 'SEV-3': 0 };
    incs.forEach(i => { if (i.severity) sevCounts[i.severity] = (sevCounts[i.severity] || 0) + 1; });
    if (_charts['chart-incidents']) _charts['chart-incidents'].destroy();
    const chartInc = $('chart-incidents');
    if (chartInc) {
      _charts['chart-incidents'] = new Chart(chartInc, {
        type: 'doughnut',
        data: {
          labels: Object.keys(sevCounts),
          datasets: [{
            data: Object.values(sevCounts),
            backgroundColor: ['#ef4444aa', '#f59e0baa', '#3b82f6aa'],
            borderColor: ['#ef4444', '#f59e0b', '#3b82f6'],
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: '#94a3b8', font: { size: 10 } }, position: 'right' },
            tooltip: { backgroundColor: '#0d1a32', titleColor: '#e2e8f0', bodyColor: '#94a3b8' },
          },
        },
      });
    }

    $('graphs-status').textContent = `Charts loaded for ${state.scenario}/${state.run}`;
  } catch (e) {
    $('graphs-status').textContent = `Error: ${e.message}`;
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  SERVICE DEPENDENCY GRAPH — D3.js
// ══════════════════════════════════════════════════════════════════════════
let _graphLoaded = false;
let _graphSimulation = null;
let _currentHealthMap = {};

async function loadDepGraph() {
  try {
    const [graphData, pipelineData] = await Promise.all([
      api.graph(),
      api.pipelineState(),
    ]);

    const graph = graphData.graph || {};
    const healthMsgs = pipelineData.telemetry_health?.messages || [];

    // Build health map
    _currentHealthMap = {};
    healthMsgs.forEach(h => {
      if (h.service) _currentHealthMap[h.service] = h.status || 'unknown';
    });

    _renderDepGraph(graph, _currentHealthMap);
  } catch (e) {
    $('dep-graph-container').innerHTML = `<div style="padding:24px;color:#ef4444;font-size:12px">Error loading graph: ${e.message}</div>`;
  }
}

function _renderDepGraph(graph, healthMap) {
  const container = $('dep-graph-container');
  const svg = $('dep-graph-svg');
  if (!svg) return;

  const width = container.clientWidth || 900;
  const height = container.clientHeight || 500;

  // Clear previous
  svg.innerHTML = '';
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);

  const d3svg = d3.select('#dep-graph-svg');

  // Add arrow marker
  const defs = d3svg.append('defs');
  defs.append('marker')
    .attr('id', 'arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 18)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#243658');

  // Build nodes and links
  const nodes = [];
  const nodeSet = new Set();
  const links = [];

  Object.entries(graph).forEach(([src, deps]) => {
    nodeSet.add(src);
    (deps || []).forEach(dst => {
      nodeSet.add(dst);
      links.push({ source: src, target: dst });
    });
  });

  const criticalServices = new Set(['paymentservice', 'checkoutservice', 'cartservice', 'frontend']);
  nodeSet.forEach(id => {
    nodes.push({
      id,
      status: healthMap[id] || 'unknown',
      critical: criticalServices.has(id),
    });
  });

  const colorMap = { healthy: '#10b981', degraded: '#f59e0b', failed: '#ef4444', unknown: '#475569' };

  const g = d3svg.append('g');

  // Zoom/pan
  d3svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', e => g.attr('transform', e.transform)));

  // Links
  const link = g.append('g')
    .selectAll('line')
    .data(links)
    .enter().append('line')
    .attr('class', 'dep-link')
    .attr('marker-end', 'url(#arrow)');

  // Nodes
  const node = g.append('g')
    .selectAll('g')
    .data(nodes)
    .enter().append('g')
    .attr('class', 'dep-node')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    )
    .on('click', (e, d) => showNodeDetail(d, graph));

  node.append('circle')
    .attr('r', d => d.critical ? 20 : 14)
    .attr('fill', d => colorMap[d.status] + '33')
    .attr('stroke', d => colorMap[d.status])
    .attr('stroke-width', 2);

  node.append('text')
    .attr('dy', 4)
    .attr('text-anchor', 'middle')
    .attr('font-size', d => d.critical ? '9px' : '8px')
    .text(d => d.id.length > 12 ? d.id.substring(0, 10) + '…' : d.id);

  // Tooltip
  const tooltip = $('dep-graph-tooltip');
  node
    .on('mouseover', (e, d) => {
      tooltip.classList.remove('hidden');
      tooltip.innerHTML = `<b style="color:#22d3ee">${d.id}</b><br>
        Status: <span style="color:${colorMap[d.status]}">${d.status}</span><br>
        Dependencies: ${(graph[d.id] || []).length}<br>
        ${d.critical ? '<span style="color:#f59e0b">⚠ Critical Service</span>' : ''}`;
    })
    .on('mousemove', (e) => {
      const rect = container.getBoundingClientRect();
      tooltip.style.left = (e.clientX - rect.left + 10) + 'px';
      tooltip.style.top = (e.clientY - rect.top - 40) + 'px';
    })
    .on('mouseleave', () => tooltip.classList.add('hidden'));

  // Force simulation
  if (_graphSimulation) _graphSimulation.stop();
  _graphSimulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(90))
    .force('charge', d3.forceManyBody().strength(-250))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide(35))
    .on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

  const sim = _graphSimulation;
  _graphLoaded = true;
}

function showNodeDetail(d, graph) {
  const detail = $('dep-graph-detail');
  const content = $('dep-graph-detail-content');
  detail.style.display = 'block';
  const colorMap = { healthy: '#10b981', degraded: '#f59e0b', failed: '#ef4444', unknown: '#475569' };
  const deps = graph[d.id] || [];
  content.innerHTML = `
    <span style="font-weight:600;color:#f1f5f9">${d.id}</span>
    <span style="color:${colorMap[d.status]};margin:0 12px">● ${d.status}</span>
    <span style="color:#4a6080">Dependencies: ${deps.join(', ') || 'none'}</span>
    ${d.critical ? ' <span style="color:#f59e0b;margin-left:8px">⚠ Critical</span>' : ''}
  `;
}

// ══════════════════════════════════════════════════════════════════════════
//  PREDICTION PANEL
// ══════════════════════════════════════════════════════════════════════════
async function loadPredictionPanel() {
  try {
    const data = await api.predictionSummary();
    renderPredictionPanel(data.predictions || []);
  } catch { /* silent */ }
}

function renderPredictionPanel(predictions) {
  const el = $('prediction-grid');
  if (!predictions.length) {
    el.innerHTML = '<div class="muted small" style="padding:24px;text-align:center">No predictions yet. Publish snapshots and let the prediction agent run.</div>';
    return;
  }
  el.innerHTML = predictions.map(p => {
    const lvl = (p.risk_level || 'low').toLowerCase();
    const prob = Math.round((p.probability || p.risk_score || 0) * 100);
    const trend = p.trend || 'stable';
    const trendClass = `trend-${trend}`;
    const trendIcon = trend === 'rising' ? '↑' : trend === 'falling' || trend === 'recovering' ? '↓' : '→';
    const rationale = (p.rationale || []).slice(0, 3);
    return `<div class="pred-card risk-${lvl}">
      <div class="pred-service">${p.service}</div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <span class="sev-badge badge-${lvl}">${lvl.toUpperCase()}</span>
        <span style="font-size:20px;font-weight:700;color:#f1f5f9">${prob}%</span>
      </div>
      <div class="pred-prob-bar"><div class="pred-prob-fill fill-${lvl}" style="width:${prob}%"></div></div>
      <div class="pred-metrics">
        <div class="pred-metric">
          <span class="pred-metric-label">Failure Type</span>
          <span class="pred-metric-value">${(p.predicted_failure_type || p.predicted_failure || 'unknown').replace(/_/g,' ')}</span>
        </div>
        <div class="pred-metric">
          <span class="pred-metric-label">Trend</span>
          <span class="pred-metric-value ${trendClass}">${trendIcon} ${trend}</span>
        </div>
        <div class="pred-metric">
          <span class="pred-metric-label">Time to Failure</span>
          <span class="pred-metric-value">${p.time_to_failure || 'unknown'}</span>
        </div>
      </div>
      ${rationale.length ? `<div class="pred-rationale"><ul>${rationale.map(r=>`<li>${escHtml(r)}</li>`).join('')}</ul></div>` : ''}
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  REMEDIATION APPROVAL PANEL
// ══════════════════════════════════════════════════════════════════════════
const _approvalDecisions = {};

async function loadApprovalPanel() {
  try {
    const [psData, approvalsData] = await Promise.all([
      api.pipelineState(),
      api.approvals(),
    ]);

    // Find decisions that require manual approval (deferred/manual_approval)
    const intents = psData.decision_intents?.messages || [];
    const results = psData.remediation_results?.messages || [];

    const pendingApprovals = [];
    intents.forEach(intent => {
      if (!intent.auto_execute || intent.action === 'manual_approval' || intent.action === 'escalate') {
        const incId = `${intent.service}-${intent.scenario || 'default'}-${intent.action}`;
        pendingApprovals.push({ ...intent, _inc_id: incId });
      }
    });

    // Also add deferred results
    results.forEach(r => {
      if (r.status === 'deferred') {
        const incId = `${r.service}-${r.scenario || 'default'}-${r.action}-result`;
        if (!pendingApprovals.find(p => p.service === r.service && p.action === r.action)) {
          pendingApprovals.push({ ...r, _inc_id: incId, _from_result: true });
        }
      }
    });

    renderApprovalQueue(pendingApprovals);

    // Update approval badge
    const badge = $('approval-badge');
    if (pendingApprovals.length > 0) {
      badge.textContent = pendingApprovals.length;
      badge.classList.remove('hidden');
    }

    // Load history
    renderApprovalHistory(approvalsData.approvals || []);
  } catch { /* silent */ }
}

function renderApprovalQueue(items) {
  const el = $('approval-queue');
  if (!items.length) {
    el.innerHTML = '<div class="muted small" style="padding:24px;text-align:center">No pending remediations requiring approval.</div>';
    return;
  }
  el.innerHTML = items.map(item => {
    const incId = item._inc_id || item.incident_id || `${item.service}-${item.action}`;
    const decision = _approvalDecisions[incId];
    const isDecided = !!decision;
    const kubectl = item.kubectl_command || `kubectl rollout restart deployment/${item.service} -n ${item.action_params?.namespace || 'default'}`;
    const reason = item.reason || item.message || 'Manual approval required';
    const confidence = item.confidence_score != null ? `${(item.confidence_score*100).toFixed(0)}%` : '—';

    return `<div class="approval-card ${isDecided ? (decision.approved?'approved':'rejected') : ''}">
      <div class="approval-header">
        <div>
          <div class="approval-id">${incId.substring(0, 40)}</div>
          <div class="approval-service" style="margin-top:2px">${item.service || '—'}</div>
        </div>
        <span class="approval-action-badge">${item.action || '—'}</span>
      </div>
      <div class="approval-body">
        <div><strong style="color:#94a3b8">Failure Type:</strong> ${(item.failure_type||'unknown').replace(/_/g,' ')}</div>
        <div><strong style="color:#94a3b8">Reason:</strong> ${escHtml(reason)}</div>
        <div><strong style="color:#94a3b8">Confidence:</strong> ${confidence}
          ${item.impacted_services?.length ? ` | <strong style="color:#94a3b8">Impacted:</strong> ${item.impacted_services.join(', ')}` : ''}
        </div>
      </div>
      <div class="approval-kubectl">${escHtml(kubectl)}</div>
      <div class="approval-btns">
        ${isDecided
          ? `<span class="${decision.approved?'approval-status-approved':'approval-status-rejected'}">${decision.approved ? '✓ Approved' : '✗ Rejected'} — ${decision.decided_at||''}</span>`
          : `<button class="btn-accept" onclick="handleApproval('${escHtml(incId)}','${escHtml(item.action||'')}',true)">✓ Accept</button>
             <button class="btn-reject" onclick="handleApproval('${escHtml(incId)}','${escHtml(item.action||'')}',false)">✗ Reject</button>`
        }
      </div>
    </div>`;
  }).join('');
}

async function handleApproval(incidentId, action, approved) {
  try {
    const result = await api.approveRemediation({ incident_id: incidentId, action, approved });
    _approvalDecisions[incidentId] = { approved, decided_at: new Date().toLocaleTimeString() };
    console.log(`[Approval] ${approved ? 'Accepted' : 'Rejected'} ${incidentId}: ${result.message}`);
    // Re-render
    loadApprovalPanel();
  } catch (e) {
    alert(`Approval error: ${e.message}`);
  }
}

function renderApprovalHistory(history) {
  const el = $('approval-history');
  if (!history.length) {
    el.innerHTML = '<div class="muted small">No approval decisions yet.</div>';
    return;
  }
  el.innerHTML = [...history].reverse().map(h =>
    `<div class="history-item">
      <span class="${h.approved ? 'history-approved' : 'history-rejected'}">${h.approved ? '✓' : '✗'}</span>
      <span style="color:#94a3b8;flex:1">${h.incident_id || '—'}</span>
      <span style="color:#64748b">${h.action || '—'}</span>
      <span style="color:#3d5270;font-size:10px">${h.decided_at || ''}</span>
    </div>`
  ).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  MONITORING INCIDENTS (5 snapshots)
// ══════════════════════════════════════════════════════════════════════════
async function loadMonitoringIncidents() {
  try {
    const data = await api.monitoringIncidents();
    const items = data.messages || [];
    const container = $('incidents-list');
    if (!items.length) {
      container.innerHTML += '<div class="muted small" style="padding:8px 24px">No snapshot-based incidents available yet.</div>';
      return;
    }
    const section = document.createElement('div');
    section.style.cssText = 'padding:8px 16px;border-bottom:1px solid #162036;color:#94a3b8;font-size:11px;margin-top:8px';
    section.textContent = `📸 Snapshot Incidents (${items.length}) — 5 telemetry snapshots per incident`;
    container.insertBefore(section, container.firstChild);
    // Render each monitoring incident with its embedded snapshot data
    const cards = items.map(inc => renderMonitoringIncidentCard(inc)).join('');
    const wrapper = document.createElement('div');
    wrapper.innerHTML = cards;
    container.insertBefore(wrapper, section.nextSibling);
  } catch (e) {
    $('incidents-list').innerHTML += `<div class="muted small" style="padding:8px 24px;color:#ef4444">Failed to load snapshot incidents: ${e.message}</div>`;
  }
}

function renderMonitoringIncidentCard(inc) {
  const sevColor = inc.severity === 'critical' ? '#ef4444' : inc.severity === 'warning' ? '#f59e0b' : '#94a3b8';
  const flags = (inc.anomaly_flags || []).map(f => `<span class="snap-flag">${escHtml(f)}</span>`).join('');
  const evidence = (inc.evidence || []).slice(0, 3).map(e => `<li>${escHtml(e)}</li>`).join('');
  const metrics = inc.metrics_snapshot || [];
  const logs = inc.logs_snapshot || [];

  const snapCols = metrics.map((m, i) => {
    const l = logs[i] || {};
    return `<div class="inc-snap-cell">
      <div class="inc-snap-header">T${i + 1}</div>
      <div class="inc-snap-metric"><span>CPU</span><span class="val">${m.cpu_millicores ?? '—'}m</span></div>
      <div class="inc-snap-metric"><span>Mem</span><span class="val">${m.memory_mib ?? '—'}MiB</span></div>
      <div class="inc-snap-metric"><span>Restarts</span><span class="val">${m.restart_count ?? '—'}</span></div>
      <div class="inc-snap-metric"><span>Errors</span><span class="val">${l.log_error_count ?? '—'}</span></div>
      <div class="inc-snap-metric"><span>Status</span><span class="val" style="color:${m.pod_status==='failed'?'#ef4444':m.pod_status==='unknown'?'#f59e0b':'#10b981'}">${m.pod_status ?? '—'}</span></div>
    </div>`;
  }).join('');

  return `<div class="incident-card" style="border-left:3px solid ${sevColor}">
    <div class="inc-header">
      <div class="inc-id-group">
        <span class="inc-sev" style="background:${sevColor}20;color:${sevColor};border:1px solid ${sevColor}40">${(inc.severity||'info').toUpperCase()}</span>
        <span class="inc-id">${escHtml(inc.incident_id || '—')}</span>
        <span class="inc-service">${escHtml(inc.service || '—')}</span>
        <span class="muted small" style="margin-left:4px">${escHtml(inc.incident_type || '')}</span>
      </div>
      <span class="inc-time muted small">${timeAgo(inc.timestamp)}</span>
    </div>
    ${flags ? `<div style="padding:4px 0;display:flex;flex-wrap:wrap;gap:4px">${flags}</div>` : ''}
    ${evidence ? `<ul class="evidence-list" style="margin:4px 0">${evidence}</ul>` : ''}
    ${snapCols ? `<div style="display:grid;grid-template-columns:repeat(${metrics.length},1fr);gap:1px;background:#162036;margin-top:8px;border-radius:4px;overflow:hidden">${snapCols}</div>` : ''}
  </div>`;
}

// ══════════════════════════════════════════════════════════════════════════
//  EVENT BINDINGS
// ══════════════════════════════════════════════════════════════════════════
$$('.scn-btn').forEach(btn => btn.addEventListener('click', () => selectScenario(btn.dataset.scenario)));
$('run-sel').addEventListener('change', () => { if ($('run-sel').value) selectRun($('run-sel').value); });
$('btn-prev').addEventListener('click', stepPrev);
$('btn-next').addEventListener('click', stepNext);
$('btn-auto').addEventListener('click', toggleAutoPlay);
$('btn-pub-all').addEventListener('click', publishAll);
$('log-svc-filter').addEventListener('change', applyLogFilter);
$('log-sev-filter').addEventListener('change', applyLogFilter);
$('btn-refresh-topic').addEventListener('click', refreshTopic);
$('topic-select').addEventListener('change', refreshTopic);
$('btn-clear-pub').addEventListener('click', () => {
  $('publish-log').innerHTML = '<div class="muted small">Publish log will appear here.</div>';
});
$('btn-refresh-incidents').addEventListener('click', loadIncidentsTab);
$('btn-load-graphs') && $('btn-load-graphs').addEventListener('click', loadGraphsTab);
$('btn-load-graph') && $('btn-load-graph').addEventListener('click', loadDepGraph);
$('btn-refresh-prediction') && $('btn-refresh-prediction').addEventListener('click', loadPredictionPanel);
$('btn-refresh-approvals') && $('btn-refresh-approvals').addEventListener('click', loadApprovalPanel);
$('btn-load-mon-incidents') && $('btn-load-mon-incidents').addEventListener('click', loadMonitoringIncidents);

// ══════════════════════════════════════════════════════════════════════════
//  BOOT
// ══════════════════════════════════════════════════════════════════════════
refreshPipeline();
setInterval(refreshPipeline, 5000);
refreshTopic();
// Auto-load dep graph and prediction panel in background
setTimeout(loadDepGraph, 1000);
setTimeout(loadPredictionPanel, 2000);
