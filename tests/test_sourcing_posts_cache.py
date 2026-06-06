from types import SimpleNamespace

from backend.services import sourcing


def make_job(**overrides):
    base = {
        "id": "job-1",
        "apply_slug": "data-analyst-job-1",
        "job_title": "Data Analyst",
        "company_name": "TechTest",
        "department": "Analytics",
        "location": "Noida / Gurugram",
        "work_mode": "Hybrid",
        "experience_required": "3+ Years",
        "salary_range": "5-8 LPA",
        "job_type": "Full Time",
        "required_skills": "SQL, Power BI, Excel",
        "jd_text": "Analyze data, build dashboards, and support business reporting.",
        "generated_linkedin_post": "",
        "generated_whatsapp_message": "",
        "generated_naukri_text": "",
        "generated_generic_post": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_complete_sourcing_posts_do_not_regenerate(monkeypatch):
    job = make_job(
        generated_linkedin_post="Saved LinkedIn",
        generated_whatsapp_message="Saved WhatsApp",
        generated_naukri_text="Saved Naukri",
        generated_generic_post="Saved Generic",
    )

    monkeypatch.setattr(
        sourcing,
        "generate_ai_sourcing_posts",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not regenerate")),
    )

    links = sourcing.ensure_generated_sourcing_content(job, db=None)
    payload = sourcing.sourcing_payload(job, db=None)

    assert links["main"].endswith("/apply/data-analyst-job-1")
    assert payload["generated_posts"]["linkedin"] == "Saved LinkedIn"
    assert payload["generated_posts"]["generic"] == "Saved Generic"


def test_missing_sourcing_posts_are_generated_and_stored_once(monkeypatch):
    job = make_job()
    calls = []

    def fake_generate(job_arg, db=None):
        calls.append(job_arg.id)
        return {
            "generated": True,
            "apply_links": sourcing.build_apply_links(job_arg, db),
            "generated_posts": {
                "linkedin": "AI LinkedIn",
                "whatsapp": "AI WhatsApp",
                "naukri": "AI Naukri",
                "generic": "AI Generic",
            },
        }

    monkeypatch.setattr(sourcing, "generate_ai_sourcing_posts", fake_generate)

    sourcing.ensure_generated_sourcing_content(job, db=None)
    sourcing.ensure_generated_sourcing_content(job, db=None)

    assert calls == ["job-1"]
    assert job.generated_linkedin_post == "AI LinkedIn"
    assert job.generated_whatsapp_message == "AI WhatsApp"
    assert job.generated_naukri_text == "AI Naukri"
    assert job.generated_generic_post == "AI Generic"
