from datetime import datetime, timedelta
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.security import get_current_user
from backend.database import get_db
from backend.models import Base, Organization, User
from backend.requirement_platform.api import admin_router, router
from backend.requirement_platform.models import MarketplaceRequirement, RequirementInvitation, RequirementPlatformProfile, SourcingAssignment, SourcingRequest


@pytest.fixture()
def api_context(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    org_a = Organization(id="org-a", name="Org A", slug="org-a")
    org_b = Organization(id="org-b", name="Org B", slug="org-b")
    users = {
        "vendor": User(id="vendor-user", name="Vendor", email="vendor@example.com", password="hashed", role="recruiter", organization_id="org-a", is_active=True),
        "other_vendor": User(id="other-vendor-user", name="Other Vendor", email="other-vendor@example.com", password="hashed", role="recruiter", organization_id="org-b", is_active=True),
        "recruiter": User(id="recruiter-user", name="Recruiter", email="recruiter@example.com", password="hashed", role="recruiter", organization_id="org-a", is_active=True),
        "unverified": User(id="unverified-user", name="Unverified", email="unverified@example.com", password="hashed", role="recruiter", organization_id="org-a", is_active=True),
        "suspended": User(id="suspended-user", name="Suspended", email="suspended@example.com", password="hashed", role="recruiter", organization_id="org-a", is_active=False),
        "admin": User(id="admin-user", name="Admin", email="admin@example.com", password="hashed", role="admin", organization_id=None, is_active=True),
    }
    db.add_all([org_a, org_b, *users.values()])
    db.flush()
    profiles = {
        "vendor": RequirementPlatformProfile(id="vendor-profile", user_id=users["vendor"].id, organization_id="org-a", profile_type="vendor", status="verified", display_name="Vendor Company"),
        "other_vendor": RequirementPlatformProfile(id="other-vendor-profile", user_id=users["other_vendor"].id, organization_id="org-b", profile_type="vendor", status="verified", display_name="Other Vendor"),
        "recruiter": RequirementPlatformProfile(id="recruiter-profile", user_id=users["recruiter"].id, organization_id="org-a", profile_type="recruiter", status="verified", display_name="Recruiter", availability="available_now"),
        "unverified": RequirementPlatformProfile(id="unverified-profile", user_id=users["unverified"].id, organization_id="org-a", profile_type="vendor", status="under_review", display_name="Pending Vendor"),
    }
    db.add_all(profiles.values())
    requirement = MarketplaceRequirement(id="requirement-a", owner_profile_id=profiles["vendor"].id, organization_id="org-a", title="Backend Engineer", description="Build secure backend services for customers.", status="open", visibility="public_marketplace")
    closed = MarketplaceRequirement(id="requirement-closed", owner_profile_id=profiles["vendor"].id, organization_id="org-a", title="Closed Role", description="This requirement is already closed now.", status="closed", visibility="public_marketplace")
    db.add_all([requirement, closed])
    db.commit()

    current = {"user": users["vendor"]}
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    def override_db():
        yield db

    def override_user():
        return current["user"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})
    try:
        yield {"client": client, "db": db, "users": users, "profiles": profiles, "current": current, "requirement": requirement}
    finally:
        db.close()


def use(ctx, name):
    ctx["current"]["user"] = ctx["users"][name]
    return ctx["client"]


def requirement_payload(title="New Requirement"):
    return {"title": title, "description": "A sufficiently detailed recruitment requirement description.", "status": "open", "visibility": "public_marketplace"}


def test_unverified_user_cannot_create_requirement(api_context):
    response = use(api_context, "unverified").post("/api/v1/requirement-platform/requirements", json=requirement_payload())
    assert response.status_code == 403


def test_recruiter_cannot_create_vendor_requirement(api_context):
    response = use(api_context, "recruiter").post("/api/v1/requirement-platform/requirements", json=requirement_payload())
    assert response.status_code == 403


