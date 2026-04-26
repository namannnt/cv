"""
Integration tests for data routes: /send-data and /class-data/{class_code}
Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.7
"""
import os
import sys
import time
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app
from db.database import get_db
import routers.data as data_router

# ── Test database ──────────────────────────────────────────────────────────────

SQLALCHEMY_TEST_URL = "sqlite:///./test_data.db"
test_engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

_SCHEMA_STMTS = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('teacher','student')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
    """CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id INTEGER NOT NULL REFERENCES users(id),
        name TEXT NOT NULL, subject TEXT NOT NULL, class_code TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
    """CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES users(id),
        class_id INTEGER NOT NULL REFERENCES classes(id),
        joined_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (student_id, class_id))""",
    """CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id),
        started_at TEXT NOT NULL DEFAULT (datetime('now')), ended_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS attention_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES users(id),
        session_id INTEGER NOT NULL REFERENCES sessions(id),
        score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
        state TEXT NOT NULL, fatigue REAL NOT NULL CHECK (fatigue >= 0 AND fatigue <= 100),
        gaze TEXT NOT NULL, blinks INTEGER NOT NULL CHECK (blinks >= 0),
        recorded_at TEXT NOT NULL DEFAULT (datetime('now')))""",
]


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    with test_engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        for stmt in _SCHEMA_STMTS:
            conn.execute(text(stmt))
        conn.commit()

    import db.database as db_module
    original_engine = db_module.engine
    db_module.engine = test_engine
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    db_module.engine = original_engine
    test_engine.dispose()
    if os.path.exists("./test_data.db"):
        os.remove("./test_data.db")


# ── Shared state ───────────────────────────────────────────────────────────────

_s: dict = {}

TEACHER = {"name": "T Data", "email": "tdata@ex.com", "password": "pw1234", "role": "teacher", "subject": "CS"}
STUDENT = {"name": "S Data", "email": "sdata@ex.com", "password": "pw1234", "role": "student"}
STUDENT2 = {"name": "S Data2", "email": "sdata2@ex.com", "password": "pw1234", "role": "student"}

VALID_PAYLOAD = {
    "class_code": None,  # filled in setup
    "score": 75.0, "state": "FOCUSED", "fatigue": 20.0, "gaze": "CENTER", "blinks": 5,
}


@pytest.fixture(scope="module", autouse=True)
def setup(client):
    # Register + login teacher
    client.post("/auth/register", json=TEACHER)
    r = client.post("/auth/login", json={"email": TEACHER["email"], "password": TEACHER["password"]})
    _s["teacher_token"] = r.json()["access_token"]

    # Create class
    r = client.post("/classes", json={"name": "Data Class", "subject": "CS"},
                    headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert r.status_code == 201
    _s["class_code"] = r.json()["class_code"]
    _s["class_id"] = r.json()["id"]
    VALID_PAYLOAD["class_code"] = _s["class_code"]

    # Register + login student
    client.post("/auth/register", json=STUDENT)
    r = client.post("/auth/login", json={"email": STUDENT["email"], "password": STUDENT["password"]})
    _s["student_token"] = r.json()["access_token"]
    _s["student_id"] = r.json()["user_id"]

    # Register + login student2
    client.post("/auth/register", json=STUDENT2)
    r = client.post("/auth/login", json={"email": STUDENT2["email"], "password": STUDENT2["password"]})
    _s["student2_token"] = r.json()["access_token"]

    # Enroll student
    client.post("/classes/join", json={"class_code": _s["class_code"]},
                headers={"Authorization": f"Bearer {_s['student_token']}"})

    # Start session
    r = client.post(f"/classes/{_s['class_id']}/sessions/start",
                    headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert r.status_code == 201
    _s["session_id"] = r.json()["id"]


# ── send-data tests ────────────────────────────────────────────────────────────

def test_send_data_accepted(client):
    """Req 6.1 — valid payload with active session returns 200."""
    resp = client.post("/send-data", json=VALID_PAYLOAD,
                       headers={"Authorization": f"Bearer {_s['student_token']}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_send_data_missing_token_returns_401(client):
    """Req 6.2 — missing Authorization header returns 401."""
    resp = client.post("/send-data", json=VALID_PAYLOAD)
    assert resp.status_code == 401


def test_send_data_invalid_token_returns_401(client):
    """Req 6.2 — invalid token returns 401."""
    resp = client.post("/send-data", json=VALID_PAYLOAD,
                       headers={"Authorization": "Bearer not.a.real.token"})
    assert resp.status_code == 401


def test_send_data_out_of_range_score_returns_422(client):
    """Req 6.3 — score > 100 returns 422."""
    payload = {**VALID_PAYLOAD, "score": 150.0}
    resp = client.post("/send-data", json=payload,
                       headers={"Authorization": f"Bearer {_s['student_token']}"})
    assert resp.status_code == 422


def test_send_data_negative_score_returns_422(client):
    """Req 6.3 — score < 0 returns 422."""
    payload = {**VALID_PAYLOAD, "score": -1.0}
    resp = client.post("/send-data", json=payload,
                       headers={"Authorization": f"Bearer {_s['student_token']}"})
    assert resp.status_code == 422


def test_send_data_bad_state_returns_422(client):
    """Req 6.4 — invalid state returns 422."""
    payload = {**VALID_PAYLOAD, "state": "SLEEPING"}
    resp = client.post("/send-data", json=payload,
                       headers={"Authorization": f"Bearer {_s['student_token']}"})
    assert resp.status_code == 422


def test_send_data_bad_gaze_returns_422(client):
    """Req 6.5 — invalid gaze returns 422."""
    payload = {**VALID_PAYLOAD, "gaze": "UP"}
    resp = client.post("/send-data", json=payload,
                       headers={"Authorization": f"Bearer {_s['student_token']}"})
    assert resp.status_code == 422


def test_send_data_not_enrolled_returns_403(client):
    """Req 6.2 — student not enrolled in class returns 403."""
    payload = {**VALID_PAYLOAD}
    resp = client.post("/send-data", json=payload,
                       headers={"Authorization": f"Bearer {_s['student2_token']}"})
    assert resp.status_code == 403


def test_send_data_no_active_session_returns_403(client):
    """Req 4.6 — data rejected when no active session (end session first)."""
    # End the session
    client.post(f"/classes/{_s['class_id']}/sessions/end",
                headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    resp = client.post("/send-data", json=VALID_PAYLOAD,
                       headers={"Authorization": f"Bearer {_s['student_token']}"})
    assert resp.status_code == 403
    # Restart for subsequent tests
    r = client.post(f"/classes/{_s['class_id']}/sessions/start",
                    headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert r.status_code == 201


# ── class-data tests ───────────────────────────────────────────────────────────

def test_class_data_returns_students(client):
    """Req 7.1 — class-data returns student entries."""
    # Send data first so student appears in cache
    client.post("/send-data", json={**VALID_PAYLOAD, "score": 80.0},
                headers={"Authorization": f"Bearer {_s['student_token']}"})
    resp = client.get(f"/class-data/{_s['class_code']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "students" in body
    assert "avg_score" in body
    assert "total_online" in body


def test_class_data_online_status(client):
    """Req 7.3, 7.4 — student who just sent data is ONLINE."""
    client.post("/send-data", json=VALID_PAYLOAD,
                headers={"Authorization": f"Bearer {_s['student_token']}"})
    resp = client.get(f"/class-data/{_s['class_code']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    body = resp.json()
    online = [s for s in body["students"] if s["status"] == "ONLINE"]
    assert len(online) >= 1


def test_class_data_avg_score_online_only(client):
    """Req 7.5 — avg_score reflects only ONLINE students."""
    resp = client.get(f"/class-data/{_s['class_code']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    body = resp.json()
    online_students = [s for s in body["students"] if s["status"] == "ONLINE"]
    if online_students:
        expected_avg = sum(s["score"] for s in online_students) / len(online_students)
        assert abs(body["avg_score"] - expected_avg) < 0.5


def test_class_data_unauthenticated_returns_401(client):
    """Req 7.7 — unauthenticated request returns 401."""
    resp = client.get(f"/class-data/{_s['class_code']}")
    assert resp.status_code == 401


def test_class_data_no_active_session_returns_404(client):
    """Req 7.1 — class-data with no active session returns 404."""
    client.post(f"/classes/{_s['class_id']}/sessions/end",
                headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    resp = client.get(f"/class-data/{_s['class_code']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert resp.status_code == 404
