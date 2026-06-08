from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.models import Job, Resume
from backend.routers import resume as resume_router


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeUploadFile:
    _counter = 0

    def __init__(self, filename="candidate.pdf", content=None, content_type="application/pdf"):
        FakeUploadFile._counter += 1
        self.filename = filename
        self.content_type = content_type
        self.content = content if content is not None else f"%PDF resume bytes {FakeUploadFile._counter}".encode()

    async def read(self):
        return self.content


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

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class FakeProgressDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        if model is Resume:
            return FakeProgressQuery(self.rows)
        return FakeProgressQuery(None)

    def close(self):
        pass


class FakeProgressQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows


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
        "folder_total_count": None,
    }


def folder_upload_kwargs():
    values = upload_kwargs()
    values["application_source"] = "folder"
    values["folder_total_count"] = 1
    return values


def fake_settings():
    return SimpleNamespace(
        use_vercel_blob_storage=True,
        max_resume_upload_count=100,
        resume_processing_batch_size=3,
        upload_bytes_limit=20 * 1024 * 1024,
        resume_upload_limit_mb=20,
    )


def fake_blob_metadata(resume_id="resume-candidate"):
    return SimpleNamespace(
        storage_uri=f"vercel_blob://resumes/org-1/job-1/{resume_id}.pdf",
        url="private-url",
        key=f"resumes/org-1/job-1/{resume_id}.pdf",
        file_size=17,
        mime_type="application/pdf",
        uploaded_at=datetime.utcnow(),
    )


@pytest.mark.anyio
async def test_upload_resumes_processes_inline_by_default(monkeypatch):
    db = FakeUploadDB()
    processed_ids = []

    monkeypatch.setenv("RESUME_PROCESSING_MODE", "inline")
    monkeypatch.delenv("PROCESS_RESUMES_INLINE", raising=False)
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_preclassify_upload_resume", lambda filename, contents: None)
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
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_preclassify_upload_resume", lambda filename, contents: None)
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


@pytest.mark.anyio
async def test_folder_upload_queues_processing_to_avoid_request_timeout(monkeypatch):
    db = FakeUploadDB()
    queued_ids = []
    processed_ids = []

    monkeypatch.delenv("RESUME_PROCESSING_MODE", raising=False)
    monkeypatch.delenv("FOLDER_RESUME_PROCESSING_MODE", raising=False)
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_preclassify_upload_resume", lambda filename, contents: None)
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
    monkeypatch.setattr(resume_router, "_queue_resume_processing", lambda resume_id: queued_ids.append(resume_id))
    monkeypatch.setattr(resume_router, "_process_resume_application_background", lambda resume_id: processed_ids.append(resume_id) or True)

    result = await resume_router.upload_resumes("job-1", FakeBackgroundTasks(), files=[FakeUploadFile()], **folder_upload_kwargs())

    assert result["processing_mode"] == "queued"
    assert result["processing"] is True
    assert processed_ids == []
    assert queued_ids == [db.added[0].id]


@pytest.mark.anyio
async def test_folder_upload_accepts_100_resumes(monkeypatch):
    db = FakeUploadDB()

    monkeypatch.setenv("FOLDER_RESUME_PROCESSING_MODE", "queued")
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_preclassify_upload_resume", lambda filename, contents: None)
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
    monkeypatch.setattr(resume_router, "_queue_resume_processing_batch", lambda resume_ids: None)

    kwargs = folder_upload_kwargs()
    kwargs["folder_total_count"] = 100
    result = await resume_router.upload_resumes("job-1", FakeBackgroundTasks(), files=[FakeUploadFile() for _ in range(100)], **kwargs)

    assert result["total_resumes"] == 100
    assert len(db.added) == 100
    assert all(row.processing_status == "pending" for row in db.added)
    assert all(row.status == "Pending Processing" for row in db.added)


@pytest.mark.anyio
async def test_upload_resumes_skips_duplicate_file_hash_within_same_request(monkeypatch):
    db = FakeUploadDB()

    monkeypatch.setenv("FOLDER_RESUME_PROCESSING_MODE", "queued")
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_preclassify_upload_resume", lambda filename, contents: None)
    monkeypatch.setattr(resume_router, "upload_resume_file", lambda *args, **kwargs: fake_blob_metadata())
    monkeypatch.setattr(resume_router, "_queue_resume_processing_batch", lambda resume_ids: None)

    duplicate_content = b"%PDF same resume bytes"
    result = await resume_router.upload_resumes(
        "job-1",
        FakeBackgroundTasks(),
        files=[
            FakeUploadFile(filename="candidate-a.pdf", content=duplicate_content),
            FakeUploadFile(filename="candidate-a-copy.pdf", content=duplicate_content),
        ],
        **folder_upload_kwargs(),
    )

    assert result["total_resumes"] == 1
    assert result["duplicates"] == 1
    assert len(db.added) == 1


@pytest.mark.anyio
async def test_upload_resumes_rejects_non_resume_document_before_row_creation(monkeypatch):
    db = FakeUploadDB()
    classification = SimpleNamespace(
        is_resume=False,
        reason="Document looks like a JD/application form, not a candidate resume.",
    )

    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_preclassify_upload_resume", lambda filename, contents: classification)

    result = await resume_router.upload_resumes("job-1", FakeBackgroundTasks(), files=[FakeUploadFile()], **upload_kwargs())

    assert result["status"] == "failed"
    assert result["total_resumes"] == 0
    assert result["skipped"] == 1
    assert "JD/application form" in result["files"][0]["reason"]
    assert db.added == []


