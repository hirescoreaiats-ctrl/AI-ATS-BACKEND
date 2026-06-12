from fastapi import APIRouter, Depends
from sqlalchemy import func

from backend.core.security import require_roles
from backend.database import get_db
from backend.models import Job, Resume, User
from backend.services.runtime import runtime_payload

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/runtime")
def runtime_debug():
    return runtime_payload(include_database_check=True)


@router.get("/dashboard-consistency")
def dashboard_consistency(
    db=Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    visible_jobs_query = db.query(Job)
    applied_filters = {"role": current_user.role or "recruiter"}
    if current_user.organization_id:
        visible_jobs_query = visible_jobs_query.filter(Job.organization_id == current_user.organization_id)
        applied_filters["organization_id"] = current_user.organization_id

    visible_job_ids = [job_id for (job_id,) in visible_jobs_query.with_entities(Job.id).all()]
    active_jobs_for_user = visible_jobs_query.filter(Job.is_active == True).count()
    candidates_for_visible_jobs = 0
    if visible_job_ids:
        candidates_for_visible_jobs = db.query(Resume).filter(
            Resume.job_id.in_(visible_job_ids),
            Resume.is_active == True,
        ).count()

    latest_jobs = visible_jobs_query.order_by(Job.created_at.desc()).limit(5).all()
    latest_candidates_query = db.query(Resume)
    if visible_job_ids:
        latest_candidates_query = latest_candidates_query.filter(Resume.job_id.in_(visible_job_ids))
    else:
        latest_candidates_query = latest_candidates_query.filter(False)
    latest_candidates = latest_candidates_query.order_by(Resume.created_at.desc()).limit(5).all()

    return {
        "current_user": {
            "email": current_user.email,
            "role": current_user.role or "recruiter",
        },
        "total_jobs_db": db.query(func.count(Job.id)).scalar() or 0,
        "visible_jobs_for_user": len(visible_job_ids),
        "active_jobs_for_user": active_jobs_for_user,
        "total_candidates_db": db.query(func.count(Resume.id)).scalar() or 0,
        "candidates_for_visible_jobs": candidates_for_visible_jobs,
        "latest_5_jobs": [
            {
                "id": job.id,
                "job_title": job.job_title,
                "company_name": job.company_name,
                "is_active": job.is_active,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            for job in latest_jobs
        ],
        "latest_5_candidates": [
            {
                "id": candidate.id,
                "job_id": candidate.job_id,
                "name": candidate.full_name or candidate.form_full_name,
                "email": candidate.email or candidate.form_email,
                "status": candidate.status,
                "rank_score": candidate.rank_score,
                "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
            }
            for candidate in latest_candidates
        ],
        "applied_filters": applied_filters,
        "database_ok": True,
    }
