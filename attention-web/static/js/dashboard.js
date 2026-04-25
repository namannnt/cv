// ── MATRIX RAIN ──
const canvas = document.getElementById('matrixCanvas');
const ctx = canvas.getContext('2d');
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;
const chars = '01アイウエオABCDEF@#$%';
const fontSize = 12;
const cols = Math.floor(canvas.width / fontSize);
const drops = Array(cols).fill(1);
function drawMatrix() {
    ctx.fillStyle = 'rgba(4,4,10,0.06)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#00e5ff';
    ctx.font = `${fontSize}px monospace`;
    drops.forEach((y, i) => {
        ctx.fillText(chars[Math.floor(Math.random() * chars.length)], i * fontSize, y * fontSize);
        if (y * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0;
        drops[i]++;
    });
}
setInterval(drawMatrix, 55);

// ── PARTICLES ──
const pc = document.getElementById('particles');
function spawnParticle() {
    const p = document.createElement('div');
    p.className = 'particle';
    const s = Math.random() * 3 + 1;
    const c = ['#00e5ff','#a259ff','#ff6b35','#00ff88'][Math.floor(Math.random()*4)];
    p.style.cssText = `width:${s}px;height:${s}px;left:${Math.random()*100}%;background:${c};box-shadow:0 0 ${s*3}px ${c};animation-duration:${Math.random()*8+6}s;animation-delay:${Math.random()*3}s;`;
    pc.appendChild(p);
    setTimeout(() => p.remove(), 14000);
}
setInterval(spawnParticle, 400);

// ── CHARTS ──
let timelineChart, stateChart, gazeChart;
Chart.defaults.color = '#444';
Chart.defaults.borderColor = '#0f0f1e';

function destroyCharts() {
    [timelineChart, stateChart, gazeChart].forEach(c => c && c.destroy());
}

function downsample(arr, max) {
    if (arr.length <= max) return arr;
    const step = arr.length / max;
    return Array.from({ length: max }, (_, i) => arr[Math.round(i * step)]);
}

// animate metric number
function animateNum(elId, target, suffix = '') {
    const el = document.getElementById(elId);
    const isFloat = String(target).includes('.');
    const duration = 1000;
    const start = performance.now();
    function tick(now) {
        const t = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);
        const val = target * ease;
        el.textContent = (isFloat ? val.toFixed(1) : Math.round(val)) + suffix;
        if (t < 1) requestAnimationFrame(tick);
        else {
            el.textContent = target + suffix;
            el.classList.add('flash');
            setTimeout(() => el.classList.remove('flash'), 800);
        }
    }
    requestAnimationFrame(tick);
}

function setBar(id, pct) {
    const el = document.getElementById(id);
    if (el) setTimeout(() => { el.style.width = pct + '%'; }, 300);
}

async function loadSession() {
    const filename = document.getElementById('sessionSelect').value;
    if (!filename) return;

    document.getElementById('decayText').textContent = 'Analyzing session...';

    const res  = await fetch(`/api/session/${filename}`);
    const data = await res.json();
    if (data.error) { alert(data.error); return; }

    const s = data.summary;

    animateNum('avgScore', parseFloat(s.avg_score), '/100');
    animateNum('quality',  parseFloat(s.quality),   '/100');
    setBar('avgBar',  s.avg_score);
    setBar('qualBar', s.quality);

    document.getElementById('focusTime').textContent    = s.focus_time;
    document.getElementById('distractions').textContent = `${s.distractions}`;
    document.getElementById('fatigue').textContent      = s.fatigue;
    document.getElementById('duration').textContent     = s.duration;
    document.getElementById('decayText').textContent    = s.decay;

    // update donut center
    document.getElementById('donutCenter').textContent = `${s.avg_score}`;

    destroyCharts();

    const attn   = downsample(data.timeline.attention, 300);
    const fat    = downsample(data.timeline.fatigue, 300);
    const labels = attn.map((_, i) => `${Math.round(i * (data.timeline.attention.length / attn.length))}s`);

    const tooltipStyle = {
        backgroundColor: '#08080f',
        borderColor: '#1a1a3a',
        borderWidth: 1,
        titleColor: '#fff',
        bodyColor: '#888',
        padding: 12,
        cornerRadius: 8
    };

    // timeline
    timelineChart = new Chart(document.getElementById('timelineChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Attention',
                    data: attn,
                    borderColor: '#00e5ff',
                    backgroundColor: (ctx) => {
                        const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 300);
                        g.addColorStop(0, '#00e5ff22');
                        g.addColorStop(1, '#00e5ff00');
                        return g;
                    },
                    borderWidth: 2.5,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.4
                },
                {
                    label: 'Fatigue',
                    data: fat,
                    borderColor: '#ff6b35',
                    backgroundColor: (ctx) => {
                        const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 300);
                        g.addColorStop(0, '#ff6b3522');
                        g.addColorStop(1, '#ff6b3500');
                        return g;
                    },
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            animation: { duration: 1200, easing: 'easeInOutQuart' },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: tooltipStyle
            },
            scales: {
                x: { ticks: { color: '#333', maxTicksLimit: 8 }, grid: { color: '#0a0a18' } },
                y: { ticks: { color: '#333' }, grid: { color: '#0a0a18' }, min: 0, max: 100 }
            }
        }
    });

    // state doughnut
    const stateColors = { FOCUSED:'#00ff88', 'LOW FOCUS':'#ffd600', DISTRACTED:'#ff1744', FATIGUED:'#ff6d00' };
    const sk = Object.keys(data.states);
    stateChart = new Chart(document.getElementById('stateChart'), {
        type: 'doughnut',
        data: {
            labels: sk,
            datasets: [{
                data: sk.map(k => data.states[k]),
                backgroundColor: sk.map(k => stateColors[k] || '#333'),
                borderWidth: 0,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            animation: { animateRotate: true, duration: 1400, easing: 'easeOutQuart' },
            plugins: {
                legend: { labels: { color: '#555', usePointStyle: true, padding: 16 } },
                tooltip: tooltipStyle
            },
            cutout: '72%'
        }
    });

    // gaze bar
    const gk = Object.keys(data.gaze);
    const gc = ['#00e5ff', '#a259ff', '#ff6b35'];
    gazeChart = new Chart(document.getElementById('gazeChart'), {
        type: 'bar',
        data: {
            labels: gk,
            datasets: [{
                data: gk.map(k => data.gaze[k]),
                backgroundColor: gk.map((_, i) => gc[i] || '#555'),
                borderRadius: 10,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            animation: { duration: 1000, easing: 'easeOutBounce' },
            plugins: { legend: { display: false }, tooltip: tooltipStyle },
            scales: {
                x: { ticks: { color: '#444' }, grid: { display: false } },
                y: { ticks: { color: '#333' }, grid: { color: '#0a0a18' } }
            }
        }
    });
}

window.onload = loadSession;
