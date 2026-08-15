from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func

from backend.models import Job, PilotResumeReservation, Resume, User


EXPIRING_SOON_DAYS = 3


def utcnow() -> datetime:
    return datetime.utcnow()


def is_pilot(user: User | None) -> bool:
    return bool(user and (getattr(user, "subscription_plan", None) or "").lower() == "pilot")


def pilot_effective_status(user: User, now: datetime | None = None) -> str:
    if not is_pilot(user):
        return "not_pilot"
    now = now or utcnow()
    configured = (user.pilot_status or "active").lower()
    access = (user.pilot_access_status or "enabled").lower()
    if configured == "suspended" or user.pilot_suspended_at:
        return "suspended"
    if configured == "deactivated" or user.pilot_deactivated_at or access == "disabled" or not user.is_active:
        return "deactivated"
    if user.pilot_expires_at and now >= user.pilot_expires_at:
        return "expired"
    if configured in {"converted", "pending_invite"}:
        return configured
    if user.pilot_expires_at and user.pilot_expires_at <= now + timedelta(days=EXPIRING_SOON_DAYS):
        return "expiring_soon"
    return "active"


def pilot_access_payload(user: User) -> dict:
    status = pilot_effective_status(user)
    messages = {
        "expired": "Your HireScore AI pilot has expired.",
        "deactivated": "Your HireScore AI access has been deactivated.",
        "suspended": "Your account access is temporarily suspended.",
    }
    return {
        "code": f"pilot_{status}",
        "status": status,
        "message": messages.get(status, "Pilot access is unavailable."),
        "pilot_started_at": user.pilot_started_at.isoformat() if user.pilot_started_at else None,
        "pilot_expires_at": user.pilot_expires_at.isoformat() if user.pilot_expires_at else None,
        "data_preserved": True,
    }


def enforce_pilot_access(user: User | None) -> None:
    if not is_pilot(user):
        return
    status = pilot_effective_status(user)
    if status not in {"active", "expiring_soon"}:
        raise HTTPException(status_code=403, detail=pilot_access_payload(user))


def lock_pilot_user(db, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="Pilot user not found")
    return user


def _owned_jobs_query(db, user: User):
    return db.query(Job).filter(Job.owner_user_id == user.id)


def pilot_usage(db, user: User) -> dict:
    total_jobs = _owned_jobs_query(db, user).count()
    active_jobs = _owned_jobs_query(db, user).filter(Job.is_active.is_(True)).count()
    total_resumes = (
        db.query(func.count(Resume.id))
        .join(Job, Job.id == Resume.job_id)
        .filter(Job.owner_user_id == user.id, Resume.is_active.is_(True))
        .scalar()
        or 0
    )
    per_job_rows = (
        db.query(Job.id, Job.job_title, Job.is_active, func.count(Resume.id))
        .outerjoin(Resume, (Resume.job_id == Job.id) & (Resume.is_active.is_(True)))
        .filter(Job.owner_user_id == user.id)
        .group_by(Job.id, Job.job_title, Job.is_active)
        .order_by(Job.created_at.desc())
        .all()
    )
    per_job = [
        {"job_id": row[0], "job_title": row[1], "active": bool(row[2]), "resumes": int(row[3] or 0)}
        for row in per_job_rows
    ]
    return {
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "closed_jobs": max(0, total_jobs - active_jobs),
        "total_resumes": int(total_resumes),
        "per_job": per_job,
    }


def _limit_error(code: str, message: str, *, used: int, limit: int, remaining: int = 0) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": code, "message": message, "used": used, "limit": limit, "remaining": max(0, remaining)},
    )


def enforce_job_creation(db, user: User) -> User:
    if not is_pilot(user):
        return user
    locked = lock_pilot_user(db, user.id)
    enforce_pilot_access(locked)
    usage = pilot_usage(db, locked)
    if locked.max_total_jobs is not None and usage["total_jobs"] >= locked.max_total_jobs:
        raise _limit_error(
            "pilot_total_jobs_limit",
            f"You've reached your pilot job limit ({usage['total_jobs']}/{locked.max_total_jobs}).",
            used=usage["total_jobs"],
            limit=locked.max_total_jobs,
        )
    if locked.max_active_jobs is not None and usage["active_jobs"] >= locked.max_active_jobs:
        raise _limit_error(
            "pilot_active_jobs_limit",
            f"You've reached your active job limit ({usage['active_jobs']}/{locked.max_active_jobs}). Close an active job or contact your administrator.",
            used=usage["active_jobs"],
            limit=locked.max_active_jobs,
        )
    locked.last_activity_at = utcnow()
    return locked


def enforce_job_activation(db, job: Job) -> None:
    if not getattr(job, "owner_user_id", None):
        return
    owner = lock_pilot_user(db, job.owner_user_id)
    if not is_pilot(owner):
        return
    enforce_pilot_access(owner)
    active_jobs = _owned_jobs_query(db, owner).filter(Job.is_active.is_(True), Job.id != job.id).count()
    if owner.max_active_jobs is not None and active_jobs >= owner.max_active_jobs:
        raise _limit_error(
            "pilot_active_jobs_limit",
            f"You've reached your active job limit ({active_jobs}/{owner.max_active_jobs}). Close an active job or contact your administrator.",
            used=active_jobs,
            limit=owner.max_active_jobs,
        )
    owner.last_activity_at = utcnow()


