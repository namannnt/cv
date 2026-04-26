import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Batch, Student
from schemas import StudentJoinRequest, StudentJoinResponse

router = APIRouter(prefix="/students", tags=["students"])


@router.post("/join", response_model=StudentJoinResponse)
def join(payload: StudentJoinRequest, db: Session = Depends(get_db)):
    batch = db.query(Batch).filter(Batch.class_code == payload.class_code).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class code not found")

    student = (
        db.query(Student)
        .filter(Student.batch_id == batch.id, Student.name == payload.name)
        .first()
    )
    if not student:
        student = Student(
            batch_id=batch.id,
            name=payload.name,
            session_token=str(uuid.uuid4()),
        )
        db.add(student)
        db.commit()
        db.refresh(student)

    return StudentJoinResponse(
        student_id=student.id,
        session_token=student.session_token,
        batch_name=batch.name,
    )
