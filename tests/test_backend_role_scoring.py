from backend.experience_engine import process_experience
from backend.jd_engine import normalize_jd_skills
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


BACKEND_JD = """
Backend Developer. Experience: 1-3 Years.
Required Skills:
Strong hands-on experience with at least one backend technology: Node.js with Express.js,
Python with Django/FastAPI, Java with Spring Boot, or PHP with Laravel.
REST API development, database design, authentication and authorization, error handling,
logging, validation, Git, GitHub, Postman, Swagger, Linux/server basics and deployment.
Frontend developers will collaborate with this role, but frontend development is not required.
Preferred: Docker, Redis, queues, CI/CD, AWS, DigitalOcean, Nginx and security best practices.
"""


def backend_profile():
    skills = normalize_jd_skills([], BACKEND_JD)
    return build_jd_profile(BACKEND_JD, {"role": "Backend Developer"}, skills)


def score_backend(parsed, resume_text):
    profile = backend_profile()
    return profile, score_candidate(parsed, BACKEND_JD, profile["must_have_skills"], {"role": "Backend Developer"}, resume_text, jd_profile=profile)


def test_backend_jd_does_not_create_frontend_mandatory_gap():
    profile = backend_profile()
    parsed = {
        "full_name": "Manoj Gajare",
        "designation": "Java Backend Developer",
        "key_skills": ["Java", "Spring Boot", "Hibernate", "REST API", "PostgreSQL", "MySQL", "RabbitMQ", "Redis", "JWT", "Git", "Postman"],
        "total_experience_years": 3,
        "relevant_experience_years": 3,
        "role_relevance_score": 88,
        "experience": [{
            "role": "Java Backend Developer",
            "company_name": "Fintech Systems Pvt Ltd",
            "description": "Developed Spring Boot microservices, REST APIs, JWT authentication, PostgreSQL queries, Redis caching, RabbitMQ queues, logging and error handling.",
        }],
        "projects": [],
        "resume_quality_score": 86,
    }

    resume_text = "Java Backend Developer. Developed Spring Boot microservices, REST APIs, JWT authentication, PostgreSQL queries, Redis caching, RabbitMQ queues, logging and error handling. Git Postman."
    profile, result = score_backend(parsed, resume_text)

    assert profile["role_family"] == "software_backend"
    assert "frontend" not in profile["core_skill_groups"]
    assert "Frontend" not in result["missing_skills"]
    assert "Frontend" not in " ".join(result["ranking_reason"].split())
    assert result["recommendation"] in {"shortlisted", "in_review"}
    assert result["final_score"] >= 78


def test_backend_jd_accepts_single_backend_path_and_auth_synonyms():
    profile = backend_profile()
    parsed = {
        "full_name": "Ayush Ahuja",
        "designation": "Software Developer",
        "key_skills": ["Java", "Spring Boot", "REST API", "SQL", "Linux", "Docker", "Git", "Swagger", "Spring Security"],
        "total_experience_years": 2,
        "relevant_experience_years": 2,
        "role_relevance_score": 84,
        "experience": [{
            "role": "Software Developer",
            "company_name": "Oracle Financial Services",
            "description": "Built Java Spring Boot REST APIs with Spring Security, token authentication, SQL schemas, Swagger docs, Linux deployment, Docker and production logging.",
        }],
        "projects": [],
        "resume_quality_score": 84,
    }

    resume_text = "Software Developer. Built Java Spring Boot REST APIs with Spring Security, token authentication, SQL schemas, Swagger docs, Linux deployment, Docker and production logging."
    _, result = score_backend(parsed, resume_text)

    assert "Backend Path" not in result["missing_skills"]
    assert "Api Auth" not in result["missing_skills"]
    assert "Database" not in result["missing_skills"]
    assert result["final_score"] >= 78


