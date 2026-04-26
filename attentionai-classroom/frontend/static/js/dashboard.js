const _jwt = localStorage.getItem('jwt');
if (!_jwt) window.location.replace('/');

const _authHeaders = { 'Authorization': `Bearer ${_jwt}`, 'Content-Type': 'application/json' };

let _pollInterval    = null;
let _activeClassCode = null;
let _activeBatchId   = null;

// ── INIT ──
window.addEventListener('DOMContentLoaded', () => {
    const name = localStorage.getItem('user_name');
    const el   = document.getElementById('navUser');
    if (el && name) el.textContent = name;
    loadBatches();
});

function doLogout() { localStorage.clear(); window.location.replace('/'); }

// ── TABS ──
function showTeacherTab(name) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    const tab = document.getElementById(`tab-${name}`);
    if (tab) tab.classList.add('active');
    document.querySelectorAll('.tab-btn').forEach(b => {
        if (b.textContent.toLowerCase().includes(name)) b.classList.add('active');
    });
}

// ── BATCHES ──
async function loadBatches() {
    try {
        const res = await fetch(`${API_BASE}/batches`, { headers: _authHeaders });
        if (res.status === 401) { doLogout(); return; }
        const batches = await res.json();
        renderBatches(batches);
    } catch (e) {
        const el = document.getElementById('batchList');
        if (el) el.innerHTML = '<div style="color:var(--red);padding:20px;font-size:.8rem">Failed to load batches. Is the server running?</div>';
    }
}

function renderBatches(batches) {
    const el = document.getElementById('batchList');
    if (!el) return;
    if (!batches.length) {
        el.innerHTML = '<div style="color:#333;font-family:\'JetBrains Mono\',monospace;font-size:.8rem;padding:20px">No batches yet. Create one above.</div>';
        return;
    }
    el.innerHTML = batches.map(b => `
        <div class="batch-card">
            <div class="${b.has_active_session ? 'active-dot' : 'idle-dot'}"></div>
            <div class="batch-info">
                <div class="batch-name">${b.name}</div>
                <div class="batch-code">Code: <strong>${b.class_code}</strong>&nbsp;&nbsp;${b.has_active_session ? '<span style="color:var(--green);font-size:.72rem">● LIVE</span>' : ''}</div>
            </div>
            <div class="batch-actions">
                ${b.has_active_session
                    ? `<button class="btn-sm btn-end"  onclick="endSession(${b.id})">■ End Session</button>
                       <button class="btn-sm btn-view" onclick="viewDashboard('${b.class_code}','${b.name}',${b.id})">📊 View Live</button>`
                    : `<button class="btn-sm btn-start" onclick="startSession(${b.id})">▶ Start Session</button>`
                }
            </div>
        </div>
    `).join('');
}

