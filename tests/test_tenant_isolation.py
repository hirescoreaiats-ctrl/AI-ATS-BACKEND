from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.models import Base, Job, Resume
from backend.routers import job as job_router


@pytest.fixture()
def tenant_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(job_router, "SessionLocal", TestingSession)
    monkeypatch.setattr(job_router, "ensure_apply_slug", lambda job, db: job.apply_slug or job.id)
    monkeypatch.setattr(
        job_router,
        "ensure_generated_sourcing_content",
        lambda job, db: {"main": f"/apply/{job.id}"},
    )

    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def recruiter(org_id="org-a"):
    return SimpleNamespace(id=f"user-{org_id}", role="recruiter", organization_id=org_id)


def admin():
    return SimpleNamespace(id="admin-1", role="admin", organization_id=None)


def add_job(session, job_id, org_id, title):
    job = Job(
        id=job_id,
        organization_id=org_id,
        owner_user_id=f"owner-{org_id}" if org_id else None,
        job_title=title,
        company_name=f"{org_id or 'legacy'} company",
        location="Remote",
        salary_range="10-20 LPA",
        job_type="Full time",
        jd_text="Python developer",
        required_skills="Python",
        shortlist_score=70,
    )
    session.add(job)
    return job


def add_resume(session, resume_id, job_id, org_id, score):
    resume = Resume(
        id=resume_id,
        job_id=job_id,
        organization_id=org_id,
        full_name=f"Candidate {resume_id}",
        email=f"{resume_id}@example.com",
        final_score=score,
        application_source="linkedin",
        is_active=True,
    )
    session.add(resume)
    return resume


def test_recruiter_sees_only_own_org_jobs_and_applicants(tenant_db):
    add_job(tenant_db, "job-a", "org-a", "Org A Job")
    add_job(tenant_db, "job-b", "org-b", "Org B Job")
    add_job(tenant_db, "legacy-job", None, "Legacy Global Job")
    add_resume(tenant_db, "resume-a", "job-a", "org-a", 88)
    add_resume(tenant_db, "resume-b", "job-b", "org-b", 99)
    tenant_db.commit()

    jobs = job_router.get_jobs(user=recruiter("org-a"))

    assert [job["id"] for job in jobs] == ["job-a"]
    assert jobs[0]["total_applicants"] == 1
    assert jobs[0]["top_score"] == 88


def test_new_recruiter_org_sees_empty_dashboard_data(tenant_db):
    add_job(tenant_db, "job-a", "org-a", "Org A Job")
    add_resume(tenant_db, "resume-a", "job-a", "org-a", 88)
    tenant_db.commit()

    assert job_router.get_jobs(user=recruiter("org-new")) == []
    assert job_router.get_top_candidate(user=recruiter("org-new")) == {"name": "None"}


def test_source_analytics_are_scoped_to_current_org(tenant_db):
    add_job(tenant_db, "job-a", "org-a", "Org A Job")
    add_job(tenant_db, "job-b", "org-b", "Org B Job")
    add_resume(tenant_db, "resume-a", "job-a", "org-a", 88)
    add_resume(tenant_db, "resume-b", "job-b", "org-b", 99)
    tenant_db.commit()

    counts = job_router.applications_by_source(job_id=None, user=recruiter("org-a"))

    assert counts["linkedin"] == 1


def test_create_job_stamps_current_user_org(monkeypatch, tenant_db):
    monkeypatch.setattr(
        job_router,
        "enrich_jd_for_scoring",
        lambda *args, **kwargs: {
            "role": "Python Developer",
            "required_skills": ["Python"],
            "preferred_skills": [],
            "min_experience_years": 2,
            "education": [],
            "jd_profile": {},
        },
    )
    job_input = job_router.JobCreate(
        job_title="Python Developer",
        company_name="Org A Company",
        location="Remote",
        job_type="Full time",
        salary_range="10-20 LPA",
        jd_text="Python developer",
    )

    response = job_router.create_job(job_input, user=recruiter("org-a"))
    created_job = tenant_db.query(Job).filter(Job.id == response["job_id"]).first()

    assert created_job.organization_id == "org-a"
    assert created_job.owner_user_id == "user-org-a"


def test_recruiter_cannot_read_other_org_job_detail(tenant_db):
    add_job(tenant_db, "job-b", "org-b", "Org B Job")
    tenant_db.commit()

    with pytest.raises(job_router.HTTPException) as exc:
        job_router.get_job_detail("job-b", user=recruiter("org-a"))

    assert exc.value.status_code == 404


def test_admin_can_still_see_all_jobs(tenant_db):
    add_job(tenant_db, "job-a", "org-a", "Org A Job")
    add_job(tenant_db, "job-b", "org-b", "Org B Job")
    tenant_db.commit()

    jobs = job_router.get_jobs(user=admin())

    assert {job["id"] for job in jobs} == {"job-a", "job-b"}
