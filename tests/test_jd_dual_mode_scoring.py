from backend.jd_engine import normalize_jd_skills
from backend.services.jd_profile_engine import JD_PROFILE_VERSION, build_jd_profile
from backend.services.scoring_context import apply_job_scoring_snapshot, job_jd_hash
from backend.services.scoring_service import score_candidate


def test_known_role_uses_template_but_jd_specific_qa_tools_win():
    jd_text = """
    QA Automation Engineer. Experience: 1-3 Years.
    Required: Selenium, Java, TestNG, REST Assured, Postman, SQL, Jira, Git.
    """
    skills = normalize_jd_skills([], jd_text)
    profile = build_jd_profile(jd_text, {"role": "QA Automation Engineer"}, skills)

    assert profile["role_family"] == "qa_automation"
    assert profile["scoring_mode"] == "known_template"
    assert profile["known_template_used"] is True
    assert profile["dynamic_profile_used"] is False
    assert profile["jd_profile_version"] == JD_PROFILE_VERSION
    assert profile["core_skill_groups"]["ui_automation"] == ["Selenium"]
    assert "Cypress" not in profile["core_skill_groups"]["ui_automation"]
    assert "Playwright" not in profile["core_skill_groups"]["ui_automation"]
    assert profile["core_skill_groups"]["test_frameworks"] == ["TestNG"]


def test_unknown_procurement_jd_creates_dynamic_profile():
    jd_text = """
    Procurement Executive. Required: vendor management, purchase orders,
    negotiation, ERP/SAP, Excel and supply chain coordination.
    """
    profile = build_jd_profile(jd_text, {"role": "Procurement Executive"}, [])

    assert profile["role_family"] == "other"
    assert profile["scoring_mode"] == "dynamic"
    assert profile["dynamic_profile_used"] is True
    assert profile["known_template_used"] is False
    assert profile["normalized_role_label"] == "procurement"
    assert {"procurement_process", "vendor_management", "erp_tools"}.issubset(profile["core_skill_groups"])
    assert profile["profile_confidence"] < 75


def test_dynamic_keyword_only_candidate_cannot_score_high():
    jd_text = """
    Procurement Executive. Required: vendor management, purchase orders,
    negotiation, ERP/SAP, Excel and supply chain coordination.
    """
    profile = build_jd_profile(jd_text, {"role": "Procurement Executive", "experience_required": "1-3 Years"}, [])
    parsed = {
        "designation": "Office Assistant",
        "key_skills": ["Vendor Management", "Purchase Orders", "Negotiation", "ERP", "SAP", "Excel"],
        "total_experience_years": 2,
        "relevant_experience_years": 0.5,
        "direct_relevant_experience_years": 0,
        "role_relevance_score": 35,
        "resume_quality_score": 82,
        "semantic_score": 0.65,
        "experience": [{
            "company_name": "Acme Services",
            "role": "Office Assistant",
            "description": "Handled office documentation, scheduling and reports.",
        }],
    }

    result = score_candidate(
        parsed,
        jd_text,
        profile["must_have_skills"],
        {"role": "Procurement Executive", "min_experience_years": 1, "max_experience_years": 3},
        "Skills: Vendor Management Purchase Orders Negotiation ERP SAP Excel.",
        jd_profile=profile,
    )

    assert result["scoring_mode"] == "dynamic"
    assert result["final_score"] <= 55
    assert "skill_match_mostly_listed_only" in result["recruiter_flags"]
    assert result["dynamic_profile_used"] is True


def test_score_snapshot_is_scoped_by_job_hash_and_profile_version():
    class Job:
        id = "job-1"
        job_title = "QA Automation Engineer"
        role = "QA Automation Engineer"
        jd_text = "QA Automation Engineer. Selenium Java TestNG."
        required_skills = "Selenium, Java, TestNG"
        preferred_skills = ""
        experience_required = "1-3 Years"
        min_experience_years = 1
        education = ""
        jd_hash = None
        jd_profile_version = None
        jd_profile_json = None

    class Resume:
        score_job_id = None
        score_jd_hash = None
        score_jd_profile_version = None
        jd_profile_json = None
        jd_profile_snapshot_json = None

    job = Job()
    resume = Resume()
    profile = build_jd_profile(job.jd_text, {"role": job.role}, normalize_jd_skills(job.required_skills, job.jd_text))

    apply_job_scoring_snapshot(resume, job, profile)
    first_hash = job_jd_hash(job)

    assert resume.score_job_id == "job-1"
    assert resume.score_jd_hash == first_hash
    assert resume.score_jd_profile_version == JD_PROFILE_VERSION

    job.jd_text = "QA Automation Engineer. Selenium Java TestNG REST Assured."
    assert job_jd_hash(job) != first_hash
