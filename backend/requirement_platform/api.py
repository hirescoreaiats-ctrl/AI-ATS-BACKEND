from __future__ import annotations

from datetime import datetime, timedelta
import json
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from backend.database import get_db
from backend.models import AuditLog, Organization, User
from backend.core.config import get_settings
from backend.repositories.audit_repository import write_audit_log
from backend.requirement_platform.constants import PROFILE_STATUSES
from backend.requirement_platform.files import candidate_fingerprint, fingerprint, normalize_email, normalize_phone, store_candidate_resume
from backend.requirement_platform.matching import match_requirement_to_profile, safe_json
from backend.requirement_platform.models import (
    AgencyProfileDetail,
    CandidateSubmission,
    HRProfileDetail,
    MarketplaceReport,
    MarketplaceRequirement,
    ProfessionalVerification,
    ProfileTaxonomyValue,
    RecruiterProfileDetail,
    RequirementInvitation,
    RequirementPlatformProfile,
    RequirementSkill,
    SourcingAssignment,
    SourcingRequest,
    TrustScore,
    VendorProfileDetail,
)
from backend.requirement_platform.permissions import active_user, profile_for_user, require_capability
from backend.requirement_platform.schemas import (
    CandidateStatusUpdate,
    InvitationCreate,
    ProfileUpsert,
    ReportCreate,
    RequirementCreate,
    RequirementUpdate,
    SourceRequestCreate,
    StatusAction,
    VerificationDecision,
    VerificationSubmit,
)
from backend.services.storage import download_stored_file
from backend.utils.sanitize import sanitize_text


router = APIRouter(prefix="/requirement-platform", tags=["requirement-platform"])
admin_router = APIRouter(prefix="/admin/requirement-platform", tags=["requirement-platform-admin"])

DETAIL_MODELS = {
    "recruiter": RecruiterProfileDetail,
    "hr_professional": HRProfileDetail,
    "vendor": VendorProfileDetail,
    "recruitment_agency": AgencyProfileDetail,
}


def utcnow() -> datetime:
    return datetime.utcnow()


def clean(value, limit=5000):
    return sanitize_text(value, limit) if value is not None else None


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def page_values(page: int, page_size: int) -> tuple[int, int]:
    return max(page, 1), min(max(page_size, 1), 50)


def require_admin(user: User = Depends(active_user)) -> User:
    if (user.role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def audit(db, user, action: str, entity_type: str, entity_id: str | None, organization_id: str | None = None, metadata: dict | None = None):
    write_audit_log(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=user.id,
        organization_id=organization_id,
        metadata=metadata,
    )


def enforce_daily_limit(db, user: User, action: str, limit: int):
    if limit <= 0 or (user.role or "").lower() == "admin":
        return
    count = db.query(AuditLog.id).filter(AuditLog.actor_user_id == user.id, AuditLog.action == action, AuditLog.created_at >= utcnow() - timedelta(days=1)).count()
    if count >= limit:
        raise HTTPException(status_code=429, detail="Daily marketplace action limit reached")


def verification_badges(db, profile_id: str) -> list[str]:
    return [
        row.verification_type
        for row in db.query(ProfessionalVerification)
        .filter(ProfessionalVerification.profile_id == profile_id, ProfessionalVerification.status == "approved")
        .all()
    ]


def taxonomy_map(db, profile_id: str) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    rows = db.query(ProfileTaxonomyValue).filter(ProfileTaxonomyValue.profile_id == profile_id).all()
    for row in rows:
        result.setdefault(row.taxonomy, []).append({"value": row.value, "experience_years": row.experience_years})
    return result


def safe_profile(db, profile: RequirementPlatformProfile) -> dict:
    trust = db.query(TrustScore).filter(TrustScore.profile_id == profile.id).first()
    taxonomy = taxonomy_map(db, profile.id)
    return {
        "id": profile.id,
        "profile_type": profile.profile_type,
        "display_name": profile.display_name,
        "professional_headline": profile.professional_headline,
        "profile_photo_url": f"/api/v1/requirement-platform/profiles/{profile.id}/photo" if profile.profile_photo_key else None,
        "location": {"city": profile.city, "state_region": profile.state_region, "country": profile.country},
        "linkedin_provided": bool(profile.linkedin_url),
        "website_url": profile.website_url,
        "availability": profile.availability,
        "preferred_engagements": safe_json(profile.preferred_engagements_json, []),
        "hire_score_verified": profile.status == "verified",
        "verification_badges": verification_badges(db, profile.id),
        "trust_score": trust.score if trust else None,
        "taxonomy": taxonomy,
        "is_available_for_sourcing": profile.is_available_for_sourcing,
    }


def own_profile_response(db, profile: RequirementPlatformProfile) -> dict:
    result = safe_profile(db, profile)
    result.update(
        {
            "status": profile.status,
            "professional_email": profile.professional_email,
            "phone": profile.phone,
            "linkedin_url": profile.linkedin_url,
            "profile_completeness": profile.profile_completeness,
            "organization_id": profile.organization_id,
        }
    )
    detail_model = DETAIL_MODELS[profile.profile_type]
    detail = db.query(detail_model).filter(detail_model.profile_id == profile.id).first()
    if detail:
        result["details"] = {
            column.name: safe_json(getattr(detail, column.name), []) if column.name.endswith("_json") else getattr(detail, column.name)
            for column in detail.__table__.columns
            if column.name != "profile_id"
        }
    else:
        result["details"] = {}
    return result


def profile_completeness(data: ProfileUpsert) -> int:
    checks = [
        data.display_name,
        data.professional_email,
        data.phone,
        data.country,
        data.linkedin_url,
        data.professional_headline,
        data.details,
        any(data.taxonomy.values()),
    ]
    return round(sum(bool(value) for value in checks) / len(checks) * 100)


def ensure_organization(db, user: User, profile: RequirementPlatformProfile, data: ProfileUpsert):
    if profile.profile_type not in {"vendor", "recruitment_agency"} or profile.organization_id:
        return
    name = data.details.get("company_name") or data.details.get("agency_name") or data.display_name
    if not name:
        return
    slug_base = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:80] or "organization"
    slug = f"{slug_base}-{profile.id[:8]}"
    org = Organization(name=clean(str(name), 180), slug=slug, plan="requirement-platform")
    db.add(org)
    db.flush()
    profile.organization_id = org.id
    user.organization_id = org.id


