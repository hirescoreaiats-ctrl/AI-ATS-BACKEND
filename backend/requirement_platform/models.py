from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from backend.database import Base


def uuid4_string() -> str:
    return str(uuid.uuid4())


class RequirementPlatformProfile(Base):
    __tablename__ = "rp_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_rp_profile_user"),
        CheckConstraint(
            "profile_type IN ('vendor','recruiter','hr_professional','recruitment_agency')",
            name="ck_rp_profile_type",
        ),
        CheckConstraint(
            "status IN ('draft','profile_incomplete','verification_pending','under_review','more_information_required','verified','rejected','suspended')",
            name="ck_rp_profile_status",
        ),
        Index("ix_rp_profiles_marketplace", "profile_type", "status", "country", "availability"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    profile_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    display_name = Column(String(180), nullable=True, index=True)
    professional_headline = Column(String(240), nullable=True)
    profile_photo_key = Column(Text, nullable=True)
    city = Column(String(120), nullable=True, index=True)
    state_region = Column(String(120), nullable=True, index=True)
    country = Column(String(120), nullable=True, index=True)
    linkedin_url = Column(Text, nullable=True)
    website_url = Column(Text, nullable=True)
    professional_email = Column(String(320), nullable=True, index=True)
    phone = Column(String(64), nullable=True)
    availability = Column(String(40), nullable=True, index=True)
    preferred_engagements_json = Column(Text, nullable=True)
    profile_completeness = Column(Integer, nullable=False, default=0)
    is_available_for_sourcing = Column(Boolean, nullable=False, default=False, index=True)
    verified_at = Column(DateTime, nullable=True)
    suspended_at = Column(DateTime, nullable=True)
    suspension_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True, index=True)


class RecruiterProfileDetail(Base):
    __tablename__ = "rp_recruiter_details"

    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), primary_key=True)
    current_job_title = Column(String(180), nullable=True)
    current_organization = Column(String(180), nullable=True)
    total_experience_years = Column(Float, nullable=True)
    current_role_years = Column(Float, nullable=True)
    employment_type = Column(String(80), nullable=True, index=True)
    us_staffing_experience = Column(Boolean, nullable=True)
    us_staffing_years = Column(Float, nullable=True)
    us_employment_types_json = Column(Text, nullable=True)
    visa_familiarity_json = Column(Text, nullable=True)
    states_worked_json = Column(Text, nullable=True)
    us_time_zones_json = Column(Text, nullable=True)
    direct_client_experience = Column(Boolean, nullable=True)
    prime_vendor_experience = Column(Boolean, nullable=True)
    implementation_partner_experience = Column(Boolean, nullable=True)
    msp_vms_experience = Column(Boolean, nullable=True)
    candidates_sourced_per_week = Column(Integer, nullable=True)
    requirements_handled_per_month = Column(Integer, nullable=True)
    candidate_delivery_time = Column(String(120), nullable=True)
    role_seniority_json = Column(Text, nullable=True)
    preferred_requirement_types_json = Column(Text, nullable=True)


class HRProfileDetail(Base):
    __tablename__ = "rp_hr_details"

    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), primary_key=True)
    current_job_title = Column(String(180), nullable=True)
    current_organization = Column(String(180), nullable=True)
    total_hr_experience_years = Column(Float, nullable=True)
    hr_specializations_json = Column(Text, nullable=True)
    recruitment_experience_years = Column(Float, nullable=True)
    industries_hired_json = Column(Text, nullable=True)
    roles_hired_json = Column(Text, nullable=True)
    technical_hiring_experience = Column(Boolean, nullable=True)
    nontechnical_hiring_experience = Column(Boolean, nullable=True)
    average_monthly_hiring = Column(Integer, nullable=True)
    sourcing_methods_json = Column(Text, nullable=True)


class VendorProfileDetail(Base):
    __tablename__ = "rp_vendor_details"

    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), primary_key=True)
    company_name = Column(String(200), nullable=True, index=True)
    company_logo_key = Column(Text, nullable=True)
    business_email = Column(String(320), nullable=True, index=True)
    linkedin_company_url = Column(Text, nullable=True)
    company_size = Column(String(80), nullable=True)
    industry = Column(String(120), nullable=True, index=True)
    company_type = Column(String(80), nullable=True, index=True)
    contact_name = Column(String(180), nullable=True)
    contact_designation = Column(String(180), nullable=True)
    contact_email = Column(String(320), nullable=True)
    contact_phone = Column(String(64), nullable=True)
    contact_linkedin_url = Column(Text, nullable=True)
    works_with_external_recruiters = Column(Boolean, nullable=True)
    accepts_third_party_submissions = Column(Boolean, nullable=True)


