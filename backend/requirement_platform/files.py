from __future__ import annotations

import hashlib
import hmac
import os
import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile

from backend.core.config import get_settings
from backend.services.storage import persist_resume_file
from backend.utils.upload_security import malware_scan, secure_upload_path, validate_upload_metadata


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[-15:]


def fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    return hmac.new(get_settings().jwt_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def candidate_fingerprint(full_name: str, email: str | None, phone: str | None) -> str:
    canonical = "|".join([normalize_email(email), normalize_phone(phone), " ".join(full_name.lower().split())])
    return fingerprint(canonical) or ""


def validate_file_signature(path: str, original_name: str) -> None:
    suffix = Path(original_name).suffix.lower()
    data = Path(path).read_bytes()[:16]
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="Uploaded file is not a valid PDF")
    if suffix == ".doc" and not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise HTTPException(status_code=415, detail="Uploaded file is not a valid DOC")
    if suffix == ".docx":
        try:
            with ZipFile(path) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or not any(name.startswith("word/") for name in names):
                    raise HTTPException(status_code=415, detail="Uploaded file is not a valid DOCX")
        except BadZipFile as exc:
            raise HTTPException(status_code=415, detail="Uploaded file is not a valid DOCX") from exc


async def store_candidate_resume(file: UploadFile, requirement_id: str) -> dict:
    content = await file.read()
    validate_upload_metadata(file.filename or "", file.content_type, len(content))
    local_path = secure_upload_path(file.filename or "resume")
    try:
        with open(local_path, "xb") as output:
            output.write(content)
        validate_file_signature(local_path, file.filename or "")
        malware_scan(local_path)
        digest = hashlib.sha256(content).hexdigest()
        storage_key = persist_resume_file(local_path, file.filename, file.content_type, job_id=f"rp-{requirement_id}")
        return {
            "storage_key": storage_key,
            "original_filename": Path(file.filename or "resume").name[:255],
            "mime_type": file.content_type,
            "size": len(content),
            "sha256": digest,
        }
    except Exception:
        try:
            os.remove(local_path)
        except OSError:
            pass
        raise
