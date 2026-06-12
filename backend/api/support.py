from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Body, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from backend.core.config import get_settings
from backend.core.security import bearer_token, decode_token
from backend.database import SessionLocal
from backend.models import SupportCase, User
from backend.services.support_email import send_support_case_email


router = APIRouter(prefix="/support", tags=["support"])
logger = logging.getLogger(__name__)

ISSUE_TYPES = {
    "Account/Login Issue",
    "Job Creation Issue",
    "Resume Upload Issue",
    "Candidate Scoring Issue",
    "Dashboard/Data Issue",
    "Billing/Pricing",
    "Feature Request",
    "Other",
}
PRIORITIES = {"Low", "Medium", "High", "Urgent"}

_SUPPORT_RATE_LIMIT: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_WINDOW_SECONDS = 600
_RATE_LIMIT_MAX_REQUESTS = 5


class SupportCaseRequest(BaseModel):
    full_name: str
    email: str
    company_name: str | None = None
    issue_type: str
    priority: str
    subject: str
    message: str

    @field_validator("full_name", "email", "issue_type", "priority", "subject", "message")
    @classmethod
    def required_text(cls, value):
        if not str(value or "").strip():
            raise ValueError("This field is required")
        return str(value).strip()

    @field_validator("company_name")
    @classmethod
    def clean_optional_text(cls, value):
        return str(value).strip() if value else None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("Valid email is required")
        return value.lower()

    @field_validator("issue_type")
    @classmethod
    def valid_issue_type(cls, value):
        if value not in ISSUE_TYPES:
            raise ValueError("Unsupported issue type")
        return value

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value):
        if value not in PRIORITIES:
            raise ValueError("Unsupported priority")
        return value


def _rate_limit_key(request: Request, payload: SupportCaseRequest) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    client_host = forwarded_for or (request.client.host if request.client else "unknown")
    return f"{client_host}:{payload.email.lower()}"


def _check_rate_limit(request: Request, payload: SupportCaseRequest) -> None:
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    key = _rate_limit_key(request, payload)
    with _RATE_LIMIT_LOCK:
        recent = [stamp for stamp in _SUPPORT_RATE_LIMIT.get(key, []) if stamp >= cutoff]
        if len(recent) >= _RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many support requests. Please try again later.")
        recent.append(now)
        _SUPPORT_RATE_LIMIT[key] = recent


def _optional_current_user(request: Request) -> User | None:
    token = bearer_token(request)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except HTTPException:
        return None

    user_id = payload.get("user_id") or payload.get("sub")
    user_email = payload.get("email")
    db = SessionLocal()
    try:
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        elif user_email:
            user = db.query(User).filter(User.email == user_email).first()
        else:
            user = None
        if user:
            request.state.user_email = user.email
            request.state.user_id = user.id
        return user
    finally:
        db.close()


def _store_support_case(payload: SupportCaseRequest, user: User | None) -> SupportCase:
    db = SessionLocal()
    try:
        support_case = SupportCase(
            user_id=user.id if user else None,
            full_name=payload.full_name,
            email=payload.email,
            company_name=payload.company_name,
            issue_type=payload.issue_type,
            priority=payload.priority,
            subject=payload.subject,
            message=payload.message,
            status="open",
        )
        db.add(support_case)
        db.commit()
        db.refresh(support_case)
        return support_case
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_support_email_failed(case_id: str) -> None:
    db = SessionLocal()
    try:
        support_case = db.query(SupportCase).filter(SupportCase.id == case_id).first()
        if support_case:
            support_case.status = "email_failed"
            support_case.updated_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to mark support case email failure: case_id=%s", case_id)
    finally:
        db.close()


@router.post("/case")
def create_support_case(request: Request, payload: SupportCaseRequest = Body(...)):
    _check_rate_limit(request, payload)
    current_user = _optional_current_user(request)
    submitted_at = datetime.now(UTC).isoformat()
    support_case = _store_support_case(payload, current_user)

    email_payload = {
        **payload.model_dump(),
        "case_id": support_case.id,
        "logged_in_user_email": current_user.email if current_user else None,
        "logged_in_user_id": current_user.id if current_user else None,
        "submitted_at": submitted_at,
        "environment": get_settings().environment,
    }

    try:
        send_support_case_email(email_payload)
    except Exception:
        logger.exception("Support case email failed: case_id=%s issue_type=%s priority=%s", support_case.id, payload.issue_type, payload.priority)
        _mark_support_email_failed(support_case.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to submit support case right now. Please try again.",
        )

    return {
        "message": "Support case submitted successfully.",
        "case_id": support_case.id,
    }
