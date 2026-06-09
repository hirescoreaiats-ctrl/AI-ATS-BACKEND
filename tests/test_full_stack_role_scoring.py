from backend.experience_engine import process_experience
from backend.jd_engine import normalize_jd_skills
from backend.services.canonical_parser import parse_resume_document
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate
from backend.validation_scoring import validate_email


FULL_STACK_JD = """
Full Stack Web Developer. Experience: 1-3 Years.
Required Skills:
Frontend: HTML5, CSS3, JavaScript, React.js / Next.js / Vue.js, Tailwind CSS / Bootstrap.
Backend: Node.js / Express.js or Python / Django / FastAPI or PHP / Laravel.
REST API development, authentication and authorization, file upload handling, error handling.
Database: MySQL / PostgreSQL / MongoDB.
Tools: Git and GitHub, Postman, deployment on Vercel, Netlify, DigitalOcean, AWS.
Preferred: TypeScript, Next.js, Docker, CI/CD, payment gateway integration, admin dashboard.
"""


def full_stack_profile():
    skills = normalize_jd_skills([], FULL_STACK_JD)
    return build_jd_profile(FULL_STACK_JD, {"role": "Full Stack Web Developer"}, skills)


def test_full_stack_jd_extracts_role_specific_skill_groups_not_data_visualization():
    profile = full_stack_profile()

    assert profile["role_family"] == "full_stack"
    assert "frontend" in profile["core_skill_groups"]
    assert "backend" in profile["core_skill_groups"]
    assert "database" in profile["core_skill_groups"]
    assert "api_auth" in profile["core_skill_groups"]
    assert "React" in profile["must_have_skills"]
    assert "Node.js" in profile["must_have_skills"]
    assert "REST API" in profile["must_have_skills"]
    assert "Data Visualization" not in profile["must_have_skills"]


def test_strong_full_stack_candidate_is_not_rejected():
    profile = full_stack_profile()
    parsed = {
        "full_name": "Kartik Tomar",
        "designation": "Full Stack Developer",
        "key_skills": ["React", "Node.js", "Express", "MongoDB", "REST API", "Git", "AWS", "JavaScript", "HTML", "CSS"],
        "total_experience_years": 2,
        "relevant_experience_years": 2,
        "role_relevance_score": 90,
        "experience": [{
            "role": "Full Stack Developer",
            "company_name": "Phable Care",
            "description": "Developed production React and Node.js applications, REST APIs, MongoDB data models, authentication and performance improvements for 1M users.",
            "start_date": "2024",
            "end_date": "Present",
        }],
        "projects": [],
        "resume_quality_score": 88,
        "semantic_score": 0.8,
    }
    result = score_candidate(parsed, FULL_STACK_JD, profile["must_have_skills"], {"role": "Full Stack Web Developer"}, FULL_STACK_JD, jd_profile=profile)

    assert result["recommendation"] in {"shortlisted", "in_review"}
    assert result["final_score"] >= 75
    assert "Data Visualization" not in result["missing_skills"]
    assert result["jd_role_family"] == "full_stack"
    assert "Backend" not in result["missing_skills"]
    assert "Database" not in result["missing_skills"]
    assert "Api Auth" not in result["missing_skills"]


def test_senior_full_stack_candidate_is_review_overqualified_not_fake_low_relevance():
    profile = full_stack_profile()
    parsed = {
        "full_name": "Mykola Diachok",
        "designation": "Senior Full Stack Developer",
        "key_skills": ["TypeScript", "React", "Angular", "Node.js", "SQL", "MongoDB", "Azure", "Docker", "CI/CD", "REST API"],
        "total_experience_years": 20,
        "relevant_experience_years": 20,
        "role_relevance_score": 92,
        "experience": [{
            "role": "Senior Full Stack Developer",
            "company_name": "Enterprise Software",
            "description": "Built enterprise full-stack products with React, Angular, Node.js, REST APIs, SQL, MongoDB, Azure DevOps and Docker.",
            "start_date": "2015",
            "end_date": "Present",
        }],
        "projects": [],
        "resume_quality_score": 86,
        "semantic_score": 0.78,
    }
    result = score_candidate(parsed, FULL_STACK_JD, profile["must_have_skills"], {"role": "Full Stack Web Developer"}, FULL_STACK_JD, jd_profile=profile)

    assert result["final_score"] >= 60
    assert result["recommendation"] == "in_review"
    assert "overqualified" in result["recruiter_flags"]
    assert result["experience_fit"] == "senior_overqualified"