@pytest.mark.anyio
async def test_folder_upload_accepts_41_files_and_returns_per_file_status(monkeypatch):
    db = FakeUploadDB()
    queued_batches = []

    monkeypatch.setenv("FOLDER_RESUME_PROCESSING_MODE", "queued")
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "upload_resume_file", lambda *args, **kwargs: fake_blob_metadata())
    monkeypatch.setattr(resume_router, "_queue_resume_processing_batch", lambda resume_ids: queued_batches.append(list(resume_ids)))

    kwargs = folder_upload_kwargs()
    kwargs["folder_total_count"] = 41
    files = [FakeUploadFile(filename=f"candidate-{index}.pdf") for index in range(41)]
    result = await resume_router.upload_resumes("job-1", FakeBackgroundTasks(), files=files, **kwargs)

    assert result["status"] == "success"
    assert result["total_resumes"] == 41
    assert result["queued"] == 41
    assert len(result["files"]) == 41
    assert all(item["status"] == "uploaded" for item in result["files"])
    assert queued_batches and len(queued_batches[0]) == 41


@pytest.mark.anyio
async def test_upload_blob_failure_for_one_file_does_not_fail_batch(monkeypatch):
    db = FakeUploadDB()

    monkeypatch.setenv("FOLDER_RESUME_PROCESSING_MODE", "queued")
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "validate_upload", lambda file, size: None)
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_queue_resume_processing_batch", lambda resume_ids: None)

    def fake_upload(file_bytes, original_filename, *args, **kwargs):
        if original_filename == "bad.pdf":
            raise HTTPException(status_code=502, detail="Vercel Blob upload failed")
        return fake_blob_metadata()

    monkeypatch.setattr(resume_router, "upload_resume_file", fake_upload)

    result = await resume_router.upload_resumes(
        "job-1",
        FakeBackgroundTasks(),
        files=[FakeUploadFile(filename="bad.pdf"), FakeUploadFile(filename="good.pdf")],
        **folder_upload_kwargs(),
    )

    assert result["status"] == "partial_success"
    assert result["total_resumes"] == 1
    assert result["failed"] == 1
    assert len(db.added) == 1
    assert {item["status"] for item in result["files"]} == {"failed", "uploaded"}


@pytest.mark.anyio
async def test_upload_unsupported_and_hidden_files_are_skipped(monkeypatch):
    db = FakeUploadDB()

    monkeypatch.setenv("FOLDER_RESUME_PROCESSING_MODE", "queued")
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "build_apply_links", lambda job, db_arg: {"direct": "https://app/apply", "main": "https://app/apply"})
    monkeypatch.setattr(resume_router, "malware_scan", lambda path: None)
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "upload_resume_file", lambda *args, **kwargs: fake_blob_metadata())
    monkeypatch.setattr(resume_router, "_queue_resume_processing_batch", lambda resume_ids: None)

    result = await resume_router.upload_resumes(
        "job-1",
        FakeBackgroundTasks(),
        files=[
            FakeUploadFile(filename=".DS_Store", content=b"metadata", content_type="application/octet-stream"),
            FakeUploadFile(filename="notes.txt", content=b"not a resume", content_type="text/plain"),
            FakeUploadFile(filename="candidate.pdf"),
        ],
        **folder_upload_kwargs(),
    )

    assert result["status"] == "partial_success"
    assert result["total_resumes"] == 1
    assert result["skipped"] == 2
    assert len(db.added) == 1
    assert [item["status"] for item in result["files"]] == ["skipped", "skipped", "uploaded"]


@pytest.mark.anyio
async def test_folder_upload_rejects_101_resumes(monkeypatch):
    db = FakeUploadDB()

    monkeypatch.setattr(resume_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: fake_job())
    monkeypatch.setattr(resume_router, "get_settings", fake_settings)

    kwargs = folder_upload_kwargs()
    kwargs["folder_total_count"] = 101
    with pytest.raises(HTTPException) as exc:
        await resume_router.upload_resumes("job-1", FakeBackgroundTasks(), files=[FakeUploadFile()], **kwargs)

    assert exc.value.status_code == 413
    assert exc.value.detail == "Maximum 100 resumes can be synced at once."


def test_processing_batch_queues_all_resumes_with_batch_size(monkeypatch):
    queued = []

    monkeypatch.setattr(resume_router, "get_settings", fake_settings)
    monkeypatch.setattr(resume_router, "_queue_resume_processing", lambda resume_id: queued.append(resume_id))

    resume_router._queue_resume_processing_batch(["r1", "r2", "r3", "r4"])

    assert queued == ["r1", "r2", "r3", "r4"]


def test_resume_processing_progress_counts(monkeypatch):
    rows = [
        Resume(job_id="job-1", processing_status="pending", status="Pending Processing", is_active=True),
        Resume(job_id="job-1", processing_status="processing", status="Processing", is_active=True),
        Resume(job_id="job-1", processing_status="completed", status="Shortlisted", is_active=True),
        Resume(job_id="job-1", processing_status="failed", status="Needs Review", is_active=True),
    ]
    monkeypatch.setattr(resume_router, "SessionLocal", lambda: FakeProgressDB(rows))
    monkeypatch.setattr(resume_router, "resolve_job_identifier", lambda job_id, db_arg: SimpleNamespace(id="job-1"))

    result = resume_router.resume_processing_progress("job-1")

    assert result["total"] == 4
    assert result["pending"] == 1
    assert result["processing"] == 1
    assert result["completed"] == 1
    assert result["failed"] == 1
    assert result["needs_review"] == 1
    assert result["percent"] == 50


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
    assert db.commits == 2
