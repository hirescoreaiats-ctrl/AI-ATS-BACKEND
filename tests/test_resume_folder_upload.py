from pathlib import Path
from types import SimpleNamespace

from backend.models import Resume
from backend.routers import job as job_router


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.items[0] if self.items else None


class FakeDB:
    def __init__(self, existing=None):
        self.added = []
        self.existing = existing or []

    def query(self, model):
        return FakeQuery(self.existing if model is Resume else [])

    def add(self, item):
        self.added.append(item)


def test_folder_upload_creates_resume_object_with_original_filename(monkeypatch, tmp_path):
    source = tmp_path / "stored_tmp_resume.pdf"
    source.write_bytes(b"%PDF test resume")
    upload_root = tmp_path / "uploads"
    db = FakeDB()
    fake_job = SimpleNamespace(
        id="job-1",
        organization_id="org-1",
        required_skills="Python",
        jd_text="Python Developer",
        min_experience_years=2,
        education="",
        role="Python Developer",
        job_title="Python Developer",
        preferred_skills="",
        shortlist_score=70,
    )

    monkeypatch.setattr(job_router, "_extract_folder_resume_text", lambda path: "Python Developer resume text")
    monkeypatch.setattr(job_router, "get_settings", lambda: SimpleNamespace(upload_dir=str(upload_root)))
    monkeypatch.setattr(job_router, "persist_resume_file", lambda path, name, content_type, job_id: path)
    monkeypatch.setattr(
        job_router,
        "analyze_resume_for_job",
        lambda *args, **kwargs: (
            {
                "full_name": "Asha Sharma",
                "email": "asha@example.com",
                "phone": "9999999999",
                "key_skills": ["Python"],
                "projects": [],
                "designation": "Python Developer",
                "total_experience_years": 3,
                "education": [],
                "final_score": 82,
                "rank_score": 82,
                "recommendation": "shortlisted",
                "matched_skills": ["Python"],
                "missing_skills": [],
            },
            {},
            {},
        ),
    )

    created, reason = job_router._save_folder_resume_application(
        db,
        fake_job,
        source,
        original_filename="Asha Resume.pdf",
    )

    assert created is True
    assert reason == "imported"
    assert len(db.added) == 1
    resume = db.added[0]
    assert isinstance(resume, Resume)
    assert resume.resume_original_filename == "Asha Resume.pdf"
    assert resume.resume_file_path
    assert Path(resume.resume_file_path).exists()
    assert resume.application_source == "folder"


def test_folder_upload_skips_existing_resume_for_same_job(monkeypatch, tmp_path):
    source = tmp_path / "stored_tmp_resume.pdf"
    source.write_bytes(b"%PDF duplicate resume")
    existing_resume = Resume(job_id="job-1", email="asha@example.com", duplicate_key="existing")
    db = FakeDB(existing=[existing_resume])
    fake_job = SimpleNamespace(
        id="job-1",
        organization_id="org-1",
        required_skills="Python",
        jd_text="Python Developer",
        min_experience_years=2,
        education="",
        role="Python Developer",
        job_title="Python Developer",
        preferred_skills="",
        shortlist_score=70,
    )

    monkeypatch.setattr(job_router, "_extract_folder_resume_text", lambda path: "Python Developer resume text")
    monkeypatch.setattr(job_router, "get_settings", lambda: SimpleNamespace(upload_dir=str(tmp_path / "uploads")))
    monkeypatch.setattr(
        job_router,
        "analyze_resume_for_job",
        lambda *args, **kwargs: (
            {
                "full_name": "Asha Sharma",
                "email": "asha@example.com",
                "phone": "9999999999",
                "key_skills": ["Python"],
                "projects": [],
                "designation": "Python Developer",
                "total_experience_years": 3,
                "education": [],
                "final_score": 82,
                "rank_score": 82,
                "recommendation": "shortlisted",
                "matched_skills": ["Python"],
                "missing_skills": [],
            },
            {},
            {},
        ),
    )

    created, reason = job_router._save_folder_resume_application(
        db,
        fake_job,
        source,
        original_filename="Asha Resume.pdf",
    )

    assert created is False
    assert reason == "duplicate skipped"
    assert db.added == []
