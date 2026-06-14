from backend.experience_engine import process_experience
from backend.jd_engine import normalize_jd_skills
from backend.models import Job, Resume
from backend.routers.job import _candidate_recruiter_trust
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.scoring_service import score_candidate


FRONTEND_JD = """
Frontend Developer. Experience Required: 1-3 Years. Location: Noida / Remote / Hybrid.
Salary: 4-5 LPA.
Required Skills: HTML5, CSS3, JavaScript, React.js, responsive web design, mobile-first
development, REST API integration, Redux, Context API, Git, GitHub, Vite, Webpack,
npm, browser compatibility, debugging, and performance optimization.
Good to Have: TypeScript, Next.js, Tailwind CSS, Bootstrap, Material UI, Node.js,
Express.js, Jest, React Testing Library, Cypress, SEO, accessibility, Vercel,
Netlify, and AWS.
"""


def frontend_profile():
    skills = normalize_jd_skills([], FRONTEND_JD)
    return build_jd_profile(
        FRONTEND_JD,
        {
            "role": "Frontend Developer",
            "location": "Noida / Remote / Hybrid",
            "salary_range": "4-5 LPA",
            "experience_required": "1-3 Years",
        },
        skills,
    )


def score_frontend(parsed):
    profile = frontend_profile()
    resume_text = " ".join(
        [
            str(parsed.get("designation") or ""),
            str(parsed.get("location") or ""),
            " ".join(str(skill) for skill in parsed.get("key_skills") or []),
            " ".join(str(exp.get("description") or "") for exp in parsed.get("experience") or []),
        ]
    )
    return profile, score_candidate(
        parsed,
        FRONTEND_JD,
        profile["must_have_skills"],
        {
            "role": "Frontend Developer",
            "location": "Noida / Remote / Hybrid",
            "salary_range": "4-5 LPA",
            "experience_required": "1-3 Years",
        },
        resume_text,
        jd_profile=profile,
    )


def _frontend_work(company="Skyfunnel AI"):
    return {
        "company_name": company,
        "role": "Frontend Developer",
        "description": (
            "Developed responsive React and Next.js interfaces using HTML, CSS, "
            "JavaScript, Redux, Zustand, REST API integrations, Vite, Webpack, GitHub, "
            "Chrome DevTools, Web Vitals, browser debugging, and performance optimization."
        ),
    }


def test_frontend_role_family_uses_frontend_groups_without_api_auth_or_database():
    profile = frontend_profile()

    assert profile["role_family"] == "software_frontend"
    assert "frontend_core" in profile["core_skill_groups"]
    assert "react_core" in profile["core_skill_groups"]
    assert "api_integration" in profile["core_skill_groups"]
    assert "api_auth" not in profile["core_skill_groups"]
    assert "auth_security" not in profile["core_skill_groups"]
    assert "database" not in profile["core_skill_groups"]


def test_noida_two_year_react_candidate_beats_foreign_overqualified_profiles():
    diwanshu = {
        "full_name": "Diwanshu Midha",
        "designation": "Full Stack Developer",
        "location": "Noida",
        "key_skills": [
            "React", "Next.js", "HTML", "CSS", "JavaScript", "Vite", "Zustand",
            "Redux", "REST API", "GitHub", "Responsive Design", "Web Vitals",
            "Performance Optimization",
        ],
        "total_experience_years": 2,
        "relevant_experience_years": 1.92,
        "role_relevance_score": 82,
        "experience": [_frontend_work()],
        "resume_quality_score": 88,
    }
    andrew = {
        "full_name": "Andrew Vuong",
        "designation": "L5 Frontend Engineer",
        "location": "Los Angeles, California",
        "key_skills": [
            "React", "HTML", "CSS", "JavaScript", "TypeScript", "Redux",
            "REST API", "GitHub", "Webpack", "Jest", "Cypress", "Responsive Design",
            "Performance Optimization",
        ],
        "total_experience_years": 4.52,
        "relevant_experience_years": 4.52,
        "role_relevance_score": 92,
        "experience": [_frontend_work("AWS S3 on Edge")],
        "resume_quality_score": 90,
    }
    george = {
        "full_name": "George Raptis",
        "designation": "Frontend Architect",
        "location": "Larissa, Greece",
        "key_skills": [
            "React", "Next.js", "HTML", "CSS", "JavaScript", "TypeScript",
            "Redux", "REST API", "Webpack", "Jest", "Cypress", "Responsive Design",
            "Performance Optimization",
        ],
        "total_experience_years": 14.42,
        "relevant_experience_years": 14.42,
        "role_relevance_score": 96,
        "experience": [_frontend_work("Allwyn Lottery Solutions")],
        "resume_quality_score": 92,
    }

    _, diwanshu_score = score_frontend(diwanshu)
    _, andrew_score = score_frontend(andrew)
    _, george_score = score_frontend(george)

    assert diwanshu_score["label"] == "Strong fit"
    assert diwanshu_score["rank_score"] > andrew_score["rank_score"]
    assert diwanshu_score["rank_score"] > george_score["rank_score"]
    assert andrew_score["label"] == "Location/Budget Mismatch"
    assert george_score["label"] == "Location/Budget Mismatch"
    assert "location_budget_mismatch" in andrew_score["recruiter_flags"]
    assert "strongly_overqualified" in george_score["recruiter_flags"]


