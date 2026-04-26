// ══ MATRIX RAIN ══
const matrixCanvas = document.getElementById('matrixCanvas');
const mCtx = matrixCanvas.getContext('2d');
matrixCanvas.width = window.innerWidth; matrixCanvas.height = window.innerHeight;
const mChars = 'ABCDEF0123456789アイウエオカキ@#$%';
const mSize = 13, mCols = Math.floor(matrixCanvas.width / mSize);
const mDrops = Array(mCols).fill(1);
function drawMatrix() {
    mCtx.fillStyle = 'rgba(2,2,10,0.05)';
    mCtx.fillRect(0, 0, matrixCanvas.width, matrixCanvas.height);
    mCtx.fillStyle = '#00e5ff'; mCtx.font = `${mSize}px monospace`;
    mDrops.forEach((y, i) => {
        mCtx.globalAlpha = Math.random() * 0.5 + 0.1;
        mCtx.fillText(mChars[Math.floor(Math.random() * mChars.length)], i * mSize, y * mSize);
        if (y * mSize > matrixCanvas.height && Math.random() > 0.975) mDrops[i] = 0;
        mDrops[i]++;
    });
    mCtx.globalAlpha = 1;
}
setInterval(drawMatrix, 50);

// ══ NEBULA BACKGROUND ══
const nebCanvas = document.getElementById('nebulaCanvas');
const nCtx = nebCanvas.getContext('2d');
nebCanvas.width = window.innerWidth; nebCanvas.height = window.innerHeight;
let nebT = 0;
function drawNebula() {
    nCtx.clearRect(0, 0, nebCanvas.width, nebCanvas.height);
    const cx = nebCanvas.width / 2, cy = nebCanvas.height / 2;
    [[cx * 0.4, cy * 0.6, '#00e5ff', 0.04], [cx * 1.6, cy * 1.4, '#a259ff', 0.035], [cx + Math.sin(nebT) * 200, cy + Math.cos(nebT * 0.7) * 150, '#ff6b35', 0.025]].forEach(([x, y, c, a]) => {
        const g = nCtx.createRadialGradient(x, y, 0, x, y, 400);
        g.addColorStop(0, c.replace(')', `,${a})`).replace('rgb', 'rgba').replace('#', 'rgba(').replace('rgba(', 'rgba(').replace(/rgba\(([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2}),/, (_, r, g2, b) => `rgba(${parseInt(r,16)},${parseInt(g2,16)},${parseInt(b,16)},`));
        g.addColorStop(1, 'transparent');
        nCtx.fillStyle = g; nCtx.fillRect(0, 0, nebCanvas.width, nebCanvas.height);
    });
    nebT += 0.003;
    requestAnimationFrame(drawNebula);
}
drawNebula();

// ══ PARTICLE SYSTEM (WebGL-style on Canvas) ══
const pCanvas = document.getElementById('particleCanvas');
const pCtx = pCanvas.getContext('2d');
pCanvas.width = window.innerWidth; pCanvas.height = window.innerHeight;
const COLORS = ['#00e5ff', '#a259ff', '#ff6b35', '#00ff88', '#ffd600'];
class Particle {
    constructor() { this.reset(); }
    reset() {
        this.x = Math.random() * pCanvas.width;
        this.y = pCanvas.height + 10;
        this.vx = (Math.random() - 0.5) * 0.8;
        this.vy = -(Math.random() * 1.5 + 0.5);
        this.size = Math.random() * 3 + 0.5;
        this.color = COLORS[Math.floor(Math.random() * COLORS.length)];
        this.alpha = Math.random() * 0.7 + 0.3;
        this.life = 0; this.maxLife = Math.random() * 200 + 100;
        this.trail = [];
    }
    update() {
        this.trail.push({ x: this.x, y: this.y });
        if (this.trail.length > 12) this.trail.shift();
        this.x += this.vx; this.y += this.vy;
        this.vx += (Math.random() - 0.5) * 0.05;
        this.life++;
        if (this.life > this.maxLife || this.y < -10) this.reset();
    }
    draw() {
        // trail
        this.trail.forEach((pt, i) => {
            const a = (i / this.trail.length) * this.alpha * 0.4;
            pCtx.beginPath();
            pCtx.arc(pt.x, pt.y, this.size * (i / this.trail.length), 0, Math.PI * 2);
            pCtx.fillStyle = this.color.replace(')', `,${a})`).replace('#', 'rgba(').replace(/rgba\(([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2}),/, (_, r, g, b) => `rgba(${parseInt(r,16)},${parseInt(g,16)},${parseInt(b,16)},`);
            pCtx.fill();
        });
        // core
        pCtx.beginPath();
        pCtx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        pCtx.fillStyle = this.color;
        pCtx.shadowBlur = 15; pCtx.shadowColor = this.color;
        pCtx.globalAlpha = this.alpha * (1 - this.life / this.maxLife);
        pCtx.fill();
        pCtx.shadowBlur = 0; pCtx.globalAlpha = 1;
    }
}
const particles = Array.from({ length: 80 }, () => new Particle());
function animParticles() {
    pCtx.clearRect(0, 0, pCanvas.width, pCanvas.height);
    particles.forEach(p => { p.update(); p.draw(); });
    requestAnimationFrame(animParticles);
}
animParticles();

// ══ CURSOR GLOW ══
const cursorGlow = document.getElementById('cursorGlow');
document.addEventListener('mousemove', e => {
    cursorGlow.style.left = e.clientX + 'px';
    cursorGlow.style.top  = e.clientY + 'px';
});

// ══ RESIZE ══
window.addEventListener('resize', () => {
    [matrixCanvas, nebCanvas, pCanvas].forEach(c => { c.width = window.innerWidth; c.height = window.innerHeight; });
});

// ══ TABS ══
function showTab(name) {
    // hide all
    document.querySelectorAll('.tab-content').forEach(t => {
        t.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

    // show selected
    const target = document.getElementById(`tab-${name}`);
    if (target) target.classList.add('active');

    // activate correct button
    document.querySelectorAll('.tab-btn').forEach(b => {
        const txt = b.textContent.toLowerCase().trim();
        if (name === 'home' && txt === 'home') b.classList.add('active');
        else if (name === 'dashboard' && txt === 'dashboard') b.classList.add('active');
        else if (name === 'coach' && txt === 'ai coach') b.classList.add('active');
        else if (name === 'gamification' && txt.includes('progress')) b.classList.add('active');
    });

    if (name === 'gamification') loadGamification();

    if (name === 'dashboard') {
        const s = document.getElementById('sessionSelect');
        if (s && s.value) {
            // wait for tab to be visible then render charts
            setTimeout(() => loadSession(), 100);
        }
    }

    if (name === 'coach') {
        // coach data already loaded with session, just show it
        const cg = document.getElementById('coachGrid');
        if (cg && cg.children.length === 1 && cg.querySelector('.coach-empty')) {
            const s = document.getElementById('sessionSelect');
            if (s && s.value) setTimeout(() => loadSession(), 100);
        }
    }

    if (name === 'home') {
        setTimeout(() => {
            document.querySelectorAll('.feat-fill').forEach(el => {
                const m = el.getAttribute('style').match(/--w:([\d.]+%)/);
                if (m) el.style.width = m[1];
            });
        }, 500);
    }
}

// ══ COUNT UP ══
function countUp(el, target, suffix = '') {
    if (!el) return;
    const dur = 1600, start = performance.now(), isFloat = String(target).includes('.');
    function tick(now) {
        const t = Math.min((now - start) / dur, 1), ease = 1 - Math.pow(1 - t, 4), val = target * ease;
        el.textContent = (isFloat ? val.toFixed(1) : Math.round(val)) + suffix;
        if (t < 1) requestAnimationFrame(tick);
        else { el.textContent = target + suffix; el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 900); }
    }
    requestAnimationFrame(tick);
}
function setBar(id, pct) { const el = document.getElementById(id); if (el) setTimeout(() => { el.style.width = Math.min(100, pct) + '%'; }, 500); }

// ══ CHARTS ══
let timelineChart, stateChart, gazeChart;
Chart.defaults.color = '#333'; Chart.defaults.borderColor = '#0a0a1a';
function destroyCharts() { [timelineChart, stateChart, gazeChart].forEach(c => c && c.destroy()); }
function downsample(arr, max) { if (arr.length <= max) return arr; const s = arr.length / max; return Array.from({ length: max }, (_, i) => arr[Math.round(i * s)]); }
const TT = { backgroundColor:'#07070f', borderColor:'#1a1a3a', borderWidth:1, titleColor:'#fff', bodyColor:'#666', padding:14, cornerRadius:10 };

// ══ LOAD SESSION ══
async function loadSession() {
    const filename = document.getElementById('sessionSelect').value;
    if (!filename) return;
    document.getElementById('decayText').textContent = '⚡ Analyzing neural patterns...';
    const res = await fetch(`/api/session/${filename}`);
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    const s = data.summary;

    // make sure dashboard tab is visible before rendering charts
    const dashTab = document.getElementById('tab-dashboard');
    const wasHidden = !dashTab.classList.contains('active');
    if (wasHidden) dashTab.style.display = 'block';

    countUp(document.getElementById('avgScore'), parseFloat(s.avg_score), '/100');
    countUp(document.getElementById('quality'),  parseFloat(s.quality),   '/100');
    setBar('avgBar', s.avg_score); setBar('qualBar', s.quality);
    document.getElementById('focusTime').textContent    = s.focus_time;
    document.getElementById('distractions').textContent = `${s.distractions} (${s.distract_pct}%)`;
    document.getElementById('fatigue').textContent      = s.fatigue;
    document.getElementById('duration').textContent     = s.duration;
    document.getElementById('decayText').textContent    = s.decay;
    document.getElementById('donutCenter').textContent  = s.avg_score;

    // show feedback section for this session
    _showFeedbackSection(filename);

    // coach cards — always update regardless of active tab
    const cg = document.getElementById('coachGrid'); cg.innerHTML = '';
    data.feedback.forEach((msg, i) => {
        const icon = msg.split(' ')[0], text = msg.slice(icon.length + 1);
        const card = document.createElement('div');
        card.className = 'coach-card'; card.style.animationDelay = `${i * 0.07}s`;
        card.innerHTML = `<div class="coach-card-icon">${icon}</div><div class="coach-card-text">${text}</div>`;
        cg.appendChild(card);
    });

    destroyCharts();
    const attn = downsample(data.timeline.attention, 300), fat = downsample(data.timeline.fatigue, 300);
    const labels = attn.map((_, i) => `${Math.round(i * (data.timeline.attention.length / attn.length))}s`);

    timelineChart = new Chart(document.getElementById('timelineChart'), {
        type: 'line',
        data: { labels, datasets: [
            { label:'Attention', data:attn, borderColor:'#00e5ff', backgroundColor: ctx => { const g = ctx.chart.ctx.createLinearGradient(0,0,0,300); g.addColorStop(0,'#00e5ff22'); g.addColorStop(1,'#00e5ff00'); return g; }, borderWidth:2.5, pointRadius:0, fill:true, tension:0.4 },
            { label:'Fatigue',   data:fat,  borderColor:'#ff6b35', backgroundColor: ctx => { const g = ctx.chart.ctx.createLinearGradient(0,0,0,300); g.addColorStop(0,'#ff6b3522'); g.addColorStop(1,'#ff6b3500'); return g; }, borderWidth:2,   pointRadius:0, fill:true, tension:0.4 }
        ]},
        options: { responsive:true, animation:{duration:1400,easing:'easeInOutQuart'}, interaction:{mode:'index',intersect:false}, plugins:{legend:{display:false},tooltip:TT}, scales:{ x:{ticks:{color:'#222',maxTicksLimit:8},grid:{color:'#08081a'}}, y:{ticks:{color:'#222'},grid:{color:'#08081a'},min:0,max:100} } }
    });

    const SC = {FOCUSED:'#00ff88','LOW FOCUS':'#ffd600',DISTRACTED:'#ff1744',FATIGUED:'#ff6d00'};
    const sk = Object.keys(data.states);
    stateChart = new Chart(document.getElementById('stateChart'), {
        type:'doughnut', data:{ labels:sk, datasets:[{data:sk.map(k=>data.states[k]),backgroundColor:sk.map(k=>SC[k]||'#333'),borderWidth:0,hoverOffset:12}] },
        options:{ responsive:true, animation:{animateRotate:true,duration:1600,easing:'easeOutQuart'}, plugins:{legend:{labels:{color:'#444',usePointStyle:true,padding:14}},tooltip:TT}, cutout:'74%' }
    });

    const gk = Object.keys(data.gaze), gc = ['#00e5ff','#a259ff','#ff6b35'];
    gazeChart = new Chart(document.getElementById('gazeChart'), {
        type:'bar', data:{ labels:gk, datasets:[{data:gk.map(k=>data.gaze[k]),backgroundColor:gk.map((_,i)=>gc[i]||'#555'),borderRadius:12,borderSkipped:false}] },
        options:{ responsive:true, animation:{duration:1100,easing:'easeOutBounce'}, plugins:{legend:{display:false},tooltip:TT}, scales:{ x:{ticks:{color:'#333'},grid:{display:false}}, y:{ticks:{color:'#222'},grid:{color:'#08081a'}} } }
    });

    if (wasHidden) dashTab.style.display = '';
}

// ══ GAMIFICATION ══
async function loadGamification() {
    const res = await fetch('/api/gamification'), data = await res.json();
    countUp(document.getElementById('streakVal'),    data.streak);
    countUp(document.getElementById('sessionsVal'),  data.total_sessions);
    countUp(document.getElementById('highScoreVal'), data.high_score, '/100');
    countUp(document.getElementById('focusMinVal'),  data.total_focus_minutes || 0);
    const fl = document.getElementById('streakFlames'); fl.innerHTML = '';
    for (let i = 0; i < Math.min(data.streak, 7); i++) { const f = document.createElement('span'); f.className = 'flame'; f.textContent = '🔥'; fl.appendChild(f); }
    const grid = document.getElementById('badgesGrid'); grid.innerHTML = '';
    if (!data.badges?.length) { grid.innerHTML = '<div class="loading-badges">No badges yet — start a session!</div>'; return; }
    [...data.badges].sort((a,b) => b.unlocked - a.unlocked).forEach((badge, i) => {
        const card = document.createElement('div');
        card.className = `badge-card ${badge.unlocked ? 'unlocked' : 'locked'}`;
        card.style.animationDelay = `${i * 0.05}s`;
        card.innerHTML = `<span class="badge-icon">${badge.icon}</span><div class="badge-name">${badge.name}</div>${badge.unlocked ? '<span class="badge-unlocked-tag">✓ UNLOCKED</span>' : '<span class="badge-locked-tag">LOCKED</span>'}`;
        grid.appendChild(card);
    });
}

// ══ SESSION START/STOP ══
async function toggleSession() {
    const btn = document.getElementById('startBtn'), btnText = document.getElementById('startBtnText'), btnIcon = document.getElementById('startBtnIcon'), bar = document.getElementById('sessionStatusBar');
    const st = await (await fetch('/api/session/status')).json();
    if (st.running) { await stopSession(); return; }
    btnText.textContent = '⏳ Starting...'; btn.disabled = true;
    const mode = document.getElementById('modeSelect')?.value || '1';
    const res = await fetch('/api/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
    });
    const d = await res.json(); btn.disabled = false;
    if (d.status === 'started' || d.status === 'already_running') {
        btnText.textContent = '■ Stop Session'; btnIcon.textContent = '🔴'; btn.classList.add('running'); bar.style.display = 'flex';
        window._poll = setInterval(async () => {
            const s = await (await fetch('/api/session/status')).json();
            if (!s.running) {
                clearInterval(window._poll);
                if (s.crashed) {
                    // FIX 2: show crash message
                    const statusText = document.getElementById('sessionStatusText');
                    if (statusText) statusText.textContent = `⚠ Session crashed unexpectedly (exit code ${s.exit_code}). Please restart.`;
                    bar.style.borderLeftColor = '#ff1744';
                    btnText.textContent = '▶ Start Session';
                    btnIcon.textContent = '🧠';
                    btn.classList.remove('running');
                } else {
                    resetBtn();
                }
            }
        }, 3000);
    }
}
async function stopSession() { await fetch('/api/session/stop', {method:'POST'}); clearInterval(window._poll); resetBtn(); }
function resetBtn() {
    const btn = document.getElementById('startBtn'); if (!btn) return;
    document.getElementById('startBtnText').textContent = '▶ Start Session';
    document.getElementById('startBtnIcon').textContent = '🧠';
    btn.classList.remove('running');
    document.getElementById('sessionStatusBar').style.display = 'none';
}

// ══ INIT ══
window.onload = () => {
    setTimeout(() => document.querySelectorAll('.feat-fill').forEach(el => { const m = el.getAttribute('style').match(/--w:([\d.]+%)/); if (m) el.style.width = m[1]; }), 700);
    document.querySelectorAll('.mini-val').forEach(el => countUp(el, parseInt(el.dataset.target)));
    // auto load latest session on startup
    const sel = document.getElementById('sessionSelect');
    if (sel?.value) loadSession();
};

// ══ FEEDBACK + CALIBRATION ══
const _feedback = { attention: null, fatigue: null };
let _currentSessionId = null;

function setFeedback(type, value) {
    _feedback[type] = value;

    // update button styles
    const prefix = type === 'attention' ? 'attention' : 'fatigue';
    document.querySelectorAll(`.fq-btn`).forEach(btn => {
        const isThisType = btn.getAttribute('onclick').includes(`'${type}'`);
        if (!isThisType) return;
        btn.classList.remove('selected');
    });
    // mark selected button
    document.querySelectorAll(`.fq-btn`).forEach(btn => {
        const onclick = btn.getAttribute('onclick') || '';
        if (!onclick.includes(`'${type}'`)) return;
        const isYes = onclick.includes('true');
        if ((isYes && value === true) || (!isYes && value === false)) {
            btn.classList.add('selected');
        }
    });

    // enable submit when both answered
    const btn = document.getElementById('submitFeedbackBtn');
    if (btn) btn.disabled = (_feedback.attention === null || _feedback.fatigue === null);
}

async function submitFeedback() {
    if (!_currentSessionId || _feedback.attention === null || _feedback.fatigue === null) return;

    const btn = document.getElementById('submitFeedbackBtn');
    btn.disabled = true;
    btn.textContent = 'Submitting...';

    const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id:     _currentSessionId,
            user_attention: _feedback.attention,
            user_fatigue:   _feedback.fatigue
        })
    });

    const data = await res.json();
    const statusEl = document.getElementById('calibrationStatus');

    if (data.status === 'ok') {
        btn.textContent = '✅ Feedback Submitted';
        if (data.changed) {
            statusEl.textContent = `System adapted based on your feedback — ${data.summary}`;
        } else {
            statusEl.textContent = 'Feedback recorded. No calibration change needed.';
        }
    } else if (data.status === 'duplicate') {
        btn.textContent = '✅ Already Recorded';
        statusEl.textContent = 'Feedback for this session was already submitted.';
    } else {
        btn.textContent = 'Submit Feedback';
        btn.disabled = false;
        statusEl.textContent = `Error: ${data.error || 'Unknown error'}`;
    }
}

