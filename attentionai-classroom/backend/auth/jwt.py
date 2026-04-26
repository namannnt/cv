import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM  = "HS256"
EXPIRE_H   = 24

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()


def _truncate(plain: str) -> str:
    """bcrypt silently truncates at 72 bytes; passlib raises on >72 — truncate explicitly."""
    return plain.encode("utf-8")[:72].decode("utf-8", errors="ignore")

def hash_password(plain: str) -> str:
    return _pwd.hash(_truncate(plain))

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(_truncate(plain), hashed)

def create_token(user_id: int, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=EXPIRE_H)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Not authenticated")

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Returns {"user_id": int, "role": str}"""
    payload = _decode(creds.credentials)
    return {"user_id": int(payload["sub"]), "role": payload["role"]}

def require_teacher(user=Depends(get_current_user)) -> dict:
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required")
    return user

def require_student(user=Depends(get_current_user)) -> dict:
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    return user
