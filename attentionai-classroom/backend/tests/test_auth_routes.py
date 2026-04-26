"""
Integration tests for auth routes.
Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5
"""
import os
import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend dir is on path (conftest.py already does this, but be explicit)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app
from db.database import get_db, init_db

# ── Test database setup ────────────────────────────────────────────────────────

SQLALCHEMY_TEST_URL = "sqlite:///./test_auth.db"
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
    """Create a TestClient backed by an isolated SQLite test database."""
    # Initialise schema on the test engine
    init_db.__globals__["engine"] = test_engine  # point init_db at test engine
    # Re-run init_db using the test engine directly
    from sqlalchemy import text
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

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    # Cleanup
    app.dependency_overrides.clear()
    test_engine.dispose()
    if os.path.exists("./test_auth.db"):
        os.remove("./test_auth.db")


# ── Helpers ────────────────────────────────────────────────────────────────────

TEACHER_PAYLOAD = {
    "name": "Alice Teacher",
    "email": "alice@example.com",
    "password": "secret123",
    "role": "teacher",
    "subject": "Physics",
}

STUDENT_PAYLOAD = {
    "name": "Bob Student",
    "email": "bob@example.com",
    "password": "pass456",
    "role": "student",
}


# ── Register tests ─────────────────────────────────────────────────────────────

def test_register_teacher_success(client):
    """Req 1.1 — successful registration returns 201."""
    resp = client.post("/auth/register", json=TEACHER_PAYLOAD)
    assert resp.status_code == 201


def test_register_student_success(client):
    """Req 1.1 — student registration (no subject) returns 201."""
    resp = client.post("/auth/register", json=STUDENT_PAYLOAD)
    assert resp.status_code == 201


def test_register_duplicate_email_returns_409(client):
    """Req 1.2 — duplicate email returns 409 Conflict."""
    # alice@example.com was already registered in test_register_teacher_success
    resp = client.post("/auth/register", json=TEACHER_PAYLOAD)
    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()


def test_register_missing_required_field_returns_422(client):
    """Req 1.4 — missing 'name' field returns 422."""
    payload = {k: v for k, v in TEACHER_PAYLOAD.items() if k != "name"}
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422


def test_register_missing_password_returns_422(client):
    """Req 1.4 — missing 'password' field returns 422."""
    payload = {k: v for k, v in TEACHER_PAYLOAD.items() if k != "password"}
    payload["email"] = "nopwd@example.com"
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422


def test_register_invalid_email_returns_422(client):
    """Req 1.5 — non-email string in email field returns 422."""
    payload = {**TEACHER_PAYLOAD, "email": "not-an-email", "name": "Charlie"}
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422


def test_register_short_password_returns_422(client):
    """Req 1.4 — password shorter than min_length=6 returns 422."""
    payload = {**TEACHER_PAYLOAD, "email": "short@example.com", "password": "abc"}
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422


def test_register_teacher_without_subject_returns_422(client):
    """Req 1.4 — teacher role without subject returns 422 (app-level check)."""
    payload = {**TEACHER_PAYLOAD, "email": "nosubject@example.com", "subject": None}
    resp = client.post("/auth/register", json=payload)
    # The router raises 422 for missing subject on teacher
    assert resp.status_code == 422


# ── Login tests ────────────────────────────────────────────────────────────────

def test_login_success_returns_jwt(client):
    """Req 2.1 — valid credentials return a JWT with access_token field."""
    resp = client.post("/auth/login", json={
        "email": TEACHER_PAYLOAD["email"],
        "password": TEACHER_PAYLOAD["password"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "teacher"
    assert "user_id" in body
    assert body["name"] == TEACHER_PAYLOAD["name"]


def test_login_wrong_password_returns_401(client):
    """Req 2.3 — correct email but wrong password returns 401."""
    resp = client.post("/auth/login", json={
        "email": TEACHER_PAYLOAD["email"],
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


def test_login_unknown_email_returns_401(client):
    """Req 2.2 — email that was never registered returns 401."""
    resp = client.post("/auth/login", json={
        "email": "nobody@example.com",
        "password": "doesntmatter",
    })
    assert resp.status_code == 401


# ── Protected endpoint tests ───────────────────────────────────────────────────

def test_protected_endpoint_without_token_returns_401(client):
    """Req 2.4 — request to protected endpoint with no Authorization header returns 401."""
    resp = client.get("/classes/mine")
    assert resp.status_code == 401


def test_protected_endpoint_with_invalid_token_returns_401(client):
    """Req 2.5 — request with a garbage/expired token returns 401."""
    resp = client.get(
        "/classes/mine",
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert resp.status_code == 401


def test_protected_endpoint_with_expired_token_returns_401(client):
    """Req 2.5 — request with an expired (past exp) JWT returns 401."""
    from jose import jwt as jose_jwt
    from auth.jwt import SECRET_KEY, ALGORITHM

    expired_token = jose_jwt.encode(
        {"sub": "1", "role": "teacher", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    resp = client.get(
        "/classes/mine",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
