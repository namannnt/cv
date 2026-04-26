/**
 * monitor.js — Browser-based attention monitoring using MediaPipe Face Mesh
 * Fixed: distraction detection, fatigue accumulation, gaze-off tracking
 */

class AttentionMonitor {
    constructor(videoEl, canvasEl, onData) {
        this.video   = videoEl;
        this.canvas  = canvasEl;
        this.ctx     = canvasEl.getContext('2d');
        this.onData  = onData;
        this.running = false;

        // Blink tracking
        this._blinkCount    = 0;
        this._blinkCooldown = 0;
        this._prevEAR       = 1.0;
        this._eyeClosedStart = null;
        this._closureDur    = 0;
        this._blinkTimes    = [];  // timestamps of blinks in last 60s

        // Gaze-off tracking (face present but looking away)
        this._gazeOffStart  = null;
        this._gazeOffTime   = 0;   // seconds looking away (not CENTER)

        // Face-off tracking (no face detected)
        this._faceOffStart  = null;
        this._faceOffTime   = 0;

        // Fatigue — rolling accumulator (0–100), decays slowly
        this._fatigueAcc    = 0;
        this._lastFrameTime = Date.now();

        this._sessionStart  = Date.now();
        this._lastSend      = 0;

        this._faceMesh = null;
        this._camera   = null;
        this._stream   = null;
    }

    async start() {
        await this._loadMediaPipe();
        await this._startCamera();
        this.running = true;
    }

    stop() {
        this.running = false;
        if (this._camera) { try { this._camera.stop(); } catch(e) {} }
        if (this._stream) { this._stream.getTracks().forEach(t => t.stop()); }
        if (this._faceMesh) { try { this._faceMesh.close(); } catch(e) {} }
    }

    async _loadMediaPipe() {
        if (window.FaceMesh) return;
        await this._loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js');
        await this._loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js');
        await this._loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/drawing_utils/drawing_utils.js');
    }