def sync_detail(db, profile: RequirementPlatformProfile, details: dict):
    detail_model = DETAIL_MODELS[profile.profile_type]
    record = db.query(detail_model).filter(detail_model.profile_id == profile.id).first()
    if not record:
        record = detail_model(profile_id=profile.id)
        db.add(record)
    allowed = {column.name: column for column in detail_model.__table__.columns if column.name != "profile_id"}
    for key, value in details.items():
        if key not in allowed:
            continue
        if key.endswith("_json"):
            value = json_text(value)
        elif isinstance(value, str):
            value = clean(value, 5000)
        setattr(record, key, value)


def sync_taxonomy(db, profile: RequirementPlatformProfile, taxonomy: dict):
    db.query(ProfileTaxonomyValue).filter(ProfileTaxonomyValue.profile_id == profile.id).delete(synchronize_session=False)
    allowed_taxonomies = {"market", "industry", "specialization", "employment_type", "sourcing_channel", "recruitment_tool", "role_seniority", "availability_market"}
    for taxonomy_name, values in taxonomy.items():
        taxonomy_name = taxonomy_name.strip().lower()
        if taxonomy_name not in allowed_taxonomies:
            continue
        for item in values[:100]:
            if isinstance(item, dict):
                value = clean(str(item.get("value") or ""), 160)
                years = item.get("experience_years")
            else:
                value = clean(str(item), 160)
                years = None
            if value:
                db.add(ProfileTaxonomyValue(profile_id=profile.id, taxonomy=taxonomy_name, value=value, experience_years=years))


def calculate_trust_score(db, profile: RequirementPlatformProfile) -> TrustScore:
    approved = set(verification_badges(db, profile.id))
    weights = {"email": 10, "phone": 10, "linkedin": 10, "identity": 20, "employment": 15, "company_domain": 20, "agency": 20, "professional": 15}
    score = min(100, round(profile.profile_completeness * 0.2) + sum(weights.get(item, 0) for item in approved))
    record = db.query(TrustScore).filter(TrustScore.profile_id == profile.id).first() or TrustScore(profile_id=profile.id)
    record.score = score
    record.factor_breakdown_json = json_text({"approved_verifications": sorted(approved), "profile_completeness": profile.profile_completeness})
    record.calculated_at = utcnow()
    db.add(record)
    return record


@router.post("/profile")
def create_profile(data: ProfileUpsert, db=Depends(get_db), user: User = Depends(active_user)):
    existing = profile_for_user(db, user, include_deleted=True)
    if existing:
        raise HTTPException(status_code=409, detail="A Requirement Platform profile already exists")
    profile = RequirementPlatformProfile(
        user_id=user.id,
        organization_id=user.organization_id,
        profile_type=data.profile_type,
        status="profile_incomplete",
    )
    db.add(profile)
    db.flush()
    return _apply_profile_update(db, user, profile, data, created=True)


@router.patch("/profile")
def update_profile(data: ProfileUpsert, db=Depends(get_db), user: User = Depends(active_user)):
    profile = profile_for_user(db, user)
    if not profile:
        raise HTTPException(status_code=404, detail="Requirement Platform profile not found")
    if profile.status == "suspended":
        raise HTTPException(status_code=403, detail="Requirement Platform access is suspended")
    if profile.profile_type != data.profile_type and profile.status not in {"draft", "profile_incomplete"}:
        raise HTTPException(status_code=409, detail="Professional type cannot be changed after verification submission")
    profile.profile_type = data.profile_type
    return _apply_profile_update(db, user, profile, data, created=False)


def _apply_profile_update(db, user, profile, data, *, created: bool):
    for field in ["display_name", "professional_headline", "city", "state_region", "country", "linkedin_url", "website_url", "professional_email", "phone", "availability"]:
        value = getattr(data, field)
        setattr(profile, field, clean(value, 1000) if isinstance(value, str) else value)
    profile.preferred_engagements_json = json_text(data.preferred_engagements)
    profile.is_available_for_sourcing = data.is_available_for_sourcing
    profile.profile_completeness = profile_completeness(data)
    if profile.status in {"draft", "profile_incomplete", "more_information_required", "rejected"}:
        profile.status = "profile_incomplete" if profile.profile_completeness < 80 else "draft"
    ensure_organization(db, user, profile, data)
    sync_detail(db, profile, data.details)
    sync_taxonomy(db, profile, data.taxonomy)
    calculate_trust_score(db, profile)
    audit(db, user, "rp.profile_created" if created else "rp.profile_updated", "rp_profile", profile.id, profile.organization_id)
    db.commit()
    db.refresh(profile)
    return own_profile_response(db, profile)


@router.get("/profile")
def get_own_profile(db=Depends(get_db), user: User = Depends(active_user)):
    profile = profile_for_user(db, user)
    if not profile:
        raise HTTPException(status_code=404, detail="Requirement Platform profile not found")
    return own_profile_response(db, profile)


@router.get("/professionals")
def list_professionals(
    q: str = Query(default="", max_length=120),
    profile_type: str | None = None,
    country: str | None = None,
    availability: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db=Depends(get_db),
    access=Depends(require_capability("professional:view")),
):
    page, page_size = page_values(page, page_size)
    query = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.status == "verified", RequirementPlatformProfile.deleted_at.is_(None))
    if profile_type:
        query = query.filter(RequirementPlatformProfile.profile_type == profile_type)
    if country:
        query = query.filter(RequirementPlatformProfile.country == country)
    if availability:
        query = query.filter(RequirementPlatformProfile.availability == availability)
    if q:
        query = query.filter(or_(RequirementPlatformProfile.display_name.ilike(f"%{q}%"), RequirementPlatformProfile.professional_headline.ilike(f"%{q}%")))
    total = query.count()
    rows = query.order_by(RequirementPlatformProfile.verified_at.desc(), RequirementPlatformProfile.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"page": page, "page_size": page_size, "total": total, "results": [safe_profile(db, row) for row in rows]}