def test_vendor_cannot_edit_another_vendor_requirement(api_context):
    response = use(api_context, "other_vendor").patch("/api/v1/requirement-platform/requirements/requirement-a", json={"profile_type": "vendor", "title": "Tampered"})
    assert response.status_code in {404, 422}
    api_context["db"].refresh(api_context["requirement"])
    assert api_context["requirement"].title == "Backend Engineer"


def test_suspended_user_cannot_use_marketplace(api_context):
    response = use(api_context, "suspended").get("/api/v1/requirement-platform/workspace")
    assert response.status_code == 403


def test_non_admin_cannot_access_verification_admin(api_context):
    response = use(api_context, "vendor").get("/api/v1/admin/requirement-platform/verifications")
    assert response.status_code == 403


def test_closed_requirement_rejects_source_request(api_context):
    response = use(api_context, "recruiter").post(
        "/api/v1/requirement-platform/requirements/requirement-closed/source-request",
        json={"suitability": "I have relevant sourcing experience for this requirement."},
    )
    assert response.status_code in {404, 409}


def test_expired_invitation_cannot_be_accepted(api_context):
    db = api_context["db"]
    invitation = RequirementInvitation(
        id="expired-invite",
        requirement_id="requirement-a",
        professional_profile_id="recruiter-profile",
        invited_by_user_id="vendor-user",
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    db.add(invitation)
    db.commit()
    response = use(api_context, "recruiter").patch("/api/v1/requirement-platform/invitations/expired-invite", json={"status": "accepted"})
    assert response.status_code == 409
    db.refresh(invitation)
    assert invitation.status == "expired"


def test_source_request_cannot_be_accepted_twice(api_context):
    db = api_context["db"]
    source_request = SourcingRequest(id="request-1", requirement_id="requirement-a", professional_profile_id="recruiter-profile", suitability="Relevant experience for this role")
    db.add(source_request)
    db.commit()
    client = use(api_context, "vendor")
    first = client.patch("/api/v1/requirement-platform/source-requests/request-1", json={"status": "accepted"})
    second = client.patch("/api/v1/requirement-platform/source-requests/request-1", json={"status": "accepted"})
    assert first.status_code == 200
    assert second.status_code == 409


def test_candidate_submission_requires_active_own_assignment(api_context):
    response = use(api_context, "recruiter").post(
        "/api/v1/requirement-platform/assignments/missing/candidates",
        data={"full_name": "Candidate"},
        files={"resume": ("resume.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 404


def test_malicious_pdf_signature_is_rejected(api_context):
    db = api_context["db"]
    assignment = db.query(SourcingAssignment).filter(SourcingAssignment.professional_profile_id == "recruiter-profile").first()
    if not assignment:
        assignment = SourcingAssignment(id="assignment-for-upload", requirement_id="requirement-a", vendor_profile_id="vendor-profile", professional_profile_id="recruiter-profile", organization_id="org-a")
        db.add(assignment)
        db.commit()
    response = use(api_context, "recruiter").post(
        f"/api/v1/requirement-platform/assignments/{assignment.id}/candidates",
        data={"full_name": "Candidate", "email": "candidate@example.com"},
        files={"resume": ("resume.pdf", b"MZ executable payload", "application/pdf")},
    )
    assert response.status_code == 415


def test_page_size_is_capped(api_context):
    response = use(api_context, "recruiter").get("/api/v1/requirement-platform/requirements?page_size=5000")
    assert response.status_code == 200
    assert response.json()["page_size"] == 50


def test_public_profile_does_not_expose_contact_details(api_context):
    profile = api_context["profiles"]["recruiter"]
    profile.professional_email = "private@example.com"
    profile.phone = "+1 555 0100"
    api_context["db"].commit()
    response = use(api_context, "vendor").get("/api/v1/requirement-platform/professionals/recruiter-profile")
    assert response.status_code == 200
    payload = response.json()
    assert "professional_email" not in payload
    assert "phone" not in payload
