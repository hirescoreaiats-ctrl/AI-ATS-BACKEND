import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from backend.api import ai, copilot, debug, enterprise, health, interviews, organizations, realtime, support, talent, uploads
from backend.core.config import get_settings
from backend.core.logging import configure_logging
from backend.database import engine
from backend.middleware.audit import AccessLogMiddleware
from backend.middleware.rate_limit import InMemoryRateLimitMiddleware
from backend.middleware.security_headers import SecurityHeadersMiddleware
from backend.models import Base
from backend.routers import auth, job, resume
from backend.services.runtime import log_startup_runtime, operational_error_type

configure_logging()
settings = get_settings()
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    except Exception:
        pass

app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description="Production-grade AI-native ATS platform with preserved recruiter workflows.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(InMemoryRateLimitMiddleware)


def _requires_no_cache(path: str) -> bool:
    protected_tokens = (
        "/jobs",
        "/results",
        "/candidate",
        "/dashboard",
        "/analytics",
        "/debug/dashboard-consistency",
    )
    return any(token in path for token in protected_tokens)


@app.middleware("http")
async def production_safety_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    try:
        response = await call_next(request)
    except OperationalError as exc:
        error_type = operational_error_type(exc)
        logger.exception(
            "Database operational error: path=%s request_id=%s user=%s error_type=%s",
            request.url.path,
            request_id,
            getattr(getattr(request, "state", None), "user_email", "unknown"),
            error_type,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Database temporarily unavailable",
                "request_id": request_id,
                "error_type": error_type,
            },
            headers={"X-Request-ID": request_id},
        )

    response.headers["X-Request-ID"] = request_id
    if _requires_no_cache(request.url.path):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.on_event("startup")
def startup_runtime_log():
    log_startup_runtime()


Base.metadata.create_all(bind=engine)