def test_full_stack_relevance_counts_software_engineer_with_web_stack():
    profile = full_stack_profile()
    parsed = {
        "designation": "Software Engineer",
        "total_experience_years": 4,
        "experience": [{
            "role": "Software Engineer",
            "company_name": "Microsoft",
            "description": "Developed React Native frontend features, Java backend APIs, Azure deployments, authentication and database integrations.",
            "start_date": "2024",
            "end_date": "Present",
        }],
    }

    relevance = estimate_relevant_experience_v2(parsed, FULL_STACK_JD, profile)

    assert relevance["relevant_experience_years"] > 0
    assert relevance["role_relevance_score"] >= 55


def test_full_stack_or_group_does_not_hallucinate_all_frontend_frameworks():
    profile = full_stack_profile()
    parsed = {
        "full_name": "Ajay Kumar",
        "designation": "Software Developer",
        "key_skills": ["React", "Vue", "Node.js", "Express", "MongoDB", "MySQL", "JWT", "Nginx", "Linux", "GitHub"],
        "total_experience_years": 1.5,
        "relevant_experience_years": 1.5,
        "role_relevance_score": 82,
        "experience": [{
            "role": "Software Developer",
            "company_name": "Tech Services Pvt Ltd",
            "description": "Built React and Vue interfaces, Node.js Express APIs, JWT authentication, MongoDB and MySQL integrations, and deployed apps on Nginx Linux servers.",
            "start_date": "2024",
            "end_date": "Present",
        }],
        "resume_quality_score": 82,
    }

    result = score_candidate(parsed, FULL_STACK_JD, profile["must_have_skills"], {"role": "Full Stack Web Developer"}, FULL_STACK_JD, jd_profile=profile)

    assert result["recommendation"] in {"shortlisted", "in_review"}
    assert "React" in result["matched_skills"]
    assert "Vue" in result["matched_skills"]
    assert "Next.js" not in result["matched_skills"]
    assert "Angular" not in result["matched_skills"]
    assert "Api Auth" not in result["missing_skills"]
    assert "Deployment Tools" not in result["missing_skills"]


def test_full_stack_keyword_only_groups_are_review_not_rejected():
    profile = full_stack_profile()
    parsed = {
        "full_name": "Kartik Tomar",
        "designation": "Full Stack Developer",
        "key_skills": ["JavaScript", "React", "Node.js", "Express", "MongoDB", "HTML", "CSS", "GitHub"],
        "total_experience_years": 1.9,
        "relevant_experience_years": 1.9,
        "role_relevance_score": 80,
        "experience": [{
            "role": "Software Engineer",
            "company_name": "Double Slit Media Tech",
            "description": "Developed full-stack product features and maintained APIs for production users.",
            "start_date": "2024",
            "end_date": "Present",
        }],
        "resume_quality_score": 80,
    }

    result = score_candidate(parsed, FULL_STACK_JD, profile["must_have_skills"], {"role": "Full Stack Web Developer"}, FULL_STACK_JD, jd_profile=profile)

    assert result["recommendation"] != "rejected"
    assert result["final_score"] >= 60
    assert "Backend" not in result["missing_skills"]
    assert "Database" not in result["missing_skills"]


def test_full_stack_parser_rejects_email_or_role_fragments_as_candidate_name():
    parsed = parse_resume_document(
        "Full Stack Developer\nEmail: webdevdesign@sundeepcharan.com\nReact Node.js Express MongoDB",
        mode="test",
        ai_parse_override={
            "full_name": "Email: webdevdesign@sundeepcharan.com",
            "email": "webdevdesign@sundeepcharan.com",
            "key_skills": ["React", "Node.js", "Express", "MongoDB"],
        },
    )

    assert parsed["full_name"] == ""
    assert "name_needs_review" in set(parsed.get("parser_flags") or [])


def test_full_stack_parser_rejects_address_or_project_fragments_as_candidate_name():
    for bad_name in [
        "About Gies.",
        "Shri Mylara Lingeshwara Nilaya",
        "- Main Developer Alius.Ai",
        "Github.com mattchiaravalloti Select coursework",
        "De V Prakash Si Ngh",
    ]:
        parsed = parse_resume_document(
            f"{bad_name}\nFull Stack Developer\ncandidate@example.com\nReact Node.js MongoDB",
            mode="test",
            ai_parse_override={"full_name": bad_name, "email": "candidate@example.com"},
        )

        assert parsed["full_name"] == ""


def test_full_stack_company_parser_does_not_use_tech_stack_fragments_as_last_company():
    result = process_experience([
        {
            "company_name": "both Node and browser environments",
            "role": "Full Stack Developer",
            "start_date": "2024",
            "end_date": "Present",
        },
        {
            "company_name": "Capgemini",
            "role": "Software Engineer",
            "start_date": "2021",
            "end_date": "2023",
        },
        {
            "company_name": "React. Node.js, Express.js",
            "role": "Developer",
            "start_date": "2020",
            "end_date": "2021",
        },
    ])

    assert result["last_company_name"] == "Capgemini"


