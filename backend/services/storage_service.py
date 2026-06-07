from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from fastapi import HTTPException, status

from backend.core.config import get_settings


logger = logging.getLogger(__name__)

VERCEL_BLOB_URI_PREFIX = "vercel_blob://"
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx"}


@dataclass
class StoredResumeFile:
    url: str
    key: str
    storage_uri: str
    original_filename: str
    file_size: int
    mime_type: str
    uploaded_at: datetime


def is_vercel_blob_uri(value: str | None) -> bool:
    return bool(value and value.startswith(VERCEL_BLOB_URI_PREFIX))


def _safe_resume_filename(original_filename: str | None) -> str:
    name = Path(original_filename or "resume.pdf").name
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem or "resume"
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")[:90] or "resume"
    return f"{safe_stem}{suffix}"


def _resume_mime_type(filename: str, fallback: str | None = None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".doc":
        return "application/msword"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return fallback or "application/octet-stream"


def _validate_resume_blob(file_bytes: bytes, original_filename: str | None) -> str:
    settings = get_settings()
    safe_filename = _safe_resume_filename(original_filename)
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOC, and DOCX resumes are allowed",
        )

    max_bytes = settings.upload_bytes_limit
    if len(file_bytes or b"") > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Resume exceeds {settings.resume_upload_limit_mb}MB limit",
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Resume file is empty")
    return safe_filename


def _vercel_blob_token() -> str:
    token = get_settings().blob_read_write_token
    if not token:
        raise HTTPException(
            status_code=500,
            detail="Vercel Blob is configured but BLOB_READ_WRITE_TOKEN is missing",
        )
    return token


def _vercel_private_url(pathname: str) -> str | None:
    settings = get_settings()
    if not settings.blob_store_id:
        return None
    quoted_path = "/".join(quote(part, safe="") for part in pathname.split("/"))
    return f"https://{settings.blob_store_id}.private.blob.vercel-storage.com/{quoted_path}"


def vercel_blob_storage_uri(pathname: str) -> str:
    return f"{VERCEL_BLOB_URI_PREFIX}{pathname}"


def upload_resume_file(
    file_bytes: bytes,
    original_filename: str,
    job_id: str,
    resume_id: str,
    organization_id: str = "default_org",
    mime_type: str | None = None,
) -> StoredResumeFile:
    settings = get_settings()
    provider = settings.storage_provider or settings.storage_backend
    if provider != "vercel_blob" and settings.storage_backend != "vercel_blob":
        raise HTTPException(status_code=500, detail="Vercel Blob storage is not enabled")

    safe_filename = _validate_resume_blob(file_bytes, original_filename)
    content_type = mime_type or _resume_mime_type(safe_filename)
    pathname = f"resumes/{organization_id or 'default_org'}/{job_id}/{resume_id}_{safe_filename}"
    os.environ.setdefault("BLOB_READ_WRITE_TOKEN", _vercel_blob_token())

    try:
        from vercel.blob import BlobClient
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Vercel Blob SDK is not installed. Run pip install -r requirements.txt.",
        ) from exc

    try:
        client = BlobClient()
        result = client.put(
            pathname,
            file_bytes,
            access="private",
            content_type=content_type,
            add_random_suffix=False,
            overwrite=False,
        )
    except Exception as exc:
        logger.exception("Vercel Blob resume upload failed for %s", pathname)
        raise HTTPException(status_code=502, detail=f"Vercel Blob upload failed: {exc}") from exc

    url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None) or _vercel_private_url(pathname) or ""
    logger.info("Resume uploaded to Vercel Blob: key=%s size=%s", pathname, len(file_bytes))
    return StoredResumeFile(
        url=url,
        key=pathname,
        storage_uri=vercel_blob_storage_uri(pathname),
        original_filename=original_filename,
        file_size=len(file_bytes),
        mime_type=content_type,
        uploaded_at=datetime.utcnow(),
    )


def download_vercel_blob_file(storage_uri_or_key: str) -> bytes:
    key = storage_uri_or_key.removeprefix(VERCEL_BLOB_URI_PREFIX)
    token = _vercel_blob_token()
    os.environ.setdefault("BLOB_READ_WRITE_TOKEN", token)
    try:
        from vercel.blob import BlobClient

        client = BlobClient()
        result = client.get(key, access="private", timeout=60, use_cache=False)
        content = getattr(result, "content", None)
        if content is None and isinstance(result, dict):
            content = result.get("content")
        if content is None:
            content = bytes(result)
        if content:
            return content
    except Exception:
        logger.exception("Vercel Blob SDK download failed for key=%s; trying signed private URL fallback", key)

    url = _vercel_private_url(key)
    if not url:
        raise RuntimeError("BLOB_STORE_ID is required to download private Vercel Blob files")

    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"Vercel Blob download failed: {response.status_code} {response.text[:300]}")
    return response.content
