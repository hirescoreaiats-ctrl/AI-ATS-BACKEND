from backend.services.canonical_parser import parse_resume_document
from backend.services.pipeline import analyze_resume_for_job
from backend.validation_scoring import validate_phone


def test_year_range_never_validates_as_phone():
    assert validate_phone("2020-2024") is None
    assert validate_phone("Education: 2020 - 2024") is None


def test_work_experience_is_not_promoted_to_project_without_project_section():
    text = """
    Rahul Sharma
    rahul.sharma@example.com
    +91 9876543210

    Work Experience
    Data Analyst, Acme Analytics, 2021 - Present
    Built Power BI dashboards and SQL reports for weekly business reviews.

    Education
    Bachelor of Technology, ABC University, 2016 - 2020

    Skills
    SQL, Excel, Power BI
    """

    parsed = parse_resume_document(text, mode="test", ai_parse_override={})

    assert parsed["email"] == "rahul.sharma@example.com"
    assert parsed["phone"] == "9876543210"
    assert parsed.get("projects") == []


def test_education_text_is_not_promoted_to_project_without_project_section():
    text = """
    Priya Mehta
    priya.mehta@example.com
    +91 9123456789

    Education
    Master of Science in Business Analytics, XYZ University, 2022 - 2024
    Bachelor of Commerce, ABC College, 2018 - 2021

    Skills
    Excel, SQL, Tableau
    """

    parsed = parse_resume_document(text, mode="test", ai_parse_override={})

    assert parsed.get("projects") == []
    assert parsed.get("education")


def test_missing_company_but_valid_role_and_dates_keeps_low_confidence_experience():
    text = """
    Aman Verma
    aman.verma@example.com
    +91 9988776655

    Professional Experience
    Data Analyst | 2021 - Present
    Built SQL reports, Excel trackers, and Power BI dashboards for operations teams.

    Skills
    SQL, Excel, Power BI
    """

    parsed = parse_resume_document(text, mode="test", ai_parse_override={})

    assert parsed.get("experience")
    assert any(item.get("needs_review") for item in parsed["experience"])
    assert "company_needs_review" in set(parsed.get("parser_flags") or [])


def test_canonical_parse_metadata_is_available_for_application_scoring():
    text = """
    Neha Singh
    neha.singh@example.com
    +91 9876501234

    Work Experience
    Data Analyst, Bright Data, 2020 - Present
    Created SQL reports, Power BI dashboards, and Excel KPI trackers.

    Skills
    SQL, Excel, Power BI
    """
    jd_text = "Data Analyst role requiring SQL, Excel and Power BI reporting."
    jd_skills = ["SQL", "Excel", "Power BI"]
    jd_data = {"role": "Data Analyst", "min_experience_years": 2, "preferred_skills": []}

    parsed, _, _ = analyze_resume_for_job(text, jd_text, jd_skills, jd_data)

    assert parsed["email"] == "neha.singh@example.com"
    assert parsed["phone"] == "9876501234"
    assert parsed.get("raw_parsed_json")
    assert parsed.get("safe_parsed_json")
    assert parsed.get("field_confidence_json")
    assert parsed.get("field_sources_json")
    assert parsed.get("text_extraction_quality")
