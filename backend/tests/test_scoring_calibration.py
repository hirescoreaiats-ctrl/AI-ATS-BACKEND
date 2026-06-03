from backend.services.scoring_service import score_candidate
from backend.jd_engine import normalize_jd_skills


DATA_ANALYST_JD = """
Data Analyst role. Experience: 1-3 Years.
Core skills: SQL, Advanced Excel, Power BI, Power Query, DAX, MIS Reporting,
KPI Reporting, Dashboard Creation, Business Reporting, and Data Cleaning.
"""


DATA_ANALYST_SKILLS = [
    "SQL",
    "Advanced Excel",
    "Power BI",
    "Power Query",
    "DAX",
    "MIS Reporting",
    "KPI Reporting",
    "Dashboard Creation",
    "Business Reporting",
    "Data Cleaning",
]


JD_DATA = {
    "role": "Data Analyst",
    "min_experience_years": 1,
    "max_experience_years": 3,
    "education": "Bachelor",
}


def score(parsed, resume_text):
    return score_candidate(parsed, DATA_ANALYST_JD, DATA_ANALYST_SKILLS, dict(JD_DATA), resume_text)


def test_best_data_analyst_match_is_capped_below_unrealistic_95():
    result = score(
        {
            "key_skills": ["SQL", "Excel", "Power BI", "Power Query", "DAX", "MIS Reporting", "KPI Reporting", "Data Cleaning"],
            "total_experience_years": 2,
            "relevant_experience_years": 2,
            "designation": "MIS Data Analyst",
            "experience": [{
                "role": "MIS Data Analyst",
                "description": "Automated KPI dashboards, business reporting, MIS reports using SQL, Advanced Excel pivot tables, Power BI, Power Query and DAX.",
            }],
            "projects": [],
            "semantic_score": 0.82,
            "role_similarity": 0.8,
            "resume_quality_score": 85,
        },
        "2+ years MIS Data Analyst. SQL Advanced Excel pivot tables Power BI Power Query DAX MIS reporting KPI dashboard report automation business reporting data cleaning.",
    )

    assert 90 <= result["final_score"] <= 94
    assert result["recommendation"] == "shortlisted"
    assert result["all_critical_requirements_met"] is True


def test_strong_project_fresher_gets_controlled_boost_not_95():
    result = score(
        {
            "key_skills": ["Python", "SQL", "Power BI", "Excel", "Pandas", "DAX", "Power Query"],
            "total_experience_years": 0.5,
            "relevant_experience_years": 0.5,
            "designation": "Junior Data Analyst",
            "experience": [],
            "projects": [{
                "name": "Sales KPI Dashboard",
                "description": "Built Power BI dashboard with SQL, DAX, Power Query, Excel, KPI tracking and report automation for retail sales data.",
                "technologies": ["Power BI", "SQL", "DAX", "Power Query", "Excel"],
            }],
            "semantic_score": 0.82,
            "role_similarity": 0.75,
            "resume_quality_score": 82,
        },
        "Projects: Sales KPI dashboard using Python SQL Power BI Excel Pandas DAX Power Query KPI tracking automation retail sales data cleaning.",
    )

    assert 78 <= result["final_score"] <= 84
    assert result["recommendation"] in {"shortlisted", "in_review"}
    assert "under_experienced" in result["recruiter_flags"]
    assert "good_project_match" in result["recruiter_flags"]


def test_zero_year_strong_projects_stay_in_review_band():
    result = score(
        {
            "key_skills": ["SQL", "MySQL", "Power BI", "DAX", "Power Query", "Microsoft Excel", "Data Cleaning"],
            "total_experience_years": 0,
            "relevant_experience_years": 0,
            "designation": "Junior Data Analyst",
            "experience": [],
            "projects": [{
                "name": "Banking ETL KPI Dashboard",
                "description": "Processed 153K rows with ETL pipeline, cleaned data in Excel, transformed in MySQL using SQL, created Power BI dashboard with DAX KPIs and business insights.",
                "technologies": ["Power BI", "SQL", "DAX", "Power Query", "Excel"],
            }],
            "semantic_score": 0.82,
            "role_similarity": 0.75,
            "resume_quality_score": 82,
        },
        "Projects Banking ETL KPI Dashboard. 153K rows. SQL MySQL Power BI DAX Power Query Advanced Excel data cleaning transformation business insights.",
    )

    assert 75 <= result["final_score"] <= 82
    assert result["recommendation"] in {"shortlisted", "in_review"}
    assert "good_project_match" in result["recruiter_flags"]


