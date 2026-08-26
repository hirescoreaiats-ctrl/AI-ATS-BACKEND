from __future__ import annotations

import html
import logging
import threading
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Body, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from backend.core.config import get_settings
from backend.services.transactional_email import send_transactional_email


router = APIRouter(prefix="/demo", tags=["demo"])
logger = logging.getLogger(__name__)

_DEMO_RATE_LIMIT: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_WINDOW_SECONDS = 600
_RATE_LIMIT_MAX_REQUESTS = 5


class DemoRequest(BaseModel):
    name: str
    workEmail: str
    companyName: str
    hiringVolume: str
    message: str | None = None
    sourcePage: str | None = None

    @field_validator("name", "workEmail", "companyName", "hiringVolume")
    @classmethod
    def required_text(cls, value):
        value = str(value or "").strip()
        if not value:
            raise ValueError("This field is required")
        return value

    @field_validator("workEmail")
    @classmethod
    def valid_email(cls, value):
        value = value.lower()
        if len(value) > 320 or "@" not in value or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("Valid work email is required")
        return value

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if len(value) < 2 or len(value) > 120:
            raise ValueError("Name must be between 2 and 120 characters")
        return value

    @field_validator("companyName")
    @classmethod
    def valid_company(cls, value):
        if len(value) > 200:
            raise ValueError("Company name is too long")
        return value

    @field_validator("hiringVolume")
    @classmethod
    def valid_hiring_volume(cls, value):
        if len(value) > 100:
            raise ValueError("Hiring volume is too long")
        return value

    @field_validator("message")
    @classmethod
    def clean_message(cls, value):
        value = str(value or "").strip()
        return value[:5000] or None

    @field_validator("sourcePage")
    @classmethod
    def clean_source_page(cls, value):
        value = str(value or "").strip()
        if not value:
            return None
        if not value.lower().startswith(("https://", "http://")):
            return None
        return value[:1000]


def _check_rate_limit(request: Request, payload: DemoRequest) -> None:
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    client_host = forwarded_for or (request.client.host if request.client else "unknown")
    key = f"{client_host}:{payload.workEmail}"
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    with _RATE_LIMIT_LOCK:
        recent = [stamp for stamp in _DEMO_RATE_LIMIT.get(key, []) if stamp >= cutoff]
        if len(recent) >= _RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many demo requests. Please try again later.")
        recent.append(now)
        _DEMO_RATE_LIMIT[key] = recent


def _deliver_demo_request(payload: DemoRequest, submitted_at: str) -> dict:
    values = [
        ("Name", payload.name),
        ("Work Email", payload.workEmail),
        ("Company", payload.companyName),
        ("Hiring Volume", payload.hiringVolume),
        ("Message", payload.message or "Not provided"),
        ("Submitted At", submitted_at),
        ("Source Page", payload.sourcePage or "Not available"),
    ]
    text_body = "New HireScoreAI demo request\n\n" + "\n".join(f"{label}: {value}" for label, value in values)
    rows = "".join(
        f'<tr><th style="text-align:left;padding:8px;border:1px solid #ddd;vertical-align:top">{html.escape(label)}</th>'
        f'<td style="padding:8px;border:1px solid #ddd;white-space:pre-wrap">{html.escape(str(value))}</td></tr>'
        for label, value in values
    )
    settings = get_settings()
    return send_transactional_email(
        to_email=settings.demo_request_to_email,
        to_name="HireScoreAI Demo Requests",
        subject=f"New HireScoreAI Demo Request — {payload.companyName}",
        text_body=text_body,
        html_body=f'<h1>New HireScoreAI Demo Request</h1><table style="border-collapse:collapse">{rows}</table>',
    )


@router.post("/request")
def create_demo_request(request: Request, payload: DemoRequest = Body(...)):
    _check_rate_limit(request, payload)
    submitted_at = datetime.now(UTC).isoformat()
    if not payload.sourcePage:
        referer = str(request.headers.get("referer") or "").strip()
        if referer.lower().startswith(("https://", "http://")):
            payload.sourcePage = referer[:1000]
    try:
        delivery = _deliver_demo_request(payload, submitted_at)
    except Exception:
        logger.exception("Demo request email delivery failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to send your demo request right now. Please try again.")
    return {
        "message": "Demo request submitted successfully.",
        "status": "sent",
        "submitted_at": submitted_at,
        "provider": delivery.get("provider"),
    }