@router.get("/professionals/{profile_id}")
def get_professional(profile_id: str, db=Depends(get_db), access=Depends(require_capability("professional:view"))):
    profile = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.id == profile_id, RequirementPlatformProfile.status == "verified", RequirementPlatformProfile.deleted_at.is_(None)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Professional profile not found")
    return safe_profile(db, profile)


@router.post("/verification/submit")
def submit_verification(data: VerificationSubmit, db=Depends(get_db), user: User = Depends(active_user)):
    profile = profile_for_user(db, user)
    if not profile or profile.profile_completeness < 80:
        raise HTTPException(status_code=409, detail="Complete at least 80% of your profile before verification")
    if profile.status in {"under_review", "verified", "suspended"}:
        raise HTTPException(status_code=409, detail="Verification cannot be submitted in the current account state")
    created = []
    for verification_type in data.verification_types:
        record = ProfessionalVerification(profile_id=profile.id, verification_type=verification_type, status="pending", user_message=clean(data.user_message, 2000))
        db.add(record)
        db.flush()
        created.append(record.id)
    profile.status = "verification_pending"
    audit(db, user, "rp.verification_submitted", "rp_profile", profile.id, profile.organization_id, {"types": data.verification_types})
    db.commit()
    return {"status": profile.status, "verification_ids": created}


@router.post("/verification/{verification_id}/evidence")
async def upload_verification_evidence(
    verification_id: str,
    file: UploadFile = File(...),
    db=Depends(get_db),
    user: User = Depends(active_user),
):
    profile = profile_for_user(db, user)
    record = db.query(ProfessionalVerification).filter(ProfessionalVerification.id == verification_id, ProfessionalVerification.profile_id == (profile.id if profile else "")).first()
    if not record or record.status not in {"pending", "more_information_required"}:
        raise HTTPException(status_code=404, detail="Verification request not found")
    stored = await store_candidate_resume(file, f"verification-{profile.id}")
    record.evidence_key = stored["storage_key"]
    record.evidence_metadata_json = json_text({key: value for key, value in stored.items() if key != "storage_key"})
    db.commit()
    return {"message": "Verification evidence uploaded securely"}


def requirement_skills(db, requirement_id: str) -> dict[str, list[str]]:
    result = {"primary": [], "secondary": []}
    for skill in db.query(RequirementSkill).filter(RequirementSkill.requirement_id == requirement_id).all():
        result.setdefault(skill.skill_type, []).append(skill.skill)
    return result


def safe_requirement(db, requirement: MarketplaceRequirement, *, include_private: bool = False) -> dict:
    skills = requirement_skills(db, requirement.id)
    vendor = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.id == requirement.owner_profile_id).first()
    result = {
        "id": requirement.id,
        "title": requirement.title,
        "description": requirement.description,
        "primary_skills": skills.get("primary", []),
        "secondary_skills": skills.get("secondary", []),
        "industry": requirement.industry,
        "experience_min": requirement.experience_min,
        "experience_max": requirement.experience_max,
        "location": requirement.location,
        "country": requirement.country,
        "work_mode": requirement.work_mode,
        "employment_type": requirement.employment_type,
        "openings": requirement.openings,
        "salary_rate": requirement.salary_rate,
        "currency": requirement.currency,
        "contract_duration": requirement.contract_duration,
        "submission_deadline": requirement.submission_deadline,
        "expected_joining_date": requirement.expected_joining_date,
        "sourcing_partners_needed": requirement.sourcing_partners_needed,
        "submission_limit_per_partner": requirement.submission_limit_per_partner,
        "visibility": requirement.visibility,
        "status": requirement.status,
        "created_at": requirement.created_at,
        "vendor": safe_profile(db, vendor) if vendor else None,
    }
    if include_private:
        result["additional_notes"] = requirement.additional_notes
        result["us_details"] = safe_json(requirement.us_details_json, {})
    return result


def can_access_requirement(db, requirement: MarketplaceRequirement, user: User, profile: RequirementPlatformProfile | None) -> bool:
    if (user.role or "").lower() == "admin" or (profile and requirement.owner_profile_id == profile.id):
        return True
    if not profile or profile.status != "verified" or requirement.status != "open":
        return False
    if requirement.visibility == "public_marketplace":
        return True
    invited = db.query(RequirementInvitation.id).filter(RequirementInvitation.requirement_id == requirement.id, RequirementInvitation.professional_profile_id == profile.id).first()
    assigned = db.query(SourcingAssignment.id).filter(SourcingAssignment.requirement_id == requirement.id, SourcingAssignment.professional_profile_id == profile.id).first()
    if requirement.visibility == "invite_only":
        return bool(invited or assigned)
    previous_connection = db.query(SourcingAssignment.id).filter(SourcingAssignment.vendor_profile_id == requirement.owner_profile_id, SourcingAssignment.professional_profile_id == profile.id).first()
    return bool(previous_connection)


def sync_requirement_skills(db, requirement: MarketplaceRequirement, primary: list[str], secondary: list[str]):
    db.query(RequirementSkill).filter(RequirementSkill.requirement_id == requirement.id).delete(synchronize_session=False)
    seen = set()
    for skill_type, skills in [("primary", primary), ("secondary", secondary)]:
        for raw in skills:
            value = clean(raw, 160)
            normalized = " ".join((raw or "").strip().lower().split())
            key = (normalized, skill_type)
            if value and normalized and key not in seen:
                seen.add(key)
                db.add(RequirementSkill(requirement_id=requirement.id, skill=value, skill_normalized=normalized, skill_type=skill_type))


