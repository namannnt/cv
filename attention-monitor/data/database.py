"""
SQLite storage layer.
Schema:
  sessions       — one row per session (metadata)
  attention_data — one row per second (time series)
  user_stats     — single-row user gamification state
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "attention.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # dict-like access
    conn.execute("PRAGMA journal_mode=WAL") # concurrent read/write
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            mode        TEXT DEFAULT 'READING',
            avg_score   REAL,
            total_rows  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS attention_data (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id),
            ts          TEXT NOT NULL,
            score       REAL NOT NULL,
            state       TEXT NOT NULL,
            blink_rate  REAL,
            gaze        TEXT,
            off_time    REAL,
            fatigue     REAL
        );

        CREATE INDEX IF NOT EXISTS idx_attention_session
            ON attention_data(session_id);

        CREATE TABLE IF NOT EXISTS user_stats (
            id                  INTEGER PRIMARY KEY CHECK (id = 1),
            streak              INTEGER DEFAULT 0,
            last_date           TEXT DEFAULT '',
            total_sessions      INTEGER DEFAULT 0,
            high_score          REAL DEFAULT 0,
            total_focus_minutes INTEGER DEFAULT 0
        );

        INSERT OR IGNORE INTO user_stats (id) VALUES (1);
    """)
    conn.commit()
    conn.close()


class SessionDB:
    def __init__(self):
        init_db()
        self.conn = get_connection()
        self.session_id: int | None = None

    def start_session(self, mode: str = "READING") -> int:
        cur = self.conn.execute(
            "INSERT INTO sessions (started_at, mode) VALUES (?, ?)",
            (datetime.now().isoformat(), mode)
        )
        self.conn.commit()
        self.session_id = cur.lastrowid
        return self.session_id

    def log(self, score, state, blink_rate, gaze, off_time, fatigue):
        if self.session_id is None:
            return
        self.conn.execute(
            """INSERT INTO attention_data
               (session_id, ts, score, state, blink_rate, gaze, off_time, fatigue)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.session_id, datetime.now().strftime("%H:%M:%S"),
             round(score, 1), state, round(blink_rate, 1),
             gaze, round(off_time, 1), round(fatigue, 1))
        )
        self.conn.commit()

    def end_session(self):
        if self.session_id is None:
            return
        row = self.conn.execute(
            "SELECT AVG(score) as avg, COUNT(*) as n FROM attention_data WHERE session_id=?",
            (self.session_id,)
        ).fetchone()
        self.conn.execute(
            "UPDATE sessions SET ended_at=?, avg_score=?, total_rows=? WHERE id=?",
            (datetime.now().isoformat(), round(row["avg"] or 0, 1), row["n"], self.session_id)
        )
        self.conn.commit()

    def close(self):
        self.end_session()
        self.conn.close()


def get_session_summary(session_id: int) -> dict:
    conn = get_connection()
    row = conn.execute(
        """SELECT s.started_at, s.ended_at, s.mode, s.avg_score, s.total_rows,
                  SUM(CASE WHEN d.state='FOCUSED' THEN 1 ELSE 0 END) as focus_sec,
                  SUM(CASE WHEN d.state='DISTRACTED' THEN 1 ELSE 0 END) as distract_sec,
                  SUM(CASE WHEN d.fatigue > 0 THEN 1 ELSE 0 END) as fatigue_events
           FROM sessions s
           JOIN attention_data d ON d.session_id = s.id
           WHERE s.id = ?
           GROUP BY s.id""",
        (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    return dict(row)


def list_sessions() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, started_at, mode, avg_score, total_rows FROM sessions ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
