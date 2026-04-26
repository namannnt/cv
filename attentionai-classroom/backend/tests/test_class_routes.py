"""
Integration tests for class and session routes.
Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4
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

SQLALCHEMY_TEST_URL = "sqlite:///./test_classes.db"
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

    # Point init_db at the test engine (same pattern as test_auth_routes.py)
    import db.database as db_module
    original_engine = db_module.engine
    db_module.engine = test_engine

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    db_module.engine = original_engine
    test_engine.dispose()
    if os.path.exists("./test_classes.db"):
        os.remove("./test_classes.db")


# ── Helpers ────────────────────────────────────────────────────────────────────

TEACHER_PAYLOAD = {
    "name": "Carol Teacher",
    "email": "carol@example.com",
    "password": "secret123",
    "role": "teacher",
    "subject": "Mathematics",
}

STUDENT_PAYLOAD = {
    "name": "Dave Student",
    "email": "dave@example.com",
    "password": "pass456",
    "role": "student",
}


def get_teacher_token(client) -> str:
    client.post("/auth/register", json=TEACHER_PAYLOAD)
    resp = client.post("/auth/login", json={
        "email": TEACHER_PAYLOAD["email"],
        "password": TEACHER_PAYLOAD["password"],
    })
    return resp.json()["access_token"]


def get_student_token(client) -> str:
    client.post("/auth/register", json=STUDENT_PAYLOAD)
    resp = client.post("/auth/login", json={
        "email": STUDENT_PAYLOAD["email"],
        "password": STUDENT_PAYLOAD["password"],
    })
    return resp.json()["access_token"]


# ── Fixtures for tokens (module-scoped via a shared state dict) ────────────────

_tokens: dict = {}


@pytest.fixture(scope="module", autouse=True)
def setup_tokens(client):
    """Register teacher and student, store tokens for use in tests."""
    _tokens["teacher"] = get_teacher_token(client)
    _tokens["student"] = get_student_token(client)


# ── Class creation tests ───────────────────────────────────────────────────────

def test_create_class_success(client):
    """Req 3.1 — authenticated teacher can create a class, returns 201 with class_code."""
    resp = client.post(
        "/classes",
        json={"name": "Physics 101", "subject": "Physics"},
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "class_code" in body
    assert len(body["class_code"]) == 6
    assert body["class_code"].isalnum()
    assert body["name"] == "Physics 101"
    assert body["has_active_session"] is False


def test_create_class_empty_name_returns_422(client):
    """Req 3.4 — empty batch name returns 422."""
    resp = client.post(
        "/classes",
        json={"name": "", "subject": "Physics"},
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 422


def test_create_class_name_too_long_returns_422(client):
    """Req 3.4 — name exceeding 100 characters returns 422."""
    resp = client.post(
        "/classes",
        json={"name": "A" * 101, "subject": "Physics"},
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 422


def test_create_class_unauthenticated_returns_401(client):
    """Req 3.5 — unauthenticated request to create class returns 401."""
    resp = client.post("/classes", json={"name": "Unauthorized Class", "subject": "Math"})
    assert resp.status_code == 401


# ── List classes tests ─────────────────────────────────────────────────────────

def test_list_classes_returns_teacher_classes(client):
    """Req 3.3 — GET /classes/mine returns teacher's classes with has_active_session=False."""
    resp = client.get(
        "/classes/mine",
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    # The class created in test_create_class_success should be here
    names = [c["name"] for c in body]
    assert "Physics 101" in names
    # No active session yet
    for cls in body:
        assert cls["has_active_session"] is False


def test_list_classes_unauthenticated_returns_401(client):
    """Req 3.5 — unauthenticated request to /classes/mine returns 401."""
    resp = client.get("/classes/mine")
    assert resp.status_code == 401


# ── Session lifecycle tests ────────────────────────────────────────────────────

def _get_class_id(client) -> int:
    """Helper: get the ID of the first class belonging to the teacher."""
    resp = client.get(
        "/classes/mine",
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    return resp.json()[0]["id"]


def test_start_session_success(client):
    """Req 4.1 — starting a session returns 201 with started_at set and ended_at null."""
    class_id = _get_class_id(client)
    resp = client.post(
        f"/classes/{class_id}/sessions/start",
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["class_id"] == class_id
    assert body["started_at"] is not None
    assert body["ended_at"] is None


def test_double_start_returns_409(client):
    """Req 4.2 — starting a session when one is already active returns 409."""
    class_id = _get_class_id(client)
    resp = client.post(
        f"/classes/{class_id}/sessions/start",
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 409


def test_list_classes_shows_active_session(client):
    """Req 3.3 — after starting a session, has_active_session should be True."""
    resp = client.get(
        "/classes/mine",
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 200
    classes = resp.json()
    class_id = _get_class_id(client)
    target = next(c for c in classes if c["id"] == class_id)
    assert target["has_active_session"] is True


def test_end_session_success(client):
    """Req 4.3 — ending an active session returns 200 with ended_at set."""
    class_id = _get_class_id(client)
    resp = client.post(
        f"/classes/{class_id}/sessions/end",
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["class_id"] == class_id
    assert body["ended_at"] is not None


def test_end_session_no_active_returns_404(client):
    """Req 4.4 — ending a session when none is active returns 404."""
    class_id = _get_class_id(client)
    resp = client.post(
        f"/classes/{class_id}/sessions/end",
        headers={"Authorization": f"Bearer {_tokens['teacher']}"},
    )
    assert resp.status_code == 404


def test_start_session_unauthenticated_returns_401(client):
    """Req 3.5 / 4.1 — unauthenticated session start returns 401."""
    class_id = _get_class_id(client)
    resp = client.post(f"/classes/{class_id}/sessions/start")
    assert resp.status_code == 401


def test_end_session_unauthenticated_returns_401(client):
    """Req 3.5 / 4.3 — unauthenticated session end returns 401."""
    class_id = _get_class_id(client)
    resp = client.post(f"/classes/{class_id}/sessions/end")
    assert resp.status_code == 401