@router.post("/requirements")
def create_requirement(data: RequirementCreate, db=Depends(get_db), access=Depends(require_capability("requirement:create"))):
    user, profile = access
    enforce_daily_limit(db, user, "rp.requirement_created", get_settings().rp_daily_requirement_limit)
    requirement = MarketplaceRequirement(owner_profile_id=profile.id, organization_id=profile.organization_id)
    _copy_requirement_fields(requirement, data.model_dump(exclude={"primary_skills", "secondary_skills", "us_details"}))
    requirement.us_details_json = json_text(data.us_details)
    db.add(requirement)
    db.flush()
    sync_requirement_skills(db, requirement, data.primary_skills, data.secondary_skills)
    audit(db, user, "rp.requirement_created", "rp_requirement", requirement.id, requirement.organization_id)
    db.commit()
    db.refresh(requirement)
    return safe_requirement(db, requirement, include_private=True)


def _copy_requirement_fields(requirement, values: dict):
    allowed = {column.name for column in MarketplaceRequirement.__table__.columns} - {"id", "owner_profile_id", "organization_id", "created_at", "updated_at", "closed_at", "deleted_at", "ats_job_id"}
    for key, value in values.items():
        if key in allowed:
            setattr(requirement, key, clean(value, 30000) if isinstance(value, str) else value)


@router.get("/requirements/recommended")
def recommended_requirements(page: int = 1, page_size: int = 20, db=Depends(get_db), access=Depends(require_capability("requirement:view"))):
    user, profile = access
    page, page_size = page_values(page, page_size)
    query = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.status == "open", MarketplaceRequirement.visibility == "public_marketplace", MarketplaceRequirement.deleted_at.is_(None))
    rows = query.order_by(MarketplaceRequirement.created_at.desc()).limit(250).all()
    ranked = []
    for requirement in rows:
        match = match_requirement_to_profile(db, requirement, profile)
        ranked.append({**safe_requirement(db, requirement), "match": match})
    ranked.sort(key=lambda item: (item["match"]["match_percentage"], item["created_at"]), reverse=True)
    start = (page - 1) * page_size
    return {"page": page, "page_size": page_size, "total": len(ranked), "results": ranked[start : start + page_size]}


@router.get("/requirements")
def list_requirements(
    keyword: str = Query(default="", max_length=120),
    country: str | None = None,
    location: str | None = None,
    work_mode: str | None = None,
    employment_type: str | None = None,
    industry: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = "newest",
    page: int = 1,
    page_size: int = 20,
    db=Depends(get_db),
    access=Depends(require_capability("requirement:view")),
):
    user, profile = access
    page, page_size = page_values(page, page_size)
    query = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.deleted_at.is_(None))
    if profile and profile.profile_type in {"vendor", "recruitment_agency"}:
        query = query.filter(
            or_(
                MarketplaceRequirement.owner_profile_id == profile.id,
                (MarketplaceRequirement.status == "open") & (MarketplaceRequirement.visibility == "public_marketplace"),
            )
        )
    else:
        query = query.filter(MarketplaceRequirement.status == "open", MarketplaceRequirement.visibility == "public_marketplace")
    for field, value in [(MarketplaceRequirement.country, country), (MarketplaceRequirement.location, location), (MarketplaceRequirement.work_mode, work_mode), (MarketplaceRequirement.employment_type, employment_type), (MarketplaceRequirement.industry, industry), (MarketplaceRequirement.status, status_filter)]:
        if value:
            query = query.filter(field == value)
    if keyword:
        query = query.filter(or_(MarketplaceRequirement.title.ilike(f"%{keyword}%"), MarketplaceRequirement.description.ilike(f"%{keyword}%")))
    total = query.count()
    if sort == "closing_soon":
        query = query.order_by(MarketplaceRequirement.submission_deadline.asc())
    else:
        query = query.order_by(MarketplaceRequirement.created_at.desc())
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"page": page, "page_size": page_size, "total": total, "results": [safe_requirement(db, row) for row in rows if can_access_requirement(db, row, user, profile)]}


@router.get("/requirements/{requirement_id}")
def get_requirement(requirement_id: str, db=Depends(get_db), access=Depends(require_capability("requirement:view"))):
    user, profile = access
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == requirement_id, MarketplaceRequirement.deleted_at.is_(None)).first()
    if not requirement or not can_access_requirement(db, requirement, user, profile):
        raise HTTPException(status_code=404, detail="Requirement not found")
    return safe_requirement(db, requirement, include_private=requirement.owner_profile_id == (profile.id if profile else None))


@router.patch("/requirements/{requirement_id}")
def update_requirement(requirement_id: str, data: RequirementUpdate, db=Depends(get_db), access=Depends(require_capability("requirement:update"))):
    user, profile = access
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == requirement_id, MarketplaceRequirement.owner_profile_id == profile.id, MarketplaceRequirement.deleted_at.is_(None)).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    values = data.model_dump(exclude_unset=True)
    primary = values.pop("primary_skills", None)
    secondary = values.pop("secondary_skills", None)
    us_details = values.pop("us_details", None)
    _copy_requirement_fields(requirement, values)
    if us_details is not None:
        requirement.us_details_json = json_text(us_details)
    if primary is not None or secondary is not None:
        current = requirement_skills(db, requirement.id)
        sync_requirement_skills(db, requirement, primary if primary is not None else current["primary"], secondary if secondary is not None else current["secondary"])
    if requirement.status in {"closed", "filled", "cancelled"} and not requirement.closed_at:
        requirement.closed_at = utcnow()
    audit(db, user, "rp.requirement_updated", "rp_requirement", requirement.id, requirement.organization_id, {"status": requirement.status})
    db.commit()
    return safe_requirement(db, requirement, include_private=True)


