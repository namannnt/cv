const _jwt = localStorage.getItem('jwt');
if (!_jwt) window.location.replace('/');

const _hdrs = { 'Authorization': `Bearer ${_jwt}`, 'Content-Type': 'application/json' };

document.addEventListener('DOMContentLoaded', () => {
    const name = localStorage.getItem('user_name');
    const el   = document.getElementById('navUser');
    if (el && name) el.textContent = name;
    loadBatchSelector();
});

function doLogout() { localStorage.clear(); window.location.replace('/'); }

function showReportTab(name) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${name}`).classList.add('active');
    document.querySelectorAll('.tab-btn').forEach(b => {
        if (b.textContent.toLowerCase().includes(name === 'sessions' ? 'session' : 'student'))
            b.classList.add('active');
    });
    loadReports();
}

function fmtDur(secs) {
    if (!secs) return '0s';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

// ── Batch selector ──
let _batchStudents = {}; // cache: batchId -> [{id, name}]

async function loadBatchSelector() {
    try {
        const res = await fetch(`${API_BASE}/batches`, { headers: _hdrs });
        if (res.status === 401) { doLogout(); return; }
        const batches = await res.json();
        const sel = document.getElementById('batchSelect');
        if (!batches.length) { sel.innerHTML = '<option value="">No batches yet</option>'; return; }
        batches.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b.id;
            opt.textContent = `${b.name} (${b.class_code})`;
            sel.appendChild(opt);
        });
        sel.value = batches[0].id;
        loadReports();
    } catch(e) {}
}

async function loadReports() {
    const batchId = document.getElementById('batchSelect').value;
    if (!batchId) return;
    loadSessionHistory(batchId);
    loadStudentSummaries(batchId);
}

// ── Session History ──
let _sessions = []; // cache for detail lookup

async function loadSessionHistory(batchId) {
    try {
        const res = await fetch(`${API_BASE}/reports/sessions/${batchId}`, { headers: _hdrs });
        if (res.status === 401) { doLogout(); return; }
        _sessions = await res.json();
        const tbody = document.getElementById('sessionsBody');
        if (!_sessions.length) {
            tbody.innerHTML = '<tr class="empty-row"><td colspan="4">No completed sessions yet</td></tr>';
            return;
        }
        tbody.innerHTML = _sessions.map(s => `
            <tr class="session-row-clickable" onclick="openSessionDetail(${s.session_id}, '${s.date}', ${batchId})">
                <td style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#888">${s.date}</td>
                <td style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#666">${fmtDur(s.duration_seconds)}</td>
                <td><span style="font-family:'JetBrains Mono',monospace;font-weight:700;
                    color:${s.avg_score>=70?'var(--green)':s.avg_score>=40?'var(--yellow)':'var(--red)'}">
                    ${s.avg_score.toFixed(1)}</span></td>
                <td style="font-family:'JetBrains Mono',monospace;font-size:.82rem;
                    color:${s.distraction_events>10?'var(--red)':'#666'}">${s.distraction_events}</td>
            </tr>
        `).join('');
    } catch(e) {}
}

// ── Student Summaries ──
async function loadStudentSummaries(batchId) {
    try {
        const res = await fetch(`${API_BASE}/reports/students/${batchId}`, { headers: _hdrs });
        if (res.status === 401) { doLogout(); return; }
        const students = await res.json();
        const tbody = document.getElementById('studentsBody');
        if (!students.length) {
            tbody.innerHTML = '<tr class="empty-row"><td colspan="4">No student data in the last 30 days</td></tr>';
            return;
        }
        tbody.innerHTML = students.map(s => {
            const trendEmoji = s.trend === 'IMPROVING' ? '📈' : s.trend === 'DECLINING' ? '📉' : '➡️';
            const trendClass = `trend-${s.trend.toLowerCase()}`;
            return `<tr>
                <td style="font-weight:700;color:#ccc">${s.name}</td>
                <td style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#666">${s.attendance_count}</td>
                <td><span style="font-family:'JetBrains Mono',monospace;font-weight:700;
                    color:${s.avg_score>=70?'var(--green)':s.avg_score>=40?'var(--yellow)':'var(--red)'}">
                    ${s.avg_score.toFixed(1)}</span></td>
                <td><span class="${trendClass}" style="font-weight:600">${trendEmoji} ${s.trend}</span></td>
            </tr>`;
        }).join('');
    } catch(e) {}
}

// ── Session Detail Modal ──
let _detailChart = null;

async function openSessionDetail(sessionId, date, batchId) {
    document.getElementById('detailOverlay').style.display = 'flex';
    document.getElementById('detailTitle').textContent = `Session Detail — ${date}`;
    document.getElementById('detailSub').textContent = 'Loading student data…';
    document.getElementById('detailContent').innerHTML =
        '<div style="text-align:center;padding:40px;color:#444;font-family:\'JetBrains Mono\',monospace">Loading…</div>';

    // Get enrolled students for this batch
    try {
        const stuRes = await fetch(`${API_BASE}/reports/students/${batchId}`, { headers: _hdrs });
        const students = await stuRes.json();

        if (!students.length) {
            document.getElementById('detailContent').innerHTML =
                '<div style="text-align:center;padding:40px;color:#444;font-family:\'JetBrains Mono\',monospace">No student data for this session</div>';
            return;
        }

        document.getElementById('detailSub').textContent = `${students.length} student(s) — click a name to view their breakdown`;

        // Build student selector tabs
        let html = `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px" id="stuTabs">`;
        students.forEach((s, i) => {
            html += `<button onclick="loadStudentDetail(${sessionId},'${date}',${s.student_id},'${s.name}',this)"
                style="padding:7px 16px;background:${i===0?'var(--cyan)':'#0a0a18'};color:${i===0?'#000':'#666'};
                border:1px solid ${i===0?'var(--cyan)':'var(--border)'};border-radius:8px;cursor:pointer;
                font-size:.82rem;font-family:'Inter',sans-serif;font-weight:600;transition:all .2s">
                ${s.name}
            </button>`;
        });
        html += `</div><div id="stuDetailBody"></div>`;
        document.getElementById('detailContent').innerHTML = html;

        // Auto-load first student
        const firstBtn = document.getElementById('stuTabs').querySelector('button');
        loadStudentDetail(sessionId, date, students[0].student_id, students[0].name, firstBtn);

    } catch(e) {
        document.getElementById('detailContent').innerHTML =
            `<div style="color:var(--red);padding:20px;font-family:'JetBrains Mono',monospace">Failed to load: ${e.message}</div>`;
    }
}

