from __future__ import annotations

import logging
import re
import secrets

from sqlalchemy import func, or_

from backend.database import SessionLocal
from backend.models import Job, Organization, RecruiterInvitation, Resume, User


logger = logging.getLogger(__name__)


def _pilot_workspace(db, user: User) -> Organization:
    label = (user.company_name or user.name or user.email.split("@", 1)[0] or "Pilot").strip()
    slug_base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:70] or "pilot"
    organization = Organization(
        name=f"{label} Workspace",
        slug=f"{slug_base}-{secrets.token_hex(6)}",
        plan="pilot",
    )
    db.add(organization)
    db.flush()
    return organization


def repair_tenant_assignments(db) -> dict[str, int]:
    """Repair historical shared-pilot and tenantless ownership safely.

    The operation is idempotent. A pilot is split only while its organization
    is shared, and tenantless legacy jobs are assigned only when ownership is
    unambiguous (exactly one organization admin exists).
    """
    result = {"pilots_split": 0, "jobs_relinked": 0, "resumes_relinked": 0, "legacy_jobs_restored": 0}

    pilots = db.query(User).filter(User.subscription_plan == "pilot", User.organization_id.isnot(None)).all()
    for pilot in pilots:
        shared_count = db.query(func.count(User.id)).filter(User.organization_id == pilot.organization_id).scalar() or 0
        if shared_count <= 1:
            continue

        organization = _pilot_workspace(db, pilot)
        pilot.organization_id = organization.id
        moved_job_ids = [row[0] for row in db.query(Job.id).filter(Job.owner_user_id == pilot.id).all()]
        if moved_job_ids:
            result["jobs_relinked"] += db.query(Job).filter(Job.id.in_(moved_job_ids)).update(
                {Job.organization_id: organization.id}, synchronize_session=False
            )
            result["resumes_relinked"] += db.query(Resume).filter(Resume.job_id.in_(moved_job_ids)).update(
                {Resume.organization_id: organization.id}, synchronize_session=False
            )
        db.query(RecruiterInvitation).filter(
            func.lower(RecruiterInvitation.email) == pilot.email.lower(),
            RecruiterInvitation.token.like("pilot_%"),
        ).update({RecruiterInvitation.organization_id: organization.id}, synchronize_session=False)
        result["pilots_split"] += 1

    # Re-apply explicit ownership after pilot splitting so every owned job and
    # candidate follows the owner's final organization.
    owners = db.query(User).filter(User.organization_id.isnot(None)).all()
    for owner in owners:
        owned_job_ids = [row[0] for row in db.query(Job.id).filter(Job.owner_user_id == owner.id).all()]
        if not owned_job_ids:
            continue
        result["jobs_relinked"] += db.query(Job).filter(
            Job.id.in_(owned_job_ids),
            or_(Job.organization_id.is_(None), Job.organization_id != owner.organization_id),
        ).update({Job.organization_id: owner.organization_id}, synchronize_session=False)
        result["resumes_relinked"] += db.query(Resume).filter(
            Resume.job_id.in_(owned_job_ids),
            or_(Resume.organization_id.is_(None), Resume.organization_id != owner.organization_id),
        ).update({Resume.organization_id: owner.organization_id}, synchronize_session=False)

    admins = db.query(User).filter(User.role == "admin", User.organization_id.isnot(None)).all()
    if len(admins) == 1:
        admin = admins[0]
        orphan_job_ids = [
            row[0]
            for row in db.query(Job.id).filter(Job.organization_id.is_(None), Job.owner_user_id.is_(None)).all()
        ]
        if orphan_job_ids:
            result["legacy_jobs_restored"] += db.query(Job).filter(Job.id.in_(orphan_job_ids)).update(
                {Job.organization_id: admin.organization_id}, synchronize_session=False
            )
            result["resumes_relinked"] += db.query(Resume).filter(Resume.job_id.in_(orphan_job_ids)).update(
                {Resume.organization_id: admin.organization_id}, synchronize_session=False
            )

    db.commit()
    return result


def repair_tenant_assignments_at_startup() -> None:
    db = SessionLocal()
    try:
        result = repair_tenant_assignments(db)
        if any(result.values()):
            logger.warning("Tenant assignment repair applied: %s", result)
    except Exception:
        db.rollback()
        logger.exception("Tenant assignment repair failed")
    finally:
        db.close()
