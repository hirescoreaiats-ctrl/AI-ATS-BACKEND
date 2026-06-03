from sqlalchemy import Column, String, Text, Integer, Float, ForeignKey, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime
import uuid


# ---------------- JOB MODEL ----------------

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # JD + AI parsing fields
    jd_text = Column(Text)
    role = Column(String)
    required_skills = Column(Text)
    preferred_skills = Column(Text, nullable=True)
    min_experience_years = Column(Float)
    education = Column(String)

    # Job post info
    job_title = Column(String)
    company_name = Column(String)
    location = Column(String)
    salary_range = Column(String)
    job_type = Column(String)
    shortlist_score = Column(Integer, default=60)  # NEW FIELD
    department = Column(String, nullable=True)
    work_mode = Column(String, nullable=True)
    experience_required = Column(String, nullable=True)
    application_deadline = Column(String, nullable=True)
    hiring_manager = Column(String, nullable=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    pipeline_template = Column(Text, nullable=True)
    status = Column(String, default="open", index=True)
    priority = Column(String, default="normal")
    headcount = Column(Integer, default=1)
    public_apply_enabled = Column(Boolean, default=True)
    source_tracking_enabled = Column(Boolean, default=True)
    apply_slug = Column(String, unique=True, nullable=True, index=True)
    generated_linkedin_post = Column(Text, nullable=True)
    generated_whatsapp_message = Column(Text, nullable=True)
    generated_naukri_text = Column(Text, nullable=True)
    resume_folder_path = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    resumes = relationship("Resume", back_populates="job")


# ---------------- RESUME MODEL ----------------



class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)

    # 🔹 Resume extracted data
    full_name = Column(String)
    email = Column(String)
    phone = Column(String)
    location = Column(String)

    # 🔹 Candidate form data
    form_full_name = Column(String)
    form_email = Column(String)
    form_phone = Column(String)
    form_location = Column(String)

    expected_salary = Column(String)
    preferred_location = Column(String)
    notice_period = Column(String)

    linkedin = Column(String)
    github = Column(String)
    portfolio = Column(String)

    # 🔹 Professional Info
    designation = Column(String)
    key_skills = Column(Text)
    projects = Column(Text, nullable=True)
    total_experience_years = Column(Float)
    relevant_experience_years = Column(Float, nullable=True)
    direct_relevant_experience_years = Column(Float, nullable=True)
    transferable_experience_years = Column(Float, nullable=True)
    senior_role_experience_years = Column(Float, nullable=True)
    last_company_name = Column(String)
    last_working_date = Column(String)

    # 🔹 Education & Domain
    education = Column(Text)
    industry = Column(String)
    domain = Column(String)
    role_family = Column(String, nullable=True)
    role_family_confidence = Column(Float, nullable=True)
    role_relevance_score = Column(Float, nullable=True)
    duplicate_key = Column(String, nullable=True, index=True)
    duplicate_of_id = Column(String, ForeignKey("resumes.id"), nullable=True)

    # 🔹 Scoring
    final_score = Column(Float)
    rank_score = Column(Float, nullable=True)
    fit_band = Column(String, nullable=True)
    skill_score = Column(Float)
    experience_score = Column(Float)
    confidence_score = Column(Float, nullable=True)
    resume_quality_score = Column(Float, nullable=True)
    ai_recommendation = Column(String, nullable=True)
    ranking_reason = Column(Text, nullable=True)
    ai_confidence_reason = Column(Text, nullable=True)
    embedding_provider = Column(String, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_vector_json = Column(Text, nullable=True)

    # 🔹 Skill Matching Insights
    matched_skills = Column(Text, nullable=True)
    missing_skills = Column(Text, nullable=True)
    skill_match_percent = Column(Float, nullable=True)
    mandatory_skill_coverage = Column(Float, nullable=True)
    core_skill_match_percent = Column(Float, nullable=True)
    missing_core_skill_groups = Column(Text, nullable=True)
    parser_quality_score = Column(Float, nullable=True)
    parser_quality_action = Column(String, nullable=True)
    parser_quality_flags = Column(Text, nullable=True)
    experience_relevance_label = Column(String, nullable=True)
    experience_evidence = Column(Text, nullable=True)
    experience_warnings = Column(Text, nullable=True)
    score_caps_applied = Column(Text, nullable=True)
    recruiter_flags = Column(Text, nullable=True)
    risk_flags = Column(Text, nullable=True)
    scoring_breakdown = Column(Text, nullable=True)
    jd_profile_json = Column(Text, nullable=True)

    # 🔹 AI Explanation
    resume_text = Column(Text, nullable=True)
    resume_file_path = Column(Text, nullable=True)
    resume_original_filename = Column(String, nullable=True)
    resume_content_type = Column(String, nullable=True)
    explanation = Column(Text, nullable=True)
    explanation_generated_at = Column(DateTime, nullable=True)

    # 🔹 Meta
    is_active = Column(Boolean, default=True)
    shortlisted = Column(Boolean, default=False)
    shortlisted_auto = Column(Boolean, default=False)
    shortlisted_manual = Column(Boolean, default=False)

    # ⭐ IMPORTANT (TRACKING SYSTEM)
    status = Column(String, default="Review")
    stage = Column(String, default="review")
    assigned_recruiter_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)

    # 🔥 NEW ADD KARNA HAI
    mail_status = Column(String, default=None)
    response_status = Column(String, default=None)
    application_source = Column(String, default="direct")
    apply_tracking_url = Column(Text, nullable=True)


    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="resumes")


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), unique=True, index=True, nullable=False)
    title = Column(String)
    question_count = Column(Integer, default=20)
    duration_minutes = Column(Integer, default=30)
    questions_json = Column(Text)
    google_form_id = Column(String, nullable=True)
    google_form_url = Column(Text, nullable=True)
    google_form_edit_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CandidateAssessment(Base):
    __tablename__ = "candidate_assessments"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), index=True, nullable=False)
    candidate_id = Column(String, ForeignKey("resumes.id"), index=True, nullable=False)
    assessment_id = Column(String, ForeignKey("assessments.id"), index=True, nullable=False)
    sent_to_email = Column(String)
    status = Column(String, default="Test Sent")
    response_id = Column(String, nullable=True)
    score = Column(Float, nullable=True)
    max_score = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)
    result_status = Column(String, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    interview_status = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

# ---------------- USER MODEL ----------------

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    name = Column(String, nullable=False)

    email = Column(String, unique=True, index=True, nullable=False)

    password = Column(String, nullable=False)
    role = Column(String, default="recruiter", index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)

    google_access_token = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_token_expires_at = Column(DateTime, nullable=True)
    outreach_sender_email = Column(String, nullable=True, index=True)
    auth_provider = Column(String, nullable=True)
    subscription_status = Column(String, default="unpaid", index=True)
    subscription_plan = Column(String, nullable=True)
    subscription_started_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    plan = Column(String, default="enterprise")
    settings_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Team(Base):
    __tablename__ = "teams"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    department = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(String, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, default="member", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class RecruiterInvitation(Base):
    __tablename__ = "recruiter_invitations"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    invited_by_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    role = Column(String, default="recruiter", index=True)
    status = Column(String, default="pending", index=True)
    token = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    position = Column(Integer, default=0, index=True)
    rules_json = Column(Text, nullable=True)
    is_terminal = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CandidateStageHistory(Base):
    __tablename__ = "candidate_stage_history"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    from_stage = Column(String, nullable=True)
    to_stage = Column(String, nullable=False, index=True)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PipelineAutomation(Base):
    __tablename__ = "pipeline_automations"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    trigger_stage = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False)
    config_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    filters_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class TalentPool(Base):
    __tablename__ = "talent_pools"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class TalentPoolCandidate(Base):
    __tablename__ = "talent_pool_candidates"
    __table_args__ = (UniqueConstraint("talent_pool_id", "candidate_id", name="uq_talent_pool_candidate"),)

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    talent_pool_id = Column(String, ForeignKey("talent_pools.id"), nullable=False, index=True)
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    added_by_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CandidateNote(Base):
    __tablename__ = "candidate_notes"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    author_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    body = Column(Text, nullable=False)
    visibility = Column(String, default="team")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CandidateTag(Base):
    __tablename__ = "candidate_tags"
    __table_args__ = (UniqueConstraint("candidate_id", "tag", name="uq_candidate_tag"),)

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    tag = Column(String, nullable=False, index=True)
    color = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CandidateActivity(Base):
    __tablename__ = "candidate_activities"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    activity_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Interview(Base):
    __tablename__ = "interviews"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, index=True)
    interviewer_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    interview_type = Column(String, default="technical")
    scheduled_at = Column(DateTime, nullable=True, index=True)
    duration_minutes = Column(Integer, default=45)
    status = Column(String, default="scheduled", index=True)
    meeting_url = Column(Text, nullable=True)
    panel_json = Column(Text, nullable=True)
    candidate_availability_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class InterviewKit(Base):
    __tablename__ = "interview_kits"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    competencies_json = Column(Text, nullable=True)
    questions_json = Column(Text, nullable=True)
    scorecard_template_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class InterviewScorecard(Base):
    __tablename__ = "interview_scorecards"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    interview_id = Column(String, ForeignKey("interviews.id"), nullable=False, index=True)
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    reviewer_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    recommendation = Column(String, nullable=False)
    technical_score = Column(Float, nullable=True)
    communication_score = Column(Float, nullable=True)
    culture_score = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Offer(Base):
    __tablename__ = "offers"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey("resumes.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, index=True)
    status = Column(String, default="draft", index=True)
    compensation = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    approval_status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class OfferApproval(Base):
    __tablename__ = "offer_approvals"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    offer_id = Column(String, ForeignKey("offers.id"), nullable=False, index=True)
    approver_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    step_order = Column(Integer, default=0, index=True)
    status = Column(String, default="pending", index=True)
    notes = Column(Text, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