async function loadStudentDetail(sessionId, date, studentId, studentName, btn) {
    // Update tab styles
    document.querySelectorAll('#stuTabs button').forEach(b => {
        b.style.background = '#0a0a18'; b.style.color = '#666'; b.style.borderColor = 'var(--border)';
    });
    btn.style.background = 'var(--cyan)'; btn.style.color = '#000'; btn.style.borderColor = 'var(--cyan)';

    const body = document.getElementById('stuDetailBody');
    body.innerHTML = '<div style="text-align:center;padding:30px;color:#444;font-family:\'JetBrains Mono\',monospace">Loading…</div>';

    try {
        const res  = await fetch(`${API_BASE}/reports/session-detail/${sessionId}/student/${studentId}`, { headers: _hdrs });
        const data = await res.json();

        if (!data.total_records) {
            body.innerHTML = '<div style="color:#444;padding:20px;font-family:\'JetBrains Mono\',monospace">No data recorded for this student in this session</div>';
            return;
        }

        const stateColors = { FOCUSED:'#00ff88', 'LOW FOCUS':'#ffd600', DISTRACTED:'#ff1744', FATIGUED:'#ff6b35' };
        const sb = data.state_breakdown;

        // ── Stats row ──
        let html = `<div class="detail-stats">
            <div class="ds-card">
                <div class="ds-val" style="color:var(--cyan)">${data.avg_score}</div>
                <div class="ds-label">Avg Score</div>
            </div>
            <div class="ds-card">
                <div class="ds-val" style="color:var(--green)">${data.quality_score}</div>
                <div class="ds-label">Quality Score</div>
            </div>
            <div class="ds-card">
                <div class="ds-val" style="color:var(--red)">${fmtDur(data.total_distraction_secs)}</div>
                <div class="ds-label">Total Distracted</div>
            </div>
            <div class="ds-card">
                <div class="ds-val" style="color:var(--orange)">${data.distraction_episodes.length}</div>
                <div class="ds-label">Distraction Episodes</div>
            </div>
        </div>`;

        // ── State breakdown ──
        html += `<div class="breakdown-section">
            <div class="breakdown-title">State Breakdown</div>`;
        ['FOCUSED','LOW FOCUS','DISTRACTED','FATIGUED'].forEach(state => {
            const d = sb[state] || {seconds:0, percent:0};
            html += `<div class="state-row">
                <div class="state-row-label">${state}</div>
                <div class="state-bar-bg">
                    <div class="state-bar-fill" style="width:${d.percent}%;background:${stateColors[state]}"></div>
                </div>
                <div class="state-row-pct">${d.percent}%</div>
                <div class="state-row-dur">${fmtDur(d.seconds)}</div>
            </div>`;
        });
        html += `</div>`;

        // ── Distraction episodes ──
        html += `<div class="episodes-section">
            <div class="breakdown-title">Distraction Episodes</div>`;
        if (!data.distraction_episodes.length) {
            html += `<div style="color:#333;font-size:.82rem;font-family:'JetBrains Mono',monospace;padding:8px">No distraction episodes detected ✅</div>`;
        } else {
            data.distraction_episodes.forEach((ep, i) => {
                html += `<div class="episode-item">
                    <span class="ep-icon">⚠</span>
                    <span class="ep-label">Episode ${i+1} — ${ep.label}</span>
                    <span class="ep-dur">${fmtDur(ep.duration_secs)}</span>
                </div>`;
            });
        }
        html += `</div>`;

        // ── Fatigue info ──
        html += `<div class="fatigue-info">`;
        if (data.fatigue_onset) {
            html += `<div class="fi-card">
                <div class="fi-label">Fatigue Onset</div>
                <div class="fi-val">${data.fatigue_onset.label}</div>
                <div style="font-size:.72rem;color:#555;margin-top:4px;font-family:'JetBrains Mono',monospace">
                    Level: ${data.fatigue_onset.fatigue_level}%
                </div>
            </div>`;
        } else {
            html += `<div class="fi-card">
                <div class="fi-label">Fatigue Onset</div>
                <div class="fi-val" style="color:var(--green)">None detected ✅</div>
            </div>`;
        }
        html += `<div class="fi-card">
            <div class="fi-label">Peak Fatigue</div>
            <div class="fi-val">${data.fatigue_peak.level}%</div>
            <div style="font-size:.72rem;color:#555;margin-top:4px;font-family:'JetBrains Mono',monospace">
                at ${fmtDur(data.fatigue_peak.secs_into_session)} into session
            </div>
        </div>`;
        html += `</div>`;

        // ── Gaze distribution ──
        html += `<div class="breakdown-title" style="margin-bottom:10px">Gaze Distribution</div>
        <div class="gaze-row">`;
        const gazeColors = { CENTER:'var(--green)', LEFT:'var(--yellow)', RIGHT:'var(--yellow)', DOWN:'var(--orange)' };
        Object.entries(data.gaze_distribution).forEach(([g, d]) => {
            html += `<div class="gaze-chip" style="color:${gazeColors[g]||'#888'};border-color:${gazeColors[g]||'#333'}22">
                ${g}: ${d.percent}%
            </div>`;
        });
        html += `</div>`;

        // ── Timeline chart ──
        html += `<div class="chart-section" style="margin-top:20px">
            <div class="breakdown-title" style="margin-bottom:10px">Attention Timeline</div>
            <canvas id="detailChart"></canvas>
        </div>`;

        body.innerHTML = html;

        // Render chart
        if (_detailChart) { _detailChart.destroy(); _detailChart = null; }
        const labels  = data.timeline.map(p => fmtDur(p.t));
        const scores  = data.timeline.map(p => p.score);
        const fatigue = data.timeline.map(p => p.fatigue);

        _detailChart = new Chart(document.getElementById('detailChart'), {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Attention Score',
                        data: scores,
                        borderColor: '#00e5ff', backgroundColor: '#00e5ff15',
                        borderWidth: 2, pointRadius: 0, fill: true, tension: 0.4,
                    },
                    {
                        label: 'Fatigue',
                        data: fatigue,
                        borderColor: '#ff6b35', backgroundColor: '#ff6b3510',
                        borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.4,
                    }
                ]
            },
            options: {
                responsive: true,
                animation: { duration: 600 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#555', usePointStyle: true } },
                    tooltip: { backgroundColor: '#07070f', borderColor: '#1a1a3a', borderWidth: 1, titleColor: '#fff', bodyColor: '#888' }
                },
                scales: {
                    x: { ticks: { color: '#333', maxTicksLimit: 8 }, grid: { color: '#08081a' } },
                    y: { ticks: { color: '#333' }, grid: { color: '#08081a' }, min: 0, max: 100 }
                }
            }
        });

    } catch(e) {
        body.innerHTML = `<div style="color:var(--red);padding:20px;font-family:'JetBrains Mono',monospace">Failed: ${e.message}</div>`;
    }
}

function closeDetail() {
    document.getElementById('detailOverlay').style.display = 'none';
    if (_detailChart) { _detailChart.destroy(); _detailChart = null; }
}