@router.get("/requirements/{requirement_id}/sourcing-partners")
def sourcing_partners(requirement_id: str, page: int = 1, page_size: int = 20, db=Depends(get_db), access=Depends(require_capability("requirement:invite"))):
    user, profile = access
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == requirement_id, MarketplaceRequirement.owner_profile_id == profile.id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    page, page_size = page_values(page, page_size)
    rows = db.query(RequirementPlatformProfile).filter(
        RequirementPlatformProfile.status == "verified",
        RequirementPlatformProfile.deleted_at.is_(None),
        or_(RequirementPlatformProfile.profile_type.in_(["recruiter", "recruitment_agency"]), RequirementPlatformProfile.is_available_for_sourcing.is_(True)),
    ).limit(300).all()
    ranked = [{**safe_profile(db, row), "requirement_match": match_requirement_to_profile(db, requirement, row)} for row in rows if row.id != profile.id]
    ranked.sort(key=lambda item: item["requirement_match"]["match_percentage"], reverse=True)
    start = (page - 1) * page_size
    return {"page": page, "page_size": page_size, "total": len(ranked), "results": ranked[start : start + page_size]}


@router.post("/requirements/{requirement_id}/source-request")
def request_to_source(requirement_id: str, data: SourceRequestCreate, db=Depends(get_db), access=Depends(require_capability("sourcing:request"))):
    user, profile = access
    enforce_daily_limit(db, user, "rp.source_request_sent", get_settings().rp_daily_source_request_limit)
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == requirement_id, MarketplaceRequirement.deleted_at.is_(None)).first()
    if not requirement or not can_access_requirement(db, requirement, user, profile):
        raise HTTPException(status_code=404, detail="Requirement not found")
    if requirement.status != "open" or (requirement.submission_deadline and requirement.submission_deadline < utcnow()):
        raise HTTPException(status_code=409, detail="This requirement is not accepting sourcing requests")
    record = SourcingRequest(
        requirement_id=requirement.id,
        professional_profile_id=profile.id,
        suitability=clean(data.suitability, 4000),
        relevant_experience=clean(data.relevant_experience, 4000),
        estimated_delivery_timeline=clean(data.estimated_delivery_timeline, 120),
        estimated_candidate_profiles=data.estimated_candidate_profiles,
        message=clean(data.message, 2000),
        expires_at=requirement.submission_deadline,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A sourcing request has already been submitted for this requirement")
    audit(db, user, "rp.source_request_sent", "rp_source_request", record.id, requirement.organization_id)
    db.commit()
    return {"id": record.id, "status": record.status, "created_at": record.created_at}


def assignment_from_request(db, requirement, request_record):
    assignment = SourcingAssignment(
        requirement_id=requirement.id,
        vendor_profile_id=requirement.owner_profile_id,
        organization_id=requirement.organization_id,
        professional_profile_id=request_record.professional_profile_id,
        source_request_id=request_record.id,
        candidate_submission_limit=requirement.submission_limit_per_partner,
    )
    db.add(assignment)
    return assignment


@router.patch("/source-requests/{request_id}")
def decide_source_request(request_id: str, data: StatusAction, db=Depends(get_db), access=Depends(require_capability("sourcing:assign"))):
    user, profile = access
    if data.status not in {"accepted", "rejected"}:
        raise HTTPException(status_code=400, detail="Source request may only be accepted or rejected")
    record = db.query(SourcingRequest).filter(SourcingRequest.id == request_id).first()
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == (record.requirement_id if record else ""), MarketplaceRequirement.owner_profile_id == profile.id).first()
    if not record or not requirement:
        raise HTTPException(status_code=404, detail="Source request not found")
    if record.status != "pending":
        raise HTTPException(status_code=409, detail="Source request has already been decided")
    if record.expires_at and record.expires_at < utcnow():
        record.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="Source request has expired")
    record.status = data.status
    record.decided_by_user_id = user.id
    record.decided_at = utcnow()
    assignment = assignment_from_request(db, requirement, record) if data.status == "accepted" else None
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This sourcing partner is already assigned")
    audit(db, user, f"rp.source_request_{data.status}", "rp_source_request", record.id, requirement.organization_id)
    if assignment:
        audit(db, user, "rp.assignment_created", "rp_assignment", assignment.id, requirement.organization_id)
    db.commit()
    return {"id": record.id, "status": record.status, "assignment_id": assignment.id if assignment else None}


@router.post("/requirements/{requirement_id}/invitations")
def invite_professional(requirement_id: str, data: InvitationCreate, db=Depends(get_db), access=Depends(require_capability("requirement:invite"))):
    user, profile = access
    enforce_daily_limit(db, user, "rp.invitation_sent", get_settings().rp_daily_invite_limit)
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == requirement_id, MarketplaceRequirement.owner_profile_id == profile.id, MarketplaceRequirement.status == "open").first()
    professional = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.id == data.professional_profile_id, RequirementPlatformProfile.status == "verified").first()
    if not requirement or not professional:
        raise HTTPException(status_code=404, detail="Requirement or sourcing professional not found")
    if requirement.submission_deadline and requirement.submission_deadline < utcnow():
        raise HTTPException(status_code=409, detail="Requirement submission deadline has passed")
    invitation = RequirementInvitation(
        requirement_id=requirement.id,
        professional_profile_id=professional.id,
        invited_by_user_id=user.id,
        message=clean(data.message, 2000),
        expires_at=data.expires_at or min(filter(None, [requirement.submission_deadline, utcnow() + timedelta(days=14)])),
    )
    db.add(invitation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This professional has already been invited")
    audit(db, user, "rp.invitation_sent", "rp_invitation", invitation.id, requirement.organization_id)
    db.commit()
    return {"id": invitation.id, "status": invitation.status, "expires_at": invitation.expires_at}


@router.patch("/invitations/{invitation_id}")
def respond_to_invitation(invitation_id: str, data: StatusAction, db=Depends(get_db), access=Depends(require_capability("sourcing:respond"))):
    user, profile = access
    if data.status not in {"accepted", "declined"}:
        raise HTTPException(status_code=400, detail="Invitation may only be accepted or declined")
    invitation = db.query(RequirementInvitation).filter(RequirementInvitation.id == invitation_id, RequirementInvitation.professional_profile_id == profile.id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation has already been answered")
    if invitation.expires_at and invitation.expires_at < utcnow():
        invitation.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="Invitation has expired")
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == invitation.requirement_id, MarketplaceRequirement.status == "open").first()
    if not requirement:
        raise HTTPException(status_code=409, detail="Requirement is no longer open")
    invitation.status = data.status
    invitation.responded_at = utcnow()
    assignment = None
    if data.status == "accepted":
        assignment = SourcingAssignment(
            requirement_id=requirement.id,
            vendor_profile_id=requirement.owner_profile_id,
            organization_id=requirement.organization_id,
            professional_profile_id=profile.id,
            invitation_id=invitation.id,
            candidate_submission_limit=requirement.submission_limit_per_partner,
        )
        db.add(assignment)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This sourcing partner is already assigned")
    audit(db, user, f"rp.invitation_{data.status}", "rp_invitation", invitation.id, requirement.organization_id)
    if assignment:
        audit(db, user, "rp.assignment_created", "rp_assignment", assignment.id, requirement.organization_id)
    db.commit()
    return {"id": invitation.id, "status": invitation.status, "assignment_id": assignment.id if assignment else None}