def test_full_stack_company_parser_rejects_locations_and_skill_headings():
    result = process_experience([
        {"company_name": "US", "role": "Full Stack Developer", "start_date": "2024", "end_date": "Present"},
        {"company_name": "Uttar Pradesh", "role": "Software Developer", "start_date": "2023", "end_date": "2024"},
        {"company_name": "Machine Learning", "role": "Intern", "start_date": "2022", "end_date": "2023"},
        {"company_name": "U2USystems, Singapore", "role": "Associate", "start_date": "2021", "end_date": "2022"},
    ])

    assert result["last_company_name"] == "U2USystems, Singapore"


def test_resume_email_validation_extracts_clean_email_from_concatenated_text():
    assert validate_email("7014167848himanshumeena2572006@gmail.comJaipur") == "7014167848himanshumeena2572006@gmail.com"


def strict_full_stack_profile():
    jd_text = """
    Full Stack Developer. Experience: 2-4 Years.
    Required: React, Next.js, HTML, CSS, JavaScript, Node.js, Express, Python, FastAPI,
    Django, MongoDB, MySQL, PostgreSQL, REST API, JWT, OAuth, RBAC, Git, Postman,
    Docker, AWS.
    """
    skills = normalize_jd_skills([], jd_text)
    return jd_text, build_jd_profile(
        jd_text,
        {"role": "Full Stack Developer", "experience_required": "2-4 Years"},
        skills,
    )


def test_strict_two_to_four_full_stack_zero_year_skill_match_is_not_shortlisted():
    jd_text, profile = strict_full_stack_profile()
    parsed = {
        "full_name": "Junior Builder",
        "designation": "Full Stack Intern",
        "key_skills": ["React", "Node.js", "Express", "MongoDB", "REST API", "JWT", "Git", "Postman"],
        "total_experience_years": 0.16,
        "relevant_experience_years": 0.16,
        "role_relevance_score": 85,
        "experience": [{
            "company_name": "Startup Lab",
            "role": "Full Stack Intern",
            "start_date": "Feb 2026",
            "end_date": "Apr 2026",
            "description": "Built React UI, Node.js Express APIs, MongoDB models, REST API endpoints, JWT auth, Postman tests, and Git workflows.",
        }],
        "resume_quality_score": 88,
    }

    result = score_candidate(parsed, jd_text, profile["must_have_skills"], {"role": "Full Stack Developer"}, jd_text, jd_profile=profile)

    assert result["recommendation"] != "shortlisted"
    assert result["final_score"] <= 60
    assert "below_jd_experience_range" in result["risk_flags"]
    assert result["label"] == "Below experience range"


def test_strict_two_to_four_full_stack_one_point_five_years_is_capped():
    jd_text, profile = strict_full_stack_profile()
    parsed = {
        "full_name": "Ajay Kumar",
        "designation": "Software Developer",
        "key_skills": ["React", "Vue", "Node.js", "Express", "MongoDB", "MySQL", "JWT", "GitHub", "Postman"],
        "total_experience_years": 1.5,
        "relevant_experience_years": 1.5,
        "role_relevance_score": 84,
        "experience": [{
            "company_name": "Credin",
            "role": "Software Developer",
            "start_date": "Jan 2025",
            "end_date": "Jun 2026",
            "description": "Built React and Vue interfaces, Node.js Express APIs, JWT authentication, MongoDB and MySQL integrations, Postman testing, and deployment workflows.",
        }],
        "resume_quality_score": 86,
    }

    result = score_candidate(parsed, jd_text, profile["must_have_skills"], {"role": "Full Stack Developer"}, jd_text, jd_profile=profile)

    assert result["recommendation"] != "shortlisted"
    assert result["final_score"] <= 72
    assert "below_jd_experience_range" in result["risk_flags"]


def test_strict_two_to_four_full_stack_over_range_is_review_not_shortlisted():
    jd_text, profile = strict_full_stack_profile()
    parsed = {
        "full_name": "Senior Candidate",
        "designation": "Senior Full Stack Developer",
        "key_skills": ["React", "Node.js", "Express", "MongoDB", "REST API", "JWT", "Git", "AWS"],
        "total_experience_years": 6.2,
        "relevant_experience_years": 6.2,
        "role_relevance_score": 92,
        "experience": [{
            "company_name": "Enterprise Software",
            "role": "Senior Full Stack Developer",
            "start_date": "Jan 2020",
            "end_date": "Mar 2026",
            "description": "Led React, Node.js, Express, MongoDB, REST API, JWT authentication, AWS deployment, and Git workflows for production systems.",
        }],
        "resume_quality_score": 90,
    }

    result = score_candidate(parsed, jd_text, profile["must_have_skills"], {"role": "Full Stack Developer"}, jd_text, jd_profile=profile)

    assert result["recommendation"] != "shortlisted"
    assert "over_jd_experience_range" in result["risk_flags"]
    assert result["label"] == "Overqualified review"