def test_ten_plus_year_candidate_is_review_not_auto_shortlisted():
    result = score(
        {
            "key_skills": ["SQL", "Excel", "Power BI", "Tableau", "Data Cleaning", "Forecasting", "Business Reporting"],
            "total_experience_years": 11,
            "relevant_experience_years": 11,
            "designation": "Senior BI Analyst",
            "experience": [{
                "role": "Business Intelligence Analyst",
                "description": "Developed BI dashboards, forecasting, sales reporting, Excel and SQL reports.",
            }],
            "projects": [],
            "semantic_score": 0.82,
            "role_similarity": 0.75,
            "resume_quality_score": 84,
        },
        "11+ years Senior BI Analyst. SQL Excel Power BI Tableau forecasting BI dashboards business reporting data cleaning.",
    )

    assert 64 <= result["final_score"] <= 72
    assert result["recommendation"] == "in_review"
    assert "overqualified" in result["recruiter_flags"]


def test_bootcamp_candidate_with_basic_tools_remains_review_not_reject():
    result = score(
        {
            "key_skills": ["Excel", "SQL", "Power BI", "Tableau", "Python"],
            "total_experience_years": 0,
            "relevant_experience_years": 0,
            "designation": "Data Analyst Bootcamp Graduate",
            "experience": [],
            "projects": [{
                "name": "Marketing Dashboard",
                "description": "Python, SQL, Tableau and Power BI project with Excel charts for campaign analysis.",
                "technologies": ["Python", "SQL", "Tableau", "Power BI", "Excel"],
            }],
            "semantic_score": 0.76,
            "role_similarity": 0.7,
            "resume_quality_score": 78,
        },
        "Bootcamp projects Python SQL Power BI Tableau Excel dashboard project for marketing campaign analysis.",
    )

    assert 60 <= result["final_score"] <= 72
    assert result["recommendation"] == "in_review"
    assert "missing_core_skills" in result["recruiter_flags"]


def test_transferable_reporting_candidate_is_capped_as_review():
    resume_text = """
    Teresa Whitesell Data Analyst bootcamp graduate.
    Nashville Software School used Excel, SQL, Python, Tableau and Power BI to create dashboards and presentations.
    Work Experience: Weight Watchers of Middle and East TN 2012-2020
    Administrative Assistant and Customer Support Rep.
    Compiled weekly spreadsheet reports, checked data for accuracy, automated spreadsheet processes,
    delivered year-over-year data analysis to leadership and analyzed attendance data for retention incentives.
    Projects: Ravelry Capstone using Python, Tableau and Excel. Nashville City Cemetery presentation using Excel.
    """
    result = score(
        {
            "key_skills": ["SQL", "Excel", "Power BI", "Tableau", "Python", "Data Visualization", "Presentation"],
            "total_experience_years": 9.0,
            "relevant_experience_years": 1.0,
            "direct_relevant_experience_years": 0.0,
            "transferable_reporting_experience_years": 1.0,
            "transition_candidate": True,
            "designation": "Data Analyst",
            "experience": [{
                "role": "Administrative Assistant and Customer Support Rep",
                "description": "Weekly spreadsheet reports, data accuracy checks, automated internal spreadsheet processes, year-over-year analysis and attendance metrics for leadership.",
            }],
            "projects": [{
                "name": "Ravelry Capstone",
                "description": "Used Python, Tableau and Excel to analyze store inventory recommendations.",
                "technologies": ["Python", "Tableau", "Excel"],
            }],
            "semantic_score": 0.78,
            "role_similarity": 0.8,
            "resume_quality_score": 82,
        },
        resume_text,
    )

    assert 68 <= result["final_score"] <= 72
    assert result["recommendation"] == "in_review"
    assert result["experience_fit"] == "transition_review"
    assert "transition_candidate" in result["recruiter_flags"]
    assert "missing_core_skills" in result["recruiter_flags"]


def test_slightly_above_range_data_analyst_is_not_overqualified_and_detects_cleaning():
    resume_text = """
    Nasarin Artoul Data Analyst with 3.25 years.
    SQL PostgreSQL Microsoft Excel Tableau Power BI dashboards.
    Structured, mined, and cleaned large data sets. Built VBA macros that normalize addresses,
    delete extraneous data, and remove unwanted characters. Created ad-hoc reports and dashboards.
    """
    result = score(
        {
            "key_skills": ["SQL", "Excel", "Power BI", "Tableau", "Data Analysis", "Dashboard"],
            "total_experience_years": 3.25,
            "relevant_experience_years": 3.25,
            "designation": "Data Analyst",
            "experience": [{
                "role": "Data Analyst",
                "description": resume_text,
            }],
            "projects": [{"name": "Comparing 2008 Recession to Coronavirus Recession", "description": "Tableau and Power BI analysis dashboard."}],
            "semantic_score": 0.8,
            "role_similarity": 0.8,
            "resume_quality_score": 82,
        },
        resume_text,
    )

    assert result["experience_fit"] == "slightly_over_range"
    assert "overqualified" not in result["recruiter_flags"]
    assert "Data Cleaning" in result["matched_skills"]
    assert "Data Cleaning" not in result["missing_skills"]
    assert 78 <= result["final_score"] <= 82
    assert result["recommendation"] in {"shortlisted", "in_review"}


