import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'attention-monitor'))

from flask import Flask, render_template, jsonify, request, Response
import glob
import pandas as pd
import json
import subprocess
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from intelligence.calibration import CalibrationManager, store_feedback
from utils.app_logger import get_logger
from utils.frame_buffer import read as read_frame

# ── FIX 1: Load .env ──
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

log = get_logger("attention_web")

session_process = None
_counted_sessions = set()

app = Flask(__name__)

LOG_DIR    = os.path.join(os.path.dirname(__file__), '..', 'attention-monitor', 'data', 'logs')
STATS_FILE = os.path.join(os.path.dirname(__file__), '..', 'attention-monitor', 'data', 'user_stats.json')
DASHBOARD_PORT = int(os.getenv("STUDENT_DASHBOARD_PORT", 5000))


def get_all_sessions():
    files = sorted(glob.glob(f"{LOG_DIR}/session_*.csv"), reverse=True)
    return [os.path.basename(f) for f in files]


def _update_gamification(avg_score, focus_minutes):
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {"streak": 0, "last_date": "", "total_sessions": 0,
                    "high_score": 0, "total_focus_minutes": 0}

        today     = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        if data["last_date"] == yesterday:
            data["streak"] += 1
        elif data["last_date"] != today:
            data["streak"] = 1

        data["last_date"]           = today
        data["total_sessions"]      = data.get("total_sessions", 0) + 1
        data["high_score"]          = max(data.get("high_score", 0), avg_score)
        data["total_focus_minutes"] = data.get("total_focus_minutes", 0) + focus_minutes

        with open(STATS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


@app.route("/video_feed")
def video_feed():
    """MJPEG stream of the annotated CV frames from main.py."""
    def generate():
        import time
        while True:
            frame = read_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                # send a placeholder black frame when no session running
                import cv2, numpy as np
                blank = np.zeros((360, 640, 3), dtype=np.uint8)
                cv2.putText(blank, "Start a session to see live feed",
                            (80, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 229, 255), 2)
                _, jpeg = cv2.imencode('.jpg', blank)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.033)  # ~30fps

    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/")
def index():
    sessions = get_all_sessions()
    return render_template("index.html", sessions=sessions)


@app.route("/api/session/start", methods=["POST"])
def start_session():
    global session_process
    if session_process and session_process.poll() is None:
        return jsonify({"status": "already_running"})

    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode", "1"))
    if mode not in ("1", "2", "3"):
        mode = "1"

    main_path  = os.path.join(os.path.dirname(__file__), '..', 'attention-monitor', 'main.py')
    python_exe = os.path.join(os.path.dirname(__file__), '..', 'attention-monitor', 'venv', 'Scripts', 'python.exe')
    if not os.path.exists(python_exe):
        python_exe = 'python'

    session_process = subprocess.Popen(
        [python_exe, main_path],
        cwd=os.path.join(os.path.dirname(__file__), '..', 'attention-monitor'),
        stdin=subprocess.PIPE
    )
    try:
        session_process.stdin.write(f"{mode}\n".encode())
        session_process.stdin.flush()
    except Exception:
        pass

    return jsonify({"status": "started"})


@app.route("/api/session/stop", methods=["POST"])
def stop_session():
    global session_process
    if session_process and session_process.poll() is None:
        session_process.terminate()
        session_process = None
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})


# ── FIX 2: Crash detection ──
@app.route("/api/session/status")
def session_status():
    global session_process
    if session_process is None:
        return jsonify({"running": False, "crashed": False})

    exit_code = session_process.poll()
    if exit_code is None:
        return jsonify({"running": True, "crashed": False})

    # process has exited
    crashed = exit_code != 0
    if crashed:
        log.error(f"Session process crashed at {datetime.now().isoformat()} with exit_code={exit_code}")
    return jsonify({"running": False, "crashed": crashed, "exit_code": exit_code})


