import os
import secrets
import string
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "./classroom.db")
engine = create_engine(f"sqlite:///{DATABASE_URL}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL CHECK (role IN ('teacher','student')),
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS classes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES users(id),
                name       TEXT NOT NULL,
                subject    TEXT NOT NULL,
                class_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES users(id),
                class_id   INTEGER NOT NULL REFERENCES classes(id),
                joined_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (student_id, class_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id   INTEGER NOT NULL REFERENCES classes(id),
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at   TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS attention_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  INTEGER NOT NULL REFERENCES users(id),
                session_id  INTEGER NOT NULL REFERENCES sessions(id),
                score       REAL NOT NULL CHECK (score >= 0 AND score <= 100),
                state       TEXT NOT NULL CHECK (state IN ('FOCUSED','LOW FOCUS','DISTRACTED','FATIGUED')),
                fatigue     REAL NOT NULL CHECK (fatigue >= 0 AND fatigue <= 100),
                gaze        TEXT NOT NULL CHECK (gaze IN ('LEFT','CENTER','RIGHT','DOWN')),
                blinks      INTEGER NOT NULL CHECK (blinks >= 0),
                recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        # indexes
        for stmt in [
            "CREATE INDEX IF NOT EXISTS idx_ar_session  ON attention_records(session_id, student_id, recorded_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_ar_student  ON attention_records(student_id, recorded_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sess_class  ON sessions(class_id, ended_at)",
            "CREATE INDEX IF NOT EXISTS idx_enroll      ON enrollments(class_id, student_id)",
            "CREATE INDEX IF NOT EXISTS idx_classes_t   ON classes(teacher_id)",
        ]:
            conn.execute(text(stmt))
        conn.commit()


ALPHABET = string.ascii_uppercase + string.digits


def generate_class_code(db: Session) -> str:
    from db.models import Class
    for _ in range(10):
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not db.query(Class).filter_by(class_code=code).first():
            return code
    raise RuntimeError("Class code generation failed")


def compute_trend(scores: list) -> str:
    if len(scores) < 2:
        return "STABLE"
    mid = len(scores) // 2
    early  = sum(scores[:mid]) / mid
    recent = sum(scores[mid:]) / (len(scores) - mid)
    diff   = recent - early
    if diff >= 5:  return "IMPROVING"
    if diff <= -5: return "DECLINING"
    return "STABLE"
