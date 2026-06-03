import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


ROLE_CASES = [
    {
        "name": "Senior Salesforce Developer",
        "jd": "Senior Salesforce Developer with 5+ years experience. Must have Salesforce, Apex, SOQL, LWC, Sales Cloud and Salesforce Flow.",
        "skills": ["Salesforce", "Apex", "SOQL", "Lightning Web Components", "Sales Cloud", "Salesforce Flow"],
        "strong": {
            "designation": "Senior Salesforce Developer",
            "key_skills": ["Salesforce", "Apex", "SOQL", "Lightning Web Components", "Sales Cloud", "Salesforce Flow"],
            "total_experience_years": 6,
            "experience": [{"company_name": "Cloud CRM", "role": "Senior Salesforce Developer", "duration_years": 6, "description": "Developed Apex classes, SOQL queries, LWC components, Sales Cloud automation and Salesforce Flow."}],
        },
        "generic": {
            "designation": "CRM Analyst",
            "key_skills": ["CRM", "Communication", "Excel"],
            "total_experience_years": 8,
            "experience": [{"company_name": "CRM Co", "role": "CRM Analyst", "duration_years": 8, "description": "Used Salesforce CRM reports and supported sales users."}],
        },
        "fresher": {
            "designation": "Salesforce Intern",
            "key_skills": ["Salesforce", "Trailhead"],
            "total_experience_years": 0.3,
            "experience": [{"company_name": "Training", "role": "Salesforce Intern", "duration_years": 0.3, "description": "Completed Salesforce Trailhead modules."}],
        },
    },
    {
        "name": "Data Analyst 1-3 years",
        "jd": "Data Analyst with 1-3 years experience. Required SQL, Excel, Power BI, dashboards, KPI reporting and MIS reporting.",
        "skills": ["SQL", "Excel", "Power BI", "Dashboard", "MIS Reporting"],
        "strong": {
            "designation": "Data Analyst",
            "key_skills": ["SQL", "Excel", "Power BI", "Dashboard", "MIS Reporting"],
            "total_experience_years": 2,
            "experience": [{"company_name": "Retail Analytics", "role": "Data Analyst", "duration_years": 2, "description": "Built SQL reports, Power BI dashboards, KPI reporting and MIS reporting."}],
        },
        "generic": {
            "designation": "Operations Executive",
            "key_skills": ["Excel", "Communication"],
            "total_experience_years": 8,
            "experience": [{"company_name": "Ops Co", "role": "Operations Executive", "duration_years": 8, "description": "Handled operations coordination and basic Excel trackers."}],
        },
    },
    {
        "name": "Python Backend Developer 3-5 years",
        "jd": "Python Backend Developer with 3-5 years. Must have Python, FastAPI, REST API, PostgreSQL and Docker.",
        "skills": ["Python", "FastAPI", "REST API", "PostgreSQL", "Docker"],
        "strong": {
            "designation": "Python Backend Developer",
            "key_skills": ["Python", "FastAPI", "REST API", "PostgreSQL", "Docker"],
            "total_experience_years": 4,
            "experience": [{"company_name": "API Labs", "role": "Python Backend Developer", "duration_years": 4, "description": "Developed FastAPI REST API services with PostgreSQL and Docker deployments."}],
        },
        "generic": {
            "designation": "Frontend Developer",
            "key_skills": ["JavaScript", "React", "CSS"],
            "total_experience_years": 6,
            "experience": [{"company_name": "Web Co", "role": "Frontend Developer", "duration_years": 6, "description": "Built React interfaces and landing pages."}],
        },
    },
    {
        "name": "HR Executive",
        "jd": "HR Executive required for recruitment, sourcing, screening, onboarding and ATS usage.",
        "skills": ["Recruitment", "Sourcing", "Screening", "Onboarding", "ATS"],
        "strong": {
            "designation": "HR Executive",
            "key_skills": ["Recruitment", "Sourcing", "Screening", "Onboarding", "ATS"],
            "total_experience_years": 2,
            "experience": [{"company_name": "People Co", "role": "HR Executive", "duration_years": 2, "description": "Managed recruitment sourcing, candidate screening, onboarding and ATS records."}],
        },
        "generic": {
            "designation": "Office Admin",
            "key_skills": ["Excel", "Coordination"],
            "total_experience_years": 5,
            "experience": [{"company_name": "Admin Co", "role": "Office Admin", "duration_years": 5, "description": "Handled office coordination and vendor records."}],
        },
    },
    {
        "name": "Sales Executive",
        "jd": "Sales Executive for lead generation, cold calling, sales closing, CRM, communication and negotiation.",
        "skills": ["Lead Generation", "Cold Calling", "Sales Closing", "CRM", "Communication", "Negotiation"],
        "strong": {
            "designation": "Sales Executive",
            "key_skills": ["Lead Generation", "Cold Calling", "Sales Closing", "CRM", "Communication", "Negotiation"],
            "total_experience_years": 3,
            "experience": [{"company_name": "Growth Co", "role": "Sales Executive", "duration_years": 3, "description": "Owned lead generation, cold calling, CRM pipeline, negotiation and sales closing."}],
        },
        "generic": {
            "designation": "Customer Support Associate",
            "key_skills": ["Communication", "CRM"],
            "total_experience_years": 5,
            "experience": [{"company_name": "Support Co", "role": "Customer Support Associate", "duration_years": 5, "description": "Resolved customer tickets using CRM."}],
        },
    },
    {
        "name": "DevOps Engineer",
        "jd": "DevOps Engineer with AWS, Docker, Kubernetes, CI/CD, Terraform and Linux experience.",
        "skills": ["AWS", "Docker", "Kubernetes", "CI/CD", "Terraform", "Linux"],
        "strong": {
            "designation": "DevOps Engineer",
            "key_skills": ["AWS", "Docker", "Kubernetes", "CI/CD", "Terraform", "Linux"],
            "total_experience_years": 4,
            "experience": [{"company_name": "Cloud Ops", "role": "DevOps Engineer", "duration_years": 4, "description": "Deployed AWS infrastructure using Docker, Kubernetes, CI/CD, Terraform and Linux automation."}],
        },
        "generic": {
            "designation": "System Support Engineer",
            "key_skills": ["Linux", "Troubleshooting"],
            "total_experience_years": 7,
            "experience": [{"company_name": "IT Co", "role": "System Support Engineer", "duration_years": 7, "description": "Handled Linux support tickets and desktop troubleshooting."}],
        },
    },
    {
        "name": "Finance Analyst",
        "jd": "Finance Analyst with accounting, financial analysis, Excel, GST, tax and audit exposure.",
        "skills": ["Finance", "Accounting", "Financial Analysis", "Excel", "GST", "Tax", "Audit"],
        "strong": {
            "designation": "Finance Analyst",
            "key_skills": ["Finance", "Accounting", "Financial Analysis", "Excel", "GST", "Tax", "Audit"],
            "total_experience_years": 3,
            "experience": [{"company_name": "Finance Co", "role": "Finance Analyst", "duration_years": 3, "description": "Prepared financial analysis in Excel and supported GST, tax and audit reporting."}],
        },
        "generic": {
            "designation": "Business Analyst",
            "key_skills": ["Excel", "Reporting"],
            "total_experience_years": 8,
            "experience": [{"company_name": "Biz Co", "role": "Business Analyst", "duration_years": 8, "description": "Built general business reports and Excel summaries."}],
        },
    },
]


