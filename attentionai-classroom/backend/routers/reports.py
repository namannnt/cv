from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.jwt import get_current_user, require_teacher
from db.database import compute_trend, get_db
from db.models import AttentionRecord, Class, Enrollment, Session as SessionModel, User
from schemas import MyClassHistoryEntry, SessionHistoryEntry, StudentSummaryEntry

router = APIRouter(tags=["reports"])


def _dur(s, e):
    """Calculate duration in seconds between two datetime strings.
    Both stored as UTC in SQLite format: 'YYYY-MM-DD HH:MM:SS'
    """
    if not e: return 0
    try:
        # Normalize both strings — strip T, strip timezone suffix
        def _parse(dt_str):
            dt_str = dt_str.replace('T', ' ').split('+')[0].split('Z')[0].strip()
            # Try with microseconds first
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(dt_str, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse: {dt_str}")
        a, b = _parse(s), _parse(e)
        return max(0, int((b - a).total_seconds()))
    except Exception:
        return 0


@router.get("/reports/sessions/{class_id}", response_model=list[SessionHistoryEntry])
def session_history(class_id: int, user=Depends(require_teacher), db: Session = Depends(get_db)):
    cls = db.query(Class).filter_by(id=class_id, teacher_id=user["user_id"]).first()
    if not cls: raise HTTPException(404, "Class not found")

    sessions = db.query(SessionModel).filter(
        SessionModel.class_id == class_id, SessionModel.ended_at.isnot(None)
    ).order_by(SessionModel.started_at.desc()).all()

    result = []
    for s in sessions:
        avg = db.query(func.avg(AttentionRecord.score)).filter_by(session_id=s.id).scalar() or 0
        dist = db.query(func.count(AttentionRecord.id)).filter(
            AttentionRecord.session_id == s.id, AttentionRecord.state == "DISTRACTED"
        ).scalar() or 0
        result.append(SessionHistoryEntry(
            session_id=s.id, date=s.started_at[:10],
            duration_seconds=_dur(s.started_at, s.ended_at),
            avg_score=round(avg, 2), distraction_events=dist,
        ))
    return result


@router.get("/reports/students/{class_id}", response_model=list[StudentSummaryEntry])
def student_summaries(class_id: int, user=Depends(require_teacher), db: Session = Depends(get_db)):
    cls = db.query(Class).filter_by(id=class_id, teacher_id=user["user_id"]).first()
    if not cls: raise HTTPException(404, "Class not found")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30, seconds=1)).isoformat()
    enrollments = db.query(Enrollment).filter_by(class_id=class_id).all()
    result = []
    for e in enrollments:
        student = db.query(User).get(e.student_id)
        sids = [r[0] for r in db.query(AttentionRecord.session_id).join(
            SessionModel, AttentionRecord.session_id == SessionModel.id
        ).filter(
            AttentionRecord.student_id == e.student_id,
            SessionModel.class_id == class_id,
            SessionModel.started_at >= cutoff,
            SessionModel.ended_at.isnot(None),
        ).distinct().all()]
        if not sids: continue
        per_session = []
        for sid in sorted(sids):
            a = db.query(func.avg(AttentionRecord.score)).filter_by(
                student_id=e.student_id, session_id=sid).scalar()
            if a: per_session.append(a)
        overall = db.query(func.avg(AttentionRecord.score)).join(
            SessionModel, AttentionRecord.session_id == SessionModel.id
        ).filter(
            AttentionRecord.student_id == e.student_id,
            SessionModel.class_id == class_id,
            SessionModel.started_at >= cutoff,
        ).scalar() or 0
        result.append(StudentSummaryEntry(
            student_id=student.id, name=student.name, email=student.email,
            attendance_count=len(sids), avg_score=round(overall, 2),
            trend=compute_trend(per_session),
        ))
    return result


@router.get("/my-history", response_model=list[MyClassHistoryEntry])
def my_history(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user["role"] != "student": raise HTTPException(403, "Students only")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30, seconds=1)).isoformat()
    sessions = db.query(SessionModel).join(
        AttentionRecord, AttentionRecord.session_id == SessionModel.id
    ).filter(
        AttentionRecord.student_id == user["user_id"],
        SessionModel.started_at >= cutoff,
        SessionModel.ended_at.isnot(None),
    ).distinct().order_by(SessionModel.started_at.desc()).all()

    result = []
    for s in sessions:
        cls = db.query(Class).get(s.class_id)
        avg = db.query(func.avg(AttentionRecord.score)).filter_by(
            student_id=user["user_id"], session_id=s.id).scalar() or 0
        result.append(MyClassHistoryEntry(
            session_id=s.id, class_name=cls.name if cls else "?",
            date=s.started_at[:10],
            duration_seconds=_dur(s.started_at, s.ended_at),
            avg_score=round(avg, 2),
        ))
    return result


