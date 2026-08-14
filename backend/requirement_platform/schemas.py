from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.requirement_platform.constants import (
    AVAILABILITY_STATUSES,
    CANDIDATE_STATUSES,
    PROFILE_TYPES,
    REPORT_REASONS,
    REQUIREMENT_STATUSES,
    REQUIREMENT_VISIBILITIES,
    VERIFICATION_TYPES,
)


class ProfileUpsert(BaseModel):
    profile_type: str
    display_name: str | None = Field(default=None, max_length=180)
    professional_headline: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=120)
    state_region: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    linkedin_url: str | None = Field(default=None, max_length=1000)
    website_url: str | None = Field(default=None, max_length=1000)
    professional_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=64)
    availability: str | None = None
    preferred_engagements: list[str] = Field(default_factory=list, max_length=20)
    is_available_for_sourcing: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    taxonomy: dict[str, list[str] | list[dict[str, Any]]] = Field(default_factory=dict)

    @field_validator("profile_type")
    @classmethod
    def valid_profile_type(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in PROFILE_TYPES:
            raise ValueError("Unsupported professional type")
        return value

    @field_validator("availability")
    @classmethod
    def valid_availability(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().lower()
        if value not in AVAILABILITY_STATUSES:
            raise ValueError("Unsupported availability")
        return value


class VerificationSubmit(BaseModel):
    verification_types: list[str] = Field(min_length=1, max_length=8)
    user_message: str | None = Field(default=None, max_length=2000)

    @field_validator("verification_types")
    @classmethod
    def valid_types(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().lower() for value in values))
        if any(value not in VERIFICATION_TYPES for value in normalized):
            raise ValueError("Unsupported verification type")
        return normalized


class VerificationDecision(BaseModel):
    status: str
    admin_notes: str | None = Field(default=None, max_length=4000)
    user_message: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"approved", "rejected", "more_information_required"}:
            raise ValueError("Unsupported verification decision")
        return value


class RequirementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=220)
    description: str = Field(min_length=20, max_length=30000)
    primary_skills: list[str] = Field(default_factory=list, max_length=50)
    secondary_skills: list[str] = Field(default_factory=list, max_length=50)
    industry: str | None = Field(default=None, max_length=120)
    experience_min: float | None = Field(default=None, ge=0, le=80)
    experience_max: float | None = Field(default=None, ge=0, le=80)
    location: str | None = Field(default=None, max_length=180)
    country: str | None = Field(default=None, max_length=120)
    work_mode: str | None = Field(default=None, max_length=40)
    employment_type: str | None = Field(default=None, max_length=60)
    openings: int = Field(default=1, ge=1, le=10000)
    salary_rate: str | None = Field(default=None, max_length=180)
    currency: str | None = Field(default=None, max_length=12)
    contract_duration: str | None = Field(default=None, max_length=120)
    submission_deadline: datetime | None = None
    expected_joining_date: datetime | None = None
    sourcing_partners_needed: int | None = Field(default=None, ge=1, le=1000)
    submission_limit_per_partner: int | None = Field(default=None, ge=1, le=10000)
    additional_notes: str | None = Field(default=None, max_length=10000)
    visibility: str = "public_marketplace"
    status: str = "draft"
    us_details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("visibility")
    @classmethod
    def valid_visibility(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in REQUIREMENT_VISIBILITIES:
            raise ValueError("Unsupported requirement visibility")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in REQUIREMENT_STATUSES:
            raise ValueError("Unsupported requirement status")
        return value

    @model_validator(mode="after")
    def validate_experience(self):
        if self.experience_min is not None and self.experience_max is not None and self.experience_max < self.experience_min:
            raise ValueError("Maximum experience must be greater than or equal to minimum experience")
        return self


class RequirementUpdate(RequirementCreate):
    title: str | None = Field(default=None, min_length=2, max_length=220)
    description: str | None = Field(default=None, min_length=20, max_length=30000)
    primary_skills: list[str] | None = Field(default=None, max_length=50)
    secondary_skills: list[str] | None = Field(default=None, max_length=50)
    openings: int | None = Field(default=None, ge=1, le=10000)
    visibility: str | None = None
    status: str | None = None
    us_details: dict[str, Any] | None = None


class SourceRequestCreate(BaseModel):
    suitability: str = Field(min_length=20, max_length=4000)
    relevant_experience: str | None = Field(default=None, max_length=4000)
    estimated_delivery_timeline: str | None = Field(default=None, max_length=120)
    estimated_candidate_profiles: int | None = Field(default=None, ge=1, le=10000)
    message: str | None = Field(default=None, max_length=2000)


class InvitationCreate(BaseModel):
    professional_profile_id: str
    message: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None


class StatusAction(BaseModel):
    status: str
    notes: str | None = Field(default=None, max_length=3000)


class CandidateStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in CANDIDATE_STATUSES:
            raise ValueError("Unsupported candidate status")
        return value


class ReportCreate(BaseModel):
    target_type: str
    target_id: str
    reason: str
    details: str | None = Field(default=None, max_length=4000)

    @field_validator("target_type")
    @classmethod
    def valid_target_type(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"profile", "requirement"}:
            raise ValueError("Reports may target a profile or requirement")
        return value

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in REPORT_REASONS:
            raise ValueError("Unsupported report reason")
        return value
