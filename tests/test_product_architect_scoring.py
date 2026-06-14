from backend.jd_engine import normalize_jd_skills
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


PRODUCT_ARCHITECT_JD = """
Senior Architect - Product Engineering. Experience 8-10 years. Location Bangalore onsite.
This is a hands-on software/product architecture role for a fast-paced product startup.
The role requires system design, software architecture, backend architecture, API design,
Node.js, Python, Docker, scalability, performance, security, code reviews, mentorship,
technical leadership, product ownership, startup/product engineering, and 0-to-1 product
experience. Do not mix this with civil architects, cloud-only architects, project managers,
delivery managers, or enterprise architects without hands-on product engineering.
"""


def product_architect_profile(jd=PRODUCT_ARCHITECT_JD, role="Senior Architect - Product Engineering"):
    skills = normalize_jd_skills([], jd)
    return build_jd_profile(jd, {"role": role, "experience_required": "8-10 years"}, skills)


def score_product_architect(parsed, jd=PRODUCT_ARCHITECT_JD, role="Senior Architect - Product Engineering"):
    profile = product_architect_profile(jd, role)
    resume_text = " ".join([
        str(parsed.get("designation") or ""),
        " ".join(str(skill) for skill in parsed.get("key_skills") or []),
        " ".join(str(exp.get("role") or "") + " " + str(exp.get("description") or "") for exp in parsed.get("experience") or []),
        " ".join(str(project.get("description") or "") for project in parsed.get("projects") or []),
    ])
    parsed.update(estimate_relevant_experience_v2(parsed, resume_text, profile))
    return profile, score_candidate(
        parsed,
        jd,
        profile["must_have_skills"],
        {"role": role, "experience_required": "8-10 years"},
        resume_text,
        jd_profile=profile,
    )


def test_product_architect_jd_profile_is_locked_to_jd_first_role():
    profile = product_architect_profile()

    assert profile["role_family"] == "product_software_architect"
    assert profile["primary_role"] == "Product Software Architect"
    assert "Software Architect" in profile["secondary_roles"]
    assert "architecture_system_design" in profile["core_skill_groups"]
    assert "hands_on_backend" in profile["core_skill_groups"]
    assert "Civil Architect" in profile["do_not_mix_with"]
    assert profile["positive_signals"]
    assert profile["profile_jd_hash"]


def test_strong_product_software_architect_scores_high():
    parsed = {
        "full_name": "Strong Architect",
        "designation": "Senior Software Architect",
        "key_skills": [
            "System Design", "Software Architecture", "Backend Architecture", "API Design",
            "Node.js", "Python", "Docker", "Kubernetes", "Microservices",
            "Product Engineering", "Startup Experience", "Technical Leadership", "Code Review",
        ],
        "total_experience_years": 9,
        "experience": [{
            "company_name": "B2B SaaS Startup",
            "role": "Senior Software Architect",
            "start_date": "Jan 2017",
            "end_date": "Jan 2026",
            "description": (
                "Architected 0-to-1 product engineering platforms, owned backend architecture "
                "and system design, designed REST API services with Node.js and Python, "
                "Dockerized microservices, improved scalability, performance and security, "
                "led code reviews, mentored engineers, and partnered with founders on product ownership."
            ),
        }],
        "projects": [],
        "resume_quality_score": 92,
    }

    _, result = score_product_architect(parsed)

    assert result["final_score"] >= 82
    assert result["label"] == "Strong Match"
    assert result["recommendation"] == "shortlisted"
    assert not result["missing_core_skill_groups"]


def test_generic_senior_engineer_without_architecture_ownership_is_capped():
    parsed = {
        "full_name": "Generic Engineer",
        "designation": "Senior Software Engineer",
        "key_skills": ["JavaScript", "React", "Node.js", "SQL", "Git"],
        "total_experience_years": 9,
        "experience": [{
            "company_name": "Web Apps Co",
            "role": "Senior Software Engineer",
            "description": "Developed features, fixed bugs, implemented React UI and Node.js APIs, and participated in sprint delivery.",
        }],
        "projects": [],
        "resume_quality_score": 86,
    }

    _, result = score_product_architect(parsed)

    assert result["final_score"] <= 62
    assert result["label"] != "Strong Match"
    assert "generic_engineer_without_architecture_ownership" in result["recruiter_flags"]


def test_cloud_only_solution_architect_without_product_coding_is_low_fit():
    parsed = {
        "full_name": "Cloud Architect",
        "designation": "Cloud Solution Architect",
        "key_skills": ["AWS", "Azure", "Kubernetes", "Terraform", "Cloud Architecture"],
        "total_experience_years": 10,
        "experience": [{
            "company_name": "Cloud Consulting",
            "role": "Cloud Solution Architect",
            "description": "Designed AWS landing zones, cloud architecture, infrastructure governance, vendor management and migration roadmaps.",
        }],
        "projects": [],
        "resume_quality_score": 88,
    }

    _, result = score_product_architect(parsed)

    assert result["final_score"] <= 58
    assert result["label"] == "Low Fit"
    assert "cloud_only_architect" in result["recruiter_flags"]


def test_civil_architect_is_wrong_role_and_capped_low():
    parsed = {
        "full_name": "Civil Architect",
        "designation": "Senior Architect",
        "key_skills": ["AutoCAD", "Revit", "BIM", "Construction", "Site Supervision"],
        "total_experience_years": 9,
        "experience": [{
            "company_name": "Build Studio",
            "role": "Civil Architect",
            "description": "Prepared building plans, Revit BIM models, construction drawings, structural design coordination and site supervision.",
        }],
        "projects": [],
        "resume_quality_score": 80,
    }

    _, result = score_product_architect(parsed)

    assert result["final_score"] <= 38
    assert result["label"] == "Low Fit"
    assert "civil_construction_architect" in result["recruiter_flags"]


def test_project_delivery_manager_is_not_ranked_as_product_architect():
    parsed = {
        "full_name": "Delivery Manager",
        "designation": "Delivery Manager",
        "key_skills": ["Agile", "Scrum", "Stakeholder Management", "Jira", "Project Management"],
        "total_experience_years": 11,
        "experience": [{
            "company_name": "Services Co",
            "role": "Project Manager",
            "description": "Managed sprint planning, resource allocation, delivery governance, stakeholder status reports and project timelines.",
        }],
        "projects": [],
        "resume_quality_score": 82,
    }

    _, result = score_product_architect(parsed)

    assert result["final_score"] <= 48
    assert result["label"] == "Low Fit"
    assert "project_delivery_manager" in result["recruiter_flags"]


def test_same_title_different_jd_creates_different_profile_hash_and_role_profile():
    cloud_jd = """
    Senior Architect. Experience 8-10 years. AWS cloud architecture, landing zones,
    Azure migration, infrastructure governance, network architecture, security posture,
    Terraform, Kubernetes, cost management, and enterprise stakeholder roadmap.
    """

    product_profile = product_architect_profile()
    cloud_profile = product_architect_profile(cloud_jd, "Senior Architect")

    assert product_profile["profile_jd_hash"] != cloud_profile["profile_jd_hash"]
    assert product_profile["role_family"] == "product_software_architect"
    assert cloud_profile["core_skill_groups"] != product_profile["core_skill_groups"]
