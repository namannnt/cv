// ── MATRIX RAIN ──
const canvas = document.getElementById('matrixCanvas');
const ctx = canvas.getContext('2d');
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*()アイウエオカキクケコ';
const fontSize = 13;
const cols = Math.floor(canvas.width / fontSize);
const drops = Array(cols).fill(1);

function drawMatrix() {
    ctx.fillStyle = 'rgba(4,4,10,0.05)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#00e5ff';
    ctx.font = `${fontSize}px JetBrains Mono, monospace`;
    drops.forEach((y, i) => {
        const char = chars[Math.floor(Math.random() * chars.length)];
        ctx.fillText(char, i * fontSize, y * fontSize);
        if (y * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0;
        drops[i]++;
    });
}
setInterval(drawMatrix, 50);
window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
});

// ── PARTICLES ──
const particleContainer = document.getElementById('particles');
function createParticle() {
    const p = document.createElement('div');
    p.className = 'particle';
    const size = Math.random() * 4 + 1;
    const colors = ['#00e5ff', '#a259ff', '#ff6b35', '#00ff88'];
    const color = colors[Math.floor(Math.random() * colors.length)];
    p.style.cssText = `
        width:${size}px; height:${size}px;
        left:${Math.random() * 100}%;
        background:${color};
        box-shadow: 0 0 ${size * 3}px ${color};
        animation-duration:${Math.random() * 8 + 6}s;
        animation-delay:${Math.random() * 5}s;
    `;
    particleContainer.appendChild(p);
    setTimeout(() => p.remove(), 14000);
}
setInterval(createParticle, 300);

// ── COUNT UP ANIMATION ──
function countUp(el, target) {
    const duration = 2000;
    const start = performance.now();
    function update(now) {
        const t = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 4);
        el.textContent = Math.round(target * ease);
        if (t < 1) requestAnimationFrame(update);
        else el.textContent = target;
    }
    requestAnimationFrame(update);
}

// trigger count-up when visible
const observer = new IntersectionObserver(entries => {
    entries.forEach(e => {
        if (e.isIntersecting) {
            const el = e.target;
            countUp(el, parseInt(el.dataset.target));
            observer.unobserve(el);
        }
    });
}, { threshold: 0.5 });

document.querySelectorAll('.mini-val').forEach(el => observer.observe(el));

// ── FEAT BAR ANIMATION ──
const barObserver = new IntersectionObserver(entries => {
    entries.forEach(e => {
        if (e.isIntersecting) {
            e.target.style.width = e.target.style.getPropertyValue('--w') ||
                e.target.closest('.feat-card').querySelector('.feat-fill').style.getPropertyValue('--w');
        }
    });
}, { threshold: 0.3 });

document.querySelectorAll('.feat-fill').forEach(el => {
    barObserver.observe(el);
    // trigger after small delay
    setTimeout(() => { el.style.width = el.style.getPropertyValue('--w'); }, 600);
});
