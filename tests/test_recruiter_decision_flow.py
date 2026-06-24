from types import SimpleNamespace

from backend.jd_engine import normalize_jd_skills
from backend.routers import job as job_router
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.pipeline import analyze_resume_for_job
from backend.services.scoring_service import score_candidate


def test_jd_profile_extracts_critical_must_have():
    jd_text = """
    Data Analyst
    Must have SQL and Power BI.
    Mandatory: Advanced Excel for reporting.
    Nice to have: Tableau.
    """
    skills = normalize_jd_skills([], jd_text)
    profile = build_jd_profile(jd_text, {"role": "Data Analyst"}, skills)

    assert profile["role_family"] == "data_analytics"
    assert {"SQL", "Power BI"}.issubset(set(profile["critical_must_have"]))
    assert profile["scoring_config_key"] == "data_analytics"


def test_missing_critical_must_have_caps_score_and_blocks_strong_match():
    jd_text = """
    Data Analyst
    Must have SQL, Power BI, and Advanced Excel.
    Required: Python for analytics automation.
    """
    skills = normalize_jd_skills([], jd_text)
    profile = build_jd_profile(jd_text, {"role": "Data Analyst", "min_experience_years": 2}, skills)
    parsed = {
        "full_name": "Asha Analyst",
        "designation": "Data Analyst",
        "key_skills": ["SQL", "Advanced Excel", "Python", "Pandas"],
        "total_experience_years": 4,
        "relevant_experience_years": 3,
        "direct_relevant_experience_years": 3,
        "role_relevance_score": 90,
        "resume_quality_score": 90,
        "semantic_score": 0.88,
        "experience": [{
            "company_name": "Acme Analytics",
            "role": "Data Analyst",
            "description": "Built SQL reporting automation with Advanced Excel and Python analytics.",
        }],
        "projects": [{
            "name": "Reporting Automation",
            "description": "Developed SQL and Python automation for KPI reporting.",
            "technologies": ["SQL", "Python", "Excel"],
        }],
    }

    result = score_candidate(parsed, jd_text, profile["must_have_skills"], {"role": "Data Analyst", "min_experience_years": 2}, jd_text, jd_profile=profile)

    assert "Power BI" in result["missing_critical_skills"]
    assert result["final_score"] <= 65
    assert result["shortlist_decision"] != "Strong Match"
    assert "critical_skill_gap" in result["risk_flags"]


def test_low_parser_confidence_becomes_needs_review():
    jd_text = "Backend Developer. Must have Python, FastAPI, SQL."
    skills = normalize_jd_skills([], jd_text)
    profile = build_jd_profile(jd_text, {"role": "Backend Developer", "min_experience_years": 1}, skills)
    parsed = {
        "designation": "Backend Developer",
        "key_skills": ["Python", "FastAPI", "SQL"],
        "total_experience_years": 2,
        "relevant_experience_years": 2,
        "role_relevance_score": 85,
        "resume_quality_score": 30,
        "parser_quality_action": "manual_review_required",
        "parser_quality_score": 30,
        "semantic_score": 0.9,
        "experience": [{
            "company_name": "Acme",
            "role": "Backend Developer",
            "description": "Built Python FastAPI services with SQL databases.",
        }],
    }

    result = score_candidate(parsed, jd_text, profile["must_have_skills"], {"role": "Backend Developer", "min_experience_years": 1}, jd_text, jd_profile=profile)

    assert result["final_score"] <= 58
    assert result["shortlist_decision"] == "Needs Review"
    assert "parser_quality" in result["risk_flags"]


def test_unreadable_resume_is_not_auto_shortlisted():
    parsed, _exp_data, score_data = analyze_resume_for_job("", "Backend Developer. Must have Python.", ["Python"], {"role": "Backend Developer"})

    assert parsed["shortlist_decision"] == "Needs Review"
    assert parsed["final_score"] == 0
    assert parsed["parser_quality_action"] == "manual_review_required"
    assert parsed["recommendation"] == "in_review"
    assert score_data["ai_parse_status"] == "regex_fallback_only"


def test_rescore_endpoint_continues_when_one_candidate_fails(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        job_title="Backend Developer",
        role="Backend Developer",
        jd_text="Must have Python and FastAPI.",
        required_skills="Python,FastAPI",
        preferred_skills="SQL",
        experience_required="2+ Years",
        min_experience_years=2,
        education="",
        jd_hash=None,
        jd_profile_version=None,
        jd_profile_json=None,
    )
    good = SimpleNamespace(id="resume-good", full_name="Good Candidate", email="", is_active=True, processing_status="completed", processing_error=None)
    bad = SimpleNamespace(id="resume-bad", full_name="Bad Candidate", email="", is_active=True, processing_status="completed", processing_error=None)

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return [good, bad]

    class FakeDb:
        commits = 0
        rollbacks = 0
        closed = False

        def query(self, _model):
            return FakeQuery()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    fake_db = FakeDb()

    def fake_rescore(candidate, _job):
        if candidate.id == "resume-bad":
            raise RuntimeError("parse failed")
        candidate.final_score = 82

    monkeypatch.setattr(job_router, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(job_router, "resolve_job_identifier", lambda _job_id, _db: job)
    monkeypatch.setattr(job_router, "_rescore_candidate_from_stored_fields", fake_rescore)

    result = job_router.rescore_job_candidates("job-1")

    assert result["total_candidates"] == 2
    assert result["rescored"] == 1
    assert result["failed"] == 1
    assert result["errors"][0]["resume_id"] == "resume-bad"
    assert fake_db.commits >= 1
    assert fake_db.rollbacks == 1
