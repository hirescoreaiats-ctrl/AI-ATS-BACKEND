from backend.experience_engine import process_experience
from backend.jd_engine import normalize_jd_skills
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


QA_JD = """
QA Automation Engineer. Experience Required: 1-3 Years.
Required Skills: Selenium, Cypress, Playwright, TestNG, JUnit, Java, Python,
JavaScript, Automation Testing, Manual Testing, API Testing, Postman,
REST Assured, SQL, Jira, Git, Jenkins, CI/CD, Test Cases, Test Plan,
Test Scenarios, Bug Reporting, STLC, SDLC, Regression Testing, Smoke Testing,
Sanity Testing, Functional Testing, Integration Testing, End-to-End Testing.
"""


def qa_profile():
    skills = normalize_jd_skills([], QA_JD)
    return build_jd_profile(
        QA_JD,
        {"role": "QA Automation Engineer", "experience_required": "1-3 Years"},
        skills,
    )


def score_qa(parsed, resume_text):
    profile = qa_profile()
    return score_candidate(
        parsed,
        QA_JD,
        profile["must_have_skills"],
        {"role": "QA Automation Engineer", "min_experience_years": 1, "max_experience_years": 3},
        resume_text,
        jd_profile=profile,
    )


def test_direct_qa_candidate_ranks_above_full_stack_tool_match():
    full_stack = {
        "full_name": "Teja Reddy Palle",
        "designation": "Java Full Stack Developer",
        "key_skills": [
            "Java", "Python", "JavaScript", "JUnit", "Postman", "API Testing",
            "Git", "Jenkins", "CI/CD", "SQL", "Automation Testing",
        ],
        "total_experience_years": 4.85,
        "relevant_experience_years": 4.85,
        "direct_relevant_experience_years": 1.4,
        "role_relevance_score": 86,
        "semantic_score": 0.82,
        "resume_quality_score": 88,
        "experience_relevance_label": "partial_match",
        "experience": [
            {
                "company_name": "DoorDash, USA | Java Full Stack Developer",
                "role": "Java Full Stack Developer",
                "start_date": "Jan 2024",
                "end_date": "Present",
                "description": "Built Spring Boot REST APIs, React features, SQL queries, Git, Jenkins and CI/CD pipelines.",
            },
            {
                "company_name": "Capgemini",
                "role": "Senior Software Engineer QA Automation",
                "start_date": "Aug 2022",
                "end_date": "Dec 2023",
                "description": "Used Postman for API Testing, Jira and JUnit on QA automation tasks.",
            },
        ],
        "experience_evidence": [{"role": "Senior Software Engineer QA Automation", "label": "direct", "credited_years": 1.4}],
    }
    direct_qa = {
        "full_name": "Jay V Kate",
        "designation": "QA Automation Engineer",
        "key_skills": [
            "Manual Testing", "Automation Testing", "Selenium", "Playwright",
            "API Testing", "Postman", "SQL", "Jira", "Git", "Java",
            "Test Cases", "Test Plan", "Bug Reporting", "Regression Testing",
            "Functional Testing", "End-to-End Testing",
        ],
        "total_experience_years": 3.1,
        "relevant_experience_years": 3.1,
        "direct_relevant_experience_years": 3.1,
        "role_relevance_score": 90,
        "semantic_score": 0.86,
        "resume_quality_score": 88,
        "experience_relevance_label": "direct_match",
        "experience": [{
            "company_name": "Hiring Tech",
            "role": "QA Automation Engineer",
            "start_date": "Jan 2023",
            "end_date": "Present",
            "description": (
                "Designed Selenium and Playwright automation tests, manual testing, API Testing with Postman, "
                "SQL database validation, Jira bug reporting, test cases, test plans, regression, functional and end-to-end testing."
            ),
        }],
        "experience_evidence": [{"role": "QA Automation Engineer", "label": "direct", "credited_years": 3.1}],
    }

    full_stack_result = score_qa(full_stack, " ".join(job["description"] for job in full_stack["experience"]))
    direct_result = score_qa(direct_qa, direct_qa["experience"][0]["description"])

    assert full_stack_result["final_score"] <= 58
    assert full_stack_result["role_alignment"] == "adjacent"
    assert "primary_role_mismatch" in full_stack_result["recruiter_flags"]
    assert direct_result["role_alignment"] == "direct"
    assert direct_result["final_score"] > full_stack_result["final_score"]
    assert direct_result["rank_score"] > full_stack_result["rank_score"]


