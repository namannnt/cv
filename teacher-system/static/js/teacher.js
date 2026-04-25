// ── MATRIX ──
const mc = document.getElementById('matrixCanvas');
const mx = mc.getContext('2d');
mc.width = window.innerWidth; mc.height = window.innerHeight;
const mch = 'ABCDEF0123456789@#$%アイウエオ';
const mfs = 12, mcols = Math.floor(mc.width / mfs), mdr = Array(mcols).fill(1);
function drawMatrix() {
    mx.fillStyle = 'rgba(2,2,10,0.05)'; mx.fillRect(0,0,mc.width,mc.height);
    mx.fillStyle = '#00e5ff'; mx.font = `${mfs}px monospace`;
    mdr.forEach((y,i) => {
        mx.globalAlpha = Math.random()*.4+.05;
        mx.fillText(mch[Math.floor(Math.random()*mch.length)], i*mfs, y*mfs);
        if (y*mfs > mc.height && Math.random()>.975) mdr[i]=0; mdr[i]++;
    }); mx.globalAlpha=1;
}
setInterval(drawMatrix, 55);

// ── CLOCK ──
function updateClock() { document.getElementById('clock').textContent = new Date().toLocaleTimeString(); }
setInterval(updateClock, 1000); updateClock();

// ── HELPERS ──
function scoreClass(s) { return s>=70?'score-high':s>=40?'score-mid':'score-low'; }
function stateClass(s) {
    const m = {'FOCUSED':'focused','DISTRACTED':'distracted','FATIGUED':'fatigued','LOW FOCUS':'low','OFFLINE':'offline'};
    return m[s] || 'unknown';
}
function stateBadge(s) {
    const m = {'FOCUSED':'badge-focused','DISTRACTED':'badge-distracted','FATIGUED':'badge-fatigued','LOW FOCUS':'badge-low','OFFLINE':'badge-offline'};
    return `<span class="state-badge ${m[s]||'badge-unknown'}">${s}</span>`;
}
function fatigueBar(f) {
    const pct = Math.min(100, f);
    const col = pct>=60?'#ff1744':pct>=30?'#ff6b35':'#00ff88';
    return `<div class="fatigue-wrap"><div class="fatigue-bar-bg"><div class="fatigue-bar-fill" style="width:${pct}%;background:${col};box-shadow:0 0 6px ${col}"></div></div><span style="font-size:.75rem;color:${col};font-family:'JetBrains Mono',monospace">${Math.round(pct)}</span></div>`;
}
function scoreBarColor(s) { return s>=70?'#00ff88':s>=40?'#ffd600':'#ff1744'; }

// ── COUNTER ANIM ──
function animNum(el, target) {
    const dur=600, start=performance.now(), from=parseFloat(el.textContent)||0;
    function tick(now) {
        const t=Math.min((now-start)/dur,1), ease=1-Math.pow(1-t,3);
        el.textContent = Math.round(from+(target-from)*ease);
        if(t<1) requestAnimationFrame(tick); else el.textContent=target;
    } requestAnimationFrame(tick);
}

// ── RENDER (called by WebSocket onmessage) ──
function render(data) {
    // overview
    animNum(document.getElementById('totalStudents'), data.total);
    const avgEl = document.getElementById('classAvg');
    const newAvg = data.avg_score || 0;
    animNum(avgEl, newAvg);
    avgEl.className = 'ov-val ' + scoreClass(newAvg);
    animNum(document.getElementById('distractedCount'), data.distracted_count);
    animNum(document.getElementById('fatiguedCount'),   data.fatigued_count);

    // critical class alert
    const banner = document.getElementById('criticalBanner');
    if (newAvg < 50 && data.total > 0) {
        document.body.classList.add('critical-alert');
        banner.classList.add('show');
        banner.textContent = `⚠ CLASS ATTENTION CRITICAL — Avg: ${newAvg}`;
    } else {
        document.body.classList.remove('critical-alert');
        banner.classList.remove('show');
    }

    // alerts — online students only
    const alertsBar = document.getElementById('alertsBar');
    alertsBar.innerHTML = '';
    Object.entries(data.students).forEach(([id, s]) => {
        if (s.status === 'OFFLINE') return;
        // XSS fix: id is already html.escape()'d server-side via Pydantic validator
        if (s.state === 'DISTRACTED')
            alertsBar.innerHTML += `<div class="alert-chip red">⚠ ${id} is DISTRACTED</div>`;
        if (s.fatigue >= 60)
            alertsBar.innerHTML += `<div class="alert-chip orange">😴 ${id} is FATIGUED</div>`;
        if (s.score < 40)
            alertsBar.innerHTML += `<div class="alert-chip red">📉 ${id} score critical: ${s.score}</div>`;
    });

    // table
    const tbody = document.getElementById('studentTableBody');
    if (Object.keys(data.students).length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="7">Waiting for students to connect...</td></tr>';
    } else {
        tbody.innerHTML = Object.entries(data.students).map(([id, s]) => {
            const offline = s.status === 'OFFLINE';
            const rowClass = offline ? 'state-offline' : `state-${stateClass(s.state)}`;
            return `
            <tr class="${rowClass}">
                <td>
                    <span style="font-family:'JetBrains Mono',monospace;font-weight:700;color:${offline?'#333':'#ccc'}">${id}</span>
                    ${offline ? '<span class="state-badge badge-offline" style="margin-left:6px">OFFLINE</span>' : ''}
                </td>
                <td><span class="score-cell ${offline?'':''+scoreClass(s.score)}" style="${offline?'color:#333':''}">${s.score}</span></td>
                <td>${offline ? '<span class="state-badge badge-offline">--</span>' : stateBadge(s.state)}</td>
                <td>${offline ? '<span style="color:#222;font-size:.75rem">--</span>' : fatigueBar(s.fatigue)}</td>
                <td><span style="font-family:'JetBrains Mono',monospace;font-size:.8rem;color:${offline?'#222':'#666'}">${s.gaze}</span></td>
                <td><span style="font-family:'JetBrains Mono',monospace;font-size:.8rem;color:${offline?'#222':'#555'}">${s.blinks}</span></td>
                <td><span style="font-family:'JetBrains Mono',monospace;font-size:.75rem;color:#333">${s.timestamp}</span></td>
            </tr>`;
        }).join('');
    }

    // score bars — online students only
    const barsDiv = document.getElementById('scoreBars');
    barsDiv.innerHTML = Object.entries(data.students)
        .filter(([, s]) => s.status === 'ONLINE')
        .sort((a, b) => b[1].score - a[1].score)
        .map(([id, s]) => {
            const col = scoreBarColor(s.score);
            return `<div class="score-bar-row">
                <div class="sbar-name">${id}</div>
                <div class="sbar-track"><div class="sbar-fill" style="width:${s.score}%;background:${col};color:${col}"></div></div>
                <div class="sbar-val" style="color:${col}">${s.score}</div>
            </div>`;
        }).join('');
}

// ── FIX 4: WebSocket with token auth ──
// Token is injected by server into the page as a data attribute
const _wsToken = document.body.dataset.apiToken || '';
let ws;
function connectWS() {
    ws = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(_wsToken)}`);
    ws.onopen  = () => console.log('[WS] Connected');
    ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.error === 'unauthorized') {
            console.error('[WS] Unauthorized — check API token');
            return;
        }
        render(data);
    };
    ws.onclose = () => { console.warn('[WS] Disconnected — retry in 2s'); setTimeout(connectWS, 2000); };
    ws.onerror = () => ws.close();
}
connectWS();