def ensure_resume_columns():
    """Keep existing SQLite installs forward-compatible until Alembic is run."""
    inspector = inspect(engine)
    resume_columns = {column["name"] for column in inspector.get_columns("resumes")}
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    job_columns = {column["name"] for column in inspector.get_columns("jobs")}
    interview_columns = (
        {column["name"] for column in inspector.get_columns("interviews")}
        if inspector.has_table("interviews")
        else set()
    )
    organization_columns = (
        {column["name"] for column in inspector.get_columns("organizations")}
        if inspector.has_table("organizations")
        else set()
    )
    candidate_assessment_columns = (
        {column["name"] for column in inspector.get_columns("candidate_assessments")}
        if inspector.has_table("candidate_assessments")
        else set()
    )

    datetime_definition = "DATETIME" if settings.is_sqlite else "TIMESTAMP"
    boolean_false_definition = "BOOLEAN DEFAULT 0" if settings.is_sqlite else "BOOLEAN DEFAULT FALSE"
    boolean_true_definition = "BOOLEAN DEFAULT 1" if settings.is_sqlite else "BOOLEAN DEFAULT TRUE"

    with engine.begin() as connection:
        def add_column(table, existing_columns, column_name, definition):
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {definition}"))
                existing_columns.add(column_name)

        add_column("resumes", resume_columns, "shortlisted", boolean_false_definition)
        add_column("resumes", resume_columns, "confidence_score", "FLOAT")
        add_column("resumes", resume_columns, "resume_quality_score", "FLOAT")
        add_column("resumes", resume_columns, "rank_score", "FLOAT")
        add_column("resumes", resume_columns, "fit_band", "VARCHAR")
        add_column("resumes", resume_columns, "ai_recommendation", "VARCHAR")
        add_column("resumes", resume_columns, "ranking_reason", "TEXT")
        add_column("resumes", resume_columns, "shortlist_decision", "VARCHAR")
        add_column("resumes", resume_columns, "decision_reason", "TEXT")
        add_column("resumes", resume_columns, "recruiter_explanation", "TEXT")
        add_column("resumes", resume_columns, "strengths", "TEXT")
        add_column("resumes", resume_columns, "concerns", "TEXT")
        add_column("resumes", resume_columns, "score_breakdown", "TEXT")
        add_column("resumes", resume_columns, "parser_confidence", "FLOAT")
        add_column("resumes", resume_columns, "parser_warnings", "TEXT")
        add_column("resumes", resume_columns, "ai_parse_status", "VARCHAR")
        add_column("resumes", resume_columns, "extraction_quality_score", "FLOAT")
        add_column("resumes", resume_columns, "low_confidence_fields", "TEXT")
        add_column("resumes", resume_columns, "missing_critical_skills", "TEXT")
        add_column("resumes", resume_columns, "matched_critical_skills", "TEXT")
        add_column("resumes", resume_columns, "cap_reason", "TEXT")
        add_column("resumes", resume_columns, "organization_id", "VARCHAR")
        add_column("resumes", resume_columns, "duplicate_key", "VARCHAR")
        add_column("resumes", resume_columns, "duplicate_of_id", "VARCHAR")
        add_column("resumes", resume_columns, "ai_confidence_reason", "TEXT")
        add_column("resumes", resume_columns, "embedding_provider", "VARCHAR")
        add_column("resumes", resume_columns, "embedding_model", "VARCHAR")
        add_column("resumes", resume_columns, "embedding_vector_json", "TEXT")
        add_column("resumes", resume_columns, "assigned_recruiter_id", "VARCHAR")
        add_column("resumes", resume_columns, "projects", "TEXT")
        add_column("resumes", resume_columns, "relevant_experience_years", "FLOAT")
        add_column("resumes", resume_columns, "direct_relevant_experience_years", "FLOAT")
        add_column("resumes", resume_columns, "transferable_experience_years", "FLOAT")
        add_column("resumes", resume_columns, "senior_role_experience_years", "FLOAT")
        add_column("resumes", resume_columns, "role_family", "VARCHAR")
        add_column("resumes", resume_columns, "role_family_confidence", "FLOAT")
        add_column("resumes", resume_columns, "role_relevance_score", "FLOAT")
        add_column("resumes", resume_columns, "mandatory_skill_coverage", "FLOAT")
        add_column("resumes", resume_columns, "core_skill_match_percent", "FLOAT")
        add_column("resumes", resume_columns, "missing_core_skill_groups", "TEXT")
        add_column("resumes", resume_columns, "parser_quality_score", "FLOAT")
        add_column("resumes", resume_columns, "parser_quality_action", "VARCHAR")
        add_column("resumes", resume_columns, "parser_quality_flags", "TEXT")
        add_column("resumes", resume_columns, "profile_extraction_quality", "VARCHAR")
        add_column("resumes", resume_columns, "raw_parsed_json", "TEXT")
        add_column("resumes", resume_columns, "safe_parsed_json", "TEXT")
        add_column("resumes", resume_columns, "field_confidence_json", "TEXT")
        add_column("resumes", resume_columns, "field_sources_json", "TEXT")
        add_column("resumes", resume_columns, "text_extraction_quality", "TEXT")
        add_column("resumes", resume_columns, "experience_relevance_label", "VARCHAR")
        add_column("resumes", resume_columns, "experience_evidence", "TEXT")
        add_column("resumes", resume_columns, "experience_warnings", "TEXT")
        add_column("resumes", resume_columns, "score_caps_applied", "TEXT")
        add_column("resumes", resume_columns, "recruiter_flags", "TEXT")
        add_column("resumes", resume_columns, "risk_flags", "TEXT")
        add_column("resumes", resume_columns, "scoring_breakdown", "TEXT")
        add_column("resumes", resume_columns, "jd_profile_json", "TEXT")
        add_column("resumes", resume_columns, "jd_profile_snapshot_json", "TEXT")
        add_column("resumes", resume_columns, "score_job_id", "VARCHAR")
        add_column("resumes", resume_columns, "score_jd_hash", "VARCHAR")
        add_column("resumes", resume_columns, "score_jd_profile_version", "VARCHAR")
        add_column("resumes", resume_columns, "resume_file_path", "TEXT")
        add_column("resumes", resume_columns, "resume_file_url", "TEXT")
        add_column("resumes", resume_columns, "resume_file_key", "TEXT")
        add_column("resumes", resume_columns, "resume_original_filename", "VARCHAR")
        add_column("resumes", resume_columns, "resume_content_type", "VARCHAR")
        add_column("resumes", resume_columns, "original_filename", "VARCHAR")
        add_column("resumes", resume_columns, "file_size", "INTEGER")
        add_column("resumes", resume_columns, "mime_type", "VARCHAR")
        add_column("resumes", resume_columns, "uploaded_at", datetime_definition)
        add_column("resumes", resume_columns, "processing_status", "VARCHAR DEFAULT 'completed'")
        add_column("resumes", resume_columns, "processing_error", "TEXT")
        add_column("resumes", resume_columns, "processing_started_at", datetime_definition)
        add_column("resumes", resume_columns, "processing_completed_at", datetime_definition)
        add_column("resumes", resume_columns, "application_source", "VARCHAR DEFAULT 'direct'")
        add_column("resumes", resume_columns, "apply_tracking_url", "TEXT")

        add_column("jobs", job_columns, "organization_id", "VARCHAR")
        add_column("jobs", job_columns, "preferred_skills", "TEXT")
        add_column("jobs", job_columns, "owner_user_id", "VARCHAR")
        add_column("jobs", job_columns, "pipeline_template", "TEXT")
        add_column("jobs", job_columns, "status", "VARCHAR DEFAULT 'open'")
        add_column("jobs", job_columns, "priority", "VARCHAR DEFAULT 'normal'")
        add_column("jobs", job_columns, "headcount", "INTEGER DEFAULT 1")
        add_column("jobs", job_columns, "public_apply_enabled", boolean_true_definition)
        add_column("jobs", job_columns, "source_tracking_enabled", boolean_true_definition)
        add_column("jobs", job_columns, "apply_slug", "VARCHAR")
        add_column("jobs", job_columns, "generated_linkedin_post", "TEXT")
        add_column("jobs", job_columns, "generated_whatsapp_message", "TEXT")
        add_column("jobs", job_columns, "generated_naukri_text", "TEXT")
        add_column("jobs", job_columns, "generated_generic_post", "TEXT")
        add_column("jobs", job_columns, "resume_folder_path", "TEXT")
        add_column("jobs", job_columns, "jd_hash", "VARCHAR")
        add_column("jobs", job_columns, "jd_profile_version", "VARCHAR")
        add_column("jobs", job_columns, "jd_profile_json", "TEXT")
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_apply_slug ON jobs (apply_slug)"))

        if organization_columns:
            add_column("organizations", organization_columns, "settings_json", "TEXT")
        if interview_columns:
            add_column("interviews", interview_columns, "panel_json", "TEXT")
            add_column("interviews", interview_columns, "candidate_availability_json", "TEXT")

        add_column("users", user_columns, "google_access_token", "TEXT")
        add_column("users", user_columns, "google_refresh_token", "TEXT")
        add_column("users", user_columns, "google_token_expires_at", datetime_definition)
        add_column("users", user_columns, "outreach_sender_email", "VARCHAR")
        add_column("users", user_columns, "outreach_sender_verified_at", datetime_definition)
        add_column("users", user_columns, "outreach_sender_verification_token", "VARCHAR")
        add_column("users", user_columns, "outreach_sender_verification_expires_at", datetime_definition)
        add_column("users", user_columns, "outreach_smtp_host", "VARCHAR")
        add_column("users", user_columns, "outreach_smtp_port", "INTEGER")
        add_column("users", user_columns, "outreach_smtp_username", "VARCHAR")
        add_column("users", user_columns, "outreach_smtp_password_enc", "TEXT")
        add_column("users", user_columns, "outreach_smtp_use_tls", boolean_true_definition)
        add_column("users", user_columns, "auth_provider", "VARCHAR")
        add_column("users", user_columns, "role", "VARCHAR DEFAULT 'recruiter'")
        add_column("users", user_columns, "organization_id", "VARCHAR")
        add_column("users", user_columns, "is_active", boolean_true_definition)
        add_column("users", user_columns, "subscription_status", "VARCHAR DEFAULT 'unpaid'")
        add_column("users", user_columns, "subscription_plan", "VARCHAR")
        add_column("users", user_columns, "subscription_started_at", datetime_definition)

        add_column("candidate_assessments", candidate_assessment_columns, "response_id", "VARCHAR")
        add_column("candidate_assessments", candidate_assessment_columns, "score", "FLOAT")
        add_column("candidate_assessments", candidate_assessment_columns, "max_score", "FLOAT")
        add_column("candidate_assessments", candidate_assessment_columns, "percentage", "FLOAT")
        add_column("candidate_assessments", candidate_assessment_columns, "result_status", "VARCHAR")
        add_column("candidate_assessments", candidate_assessment_columns, "completed_at", datetime_definition)
        add_column("candidate_assessments", candidate_assessment_columns, "interview_status", "VARCHAR")

        connection.execute(
            text(
                """
                UPDATE resumes
                SET shortlisted = true,
                    status = 'Shortlisted',
                    stage = 'shortlisted'
                WHERE (shortlisted_auto = true OR status IN ('Shortlisted', 'Shortlisted (AI)'))
                  AND status NOT IN ('Rejected', 'Communication')
                """
            )
        )
        connection.execute(text("UPDATE resumes SET stage = 'communication' WHERE status = 'Communication'"))


