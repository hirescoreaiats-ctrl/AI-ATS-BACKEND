from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Organization, User
from backend.requirement_platform.models import (
    CandidateSubmission,
    MarketplaceRequirement,
    RequirementPlatformProfile,
    SourcingAssignment,
)
from backend.requirement_platform.permissions import active_user, effective_capabilities, profile_for_user


@pytest.fixture()
def rp_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()


def add_identity(db, *, user_id="user-1", org_id="org-1", role="recruiter", active=True):
    org = Organization(id=org_id, name="Example", slug=org_id)
    user = User(id=user_id, name="Test User", email=f"{user_id}@example.com", password="hashed", role=role, organization_id=org_id, is_active=active)
    db.add_all([org, user])
    db.commit()
    return user


def test_one_requirement_platform_profile_per_user(rp_db):
    user = add_identity(rp_db)
    rp_db.add(RequirementPlatformProfile(user_id=user.id, organization_id=user.organization_id, profile_type="recruiter"))
    rp_db.commit()
    rp_db.add(RequirementPlatformProfile(user_id=user.id, organization_id=user.organization_id, profile_type="vendor"))
    with pytest.raises(IntegrityError):
        rp_db.commit()


def test_inactive_user_is_rejected():
    with pytest.raises(HTTPException) as exc:
        active_user(SimpleNamespace(method="GET", headers={}, cookies={}), SimpleNamespace(is_active=False))
    assert exc.value.status_code == 403


def test_hr_sourcing_capabilities_require_opt_in(rp_db):
    user = add_identity(rp_db)
    profile = RequirementPlatformProfile(user_id=user.id, organization_id=user.organization_id, profile_type="hr_professional", status="verified", is_available_for_sourcing=False)
    rp_db.add(profile)
    rp_db.commit()
    assert "candidate:submit" not in effective_capabilities(rp_db, user, profile)
    profile.is_available_for_sourcing = True
    rp_db.commit()
    assert "candidate:submit" in effective_capabilities(rp_db, user, profile)


def test_profile_lookup_is_user_scoped(rp_db):
    user = add_identity(rp_db)
    profile = RequirementPlatformProfile(user_id=user.id, organization_id=user.organization_id, profile_type="vendor")
    rp_db.add(profile)
    rp_db.commit()
    assert profile_for_user(rp_db, user).id == profile.id
    assert profile_for_user(rp_db, SimpleNamespace(id="another-user")) is None


def test_candidate_duplicate_fingerprint_is_blocked_per_requirement(rp_db):
    vendor_user = add_identity(rp_db, user_id="vendor-user")
    recruiter_user = User(id="recruiter-user", name="Recruiter", email="recruiter@example.com", password="hashed", role="recruiter", organization_id="org-1", is_active=True)
    rp_db.add(recruiter_user)
    rp_db.flush()
    vendor = RequirementPlatformProfile(user_id=vendor_user.id, organization_id="org-1", profile_type="vendor", status="verified")
    recruiter = RequirementPlatformProfile(user_id=recruiter_user.id, organization_id="org-1", profile_type="recruiter", status="verified")
    rp_db.add_all([vendor, recruiter])
    rp_db.flush()
    requirement = MarketplaceRequirement(owner_profile_id=vendor.id, organization_id="org-1", title="Backend Engineer", description="Build APIs", status="open")
    rp_db.add(requirement)
    rp_db.flush()
    assignment = SourcingAssignment(requirement_id=requirement.id, vendor_profile_id=vendor.id, professional_profile_id=recruiter.id, organization_id="org-1")
    rp_db.add(assignment)
    rp_db.flush()

    common = dict(
        requirement_id=requirement.id,
        assignment_id=assignment.id,
        professional_profile_id=recruiter.id,
        vendor_profile_id=vendor.id,
        organization_id="org-1",
        full_name="Candidate",
        resume_storage_key="private/resume.pdf",
        candidate_fingerprint="same-fingerprint",
    )
    rp_db.add(CandidateSubmission(**common))
    rp_db.commit()
    rp_db.add(CandidateSubmission(**common))
    with pytest.raises(IntegrityError):
        rp_db.commit()