async function createBatch() {
    const nameEl = document.getElementById('newBatchName');
    const errEl  = document.getElementById('batchError');
    const name   = nameEl.value.trim();
    errEl.textContent = '';
    if (!name) { errEl.textContent = 'Please enter a batch name.'; return; }

    const res  = await fetch(`${API_BASE}/batches`, {
        method: 'POST', headers: _authHeaders, body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.detail || 'Failed to create batch.'; return; }
    nameEl.value = '';
    loadBatches();
}

async function startSession(batchId) {
    const res = await fetch(`${API_BASE}/batches/${batchId}/sessions/start`, {
        method: 'POST', headers: _authHeaders
    });
    if (!res.ok) {
        const d = await res.json();
        alert(d.detail || 'Failed to start session');
        return;
    }
    // Reload batches then auto-jump to live dashboard
    const batchRes = await fetch(`${API_BASE}/batches`, { headers: _authHeaders });
    if (!batchRes.ok) return;
    const batches = await batchRes.json();
    renderBatches(batches);
    const batch = batches.find(b => b.id === batchId);
    if (batch) viewDashboard(batch.class_code, batch.name, batch.id);
}

async function endSession(batchId) {
    const res = await fetch(`${API_BASE}/batches/${batchId}/sessions/end`, {
        method: 'POST', headers: _authHeaders
    });
    if (!res.ok) {
        const d = await res.json();
        alert(d.detail || 'Failed to end session');
        return;
    }
    stopPolling();
    _activeClassCode = null;
    _activeBatchId   = null;
    const endBtn = document.getElementById('btnEndFromDash');
    if (endBtn) endBtn.style.display = 'none';
    showTeacherTab('batches');
    loadBatches();
}

function viewDashboard(classCode, batchName, batchId) {
    _activeClassCode = classCode;
    _activeBatchId   = batchId;
    const subtitle = document.getElementById('dashSubtitle');
    if (subtitle) subtitle.textContent = `Monitoring: ${batchName} · Code: ${classCode}`;
    const endBtn = document.getElementById('btnEndFromDash');
    if (endBtn) endBtn.style.display = 'inline-block';
    showTeacherTab('dashboard');
    startPolling();
}

async function endSessionFromDash() {
    if (!_activeBatchId) return;
    await endSession(_activeBatchId);
}

// ── POLLING ──
function startPolling() {
    stopPolling();
    pollClassData();
    _pollInterval = setInterval(pollClassData, 2000);
}

function stopPolling() {
    if (_pollInterval) { clearInterval(_pollInterval); _pollInterval = null; }
}

async function pollClassData() {
    if (!_activeClassCode) return;
    try {
        const res = await fetch(`${API_BASE}/class-data/${_activeClassCode}`, { headers: _authHeaders });
        if (res.status === 401) { doLogout(); return; }
        if (res.status === 404) {
            // Session ended externally — stop polling and go back
            stopPolling();
            _activeClassCode = null;
            _activeBatchId   = null;
            const endBtn = document.getElementById('btnEndFromDash');
            if (endBtn) endBtn.style.display = 'none';
            return;
        }
        if (!res.ok) return;
        renderDashboard(await res.json());
    } catch (e) {}
}

function renderDashboard(data) {
    const metOnline     = document.getElementById('metOnline');
    const metAvg        = document.getElementById('metAvg');
    const metDistracted = document.getElementById('metDistracted');
    const metFatigued   = document.getElementById('metFatigued');
    if (metOnline)     metOnline.textContent     = data.total_online;
    if (metAvg)        metAvg.textContent        = data.avg_score ? data.avg_score.toFixed(1) : '--';
    if (metDistracted) metDistracted.textContent = data.distracted_count;
    if (metFatigued)   metFatigued.textContent   = data.fatigued_count;

    const alertBar = document.getElementById('alertBar');
    if (alertBar) {
        alertBar.innerHTML = '';
        data.students.forEach(s => {
            if (s.status === 'OFFLINE') return;
            if (s.state === 'DISTRACTED')
                alertBar.innerHTML += `<div class="alert-chip red">⚠ ${s.name} — DISTRACTED</div>`;
            if (s.fatigue >= 60)
                alertBar.innerHTML += `<div class="alert-chip orange">😴 ${s.name} — Fatigue ${Math.round(s.fatigue)}%</div>`;
        });
    }

    const tbody = document.getElementById('studentTableBody');
    if (!tbody) return;
    if (!data.students.length) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="6">Waiting for students to send data…</td></tr>';
        return;
    }
    tbody.innerHTML = data.students.map(s => {
        const offline    = s.status === 'OFFLINE';
        const scoreColor = s.score >= 70 ? '#00ff88' : s.score >= 40 ? '#ffd600' : '#ff1744';
        const stateBadge = {
            'FOCUSED':    'badge-focused',
            'LOW FOCUS':  'badge-low',
            'DISTRACTED': 'badge-distracted',
            'FATIGUED':   'badge-fatigued',
        }[s.state] || 'badge-low';
        return `<tr style="${offline ? 'opacity:.35;filter:grayscale(1)' : ''}">
            <td style="font-weight:700;color:${offline ? '#444' : '#ccc'}">${s.name}</td>
            <td>
                <div class="score-bar-wrap">
                    <div class="score-bar-bg">
                        <div class="score-bar-fill" style="width:${s.score}%;background:${scoreColor}"></div>
                    </div>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:.8rem;color:${scoreColor}">${s.score.toFixed(0)}</span>
                </div>
            </td>
            <td><span class="state-badge ${stateBadge}">${s.state}</span></td>
            <td style="font-family:'JetBrains Mono',monospace;font-size:.8rem;color:${s.fatigue >= 60 ? 'var(--orange)' : '#666'}">${s.fatigue.toFixed(0)}%</td>
            <td style="font-family:'JetBrains Mono',monospace;font-size:.8rem;color:#555">${s.gaze}</td>
            <td><span class="state-badge ${s.status === 'ONLINE' ? 'badge-online' : 'badge-offline'}">${s.status}</span></td>
        </tr>`;
    }).join('');
}