def test_backend_project_only_candidate_stays_junior_review_not_auto_shortlisted():
    profile = backend_profile()
    parsed = {
        "full_name": "Sohel Kureshi",
        "designation": "Full Stack Development Intern",
        "key_skills": ["Node.js", "Express", "MongoDB", "JWT", "Firebase Auth", "Git", "Render", "JavaScript"],
        "total_experience_years": 0,
        "relevant_experience_years": 0,
        "professional_role_experience_years": 0,
        "project_only_exposure": 1,
        "role_relevance_score": 55,
        "experience": [],
        "projects": [{
            "name": "EstateEase",
            "description": "Built MERN backend with Node.js Express, 15+ REST APIs, JWT authentication, Firebase OAuth, MongoDB queries, protected routes and Render deployment.",
            "technologies": ["Node.js", "Express", "MongoDB", "JWT", "Firebase Auth", "Render"],
        }],
        "resume_quality_score": 82,
    }

    resume_text = "EstateEase MERN backend with Node.js Express, 15+ REST APIs, JWT authentication, Firebase OAuth, MongoDB queries, protected routes and Render deployment."
    _, result = score_backend(parsed, resume_text)

    assert result["recommendation"] == "in_review"
    assert result["final_score"] <= 74
    assert "junior_project_review" in result["recruiter_flags"]
    assert result["project_strength_score"] >= 55


