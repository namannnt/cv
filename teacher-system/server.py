import time
import sqlite3
import os
from datetime import datetime
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import logging

# ── FIX 1: Load .env ──
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("teacher_server.log")
    ]
)
logger = logging.getLogger(__name__)

# ── FIX 1: Load secrets from env ──
API_TOKEN   = os.getenv("API_TOKEN", "attentionai-demo-2026")
SERVER_PORT = int(os.getenv("TEACHER_SERVER_PORT", 5001))

# ── FIX 8: Rate limiter ──
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="AttentionAI Teacher Server", version="2.0")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return HTTPException(status_code=429, detail="Rate limit exceeded")


def verify_token(x_api_token: str = Header(...)):
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── In-memory store ──
class_data: Dict[str, dict] = {}
active_websockets: list[WebSocket] = []


# ── FIX 7 (teacher persistence): SessionDB ──
class SessionDB:
    def __init__(self, db_path: str = "class_data.db"):
        self._path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS class_data (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    score      REAL,
                    state      TEXT,
                    fatigue    REAL,
                    gaze       TEXT,
                    blinks     INTEGER,
                    timestamp  TEXT
                )
            """)

    def insert(self, student_id, score, state, fatigue, gaze, blinks, timestamp):
        try:
            with sqlite3.connect(self._path) as conn:
                conn.execute(
                    "INSERT INTO class_data VALUES (NULL,?,?,?,?,?,?,?)",
                    (student_id, score, state, fatigue, gaze, blinks, timestamp)
                )
        except Exception as e:
            logger.error(f"SessionDB insert failed: {e}")


session_db = SessionDB()


# ── Pydantic models ──
class StudentData(BaseModel):
    student_id: str   = Field(..., min_length=1, max_length=50)
    score:      float = Field(..., ge=0, le=100)
    state:      str   = Field(..., pattern="^(FOCUSED|LOW FOCUS|DISTRACTED|FATIGUED|UNKNOWN)$")
    fatigue:    float = Field(..., ge=0, le=100)
    gaze:       str   = Field(..., pattern="^(LEFT|CENTER|RIGHT)$")
    blinks:     int   = Field(..., ge=0)

    @validator("student_id")
    def sanitize_id(cls, v):
        import html
        return html.escape(v.strip())


# ── Routes ──
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Read template, inject token manually to avoid Jinja2 cache key bug
    import os
    template_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{ api_token }}", str(API_TOKEN))
    return HTMLResponse(content=html)


# ── FIX 8: Rate-limited send-data ──
@app.post("/send-data", dependencies=[Depends(verify_token)])
@limiter.limit("10/second")
async def send_data(request: Request, data: StudentData):
    ts = datetime.now().strftime("%H:%M:%S")
    class_data[data.student_id] = {
        "score":     data.score,
        "state":     data.state,
        "fatigue":   data.fatigue,
        "gaze":      data.gaze,
        "blinks":    data.blinks,
        "timestamp": ts,
        "last_seen": time.time()
    }
    logger.info(f"Data received from {data.student_id}: score={data.score} state={data.state}")

    # persist to SQLite
    session_db.insert(data.student_id, data.score, data.state,
                      data.fatigue, data.gaze, data.blinks, ts)

    await _broadcast_class_data()
    return {"message": "ok"}


@app.get("/get-class-data")
async def get_class_data():
    return _build_class_response()


# ── FIX 4: WebSocket with token auth ──
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != API_TOKEN:
        await websocket.accept()
        await websocket.send_json({"error": "unauthorized"})
        await websocket.close(code=4001)
        logger.warning(f"WebSocket rejected — invalid token from {websocket.client}")
        return

    await websocket.accept()
    active_websockets.append(websocket)
    logger.info(f"WebSocket client connected. Total: {len(active_websockets)}")
    try:
        await websocket.send_json(_build_class_response())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(active_websockets)}")


async def _broadcast_class_data():
    if not active_websockets:
        return
    payload = _build_class_response()
    dead = []
    for ws in active_websockets:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in active_websockets:
            active_websockets.remove(ws)


def _build_class_response() -> dict:
    now = time.time()
    students = {}
    for sid, s in class_data.items():
        entry = dict(s)
        entry["status"] = "OFFLINE" if (now - s.get("last_seen", 0)) > 5 else "ONLINE"
        students[sid] = entry

    active     = [s for s in students.values() if s["status"] == "ONLINE"]
    avg        = round(sum(s["score"] for s in active) / len(active), 1) if active else 0
    distracted = sum(1 for s in active if s["state"] == "DISTRACTED")
    fatigued   = sum(1 for s in active if s["fatigue"] >= 60)

    return {
        "students":         students,
        "avg_score":        avg,
        "distracted_count": distracted,
        "fatigued_count":   fatigued,
        "total":            len(active)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=SERVER_PORT, reload=True)
