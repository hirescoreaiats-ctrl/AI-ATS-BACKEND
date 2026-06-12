from backend.experience_engine import process_experience
from backend.services.canonical_parser import parse_resume_document
from backend.services.document_classifier import classify_resume_document
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.pipeline import analyze_resume_for_job
from backend.services.scoring_service import score_candidate


BUSINESS_ANALYST_JD = """
Job Title: Business Analyst
Experience Required: 1-3 Years
The candidate will gather business requirements, document BRD, FRD and SRS,
write user stories, use cases and acceptance criteria, coordinate with
stakeholders, support UAT, manage change requests, create process flows and
work in Agile sprint planning. SQL, Excel, Power BI, Jira and Confluence are useful.
"""


def _profile():
    return build_jd_profile(
        BUSINESS_ANALYST_JD,
        {"role": "Business Analyst", "experience_required": "1-3 Years"},
        [],
    )


def _score(parsed, resume_text):
    profile = _profile()
    parsed.update(estimate_relevant_experience_v2(parsed, resume_text, profile))
    if not parsed.get("total_experience_years"):
        parsed["total_experience_years"] = 1.2
    return score_candidate(
        parsed,
        BUSINESS_ANALYST_JD,
        profile["must_have_skills"],
        {"role": "Business Analyst", "min_experience_years": 1, "max_experience_years": 3},
        resume_text,
        jd_profile=profile,
    )


def test_business_analyst_profile_uses_ba_family_and_core_groups():
    profile = _profile()

    assert profile["role_family"] == "business_analyst"
    groups = profile["core_skill_groups"]
    assert "requirements_gathering" in groups
    assert "requirements_documentation" in groups
    assert "stakeholder_coordination" in groups
    assert "uat_change_management" in groups


def test_business_analyst_intern_with_requirements_evidence_outranks_dashboard_only_data_analyst():
    ba_text = """
    Priya Sharma
    priya@example.com | 9999999999
    Professional Experience
    Business Analyst Intern, Alpha Systems, Jun 2025 - Present
    Gathered business requirements from stakeholders, documented BRD and FRD,
    wrote user stories, use cases and acceptance criteria, supported UAT and
    tracked change requests during sprint planning.
    Education
    B.Tech Computer Science
    Skills
    Business Analysis, Requirement Gathering, User Stories, Use Cases, UAT, Jira, SQL
    """
    dashboard_text = """
    Arjun Mehta
    arjun@example.com | 8888888888
    Professional Experience
    Data Analyst, Digital Realty, Jun 2024 - Present
    Built Power BI dashboards, KPI reports, SQL extracts and Excel reporting packs
    for operational metrics and data visualization.
    Education
    BBA
    Skills
    SQL, Excel, Power BI, Tableau, Dashboard Reporting, Data Cleaning
    """
    ba_parsed = {
        "full_name": "Priya Sharma",
        "current_title": "Business Analyst Intern",
        "designation": "Business Analyst Intern",
        "key_skills": ["Business Analysis", "Requirement Gathering", "User Stories", "Use Cases", "UAT", "Jira", "SQL"],
        "education": [{"degree": "B.Tech Computer Science"}],
        "experience": [{
            "company_name": "Alpha Systems",
            "role": "Business Analyst Intern",
            "start_date": "Jun 2025",
            "end_date": "Present",
            "description": "Gathered business requirements from stakeholders, documented BRD and FRD, wrote user stories, use cases and acceptance criteria, supported UAT and tracked change requests during sprint planning.",
        }],
        "parser_quality_score": 90,
    }
    dashboard_parsed = {
        "full_name": "Arjun Mehta",
        "current_title": "Data Analyst",
        "designation": "Data Analyst",
        "key_skills": ["SQL", "Excel", "Power BI", "Tableau", "Dashboard Reporting", "Data Cleaning"],
        "education": [{"degree": "BBA"}],
        "experience": [{
            "company_name": "Digital Realty",
            "role": "Data Analyst",
            "start_date": "Jun 2024",
            "end_date": "Present",
            "description": "Built Power BI dashboards, KPI reports, SQL extracts and Excel reporting packs for operational metrics and data visualization.",
        }],
        "parser_quality_score": 90,
    }

    ba_result = _score(ba_parsed, ba_text)
    dashboard_result = _score(dashboard_parsed, dashboard_text)

    assert ba_result["final_score"] > dashboard_result["final_score"]
    assert ba_result["role_alignment"] == "direct"
    assert dashboard_result["final_score"] <= 52
    assert "analytics_only_for_ba" in dashboard_result["recruiter_flags"]


def test_application_form_is_rejected_before_scoring():
    text = """
    NICDC Logistics Data Services
    APPLICATION FORM
    Name of the position applied for: Business Analyst
    Affix your recent passport size photo
    Job description for the post
    Selection process and how to apply
    Declaration
    """

    classification = classify_resume_document(text, filename="application.pdf")
    parsed, _, score = analyze_resume_for_job(text, BUSINESS_ANALYST_JD, [], {"role": "Business Analyst"})

    assert classification.is_resume is False
    assert score["final_score"] == 0
    assert parsed["invalid_resume_type"] == "application_form"


def test_parser_rejects_bad_candidate_names_and_company_fragments():
    parsed = parse_resume_document(
        "City state GPA\nEmail: candidate@example.com\nPhone: 9999999999\nSkills: SQL, Excel",
        ai_parse_override={"full_name": "City state Gpa", "email": "candidate@example.com"},
    )
    company_result = process_experience([
        {"company_name": "DA TA ANALY ST", "role": "Data Analyst", "start_date": "Jan 2024", "end_date": "Present"},
        {"company_name": "Digitalrealty Usa Remote", "role": "Business Analyst Intern", "start_date": "Jan 2024", "end_date": "Present"},
    ])

    assert parsed["full_name"] == ""
    assert not company_result["last_company_name"]
    assert company_result["last_company_needs_review"] is True