def test_backend_senior_candidate_is_overqualified_review_not_fake_frontend_gap():
    profile = backend_profile()
    parsed = {
        "full_name": "Abhinav Gangwar",
        "designation": "Senior Backend Engineer",
        "key_skills": ["Node.js", "Express", "GraphQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "RabbitMQ", "AWS", "Docker", "Kubernetes", "Git"],
        "total_experience_years": 9,
        "relevant_experience_years": 9,
        "role_relevance_score": 92,
        "experience": [{
            "role": "Senior Backend Engineer",
            "company_name": "OLX India Pvt. Ltd.",
            "description": "Designed Node.js Express backend services, GraphQL APIs, PostgreSQL data models, Redis caching, RabbitMQ queues, Docker Kubernetes deployments and observability.",
        }],
        "projects": [],
        "resume_quality_score": 86,
    }

    resume_text = "Senior Backend Engineer. Designed Node.js Express backend services, GraphQL APIs, PostgreSQL data models, Redis caching, RabbitMQ queues, Docker Kubernetes deployments and observability."
    _, result = score_backend(parsed, resume_text)

    assert result["recommendation"] == "in_review"
    assert "overqualified" in result["recruiter_flags"]
    assert "Frontend" not in result["missing_skills"]
    assert result["final_score"] <= 78


def test_backend_company_parser_rejects_role_and_skill_fragments():
    result = process_experience([
        {"company_name": "Senior Backend", "role": "Lead Backend Engineer", "start_date": "2024", "end_date": "Present"},
        {"company_name": "ElasticSeach", "role": "Backend Engineer", "start_date": "2023", "end_date": "2024"},
        {"company_name": "OLX India Pvt. Ltd.", "role": "Senior Backend Engineer", "start_date": "2020", "end_date": "2023"},
    ])

    assert result["last_company_name"] == "OLX India Pvt. Ltd."


def test_experience_parser_skips_impossible_old_ranges():
    result = process_experience([
        {"company_name": "Impossible Corp", "role": "Backend Developer", "start_date": "1968", "end_date": "Present"},
        {"company_name": "Modern APIs Ltd", "role": "Backend Developer", "start_date": "2021", "end_date": "2024"},
    ])

    assert result["total_experience_years"] < 10
    assert result["last_company_name"] == "Modern APIs Ltd"


def test_anthony_style_qa_year_only_roles_merge_without_inflating_total_experience():
    result = process_experience([
        {
            "company_name": "SiriusXM",
            "role": "Senior Quality Engineer",
            "start_date": "2008",
            "end_date": "2025",
            "description": "Designed Selenium automation and CI/CD tests.",
        },
        {
            "company_name": "WebMD",
            "role": "QA/Automation",
            "start_date": "2003",
            "end_date": "2008",
            "description": "Managed automation and API test reporting.",
        },
        {
            "company_name": "Dynax Solutions",
            "role": "Programmer/QA/IT/Tech Support",
            "start_date": "2000",
            "end_date": "2003",
            "description": "QA and support.",
        },
        {
            "company_name": "Columbia Bootcamp",
            "role": "Bootcamp",
            "start_date": "2018",
            "end_date": "2019",
            "section": "education",
        },
    ])

    assert 25 <= result["total_experience_years"] <= 27
    assert result["total_experience_years"] < 33
    assert result["last_company_name"] == "SiriusXM"
    assert any(item["reason"] == "non_work_experience_section" for item in result["excluded_ranges_with_reason"])


def test_qa_relevant_experience_uses_canonical_total_not_duplicate_parser_rows():
    jd_text = (
        "QA Automation Engineer, 1-3 Years. Selenium, Playwright, API Testing, Postman, "
        "SQL, Manual Testing, Automation Testing, Test Cases, Bug Reporting."
    )
    jd_profile = build_jd_profile(jd_text, {"role": "QA Automation Engineer", "experience_required": "1-3 Years"}, [])
    parsed = {
        "designation": "Engineer- Digital Quality Assurance",
        "key_skills": ["Manual Testing", "Automation Testing", "API Testing", "Java", "Python", "Playwright", "Selenium", "MySQL", "Postman"],
        "total_experience_years": 4.28,
        "experience": [
            {
                "company_name": "Virtusa Pvt Ltd",
                "role": "Engineer- Digital Quality Assurance",
                "start_date": "Jan 2022",
                "end_date": "Oct 2025",
                "description": "Manual testing, automation testing, API testing, Selenium, Playwright, MySQL, Postman.",
            },
            {
                "company_name": "Virtusa Pvt Ltd., Colombo, Sri Lanka",
                "role": "Engineer- Digital Quality Assurance",
                "start_date": "Jan 2022",
                "end_date": "Oct 2025",
                "description": "Duplicate parser block with automation testing evidence.",
            },
            {
                "company_name": "Internship",
                "role": "Software Engineer Intern",
                "start_date": "Aug 2020",
                "end_date": "Jan 2021",
                "description": "Automation testing internship.",
            },
        ],
    }

    relevance = estimate_relevant_experience_v2(parsed, jd_text, jd_profile)

    assert relevance["total_experience_years"] == 4.28
    assert 3.5 <= relevance["relevant_experience_years"] <= 4.28
    assert relevance["role_relevance_score"] >= 75


def test_qa_jd_does_not_emit_generic_reliability_security_gap():
    jd_text = (
        "QA Automation Engineer. Required: Selenium, Cypress, Playwright, TestNG, JUnit, "
        "Java, Python, JavaScript, Automation Testing, Manual Testing, API Testing, Postman, "
        "REST Assured, SQL, Jira, Git, Jenkins, CI/CD."
    )

    skills = normalize_jd_skills([], jd_text)

    assert "Reliability Security" not in skills
    assert "Selenium" in skills
    assert "API Testing" in skills
    assert "REST Assured" in skills


def test_role_prefixed_qa_company_names_are_corrected():
    result = process_experience([
        {
            "company_name": "Technical Test Lead",
            "role": "Technical Test Lead",
            "start_date": "Jan 2021",
            "end_date": "Dec 2022",
        },
        {
            "company_name": "SDET 3 & SDET 2 , Junglee Games Pvt Ltd",
            "role": "SDET 3 & SDET 2",
            "start_date": "Jan 2023",
            "end_date": "Present",
        },
    ])

    assert result["last_company_name"] == "Junglee Games Pvt Ltd"
    assert any(not item["company_valid"] for item in result["extracted_date_ranges_raw"] if item["company_name"] == "Technical Test Lead")