@app.route("/api/session/<filename>")
def session_data(filename):
    if not re.match(r'^session_\d{8}_\d{6}\.csv$', filename):
        return jsonify({"error": "Invalid filename"}), 400

    file_path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    df = pd.read_csv(file_path)
    if df.empty:
        return jsonify({"error": "Empty session"}), 400

    total     = len(df)
    focus_sec = int((df["state"] == "FOCUSED").sum())
    distract  = int((df["state"] == "DISTRACTED").sum())
    fatigue   = int((df["fatigue_score"] > 0).sum())
    avg_score = round(df["attention_score"].mean(), 1)
    quality   = max(0, min(100, round((avg_score * 0.5) - (distract * 2) - (fatigue * 3), 1)))

    mid = len(df) // 2
    fh  = round(df["attention_score"][:mid].mean(), 1)
    sh  = round(df["attention_score"][mid:].mean(), 1)
    if sh < fh - 5:   decay = f"📉 Focus decreased over session ({fh} → {sh})"
    elif sh > fh + 5: decay = f"📈 Focus improved over session ({fh} → {sh})"
    else:             decay = f"➡️ Focus stayed consistent ({fh} → {sh})"

    distract_pct = round((distract / total) * 100, 1)
    feedback = []
    if avg_score > 80:   feedback.append("🔥 Excellent focus! Your attention was consistently high.")
    elif avg_score > 60: feedback.append("👍 Good focus overall, but some dips detected.")
    elif avg_score > 40: feedback.append("⚠️ Moderate focus. Try reducing background distractions.")
    else:                feedback.append("🔴 Low focus detected. Consider shorter, more intense sessions.")

    if distract_pct > 40:   feedback.append("📱 Very high distraction rate. Remove phone/notifications.")
    elif distract_pct > 20: feedback.append("👀 Frequent distractions. Try facing away from windows.")
    elif distract < 5:      feedback.append("✅ Very few distractions — great environment control!")

    if fatigue > 30:   feedback.append("😴 Heavy fatigue detected. Use 25-5 Pomodoro breaks.")
    elif fatigue > 10: feedback.append("🟠 Some fatigue detected. Blink more and rest your eyes.")
    else:              feedback.append("💪 Low fatigue — your energy levels were good this session.")

    focus_min = focus_sec // 60
    if focus_min >= 20:   feedback.append("⏱ Strong sustained focus — you maintained attention well.")
    elif focus_min >= 10: feedback.append("⏳ Moderate focus duration. Try to extend focused blocks.")
    else:                 feedback.append("⌛ Short focus periods. Eliminate distractions before starting.")

    if avg_score < 60 and distract_pct > 30:
        feedback.append("💡 Tip: Try Pomodoro — 25 min focus, 5 min break.")
    elif avg_score > 75 and fatigue < 5:
        feedback.append("💡 Tip: You're performing well — consider slightly longer sessions.")

    if filename not in _counted_sessions:
        _update_gamification(avg_score, focus_sec // 60)
        _counted_sessions.add(filename)

    return jsonify({
        "summary": {
            "avg_score":    avg_score,
            "quality":      quality,
            "focus_time":   f"{focus_sec // 60}m {focus_sec % 60}s",
            "focus_pct":    round((focus_sec / total) * 100, 1),
            "distractions": distract,
            "distract_pct": distract_pct,
            "fatigue":      fatigue,
            "duration":     f"{total // 60}m {total % 60}s",
            "decay":        decay,
        },
        "timeline": {
            "attention": df["attention_score"].tolist(),
            "fatigue":   df["fatigue_score"].tolist(),
        },
        "states":   df["state"].value_counts().to_dict(),
        "gaze":     df["gaze"].value_counts().to_dict(),
        "feedback": feedback,
    })


@app.route("/api/gamification")
def gamification_data():
    if not os.path.exists(STATS_FILE):
        return jsonify({"streak": 0, "last_date": "", "total_sessions": 0,
                        "high_score": 0, "total_focus_minutes": 0, "badges": []})

    with open(STATS_FILE, "r") as f:
        data = json.load(f)

    streak   = data.get("streak", 0)
    score    = data.get("high_score", 0)
    sessions = data.get("total_sessions", 0)
    focus_m  = data.get("total_focus_minutes", 0)

    badges = []
    if streak >= 3:    badges.append({"icon": "🔥", "name": "3-Day Streak",    "unlocked": True})
    if streak >= 7:    badges.append({"icon": "🏆", "name": "7-Day Warrior",   "unlocked": True})
    if streak >= 30:   badges.append({"icon": "💀", "name": "30-Day Legend",   "unlocked": True})
    if score > 85:     badges.append({"icon": "🎯", "name": "Focus Master",    "unlocked": True})
    if score >= 95:    badges.append({"icon": "🧠", "name": "Attention God",   "unlocked": True})
    if sessions >= 5:  badges.append({"icon": "📚", "name": "5 Sessions Done", "unlocked": True})
    if sessions >= 20: badges.append({"icon": "🚀", "name": "20 Sessions Pro", "unlocked": True})
    if focus_m >= 60:  badges.append({"icon": "⏱", "name": "1 Hour Focused",  "unlocked": True})
    if focus_m >= 300: badges.append({"icon": "⚡", "name": "5 Hours Legend",  "unlocked": True})

    all_badges = [
        {"icon": "🔥", "name": "3-Day Streak"}, {"icon": "🏆", "name": "7-Day Warrior"},
        {"icon": "💀", "name": "30-Day Legend"}, {"icon": "🎯", "name": "Focus Master"},
        {"icon": "🧠", "name": "Attention God"}, {"icon": "📚", "name": "5 Sessions Done"},
        {"icon": "🚀", "name": "20 Sessions Pro"}, {"icon": "⏱", "name": "1 Hour Focused"},
        {"icon": "⚡", "name": "5 Hours Legend"},
    ]
    unlocked_names = {b["name"] for b in badges}
    for b in all_badges:
        if b["name"] not in unlocked_names:
            badges.append({"icon": b["icon"], "name": b["name"], "unlocked": False})

    data["badges"] = badges
    return jsonify(data)


@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid JSON"}), 400

    session_id     = body.get("session_id", "")
    user_attention = body.get("user_attention")
    user_fatigue   = body.get("user_fatigue")

    if not session_id or user_attention is None or user_fatigue is None:
        return jsonify({"error": "Missing fields"}), 400

    if not re.match(r'^session_\d{8}_\d{6}$', session_id):
        return jsonify({"error": "Invalid session_id format"}), 400

    csv_path = os.path.join(LOG_DIR, session_id + ".csv")
    if not os.path.exists(csv_path):
        return jsonify({"error": "Session not found"}), 404

    df = pd.read_csv(csv_path)
    if df.empty:
        return jsonify({"error": "Empty session"}), 400

    avg_score   = round(df["attention_score"].mean(), 1)
    avg_fatigue = round(df["fatigue_score"].mean(), 1)

    stored = store_feedback(session_id, avg_score, avg_fatigue,
                            bool(user_attention), bool(user_fatigue))
    if not stored:
        return jsonify({"status": "duplicate", "message": "Feedback already recorded"}), 200

    cal     = CalibrationManager()
    changed = cal.update_from_feedback(avg_score, avg_fatigue,
                                       bool(user_attention), bool(user_fatigue))
    return jsonify({"status": "ok", "changed": changed, "summary": cal.summary()}), 200


@app.route("/api/calibration")
def calibration_status():
    cal = CalibrationManager()
    return jsonify({
        "blink_offset":      cal.blink_offset,
        "gaze_scale":        cal.gaze_scale,
        "fatigue_threshold": cal.fatigue_threshold,
        "fatigue_offset":    cal.params.get("fatigue_offset", 0),
        "summary":           cal.summary(),
        "sessions_used":     cal.params.get("sessions_used", 0)
    })


if __name__ == "__main__":
    app.run(debug=True, port=DASHBOARD_PORT)
