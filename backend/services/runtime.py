import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.core.config import get_settings
from backend.database import SessionLocal, db_pool_settings

logger = logging.getLogger(__name__)
START_TIME = time.time()


def git_commit() -> str:
    env_value = os.getenv("GIT_COMMIT") or os.getenv("APP_VERSION")
    if env_value:
        return env_value[:40]
    try:
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return (result.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def database_ready() -> bool:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        db.close()


def runtime_payload(include_database_check: bool = True) -> dict:
    settings = get_settings()
    payload = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "environment": settings.environment,
        "app_version": git_commit(),
        "git_commit": git_commit(),
        "db_pool_settings": db_pool_settings(),
        "uptime": round(time.time() - START_TIME, 2),
        "active_threads": threading.active_count(),
        "port": int(os.getenv("PORT", "8000")),
    }
    if include_database_check:
        payload["database_ready"] = database_ready()
    return payload


def operational_error_type(exc: OperationalError) -> str:
    message = str(exc).lower()
    if "max clients reached" in message or "emaxconnsession" in message:
        return "db_connection_exhausted"
    return "db_operational_error"


def log_startup_runtime() -> None:
    settings = get_settings()
    logger.info(
        "Backend startup runtime: pid=%s ppid=%s environment=%s port=%s app_version=%s db_pool=%s",
        os.getpid(),
        os.getppid(),
        settings.environment,
        os.getenv("PORT", "8000"),
        git_commit(),
        db_pool_settings(),
    )