def test_direct_qa_slightly_above_range_is_review_not_rejected():
    parsed = {
        "full_name": "Sivavithushan",
        "designation": "Engineer- Digital Quality Assurance",
        "key_skills": [
            "Manual Testing", "Automation Testing", "API Testing", "Java", "Python",
            "Playwright", "Selenium", "MySQL", "Postman", "SQL", "Jira",
            "Test Cases", "Bug Reporting", "Regression Testing",
        ],
        "total_experience_years": 4.27,
        "relevant_experience_years": 4.27,
        "direct_relevant_experience_years": 4.27,
        "role_relevance_score": 88,
        "semantic_score": 0.82,
        "resume_quality_score": 84,
        "experience_relevance_label": "direct_match",
        "experience": [{
            "company_name": "Virtusa Pvt Ltd",
            "role": "Engineer- Digital Quality Assurance",
            "start_date": "Jan 2022",
            "end_date": "Oct 2025",
            "description": "Manual testing, automation testing, Selenium, Playwright, API Testing, Postman, SQL validation, Jira bug reporting and regression testing.",
        }],
    }

    result = score_qa(parsed, parsed["experience"][0]["description"])

    assert result["role_alignment"] == "direct"
    assert result["final_score"] >= 62
    assert result["recommendation"] in {"in_review", "shortlisted"}
    assert result["label"] != "Rejected - missing core skills"


def test_senior_qa_profile_is_capped_for_junior_role():
    parsed = {
        "full_name": "Anthony Montalto",
        "designation": "Senior Software Testing Engineer",
        "key_skills": ["Selenium", "Postman", "API Testing", "SQL", "Jira", "Manual Testing", "Regression Testing", "Test Cases", "Bug Reporting"],
        "total_experience_years": 26.02,
        "relevant_experience_years": 22.02,
        "direct_relevant_experience_years": 22.02,
        "role_relevance_score": 92,
        "semantic_score": 0.8,
        "resume_quality_score": 86,
        "experience": [{
            "company_name": "SiriusXM",
            "role": "Senior Software Testing Engineer",
            "start_date": "Jan 2000",
            "end_date": "Present",
            "description": "Led manual testing, Selenium regression testing, API Testing with Postman, SQL checks, Jira defect tracking and bug reporting.",
        }],
    }

    result = score_qa(parsed, parsed["experience"][0]["description"])

    assert result["final_score"] <= 60
    assert result["recommendation"] == "in_review"
    assert "strongly_overqualified" in result["recruiter_flags"]


def test_keyword_only_qa_tools_do_not_score_like_professional_qa():
    parsed = {
        "designation": "Software Developer",
        "key_skills": [
            "Selenium", "Cypress", "Playwright", "Postman", "REST Assured",
            "SQL", "Jira", "Git", "Jenkins", "Java", "Python", "JavaScript",
        ],
        "total_experience_years": 2.5,
        "relevant_experience_years": 1.0,
        "direct_relevant_experience_years": 0,
        "role_relevance_score": 55,
        "semantic_score": 0.6,
        "resume_quality_score": 80,
        "experience": [{
            "company_name": "Acme Technologies",
            "role": "Software Developer",
            "start_date": "Jan 2024",
            "end_date": "Present",
            "description": "Developed web APIs and frontend components using JavaScript and Python.",
        }],
    }
    resume_text = "Skills: Selenium Cypress Playwright Postman REST Assured SQL Jira Git Jenkins Java Python JavaScript."

    result = score_qa(parsed, resume_text)

    assert result["final_score"] <= 58
    assert result["role_alignment"] in {"transferable", "adjacent"}
    assert "qa_professional_evidence_gap" in result["recruiter_flags"]


def test_location_and_role_strings_are_not_last_company_names():
    result = process_experience([
        {
            "company_name": "REMOTE QA",
            "role": "QA Engineer",
            "start_date": "Jan 2020",
            "end_date": "Dec 2020",
        },
        {
            "company_name": "Karachi, Pakistan Senior SQA",
            "role": "Senior SQA Engineer",
            "start_date": "Jan 2021",
            "end_date": "Dec 2021",
        },
        {
            "company_name": "DoorDash, USA | Java Full Stack Developer",
            "role": "Java Full Stack Developer",
            "start_date": "Jan 2022",
            "end_date": "Present",
        },
    ])

    assert result["last_company_name"] == "DoorDash"
    invalid = {
        item["company_name"]: item["company_valid"]
        for item in result["extracted_date_ranges_raw"]
    }
    assert invalid["REMOTE QA"] is False
    assert invalid["Karachi, Pakistan Senior SQA"] is False
