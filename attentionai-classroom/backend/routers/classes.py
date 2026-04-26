from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.jwt import get_current_user, require_teacher, require_student
from db.database import generate_class_code, get_db
from db.models import Class, Enrollment, Session as SessionModel, User
from schemas import ClassCreateRequest, ClassResponse, EnrollmentResponse, JoinClassRequest, SessionResponse

router = APIRouter(tags=["classes"])

# ── Schema alias: frontend uses "name" only (no subject required for batches) ──
from pydantic import BaseModel as _BM
class _BatchCreateRequest(_BM):
    name: str


def _has_active(db, class_id):
    return db.query(SessionModel).filter(
        SessionModel.class_id == class_id,
        SessionModel.ended_at.is_(None)
    ).first() is not None


# ── Teacher: create class ──
@router.post("/classes", response_model=ClassResponse, status_code=201)
def create_class(payload: ClassCreateRequest, user=Depends(require_teacher), db: Session = Depends(get_db)):
    code = generate_class_code(db)
    cls = Class(teacher_id=user["user_id"], name=payload.name, subject=payload.subject, class_code=code)
    db.add(cls)
    db.commit()
    db.refresh(cls)
    teacher = db.query(User).get(user["user_id"])
    return ClassResponse(id=cls.id, name=cls.name, subject=cls.subject, class_code=cls.class_code,
                         teacher_name=teacher.name, has_active_session=False, student_count=0)


# ── Teacher: list own classes ──
@router.get("/classes/mine", response_model=list[ClassResponse])
def my_classes_teacher(user=Depends(require_teacher), db: Session = Depends(get_db)):
    classes = db.query(Class).filter_by(teacher_id=user["user_id"]).all()
    teacher = db.query(User).get(user["user_id"])
    return [ClassResponse(
        id=c.id, name=c.name, subject=c.subject, class_code=c.class_code,
        teacher_name=teacher.name,
        has_active_session=_has_active(db, c.id),
        student_count=db.query(Enrollment).filter_by(class_id=c.id).count()
    ) for c in classes]


# ── Student: join class by code ──
@router.post("/classes/join", response_model=EnrollmentResponse, status_code=201)
def join_class(payload: JoinClassRequest, user=Depends(require_student), db: Session = Depends(get_db)):
    cls = db.query(Class).filter_by(class_code=payload.class_code.upper()).first()
    if not cls:
        raise HTTPException(404, "Class code not found")
    existing = db.query(Enrollment).filter_by(student_id=user["user_id"], class_id=cls.id).first()
    if existing:
        raise HTTPException(409, "Already enrolled in this class")
    enroll = Enrollment(student_id=user["user_id"], class_id=cls.id)
    db.add(enroll)
    db.commit()
    teacher = db.query(User).get(cls.teacher_id)
    return EnrollmentResponse(class_id=cls.id, class_name=cls.name, subject=cls.subject,
                               class_code=cls.class_code, teacher=teacher.name)


# ── Student: list enrolled classes ──
@router.get("/classes/enrolled", response_model=list[ClassResponse])
def enrolled_classes(user=Depends(require_student), db: Session = Depends(get_db)):
    enrollments = db.query(Enrollment).filter_by(student_id=user["user_id"]).all()
    result = []
    for e in enrollments:
        cls = db.query(Class).get(e.class_id)
        teacher = db.query(User).get(cls.teacher_id)
        result.append(ClassResponse(
            id=cls.id, name=cls.name, subject=cls.subject, class_code=cls.class_code,
            teacher_name=teacher.name,
            has_active_session=_has_active(db, cls.id),
            student_count=db.query(Enrollment).filter_by(class_id=cls.id).count()
        ))
    return result


# ── Teacher: start session ──
@router.post("/classes/{class_id}/sessions/start", response_model=SessionResponse, status_code=201)
def start_session(class_id: int, user=Depends(require_teacher), db: Session = Depends(get_db)):
    cls = db.query(Class).filter_by(id=class_id, teacher_id=user["user_id"]).first()
    if not cls:
        raise HTTPException(404, "Class not found")
    if _has_active(db, class_id):
        raise HTTPException(409, "Session already active")
    s = SessionModel(class_id=class_id)
    db.add(s); db.commit(); db.refresh(s)
    return SessionResponse(id=s.id, class_id=s.class_id, started_at=s.started_at, ended_at=s.ended_at)


# ── Teacher: end session ──
@router.post("/classes/{class_id}/sessions/end", response_model=SessionResponse)
def end_session(class_id: int, user=Depends(require_teacher), db: Session = Depends(get_db)):
    cls = db.query(Class).filter_by(id=class_id, teacher_id=user["user_id"]).first()
    if not cls:
        raise HTTPException(404, "Class not found")
    s = db.query(SessionModel).filter(SessionModel.class_id == class_id, SessionModel.ended_at.is_(None)).first()
    if not s:
        raise HTTPException(404, "No active session")
    from datetime import datetime, timezone
    s.ended_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    db.commit(); db.refresh(s)
    return SessionResponse(id=s.id, class_id=s.class_id, started_at=s.started_at, ended_at=s.ended_at)


# ── /batches aliases (frontend compatibility) ──────────────────────────────────

@router.post("/batches", response_model=ClassResponse, status_code=201)
def create_batch(payload: _BatchCreateRequest, user=Depends(require_teacher), db: Session = Depends(get_db)):
    """Alias for POST /classes — frontend uses /batches."""
    code = generate_class_code(db)
    cls = Class(teacher_id=user["user_id"], name=payload.name,
                subject="General", class_code=code)
    db.add(cls); db.commit(); db.refresh(cls)
    teacher = db.query(User).get(user["user_id"])
    return ClassResponse(id=cls.id, name=cls.name, subject=cls.subject,
                         class_code=cls.class_code, teacher_name=teacher.name,
                         has_active_session=False, student_count=0)


@router.get("/batches", response_model=list[ClassResponse])
def list_batches(user=Depends(require_teacher), db: Session = Depends(get_db)):
    """Alias for GET /classes/mine."""
    classes = db.query(Class).filter_by(teacher_id=user["user_id"]).all()
    teacher = db.query(User).get(user["user_id"])
    return [ClassResponse(
        id=c.id, name=c.name, subject=c.subject, class_code=c.class_code,
        teacher_name=teacher.name,
        has_active_session=_has_active(db, c.id),
        student_count=db.query(Enrollment).filter_by(class_id=c.id).count()
    ) for c in classes]


@router.post("/batches/{batch_id}/sessions/start", response_model=SessionResponse, status_code=201)
def start_session_batch(batch_id: int, user=Depends(require_teacher), db: Session = Depends(get_db)):
    """Alias for POST /classes/{id}/sessions/start."""
    return start_session(batch_id, user, db)


@router.post("/batches/{batch_id}/sessions/end", response_model=SessionResponse)
def end_session_batch(batch_id: int, user=Depends(require_teacher), db: Session = Depends(get_db)):
    """Alias for POST /classes/{id}/sessions/end."""
    return end_session(batch_id, user, db)
