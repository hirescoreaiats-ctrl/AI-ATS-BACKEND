from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.models import Job
from backend.routers import job as job_router
from test_tenant_isolation import recruiter, tenant_db


def job_input(*, sourcing: bool):
    return job_router.JobCreate(
        job_title="Embedded Software Engineer",
        company_name="Example Devices",
        company_website="exampledevices.com",
        department="Engineering",
        location="Bengaluru",
        work_mode="Hybrid",
        job_type="Full time",
        salary_range="12-18 LPA",
        experience_required="3-5 years",
        application_deadline="2026-09-15",
        hiring_manager="Engineering Lead",
        jd_text="Build embedded firmware using C, RTOS, microcontrollers, Git, debugging, and hardware interfaces.",
        request_candidate_sourcing=sourcing,
    )


def scoring_enrichment(*_args, **_kwargs):
    return {
        "role": "Embedded Software Engineer",
        "required_skills": ["C", "RTOS", "Microcontrollers"],
        "preferred_skills": ["Git", "Debugging"],
        "min_experience_years": 3,
        "education": [],
        "jd_profile": {},
    }


def test_sourcing_opt_in_publishes_job_and_sends_complete_email(monkeypatch, tenant_db):
    sent = []
    monkeypatch.setattr(job_router, "enrich_jd_for_scoring", scoring_enrichment)
    monkeypatch.setattr(job_router, "_deliver_sourcing_request_email", lambda job, owner, db: sent.append((job.id, owner.id)) or {"provider": "test"})

    response = job_router.create_job(job_input(sourcing=True), user=recruiter("org-a"))
    stored = tenant_db.query(Job).filter(Job.id == response["job_id"]).one()

    assert stored.sourcing_requested is True
    assert stored.sourcing_requested_at is not None
    assert stored.sourcing_email_status == "sent"
    assert sent == [(stored.id, "user-org-a")]
    assert response["requirement_url"].startswith("https://hirescoreai.com/requirement-platform/?view=requirements&job_id=")

    feed = job_router.public_sourcing_requirements(job_id=stored.id, limit=10)
    assert feed["count"] == 1
    assert feed["results"][0]["title"] == "Embedded Software Engineer"
    assert feed["results"][0]["company_website"] == "https://exampledevices.com"
    assert feed["results"][0]["primary_skills"] == ["C", "RTOS", "Microcontrollers"]
    assert "hiring_manager" not in feed["results"][0]


def test_sourcing_email_failure_does_not_roll_back_job(monkeypatch, tenant_db):
    monkeypatch.setattr(job_router, "enrich_jd_for_scoring", scoring_enrichment)
    monkeypatch.setattr(job_router, "_deliver_sourcing_request_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("mail offline")))

    response = job_router.create_job(job_input(sourcing=True), user=recruiter("org-a"))
    stored = tenant_db.query(Job).filter(Job.id == response["job_id"]).one()

    assert stored.sourcing_requested is True
    assert stored.sourcing_email_status == "failed"
    assert "mail offline" in stored.sourcing_email_error
    assert response["sourcing_email_status"] == "failed"


def test_sourcing_email_contains_owner_and_complete_job_details(monkeypatch, tenant_db):
    captured = {}
    monkeypatch.setattr(job_router, "send_transactional_email", lambda **kwargs: captured.update(kwargs) or {"provider": "test"})
    job = Job(
        id="email-job",
        job_title="Embedded Software Engineer",
        company_name="Example Devices",
        company_website="https://exampledevices.com/careers",
        department="Engineering",
        location="Bengaluru",
        work_mode="Hybrid",
        job_type="Full time",
        salary_range="12-18 LPA",
        experience_required="3-5 years",
        application_deadline="2026-09-15",
        hiring_manager="Engineering Lead",
        required_skills="C,RTOS,Microcontrollers",
        preferred_skills="Git,Debugging",
        jd_text="Complete embedded firmware job description.",
        apply_slug="embedded-software-engineer",
        sourcing_requested=True,
    )
    owner = SimpleNamespace(id="owner-1", name="Recruiter Name", email="recruiter@example.com", company_name="Account Company")

    result = job_router._deliver_sourcing_request_email(job, owner, tenant_db)

    assert result["provider"] == "test"
    assert captured["to_email"].lower() == "info@hirescoreai.com"
    assert "Recruiter email: recruiter@example.com" in captured["text_body"]
    assert "Hiring manager: Engineering Lead" in captured["text_body"]
    assert "Company website: https://exampledevices.com/careers" in captured["text_body"]
    assert "Required skills: C,RTOS,Microcontrollers" in captured["text_body"]
    assert "Full job description: Complete embedded firmware job description." in captured["text_body"]
    assert "requirement-platform/?view=requirements&amp;job_id=email-job" in captured["html_body"]


def test_company_website_is_optional_and_rejects_unsafe_schemes(monkeypatch, tenant_db):
    monkeypatch.setattr(job_router, "enrich_jd_for_scoring", scoring_enrichment)
    no_website = job_input(sourcing=False)
    no_website.company_website = None
    response = job_router.create_job(no_website, user=recruiter("org-a"))
    assert tenant_db.query(Job).filter(Job.id == response["job_id"]).one().company_website is None

    unsafe = job_input(sourcing=False)
    unsafe.company_website = "javascript:alert(1)"
    try:
        job_router.create_job(unsafe, user=recruiter("org-a"))
    except job_router.HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("Unsafe company website should be rejected")


def test_no_sourcing_opt_in_does_not_publish_or_send(monkeypatch, tenant_db):
    monkeypatch.setattr(job_router, "enrich_jd_for_scoring", scoring_enrichment)
    monkeypatch.setattr(job_router, "_deliver_sourcing_request_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not send")))

    response = job_router.create_job(job_input(sourcing=False), user=recruiter("org-a"))

    assert response["sourcing_requested"] is False
    assert response["requirement_url"] is None
    assert job_router.public_sourcing_requirements(job_id=response["job_id"], limit=10)["count"] == 0
