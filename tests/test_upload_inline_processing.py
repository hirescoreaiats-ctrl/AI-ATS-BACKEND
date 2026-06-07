from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.models import Job, Resume
from backend.routers import resume as resume_router


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeUploadFile:
    filename = "candidate.pdf"
    content_type = "application/pdf"

    async def read(self):
        return b"%PDF resume bytes"


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


class FakeQuery:
    def __init__(self, item=None):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item

    def all(self):
        return []


class FakeUploadDB:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(None)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class FakeProcessingDB:
    def __init__(self, resume, job):
        self.resume = resume
        self.job = job
        self.commits = 0
        self.closed = False

    def query(self, model):
        if model is Resume:
            return FakeQuery(self.resume)
        if model is Job:
            return FakeQuery(self.job)
        return FakeQuery(None)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def fake_job():
    return SimpleNamespace(
        id="job-1",
        organization_id="org-1",
        required_skills="Python, SQL",
        jd_text="Data Analyst with Python and SQL",
        min_experience_years=2,
        education="",
        role="Data Analyst",
        preferred_skills="",
        shortlist_score=70,
        source_tracking_enabled=True,
    )


def upload_kwargs():
    return {
        "form_full_name": None,
        "form_email": None,
        "form_phone": None,
        "form_location": None,
        "expected_salary": None,
        "preferred_location": None,
        "notice_period": None,
        "linkedin": None,
        "github": None,
        "portfolio": None,
        "application_source": None,
        "apply_tracking_url": None,
    }


@pytest.mark.anyio
async def test_upload_resumes_processes_inline_by_default(monkeypatch):
    db = FakeUploadDB()
    processed_ids = []

    monkeypatch.delenv("RESUME_PROCESSING_MODE", raising=False)
    monkeypatch.delenv("PROCESS_RESUMES_INLINE", raising=False)
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", lambda: SimpleNamespace(use_vercel_blob_storage=True))
    monkeypatch.setattr(
        resume_router,
        "upload_resume_file",
        lambda *args, **kwargs: SimpleNamespace(
            storage_uri="vercel_blob://resumes/org-1/job-1/resume_candidate.pdf",
            url="private-url",
            key="resumes/org-1/job-1/resume_candidate.pdf",
            file_size=17,
            mime_type="application/pdf",
            uploaded_at=datetime.utcnow(),
        ),
    )
    monkeypatch.setattr(resume_router, "_process_resume_application_background", lambda resume_id: processed_ids.append(resume_id) or True)

    result = await resume_router.upload_resumes("job-1", FakeBackgroundTasks(), files=[FakeUploadFile()], **upload_kwargs())

    assert result["processing_mode"] == "inline"
    assert result["processing"] is False
    assert result["processing_failures"] == 0
    assert len(db.added) == 1
    assert processed_ids == [db.added[0].id]


@pytest.mark.anyio
async def test_upload_resumes_can_use_background_mode(monkeypatch):
    db = FakeUploadDB()
    background_tasks = FakeBackgroundTasks()
    processed_ids = []

    monkeypatch.setenv("RESUME_PROCESSING_MODE", "background")
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", lambda: SimpleNamespace(use_vercel_blob_storage=True))
    monkeypatch.setattr(
        resume_router,
        "upload_resume_file",
        lambda *args, **kwargs: SimpleNamespace(
            storage_uri="vercel_blob://resumes/org-1/job-1/resume_candidate.pdf",
            url="private-url",
            key="resumes/org-1/job-1/resume_candidate.pdf",
            file_size=17,
            mime_type="application/pdf",
            uploaded_at=datetime.utcnow(),
        ),
    )
    monkeypatch.setattr(resume_router, "_process_resume_application_background", lambda resume_id: processed_ids.append(resume_id) or True)

    result = await resume_router.upload_resumes("job-1", background_tasks, files=[FakeUploadFile()], **upload_kwargs())

    assert result["processing_mode"] == "background"
    assert result["processing"] is True
    assert processed_ids == []
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0][1] == (db.added[0].id,)


def test_processing_updates_candidate_when_extraction_succeeds(monkeypatch):
    resume = Resume(
        id="resume-1",
        job_id="job-1",
        resume_file_path="vercel_blob://resumes/org-1/job-1/resume_candidate.pdf",
        final_score=0,
        rank_score=0,
    )
    job = fake_job()
    db = FakeProcessingDB(resume, job)

    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "_extract_resume_text_from_file_path", lambda *args, **kwargs: "Data Analyst resume with Python SQL")
    monkeypatch.setattr(resume_router, "normalize_jd_skills", lambda *args, **kwargs: ["Python", "SQL"])
    monkeypatch.setattr(resume_router, "apply_resume_intelligence_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(resume_router, "apply_job_scoring_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(resume_router, "enrich_candidate_embedding", lambda resume_arg: None)
    monkeypatch.setattr(
        resume_router,
        "analyze_resume_for_job",
        lambda *args, **kwargs: (
            {
                "full_name": "Asha Sharma",
                "email": "asha@example.com",
                "phone": "9999999999",
                "location": "Noida",
                "key_skills": ["Python", "SQL"],
                "projects": [],
                "designation": "Data Analyst",
                "total_experience_years": 3,
                "education": [],
                "final_score": 82,
                "rank_score": 82,
                "fit_band": "Good Match",
                "recommendation": "shortlisted",
                "matched_skills": ["Python", "SQL"],
                "missing_skills": [],
                "skill_match_percent": 100,
            },
            {},
            {},
        ),
    )

    assert resume_router._process_resume_application_background("resume-1") is True
    assert resume.full_name == "Asha Sharma"
    assert resume.email == "asha@example.com"
    assert resume.rank_score == 82
    assert resume.status == "Shortlisted"
    assert db.commits == 1