def enforce_resume_batch(db, job: Job, incoming_count: int) -> None:
    if not getattr(job, "owner_user_id", None) or incoming_count <= 0:
        return
    owner = lock_pilot_user(db, job.owner_user_id)
    if not is_pilot(owner):
        return
    enforce_pilot_access(owner)
    per_job_used = db.query(func.count(Resume.id)).filter(Resume.job_id == job.id, Resume.is_active.is_(True)).scalar() or 0
    if owner.max_resumes_per_job is not None and per_job_used + incoming_count > owner.max_resumes_per_job:
        remaining = owner.max_resumes_per_job - per_job_used
        raise _limit_error(
            "pilot_job_resume_limit",
            f"This job has {max(0, remaining)} resume slots remaining.",
            used=int(per_job_used),
            limit=owner.max_resumes_per_job,
            remaining=remaining,
        )
    if owner.max_total_resumes is not None:
        total_used = (
            db.query(func.count(Resume.id))
            .join(Job, Job.id == Resume.job_id)
            .filter(Job.owner_user_id == owner.id, Resume.is_active.is_(True))
            .scalar()
            or 0
        )
        if total_used + incoming_count > owner.max_total_resumes:
            remaining = owner.max_total_resumes - total_used
            raise _limit_error(
                "pilot_total_resume_limit",
                f"Your pilot has {max(0, remaining)} total resume slots remaining.",
                used=int(total_used),
                limit=owner.max_total_resumes,
                remaining=remaining,
            )
    owner.last_activity_at = utcnow()


def reserve_resume_batch(db, job: Job, incoming_count: int) -> str | None:
    if not getattr(job, "owner_user_id", None) or incoming_count <= 0:
        return None
    owner = lock_pilot_user(db, job.owner_user_id)
    if not is_pilot(owner):
        return None
    enforce_pilot_access(owner)
    now = utcnow()
    db.query(PilotResumeReservation).filter(PilotResumeReservation.expires_at <= now).delete(synchronize_session=False)
    per_job_reserved = db.query(func.coalesce(func.sum(PilotResumeReservation.reserved_count), 0)).filter(PilotResumeReservation.job_id == job.id).scalar() or 0
    total_reserved = db.query(func.coalesce(func.sum(PilotResumeReservation.reserved_count), 0)).filter(PilotResumeReservation.user_id == owner.id).scalar() or 0
    per_job_used = db.query(func.count(Resume.id)).filter(Resume.job_id == job.id, Resume.is_active.is_(True)).scalar() or 0
    if owner.max_resumes_per_job is not None and per_job_used + per_job_reserved + incoming_count > owner.max_resumes_per_job:
        remaining = owner.max_resumes_per_job - per_job_used - per_job_reserved
        raise _limit_error("pilot_job_resume_limit", f"This job has {max(0, remaining)} resume slots remaining.", used=int(per_job_used), limit=owner.max_resumes_per_job, remaining=remaining)
    if owner.max_total_resumes is not None:
        total_used = db.query(func.count(Resume.id)).join(Job, Job.id == Resume.job_id).filter(Job.owner_user_id == owner.id, Resume.is_active.is_(True)).scalar() or 0
        if total_used + total_reserved + incoming_count > owner.max_total_resumes:
            remaining = owner.max_total_resumes - total_used - total_reserved
            raise _limit_error("pilot_total_resume_limit", f"Your pilot has {max(0, remaining)} total resume slots remaining.", used=int(total_used), limit=owner.max_total_resumes, remaining=remaining)
    reservation = PilotResumeReservation(user_id=owner.id, job_id=job.id, reserved_count=incoming_count, expires_at=now + timedelta(minutes=30))
    db.add(reservation)
    owner.last_activity_at = now
    db.commit()
    return reservation.id


def release_resume_reservation(db, reservation_id: str | None) -> None:
    if not reservation_id:
        return
    db.rollback()
    db.query(PilotResumeReservation).filter(PilotResumeReservation.id == reservation_id).delete(synchronize_session=False)
    db.commit()


def remaining(limit: int | None, used: int) -> int | None:
    return None if limit is None else max(0, limit - used)


def usage_with_limits(db, user: User) -> dict:
    usage = pilot_usage(db, user)
    limits = {
        "total_jobs": user.max_total_jobs,
        "active_jobs": user.max_active_jobs,
        "resumes_per_job": user.max_resumes_per_job,
        "total_resumes": user.max_total_resumes,
    }
    usage["limits"] = limits
    usage["remaining"] = {
        "total_jobs": remaining(user.max_total_jobs, usage["total_jobs"]),
        "active_jobs": remaining(user.max_active_jobs, usage["active_jobs"]),
        "total_resumes": remaining(user.max_total_resumes, usage["total_resumes"]),
    }
    usage["over_limit"] = {
        "total_jobs": user.max_total_jobs is not None and usage["total_jobs"] > user.max_total_jobs,
        "active_jobs": user.max_active_jobs is not None and usage["active_jobs"] > user.max_active_jobs,
        "total_resumes": user.max_total_resumes is not None and usage["total_resumes"] > user.max_total_resumes,
    }
    return usage
