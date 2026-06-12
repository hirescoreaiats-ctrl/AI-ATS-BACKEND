from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from jwt.utils import base64url_decode, base64url_encode

from backend.core.config import get_settings
from backend.database import get_db
from backend.models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


def create_access_token(payload: dict, minutes: int | None = None) -> str:
    settings = get_settings()
    expiry = datetime.utcnow() + timedelta(minutes=minutes or settings.access_token_minutes)
    token_payload = {**payload, "exp": expiry}
    return jwt.encode(token_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_candidate_tracking_token(candidate_id: str, job_id: str | None = None, days: int | None = None) -> str:
    settings = get_settings()
    expiry = datetime.utcnow() + timedelta(days=days or settings.candidate_tracking_token_days)
    token_payload = {
        "purpose": "candidate_tracking",
        "candidate_id": candidate_id,
        "job_id": job_id,
        "exp": expiry,
    }
    return jwt.encode(token_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise jwt.InvalidTokenError("Invalid token format")
        for part in parts:
            if base64url_encode(base64url_decode(part.encode())).decode() != part:
                raise jwt.InvalidTokenError("Non-canonical token encoding")
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def decode_candidate_tracking_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("purpose") != "candidate_tracking" or not payload.get("candidate_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid candidate tracking token")
    return payload


def bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.cookies.get("ats_access_token")


def get_current_user(request: Request, db=Depends(get_db)) -> User:
    token = bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    payload = decode_token(token)
    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    request.state.user_email = user.email
    request.state.user_id = user.id
    return user


def require_roles(*roles: str):
    allowed = set(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        role = getattr(user, "role", None) or "recruiter"
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission")
        return user

    return dependency


def validate_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie_value = request.cookies.get(get_settings().csrf_cookie_name)
    if cookie_value and x_csrf_token and cookie_value == x_csrf_token:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
