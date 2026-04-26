import cv2
import os
import sys
import time
import queue
import threading
import requests
from dotenv import load_dotenv

# ── Load .env from project root ──
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ── FIX 1: Load secrets from environment ──
TEACHER_SERVER = os.getenv("TEACHER_SERVER_URL")
STUDENT_ID     = os.getenv("STUDENT_ID")
API_TOKEN      = os.getenv("API_TOKEN")

for _var, _name in [(TEACHER_SERVER, "TEACHER_SERVER_URL"),
                    (STUDENT_ID,     "STUDENT_ID"),
                    (API_TOKEN,      "API_TOKEN")]:
    if not _var:
        raise ValueError(
            f"Missing required environment variable: {_name}\n"
            f"Copy .env.example to .env and fill in the values."
        )

# ── FIX 3: Auto-download model file if missing ──
def ensure_model():
    model_path = os.path.join(os.path.dirname(__file__), "models", "face_landmarker.task")
    if os.path.exists(model_path):
        return
    model_url = (
        "https://storage.googleapis.com/mediapipe-models/"
        "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    )
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    print("Model file not found. Downloading face_landmarker.task...")
    try:
        import urllib.request
        urllib.request.urlretrieve(model_url, model_path)
        print("Download complete.")
    except Exception as e:
        print(f"\nERROR: Could not download model file: {e}")
        print(f"Please download it manually from:\n  {model_url}")
        print(f"And save it to: {model_path}")
        sys.exit(1)

ensure_model()

from perception.face_mesh import FaceMeshDetector
from features.blink import BlinkDetector
from features.gaze import GazeDetector
from features.movement import MovementDetector
from intelligence.scoring import AttentionScorer
from intelligence.classification import StateClassifier
from intelligence.fatigue import FatigueDetector
from intelligence.personalization import Personalization
from intelligence.context import ContextManager
from intelligence.gamification import Gamification
from intelligence.intervention import InterventionSystem
from intelligence.calibration import CalibrationManager
from utils.buffer import TimeBuffer
from utils.temporal_smoother import TemporalSmoother
from utils.app_logger import get_logger
from utils.frame_buffer import write as write_frame
from data.logger import SessionLogger
from data.database import SessionDB

log = get_logger("attention_monitor")

# ── FIX 5: Queue-based sender (one persistent thread, no per-POST threads) ──
_data_queue: queue.Queue = queue.Queue(maxsize=10)
_http_session = requests.Session()

def _sender_worker():
    """Single background thread that drains the queue and POSTs to teacher server."""
    while True:
        payload = _data_queue.get()
        if payload is None:
            break
        try:
            _http_session.post(
                TEACHER_SERVER,
                json=payload,
                headers={"x-api-token": API_TOKEN},
                timeout=2.0
            )
        except Exception as e:
            log.warning(f"Teacher send failed: {e}")

_sender_thread = threading.Thread(target=_sender_worker, daemon=True)
_sender_thread.start()

def send_to_teacher(score, state, fatigue, gaze, blinks):
    payload = {
        "student_id": STUDENT_ID,
        "score":   round(float(score), 1),
        "state":   state,
        "fatigue": round(float(fatigue), 1),
        "gaze":    gaze,
        "blinks":  int(blinks)
    }
    try:
        _data_queue.put_nowait(payload)
    except queue.Full:
        log.debug("Teacher send queue full — dropping oldest item")
        try:
            _data_queue.get_nowait()
            _data_queue.put_nowait(payload)
        except queue.Empty:
            pass


# ── Classroom backend integration ──────────────────────────────────────────────
CLASSROOM_URL       = os.getenv("CLASSROOM_BACKEND_URL", "").rstrip("/")
CLASSROOM_EMAIL     = os.getenv("CLASSROOM_EMAIL", "")
CLASSROOM_PASSWORD  = os.getenv("CLASSROOM_PASSWORD", "")
CLASSROOM_CLASS_CODE = os.getenv("CLASSROOM_CLASS_CODE", "")

_classroom_jwt: str = ""
_classroom_queue: queue.Queue = queue.Queue(maxsize=10)

def _get_classroom_jwt() -> str:
    """Login to classroom backend and return JWT. Returns '' on failure."""
    if not (CLASSROOM_URL and CLASSROOM_EMAIL and CLASSROOM_PASSWORD):
        return ""
    try:
        r = _http_session.post(
            f"{CLASSROOM_URL}/auth/login",
            json={"email": CLASSROOM_EMAIL, "password": CLASSROOM_PASSWORD},
            timeout=5.0
        )
        if r.status_code == 200:
            token = r.json().get("access_token", "")
            log.info("Classroom backend: logged in successfully")
            return token
        else:
            log.warning(f"Classroom login failed: {r.status_code} {r.text[:100]}")
    except Exception as e:
        log.warning(f"Classroom login error: {e}")
    return ""

def _classroom_sender_worker():
    global _classroom_jwt
    while True:
        payload = _classroom_queue.get()
        if payload is None:
            break
        if not _classroom_jwt:
            continue
        try:
            r = _http_session.post(
                f"{CLASSROOM_URL}/send-data",
                json=payload,
                headers={"Authorization": f"Bearer {_classroom_jwt}"},
                timeout=2.0
            )
            if r.status_code == 401:
                # JWT expired — re-login once
                log.info("Classroom JWT expired, re-logging in...")
                _classroom_jwt = _get_classroom_jwt()
        except Exception as e:
            log.debug(f"Classroom send failed: {e}")

def send_to_classroom(score, state, fatigue, gaze, blinks):
    if not _classroom_active:
        return
    payload = {
        "class_code": CLASSROOM_CLASS_CODE,
        "score":   round(float(score), 1),
        "state":   state,
        "fatigue": round(float(fatigue), 1),
        "gaze":    gaze if gaze in ("LEFT", "CENTER", "RIGHT", "DOWN") else "CENTER",
        "blinks":  int(blinks),
    }
    try:
        _classroom_queue.put_nowait(payload)
    except queue.Full:
        try:
            _classroom_queue.get_nowait()
            _classroom_queue.put_nowait(payload)
        except queue.Empty:
            pass


# mode select
print("\nSelect Mode:")
print("  1. READING")
print("  2. PROBLEM_SOLVING")
print("  3. LECTURE")
choice = input("Enter choice (1/2/3) [default=1]: ").strip()
mode_map = {"1": "READING", "2": "PROBLEM_SOLVING", "3": "LECTURE"}
selected_mode = mode_map.get(choice, "READING")

# ── Classroom integration setup ────────────────────────────────────────────────
_classroom_active = False

if CLASSROOM_URL:
    print(f"\n── AttentionAI Classroom ──")
    print(f"Backend: {CLASSROOM_URL}")

    # Use env vars if set, otherwise prompt
    _email = CLASSROOM_EMAIL or input("Student email (leave blank to skip): ").strip()
    if _email:
        import getpass as _gp
        _password = CLASSROOM_PASSWORD or _gp.getpass("Student password: ")
        _code     = CLASSROOM_CLASS_CODE or input("Class code (6 chars): ").strip().upper()

        if _email and _password and _code:
            CLASSROOM_EMAIL      = _email
            CLASSROOM_PASSWORD   = _password
            CLASSROOM_CLASS_CODE = _code

            _classroom_jwt = _get_classroom_jwt()
            if _classroom_jwt:
                _classroom_thread = threading.Thread(target=_classroom_sender_worker, daemon=True)
                _classroom_thread.start()
                _classroom_active = True
                print(f"✅ Classroom connected — class {CLASSROOM_CLASS_CODE}")
            else:
                print("⚠  Classroom login failed — running without classroom integration")
        else:
            print("⚠  Skipping classroom integration (incomplete credentials)")
    else:
        print("⚠  Skipping classroom integration")
else:
    log.info("CLASSROOM_BACKEND_URL not set — classroom integration disabled")

# init
cap              = cv2.VideoCapture(0)
detector         = FaceMeshDetector()
blink_detector   = BlinkDetector()
gaze_detector    = GazeDetector()
scorer           = AttentionScorer()
classifier       = StateClassifier()
fatigue_detector = FatigueDetector()
buffer           = TimeBuffer()
personalization  = Personalization()
context          = ContextManager()
context.set_mode(selected_mode)
logger           = SessionLogger()
session_db       = SessionDB()
session_db.start_session(mode=selected_mode)
log.info(f"Session started — mode={selected_mode} student={STUDENT_ID}")
gamification     = Gamification()
intervention     = InterventionSystem()
calibration      = CalibrationManager()
log.info(f"Calibration loaded: {calibration.summary()}")
movement_detector = MovementDetector()

score_smoother = TemporalSmoother(window_seconds=1.0)
last_log_time  = 0

LEFT_EYE  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
LEFT_IRIS  = 468
RIGHT_IRIS = 473

STATE_COLORS = {
    "FOCUSED":    (0, 255, 0),
    "LOW FOCUS":  (0, 255, 255),
    "DISTRACTED": (0, 0, 255),
    "FATIGUED":   (0, 165, 255),
}

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame, landmarks = detector.process(frame)

    if landmarks:
        left_eye  = [landmarks[i] for i in LEFT_EYE]
        right_eye = [landmarks[i] for i in RIGHT_EYE]

        ear, eye_closed, blink_count = blink_detector.detect(left_eye, right_eye)

        left_iris  = landmarks[LEFT_IRIS]
        right_iris = landmarks[RIGHT_IRIS]
        gaze_left  = gaze_detector.get_gaze_direction(left_eye, left_iris,
                                                       landmarks, frame.shape)
        gaze_right = gaze_detector.get_gaze_direction(right_eye, right_iris,
                                                       landmarks, frame.shape)
        # DOWN takes priority if either eye detects it (pitch-based)
        if gaze_left == "DOWN" or gaze_right == "DOWN":
            raw_gaze = "DOWN"
        else:
            raw_gaze = gaze_left if gaze_left == gaze_right else "CENTER"
        gaze, off_time = gaze_detector.update_off_screen(raw_gaze, face_detected=True)

        buffer.update_blinks(blink_count)
        blink_rate = buffer.get_blink_rate()

        fatigue_score, closure_dur, instability, session_min = \
            fatigue_detector.get_fatigue_score(eye_closed, blink_rate, gaze)

        personalization.update(blink_rate, gaze, fatigue_score, off_time)
        blink_threshold = personalization.get_baseline_blink() + 5 + calibration.blink_offset

        gaze_w, blink_w = context.get_weights()

        nose_pos = landmarks[1]
        movement_penalty = movement_detector.update(nose_pos)

        raw_score = scorer.calculate(gaze, off_time, eye_closed, blink_rate,
                                     blink_threshold,
                                     gaze_w * calibration.gaze_scale,
                                     blink_w,
                                     movement_penalty)

        score      = score_smoother.update(raw_score)
        confidence = score_smoother.get_confidence()

        fatigue_thresh = personalization.get_fatigue_threshold()
        off_thresh     = personalization.get_off_threshold()
        state       = classifier.classify(score, off_time,
                                          fatigue_score,
                                          fatigue_thresh,
                                          off_thresh)
        state_color  = STATE_COLORS.get(state, (255, 255, 255))
        learning_tag = " [LEARNING]" if personalization.learning else ""

        cv2.putText(frame, f"EAR: {ear:.2f}",                                          (30, 30),  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Blinks: {blink_count}  Rate: {blink_rate:.1f}/min",       (30, 58),  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Eye: {'Closed' if eye_closed else 'Open'}  Dur: {closure_dur:.1f}s", (30, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        # gaze display — DOWN shown in orange to distinguish from LEFT/RIGHT
        gaze_color = (0, 165, 255) if gaze == "DOWN" else (255, 255, 0)
        cv2.putText(frame, f"Gaze: {gaze}  Off: {off_time:.1f}s",                      (30, 114), cv2.FONT_HERSHEY_SIMPLEX, 0.6, gaze_color, 2)
        cv2.putText(frame, f"Instability: {instability}  Session: {session_min:.1f}m", (30, 142), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.putText(frame, f"Mode: {context.mode}{learning_tag}",                      (30, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
        cv2.putText(frame, f"Baseline Blink: {int(blink_threshold)}",                  (30, 198), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
        cv2.putText(frame, f"Fatigue: {int(fatigue_score)}",                           (30, 228), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
        cv2.putText(frame, f"Score: {int(score)}  Conf: {confidence:.2f}",             (30, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(frame, f"State: {state}",                                          (30, 292), cv2.FONT_HERSHEY_SIMPLEX, 0.9, state_color, 2)

        alerts = intervention.check(score, state, fatigue_score, off_time, session_min)
        if alerts:
            for i, alert in enumerate(alerts):
                cv2.putText(frame, f">> {alert}", (10, 340 + i * 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if time.time() - last_log_time > 1:
            logger.log(score, state, blink_rate, gaze, off_time, fatigue_score)
            session_db.log(score, state, blink_rate, gaze, off_time, fatigue_score)
            send_to_teacher(score, state, fatigue_score, gaze, blink_count)
            send_to_classroom(score, state, fatigue_score, gaze, blink_count)
            last_log_time = time.time()

        if fatigue_score >= 60:
            h, w = frame.shape[:2]
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, 45), (0, 0, 180), -1)
            cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
            cv2.putText(frame, "WARNING: FATIGUE DETECTED — Take a break!", (10, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

    else:
        gaze, off_time = gaze_detector.update_off_screen("CENTER", face_detected=False)
        movement_detector.reset()
        log.debug("Face not detected — gaze timer preserved")
        cv2.putText(frame, "Face not detected",            (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, f"Off-screen: {off_time:.1f}s", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    cv2.imshow("Attention Monitor", frame)

    # encode frame as JPEG and push to shared buffer for web stream
    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    write_frame(jpeg.tobytes())

    if cv2.waitKey(1) & 0xFF == 27:
        break

if 'score' in locals() and 'session_min' in locals():
    gamification.update(score, focus_minutes=int(session_min))
    log.info(f"Session ended — final_score={score} session_min={session_min:.1f}")

session_db.close()
log.info("Session DB closed")
cap.release()
cv2.destroyAllWindows()
