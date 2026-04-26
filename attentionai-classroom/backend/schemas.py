from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name:     str      = Field(..., min_length=1, max_length=100)
    email:    EmailStr
    password: str      = Field(..., min_length=6)
    role:     Literal["teacher", "student"]
    # teachers only
    subject:  Optional[str] = Field(None, max_length=100)

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    role:         str
    user_id:      int
    name:         str

# ── Classes ───────────────────────────────────────────────────────────────────
class ClassCreateRequest(BaseModel):
    name:    str = Field(..., min_length=1, max_length=100)
    subject: str = Field(..., min_length=1, max_length=100)

class ClassResponse(BaseModel):
    id:                 int
    name:               str
    subject:            str
    class_code:         str
    teacher_name:       str
    has_active_session: bool
    student_count:      int

# ── Enrollment ────────────────────────────────────────────────────────────────
class JoinClassRequest(BaseModel):
    class_code: str = Field(..., min_length=6, max_length=6)

class EnrollmentResponse(BaseModel):
    class_id:   int
    class_name: str
    subject:    str
    class_code: str
    teacher:    str

# ── Sessions ──────────────────────────────────────────────────────────────────
class SessionResponse(BaseModel):
    id:         int
    class_id:   int
    started_at: str
    ended_at:   Optional[str] = None

# ── CV data ───────────────────────────────────────────────────────────────────
class AttentionRecordRequest(BaseModel):
    class_code: str
    score:      float = Field(..., ge=0, le=100)
    state:      Literal["FOCUSED", "LOW FOCUS", "DISTRACTED", "FATIGUED"]
    fatigue:    float = Field(..., ge=0, le=100)
    gaze:       Literal["LEFT", "CENTER", "RIGHT", "DOWN"]
    blinks:     int   = Field(..., ge=0)

# ── Live dashboard ────────────────────────────────────────────────────────────
class StudentLiveEntry(BaseModel):
    student_id: int
    name:       str
    email:      str
    score:      float
    state:      str
    fatigue:    float
    gaze:       str
    blinks:     int
    status:     Literal["ONLINE", "OFFLINE"]
    last_seen:  str

class ClassDataResponse(BaseModel):
    class_name:       str
    students:         list[StudentLiveEntry]
    avg_score:        float
    distracted_count: int
    fatigued_count:   int
    total_online:     int

# ── Reports ───────────────────────────────────────────────────────────────────
class SessionHistoryEntry(BaseModel):
    session_id:         int
    date:               str
    duration_seconds:   int
    avg_score:          float
    distraction_events: int

class StudentSummaryEntry(BaseModel):
    student_id:       int
    name:             str
    email:            str
    attendance_count: int
    avg_score:        float
    trend:            Literal["IMPROVING", "DECLINING", "STABLE"]

class MyClassHistoryEntry(BaseModel):
    session_id:       int
    class_name:       str
    date:             str
    duration_seconds: int
    avg_score:        float
