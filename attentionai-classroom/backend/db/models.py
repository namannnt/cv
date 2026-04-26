from sqlalchemy import Column, Integer, Text, Float, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Single users table for both teachers and students."""
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(Text, nullable=False)
    email         = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role          = Column(Text, nullable=False)   # "teacher" | "student"
    created_at    = Column(Text, nullable=False, server_default="(datetime('now'))")

    # teacher side
    classes     = relationship("Class", back_populates="teacher", foreign_keys="Class.teacher_id")
    # student side
    enrollments = relationship("Enrollment", back_populates="student")
    attention_records = relationship("AttentionRecord", back_populates="student")


class Class(Base):
    """A class created by a teacher. Students join via class_code."""
    __tablename__ = "classes"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name       = Column(Text, nullable=False)          # e.g. "Physics 101"
    subject    = Column(Text, nullable=False)          # e.g. "Physics"
    class_code = Column(Text, nullable=False, unique=True)  # 6-char
    created_at = Column(Text, nullable=False, server_default="(datetime('now'))")

    teacher     = relationship("User", back_populates="classes", foreign_keys=[teacher_id])
    enrollments = relationship("Enrollment", back_populates="cls")
    sessions    = relationship("Session", back_populates="cls")


class Enrollment(Base):
    """Many-to-many: students ↔ classes."""
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "class_id"),)

    id         = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    class_id   = Column(Integer, ForeignKey("classes.id"), nullable=False)
    joined_at  = Column(Text, nullable=False, server_default="(datetime('now'))")

    student = relationship("User", back_populates="enrollments")
    cls     = relationship("Class", back_populates="enrollments")


class Session(Base):
    """A live monitoring session started by a teacher for a class."""
    __tablename__ = "sessions"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    class_id   = Column(Integer, ForeignKey("classes.id"), nullable=False)
    started_at = Column(Text, nullable=False, server_default="(datetime('now'))")
    ended_at   = Column(Text, nullable=True)

    cls               = relationship("Class", back_populates="sessions")
    attention_records = relationship("AttentionRecord", back_populates="session")


class AttentionRecord(Base):
    """One data point per second from the CV engine."""
    __tablename__ = "attention_records"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100",   name="ck_score"),
        CheckConstraint("fatigue >= 0 AND fatigue <= 100", name="ck_fatigue"),
        CheckConstraint("state IN ('FOCUSED','LOW FOCUS','DISTRACTED','FATIGUED')", name="ck_state"),
        CheckConstraint("gaze IN ('LEFT','CENTER','RIGHT','DOWN')", name="ck_gaze"),
        CheckConstraint("blinks >= 0", name="ck_blinks"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    student_id  = Column(Integer, ForeignKey("users.id"),    nullable=False)
    session_id  = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    score       = Column(Float,   nullable=False)
    state       = Column(Text,    nullable=False)
    fatigue     = Column(Float,   nullable=False)
    gaze        = Column(Text,    nullable=False)
    blinks      = Column(Integer, nullable=False)
    recorded_at = Column(Text,    nullable=False, server_default="(datetime('now'))")

    student = relationship("User",    back_populates="attention_records")
    session = relationship("Session", back_populates="attention_records")
