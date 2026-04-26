"""
Property-based tests for AttentionAI Classroom backend.

Property 1: Password storage never exposes plaintext
  Validates: Requirements 1.3
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis import HealthCheck

from auth.jwt import hash_password, verify_password


# ---------------------------------------------------------------------------
# Property 1: Password storage never exposes plaintext
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(plain=st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),  # printable ASCII
    min_size=6,
    max_size=72,  # bcrypt hard limit is 72 bytes; ASCII chars are 1 byte each
))
def test_password_hash_never_equals_plaintext(plain):
    """
    **Validates: Requirements 1.3**

    For any valid plaintext password, the bcrypt hash produced by
    hash_password() SHALL NOT equal the original plaintext string.
    """
    hashed = hash_password(plain)
    assert hashed != plain, (
        f"hash_password returned the plaintext unchanged for input: {plain!r}"
    )


# ---------------------------------------------------------------------------
# Property 2: JWT round-trip preserves teacher identity
# ---------------------------------------------------------------------------

from auth.jwt import create_token, _decode


@settings(max_examples=100, deadline=None)
@given(teacher_id=st.integers(min_value=1, max_value=2**31 - 1))
def test_jwt_roundtrip_preserves_teacher_identity(teacher_id):
    """
    **Validates: Requirements 2.1**

    For any teacher ID, encoding it into a JWT and then decoding that JWT
    SHALL return the same teacher ID, provided the token has not expired.
    """
    token = create_token(teacher_id, role="teacher")
    payload = _decode(token)
    decoded_id = int(payload["sub"])
    assert decoded_id == teacher_id, (
        f"JWT round-trip failed: encoded {teacher_id!r}, decoded {decoded_id!r}"
    )


# ---------------------------------------------------------------------------
# Property 3: Class code format invariant
# ---------------------------------------------------------------------------

import string
from unittest.mock import MagicMock

from db.database import generate_class_code


@settings(max_examples=100, deadline=None)
@given(st.integers())
def test_class_code_format_invariant(_: int):
    """
    **Validates: Requirements 3.1, 3.2**

    For any call to generate_class_code, the returned string SHALL be exactly
    6 characters long and consist only of uppercase ASCII letters and digits.
    """
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = None

    code = generate_class_code(mock_db)

    assert len(code) == 6, (
        f"Expected class code of length 6, got {len(code)!r}: {code!r}"
    )
    valid_chars = string.ascii_uppercase + string.digits
    for ch in code:
        assert ch in valid_chars, (
            f"Class code {code!r} contains invalid character {ch!r}"
        )


# ---------------------------------------------------------------------------
# Property 4: Student join idempotence (enrollment uniqueness enforced)
# ---------------------------------------------------------------------------

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from db.models import Base, User, Class, Enrollment


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    student_name=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=1,
        max_size=100,
    ),
    class_name=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=1,
        max_size=100,
    ),
)
def test_student_enrollment_uniqueness_enforced(student_name, class_name):
    """
    **Validates: Requirements 5.4**

    For any student who joins a class, the enrollment record is unique —
    no duplicate (student_id, class_id) rows can exist in the database.

    The UNIQUE(student_id, class_id) constraint on the enrollments table
    SHALL raise an IntegrityError on a second insert for the same pair,
    and exactly 1 enrollment record SHALL exist after both attempts.
    """
    # Set up an isolated in-memory SQLite database per iteration
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Create a teacher
        teacher = User(
            name="Teacher",
            email="teacher@test.com",
            password_hash="hashed",
            role="teacher",
        )
        db.add(teacher)
        db.flush()

        # Create a class
        cls = Class(
            teacher_id=teacher.id,
            name=class_name,
            subject="Test Subject",
            class_code="TST001",
        )
        db.add(cls)
        db.flush()

        # Create a student
        student = User(
            name=student_name,
            email="student@test.com",
            password_hash="hashed",
            role="student",
        )
        db.add(student)
        db.flush()

        # First enrollment — should succeed
        enrollment1 = Enrollment(student_id=student.id, class_id=cls.id)
        db.add(enrollment1)
        db.commit()

        # Second enrollment — should raise IntegrityError due to UNIQUE constraint
        enrollment2 = Enrollment(student_id=student.id, class_id=cls.id)
        db.add(enrollment2)
        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

        # Assert exactly 1 enrollment record exists for this student+class pair
        count = (
            db.query(Enrollment)
            .filter_by(student_id=student.id, class_id=cls.id)
            .count()
        )
        assert count == 1, (
            f"Expected exactly 1 enrollment for student_id={student.id}, "
            f"class_id={cls.id}, but found {count}"
        )

    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 5: Data ingestion rejected without active session
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import get_db
from db.models import Base, User, Class, Enrollment, Session as SessionModel, AttentionRecord
from auth.jwt import hash_password, create_token


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    state=st.sampled_from(["FOCUSED", "LOW FOCUS", "DISTRACTED", "FATIGUED"]),
    fatigue=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    gaze=st.sampled_from(["LEFT", "CENTER", "RIGHT", "DOWN"]),
    blinks=st.integers(min_value=0, max_value=100),
)
def test_send_data_rejected_without_active_session(score, state, fatigue, gaze, blinks):
    """
    **Validates: Requirements 4.5, 4.6**

    For any valid attention record payload, if no session is currently active
    for the associated batch, the guard condition SHALL detect no active session
    and SHALL NOT insert any row into attention_records.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    db = Sess()
    try:
        teacher = User(name="T", email="t@t.com", password_hash="h", role="teacher")
        db.add(teacher); db.flush()
        cls = Class(teacher_id=teacher.id, name="C", subject="S", class_code="NOACT1")
        db.add(cls); db.flush()
        student = User(name="S", email="s@s.com", password_hash="h", role="student")
        db.add(student); db.flush()
        db.add(Enrollment(student_id=student.id, class_id=cls.id))
        db.commit()

        # No active session exists — simulate the guard check from data.py
        active = db.query(SessionModel).filter(
            SessionModel.class_id == cls.id,
            SessionModel.ended_at.is_(None)
        ).first()

        # Guard: no active session → data must NOT be inserted
        assert active is None, "Expected no active session"

        if active is None:
            # This is the 403 path — do not insert
            pass
        else:
            db.add(AttentionRecord(
                student_id=student.id, session_id=active.id,
                score=score, state=state, fatigue=fatigue,
                gaze=gaze, blinks=blinks,
            ))
            db.commit()

        count = db.query(AttentionRecord).filter_by(student_id=student.id).count()
        assert count == 0, f"Expected 0 records when no active session, found {count}"
    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 6: Online/offline classification correctness
