from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Enterprise AI ATS"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    api_prefix: str = field(default_factory=lambda: os.getenv("API_PREFIX", "/api/v1"))

    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./resume_ai.db"))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "change-me-in-production")))
    jwt_algorithm: str = field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    access_token_minutes: int = field(default_factory=lambda: int(os.getenv("ACCESS_TOKEN_MINUTES", "1440")))
    signup_mode: str = field(default_factory=lambda: os.getenv("SIGNUP_MODE", "access_code").strip().lower())
    paid_signup_access_codes: list[str] = field(default_factory=lambda: _csv(os.getenv("PAID_SIGNUP_ACCESS_CODES"), []))
    checkout_url: str | None = field(default_factory=lambda: os.getenv("CHECKOUT_URL"))
    sales_contact_email: str = field(default_factory=lambda: os.getenv("SALES_CONTACT_EMAIL", "sales@example.com"))
    candidate_tracking_token_days: int = field(default_factory=lambda: int(os.getenv("CANDIDATE_TRACKING_TOKEN_DAYS", "30")))
    allow_legacy_candidate_tracking: bool = field(default_factory=lambda: os.getenv("ALLOW_LEGACY_CANDIDATE_TRACKING", "true").lower() == "true")
    secure_cookies: bool = field(default_factory=lambda: os.getenv("SECURE_COOKIES", "false").lower() == "true")
    csrf_cookie_name: str = field(default_factory=lambda: os.getenv("CSRF_COOKIE_NAME", "ats_csrf"))

    allowed_origins: list[str] = field(
        default_factory=lambda: _csv(
            os.getenv("ALLOWED_ORIGINS"),
            ["http://127.0.0.1:5500", "http://localhost:5173", "http://127.0.0.1:5173"],
        )
    )
    allowed_origin_regex: str | None = field(default_factory=lambda: os.getenv("ALLOWED_ORIGIN_REGEX") or None)

    upload_dir: str = field(default_factory=lambda: os.getenv("UPLOAD_DIR", "uploads"))
    max_upload_mb: float = field(default_factory=lambda: float(os.getenv("MAX_UPLOAD_MB", "20")))
    max_resume_size_mb: float | None = field(default_factory=lambda: float(os.getenv("MAX_RESUME_SIZE_MB")) if os.getenv("MAX_RESUME_SIZE_MB") else None)
    storage_backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local").strip().lower())
    supabase_url: str | None = field(default_factory=lambda: os.getenv("SUPABASE_URL"))
    supabase_service_role_key: str | None = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    supabase_storage_bucket: str = field(default_factory=lambda: os.getenv("SUPABASE_STORAGE_BUCKET", "resumes"))
    supabase_delete_local_after_upload: bool = field(default_factory=lambda: os.getenv("SUPABASE_DELETE_LOCAL_AFTER_UPLOAD", "true").lower() == "true")
    r2_endpoint_url: str | None = field(default_factory=lambda: os.getenv("R2_ENDPOINT_URL"))
    r2_access_key_id: str | None = field(default_factory=lambda: os.getenv("R2_ACCESS_KEY_ID"))
    r2_secret_access_key: str | None = field(default_factory=lambda: os.getenv("R2_SECRET_ACCESS_KEY"))
    r2_bucket: str = field(default_factory=lambda: os.getenv("R2_BUCKET", "resumes"))
    r2_public_base_url: str | None = field(default_factory=lambda: os.getenv("R2_PUBLIC_BASE_URL"))
    r2_delete_local_after_upload: bool = field(default_factory=lambda: os.getenv("R2_DELETE_LOCAL_AFTER_UPLOAD", "true").lower() == "true")
    storage_provider: str = field(default_factory=lambda: os.getenv("STORAGE_PROVIDER", os.getenv("STORAGE_BACKEND", "local")).strip().lower())
    blob_store_id: str | None = field(default_factory=lambda: os.getenv("BLOB_STORE_ID"))
    blob_read_write_token: str | None = field(default_factory=lambda: os.getenv("BLOB_READ_WRITE_TOKEN"))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "600")))
    sentry_dsn: str | None = field(default_factory=lambda: os.getenv("SENTRY_DSN"))

    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    frontend_url: str = field(default_factory=lambda: os.getenv("FRONTEND_URL", "http://127.0.0.1:5500"))
    frontend_signup_path: str = field(default_factory=lambda: os.getenv("FRONTEND_SIGNUP_PATH", "Signup.html"))
    frontend_login_path: str = field(default_factory=lambda: os.getenv("FRONTEND_LOGIN_PATH", "login.html"))
    frontend_pricing_path: str = field(default_factory=lambda: os.getenv("FRONTEND_PRICING_PATH", "pricing.html"))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def upload_bytes_limit(self) -> int:
        limit_mb = self.max_resume_size_mb or self.max_upload_mb
        return int(limit_mb * 1024 * 1024)

    @property
    def resume_upload_limit_mb(self) -> float:
        return self.max_resume_size_mb or self.max_upload_mb

    @property
    def use_supabase_storage(self) -> bool:
        return (
            self.storage_backend == "supabase"
            and bool(self.supabase_url)
            and bool(self.supabase_service_role_key)
            and bool(self.supabase_storage_bucket)
        )

    @property
    def use_r2_storage(self) -> bool:
        return (
            self.storage_backend == "r2"
            and bool(self.r2_endpoint_url)
            and bool(self.r2_access_key_id)
            and bool(self.r2_secret_access_key)
            and bool(self.r2_bucket)
        )

    @property
    def use_vercel_blob_storage(self) -> bool:
        provider = self.storage_provider or self.storage_backend
        return provider == "vercel_blob" or self.storage_backend == "vercel_blob"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    return Settings()