    _loadScript(src) {
        return new Promise((resolve, reject) => {
            if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
            const s = document.createElement('script');
            s.src = src; s.crossOrigin = 'anonymous';
            s.onload = resolve; s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    async _startCamera() {
        this._stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' },
            audio: false
        });
        this.video.srcObject = this._stream;
        await new Promise(r => { this.video.onloadedmetadata = r; });
        this.video.play();

        this._faceMesh = new window.FaceMesh({
            locateFile: f => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${f}`
        });
        this._faceMesh.setOptions({
            maxNumFaces: 1,
            refineLandmarks: true,
            minDetectionConfidence: 0.5,
            minTrackingConfidence: 0.5,
        });
        this._faceMesh.onResults(r => this._onResults(r));

        this._camera = new window.Camera(this.video, {
            onFrame: async () => {
                if (this.running) await this._faceMesh.send({ image: this.video });
            },
            width: 640, height: 480,
        });
        await this._camera.start();
    }

    _onResults(results) {
        if (!this.running) return;

        const now = Date.now();
        const dt  = Math.min((now - this._lastFrameTime) / 1000, 0.5); // seconds since last frame, capped
        this._lastFrameTime = now;

        const w = this.canvas.width  = this.video.videoWidth  || 640;
        const h = this.canvas.height = this.video.videoHeight || 480;
        this.ctx.clearRect(0, 0, w, h);
        this.ctx.drawImage(this.video, 0, 0, w, h);

        if (!results.multiFaceLandmarks || !results.multiFaceLandmarks.length) {
            // No face detected
            this._faceOffStart = this._faceOffStart || now;
            this._faceOffTime  = (now - this._faceOffStart) / 1000;
            this._gazeOffStart = null;
            this._gazeOffTime  = 0;

            // Fatigue decays slowly when no face
            this._fatigueAcc = Math.max(0, this._fatigueAcc - dt * 2);

            const offTime = this._faceOffTime;
            const score   = Math.max(0, 100 - offTime * 15);
            const state   = offTime > 2 ? 'DISTRACTED' : 'LOW FOCUS';

            this._drawOverlay({ score, state, gaze: 'AWAY', ear: 0, fatigue: this._fatigueAcc }, w, h);
            this._maybeSend(now, true, { score, state, fatigue: this._fatigueAcc, gaze: 'CENTER', blinks: this._blinkCount });
            return;
        }

        // Face detected — reset face-off timer
        this._faceOffStart = null;
        this._faceOffTime  = 0;

        const lm = results.multiFaceLandmarks[0];

        // ── EAR ──
        const ear       = this._calcEAR(lm);
        const eyeClosed = ear < 0.22;  // MediaPipe normalized coords — slightly higher threshold

        // ── Blink detection ──
        if (eyeClosed && this._prevEAR >= 0.22 && this._blinkCooldown <= 0) {
            this._blinkCount++;
            this._blinkTimes.push(now);
            this._blinkCooldown = 6;
        }
        if (this._blinkCooldown > 0) this._blinkCooldown--;
        this._prevEAR = ear;

        // Prune blinks older than 60s
        this._blinkTimes = this._blinkTimes.filter(t => now - t < 60000);
        const blinkRate  = this._blinkTimes.length;

        // ── Eye closure duration ──
        if (eyeClosed) {
            this._eyeClosedStart = this._eyeClosedStart || now;
            this._closureDur = (now - this._eyeClosedStart) / 1000;
        } else {
            this._eyeClosedStart = null;
            this._closureDur = 0;
        }

        // ── Gaze ──
        const gaze = this._calcGaze(lm);

        // ── Gaze-off time tracking ──
        // Tracks how long the student has been looking away (LEFT/RIGHT/DOWN)
        if (gaze !== 'CENTER') {
            this._gazeOffStart = this._gazeOffStart || now;
            this._gazeOffTime  = (now - this._gazeOffStart) / 1000;
        } else {
            this._gazeOffStart = null;
            this._gazeOffTime  = 0;
        }

        // ── Fatigue accumulator ──
        // Increases based on signals, decays slowly when all is normal
        const sessionMin = (now - this._sessionStart) / 60000;
        this._fatigueAcc = this._updateFatigue(this._fatigueAcc, dt, ear, blinkRate, this._closureDur, sessionMin);

        // ── Attention Score ──
        const score = this._calcScore(gaze, this._gazeOffTime, eyeClosed, blinkRate, this._closureDur);

        // ── State ──
        const state = this._classify(score, this._gazeOffTime, this._faceOffTime, this._fatigueAcc);

        this._drawOverlay({ score, state, gaze, ear, fatigue: this._fatigueAcc }, w, h);
        this._maybeSend(now, true, { score, state, fatigue: this._fatigueAcc, gaze, blinks: this._blinkCount });
    }

    _calcEAR(lm) {
        const eye = (p1, p2, p3, p4, p5, p6) => {
            const d = (a, b) => Math.hypot(lm[a].x - lm[b].x, lm[a].y - lm[b].y);
            return (d(p2, p6) + d(p3, p5)) / (2 * d(p1, p4));
        };
        const left  = eye(33, 160, 158, 133, 153, 144);
        const right = eye(362, 385, 387, 263, 373, 380);
        return (left + right) / 2;
    }

    _calcGaze(lm) {
        // Left eye iris ratio
        const lEL = lm[33].x, lER = lm[133].x;
        const lIris = lm[468] ? lm[468].x : (lEL + lER) / 2;
        const lRatio = (lIris - lEL) / (lER - lEL + 1e-6);

        // Right eye iris ratio
        const rEL = lm[362].x, rER = lm[263].x;
        const rIris = lm[473] ? lm[473].x : (rEL + rER) / 2;
        const rRatio = (rIris - rEL) / (rER - rEL + 1e-6);

        const ratio = (lRatio + rRatio) / 2;

        // Head pitch — looking down
        const noseTip = lm[1], chin = lm[152];
        const pitchRatio = noseTip.y / (chin.y + 1e-6);
        if (pitchRatio < 0.70) return 'DOWN';

        // Head yaw — looking left/right using nose vs face width
        const noseX    = lm[1].x;
        const faceLeft = lm[234].x;  // left cheek
        const faceRight= lm[454].x;  // right cheek
        const faceW    = faceRight - faceLeft;
        const noseRel  = (noseX - faceLeft) / (faceW + 1e-6);
        if (noseRel < 0.38) return 'RIGHT';  // face turned right = nose shifts left
        if (noseRel > 0.62) return 'LEFT';

        // Iris-based fine gaze
        if (ratio < 0.35) return 'LEFT';
        if (ratio > 0.65) return 'RIGHT';
        return 'CENTER';
    }

    _updateFatigue(current, dt, ear, blinkRate, closureDur, sessionMin) {
        // Fatigue increases based on signals, decays when normal
        let delta = 0;

        // Low EAR = droopy eyes = fatigue signal
        if (ear < 0.18)      delta += 15 * dt;  // very droopy
        else if (ear < 0.22) delta += 8  * dt;  // somewhat droopy
        else if (ear > 0.28) delta -= 5  * dt;  // wide open = alert, decay faster

        // Prolonged eye closure
        if (closureDur > 2.0) delta += 20 * dt;
        else if (closureDur > 1.0) delta += 10 * dt;

        // Abnormal blink rate
        if (blinkRate > 30)     delta += 5 * dt;  // excessive blinking
        else if (blinkRate < 5) delta += 3 * dt;  // too few blinks (staring)
        else                    delta -= 2 * dt;  // normal range, slight decay

        // Session duration fatigue
        if (sessionMin > 45) delta += 2 * dt;
        if (sessionMin > 30) delta += 1 * dt;

        // Natural decay when no strong signals
        if (delta <= 0) delta -= 1 * dt;

        return Math.min(100, Math.max(0, current + delta));
    }

    _calcScore(gaze, gazeOffTime, eyeClosed, blinkRate, closureDur) {
        let s = 100;

        // Gaze penalty — proportional to how long they've been looking away
        if (gaze !== 'CENTER') {
            s -= Math.min(50, gazeOffTime * 12);
        }

        // Eye closure penalty — scales with duration
        // Brief blink (< 0.3s): no penalty
        // Short closure (0.3-1s): -20
        // Prolonged closure (1-3s): up to -50
        // Eyes closed whole time (3s+): -70
        if (closureDur > 3.0)      s -= 70;
        else if (closureDur > 1.0) s -= 20 + (closureDur - 1.0) * 15;
        else if (closureDur > 0.3) s -= 20;

        // High blink rate penalty
        if (blinkRate > 25) s -= 15;

        return Math.max(0, Math.min(100, s));
    }

    _classify(score, gazeOffTime, faceOffTime, fatigue) {
        // Fatigue takes priority
        if (fatigue >= 65) return 'FATIGUED';

        // Face completely away for 2+ seconds
        if (faceOffTime > 2) return 'DISTRACTED';

        // Gaze away for 3+ seconds = distracted
        if (gazeOffTime > 3) return 'DISTRACTED';

        // Score-based
        if (score > 70) return 'FOCUSED';
        if (score > 45) return 'LOW FOCUS';
        return 'DISTRACTED';
    }

    _drawOverlay(data, w, h) {
        const ctx = this.ctx;
        const stateColors = {
            'FOCUSED':    '#00ff88',
            'LOW FOCUS':  '#ffd600',
            'DISTRACTED': '#ff1744',
            'FATIGUED':   '#ff6b35',
        };

        if (!data) return;

        const color = stateColors[data.state] || '#00e5ff';

        // Border color = state
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(2, 2, w - 4, h - 4);

        // HUD
        ctx.fillStyle = 'rgba(2,2,10,0.75)';
        ctx.fillRect(0, 0, w, 88);

        ctx.font = 'bold 14px JetBrains Mono, monospace';
        ctx.fillStyle = '#00e5ff';
        ctx.fillText(`Score: ${data.score.toFixed(0)}`, 12, 22);
        ctx.fillStyle = color;
        ctx.fillText(`State: ${data.state}`, 12, 44);
        ctx.fillStyle = data.fatigue >= 65 ? '#ff6b35' : '#888';
        ctx.fillText(`Fatigue: ${data.fatigue.toFixed(0)}%`, 12, 66);
        ctx.fillStyle = data.gaze !== 'CENTER' ? '#ff1744' : '#a259ff';
        ctx.fillText(`Gaze: ${data.gaze}`, 220, 22);
        ctx.fillStyle = '#555';
        ctx.fillText(`EAR: ${data.ear.toFixed(3)}`, 220, 44);
    }

    _maybeSend(now, hasFace, data) {
        if (now - this._lastSend < 1000) return;
        this._lastSend = now;
        if (hasFace && data) this.onData(data);
    }
}