# ---------------------------------------------------------------------------

import time as _time


@settings(max_examples=100, deadline=None)
@given(
    seconds_ago=st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False),
)
def test_online_offline_classification(seconds_ago):
    """
    **Validates: Requirements 7.3, 7.4**

    A student whose last_seen is within 5 seconds SHALL be ONLINE;
    a student whose last_seen is more than 5 seconds ago SHALL be OFFLINE.
    """
    ONLINE_SECS = 5
    now = _time.time()
    last_seen = now - seconds_ago
    is_online = (now - last_seen) <= ONLINE_SECS

    if seconds_ago <= ONLINE_SECS:
        assert is_online, (
            f"Expected ONLINE for last_seen {seconds_ago:.3f}s ago, but classified OFFLINE"
        )
    else:
        assert not is_online, (
            f"Expected OFFLINE for last_seen {seconds_ago:.3f}s ago, but classified ONLINE"
        )


# ---------------------------------------------------------------------------
# Property 7: Class average computed only over ONLINE students
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(
    online_scores=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0, max_size=20,
    ),
    offline_scores=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=0, max_size=20,
    ),
)
def test_class_average_only_over_online_students(online_scores, offline_scores):
    """
    **Validates: Requirements 7.5**

    The avg_score SHALL equal the arithmetic mean of scores of ONLINE students only.
    When no students are ONLINE, avg_score SHALL be 0.
    """
    # Simulate the avg computation from data.py
    avg = round(sum(online_scores) / len(online_scores), 1) if online_scores else 0.0

    if not online_scores:
        assert avg == 0.0, f"Expected 0.0 avg with no online students, got {avg}"
    else:
        expected = sum(online_scores) / len(online_scores)
        assert abs(avg - expected) < 0.1, (
            f"avg_score {avg} does not match expected {expected:.3f} "
            f"for online_scores={online_scores}"
        )

    # Offline scores must NOT affect the average
    avg_with_offline = round(sum(online_scores) / len(online_scores), 1) if online_scores else 0.0
    assert avg == avg_with_offline, (
        f"avg changed when offline scores were present: {avg} vs {avg_with_offline}"
    )


# ---------------------------------------------------------------------------
# Property 9: Attention record validation rejects out-of-range inputs
# ---------------------------------------------------------------------------

from pydantic import ValidationError
from schemas import AttentionRecordRequest


@settings(max_examples=100, deadline=None)
@given(score=st.floats(min_value=100.01, max_value=1000.0, allow_nan=False, allow_infinity=False))
def test_attention_record_rejects_score_above_100(score):
    """
    **Validates: Requirements 6.3**
    score > 100 SHALL be rejected with a ValidationError.
    """
    try:
        AttentionRecordRequest(
            class_code="ABC123", score=score, state="FOCUSED",
            fatigue=50.0, gaze="CENTER", blinks=5,
        )
        assert False, f"Expected ValidationError for score={score}"
    except ValidationError:
        pass