@router.get("/assignments")
def list_assignments(status_filter: str | None = Query(default=None, alias="status"), page: int = 1, page_size: int = 20, db=Depends(get_db), user: User = Depends(active_user)):
    profile = profile_for_user(db, user)
    if not profile or profile.status != "verified":
        raise HTTPException(status_code=403, detail="HireScore verification is required for this action")
    page, page_size = page_values(page, page_size)
    query = db.query(SourcingAssignment)
    if profile.profile_type in {"vendor", "recruitment_agency"}:
        query = query.filter(SourcingAssignment.vendor_profile_id == profile.id)
    else:
        query = query.filter(SourcingAssignment.professional_profile_id == profile.id)
    if status_filter:
        query = query.filter(SourcingAssignment.status == status_filter)
    total = query.count()
    rows = query.order_by(SourcingAssignment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"page": page, "page_size": page_size, "total": total, "results": [{"id": row.id, "requirement_id": row.requirement_id, "professional_profile_id": row.professional_profile_id, "status": row.status, "started_at": row.started_at, "candidate_submission_limit": row.candidate_submission_limit} for row in rows]}


@router.post("/assignments/{assignment_id}/candidates")
async def submit_candidate(
    assignment_id: str,
    full_name: str = Form(..., max_length=180),
    email: str | None = Form(default=None, max_length=320),
    phone: str | None = Form(default=None, max_length=64),
    current_location: str | None = Form(default=None, max_length=180),
    total_experience: float | None = Form(default=None),
    current_employer: str | None = Form(default=None, max_length=180),
    current_job_title: str | None = Form(default=None, max_length=180),
    relevant_skills: str | None = Form(default=None, max_length=4000),
    work_authorization: str | None = Form(default=None, max_length=120),
    expected_salary_rate: str | None = Form(default=None, max_length=180),
    notice_period_availability: str | None = Form(default=None, max_length=180),
    recruiter_notes: str | None = Form(default=None, max_length=5000),
    resume: UploadFile = File(...),
    db=Depends(get_db),
    access=Depends(require_capability("candidate:submit")),
):
    user, profile = access
    enforce_daily_limit(db, user, "rp.candidate_submitted", get_settings().rp_daily_candidate_limit)
    assignment = db.query(SourcingAssignment).filter(SourcingAssignment.id == assignment_id, SourcingAssignment.professional_profile_id == profile.id, SourcingAssignment.status == "active").first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Active sourcing assignment not found")
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == assignment.requirement_id, MarketplaceRequirement.status == "open").first()
    if not requirement:
        raise HTTPException(status_code=409, detail="Requirement is not accepting candidate submissions")
    if not normalize_email(email) and not normalize_phone(phone):
        raise HTTPException(status_code=422, detail="Candidate email or phone is required")
    if assignment.candidate_submission_limit:
        submitted_count = db.query(CandidateSubmission).filter(CandidateSubmission.assignment_id == assignment.id, CandidateSubmission.status != "withdrawn").count()
        if submitted_count >= assignment.candidate_submission_limit:
            raise HTTPException(status_code=409, detail="Candidate submission limit has been reached")
    stored = await store_candidate_resume(resume, requirement.id)
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)
    submission = CandidateSubmission(
        requirement_id=requirement.id,
        assignment_id=assignment.id,
        professional_profile_id=profile.id,
        vendor_profile_id=requirement.owner_profile_id,
        organization_id=requirement.organization_id,
        full_name=clean(full_name, 180),
        email=normalized_email or None,
        phone=normalized_phone or None,
        current_location=clean(current_location, 180),
        total_experience=total_experience,
        current_employer=clean(current_employer, 180),
        current_job_title=clean(current_job_title, 180),
        relevant_skills_json=json_text([item.strip() for item in (relevant_skills or "").split(",") if item.strip()][:100]),
        work_authorization=clean(work_authorization, 120),
        expected_salary_rate=clean(expected_salary_rate, 180),
        notice_period_availability=clean(notice_period_availability, 180),
        recruiter_notes=clean(recruiter_notes, 5000),
        resume_storage_key=stored["storage_key"],
        resume_original_filename=stored["original_filename"],
        resume_mime_type=stored["mime_type"],
        resume_size=stored["size"],
        resume_hash=stored["sha256"],
        email_fingerprint=fingerprint(normalized_email),
        phone_fingerprint=fingerprint(normalized_phone),
        candidate_fingerprint=candidate_fingerprint(full_name, normalized_email, normalized_phone),
    )
    db.add(submission)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This candidate has already been submitted for this requirement")
    audit(db, user, "rp.candidate_submitted", "rp_candidate_submission", submission.id, requirement.organization_id)
    db.commit()
    return {"id": submission.id, "status": submission.status, "created_at": submission.created_at}