ensure_resume_columns()

app.include_router(job.router)
app.include_router(resume.router)
app.include_router(auth.router)
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(debug.router, prefix=settings.api_prefix)
app.include_router(ai.router, prefix=settings.api_prefix)
app.include_router(copilot.router, prefix=settings.api_prefix)
app.include_router(enterprise.router, prefix=settings.api_prefix)
app.include_router(interviews.router, prefix=settings.api_prefix)
app.include_router(organizations.router, prefix=settings.api_prefix)
app.include_router(realtime.router, prefix=settings.api_prefix)
app.include_router(support.router, prefix=settings.api_prefix)
app.include_router(talent.router, prefix=settings.api_prefix)
app.include_router(uploads.router, prefix=settings.api_prefix)
app.mount("/frontend", StaticFiles(directory="frontend", check_dir=False), name="frontend")


@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "status": "online",
        "legacy_endpoints": "enabled",
        "api": settings.api_prefix,
    }


@app.get("/system-readiness")
def system_readiness():
    """Non-sensitive production checklist for the recruiter dashboard."""
    checks = [
        {
            "key": "jwt_secret",
            "label": "JWT secret configured",
            "status": "pass" if settings.jwt_secret != "change-me-in-production" else "warn",
            "message": "Use a strong JWT_SECRET in production.",
        },
        {
            "key": "secure_cookies",
            "label": "Secure cookies",
            "status": "pass" if settings.secure_cookies or settings.environment == "development" else "warn",
            "message": "Enable SECURE_COOKIES=true behind HTTPS.",
        },
        {
            "key": "cors",
            "label": "CORS allowlist",
            "status": "pass" if "*" not in settings.allowed_origins else "warn",
            "message": "Avoid wildcard origins for recruiter data.",
        },
        {
            "key": "upload_limit",
            "label": "Upload limit",
            "status": "pass" if settings.max_upload_mb <= 20 else "warn",
            "message": f"Current resume upload limit is {settings.max_upload_mb}MB.",
        },
        {
            "key": "rate_limit",
            "label": "Rate limiting",
            "status": "pass" if settings.rate_limit_per_minute > 0 else "warn",
            "message": f"Current limit is {settings.rate_limit_per_minute} requests/minute per client.",
        },
        {
            "key": "signed_candidate_tracking",
            "label": "Signed candidate tracking links",
            "status": "pass" if not settings.allow_legacy_candidate_tracking else "warn",
            "message": "Set ALLOW_LEGACY_CANDIDATE_TRACKING=false after old candidate_id links are rotated.",
        },
    ]
    return {
        "environment": settings.environment,
        "overall_status": "ready" if all(check["status"] == "pass" for check in checks) else "review",
        "checks": checks,
        "workflow_features": [
            "Job creation",
            "Resume upload and AI matching",
            "Shortlist review",
            "Communication stage",
            "Assessment and interview scheduling",
            "Candidate timeline/audit events",
            "Bulk analyzer session persistence",
        ],
    }