def test_gurugram_slightly_senior_frontend_candidate_is_good_fit_without_false_gaps():
    parsed = {
        "full_name": "Aakash Dinkar",
        "designation": "Frontend Engineer",
        "location": "Gurugram, India",
        "key_skills": [
            "React", "Next.js", "HTML", "CSS", "JavaScript", "TypeScript",
            "Redux", "REST API", "GitHub", "Webpack", "Responsive Design",
            "SEO", "Performance Optimization",
        ],
        "total_experience_years": 3.8,
        "relevant_experience_years": 3.44,
        "role_relevance_score": 90,
        "experience": [_frontend_work("Fashnear Technologies Private Limited / Meesho")],
        "resume_quality_score": 89,
    }

    _, result = score_frontend(parsed)

    assert result["final_score"] >= 78
    assert result["experience_fit"] == "slightly_over_range"
    assert result["location_fit"]["label"] == "location_strong_fit"
    assert "Api Auth" not in result["missing_skills"]
    assert "Database" not in result["missing_skills"]
    assert "React" in result["matched_skills"][:3]
    assert "Node.js" not in result["matched_skills"][:8]


def test_senior_india_frontend_profile_is_overqualified_review_not_fake_database_gap():
    parsed = {
        "full_name": "Divya Tiwari",
        "designation": "Senior Frontend Developer",
        "location": "India",
        "key_skills": [
            "React", "Next.js", "HTML", "CSS", "JavaScript", "TypeScript",
            "Redux", "REST API", "GitHub", "Vite", "Jest", "Cypress",
            "Responsive Design", "Performance Optimization",
        ],
        "total_experience_years": 8.2,
        "relevant_experience_years": 8.2,
        "role_relevance_score": 92,
        "experience": [_frontend_work("Enterprise Software")],
        "resume_quality_score": 90,
    }

    _, result = score_frontend(parsed)

    assert result["label"] == "Overqualified review"
    assert result["final_score"] <= 70
    assert "Api Auth" not in result["missing_skills"]
    assert "Database" not in result["missing_skills"]
    assert "overqualified_review" in result["recruiter_flags"]
    assert result["recommendation"] == "in_review"


def test_frontend_api_product_work_counts_without_literal_rest_api_keyword():
    parsed = {
        "full_name": "Frontend Product Engineer",
        "designation": "SDE-2",
        "location": "Gurugram, India",
        "key_skills": [
            "React", "Next.js", "HTML", "CSS", "JavaScript", "TypeScript",
            "GitHub", "Webpack", "Responsive Design", "SEO", "Performance Optimization",
        ],
        "total_experience_years": 3.8,
        "relevant_experience_years": 3.44,
        "role_relevance_score": 88,
        "experience": [{
            "company_name": "Fashnear Technologies Private Limited (Meesho)",
            "role": "SDE-2",
            "description": (
                "Built React and Next.js customer-facing listing pages, prepaid payment methods, "
                "UPI/card/net banking flows, native webviews, role-based dashboards, React Hook Form "
                "forms, and dynamic data-driven UI for production commerce workflows."
            ),
        }],
        "resume_quality_score": 89,
    }

    _, result = score_frontend(parsed)

    assert "Api Integration" not in result["missing_skills"]
    assert "api_integration" in result["matched_core_skill_groups"]
    assert "API Integration" in result["matched_skills"]
    assert result["evidence_group_scores"]["api_integration"]["best_source"] == "frontend_product_evidence"


def test_frontend_relevance_credits_sde_with_product_api_frontend_evidence():
    profile = frontend_profile()
    parsed = {
        "total_experience_years": 3.8,
        "experience": [{
            "company_name": "Fashnear Technologies Private Limited (Meesho)",
            "role": "SDE-2",
            "start_date": "Oct 2022",
            "end_date": "Jun 2026",
            "description": (
                "Developed React and Next.js frontend interfaces, payment method integration, "
                "webviews, role-based dashboards, listing pages, and dynamic data-driven UI."
            ),
        }],
    }

    relevance = estimate_relevant_experience_v2(parsed, FRONTEND_JD, profile)

    assert relevance["relevant_experience_years"] >= 3.0
    assert relevance["experience_relevance_label"] == "direct_match"
    assert relevance["experience_evidence"][0]["label"] == "direct"


