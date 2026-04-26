import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.jwt import get_current_user, require_teacher
from db.database import get_db
from db.models import AttentionRecord, Class, Enrollment, Session as SessionModel, User
from schemas import AttentionRecordRequest, ClassDataResponse, StudentLiveEntry

router = APIRouter(tags=["data"])

# { student_id: { score, state, fatigue, gaze, blinks, last_seen, name, email } }
_live: dict[int, dict] = {}
ONLINE_SECS = 5


@router.post("/send-data")
def send_data(
    payload: AttentionRecordRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user["role"] != "student":
        raise HTTPException(403, "Only students can send data")

    cls = db.query(Class).filter_by(class_code=payload.class_code.upper()).first()
    if not cls:
        raise HTTPException(404, "Class not found")

    # verify enrolled
    if not db.query(Enrollment).filter_by(student_id=user["user_id"], class_id=cls.id).first():
        raise HTTPException(403, "Not enrolled in this class")

    # active session required
    active = db.query(SessionModel).filter(
        SessionModel.class_id == cls.id, SessionModel.ended_at.is_(None)
    ).first()
    if not active:
        raise HTTPException(403, "No active session")

    rec = AttentionRecord(
        student_id=user["user_id"], session_id=active.id,
        score=payload.score, state=payload.state,
        fatigue=payload.fatigue, gaze=payload.gaze, blinks=payload.blinks,
    )
    db.add(rec); db.commit()

    student = db.query(User).get(user["user_id"])
    _live[user["user_id"]] = {
        "name": student.name, "email": student.email,
        "score": payload.score, "state": payload.state,
        "fatigue": payload.fatigue, "gaze": payload.gaze,
        "blinks": payload.blinks, "last_seen": time.time(),
    }
    return {"status": "ok"}


@router.get("/class-data/{class_code}", response_model=ClassDataResponse)
def class_data(class_code: str, user=Depends(require_teacher), db: Session = Depends(get_db)):
    cls = db.query(Class).filter_by(class_code=class_code.upper(), teacher_id=user["user_id"]).first()
    if not cls:
        raise HTTPException(404, "Class not found")

    active = db.query(SessionModel).filter(
        SessionModel.class_id == cls.id, SessionModel.ended_at.is_(None)
    ).first()
    if not active:
        raise HTTPException(404, "No active session")

    # Only show students who have sent data in THIS session
    from db.models import AttentionRecord as AR
    student_ids_in_session = {
        r.student_id for r in db.query(AR.student_id).filter_by(session_id=active.id).distinct().all()
    }

    now = time.time()
    entries, online_scores = [], []
    distracted = fatigued = 0

    for sid in student_ids_in_session:
        student = db.query(User).get(sid)
        if not student:
            continue
        cached = _live.get(sid)
        online = cached and (now - cached["last_seen"]) <= ONLINE_SECS

        if online:
            online_scores.append(cached["score"])
            if cached["state"] == "DISTRACTED": distracted += 1
            if cached["fatigue"] >= 60:         fatigued  += 1

        entries.append(StudentLiveEntry(
            student_id=student.id,
            name=student.name,
            email=student.email,
            score=cached["score"]     if cached else 0.0,
            state=cached["state"]     if cached else "FOCUSED",
            fatigue=cached["fatigue"] if cached else 0.0,
            gaze=cached["gaze"]       if cached else "CENTER",
            blinks=cached["blinks"]   if cached else 0,
            status="ONLINE" if online else "OFFLINE",
            last_seen=datetime.fromtimestamp(cached["last_seen"]).isoformat() if cached else "",
        ))

    avg = round(sum(online_scores) / len(online_scores), 1) if online_scores else 0.0
    return ClassDataResponse(
        class_name=cls.name, students=entries,
        avg_score=avg, distracted_count=distracted,
        fatigued_count=fatigued, total_online=len(online_scores),
    )
