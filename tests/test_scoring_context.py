import inspect

from backend.models import Job, Resume
from backend.routers.job import _rescore_candidate_from_stored_fields
from backend.services.scoring_context import apply_job_scoring_snapshot, job_jd_hash


def test_score_snapshot_is_bound_to_the_current_job_jd():
    first_job = Job(
        id="job-a",
        job_title="Data Analyst",
        role="Data Analyst",
        jd_text="Need SQL, Excel and Power BI reporting.",
        required_skills="SQL,Excel,Power BI",
        preferred_skills="Tableau",
        experience_required="3+ Years",
        min_experience_years=3,
    )
    second_job = Job(
        id="job-b",
        job_title="Data Analyst",
        role="Data Analyst",
        jd_text="Need Python, Pandas and statistics for analytics.",
        required_skills="Python,Pandas,Statistics",
        preferred_skills="SQL",
        experience_required="1+ Years",
        min_experience_years=1,
    )
    resume = Resume(id="resume-1", job_id="job-a")

    apply_job_scoring_snapshot(resume, first_job)

    assert resume.score_job_id == "job-a"
    assert resume.score_jd_hash == job_jd_hash(first_job)
    assert resume.score_jd_hash != job_jd_hash(second_job)


def test_stored_field_rescore_does_not_reuse_previous_ranking_reason_as_resume_evidence():
    source = inspect.getsource(_rescore_candidate_from_stored_fields)

    assert "candidate.ranking_reason or \"\"" not in source
    assert "\"description\": candidate.resume_text or \"\"" in source
