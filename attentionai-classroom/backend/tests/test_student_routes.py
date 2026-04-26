"""
Integration tests for student join route.
Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
"""
import os
import sys
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app
from db.database import get_db

# ── Test database setup ────────────────────────────────────────────────────────

SQLALCHEMY_TEST_URL = "sqlite:///./test_students.db"
test_engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    """TestClient backed by an isolated SQLite test database."""
    with test_engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        for stmt in [
            """CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL CHECK (role IN ('teacher','student')),
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS classes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES users(id),
                name       TEXT NOT NULL,
                subject    TEXT NOT NULL,
                class_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
            """CREATE TABLE IF NOT EXISTS enrollments (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES users(id),
                class_id   INTEGER NOT NULL REFERENCES classes(id),
                joined_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (student_id, class_id)
            )""",
            """CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id   INTEGER NOT NULL REFERENCES classes(id),
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at   TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS attention_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  INTEGER NOT NULL REFERENCES users(id),
                session_id  INTEGER NOT NULL REFERENCES sessions(id),
                score       REAL NOT NULL CHECK (score >= 0 AND score <= 100),
                state       TEXT NOT NULL,
                fatigue     REAL NOT NULL CHECK (fatigue >= 0 AND fatigue <= 100),
                gaze        TEXT NOT NULL,
                blinks      INTEGER NOT NULL CHECK (blinks >= 0),
                recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
        ]:
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
    if os.path.exists("./test_students.db"):
        os.remove("./test_students.db")


# ── Shared state ───────────────────────────────────────────────────────────────

_state: dict = {}

TEACHER_PAYLOAD = {
    "name": "Eve Teacher",
    "email": "eve@example.com",
    "password": "secret123",
    "role": "teacher",
    "subject": "Biology",
}

STUDENT_PAYLOAD = {
    "name": "Frank Student",
    "email": "frank@example.com",
    "password": "pass456",
    "role": "student",
}

STUDENT2_PAYLOAD = {
    "name": "Grace Student",
    "email": "grace@example.com",
    "password": "pass789",
    "role": "student",
}


@pytest.fixture(scope="module", autouse=True)
def setup_state(client):
    """Register teacher, create a class, register a student — store shared state."""
    # Register + login teacher
    client.post("/auth/register", json=TEACHER_PAYLOAD)
    resp = client.post("/auth/login", json={
        "email": TEACHER_PAYLOAD["email"],
        "password": TEACHER_PAYLOAD["password"],
    })
    _state["teacher_token"] = resp.json()["access_token"]

    # Create a class
    resp = client.post(
        "/classes",
        json={"name": "Bio 101", "subject": "Biology"},
        headers={"Authorization": f"Bearer {_state['teacher_token']}"},
    )
    assert resp.status_code == 201
    _state["class_code"] = resp.json()["class_code"]

    # Register + login student
    client.post("/auth/register", json=STUDENT_PAYLOAD)
    resp = client.post("/auth/login", json={
        "email": STUDENT_PAYLOAD["email"],
        "password": STUDENT_PAYLOAD["password"],
    })
    _state["student_token"] = resp.json()["access_token"]

    # Register + login second student (for teacher-role test)
    client.post("/auth/register", json=STUDENT2_PAYLOAD)
    resp = client.post("/auth/login", json={
        "email": STUDENT2_PAYLOAD["email"],
        "password": STUDENT2_PAYLOAD["password"],
    })
    _state["student2_token"] = resp.json()["access_token"]


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_successful_join_returns_201_with_enrollment(client):
    """Req 5.1 — student joins a valid class, gets 201 with EnrollmentResponse."""
    resp = client.post(
        "/classes/join",
        json={"class_code": _state["class_code"]},
        headers={"Authorization": f"Bearer {_state['student_token']}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["class_code"] == _state["class_code"]
    assert "class_id" in body
    assert "class_name" in body
    assert "subject" in body
    assert "teacher" in body


def test_duplicate_join_returns_409(client):
    """Req 5.4 — same student joining the same class again returns 409 (already enrolled)."""
    resp = client.post(
        "/classes/join",
        json={"class_code": _state["class_code"]},
        headers={"Authorization": f"Bearer {_state['student_token']}"},
    )
    assert resp.status_code == 409


def test_bad_class_code_returns_404(client):
    """Req 5.2 — class_code that doesn't exist returns 404."""
    resp = client.post(
        "/classes/join",
        json={"class_code": "XXXXXX"},
        headers={"Authorization": f"Bearer {_state['student2_token']}"},
    )
    assert resp.status_code == 404


def test_class_code_wrong_length_returns_422(client):
    """Req 5.3 — class_code shorter than 6 chars fails Pydantic validation → 422."""
    resp = client.post(
        "/classes/join",
        json={"class_code": "ABC"},
        headers={"Authorization": f"Bearer {_state['student2_token']}"},
    )
    assert resp.status_code == 422


def test_class_code_too_long_returns_422(client):
    """Req 5.3 — class_code longer than 6 chars fails Pydantic validation → 422."""
    resp = client.post(
        "/classes/join",
        json={"class_code": "ABCDEFG"},
        headers={"Authorization": f"Bearer {_state['student2_token']}"},
    )
    assert resp.status_code == 422


def test_unauthenticated_join_returns_401(client):
    """Req 5.1 — join without a token returns 401."""
    resp = client.post(
        "/classes/join",
        json={"class_code": _state["class_code"]},
    )
    assert resp.status_code == 401


def test_teacher_cannot_join_class_returns_403(client):
    """Req 5.1 — teacher role is rejected by require_student → 403."""
    resp = client.post(
        "/classes/join",
        json={"class_code": _state["class_code"]},
        headers={"Authorization": f"Bearer {_state['teacher_token']}"},
    )
    assert resp.status_code == 403


# ── Registration validation (name constraints live on /auth/register) ──────────

def test_register_empty_name_returns_422(client):
    """Req 5.3 — student name is set at registration; empty name → 422."""
    resp = client.post("/auth/register", json={
        "name": "",
        "email": "noname@example.com",
        "password": "pass123",
        "role": "student",
    })
    assert resp.status_code == 422


def test_register_name_too_long_returns_422(client):
    """Req 5.3 — student name exceeding 100 chars at registration → 422."""
    resp = client.post("/auth/register", json={
        "name": "A" * 101,
        "email": "longname@example.com",
        "password": "pass123",
        "role": "student",
    })
    assert resp.status_code == 422
