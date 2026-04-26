from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth.jwt import get_current_teacher
from db.database import generate_class_code, get_db
from db.models import Batch, SessionModel
from schemas import BatchCreateRequest, BatchResponse, SessionResponse

router = APIRouter(prefix="/batches", tags=["batches"])


def _has_active_session(db: Session, batch_id: int) -> bool:
    return (
        db.query(SessionModel)
        .filter(SessionModel.batch_id == batch_id, SessionModel.ended_at.is_(None))
        .first()
        is not None
    )


@router.post("", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: BatchCreateRequest,
    teacher_id: int = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    code = generate_class_code(db)
    batch = Batch(teacher_id=teacher_id, name=payload.name, class_code=code)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return BatchResponse(
        id=batch.id,
        name=batch.name,
        class_code=batch.class_code,
        has_active_session=False,
    )


@router.get("", response_model=list[BatchResponse])
def list_batches(
    teacher_id: int = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    batches = db.query(Batch).filter(Batch.teacher_id == teacher_id).all()
    return [
        BatchResponse(
            id=b.id,
            name=b.name,
            class_code=b.class_code,
            has_active_session=_has_active_session(db, b.id),
        )
        for b in batches
    ]


@router.post("/{batch_id}/sessions/start", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def start_session(
    batch_id: int,
    teacher_id: int = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.teacher_id == teacher_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    if _has_active_session(db, batch_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already active for this batch",
        )

    session = SessionModel(batch_id=batch_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionResponse(
        id=session.id,
        batch_id=session.batch_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


@router.post("/{batch_id}/sessions/end", response_model=SessionResponse)
def end_session(
    batch_id: int,
    teacher_id: int = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.teacher_id == teacher_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    session = (
        db.query(SessionModel)
        .filter(SessionModel.batch_id == batch_id, SessionModel.ended_at.is_(None))
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active session for this batch",
        )

    session.ended_at = datetime.now().isoformat()
    db.commit()
    db.refresh(session)
    return SessionResponse(
        id=session.id,
        batch_id=session.batch_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )
