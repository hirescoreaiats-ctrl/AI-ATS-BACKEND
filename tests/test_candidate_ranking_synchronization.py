from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.routers import job as job_router
from backend.services.scoring_context import apply_job_scoring_snapshot
from test_tenant_isolation import add_job, add_resume, recruiter, tenant_db


def test_results_select_latest_ranking_version_not_workflow_status(tenant_db):
    add_job(tenant_db, "job-a", "org-a", "Firmware Engineer")
    old = add_resume(tenant_db, "old", "job-a", "org-a", 82)
    old.email = "same@example.com"
    old.phone = "1111111111"
    old.status = "Shortlisted"
    old.ranking_version = 1
    old.ranking_updated_at = datetime.utcnow() - timedelta(days=1)
    latest = add_resume(tenant_db, "latest", "job-a", "org-a", 64)
    latest.email = "same@example.com"
    latest.phone = "2222222222"
    latest.status = "Review"
    latest.shortlist_decision = "maybe"
    latest.ranking_reason = "Latest evidence-based reason"
    latest.ranking_version = 3
    latest.ranking_updated_at = datetime.utcnow()
    tenant_db.commit()

    response = job_router.get_results("job-a", user=recruiter("org-a"))

    assert len(response["results"]) == 1
    assert response["results"][0]["resume_id"] == "latest"
    assert response["results"][0]["ranking_version"] == 3
    assert response["results"][0]["ranking_reason"] == "Latest evidence-based reason"


def test_same_candidate_keeps_job_specific_rankings(tenant_db):
    add_job(tenant_db, "job-a", "org-a", "Firmware Engineer")
    add_job(tenant_db, "job-b", "org-a", "QA Engineer")
    first = add_resume(tenant_db, "resume-a", "job-a", "org-a", 91)
    second = add_resume(tenant_db, "resume-b", "job-b", "org-a", 24)
    first.email = second.email = "person@example.com"
    first.ranking_version = second.ranking_version = 2
    tenant_db.commit()

    firmware = job_router.get_results("job-a", user=recruiter("org-a"))["results"][0]
    qa = job_router.get_results("job-b", user=recruiter("org-a"))["results"][0]

    assert (firmware["job_id"], firmware["final_score"]) == ("job-a", 91)
    assert (qa["job_id"], qa["final_score"]) == ("job-b", 24)


def test_rereview_response_and_results_share_committed_snapshot(monkeypatch, tenant_db):
    job = add_job(tenant_db, "job-a", "org-a", "Firmware Engineer")
    candidate = add_resume(tenant_db, "resume-a", "job-a", "org-a", 20)
    candidate.ranking_version = 1
    tenant_db.commit()

    def refresh(row, current_job, force=False):
        row.final_score = 73
        row.rank_score = 73
        row.ranking_reason = "Refreshed reason"
        row.shortlist_decision = "good match"
        row.last_company_name = "Canonical Company"
        apply_job_scoring_snapshot(row, current_job, {"jd_profile_version": "test-v1"})
        return True

    monkeypatch.setattr(job_router, "_repair_stored_candidate_profile", refresh)
    action = job_router.rereview_candidate_profile("resume-a", user=recruiter("org-a"))["candidate"]
    listing = job_router.get_results(job.id, user=recruiter("org-a"))["results"][0]

    for field in ("final_score", "rank_score", "ranking_reason", "shortlist_decision", "last_company_name", "ranking_version"):
        assert listing[field] == action[field]
    assert listing["ranking_version"] == 2


def test_candidate_detail_is_tenant_scoped(tenant_db):
    add_job(tenant_db, "job-b", "org-b", "Other Tenant Job")
    add_resume(tenant_db, "resume-b", "job-b", "org-b", 99)
    tenant_db.commit()

    with pytest.raises(job_router.HTTPException) as exc:
        job_router.candidate_workspace("resume-b", user=recruiter("org-a"))

    assert exc.value.status_code == 404


def test_score_publication_increments_version_and_refreshes_timestamp(tenant_db):
    job = add_job(tenant_db, "job-a", "org-a", "Firmware Engineer")
    candidate = add_resume(tenant_db, "resume-a", "job-a", "org-a", 50)
    candidate.ranking_version = 2

    apply_job_scoring_snapshot(candidate, job, {"jd_profile_version": "test-v1"})

    assert candidate.ranking_version == 3
    assert candidate.ranking_updated_at is not None
    assert candidate.score_job_id == "job-a"