def test_salesforce_jd_extracts_core_platform_skills():
    jd_text = """
    Salesforce Developer with 3+ years of experience.
    Must have Salesforce, Apex, Lightning Web Components (LWC), SOQL,
    Salesforce Flow, JavaScript, and strong communication.
    """

    skills = normalize_jd_skills([], jd_text)

    assert "Salesforce" in skills
    assert "Salesforce Development" in skills
    assert "Apex" in skills
    assert "Lightning Web Components" in skills
    assert "SOQL" in skills
    assert "Salesforce Flow" in skills
    assert "JavaScript" in skills


def test_salesforce_role_does_not_shortlist_generic_javascript_candidate():
    jd_text = """
    Salesforce Developer with 3+ years of experience.
    Must have Salesforce, Apex, Lightning Web Components (LWC), SOQL,
    Salesforce Flow, JavaScript, and communication.
    """
    jd_skills = normalize_jd_skills([], jd_text)
    jd_data = {
        "role": "Salesforce Developer",
        "min_experience_years": 3,
        "preferred_skills": [],
    }

    generic_result = score_candidate(
        {
            "key_skills": ["Python", "Java", "JavaScript", "Flask", "SQL", "Communication"],
            "total_experience_years": 5.33,
            "relevant_experience_years": 5.33,
            "designation": "Developer",
            "experience": [{
                "role": "Developer",
                "description": "Built Python Flask web apps with JavaScript and SQL.",
            }],
            "projects": [],
            "resume_quality_score": 88,
            "semantic_score": 0.45,
        },
        jd_text,
        jd_skills,
        jd_data,
        "Python Flask JavaScript SQL Communication developer projects.",
    )

    salesforce_result = score_candidate(
        {
            "key_skills": [
                "Salesforce",
                "Apex",
                "Lightning Web Components",
                "SOQL",
                "Salesforce Flow",
                "JavaScript",
                "Communication",
            ],
            "total_experience_years": 4,
            "relevant_experience_years": 4,
            "designation": "Salesforce Developer",
            "experience": [{
                "role": "Salesforce Developer",
                "description": "Developed Apex classes, LWC components, SOQL queries and Salesforce Flow automation.",
            }],
            "projects": [],
            "resume_quality_score": 86,
            "semantic_score": 0.8,
        },
        jd_text,
        jd_skills,
        jd_data,
        "Salesforce Developer Apex LWC Lightning Web Components SOQL Salesforce Flow JavaScript Communication.",
    )

    assert generic_result["recommendation"] != "shortlisted"
    assert generic_result["mandatory_skill_coverage"] <= 30
    assert "Salesforce" in generic_result["missing_skills"]
    assert salesforce_result["recommendation"] == "shortlisted"
    assert salesforce_result["rank_score"] > generic_result["rank_score"]
    assert "transition_candidate" not in salesforce_result["recruiter_flags"]


def test_salesforce_crm_usage_does_not_satisfy_developer_skills():
    jd_text = """
    Senior Salesforce Developer. Must have Salesforce, Apex, Lightning Web Components,
    SOQL, Salesforce Flow, JavaScript, and Communication.
    """
    jd_skills = normalize_jd_skills([], jd_text)
    jd_data = {
        "role": "Senior Salesforce Developer",
        "min_experience_years": 5,
        "preferred_skills": [],
    }

    result = score_candidate(
        {
            "key_skills": ["Salesforce", "JavaScript", "Communication", "CRM"],
            "total_experience_years": 6.16,
            "relevant_experience_years": 6.16,
            "designation": "New Business Development",
            "experience": [{
                "role": "New Business Development",
                "description": "Used Salesforce CRM, SalesNav and SalesLoft for lead and account tracking.",
            }],
            "projects": [],
            "resume_quality_score": 85,
            "semantic_score": 0.55,
        },
        jd_text,
        jd_skills,
        jd_data,
        "Cloudflare business development using Salesforce CRM and JavaScript demos.",
    )

    assert "Salesforce" in result["matched_skills"]
    assert "Apex" in result["missing_skills"]
    assert "Lightning Web Components" in result["missing_skills"]
    assert "SOQL" in result["missing_skills"]
    assert result["recommendation"] != "shortlisted"
    assert result["rank_score"] < 68


