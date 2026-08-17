from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Job, Organization, RecruiterInvitation, Resume, User
from backend.routers import auth as auth_router
from backend.routers.auth import _pilot_config
from backend.services.pilot_access import (
    enforce_job_creation,
    enforce_pilot_access,
    enforce_resume_batch,
    pilot_effective_status,
    release_resume_reservation,
    reserve_resume_batch,
    usage_with_limits,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def pilot(**values):
    defaults = {
        "id": "pilot-1",
        "name": "Pilot User",
        "email": "pilot@example.com",
        "password": "hash",
        "subscription_plan": "pilot",
        "subscription_status": "active",
        "is_active": True,
        "pilot_status": "active",
        "pilot_access_status": "enabled",
        "pilot_started_at": datetime.utcnow() - timedelta(days=1),
        "pilot_expires_at": datetime.utcnow() + timedelta(days=14),
        "max_total_jobs": 2,
        "max_active_jobs": 1,
        "max_resumes_per_job": 2,
        "max_total_resumes": 3,
    }
    defaults.update(values)
    return User(**defaults)


def add_job(db, owner, job_id="job-1", active=True):
    job = Job(id=job_id, owner_user_id=owner.id, organization_id=owner.organization_id, job_title="Data Analyst", is_active=active)
    db.add(job)
    db.flush()
    return job


def add_resume(db, job, resume_id):
    db.add(Resume(id=resume_id, job_id=job.id, organization_id=job.organization_id, is_active=True))
    db.flush()


def test_effective_status_keeps_expiry_suspension_and_deactivation_distinct():
    assert pilot_effective_status(pilot(pilot_expires_at=datetime.utcnow() - timedelta(seconds=1))) == "expired"
    assert pilot_effective_status(pilot(pilot_status="suspended", pilot_suspended_at=datetime.utcnow())) == "suspended"
    assert pilot_effective_status(pilot(pilot_status="deactivated", pilot_deactivated_at=datetime.utcnow())) == "deactivated"


def test_expired_pilot_is_blocked_without_deleting_data(db):
    user = pilot(pilot_expires_at=datetime.utcnow() - timedelta(minutes=1))
    db.add(user)
    job = add_job(db, user)
    add_resume(db, job, "resume-1")
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enforce_pilot_access(user)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "pilot_expired"
    assert db.query(Job).count() == 1
    assert db.query(Resume).count() == 1


def test_job_limit_enforcement_uses_authoritative_jobs(db):
    user = pilot(max_total_jobs=1, max_active_jobs=5)
    db.add(user)
    add_job(db, user)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enforce_job_creation(db, user)

    assert exc.value.detail["code"] == "pilot_total_jobs_limit"
    assert exc.value.detail["used"] == 1


def test_active_job_limit_returns_a_clear_user_message(db):
    user = pilot(max_total_jobs=10, max_active_jobs=1)
    db.add(user)
    add_job(db, user, "active-job", True)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enforce_job_creation(db, user)

    assert exc.value.status_code == 409
    assert exc.value.detail == {
        "code": "pilot_active_jobs_limit",
        "message": "You already have 1 active job, which is your pilot limit. Close one active job or ask your administrator to increase the limit.",
        "used": 1,
        "limit": 1,
        "remaining": 0,
    }


def test_resume_batch_is_checked_before_processing(db):
    user = pilot(max_resumes_per_job=2, max_total_resumes=10)
    db.add(user)
    job = add_job(db, user)
    add_resume(db, job, "resume-1")
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enforce_resume_batch(db, job, 2)

    assert exc.value.detail == {
        "code": "pilot_job_resume_limit",
        "message": "This job has 1 resume slots remaining.",
        "used": 1,
        "limit": 2,
        "remaining": 1,
    }


def test_limit_reduction_reports_over_limit_without_deleting_rows(db):
    user = pilot(max_total_jobs=1, max_active_jobs=1, max_total_resumes=1)
    db.add(user)
    first = add_job(db, user, "job-1", True)
    add_job(db, user, "job-2", True)
    add_resume(db, first, "resume-1")
    add_resume(db, first, "resume-2")
    db.commit()

    usage = usage_with_limits(db, user)

    assert usage["over_limit"] == {"total_jobs": True, "active_jobs": True, "total_resumes": True}
    assert db.query(Job).count() == 2
    assert db.query(Resume).count() == 2


def test_unlimited_legacy_pilot_remains_backward_compatible(db):
    user = pilot(max_total_jobs=None, max_active_jobs=None, max_resumes_per_job=None, max_total_resumes=None, pilot_expires_at=None)
    db.add(user)
    db.commit()

    assert enforce_job_creation(db, user).id == user.id
    enforce_resume_batch(db, add_job(db, user), 5000)


def test_creation_config_rejects_invalid_active_job_limit():
    with pytest.raises(HTTPException) as exc:
        _pilot_config({"max_total_jobs": 2, "max_active_jobs": 3, "duration_days": 14})
    assert exc.value.status_code == 400


def test_concurrent_resume_batches_cannot_claim_the_same_slots(db):
    user = pilot(max_resumes_per_job=2, max_total_resumes=2)
    db.add(user)
    job = add_job(db, user)
    db.commit()

    reservation_id = reserve_resume_batch(db, job, 2)
    with pytest.raises(HTTPException) as exc:
        reserve_resume_batch(db, job, 1)
    assert exc.value.detail["remaining"] == 0

    release_resume_reservation(db, reservation_id)
    assert reserve_resume_batch(db, job, 1)


def test_admin_invite_preserves_limits_for_future_signup(db, monkeypatch):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    admin_org = Organization(id="admin-org", name="Admin Workspace", slug="admin-workspace")
    admin = User(id="admin-1", name="Admin", email="admin@example.com", password="hash", role="admin", organization_id=admin_org.id, is_active=True)
    db.add_all([admin_org, admin])
    add_job(db, admin, "admin-job")
    db.commit()
    monkeypatch.setattr(auth_router, "SessionLocal", Session)
    monkeypatch.setattr(auth_router, "_send_pilot_invitation_email", lambda invitation, invited_by: {"provider": "test"})

    result = auth_router.create_pilot_user_invite(
        {
            "name": "Testing User",
            "email": "testing@example.com",
            "company_name": "ABC Recruitment",
            "max_total_jobs": 10,
            "max_active_jobs": 3,
            "max_resumes_per_job": 500,
            "max_total_resumes": 2000,
            "duration_days": 14,
            "pilot_notes": "Admin only",
        },
        admin=admin,
    )

    assert result["status"] == "pending"
    assert result["email_sent"] is True
    invitation = db.query(RecruiterInvitation).filter(RecruiterInvitation.email == "testing@example.com").one()
    assert invitation.organization_id != admin.organization_id
    assert db.query(Job).filter(Job.organization_id == invitation.organization_id).count() == 0
    future_user = pilot(id="future-1", email="testing@example.com")
    auth_router._apply_invitation_to_user(invitation, future_user)
    assert future_user.company_name == "ABC Recruitment"
    assert future_user.max_total_jobs == 10
    assert future_user.max_active_jobs == 3
    assert future_user.max_resumes_per_job == 500
    assert future_user.max_total_resumes == 2000
    assert invitation.status == "accepted"


def test_admin_can_manage_pilot_from_another_workspace(db):
    admin_org = Organization(id="admin-org", name="Admin Workspace", slug="admin-manage-workspace")
    pilot_org = Organization(id="pilot-org", name="Pilot Workspace", slug="pilot-manage-workspace")
    admin = User(id="admin-manage", name="Admin", email="manage-admin@example.com", password="hash", role="admin", organization_id=admin_org.id)
    managed_pilot = pilot(id="managed-pilot", email="managed-pilot@example.com", organization_id=pilot_org.id)
    db.add_all([admin_org, pilot_org, admin, managed_pilot])
    db.commit()

    assert auth_router._admin_pilot(db, managed_pilot.id, admin).id == managed_pilot.id
