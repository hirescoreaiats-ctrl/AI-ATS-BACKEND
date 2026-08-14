from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status

from backend.core.security import get_current_user
from backend.core.config import get_settings
from backend.database import get_db
from backend.models import User
from backend.requirement_platform.constants import ADMIN_CAPABILITIES, CAPABILITIES_BY_PROFILE_TYPE
from backend.requirement_platform.models import ProfileCapability, RequirementPlatformProfile


def active_user(request: Request, user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_active", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account access is suspended")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not (request.headers.get("Authorization") or "").lower().startswith("bearer "):
        settings = get_settings()
        cookie_token = request.cookies.get(settings.csrf_cookie_name) or ""
        header_token = request.headers.get("X-CSRF-Token") or ""
        if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return user


def profile_for_user(db, user: User, *, include_deleted: bool = False) -> RequirementPlatformProfile | None:
    query = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.user_id == user.id)
    if not include_deleted:
        query = query.filter(RequirementPlatformProfile.deleted_at.is_(None))
    return query.first()


def marketplace_profile(db=Depends(get_db), user: User = Depends(active_user)) -> RequirementPlatformProfile:
    profile = profile_for_user(db, user)
    if not profile:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Complete your Requirement Platform profile")
    if profile.status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requirement Platform access is suspended")
    return profile


def verified_marketplace_profile(profile: RequirementPlatformProfile = Depends(marketplace_profile)) -> RequirementPlatformProfile:
    if profile.status != "verified":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="HireScore verification is required for this action")
    return profile


def effective_capabilities(db, user: User, profile: RequirementPlatformProfile | None) -> set[str]:
    if (getattr(user, "role", "") or "").lower() == "admin":
        return set(ADMIN_CAPABILITIES) | {item for values in CAPABILITIES_BY_PROFILE_TYPE.values() for item in values}
    if not profile:
        return set()
    capabilities = set(CAPABILITIES_BY_PROFILE_TYPE.get(profile.profile_type, set()))
    if profile.profile_type == "hr_professional" and profile.is_available_for_sourcing:
        capabilities.update({"sourcing:request", "sourcing:respond", "candidate:submit"})
    overrides = db.query(ProfileCapability).filter(ProfileCapability.profile_id == profile.id).all()
    for override in overrides:
        if override.enabled:
            capabilities.add(override.capability)
        else:
            capabilities.discard(override.capability)
    return capabilities


def require_capability(capability: str, *, verified: bool = True):
    def dependency(db=Depends(get_db), user: User = Depends(active_user)):
        profile = profile_for_user(db, user)
        is_admin = (getattr(user, "role", "") or "").lower() == "admin"
        if is_admin and not capability.startswith("admin:") and not profile:
            raise HTTPException(status_code=403, detail="A Requirement Platform profile is required for marketplace actions")
        if not is_admin:
            if not profile:
                raise HTTPException(status_code=403, detail="Complete your Requirement Platform profile")
            if profile.status == "suspended":
                raise HTTPException(status_code=403, detail="Requirement Platform access is suspended")
            if verified and profile.status != "verified":
                raise HTTPException(status_code=403, detail="HireScore verification is required for this action")
        if capability not in effective_capabilities(db, user, profile):
            raise HTTPException(status_code=403, detail="Insufficient Requirement Platform permission")
        return user, profile

    return dependency