@router.get("/reports/session-detail/{session_id}/student/{student_id}")
def session_detail(session_id: int, student_id: int, user=Depends(require_teacher), db: Session = Depends(get_db)):
    """
    Detailed per-student breakdown for a session.
    Returns: state breakdown, distraction episodes, fatigue onset,
             attention timeline (sampled), gaze distribution.
    """
    # Verify teacher owns the session's class
    session = db.query(SessionModel).get(session_id)
    if not session: raise HTTPException(404, "Session not found")
    cls = db.query(Class).filter_by(id=session.class_id, teacher_id=user["user_id"]).first()
    if not cls: raise HTTPException(403, "Not your session")

    student = db.query(User).get(student_id)
    if not student: raise HTTPException(404, "Student not found")

    # Fetch all records for this student in this session, ordered by time
    records = db.query(AttentionRecord).filter_by(
        session_id=session_id, student_id=student_id
    ).order_by(AttentionRecord.recorded_at).all()

    if not records:
        return {"student_name": student.name, "total_records": 0, "message": "No data for this student"}

    session_start_str = session.started_at

    def _secs_into_session(ts_str):
        """Seconds from session start to this record."""
        return max(0, _dur(session_start_str, ts_str))

    # ── State breakdown (seconds in each state) ──
    state_counts = {"FOCUSED": 0, "LOW FOCUS": 0, "DISTRACTED": 0, "FATIGUED": 0}
    for r in records:
        state_counts[r.state] = state_counts.get(r.state, 0) + 1  # each record ≈ 1 second

    total_secs = len(records)

    # ── Distraction episodes ──
    # Group consecutive DISTRACTED records into episodes
    episodes = []
    in_episode = False
    ep_start = None
    ep_start_secs = 0
    for r in records:
        if r.state == "DISTRACTED":
            if not in_episode:
                in_episode = True
                ep_start = r.recorded_at
                ep_start_secs = _secs_into_session(r.recorded_at)
        else:
            if in_episode:
                in_episode = False
                ep_dur = _secs_into_session(r.recorded_at) - ep_start_secs
                if ep_dur >= 2:  # only count episodes ≥ 2s
                    episodes.append({
                        "start_secs": ep_start_secs,
                        "duration_secs": ep_dur,
                        "label": f"{ep_start_secs // 60}m {ep_start_secs % 60}s into session"
                    })
    # Close open episode at end
    if in_episode and ep_start:
        ep_dur = _secs_into_session(records[-1].recorded_at) - ep_start_secs
        if ep_dur >= 2:
            episodes.append({
                "start_secs": ep_start_secs,
                "duration_secs": ep_dur,
                "label": f"{ep_start_secs // 60}m {ep_start_secs % 60}s into session"
            })

    # ── Fatigue onset ──
    fatigue_onset = None
    fatigue_peak  = 0.0
    fatigue_peak_secs = 0
    for r in records:
        if r.fatigue > fatigue_peak:
            fatigue_peak = r.fatigue
            fatigue_peak_secs = _secs_into_session(r.recorded_at)
        if fatigue_onset is None and r.fatigue >= 60:
            onset_secs = _secs_into_session(r.recorded_at)
            fatigue_onset = {
                "secs_into_session": onset_secs,
                "label": f"{onset_secs // 60}m {onset_secs % 60}s into session",
                "fatigue_level": round(r.fatigue, 1)
            }

    # ── Attention timeline (sampled to max 120 points for chart) ──
    step = max(1, len(records) // 120)
    timeline = []
    for i, r in enumerate(records):
        if i % step == 0:
            timeline.append({
                "t": _secs_into_session(r.recorded_at),
                "score": round(r.score, 1),
                "fatigue": round(r.fatigue, 1),
                "state": r.state,
            })

    # ── Gaze distribution ──
    gaze_counts = {}
    for r in records:
        gaze_counts[r.gaze] = gaze_counts.get(r.gaze, 0) + 1

    # ── Focus quality score (0-100) ──
    focused_pct    = state_counts.get("FOCUSED", 0) / max(1, total_secs) * 100
    distracted_pct = state_counts.get("DISTRACTED", 0) / max(1, total_secs) * 100
    fatigued_pct   = state_counts.get("FATIGUED", 0) / max(1, total_secs) * 100
    quality = max(0, round(focused_pct - distracted_pct * 0.5 - fatigued_pct * 0.3, 1))

    return {
        "student_name":    student.name,
        "total_records":   total_secs,
        "duration_secs":   total_secs,
        "avg_score":       round(sum(r.score for r in records) / total_secs, 1),
        "quality_score":   quality,
        "state_breakdown": {
            k: {"seconds": v, "percent": round(v / max(1, total_secs) * 100, 1)}
            for k, v in state_counts.items()
        },
        "distraction_episodes": episodes,
        "total_distraction_secs": sum(e["duration_secs"] for e in episodes),
        "fatigue_onset":   fatigue_onset,
        "fatigue_peak":    {"level": round(fatigue_peak, 1), "secs_into_session": fatigue_peak_secs},
        "gaze_distribution": {
            k: {"count": v, "percent": round(v / max(1, total_secs) * 100, 1)}
            for k, v in gaze_counts.items()
        },
        "timeline": timeline,
    }
