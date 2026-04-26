"""
Integration tests for report routes.
Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.2, 9.3
"""
import os
import sys
import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app
from db.database import get_db

SQLALCHEMY_TEST_URL = "sqlite:///./test_reports.db"
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
    if os.path.exists("./test_reports.db"):
        os.remove("./test_reports.db")


_s: dict = {}

TEACHER = {"name": "Rep Teacher", "email": "repteacher@ex.com", "password": "pw1234",
           "role": "teacher", "subject": "History"}
STUDENT = {"name": "Rep Student", "email": "repstudent@ex.com", "password": "pw1234", "role": "student"}


@pytest.fixture(scope="module", autouse=True)
def setup(client):
    # Register + login teacher
    client.post("/auth/register", json=TEACHER)
    r = client.post("/auth/login", json={"email": TEACHER["email"], "password": TEACHER["password"]})
    _s["teacher_token"] = r.json()["access_token"]
    _s["teacher_id"] = r.json()["user_id"]

    # Create class
    r = client.post("/classes", json={"name": "History 101", "subject": "History"},
                    headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert r.status_code == 201
    _s["class_id"] = r.json()["id"]
    _s["class_code"] = r.json()["class_code"]

    # Register + login student
    client.post("/auth/register", json=STUDENT)
    r = client.post("/auth/login", json={"email": STUDENT["email"], "password": STUDENT["password"]})
    _s["student_token"] = r.json()["access_token"]
    _s["student_id"] = r.json()["user_id"]

    # Enroll student
    client.post("/classes/join", json={"class_code": _s["class_code"]},
                headers={"Authorization": f"Bearer {_s['student_token']}"})

    # Start session, send data, end session
    r = client.post(f"/classes/{_s['class_id']}/sessions/start",
                    headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert r.status_code == 201

    for score in [60.0, 70.0, 80.0]:
        client.post("/send-data", json={
            "class_code": _s["class_code"], "score": score,
            "state": "FOCUSED", "fatigue": 20.0, "gaze": "CENTER", "blinks": 5,
        }, headers={"Authorization": f"Bearer {_s['student_token']}"})

    client.post(f"/classes/{_s['class_id']}/sessions/end",
                headers={"Authorization": f"Bearer {_s['teacher_token']}"})


# ── Session history tests ──────────────────────────────────────────────────────

def test_session_history_returns_list(client):
    """Req 8.1 — session history returns a list of past sessions."""
    resp = client.get(f"/reports/sessions/{_s['class_id']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1


def test_session_history_has_required_fields(client):
    """Req 8.1 — each session entry has date, duration_seconds, avg_score, distraction_events."""
    resp = client.get(f"/reports/sessions/{_s['class_id']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    entry = resp.json()[0]
    assert "session_id" in entry
    assert "date" in entry
    assert "duration_seconds" in entry
    assert "avg_score" in entry
    assert "distraction_events" in entry
    assert entry["avg_score"] > 0


def test_session_history_unauthenticated_returns_401(client):
    """Req 8.6 — unauthenticated request returns 401."""
    resp = client.get(f"/reports/sessions/{_s['class_id']}")
    assert resp.status_code == 401


def test_session_history_wrong_teacher_returns_404(client):
    """Req 8.1 — teacher cannot access another teacher's class history."""
    # Register a second teacher
    client.post("/auth/register", json={
        "name": "Other", "email": "other@ex.com", "password": "pw1234",
        "role": "teacher", "subject": "Math"
    })
    r = client.post("/auth/login", json={"email": "other@ex.com", "password": "pw1234"})
    other_token = r.json()["access_token"]
    resp = client.get(f"/reports/sessions/{_s['class_id']}",
                      headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 404


# ── Student summaries tests ────────────────────────────────────────────────────

def test_student_summaries_returns_list(client):
    """Req 8.2 — student summaries returns per-student data."""
    resp = client.get(f"/reports/students/{_s['class_id']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1


def test_student_summaries_has_trend(client):
    """Req 8.2, 8.3–8.5 — each student entry includes a trend field."""
    resp = client.get(f"/reports/students/{_s['class_id']}",
                      headers={"Authorization": f"Bearer {_s['teacher_token']}"})
    entry = resp.json()[0]
    assert "trend" in entry
    assert entry["trend"] in ("IMPROVING", "DECLINING", "STABLE")
    assert "attendance_count" in entry
    assert "avg_score" in entry


def test_student_summaries_unauthenticated_returns_401(client):
    """Req 8.6 — unauthenticated request returns 401."""
    resp = client.get(f"/reports/students/{_s['class_id']}")
    assert resp.status_code == 401


# ── Student history tests ──────────────────────────────────────────────────────

def test_student_history_returns_list(client):
    """Req 9.1 — student history returns list of attended sessions."""
    resp = client.get("/my-history",
                      headers={"Authorization": f"Bearer {_s['student_token']}"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1


def test_student_history_has_required_fields(client):
    """Req 9.1 — each entry has session_id, date, duration_seconds, avg_score."""
    resp = client.get("/my-history",
                      headers={"Authorization": f"Bearer {_s['student_token']}"})
    entry = resp.json()[0]
    assert "session_id" in entry
    assert "date" in entry
    assert "duration_seconds" in entry
    assert "avg_score" in entry
    assert entry["avg_score"] > 0


def test_student_history_unauthenticated_returns_401(client):
    """Req 9.2 — invalid/missing token returns 401."""
    resp = client.get("/my-history")
    assert resp.status_code == 401


def test_student_history_invalid_token_returns_401(client):
    """Req 9.2 — garbage token returns 401."""
    resp = client.get("/my-history",
                      headers={"Authorization": "Bearer garbage.token.here"})
    assert resp.status_code == 401
