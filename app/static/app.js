/* =====================================================================
   JATAYU Dashboard — app.js  (Full Pipeline Edition)
   ===================================================================== */

// ── API helpers ─────────────────────────────────────────────────────────
const api = {
  runs:            (s)        => fetch(`/api/runs/${s}`).then(r => r.json()),
  snapshots:       (s, r)     => fetch(`/api/snapshots/${s}/${r}`).then(r => r.json()),
  snapshot:        (s, r, n)  => fetch(`/api/snapshot/${s}/${r}/${n}`).then(r => r.json()),
  publishSnapshot: (p)        => fetch('/api/publish/snapshot', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) }).then(r => r.json()),
  publishAll:      (p)        => fetch('/api/publish/all', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) }).then(r => r.json()),
  topic:           (t, n=20)  => fetch(`/api/topic/${encodeURIComponent(t)}?max_messages=${n}`).then(r => r.json()),
  pipelineState:   ()         => fetch('/api/pipeline/state').then(r => r.json()),
  incidents:       (n=10)     => fetch(`/api/incidents?max=${n}`).then(r => r.json()),
  registry:        ()         => fetch('/api/registry').then(r => r.json()),
  graph:           ()         => fetch('/api/graph').then(r => r.json()),
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
  if (tab === 'incidents') loadIncidentsTab();
  if (tab === 'registry')  loadRegistryTab();
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
    el.innerHTML = '<div class="muted small" style="padding:24px;text-align:center">No incidents yet.</div>';
    return;
  }
  el.innerHTML = [...items].reverse().map(inc => {
    const sev = inc.severity || 'SEV-3';
    const sevCls = sev === 'SEV-1' ? 'sev-critical' : sev === 'SEV-2' ? 'sev-warning' : 'sev-info-cls';
    const status = inc.remediation_status || 'unknown';
    const statusCls = status === 'success' ? 'rem-success' : status === 'deferred' ? 'rem-deferred' : 'rem-failed';
    const timeline = (inc.timeline || []).map(t =>
      `<div class="tl-step">
        <span class="tl-phase">${t.phase}</span>
        <span class="tl-agent">${t.agent}</span>
        <span class="tl-arrow">→</span>
        <span class="tl-outcome">${t.outcome}</span>
      </div>`
    ).join('');
    const runbook = (inc.runbook_steps || []).map(s =>
      `<div class="rb-step">${escHtml(s)}</div>`
    ).join('');
    const impacted = (inc.impacted_services || []).join(', ') || '—';
    const evidence = (inc.evidence || []).slice(0,3).map(e => `<li>${escHtml(e)}</li>`).join('');
    return `<div class="incident-card">
      <div class="inc-header">
        <div class="inc-id-group">
          <span class="inc-sev ${sevCls}">${sev}</span>
          <span class="inc-id">${inc.incident_id || '—'}</span>
          <span class="inc-service">${inc.service || '—'}</span>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="rem-badge ${statusCls}">${status.toUpperCase()}</span>
          <span class="inc-time muted small">${timeAgo(inc.reported_at)}</span>
        </div>
      </div>

      <div class="inc-summary">${escHtml(inc.summary || '—')}</div>

      <div class="inc-details-grid">
        <div class="inc-detail-block">
          <div class="detail-label">Failure Type</div>
          <div class="detail-value">${inc.failure_type || '—'}</div>
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
        <summary>Evidence</summary>
        <ul class="evidence-list">${evidence}</ul>
      </details>` : ''}

      ${runbook ? `<details class="inc-collapsible">
        <summary>Runbook Steps</summary>
        <div class="rb-container">${runbook}</div>
      </details>` : ''}
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

// ══════════════════════════════════════════════════════════════════════════
//  BOOT
// ══════════════════════════════════════════════════════════════════════════
refreshPipeline();
setInterval(refreshPipeline, 5000);
refreshTopic();