def score_case(jd, skills, parsed, force_low_quality=False):
    jd_data = {"role": parsed.get("target_role") or "", "min_experience_years": 0, "preferred_skills": ""}
    profile = build_jd_profile(jd, jd_data, skills)
    parsed = dict(parsed)
    resume_text = " ".join([
        str(parsed.get("designation") or ""),
        " ".join(str(skill) for skill in parsed.get("key_skills") or []),
        " ".join(
            " ".join(str(job.get(key) or "") for key in ("company_name", "role", "description"))
            for job in parsed.get("experience") or []
        ),
    ])
    if force_low_quality:
        parsed["parser_quality_action"] = "manual_review_required"
        parsed["parser_quality_score"] = 35
    parsed.update(estimate_relevant_experience_v2(parsed, resume_text, profile))
    parsed["semantic_score"] = 0.65
    parsed["role_similarity"] = 0.6
    parsed["role_family"] = profile["role_family"]
    parsed["role_family_confidence"] = profile["role_family_confidence"]
    return score_candidate(parsed, jd, profile["must_have_skills"], jd_data, resume_text, jd_profile=profile), parsed


def main():
    for case in ROLE_CASES:
        strong_score, strong_parsed = score_case(case["jd"], case["skills"], case["strong"])
        generic_score, generic_parsed = score_case(case["jd"], case["skills"], case["generic"])

        assert strong_score["rank_score"] > generic_score["rank_score"], case["name"]
        assert strong_parsed["relevant_experience_years"] > generic_parsed["relevant_experience_years"], case["name"]
        assert generic_parsed["relevant_experience_years"] < generic_parsed["total_experience_years"], case["name"]
        assert "ranking_reason" in strong_score and strong_score["risk_flags"] is not None, case["name"]

        weak_core = dict(case["strong"])
        weak_core["key_skills"] = weak_core["key_skills"][:1]
        weak_core["experience"] = [{
            "company_name": "Generic Co",
            "role": weak_core.get("designation") or "Associate",
            "duration_years": weak_core.get("total_experience_years") or 1,
            "description": "Handled general responsibilities with limited JD-specific evidence.",
        }]
        weak_score, _ = score_case(case["jd"], case["skills"], weak_core)
        assert weak_score["final_score"] <= 65 or weak_score["mandatory_skill_coverage"] < 40, case["name"]

        low_quality_score, _ = score_case(case["jd"], case["skills"], case["strong"], force_low_quality=True)
        assert low_quality_score["final_score"] <= 58, case["name"]

        if "Senior" in case["name"]:
            fresher_score, fresher_parsed = score_case(case["jd"], case["skills"], case["fresher"])
            assert fresher_score["final_score"] < 70, case["name"]
            assert fresher_parsed["relevant_experience_years"] <= 0.35, case["name"]

    unknown_jd = "Unusual role needing vendor coordination and internal documentation."
    unknown_skills = ["Vendor Coordination"]
    unknown_profile = build_jd_profile(unknown_jd, {}, unknown_skills)
    unknown_score, _ = score_case(unknown_jd, unknown_skills, {
        "designation": "Coordinator",
        "key_skills": ["Vendor Coordination"],
        "total_experience_years": 2,
        "experience": [{"company_name": "Ops", "role": "Coordinator", "duration_years": 2, "description": "Handled vendor coordination and internal documentation."}],
    })
    assert unknown_profile["role_family"] in {"operations", "other"}
    assert unknown_score["confidence_score"] < 90

    print("Role-agnostic ranking checks passed.")


if __name__ == "__main__":
    main()