// show feedback section when a session is loaded
function _showFeedbackSection(sessionId) {
    _currentSessionId = sessionId.replace('.csv', '');
    _feedback.attention = null;
    _feedback.fatigue   = null;

    const section = document.getElementById('feedbackSection');
    const btn     = document.getElementById('submitFeedbackBtn');
    const status  = document.getElementById('calibrationStatus');

    if (section) section.style.display = 'block';
    if (btn)     { btn.disabled = true; btn.textContent = 'Submit Feedback'; }
    if (status)  status.textContent = '';

    // reset button styles
    document.querySelectorAll('.fq-btn').forEach(b => b.classList.remove('selected'));

    // load current calibration summary
    fetch('/api/calibration').then(r => r.json()).then(cal => {
        if (status && cal.sessions_used > 0) {
            status.textContent = cal.summary;
        }
    }).catch(() => {});
}

// ══ CAMERA PREVIEW (Option A — local only, no video transmitted) ══
async function startCameraPreview() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' },
            audio: false
        });
        const video   = document.getElementById('cameraFeed');
        const overlay = document.getElementById('cameraOverlay');
        const box     = document.getElementById('cameraBox');

        video.srcObject = stream;
        video.classList.add('active');
        overlay.classList.add('hidden');
        box.classList.add('live');

        // store stream so we can stop it later
        window._cameraStream = stream;

    } catch (err) {
        const overlay = document.getElementById('cameraOverlay');
        if (overlay) {
            overlay.innerHTML = `<div style="text-align:center;padding:20px;color:#ff1744;font-size:.8rem;font-family:'JetBrains Mono',monospace">
                ⚠ Camera access denied<br><span style="color:#444;font-size:.7rem">Allow camera in browser settings</span>
            </div>`;
        }
    }
}

function stopCameraPreview() {
    if (window._cameraStream) {
        window._cameraStream.getTracks().forEach(t => t.stop());
        window._cameraStream = null;
        const video = document.getElementById('cameraFeed');
        if (video) { video.srcObject = null; video.classList.remove('active'); }
        const box = document.getElementById('cameraBox');
        if (box) box.classList.remove('live');
    }
}

// auto-start camera when Home tab is active
const _origShowTab = showTab;
// override showTab to handle camera
window.showTab = function(name) {
    _origShowTab(name);
    if (name !== 'home') stopCameraPreview();
};