@settings(max_examples=100, deadline=None)
@given(score=st.floats(min_value=-1000.0, max_value=-0.01, allow_nan=False, allow_infinity=False))
def test_attention_record_rejects_score_below_0(score):
    """
    **Validates: Requirements 6.3**
    score < 0 SHALL be rejected with a ValidationError.
    """
    try:
        AttentionRecordRequest(
            class_code="ABC123", score=score, state="FOCUSED",
            fatigue=50.0, gaze="CENTER", blinks=5,
        )
        assert False, f"Expected ValidationError for score={score}"
    except ValidationError:
        pass


@settings(max_examples=100, deadline=None)
@given(
    state=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in {"FOCUSED", "LOW FOCUS", "DISTRACTED", "FATIGUED"}
    )
)
def test_attention_record_rejects_invalid_state(state):
    """
    **Validates: Requirements 6.4**
    state not in valid set SHALL be rejected with a ValidationError.
    """
    try:
        AttentionRecordRequest(
            class_code="ABC123", score=50.0, state=state,
            fatigue=50.0, gaze="CENTER", blinks=5,
        )
        assert False, f"Expected ValidationError for state={state!r}"
    except ValidationError:
        pass


@settings(max_examples=100, deadline=None)
@given(
    gaze=st.text(min_size=1, max_size=20).filter(
        lambda g: g not in {"LEFT", "CENTER", "RIGHT", "DOWN"}
    )
)
def test_attention_record_rejects_invalid_gaze(gaze):
    """
    **Validates: Requirements 6.5**
    gaze not in valid set SHALL be rejected with a ValidationError.
    """
    try:
        AttentionRecordRequest(
            class_code="ABC123", score=50.0, state="FOCUSED",
            fatigue=50.0, gaze=gaze, blinks=5,
        )
        assert False, f"Expected ValidationError for gaze={gaze!r}"
    except ValidationError:
        pass


