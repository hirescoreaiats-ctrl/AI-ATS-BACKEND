from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from backend.core.config import get_settings
from backend.core.security import create_access_token, get_current_user, hash_password, require_roles, verify_password
from backend.database import SessionLocal
from backend.models import AuditLog, Job, Organization, RecruiterInvitation, User
from backend.repositories.audit_repository import write_audit_log
from backend.services.transactional_email import send_transactional_email
import jwt
import datetime
from fastapi.responses import RedirectResponse
import requests
import os
import urllib.parse
import secrets
import string
import smtplib
import html
import json
from email.mime.text import MIMEText
from backend.services.pilot_access import is_pilot, pilot_access_payload, pilot_effective_status, usage_with_limits

router = APIRouter()

settings = get_settings()
SECRET = settings.jwt_secret


def _load_local_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


# ---------------- REQUEST MODEL ----------------

class AuthRequest(BaseModel):
    name: str = None
    email: str
    password: str
    access_code: str = None


class ResetPasswordRequest(BaseModel):
    email: str


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _validate_password_strength(password: str | None) -> None:
    password = password or ""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if password.lower() in {"password", "password123", "12345678", "admin1234"}:
        raise HTTPException(status_code=400, detail="Password is too common")


def _clean_access_code(value: str | None) -> str:
    return (value or "").strip()


def _configured_paid_codes() -> set[str]:
    blocked = {"", "<paid-access-code>", "<code-from-payment-provider>", "change-me", "changeme"}
    return {code.strip() for code in settings.paid_signup_access_codes if code.strip() and code.strip().lower() not in blocked}


def _find_valid_invitation(db, email: str, access_code: str) -> RecruiterInvitation | None:
    if not access_code or db is None:
        return None
    invitation = (
        db.query(RecruiterInvitation)
        .filter(
            RecruiterInvitation.token == access_code,
            RecruiterInvitation.status == "pending",
        )
        .first()
    )
    if not invitation:
        return None
    if invitation.email and invitation.email.strip().lower() != email:
        return None
    if invitation.expires_at and invitation.expires_at < datetime.datetime.utcnow():
        return None
    return invitation


def _validate_signup_access(db, email: str, access_code: str | None) -> RecruiterInvitation | None:
    mode = (settings.signup_mode or "access_code").lower()
    access_code = _clean_access_code(access_code)

    if mode == "open":
        return None

    invitation = _find_valid_invitation(db, email, access_code)
    if invitation:
        return invitation

    if mode in {"access_code", "paid"}:
        if access_code and access_code in _configured_paid_codes():
            return None
        raise HTTPException(
            status_code=402,
            detail="Paid access required. Complete checkout or enter a valid admin invite code.",
        )

    raise HTTPException(status_code=403, detail="Direct signup is disabled. Ask admin for an invite or choose a paid plan.")


def _apply_invitation_to_user(invitation: RecruiterInvitation | None, user: User) -> None:
    if not invitation:
        return
    user.role = invitation.role or user.role or "recruiter"
    user.organization_id = invitation.organization_id
    if (invitation.token or "").startswith("pilot_"):
        user.subscription_plan = "pilot"
        config = json.loads(invitation.pilot_config_json or "{}")
        user.company_name = config.get("company_name") or user.company_name
        user.pilot_started_at = _parse_datetime(config.get("pilot_started_at")) or datetime.datetime.utcnow()
        user.pilot_expires_at = _parse_datetime(config.get("pilot_expires_at"))
        user.pilot_status = "active"
        user.pilot_access_status = "enabled"
        user.max_total_jobs = config.get("max_total_jobs")
        user.max_active_jobs = config.get("max_active_jobs")
        user.max_resumes_per_job = config.get("max_resumes_per_job")
        user.max_total_resumes = config.get("max_total_resumes")
        user.pilot_notes = config.get("pilot_notes")
        user.pilot_source = config.get("pilot_source")
    invitation.status = "accepted"
    invitation.accepted_at = datetime.datetime.utcnow()


def _ensure_user_organization(db, user: User) -> str | None:
    """Create an isolated workspace for independent accounts; invitations keep their assigned workspace."""
    if user.organization_id:
        return user.organization_id
    if (user.role or "").strip().lower() == "super_admin":
        return None
    workspace_name = (user.company_name or user.name or "HireScore").strip()
    organization = Organization(
        name=f"{workspace_name} Workspace",
        slug=f"workspace-{secrets.token_hex(8)}",
    )
    db.add(organization)
    db.flush()
    user.organization_id = organization.id
    return organization.id


def _parse_datetime(value) -> datetime.datetime | None:
    if isinstance(value, datetime.datetime):
        return value
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role or "recruiter",
        "organization_id": user.organization_id,
        "subscription_status": user.subscription_status or "unpaid",
        "subscription_plan": user.subscription_plan,
    }


def _pilot_signup_url(invitation: RecruiterInvitation) -> str:
    query = urllib.parse.urlencode({"access_code": invitation.token, "email": invitation.email})
    return _frontend_page_url(SIGNUP_PAGE, query)


