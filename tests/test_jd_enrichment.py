from backend.services.jd_enrichment import enrich_jd_for_scoring
from backend.services.scoring_service import score_candidate


EMPTY_STRUCTURED = {
    "role": "",
    "required_skills": [],
    "preferred_skills": [],
    "min_experience_years": 0,
    "location": "",
    "education": "",
}


def test_title_only_data_analyst_jd_gets_scoring_profile_defaults():
    enrichment = enrich_jd_for_scoring(
        "Data Analyst",
        {"job_title": "Data Analyst", "role": "Data Analyst"},
        structured_jd=dict(EMPTY_STRUCTURED),
    )

    assert enrichment["role_family"] == "data_analytics"
    assert {"SQL", "Excel", "Data Analysis", "Data Visualization", "Reporting"}.issubset(
        set(enrichment["required_skills"])
    )
    assert {"Power BI", "Tableau", "Power Query", "DAX", "MIS Reporting"}.issubset(
        set(enrichment["preferred_skills"])
    )
    assert {"querying", "spreadsheet", "bi_tool", "reporting"} == set(enrichment["core_skill_groups"])


def test_title_only_salesforce_developer_jd_gets_developer_gates():
    enrichment = enrich_jd_for_scoring(
        "Salesforce Developer",
        {"job_title": "Salesforce Developer", "role": "Salesforce Developer"},
        structured_jd=dict(EMPTY_STRUCTURED),
    )

    assert enrichment["role_family"] == "salesforce_crm"
    assert {"Salesforce", "Salesforce Development", "Apex", "SOQL", "Lightning Web Components"}.issubset(
        set(enrichment["required_skills"])
    )
    assert {"Salesforce Flow", "Sales Cloud", "Service Cloud", "Salesforce CPQ"}.issubset(
        set(enrichment["preferred_skills"])
    )
    assert {"platform", "programming", "ui"} == set(enrichment["core_skill_groups"])


def test_enriched_salesforce_jd_keeps_generic_crm_user_out_of_shortlist():
    enrichment = enrich_jd_for_scoring(
        "Salesforce Developer",
        {"job_title": "Salesforce Developer", "role": "Salesforce Developer", "experience_required": "3+ Years"},
        structured_jd={**EMPTY_STRUCTURED, "min_experience_years": 3},
    )
    jd_data = {
        "role": enrichment["role"],
        "min_experience_years": enrichment["min_experience_years"],
        "preferred_skills": enrichment["preferred_skills"],
    }

    generic = score_candidate(
        {
            "key_skills": ["Salesforce", "CRM", "Communication", "Excel"],
            "total_experience_years": 5,
            "relevant_experience_years": 0.5,
            "role_relevance_score": 20,
            "designation": "Business Development Executive",
            "experience": [{
                "role": "Business Development Executive",
                "description": "Used Salesforce CRM for account tracking and reports.",
            }],
            "resume_quality_score": 82,
            "semantic_score": 0.45,
        },
        "Salesforce Developer",
        enrichment["required_skills"],
        jd_data,
        "Business development candidate using Salesforce CRM for account tracking.",
        jd_profile=enrichment["jd_profile"],
    )

    strong = score_candidate(
        {
            "key_skills": ["Salesforce", "Salesforce Development", "Apex", "SOQL", "Lightning Web Components"],
            "total_experience_years": 4,
            "relevant_experience_years": 4,
            "role_relevance_score": 90,
            "designation": "Salesforce Developer",
            "experience": [{
                "role": "Salesforce Developer",
                "description": "Handled Salesforce Development work building Apex classes, SOQL queries and Lightning Web Components.",
            }],
            "resume_quality_score": 86,
            "semantic_score": 0.78,
        },
        "Salesforce Developer",
        enrichment["required_skills"],
        jd_data,
        "Salesforce Developer handled Salesforce Development using Apex SOQL Lightning Web Components.",
        jd_profile=enrichment["jd_profile"],
    )

    assert generic["recommendation"] != "shortlisted"
    assert "Apex" in generic["missing_skills"]
    assert "SOQL" in generic["missing_skills"]
    assert strong["rank_score"] > generic["rank_score"]
    assert strong["mandatory_skill_coverage"] >= 80
