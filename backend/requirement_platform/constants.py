from __future__ import annotations


PROFILE_TYPES = {"vendor", "recruiter", "hr_professional", "recruitment_agency"}
PROFILE_STATUSES = {
    "draft",
    "profile_incomplete",
    "verification_pending",
    "under_review",
    "more_information_required",
    "verified",
    "rejected",
    "suspended",
}
VERIFICATION_STATUSES = {"pending", "under_review", "approved", "rejected", "more_information_required"}
VERIFICATION_TYPES = {
    "email",
    "phone",
    "linkedin",
    "identity",
    "employment",
    "company_domain",
    "agency",
    "professional",
}
AVAILABILITY_STATUSES = {"available_now", "limited_availability", "not_accepting_projects"}
REQUIREMENT_STATUSES = {"draft", "pending_review", "open", "paused", "filled", "closed", "cancelled", "expired"}
REQUIREMENT_VISIBILITIES = {"public_marketplace", "invite_only", "private_network"}
SOURCE_REQUEST_STATUSES = {"pending", "accepted", "rejected", "withdrawn", "expired"}
INVITATION_STATUSES = {"pending", "accepted", "declined", "expired"}
ASSIGNMENT_STATUSES = {"active", "paused", "completed", "terminated"}
CANDIDATE_STATUSES = {"submitted", "under_review", "shortlisted", "interview", "selected", "rejected", "withdrawn"}
REPORT_STATUSES = {"open", "under_review", "resolved", "dismissed"}
REPORT_REASONS = {"fake_profile", "fake_requirement", "spam", "fraud", "misleading_information", "abuse", "other"}

CAPABILITIES_BY_PROFILE_TYPE = {
    "vendor": {
        "requirement:create",
        "requirement:view",
        "requirement:update",
        "requirement:close",
        "requirement:invite",
        "sourcing:assign",
        "candidate:view",
        "candidate:update_status",
        "professional:view",
        "professional:update",
        "verification:submit",
    },
    "recruitment_agency": {
        "requirement:create",
        "requirement:view",
        "requirement:update",
        "requirement:close",
        "requirement:invite",
        "sourcing:request",
        "sourcing:respond",
        "sourcing:assign",
        "candidate:submit",
        "candidate:view",
        "candidate:update_status",
        "professional:view",
        "professional:update",
        "verification:submit",
    },
    "recruiter": {
        "requirement:view",
        "sourcing:request",
        "sourcing:respond",
        "candidate:submit",
        "professional:view",
        "professional:update",
        "verification:submit",
    },
    "hr_professional": {
        "requirement:view",
        "professional:view",
        "professional:update",
        "verification:submit",
    },
}

ADMIN_CAPABILITIES = {"admin:review_verification", "admin:suspend_user", "admin:moderate_reports"}