def test_salesforce_developer_with_partial_core_coverage_is_review_not_rejected():
    jd_text = """
    Senior Salesforce Developer. Must have Salesforce, Salesforce Development,
    Apex, Lightning Web Components, Aura Components, Visualforce, SOQL, SOSL,
    Salesforce Flow, Salesforce CPQ, Sales Cloud, Service Cloud, Salesforce Admin,
    JavaScript, and Communication.
    """
    jd_skills = normalize_jd_skills([], jd_text)
    jd_data = {
        "role": "Senior Salesforce Developer",
        "min_experience_years": 5,
        "max_experience_years": 8,
        "preferred_skills": [],
    }

    result = score_candidate(
        {
            "key_skills": [
                "Salesforce",
                "Salesforce Development",
                "Apex",
                "Visualforce",
                "SOQL",
                "Salesforce Flow",
                "Salesforce CPQ",
                "Salesforce Admin",
                "JavaScript",
                "Communication",
            ],
            "total_experience_years": 8.74,
            "relevant_experience_years": 4.91,
            "designation": "Senior Salesforce Developer",
            "experience": [{
                "role": "Senior Salesforce Developer",
                "description": "Created Apex triggers, Visualforce pages, SOQL queries, Salesforce Flows, CPQ automation, admin tasks, and JavaScript tooling.",
            }],
            "projects": [],
            "resume_quality_score": 90,
            "semantic_score": 0.75,
        },
        jd_text,
        jd_skills,
        jd_data,
        "Senior Salesforce Developer Apex Visualforce SOQL Salesforce Flow CPQ Admin JavaScript Communication.",
    )

    assert result["mandatory_skill_coverage"] >= 60
    assert result["recommendation"] == "in_review"
    assert "missing_core_skills" not in result["recruiter_flags"]


def test_senior_salesforce_caps_use_salesforce_specific_experience():
    jd_text = """
    Senior Salesforce Developer. Must have Apex, Lightning Web Components,
    Visualforce, SOQL, Salesforce Flow, Sales Cloud, JavaScript, and Communication.
    """
    jd_skills = normalize_jd_skills([], jd_text)
    jd_data = {
        "role": "Senior Salesforce Developer",
        "min_experience_years": 5,
        "max_experience_years": 8,
        "preferred_skills": [],
    }

    result = score_candidate(
        {
            "key_skills": ["Salesforce", "Apex", "SOQL", "Salesforce Flow", "Sales Cloud", "JavaScript", "Communication"],
            "total_experience_years": 8,
            "relevant_experience_years": 1.58,
            "salesforce_experience_years": 1.58,
            "designation": "Salesforce Developer",
            "experience": [{
                "role": "Salesforce Developer",
                "description": "Built Apex classes, SOQL queries and Salesforce Flows for Sales Cloud.",
            }],
            "projects": [],
            "resume_quality_score": 88,
            "semantic_score": 0.82,
        },
        jd_text,
        jd_skills,
        jd_data,
        "Salesforce Developer Apex SOQL Salesforce Flow Sales Cloud JavaScript Communication.",
    )

    assert result["final_score"] <= 50
    assert result["recommendation"] == "rejected"
    assert "salesforce_seniority_gate" in result["recruiter_flags"]


def test_borderline_senior_salesforce_is_review_capped_not_auto_shortlisted():
    jd_text = """
    Senior Salesforce Developer. Must have Salesforce, Apex, Lightning Web Components,
    Visualforce, SOQL, Salesforce Flow, JavaScript, and Communication.
    """
    jd_skills = normalize_jd_skills([], jd_text)
    jd_data = {
        "role": "Senior Salesforce Developer",
        "min_experience_years": 5,
        "max_experience_years": 8,
        "preferred_skills": [],
    }

    result = score_candidate(
        {
            "key_skills": ["Salesforce", "Apex", "Lightning Web Components", "Visualforce", "SOQL", "Salesforce Flow", "JavaScript", "Communication"],
            "total_experience_years": 8.7,
            "relevant_experience_years": 4.2,
            "salesforce_experience_years": 4.2,
            "designation": "Senior Salesforce Developer",
            "experience": [{
                "role": "Senior Salesforce Developer",
                "description": "Owned Apex, LWC, Visualforce, SOQL and Flow work on Salesforce.",
            }],
            "projects": [],
            "resume_quality_score": 95,
            "semantic_score": 0.9,
        },
        jd_text,
        jd_skills,
        jd_data,
        "Senior Salesforce Developer Apex LWC Lightning Web Components Visualforce SOQL Salesforce Flow JavaScript Communication.",
    )

    assert result["final_score"] <= 75
    assert result["recommendation"] == "in_review"
    assert "salesforce_seniority_gate" in result["recruiter_flags"]