def _send_pilot_invitation_email(invitation: RecruiterInvitation, invited_by: User) -> dict:
    signup_url = _pilot_signup_url(invitation)
    inviter_name = (invited_by.name or "HireScore AI Admin").strip()
    safe_inviter_name = html.escape(inviter_name)
    safe_email = html.escape(invitation.email)
    safe_signup_url = html.escape(signup_url, quote=True)
    text_body = (
        "You're invited to join the HireScore AI pilot.\n\n"
        f"{inviter_name} created pilot access for {invitation.email}.\n"
        "Create your account using this private link:\n"
        f"{signup_url}\n\n"
        "This invitation expires in 7 days and can only be used with this email address.\n\n"
        "HireScore AI"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#172033;line-height:1.55">
      <div style="padding:28px;border:1px solid #dfe5ee;border-radius:16px;background:#ffffff">
        <div style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#4f46e5">HIRESCORE AI PILOT</div>
        <h1 style="font-size:24px;margin:10px 0 8px">You're invited to HireScore AI</h1>
        <p style="color:#5f6b7d;margin:0 0 22px">{safe_inviter_name} created secure pilot access for <strong>{safe_email}</strong>.</p>
        <a href="{safe_signup_url}" style="display:inline-block;padding:12px 20px;border-radius:9px;background:#315bea;color:#ffffff;text-decoration:none;font-weight:700">Create Pilot Account</a>
        <p style="font-size:12px;color:#7b8798;margin:20px 0 0">This private invitation expires in 7 days and only works for the invited email address.</p>
      </div>
    </div>
    """
    return send_transactional_email(
        to_email=invitation.email,
        to_name=invitation.email.split("@", 1)[0],
        subject="You're invited to the HireScore AI Pilot",
        html_body=html_body,
        text_body=text_body,
    )


def _ensure_admin_organization(db, admin: User) -> str:
    local_admin = db.query(User).filter(User.id == admin.id).first()
    if not local_admin:
        raise HTTPException(status_code=401, detail="Admin account not found")
    if local_admin.organization_id:
        return local_admin.organization_id
    slug = f"pilot-{local_admin.id[:8]}-{secrets.token_hex(3)}"
    organization = Organization(name=f"{local_admin.name or 'HireScore'} Pilot Workspace", slug=slug)
    db.add(organization)
    db.flush()
    local_admin.organization_id = organization.id
    return organization.id


def _pilot_limit(data: dict, key: str, default=None) -> int | None:
    value = data.get(key, default)
    if value in {None, "", "unlimited"}:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{key} must be a positive number or unlimited") from exc
    if parsed <= 0:
        raise HTTPException(status_code=400, detail=f"{key} must be greater than zero")
    return parsed


def _pilot_config(data: dict) -> dict:
    now = datetime.datetime.utcnow()
    started = _parse_datetime(data.get("pilot_started_at") or data.get("start_date")) or now
    expires = _parse_datetime(data.get("pilot_expires_at") or data.get("expiry_date"))
    if not expires:
        try:
            duration_days = int(data.get("duration_days") or 14)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Pilot duration must be 7, 14, 30, or a custom expiry date") from exc
        if duration_days not in {7, 14, 30}:
            raise HTTPException(status_code=400, detail="Custom duration requires an explicit expiry date")
        expires = started + datetime.timedelta(days=duration_days)
    if expires <= started:
        raise HTTPException(status_code=400, detail="Pilot expiry must be after the start date")
    total_jobs = _pilot_limit(data, "max_total_jobs", 10)
    active_jobs = _pilot_limit(data, "max_active_jobs", 3)
    if total_jobs is not None and active_jobs is not None and active_jobs > total_jobs:
        raise HTTPException(status_code=400, detail="Maximum active jobs cannot exceed total jobs allowed")
    return {
        "name": str(data.get("name") or "").strip() or None,
        "company_name": str(data.get("company_name") or "").strip() or None,
        "max_total_jobs": total_jobs,
        "max_active_jobs": active_jobs,
        "max_resumes_per_job": _pilot_limit(data, "max_resumes_per_job", 500),
        "max_total_resumes": _pilot_limit(data, "max_total_resumes"),
        "pilot_started_at": started.isoformat(),
        "pilot_expires_at": expires.isoformat(),
        "pilot_notes": str(data.get("pilot_notes") or "").strip() or None,
        "pilot_source": str(data.get("pilot_source") or "manual").strip().lower() or "manual",
    }


def _apply_pilot_config(user: User, config: dict) -> None:
    user.name = config.get("name") or user.name
    user.company_name = config.get("company_name")
    user.pilot_started_at = _parse_datetime(config.get("pilot_started_at")) or datetime.datetime.utcnow()
    user.pilot_expires_at = _parse_datetime(config.get("pilot_expires_at"))
    user.max_total_jobs = config.get("max_total_jobs")
    user.max_active_jobs = config.get("max_active_jobs")
    user.max_resumes_per_job = config.get("max_resumes_per_job")
    user.max_total_resumes = config.get("max_total_resumes")
    user.pilot_notes = config.get("pilot_notes")
    user.pilot_source = config.get("pilot_source")
    user.pilot_status = "active"
    user.pilot_access_status = "enabled"
    user.pilot_deactivated_at = None
    user.pilot_deactivated_by = None
    user.pilot_deactivation_reason = None
    user.pilot_suspended_at = None
    user.pilot_suspended_by = None
    user.pilot_suspension_reason = None


def _days_remaining(user: User) -> int | None:
    if not user.pilot_expires_at:
        return None
    seconds = (user.pilot_expires_at - datetime.datetime.utcnow()).total_seconds()
    return max(0, int((seconds + 86399) // 86400))


def _pilot_user_payload(db, user: User, include_details: bool = False) -> dict:
    usage = usage_with_limits(db, user)
    status = pilot_effective_status(user)
    payload = {
        "id": user.id,
        "account_id": user.id,
        "organization_id": user.organization_id,
        "name": user.name,
        "email": user.email,
        "company_name": user.company_name,
        "account_status": user.pilot_access_status or ("enabled" if user.is_active else "disabled"),
        "status": status,
        "pilot_status": status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "pilot_started_at": user.pilot_started_at.isoformat() if user.pilot_started_at else None,
        "pilot_expires_at": user.pilot_expires_at.isoformat() if user.pilot_expires_at else None,
        "days_remaining": _days_remaining(user),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "last_activity_at": user.last_activity_at.isoformat() if user.last_activity_at else None,
        "usage": usage,
    }
    if include_details:
        payload.update({
            "pilot_notes": user.pilot_notes,
            "pilot_source": user.pilot_source,
            "deactivation_reason": user.pilot_deactivation_reason,
            "suspension_reason": user.pilot_suspension_reason,
        })
    return payload


@router.get("/admin/pilot-users")
def list_pilot_users(admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        user_query = db.query(User).filter(User.subscription_plan == "pilot")
        invite_query = db.query(RecruiterInvitation).filter(RecruiterInvitation.token.like("pilot_%"))
        if admin.role != "super_admin":
            user_query = user_query.filter(User.organization_id == admin.organization_id)
            invite_query = invite_query.filter(RecruiterInvitation.organization_id == admin.organization_id)

        users = user_query.order_by(User.created_at.desc()).limit(200).all()
        invitations = invite_query.order_by(RecruiterInvitation.created_at.desc()).limit(200).all()
        return {
            "users": [_pilot_user_payload(db, user) for user in users],
            "invitations": [
                {
                    "id": invitation.id,
                    "email": invitation.email,
                    "status": "invite_expired" if invitation.status == "pending" and invitation.expires_at and invitation.expires_at <= datetime.datetime.utcnow() else invitation.status,
                    "access_code": invitation.token if invitation.status == "pending" else None,
                    "signup_url": _pilot_signup_url(invitation) if invitation.status == "pending" else None,
                    "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
                    "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
                    "accepted_at": invitation.accepted_at.isoformat() if invitation.accepted_at else None,
                    "config": json.loads(invitation.pilot_config_json or "{}"),
                }
                for invitation in invitations
            ],
        }
    finally:
        db.close()


@router.post("/admin/pilot-users")
def create_pilot_user_invite(
    data: dict,
    admin: User = Depends(require_roles("admin", "super_admin")),
):
    email = _normalize_email(data.get("email"))
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid pilot user email is required")

    config = _pilot_config(data)
    db = SessionLocal()
    try:
        organization_id = _ensure_admin_organization(db, admin)
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            if admin.role != "super_admin" and existing_user.organization_id not in {None, organization_id}:
                raise HTTPException(status_code=403, detail="User belongs to another organization")
            existing_user.organization_id = organization_id
            existing_user.subscription_status = "active"
            existing_user.subscription_plan = "pilot"
            existing_user.subscription_started_at = datetime.datetime.utcnow()
            existing_user.is_active = True
            if data.get("name"):
                existing_user.name = str(data.get("name")).strip()
            _apply_pilot_config(existing_user, config)
            write_audit_log(
                db,
                action="pilot_user.activated",
                entity_type="user",
                entity_id=existing_user.id,
                actor_user_id=admin.id,
                organization_id=organization_id,
                metadata={"email": email, "config": config},
            )
            db.commit()
            return {"status": "active", "email": email, "message": "Existing user activated as a pilot user"}

        invitation = (
            db.query(RecruiterInvitation)
            .filter(
                RecruiterInvitation.email == email,
                RecruiterInvitation.organization_id == organization_id,
                RecruiterInvitation.status == "pending",
            )
            .first()
        )
        if not invitation:
            invitation = RecruiterInvitation(
                organization_id=organization_id,
                invited_by_user_id=admin.id,
                email=email,
                role="recruiter",
                status="pending",
            )
            db.add(invitation)
        invitation.token = "pilot_" + secrets.token_urlsafe(28)
        invitation.expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        invitation.pilot_config_json = json.dumps(config)
        db.flush()
        write_audit_log(
            db,
            action="pilot_user.invited",
            entity_type="invitation",
            entity_id=invitation.id,
            actor_user_id=admin.id,
            organization_id=organization_id,
            metadata={"email": email, "config": config},
        )
        db.commit()
        db.refresh(invitation)
        email_sent = False
        email_provider = None
        try:
            delivery = _send_pilot_invitation_email(invitation, admin)
            email_sent = True
            email_provider = delivery.get("provider")
            write_audit_log(
                db,
                action="pilot_user.invitation_email_sent",
                entity_type="invitation",
                entity_id=invitation.id,
                actor_user_id=admin.id,
                organization_id=organization_id,
                metadata={"email": email, "provider": email_provider},
            )
        except Exception as exc:
            write_audit_log(
                db,
                action="pilot_user.invitation_email_failed",
                entity_type="invitation",
                entity_id=invitation.id,
                actor_user_id=admin.id,
                organization_id=organization_id,
                metadata={"email": email, "error": str(exc)[:500]},
            )
        db.commit()
        return {
            "status": "pending",
            "email": email,
            "access_code": invitation.token,
            "signup_url": _pilot_signup_url(invitation),
            "expires_at": invitation.expires_at.isoformat(),
            "email_sent": email_sent,
            "email_provider": email_provider,
            "message": "Pilot invitation emailed" if email_sent else "Pilot invitation created, but email delivery failed",
        }
    finally:
        db.close()


@router.post("/admin/pilot-users/{user_id}/deactivate")
def deactivate_pilot_user(user_id: str, data: dict | None = None, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        pilot = db.query(User).filter(User.id == user_id, User.subscription_plan == "pilot").first()
        if not pilot:
            raise HTTPException(status_code=404, detail="Pilot user not found")
        if admin.role != "super_admin" and pilot.organization_id != admin.organization_id:
            raise HTTPException(status_code=403, detail="Pilot user belongs to another organization")
        pilot.is_active = False
        pilot.subscription_status = "inactive"
        pilot.pilot_status = "deactivated"
        pilot.pilot_access_status = "disabled"
        pilot.pilot_deactivated_at = datetime.datetime.utcnow()
        pilot.pilot_deactivated_by = admin.id
        pilot.pilot_deactivation_reason = str((data or {}).get("reason") or "Manual deactivation").strip()
        write_audit_log(
            db,
            action="pilot_user.deactivated",
            entity_type="user",
            entity_id=pilot.id,
            actor_user_id=admin.id,
            organization_id=pilot.organization_id,
            metadata={"email": pilot.email, "reason": pilot.pilot_deactivation_reason},
        )
        db.commit()
        return {"message": "Pilot access deactivated", "id": pilot.id}
    finally:
        db.close()


def _admin_pilot(db, user_id: str, admin: User) -> User:
    pilot = db.query(User).filter(User.id == user_id, User.subscription_plan == "pilot").with_for_update().first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot user not found")
    if admin.role != "super_admin" and pilot.organization_id != admin.organization_id:
        raise HTTPException(status_code=403, detail="Pilot user belongs to another organization")
    return pilot


@router.get("/admin/pilot-users/{user_id}")
def get_pilot_user(user_id: str, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        pilot = _admin_pilot(db, user_id, admin)
        payload = _pilot_user_payload(db, pilot, include_details=True)
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "user", AuditLog.entity_id == pilot.id)
            .order_by(AuditLog.created_at.desc())
            .limit(100)
            .all()
        )
        payload["history"] = [
            {
                "id": log.id,
                "action": log.action,
                "admin_id": log.actor_user_id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "changes": json.loads(log.metadata_json or "{}"),
            }
            for log in logs
        ]
        return payload
    finally:
        db.close()


@router.patch("/admin/pilot-users/{user_id}")
def update_pilot_user(user_id: str, data: dict, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        pilot = _admin_pilot(db, user_id, admin)
        old = {
            "company_name": pilot.company_name,
            "max_total_jobs": pilot.max_total_jobs,
            "max_active_jobs": pilot.max_active_jobs,
            "max_resumes_per_job": pilot.max_resumes_per_job,
            "max_total_resumes": pilot.max_total_resumes,
            "pilot_expires_at": pilot.pilot_expires_at.isoformat() if pilot.pilot_expires_at else None,
            "pilot_notes": pilot.pilot_notes,
            "pilot_source": pilot.pilot_source,
        }
        total_jobs = _pilot_limit(data, "max_total_jobs", pilot.max_total_jobs)
        active_jobs = _pilot_limit(data, "max_active_jobs", pilot.max_active_jobs)
        if total_jobs is not None and active_jobs is not None and active_jobs > total_jobs:
            raise HTTPException(status_code=400, detail="Maximum active jobs cannot exceed total jobs allowed")
        pilot.max_total_jobs = total_jobs
        pilot.max_active_jobs = active_jobs
        pilot.max_resumes_per_job = _pilot_limit(data, "max_resumes_per_job", pilot.max_resumes_per_job)
        pilot.max_total_resumes = _pilot_limit(data, "max_total_resumes", pilot.max_total_resumes)
        if "company_name" in data:
            pilot.company_name = str(data.get("company_name") or "").strip() or None
        if "pilot_notes" in data:
            pilot.pilot_notes = str(data.get("pilot_notes") or "").strip() or None
        if "pilot_source" in data:
            pilot.pilot_source = str(data.get("pilot_source") or "manual").strip().lower()
        if "pilot_expires_at" in data:
            expires = _parse_datetime(data.get("pilot_expires_at"))
            if not expires or (pilot.pilot_started_at and expires <= pilot.pilot_started_at):
                raise HTTPException(status_code=400, detail="Pilot expiry must be after the start date")
            pilot.pilot_expires_at = expires
        new = {
            "company_name": pilot.company_name,
            "max_total_jobs": pilot.max_total_jobs,
            "max_active_jobs": pilot.max_active_jobs,
            "max_resumes_per_job": pilot.max_resumes_per_job,
            "max_total_resumes": pilot.max_total_resumes,
            "pilot_expires_at": pilot.pilot_expires_at.isoformat() if pilot.pilot_expires_at else None,
            "pilot_notes": pilot.pilot_notes,
            "pilot_source": pilot.pilot_source,
        }
        write_audit_log(db, action="pilot_user.updated", entity_type="user", entity_id=pilot.id, actor_user_id=admin.id, organization_id=pilot.organization_id, metadata={"old": old, "new": new})
        db.commit()
        return _pilot_user_payload(db, pilot, include_details=True)
    finally:
        db.close()


@router.post("/admin/pilot-users/{user_id}/extend")
def extend_pilot_user(user_id: str, data: dict, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        pilot = _admin_pilot(db, user_id, admin)
        old_expiry = pilot.pilot_expires_at
        new_expiry = _parse_datetime(data.get("pilot_expires_at"))
        if not new_expiry:
            try:
                days = int(data.get("days"))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="Choose +7, +14, +30 days or a custom date") from exc
            if days not in {7, 14, 30}:
                raise HTTPException(status_code=400, detail="Extension must be 7, 14, or 30 days")
            new_expiry = max(old_expiry or datetime.datetime.utcnow(), datetime.datetime.utcnow()) + datetime.timedelta(days=days)
        if new_expiry <= datetime.datetime.utcnow():
            raise HTTPException(status_code=400, detail="New expiry must be in the future")
        pilot.pilot_expires_at = new_expiry
        if pilot_effective_status(pilot) == "expired":
            pilot.pilot_status = "active"
        write_audit_log(db, action="pilot_user.access_extended", entity_type="user", entity_id=pilot.id, actor_user_id=admin.id, organization_id=pilot.organization_id, metadata={"old_expiry": old_expiry.isoformat() if old_expiry else None, "new_expiry": new_expiry.isoformat()})
        db.commit()
        return _pilot_user_payload(db, pilot, include_details=True)
    finally:
        db.close()


@router.post("/admin/pilot-users/{user_id}/suspend")
def suspend_pilot_user(user_id: str, data: dict, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        pilot = _admin_pilot(db, user_id, admin)
        pilot.pilot_status = "suspended"
        pilot.pilot_access_status = "disabled"
        pilot.pilot_suspended_at = datetime.datetime.utcnow()
        pilot.pilot_suspended_by = admin.id
        pilot.pilot_suspension_reason = str(data.get("reason") or "Temporary suspension").strip()
        write_audit_log(db, action="pilot_user.suspended", entity_type="user", entity_id=pilot.id, actor_user_id=admin.id, organization_id=pilot.organization_id, metadata={"reason": pilot.pilot_suspension_reason})
        db.commit()
        return _pilot_user_payload(db, pilot, include_details=True)
    finally:
        db.close()


@router.post("/admin/pilot-users/{user_id}/reactivate")
def reactivate_pilot_user(user_id: str, data: dict | None = None, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        pilot = _admin_pilot(db, user_id, admin)
        new_expiry = _parse_datetime((data or {}).get("pilot_expires_at")) or pilot.pilot_expires_at
        if not new_expiry or new_expiry <= datetime.datetime.utcnow():
            raise HTTPException(status_code=400, detail="A future expiry date is required to reactivate this pilot")
        pilot.pilot_expires_at = new_expiry
        pilot.pilot_status = "active"
        pilot.pilot_access_status = "enabled"
        pilot.is_active = True
        pilot.subscription_status = "active"
        pilot.pilot_deactivated_at = None
        pilot.pilot_deactivated_by = None
        pilot.pilot_deactivation_reason = None
        pilot.pilot_suspended_at = None
        pilot.pilot_suspended_by = None
        pilot.pilot_suspension_reason = None
        write_audit_log(db, action="pilot_user.reactivated", entity_type="user", entity_id=pilot.id, actor_user_id=admin.id, organization_id=pilot.organization_id, metadata={"pilot_expires_at": new_expiry.isoformat()})
        db.commit()
        return _pilot_user_payload(db, pilot, include_details=True)
    finally:
        db.close()


@router.post("/admin/pilot-invitations/{invitation_id}/resend")
def resend_pilot_invitation(invitation_id: str, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        invitation = db.query(RecruiterInvitation).filter(RecruiterInvitation.id == invitation_id, RecruiterInvitation.token.like("pilot_%")).with_for_update().first()
        if not invitation:
            raise HTTPException(status_code=404, detail="Pilot invitation not found")
        if admin.role != "super_admin" and invitation.organization_id != admin.organization_id:
            raise HTTPException(status_code=403, detail="Pilot invitation belongs to another organization")
        if invitation.status == "accepted":
            raise HTTPException(status_code=409, detail="Accepted invitations cannot be resent")
        invitation.status = "pending"
        invitation.token = "pilot_" + secrets.token_urlsafe(28)
        invitation.expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        db.commit()
        delivery = _send_pilot_invitation_email(invitation, admin)
        write_audit_log(db, action="pilot_user.invitation_resent", entity_type="invitation", entity_id=invitation.id, actor_user_id=admin.id, organization_id=invitation.organization_id, metadata={"email": invitation.email, "provider": delivery.get("provider")})
        db.commit()
        return {"message": "Pilot invitation resent", "expires_at": invitation.expires_at.isoformat(), "signup_url": _pilot_signup_url(invitation)}
    finally:
        db.close()


@router.post("/admin/pilot-invitations/{invitation_id}/cancel")
def cancel_pilot_invitation(invitation_id: str, admin: User = Depends(require_roles("admin", "super_admin"))):
    db = SessionLocal()
    try:
        invitation = db.query(RecruiterInvitation).filter(RecruiterInvitation.id == invitation_id, RecruiterInvitation.token.like("pilot_%")).with_for_update().first()
        if not invitation:
            raise HTTPException(status_code=404, detail="Pilot invitation not found")
        if admin.role != "super_admin" and invitation.organization_id != admin.organization_id:
            raise HTTPException(status_code=403, detail="Pilot invitation belongs to another organization")
        if invitation.status == "accepted":
            raise HTTPException(status_code=409, detail="An activated account cannot be cancelled as an invitation")
        invitation.status = "cancelled"
        write_audit_log(db, action="pilot_user.invitation_cancelled", entity_type="invitation", entity_id=invitation.id, actor_user_id=admin.id, organization_id=invitation.organization_id, metadata={"email": invitation.email})
        db.commit()
        return {"message": "Pilot invitation cancelled", "id": invitation.id}
    finally:
        db.close()


# ---------------- SIGNUP ----------------

@router.post("/signup")
def signup(data: AuthRequest):

    db = SessionLocal()
    email = _normalize_email(data.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    _validate_password_strength(data.password)

    try:
        hashed_password = hash_password(data.password)
        try:
            invitation = _validate_signup_access(db, email, data.access_code)
        except HTTPException as exc:
            if exc.status_code == 402:
                pending_token = _pending_email_signup_token((data.name or email.split("@")[0]).strip(), email, hashed_password)
                raise HTTPException(
                    status_code=402,
                    detail={
                        "message": "Paid access required. Choose a plan to complete account creation.",
                        "pending_signup_token": pending_token,
                        "email": email,
                        "name": (data.name or email.split("@")[0]).strip(),
                    },
                ) from exc
            raise

        # check existing user
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=400, detail="User already exists")

        user = User(
            name=(data.name or email.split("@")[0]).strip(),
            email=email,
            password=hashed_password,
            role="recruiter",
            is_active=True,
            subscription_status="active",
            subscription_plan="manual",
            subscription_started_at=datetime.datetime.utcnow(),
        )
        _apply_invitation_to_user(invitation, user)

        db.add(user)
        _ensure_user_organization(db, user)
        db.commit()

        return {"message": "Account created successfully"}
    finally:
        db.close()


# ---------------- LOGIN ----------------

@router.post("/login")
def login(data: AuthRequest, response: Response):

    db = SessionLocal()
    email = _normalize_email(data.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    try:
        user = db.query(User).filter(User.email == email).first()

        if not user:
            raise HTTPException(status_code=400, detail="Invalid credentials")

        if not getattr(user, "is_active", True) and not is_pilot(user):
            raise HTTPException(status_code=403, detail="Account is disabled")

        # check password
        if not verify_password(data.password, user.password):
            raise HTTPException(status_code=400, detail="Invalid credentials")

        user.last_login_at = datetime.datetime.utcnow()
        _ensure_user_organization(db, user)
        pilot_access = pilot_access_payload(user) if is_pilot(user) else None
        workspace_access = not pilot_access or pilot_access["status"] in {"active", "expiring_soon"}
        db.commit()

        # create token
        token = create_access_token(
            {
                "user_id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role or "recruiter",
                "organization_id": user.organization_id,
            }
        )
        csrf_token = secrets.token_urlsafe(24)
        response.set_cookie(
            "ats_access_token",
            token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            max_age=settings.access_token_minutes * 60,
        )
        response.set_cookie(
            settings.csrf_cookie_name,
            csrf_token,
            httponly=False,
            secure=settings.secure_cookies,
            samesite="lax",
            max_age=settings.access_token_minutes * 60,
        )

        return {
            "token": token,
            "csrf_token": csrf_token,
            "name": user.name,
            "email": user.email,
            "role": user.role or "recruiter",
            "organization_id": user.organization_id,
            "subscription_status": user.subscription_status or "unpaid",
            "subscription_plan": user.subscription_plan,
            "workspace_access": workspace_access,
            "pilot_access": pilot_access,
        }
    finally:
        db.close()


def _generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _send_reset_email(to_email: str, temp_password: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or smtp_user

    if not (smtp_host and smtp_user and smtp_password and sender):
        return False

    body = (
        "Hi,\n\n"
        "Your AI ATS password has been reset.\n\n"
        f"Temporary password: {temp_password}\n\n"
        "Please sign in and update your password after login.\n\n"
        "AI ATS Recruiting Team"
    )

    msg = MIMEText(body)
    msg["Subject"] = "AI ATS Password Reset"
    msg["From"] = sender
    msg["To"] = to_email

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)

    return True


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest):
    email = (data.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="No account found for this email")

        temp_password = _generate_temp_password()
        user.password = hash_password(temp_password)
        db.commit()

        mail_sent = _send_reset_email(email, temp_password)
        response = {
            "message": "Password reset successfully",
            "mail_sent": mail_sent,
        }

        if not mail_sent:
            response["temporary_password"] = temp_password
            response["message"] = "Password reset successfully. Email is not configured, so use the temporary password shown here."

        return response
    finally:
        db.close()


# ---------------- GOOGLE AUTH ----------------

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/google-callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5500")
SIGNUP_PAGE = settings.frontend_signup_path
LOGIN_PAGE = settings.frontend_login_path
PRICING_PAGE = settings.frontend_pricing_path
GMAIL_CONNECT_SCOPE = (
    "openid email profile "
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/forms.body "
    "https://www.googleapis.com/auth/forms.responses.readonly"
)


def _google_oauth_configured() -> bool:
    return bool(
        GOOGLE_CLIENT_ID
        and GOOGLE_CLIENT_SECRET
        and "paste-your" not in GOOGLE_CLIENT_ID
        and "paste-your" not in GOOGLE_CLIENT_SECRET
    )


def _frontend_page_url(path: str, query: str = "") -> str:
    clean_path = (path or "").lstrip("/")
    url = f"{FRONTEND_URL.rstrip('/')}/{clean_path}"
    return f"{url}?{query}" if query else url


def _pending_google_signup_token(email: str, name: str | None) -> str:
    return jwt.encode(
        {
            "purpose": "pending_google_signup",
            "email": email,
            "name": name or email.split("@")[0],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=45),
        },
        SECRET,
        algorithm=settings.jwt_algorithm,
    )


def _pending_email_signup_token(name: str, email: str, password_hash: str) -> str:
    return jwt.encode(
        {
            "purpose": "pending_email_signup",
            "name": name or email.split("@")[0],
            "email": email,
            "password_hash": password_hash,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=45),
        },
        SECRET,
        algorithm=settings.jwt_algorithm,
    )


def _decode_pending_google_signup(token: str) -> dict:
    payload = jwt.decode(token, SECRET, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") not in {"pending_google_signup", "pending_email_signup"} or not payload.get("email"):
        raise ValueError("Invalid pending signup token")
    return payload


def _login_redirect_for_user(user: User, name: str | None = None) -> RedirectResponse:
    if is_pilot(user):
        access = pilot_access_payload(user)
        if access["status"] not in {"active", "expiring_soon"}:
            query = urllib.parse.urlencode({"pilot_status": access["status"], "pilot_expires_at": access.get("pilot_expires_at") or ""})
            return RedirectResponse(_frontend_page_url(LOGIN_PAGE, query))
    token = create_access_token(
        {
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role or "recruiter",
            "organization_id": user.organization_id,
        }
    )
    redirect = (
        f"{FRONTEND_URL.rstrip('/')}/index.html"
        f"?token={urllib.parse.quote(token)}"
        f"&name={urllib.parse.quote(name or user.name or 'Recruiter')}"
        f"&email={urllib.parse.quote(user.email)}"
    )
    return RedirectResponse(url=redirect)


def _pricing_redirect_for_pending_signup(email: str, name: str | None, error: str = "paid_access_required") -> RedirectResponse:
    pending_token = _pending_google_signup_token(email, name)
    query = urllib.parse.urlencode(
        {
            "error": error,
            "email": email,
            "name": name or "",
            "pending_signup_token": pending_token,
            "provider": "google",
        }
    )
    return RedirectResponse(_frontend_page_url(PRICING_PAGE, query))


def _activate_subscription(user: User, plan: str | None) -> None:
    user.subscription_status = "active"
    user.subscription_plan = plan or user.subscription_plan or "agency-pro"
    user.subscription_started_at = datetime.datetime.utcnow()
    user.is_active = True


# ---------------- GOOGLE LOGIN ----------------

@router.get("/auth-providers")
def auth_providers():
    return {
        "google_enabled": _google_oauth_configured(),
        "email_password_enabled": True,
        "signup_mode": settings.signup_mode,
        "paid_signup_required": settings.signup_mode in {"access_code", "paid", "disabled"},
        "checkout_url": settings.checkout_url or "",
        "sales_contact_email": settings.sales_contact_email,
    }


@router.get("/google-login")
def google_login(mode: str = "login", access_code: str = None):

    if not _google_oauth_configured():
        target = SIGNUP_PAGE if mode == "signup" else LOGIN_PAGE
        return RedirectResponse(
            _frontend_page_url(target, "error=google_not_configured")
        )

    mode = "signup" if mode == "signup" else "login"
    state = jwt.encode(
        {
            "purpose": "google_oauth",
            "mode": mode,
            "access_code": _clean_access_code(access_code),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        },
        SECRET,
        algorithm=settings.jwt_algorithm,
    )

    query = urllib.parse.urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account consent",
            "state": state,
        }
    )

    google_url = "https://accounts.google.com/o/oauth2/v2/auth?" + query

    return RedirectResponse(google_url)


# ---------------- GOOGLE CALLBACK ----------------

@router.get("/google-callback")
def google_callback(code: str, state: str = None):

    if not _google_oauth_configured():
        return RedirectResponse(
            _frontend_page_url(LOGIN_PAGE, "error=google_not_configured")
        )

    try:
        state_payload = jwt.decode(state, SECRET, algorithms=[settings.jwt_algorithm])
        purpose = state_payload.get("purpose")
        if purpose not in ("google_oauth", "gmail_connect"):
            raise ValueError("Invalid state")
        mode = state_payload.get("mode") or "login"
    except Exception:
        return RedirectResponse(
            _frontend_page_url(LOGIN_PAGE, "error=google_auth_failed")
        )

    token_url = "https://oauth2.googleapis.com/token"

    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    token_res = requests.post(token_url, data=data, timeout=20)
    token_json = token_res.json()

    access_token = token_json.get("access_token")

    if not access_token:
        target = SIGNUP_PAGE if mode == "signup" else LOGIN_PAGE
        return RedirectResponse(
            _frontend_page_url(target, "error=google_auth_failed")
        )

    userinfo = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    ).json()

    email = userinfo.get("email")
    name = userinfo.get("name")

    if not email:
        target = SIGNUP_PAGE if mode == "signup" else LOGIN_PAGE
        return RedirectResponse(
            _frontend_page_url(target, "error=google_auth_failed")
        )

    db = SessionLocal()

    requested_email = state_payload.get("email")
    strict_sender_match = state_payload.get("strict_sender_match", True)
    if purpose == "gmail_connect" and strict_sender_match and requested_email and requested_email.lower() != email.lower():
        db.close()
        return RedirectResponse(
            f"{FRONTEND_URL.rstrip('/')}/index.html?error=gmail_email_mismatch"
        )

    app_user_email = (state_payload.get("app_user_email") or "").strip().lower()
    user = db.query(User).filter(User.email == app_user_email).first() if purpose == "gmail_connect" and app_user_email else None
    if not user:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        if purpose == "gmail_connect":
            db.close()
            return RedirectResponse(
                _frontend_page_url(LOGIN_PAGE, "error=google_account_not_found")
            )
        if mode != "signup":
            db.close()
            return RedirectResponse(
                _frontend_page_url(LOGIN_PAGE, "error=google_account_not_found")
            )

        try:
            invitation = _validate_signup_access(db, email.lower(), state_payload.get("access_code"))
        except HTTPException:
            db.close()
            return _pricing_redirect_for_pending_signup(email.lower(), name)

        hashed_password = hash_password("google_auth")

        user = User(name=name, email=email, password=hashed_password, role="recruiter")
        _apply_invitation_to_user(invitation, user)
        _activate_subscription(user, "pilot" if invitation and (invitation.token or "").startswith("pilot_") else "manual")
        db.add(user)
        _ensure_user_organization(db, user)
        db.commit()

    user.google_access_token = access_token
    if token_json.get("refresh_token"):
        user.google_refresh_token = token_json.get("refresh_token")
    elif purpose == "gmail_connect":
        user.google_refresh_token = None
    expires_in = int(token_json.get("expires_in") or 3600)
    user.google_token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in - 60)
    user.auth_provider = "google"
    _ensure_user_organization(db, user)
    if purpose == "gmail_connect":
        user.outreach_sender_email = email.lower()
    db.commit()

    if purpose == "gmail_connect":
        db.close()
        return RedirectResponse(
            f"{FRONTEND_URL.rstrip('/')}/index.html?gmail_connected=1&email={urllib.parse.quote(email)}"
        )

    # 🔐 JWT token with expiry
    token = create_access_token(
        {
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role or "recruiter",
            "organization_id": user.organization_id,
        }
    )

    # 👉 redirect to frontend
    redirect = (
        f"{FRONTEND_URL.rstrip('/')}/index.html"
        f"?token={urllib.parse.quote(token)}"
        f"&name={urllib.parse.quote(name or 'Recruiter')}"
        f"&email={urllib.parse.quote(email)}"
    )
    return RedirectResponse(url=redirect)


@router.get("/paid-signup-complete")
def paid_signup_complete(pending_signup_token: str, access_code: str = None, plan: str = None):
    try:
        payload = _decode_pending_google_signup(pending_signup_token)
    except Exception:
        return RedirectResponse(_frontend_page_url(PRICING_PAGE, "error=paid_access_required"))

    email = _normalize_email(payload.get("email"))
    name = payload.get("name") or email.split("@")[0]
    password_hash = payload.get("password_hash")
    provider = "email" if payload.get("purpose") == "pending_email_signup" else "google"
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                name=name,
                email=email,
                password=password_hash or hash_password("google_auth"),
                role="recruiter",
                is_active=True,
                auth_provider=provider,
            )
            db.add(user)

        _ensure_user_organization(db, user)

        user.auth_provider = user.auth_provider or provider
        _activate_subscription(user, plan)
        db.commit()
        db.refresh(user)
        return _login_redirect_for_user(user, name)
    finally:
        db.close()


@router.get("/gmail-connect")
def gmail_connect(email: str = None, app_email: str = None, strict_sender: str = "1"):
    if not _google_oauth_configured():
        return RedirectResponse(
            f"{FRONTEND_URL.rstrip('/')}/index.html?error=google_not_configured"
        )

    state = jwt.encode(
        {
            "purpose": "gmail_connect",
            "email": email or "",
            "app_user_email": app_email or "",
            "strict_sender_match": str(strict_sender).lower() not in ("0", "false", "no"),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        },
        SECRET,
        algorithm=settings.jwt_algorithm,
    )

    query = urllib.parse.urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": GMAIL_CONNECT_SCOPE,
            "access_type": "offline",
            "include_granted_scopes": "false",
            "prompt": "select_account consent",
            "state": state,
        }
    )

    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + query)