def test_frontend_company_parser_rejects_headings_skills_and_unicode_noise():
    result = process_experience([
        {"company_name": "CMS", "role": "Engineer", "start_date": "Jan 2024", "end_date": "Present"},
        {"company_name": "SEO, Web Performance", "role": "Frontend Engineer", "start_date": "Jan 2023", "end_date": "Dec 2023"},
        {"company_name": "company and its associated businesses", "role": "Lead Frontend Engineer", "start_date": "Jan 2022", "end_date": "Dec 2022"},
        {"company_name": "\u202c", "role": "Software Engineer", "start_date": "Jan 2021", "end_date": "Dec 2021"},
        {"company_name": "Deloitte", "role": "Senior Consultant", "start_date": "Jan 2020", "end_date": "Dec 2020"},
    ])

    assert result["last_company_name"] == "Deloitte"
    invalid = {
        item["company_name"]: item["company_valid"]
        for item in result["extracted_date_ranges_raw"]
    }
    assert invalid["CMS"] is False
    assert invalid["SEO, Web Performance"] is False
    assert invalid["company and its associated businesses"] is False
    assert invalid["\u202c"] is False


def test_frontend_company_parser_prefers_latest_real_company_over_skill_headings():
    result = process_experience([
        {"company_name": "Web Performance", "role": "Frontend Engineer", "start_date": "Jan 2025", "end_date": "Present"},
        {"company_name": "Fashnear Technologies Private Limited (Meesho) - SDE-2", "role": "SDE-2", "start_date": "Oct 2023", "end_date": "Present"},
        {"company_name": "Cogoport Private Limited", "role": "Software Engineer", "start_date": "Jun 2021", "end_date": "Sep 2023"},
    ])

    assert result["last_company_name"] == "Fashnear Technologies Private Limited (Meesho)"
    invalid = {
        item["company_name"]: item["company_valid"]
        for item in result["extracted_date_ranges_raw"]
    }
    assert invalid["Web Performance"] is False
    assert invalid["Fashnear Technologies Private Limited (Meesho) - SDE-2"] is True


def test_company_parser_rejects_csv_api_route_and_graph_terms_as_companies():
    result = process_experience([
        {"company_name": "CSV", "role": "Frontend Engineer", "start_date": "Jan 2026", "end_date": "Present"},
        {"company_name": "API routes", "role": "Software Engineer", "start_date": "Jan 2025", "end_date": "Dec 2025"},
        {"company_name": "Google Share Drive", "role": "Developer", "start_date": "Jan 2024", "end_date": "Dec 2024"},
        {"company_name": "nodes and relationships", "role": "Developer", "start_date": "Jan 2023", "end_date": "Dec 2023"},
        {"company_name": "Outlier AI", "role": "Software Engineer", "start_date": "Jan 2022", "end_date": "Dec 2022"},
    ])

    assert result["last_company_name"] == "Outlier AI"
    invalid = {
        item["company_name"]: item["company_valid"]
        for item in result["extracted_date_ranges_raw"]
    }
    assert invalid["CSV"] is False
    assert invalid["API routes"] is False
    assert invalid["Google Share Drive"] is False
    assert invalid["nodes and relationships"] is False


def test_senior_react_profile_gets_soft_state_management_validation_not_hard_gap():
    parsed = {
        "full_name": "Senior React Consultant",
        "designation": "Senior Consultant",
        "location": "India",
        "key_skills": [
            "React", "Next.js", "HTML", "CSS", "JavaScript", "TypeScript",
            "REST API", "GitHub", "Webpack", "Responsive Design", "Performance Optimization",
        ],
        "total_experience_years": 7.2,
        "relevant_experience_years": 7.2,
        "role_relevance_score": 92,
        "experience": [{
            "company_name": "Deloitte",
            "role": "Senior Consultant",
            "description": (
                "Developed React and Next.js enterprise dashboards using HTML, CSS, JavaScript, "
                "TypeScript, REST API integrations, Webpack, GitHub, responsive layouts, browser "
                "debugging, and performance optimization."
            ),
        }],
        "resume_quality_score": 90,
    }

    _, result = score_frontend(parsed)

    assert "State Management" not in result["missing_skills"]
    assert "state_management" not in result["missing_core_skill_groups"]
    assert "state_management_validation" in result["recruiter_flags"]
    assert result["label"] == "Overqualified review"


def test_overqualified_recruiter_trust_never_sends_to_client_even_above_75():
    candidate = Resume(
        full_name="Senior Frontend Candidate",
        email="candidate@example.com",
        designation="Senior Frontend Developer",
        final_score=78,
        rank_score=78,
        skill_match_percent=82,
        confidence_score=80,
        matched_skills="React,JavaScript,REST API",
        missing_skills="",
        recruiter_flags='["overqualified", "overqualified_review"]',
        risk_flags='["over_jd_experience_range"]',
    )
    job = Job(required_skills="React,JavaScript,REST API", preferred_skills="TypeScript")

    trust = _candidate_recruiter_trust(candidate, job)

    assert trust["recruiter_recommendation"] == "recruiter_review"
    assert any("overqualified" in point.lower() for point in trust["risk_points"])
