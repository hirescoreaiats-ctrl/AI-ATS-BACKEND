from __future__ import annotations

import argparse
import os

from backend.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Vercel Blob storage configuration.")
    parser.add_argument("--upload-smoke-test", action="store_true", help="Upload a tiny DOCX-like test object to Vercel Blob.")
    args = parser.parse_args()

    settings = get_settings()
    print(f"storage_backend={settings.storage_backend}")
    print(f"storage_provider={settings.storage_provider}")
    print(f"use_vercel_blob_storage={settings.use_vercel_blob_storage}")
    print(f"blob_store_id_present={bool(settings.blob_store_id)}")
    print(f"blob_token_present={bool(settings.blob_read_write_token)}")
    print(f"resume_limit_mb={settings.resume_upload_limit_mb}")

    try:
        import vercel.blob  # noqa: F401
        print("vercel_blob_sdk=installed")
    except ImportError:
        print("vercel_blob_sdk=missing")
        return

    if not args.upload_smoke_test:
        print("smoke_upload=skipped")
        return

    from backend.services.storage_service import upload_resume_file

    stored = upload_resume_file(
        b"PK\x03\x04vercel-blob-smoke-test",
        "vercel-blob-smoke-test.docx",
        "verification-job",
        "verification-resume",
        organization_id=os.getenv("VERIFY_ORG_ID", "default_org"),
    )
    print(f"smoke_upload=ok key={stored.key} size={stored.file_size}")


if __name__ == "__main__":
    main()
