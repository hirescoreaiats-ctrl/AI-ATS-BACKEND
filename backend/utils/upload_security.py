from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from backend.core.config import get_settings


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "application/octet-stream",
}


def safe_upload_name(original_name: str) -> str:
    suffix = Path(original_name or "").suffix.lower()
    clean_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(original_name or "resume").stem)[:80]
    return f"{uuid.uuid4()}_{clean_stem}{suffix}"


def validate_upload(file: UploadFile, size_bytes: int) -> None:
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOC, DOCX, and TXT resumes are allowed",
        )
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported upload MIME type: {file.content_type}",
        )
    if size_bytes > settings.upload_bytes_limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Resume exceeds {settings.resume_upload_limit_mb}MB limit",
        )


def validate_upload_metadata(file_name: str, content_type: str | None, size_bytes: int) -> None:
    class UploadMetadata:
        filename = file_name
        content_type = content_type

    validate_upload(UploadMetadata(), size_bytes)


def malware_scan(file_path: str) -> None:
    scanner = shutil.which("clamscan")
    if not scanner:
        return
    result = subprocess.run([scanner, "--no-summary", file_path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload failed malware validation",
        )


def secure_upload_path(original_name: str) -> str:
    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    return os.path.join(settings.upload_dir, safe_upload_name(original_name))
