from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote

import requests

from backend.core.config import get_settings
from backend.services.storage_service import download_vercel_blob_file, is_vercel_blob_uri
from backend.utils.upload_security import safe_upload_name


SUPABASE_URI_PREFIX = "supabase://"
R2_URI_PREFIX = "r2://"


def is_supabase_uri(value: str | None) -> bool:
    return bool(value and value.startswith(SUPABASE_URI_PREFIX))


def is_r2_uri(value: str | None) -> bool:
    return bool(value and value.startswith(R2_URI_PREFIX))


def is_remote_storage_uri(value: str | None) -> bool:
    return is_supabase_uri(value) or is_r2_uri(value) or is_vercel_blob_uri(value)


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


def r2_uri(bucket: str, object_path: str) -> str:
    return f"{R2_URI_PREFIX}{bucket}/{object_path}"


def _parse_r2_uri(uri: str) -> tuple[str, str]:
    raw = uri.removeprefix(R2_URI_PREFIX)
    bucket, _, object_path = raw.partition("/")
    if not bucket or not object_path:
        raise ValueError("Invalid R2 storage URI")
    return bucket, object_path


def _r2_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("R2 storage requires boto3. Install requirements.txt before using STORAGE_BACKEND=r2.") from exc

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def _persist_to_r2(local_path: str, original_filename: str | None, content_type: str | None, job_id: str | None = None) -> str:
    settings = get_settings()
    safe_name = safe_upload_name(original_filename or Path(local_path).name)
    object_path = f"resumes/{job_id or 'unassigned'}/{uuid.uuid4()}_{safe_name}"
    bucket = settings.r2_bucket

    extra_args = {"ContentType": content_type or "application/octet-stream"}
    _r2_client().upload_file(local_path, bucket, object_path, ExtraArgs=extra_args)

    if settings.r2_delete_local_after_upload:
        try:
            os.remove(local_path)
        except OSError:
            pass

    return r2_uri(bucket, object_path)


def persist_resume_file(local_path: str, original_filename: str | None, content_type: str | None, job_id: str | None = None) -> str:
    settings = get_settings()
    if settings.use_vercel_blob_storage:
        from backend.services.storage_service import upload_resume_file

        resume_id = Path(local_path).stem.split("_", 1)[0] or str(uuid.uuid4())
        stored = upload_resume_file(
            Path(local_path).read_bytes(),
            original_filename or Path(local_path).name,
            job_id or "unassigned",
            resume_id,
            mime_type=content_type,
        )
        try:
            os.remove(local_path)
        except OSError:
            pass
        return stored.storage_uri

    if settings.use_r2_storage:
        return _persist_to_r2(local_path, original_filename, content_type, job_id)

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


def download_r2_file(uri: str) -> bytes:
    bucket, object_path = _parse_r2_uri(uri)
    response = _r2_client().get_object(Bucket=bucket, Key=object_path)
    return response["Body"].read()


def download_stored_file(uri: str) -> bytes:
    if is_supabase_uri(uri):
        return download_supabase_file(uri)
    if is_r2_uri(uri):
        return download_r2_file(uri)
    if is_vercel_blob_uri(uri):
        return download_vercel_blob_file(uri)
    return Path(uri).read_bytes()


def materialize_resume_file(stored_path: str, original_filename: str | None = None) -> tuple[str, bool]:
    if not is_remote_storage_uri(stored_path):
        return stored_path, False

    suffix = Path(original_filename or stored_path).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(download_stored_file(stored_path))
        return temp_file.name, True
