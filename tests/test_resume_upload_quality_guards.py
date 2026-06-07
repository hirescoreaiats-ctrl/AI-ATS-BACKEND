from backend.experience_engine import process_experience
from backend.services.canonical_parser import parse_resume_document
from backend.services.document_classifier import classify_resume_document


def test_document_classifier_rejects_job_description_form():
    text = """
    JOB TITLE
    Minimum 3 years of professional experience
    COMPANY NAME Infometry
    DEPARTMENT Analytics
    JOB LOCATION Noida / Gurugram / Hybrid
    EXPERIENCE REQUIRED Required: 3+ Years
    SALARY RANGE 8-12 LPA
    APPLICATION DEADLINE
    """

    result = classify_resume_document(text, filename="data-analyst-jd.pdf")

    assert result.is_resume is False
    assert result.label == "non_resume"


def test_document_classifier_allows_real_resume():
    text = """
    Asha Sharma
    asha@example.com | 9999999999 | Noida
    Professional Experience
    Data Analyst, Acme Analytics, Jan 2022 - Present
    Built SQL, Excel and Power BI dashboards for KPI reporting.
    Education
    B.Tech Computer Science
    Technical Skills
    SQL, Advanced Excel, Power BI, Power Query, DAX, Data Cleaning
    """

    result = classify_resume_document(text, filename="asha-resume.pdf")

    assert result.is_resume is True


def test_canonical_parser_clears_form_label_as_candidate_name():
    parsed = parse_resume_document(
        "Preferred Full Name\nEmail: candidate@example.com\nPhone: 9999999999\nSkills: SQL, Excel, Power BI",
        ai_parse_override={"full_name": "Preferred Full Name", "email": "candidate@example.com"},
    )

    assert parsed["full_name"] == ""
    assert "name_needs_review" in parsed.get("parser_flags", [])


def test_current_company_wins_last_company_detection():
    result = process_experience([
        {
            "company_name": "The Ministry of National Defense",
            "role": "Systems Engineer",
            "start_date": "Sep 2010",
            "end_date": "Aug 2014",
        },
        {
            "company_name": "Mega Metal",
            "role": "Data Analyst",
            "start_date": "Feb 2024",
            "end_date": "Present",
        },
    ])

    assert result["last_company_name"] == "Mega Metal"
    assert result["last_working_date"] == "Present"