def can_view_candidate(profile, submission) -> bool:
    return bool(profile and (profile.id == submission.vendor_profile_id or profile.id == submission.professional_profile_id))


@router.get("/requirements/{requirement_id}/candidates")
def list_candidates(requirement_id: str, page: int = 1, page_size: int = 20, db=Depends(get_db), access=Depends(require_capability("candidate:view"))):
    user, profile = access
    requirement = db.query(MarketplaceRequirement).filter(MarketplaceRequirement.id == requirement_id, MarketplaceRequirement.owner_profile_id == profile.id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    page, page_size = page_values(page, page_size)
    query = db.query(CandidateSubmission).filter(CandidateSubmission.requirement_id == requirement.id, CandidateSubmission.organization_id == requirement.organization_id)
    total = query.count()
    rows = query.order_by(CandidateSubmission.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"page": page, "page_size": page_size, "total": total, "results": [safe_candidate(row) for row in rows]}


def safe_candidate(row: CandidateSubmission) -> dict:
    return {
        "id": row.id,
        "requirement_id": row.requirement_id,
        "assignment_id": row.assignment_id,
        "full_name": row.full_name,
        "email": row.email,
        "phone": row.phone,
        "current_location": row.current_location,
        "total_experience": row.total_experience,
        "current_employer": row.current_employer,
        "current_job_title": row.current_job_title,
        "relevant_skills": safe_json(row.relevant_skills_json, []),
        "work_authorization": row.work_authorization,
        "expected_salary_rate": row.expected_salary_rate,
        "notice_period_availability": row.notice_period_availability,
        "recruiter_notes": row.recruiter_notes,
        "status": row.status,
        "resume_download_url": f"/api/v1/requirement-platform/candidates/{row.id}/resume",
        "created_at": row.created_at,
    }


@router.patch("/candidates/{candidate_id}/status")
def update_candidate_status(candidate_id: str, data: CandidateStatusUpdate, db=Depends(get_db), access=Depends(require_capability("candidate:update_status"))):
    user, profile = access
    submission = db.query(CandidateSubmission).filter(CandidateSubmission.id == candidate_id, CandidateSubmission.vendor_profile_id == profile.id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Candidate submission not found")
    previous = submission.status
    submission.status = data.status
    audit(db, user, "rp.candidate_status_changed", "rp_candidate_submission", submission.id, submission.organization_id, {"from": previous, "to": data.status})
    db.commit()
    return {"id": submission.id, "status": submission.status}


@router.get("/candidates/{candidate_id}/resume")
def download_candidate_resume(candidate_id: str, db=Depends(get_db), user: User = Depends(active_user)):
    profile = profile_for_user(db, user)
    submission = db.query(CandidateSubmission).filter(CandidateSubmission.id == candidate_id).first()
    if not submission or not can_view_candidate(profile, submission):
        raise HTTPException(status_code=404, detail="Candidate submission not found")
    content = download_stored_file(submission.resume_storage_key)
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", submission.resume_original_filename or "resume")
    return Response(content, media_type=submission.resume_mime_type or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"})


@router.get("/workspace")
def workspace(db=Depends(get_db), user: User = Depends(active_user)):
    profile = profile_for_user(db, user)
    if not profile:
        raise HTTPException(status_code=403, detail="Complete your Requirement Platform profile")
    if profile.profile_type in {"vendor", "recruitment_agency"}:
        requirement_ids = [row[0] for row in db.query(MarketplaceRequirement.id).filter(MarketplaceRequirement.owner_profile_id == profile.id).all()]
        return {
            "role": "vendor",
            "stats": {
                "active_requirements": db.query(MarketplaceRequirement).filter(MarketplaceRequirement.owner_profile_id == profile.id, MarketplaceRequirement.status == "open").count(),
                "new_source_requests": db.query(SourcingRequest).filter(SourcingRequest.requirement_id.in_(requirement_ids or [""]), SourcingRequest.status == "pending").count(),
                "assigned_sourcing_partners": db.query(SourcingAssignment).filter(SourcingAssignment.vendor_profile_id == profile.id, SourcingAssignment.status == "active").count(),
                "candidate_submissions": db.query(CandidateSubmission).filter(CandidateSubmission.vendor_profile_id == profile.id).count(),
                "shortlisted": db.query(CandidateSubmission).filter(CandidateSubmission.vendor_profile_id == profile.id, CandidateSubmission.status == "shortlisted").count(),
                "selected": db.query(CandidateSubmission).filter(CandidateSubmission.vendor_profile_id == profile.id, CandidateSubmission.status == "selected").count(),
            },
        }
    return {
        "role": "sourcing_professional",
        "stats": {
            "invitations": db.query(RequirementInvitation).filter(RequirementInvitation.professional_profile_id == profile.id, RequirementInvitation.status == "pending").count(),
            "pending_requests": db.query(SourcingRequest).filter(SourcingRequest.professional_profile_id == profile.id, SourcingRequest.status == "pending").count(),
            "active_assignments": db.query(SourcingAssignment).filter(SourcingAssignment.professional_profile_id == profile.id, SourcingAssignment.status == "active").count(),
            "candidate_submissions": db.query(CandidateSubmission).filter(CandidateSubmission.professional_profile_id == profile.id).count(),
        },
    }


@router.post("/reports")
def report_marketplace_record(data: ReportCreate, db=Depends(get_db), user: User = Depends(active_user)):
    if data.target_type == "profile":
        exists = db.query(RequirementPlatformProfile.id).filter(RequirementPlatformProfile.id == data.target_id).first()
    else:
        exists = db.query(MarketplaceRequirement.id).filter(MarketplaceRequirement.id == data.target_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Reported record not found")
    report = MarketplaceReport(reporter_user_id=user.id, target_type=data.target_type, target_id=data.target_id, reason=data.reason, details=clean(data.details, 4000))
    db.add(report)
    db.commit()
    return {"id": report.id, "status": report.status}


@admin_router.get("/verifications")
def admin_verifications(status_filter: str = Query(default="pending", alias="status"), profile_type: str | None = None, page: int = 1, page_size: int = 20, db=Depends(get_db), admin: User = Depends(require_admin)):
    page, page_size = page_values(page, page_size)
    query = db.query(ProfessionalVerification, RequirementPlatformProfile).join(RequirementPlatformProfile, RequirementPlatformProfile.id == ProfessionalVerification.profile_id).filter(ProfessionalVerification.status == status_filter)
    if profile_type:
        query = query.filter(RequirementPlatformProfile.profile_type == profile_type)
    total = query.count()
    rows = query.order_by(ProfessionalVerification.created_at.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "results": [
            {
                "id": verification.id,
                "verification_type": verification.verification_type,
                "status": verification.status,
                "submitted_at": verification.submitted_at,
                "has_evidence": bool(verification.evidence_key),
                "user_message": verification.user_message,
                "profile": own_profile_response(db, profile),
            }
            for verification, profile in rows
        ],
    }


@admin_router.patch("/verifications/{verification_id}")
def decide_verification(verification_id: str, data: VerificationDecision, db=Depends(get_db), admin: User = Depends(require_admin)):
    verification = db.query(ProfessionalVerification).filter(ProfessionalVerification.id == verification_id).first()
    if not verification:
        raise HTTPException(status_code=404, detail="Verification request not found")
    profile = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.id == verification.profile_id).first()
    verification.status = data.status
    verification.admin_notes = clean(data.admin_notes, 4000)
    verification.user_message = clean(data.user_message, 2000)
    verification.reviewer_user_id = admin.id
    verification.reviewed_at = utcnow()
    if data.status == "approved":
        pending = db.query(ProfessionalVerification).filter(ProfessionalVerification.profile_id == profile.id, ProfessionalVerification.id != verification.id, ProfessionalVerification.status.in_(["pending", "under_review"])).count()
        if pending == 0:
            profile.status = "verified"
            profile.verified_at = utcnow()
    elif data.status == "more_information_required":
        profile.status = "more_information_required"
    else:
        profile.status = "rejected"
    calculate_trust_score(db, profile)
    audit(db, admin, f"rp.verification_{data.status}", "rp_verification", verification.id, profile.organization_id)
    db.commit()
    return {"id": verification.id, "status": verification.status, "profile_status": profile.status}


@admin_router.get("/verifications/{verification_id}/evidence")
def download_verification_evidence(verification_id: str, db=Depends(get_db), admin: User = Depends(require_admin)):
    verification = db.query(ProfessionalVerification).filter(ProfessionalVerification.id == verification_id).first()
    if not verification or not verification.evidence_key:
        raise HTTPException(status_code=404, detail="Verification evidence not found")
    metadata = safe_json(verification.evidence_metadata_json, {})
    content = download_stored_file(verification.evidence_key)
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", metadata.get("original_filename") or "verification-document")
    return Response(content, media_type=metadata.get("mime_type") or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"})


@admin_router.patch("/profiles/{profile_id}/suspension")
def set_profile_suspension(profile_id: str, data: StatusAction, db=Depends(get_db), admin: User = Depends(require_admin)):
    profile = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if data.status == "suspended":
        profile.status = "suspended"
        profile.suspended_at = utcnow()
        profile.suspension_reason = clean(data.notes, 3000)
        action = "rp.account_suspended"
    elif data.status == "verified":
        profile.status = "verified"
        profile.suspended_at = None
        profile.suspension_reason = None
        action = "rp.account_unsuspended"
    else:
        raise HTTPException(status_code=400, detail="Use suspended or verified status")
    audit(db, admin, action, "rp_profile", profile.id, profile.organization_id)
    db.commit()
    return {"id": profile.id, "status": profile.status}


@admin_router.get("/reports")
def admin_reports(status_filter: str = Query(default="open", alias="status"), page: int = 1, page_size: int = 20, db=Depends(get_db), admin: User = Depends(require_admin)):
    page, page_size = page_values(page, page_size)
    query = db.query(MarketplaceReport).filter(MarketplaceReport.status == status_filter)
    total = query.count()
    rows = query.order_by(MarketplaceReport.created_at.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"page": page, "page_size": page_size, "total": total, "results": [{"id": row.id, "target_type": row.target_type, "target_id": row.target_id, "reason": row.reason, "details": row.details, "status": row.status, "created_at": row.created_at} for row in rows]}


@admin_router.patch("/reports/{report_id}")
def moderate_report(report_id: str, data: StatusAction, db=Depends(get_db), admin: User = Depends(require_admin)):
    if data.status not in {"under_review", "resolved", "dismissed"}:
        raise HTTPException(status_code=400, detail="Unsupported report status")
    report = db.query(MarketplaceReport).filter(MarketplaceReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = data.status
    report.reviewer_user_id = admin.id
    report.admin_notes = clean(data.notes, 3000)
    report.resolved_at = utcnow() if data.status in {"resolved", "dismissed"} else None
    audit(db, admin, f"rp.report_{data.status}", "rp_report", report.id)
    db.commit()
    return {"id": report.id, "status": report.status}


@admin_router.get("/profiles")
def admin_profiles(status_filter: str | None = Query(default=None, alias="status"), profile_type: str | None = None, page: int = 1, page_size: int = 20, db=Depends(get_db), admin: User = Depends(require_admin)):
    page, page_size = page_values(page, page_size)
    query = db.query(RequirementPlatformProfile).filter(RequirementPlatformProfile.deleted_at.is_(None))
    if status_filter:
        query = query.filter(RequirementPlatformProfile.status == status_filter)
    if profile_type:
        query = query.filter(RequirementPlatformProfile.profile_type == profile_type)
    total = query.count()
    rows = query.order_by(RequirementPlatformProfile.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"page": page, "page_size": page_size, "total": total, "results": [own_profile_response(db, row) for row in rows]}
