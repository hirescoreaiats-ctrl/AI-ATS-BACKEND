from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from backend.core.metrics import prometheus_text
from backend.core.config import get_settings
from backend.database import SessionLocal

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check():
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@router.get("/ready")
def readiness_check():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    finally:
        db.close()
    return {"status": "ready", "database": database}


@router.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return prometheus_text()
