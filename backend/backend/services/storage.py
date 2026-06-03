from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote

import requests

from backend.core.config import get_settings
from backend.utils.upload_security import safe_upload_name


SUPABASE_URI_PREFIX = "supabase://"


def is_supabase_uri(value: str | None) -> bool:
    return bool(value and value.startswith(SUPABASE_URI_PREFIX))


def _supabase_object_base_url(bucket: str, object_path: str) -> str:
    settings = get_settings()
    base_url = (settings.supabase_url or "").rstrip("/")
    quoted_path = "/".join(quote(part, safe="") for part in object_path.split("/"))
    return f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quoted_path}"


def _supabase_headers(content_type: str | None = None) -> dict[str, str]:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _parse_supabase_uri(uri: str) -> tuple[str, str]:
    raw = uri.removeprefix(SUPABASE_URI_PREFIX)
    bucket, _, object_path = raw.partition("/")
    if not bucket or not object_path:
        raise ValueError("Invalid Supabase storage URI")
    return bucket, object_path


def supabase_uri(bucket: str, object_path: str) -> str:
    return f"{SUPABASE_URI_PREFIX}{bucket}/{object_path}"


def persist_resume_file(local_path: str, original_filename: str | None, content_type: str | None, job_id: str | None = None) -> str:
    settings = get_settings()
    if not settings.use_supabase_storage:
        return local_path

    safe_name = safe_upload_name(original_filename or Path(local_path).name)
    object_path = f"resumes/{job_id or 'unassigned'}/{uuid.uuid4()}_{safe_name}"
    bucket = settings.supabase_storage_bucket

    with open(local_path, "rb") as file_handle:
        response = requests.post(
            _supabase_object_base_url(bucket, object_path),
            headers={
                **_supabase_headers(content_type or "application/octet-stream"),
                "x-upsert": "false",
            },
            data=file_handle,
            timeout=60,
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage upload failed: {response.status_code} {response.text[:300]}")

    if settings.supabase_delete_local_after_upload:
        try:
            os.remove(local_path)
        except OSError:
            pass

    return supabase_uri(bucket, object_path)


def download_supabase_file(uri: str) -> bytes:
    bucket, object_path = _parse_supabase_uri(uri)
    response = requests.get(
        _supabase_object_base_url(bucket, object_path),
        headers=_supabase_headers(),
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage download failed: {response.status_code} {response.text[:300]}")
    return response.content


def materialize_resume_file(stored_path: str, original_filename: str | None = None) -> tuple[str, bool]:
    if not is_supabase_uri(stored_path):
        return stored_path, False

    suffix = Path(original_filename or stored_path).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(download_supabase_file(stored_path))
        return temp_file.name, True
