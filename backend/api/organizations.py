from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.core.security import get_current_user, require_roles
from backend.database import get_db
from backend.models import Job, Organization, RecruiterInvitation, Resume, Team, TeamMember, User
from backend.repositories.audit_repository import write_audit_log
from backend.utils.sanitize import sanitize_text

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("")
def create_organization(data: dict = Body(...), db=Depends(get_db), user=Depends(require_roles("admin", "recruiter"))):
    name = sanitize_text(data.get("name"), 160)
    slug = sanitize_text(data.get("slug") or name.lower().replace(" ", "-"), 120)
    if not name:
        raise HTTPException(status_code=400, detail="Organization name is required")
    org = Organization(name=name, slug=slug, settings_json=json.dumps(data.get("settings") or {}))
    db.add(org)
    db.flush()
    user.organization_id = org.id
    user.role = "admin"
    write_audit_log(db, action="organization.created", entity_type="organization", entity_id=org.id, actor_user_id=user.id)
    db.commit()
    db.refresh(org)
    return {"id": org.id, "name": org.name, "slug": org.slug}


@router.get("")
def list_organizations(db=Depends(get_db), user=Depends(get_current_user)):
    query = db.query(Organization)
    if user.role != "admin" and user.organization_id:
        query = query.filter(Organization.id == user.organization_id)
    return [{"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan} for org in query.limit(100).all()]


@router.post("/{organization_id}/teams")
def create_team(organization_id: str, data: dict = Body(...), db=Depends(get_db), user=Depends(require_roles("admin", "recruiter"))):
    team = Team(
        organization_id=organization_id,
        name=sanitize_text(data.get("name"), 120),
        department=sanitize_text(data.get("department"), 120),
    )
    db.add(team)
    write_audit_log(db, action="team.created", entity_type="team", actor_user_id=user.id, organization_id=organization_id)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "name": team.name, "department": team.department}


@router.post("/{organization_id}/invitations")
def invite_recruiter(organization_id: str, data: dict = Body(...), db=Depends(get_db), user=Depends(require_roles("admin"))):
    email = (data.get("email") or "").strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    invitation = RecruiterInvitation(
        organization_id=organization_id,
        invited_by_user_id=user.id,
        email=email,
        role=data.get("role") or "recruiter",
        token=secrets.token_urlsafe(32),
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(invitation)
    write_audit_log(db, action="recruiter.invited", entity_type="invitation", actor_user_id=user.id, organization_id=organization_id, metadata={"email": email})
    db.commit()
    return {"id": invitation.id, "email": invitation.email, "role": invitation.role, "status": invitation.status}


@router.post("/teams/{team_id}/members")
def add_team_member(team_id: str, data: dict = Body(...), db=Depends(get_db), user=Depends(require_roles("admin", "recruiter"))):
    member = TeamMember(team_id=team_id, user_id=data.get("user_id"), role=data.get("role") or "member")
    db.add(member)
    db.commit()
    return {"id": member.id, "team_id": team_id, "user_id": member.user_id, "role": member.role}


@router.put("/users/{user_id}/role")
def update_user_role(user_id: str, data: dict = Body(...), db=Depends(get_db), user=Depends(require_roles("admin"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = data.get("role") or target.role
    db.commit()
    return {"id": target.id, "role": target.role}


@router.get("/{organization_id}/analytics")
def organization_analytics(organization_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    if user.organization_id and user.organization_id != organization_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Organization access denied")
    jobs = db.query(Job).filter(Job.organization_id == organization_id).all()
    candidates = db.query(Resume).filter(Resume.organization_id == organization_id, Resume.is_active == True).all()
    users = db.query(User).filter(User.organization_id == organization_id, User.is_active == True).all()
    stage_counts = {}
    for candidate in candidates:
        stage_counts[candidate.stage or "review"] = stage_counts.get(candidate.stage or "review", 0) + 1
    return {
        "organization_id": organization_id,
        "active_jobs": len([job for job in jobs if job.is_active]),
        "users": len(users),
        "candidates": len(candidates),
        "stage_counts": stage_counts,
        "departments": sorted({job.department for job in jobs if job.department}),
    }