class AgencyProfileDetail(Base):
    __tablename__ = "rp_agency_details"

    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), primary_key=True)
    agency_name = Column(String(200), nullable=True, index=True)
    logo_key = Column(Text, nullable=True)
    business_email = Column(String(320), nullable=True, index=True)
    address_region = Column(Text, nullable=True)
    year_established = Column(Integer, nullable=True)
    team_size = Column(Integer, nullable=True)
    contact_person_json = Column(Text, nullable=True)
    description = Column(Text, nullable=True)


class ProfileTaxonomyValue(Base):
    __tablename__ = "rp_profile_taxonomy_values"
    __table_args__ = (
        UniqueConstraint("profile_id", "taxonomy", "value", name="uq_rp_profile_taxonomy_value"),
        Index("ix_rp_taxonomy_search", "taxonomy", "value", "profile_id"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    taxonomy = Column(String(60), nullable=False, index=True)
    value = Column(String(160), nullable=False, index=True)
    experience_years = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProfileCapability(Base):
    __tablename__ = "rp_profile_capabilities"
    __table_args__ = (UniqueConstraint("profile_id", "capability", name="uq_rp_profile_capability"),)

    id = Column(String, primary_key=True, default=uuid4_string)
    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    capability = Column(String(80), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    granted_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProfessionalVerification(Base):
    __tablename__ = "rp_verifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','under_review','approved','rejected','more_information_required')",
            name="ck_rp_verification_status",
        ),
        Index("ix_rp_verification_queue", "status", "verification_type", "created_at"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    verification_type = Column(String(60), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="pending", index=True)
    evidence_key = Column(Text, nullable=True)
    evidence_metadata_json = Column(Text, nullable=True)
    reviewer_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    admin_notes = Column(Text, nullable=True)
    user_message = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrustScore(Base):
    __tablename__ = "rp_trust_scores"

    profile_id = Column(String, ForeignKey("rp_profiles.id", ondelete="CASCADE"), primary_key=True)
    score = Column(Integer, nullable=False, default=0)
    factor_breakdown_json = Column(Text, nullable=True)
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class MarketplaceRequirement(Base):
    __tablename__ = "rp_requirements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','pending_review','open','paused','filled','closed','cancelled','expired')",
            name="ck_rp_requirement_status",
        ),
        CheckConstraint(
            "visibility IN ('public_marketplace','invite_only','private_network')",
            name="ck_rp_requirement_visibility",
        ),
        CheckConstraint("experience_max IS NULL OR experience_min IS NULL OR experience_max >= experience_min", name="ck_rp_requirement_experience"),
        CheckConstraint("openings > 0", name="ck_rp_requirement_openings"),
        Index("ix_rp_requirement_feed", "status", "visibility", "country", "created_at"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    owner_profile_id = Column(String, ForeignKey("rp_profiles.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    title = Column(String(220), nullable=False, index=True)
    description = Column(Text, nullable=False)
    industry = Column(String(120), nullable=True, index=True)
    experience_min = Column(Float, nullable=True)
    experience_max = Column(Float, nullable=True)
    location = Column(String(180), nullable=True, index=True)
    country = Column(String(120), nullable=True, index=True)
    work_mode = Column(String(40), nullable=True, index=True)
    employment_type = Column(String(60), nullable=True, index=True)
    openings = Column(Integer, nullable=False, default=1)
    salary_rate = Column(String(180), nullable=True)
    currency = Column(String(12), nullable=True)
    contract_duration = Column(String(120), nullable=True)
    submission_deadline = Column(DateTime, nullable=True, index=True)
    expected_joining_date = Column(DateTime, nullable=True)
    sourcing_partners_needed = Column(Integer, nullable=True)
    submission_limit_per_partner = Column(Integer, nullable=True)
    additional_notes = Column(Text, nullable=True)
    visibility = Column(String(40), nullable=False, default="public_marketplace", index=True)
    status = Column(String(40), nullable=False, default="draft", index=True)
    us_details_json = Column(Text, nullable=True)
    ats_job_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)


class RequirementSkill(Base):
    __tablename__ = "rp_requirement_skills"
    __table_args__ = (UniqueConstraint("requirement_id", "skill_normalized", "skill_type", name="uq_rp_requirement_skill"),)

    id = Column(String, primary_key=True, default=uuid4_string)
    requirement_id = Column(String, ForeignKey("rp_requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    skill = Column(String(160), nullable=False)
    skill_normalized = Column(String(160), nullable=False, index=True)
    skill_type = Column(String(20), nullable=False, default="primary")


class SourcingRequest(Base):
    __tablename__ = "rp_source_requests"
    __table_args__ = (
        UniqueConstraint("requirement_id", "professional_profile_id", name="uq_rp_source_request_professional"),
        CheckConstraint("status IN ('pending','accepted','rejected','withdrawn','expired')", name="ck_rp_source_request_status"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    requirement_id = Column(String, ForeignKey("rp_requirements.id"), nullable=False, index=True)
    professional_profile_id = Column(String, ForeignKey("rp_profiles.id"), nullable=False, index=True)
    suitability = Column(Text, nullable=False)
    relevant_experience = Column(Text, nullable=True)
    estimated_delivery_timeline = Column(String(120), nullable=True)
    estimated_candidate_profiles = Column(Integer, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    decided_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class RequirementInvitation(Base):
    __tablename__ = "rp_invitations"
    __table_args__ = (
        UniqueConstraint("requirement_id", "professional_profile_id", name="uq_rp_invitation_professional"),
        CheckConstraint("status IN ('pending','accepted','declined','expired')", name="ck_rp_invitation_status"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    requirement_id = Column(String, ForeignKey("rp_requirements.id"), nullable=False, index=True)
    professional_profile_id = Column(String, ForeignKey("rp_profiles.id"), nullable=False, index=True)
    invited_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class SourcingAssignment(Base):
    __tablename__ = "rp_assignments"
    __table_args__ = (
        UniqueConstraint("requirement_id", "professional_profile_id", name="uq_rp_assignment_professional"),
        CheckConstraint("status IN ('active','paused','completed','terminated')", name="ck_rp_assignment_status"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    requirement_id = Column(String, ForeignKey("rp_requirements.id"), nullable=False, index=True)
    vendor_profile_id = Column(String, ForeignKey("rp_profiles.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    professional_profile_id = Column(String, ForeignKey("rp_profiles.id"), nullable=False, index=True)
    source_request_id = Column(String, ForeignKey("rp_source_requests.id"), nullable=True, unique=True)
    invitation_id = Column(String, ForeignKey("rp_invitations.id"), nullable=True, unique=True)
    status = Column(String(30), nullable=False, default="active", index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    candidate_submission_limit = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)


class CandidateSubmission(Base):
    __tablename__ = "rp_candidate_submissions"
    __table_args__ = (
        UniqueConstraint("requirement_id", "email_fingerprint", name="uq_rp_candidate_requirement_email"),
        UniqueConstraint("requirement_id", "phone_fingerprint", name="uq_rp_candidate_requirement_phone"),
        UniqueConstraint("requirement_id", "candidate_fingerprint", name="uq_rp_candidate_requirement_fingerprint"),
        UniqueConstraint("requirement_id", "resume_hash", name="uq_rp_candidate_requirement_resume"),
        CheckConstraint(
            "status IN ('submitted','under_review','shortlisted','interview','selected','rejected','withdrawn')",
            name="ck_rp_candidate_status",
        ),
        Index("ix_rp_candidate_vendor_queue", "organization_id", "requirement_id", "status", "created_at"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    requirement_id = Column(String, ForeignKey("rp_requirements.id"), nullable=False, index=True)
    assignment_id = Column(String, ForeignKey("rp_assignments.id"), nullable=False, index=True)
    professional_profile_id = Column(String, ForeignKey("rp_profiles.id"), nullable=False, index=True)
    vendor_profile_id = Column(String, ForeignKey("rp_profiles.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    full_name = Column(String(180), nullable=False)
    email = Column(String(320), nullable=True)
    phone = Column(String(64), nullable=True)
    current_location = Column(String(180), nullable=True)
    total_experience = Column(Float, nullable=True)
    current_employer = Column(String(180), nullable=True)
    current_job_title = Column(String(180), nullable=True)
    relevant_skills_json = Column(Text, nullable=True)
    work_authorization = Column(String(120), nullable=True)
    expected_salary_rate = Column(String(180), nullable=True)
    notice_period_availability = Column(String(180), nullable=True)
    recruiter_notes = Column(Text, nullable=True)
    resume_storage_key = Column(Text, nullable=False)
    resume_original_filename = Column(String(255), nullable=True)
    resume_mime_type = Column(String(120), nullable=True)
    resume_size = Column(Integer, nullable=True)
    resume_hash = Column(String(128), nullable=True, index=True)
    email_fingerprint = Column(String(128), nullable=True)
    phone_fingerprint = Column(String(128), nullable=True)
    candidate_fingerprint = Column(String(128), nullable=False)
    status = Column(String(30), nullable=False, default="submitted", index=True)
    ats_job_id = Column(String, nullable=True, index=True)
    ats_candidate_id = Column(String, nullable=True, index=True)
    ats_application_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    withdrawn_at = Column(DateTime, nullable=True)


class MarketplaceReport(Base):
    __tablename__ = "rp_reports"
    __table_args__ = (
        CheckConstraint("status IN ('open','under_review','resolved','dismissed')", name="ck_rp_report_status"),
        Index("ix_rp_report_queue", "status", "target_type", "created_at"),
    )

    id = Column(String, primary_key=True, default=uuid4_string)
    reporter_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    target_type = Column(String(30), nullable=False, index=True)
    target_id = Column(String, nullable=False, index=True)
    reason = Column(String(60), nullable=False, index=True)
    details = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="open", index=True)
    reviewer_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
