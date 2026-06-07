from backend.experience_engine import process_experience
from backend.jd_engine import normalize_jd_skills
from backend.services.canonical_parser import parse_resume_document
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


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