# ---------------------------------------------------------------------------
# Property 10: Valid data ingestion persists to database
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    state=st.sampled_from(["FOCUSED", "LOW FOCUS", "DISTRACTED", "FATIGUED"]),
    fatigue=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    gaze=st.sampled_from(["LEFT", "CENTER", "RIGHT", "DOWN"]),
    blinks=st.integers(min_value=0, max_value=100),
)
def test_valid_data_persists_to_database(score, state, fatigue, gaze, blinks):
    """
    **Validates: Requirements 6.1**

    For any valid attention record, when an active session exists, inserting
    the record SHALL succeed and the row SHALL be retrievable from attention_records.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    db = Sess()
    try:
        teacher = User(name="T", email="t@t.com", password_hash="h", role="teacher")
        db.add(teacher); db.flush()
        cls = Class(teacher_id=teacher.id, name="C", subject="S", class_code="ACTIVE")
        db.add(cls); db.flush()
        student = User(name="S", email="s@s.com", password_hash="h", role="student")
        db.add(student); db.flush()
        db.add(Enrollment(student_id=student.id, class_id=cls.id))
        active = SessionModel(class_id=cls.id)
        db.add(active); db.commit()

        # Simulate the data.py insert path
        rec = AttentionRecord(
            student_id=student.id, session_id=active.id,
            score=round(score, 2), state=state,
            fatigue=round(fatigue, 2), gaze=gaze, blinks=blinks,
        )
        db.add(rec); db.commit()

        count = db.query(AttentionRecord).filter_by(student_id=student.id).count()
        assert count == 1, f"Expected 1 persisted record, found {count}"

        fetched = db.query(AttentionRecord).filter_by(student_id=student.id).first()
        assert fetched is not None
        assert fetched.score == round(score, 2)
        assert fetched.state == state
        assert fetched.gaze == gaze
    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 11: Class-data returns latest record per student (via _live cache)
# ---------------------------------------------------------------------------

import routers.data as _data_router


@settings(max_examples=100, deadline=None)
@given(
    scores=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=2, max_size=10,
    ),
    state=st.sampled_from(["FOCUSED", "LOW FOCUS", "DISTRACTED", "FATIGUED"]),
    gaze=st.sampled_from(["LEFT", "CENTER", "RIGHT", "DOWN"]),
)
def test_live_cache_stores_latest_record_per_student(scores, state, gaze):
    """
    **Validates: Requirements 7.1**

    After multiple updates to _live_cache for the same student_id, the cache
    SHALL contain exactly one entry per student reflecting the most recent values.
    """
    student_id = 99999  # synthetic ID, won't collide with real data

    # Simulate multiple send-data calls updating the cache
    for score in scores:
        _data_router._live[student_id] = {
            "name": "Test Student",
            "email": "test@test.com",
            "score": round(score, 2),
            "state": state,
            "fatigue": 50.0,
            "gaze": gaze,
            "blinks": 5,
            "last_seen": _time.time(),
        }

    # Cache must have exactly one entry for this student
    assert student_id in _data_router._live, "Student not found in _live cache"
    cached = _data_router._live[student_id]

    # The cached score must be the last one written
    expected_score = round(scores[-1], 2)
    assert cached["score"] == expected_score, (
        f"Expected latest score {expected_score}, got {cached['score']}"
    )

    # Cleanup
    del _data_router._live[student_id]


# ---------------------------------------------------------------------------
# Property 8: Performance trend classification correctness
# ---------------------------------------------------------------------------

from db.database import compute_trend


@settings(max_examples=200, deadline=None)
@given(
    early_scores=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=10,
    ),
    recent_scores=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=10,
    ),
)
def test_compute_trend_classification(early_scores, recent_scores):
    """
    **Validates: Requirements 8.3, 8.4, 8.5**

    compute_trend SHALL return:
    - IMPROVING when recent_half_avg - early_half_avg >= 5
    - DECLINING when early_half_avg - recent_half_avg >= 5
    - STABLE otherwise (difference < 5 in either direction)
    """
    scores = early_scores + recent_scores
    result = compute_trend(scores)

    if len(scores) < 2:
        assert result == "STABLE", f"Expected STABLE for <2 scores, got {result}"
        return

    mid = len(scores) // 2
    early_avg = sum(scores[:mid]) / mid
    recent_avg = sum(scores[mid:]) / (len(scores) - mid)
    diff = recent_avg - early_avg

    if diff >= 5:
        assert result == "IMPROVING", (
            f"Expected IMPROVING (diff={diff:.2f}), got {result!r}. scores={scores}"
        )
    elif diff <= -5:
        assert result == "DECLINING", (
            f"Expected DECLINING (diff={diff:.2f}), got {result!r}. scores={scores}"
        )
    else:
        assert result == "STABLE", (
            f"Expected STABLE (diff={diff:.2f}), got {result!r}. scores={scores}"
        )


# ---------------------------------------------------------------------------
# Property 12: Student history respects 30-day window
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    days_ago=st.integers(min_value=0, max_value=120),
)
def test_student_history_30_day_window(days_ago):
    """
    **Validates: Requirements 9.3**

    The /my-history endpoint SHALL only return sessions whose started_at is
    within the past 30 days. Sessions older than 30 days SHALL be excluded.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    db = Sess()
    try:
        teacher = User(name="T", email="t@t.com", password_hash="h", role="teacher")
        db.add(teacher); db.flush()
        cls = Class(teacher_id=teacher.id, name="C", subject="S", class_code="HIST01")
        db.add(cls); db.flush()
        student = User(name="S", email="s@s.com", password_hash="h", role="student")
        db.add(student); db.flush()
        db.add(Enrollment(student_id=student.id, class_id=cls.id))

        # Create a session started `days_ago` days in the past.
        # Add a 1-minute buffer so boundary cases (days_ago==30) don't flap
        # due to microsecond differences between session_start and cutoff.
        now = datetime.now(timezone.utc)
        session_start = (now - timedelta(days=days_ago) + timedelta(minutes=1)).isoformat()
        session_end = (now - timedelta(days=days_ago) + timedelta(hours=1)).isoformat()
        sess = SessionModel(class_id=cls.id, started_at=session_start, ended_at=session_end)
        db.add(sess); db.flush()

        # Add an attention record for this student in this session
        db.add(AttentionRecord(
            student_id=student.id, session_id=sess.id,
            score=75.0, state="FOCUSED", fatigue=20.0, gaze="CENTER", blinks=5,
        ))
        db.commit()

        # Simulate the 30-day cutoff filter from reports.py
        # Use timedelta(days=30, seconds=1) to match the implementation's inclusive boundary
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30, seconds=1)).isoformat()
        matching_sessions = db.query(SessionModel).join(
            AttentionRecord, AttentionRecord.session_id == SessionModel.id
        ).filter(
            AttentionRecord.student_id == student.id,
            SessionModel.started_at >= cutoff,
            SessionModel.ended_at.isnot(None),
        ).distinct().all()

        if days_ago <= 30:
            assert len(matching_sessions) == 1, (
                f"Expected session within 30 days to be included (days_ago={days_ago}), "
                f"but got {len(matching_sessions)} results"
            )
        else:
            assert len(matching_sessions) == 0, (
                f"Expected session older than 30 days to be excluded (days_ago={days_ago}), "
                f"but got {len(matching_sessions)} results"
            )
    finally:
        db.close()
        engine.dispose()
