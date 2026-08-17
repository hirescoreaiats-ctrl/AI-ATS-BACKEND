from __future__ import annotations

import re
import secrets

from fastapi import HTTPException

from backend.models import Job, Organization, Resume, User


GLOBAL_ADMIN_ROLES = {"super_admin"}


def is_global_admin(user: User) -> bool:
    return (getattr(user, "role", None) or "").strip().lower() in GLOBAL_ADMIN_ROLES


def current_organization_id(user: User, *, allow_global_admin: bool = False) -> str | None:
    if allow_global_admin and is_global_admin(user):
        return None
    organization_id = (getattr(user, "organization_id", None) or "").strip()
    if not organization_id:
        raise HTTPException(status_code=403, detail="Account is not assigned to an organization")
    return organization_id


def scope_tenant_query(query, model, user: User, *, allow_global_admin: bool = False):
    organization_id = current_organization_id(user, allow_global_admin=allow_global_admin)
    if organization_id is None:
        return query
    return query.filter(model.organization_id == organization_id)


def require_candidate(db, candidate_id: str, user: User, *, active_only: bool = False) -> Resume:
    query = db.query(Resume).filter(Resume.id == candidate_id)
    if active_only:
        query = query.filter(Resume.is_active == True)
    candidate = scope_tenant_query(query, Resume, user, allow_global_admin=True).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def require_job(db, job_id: str, user: User) -> Job:
    job = scope_tenant_query(db.query(Job).filter(Job.id == job_id), Job, user, allow_global_admin=True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def create_personal_organization(db, user: User, *, plan: str = "pilot") -> Organization:
    label = (user.name or user.email.split("@", 1)[0] or "Workspace").strip()
    slug_base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:70] or "workspace"
    org = Organization(name=f"{label} Workspace", slug=f"{slug_base}-{secrets.token_hex(6)}", plan=plan)
    db.add(org)
    db.flush()
    user.organization_id = org.id
    return org
