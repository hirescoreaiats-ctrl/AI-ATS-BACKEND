from backend.jd_engine import normalize_jd_skills
from backend.experience_engine import process_experience
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


AML_JD = """
AML Transaction Monitoring Investigator (L2). Experience 5-7 years.
Location Bangalore. 100% work from office.
Conduct in-depth investigations on escalated AML alerts and cases, perform
end-to-end transaction and money flow analysis, review KYC, source of funds,
and adverse media findings, identify typologies such as smurfing, layering,
and structuring, prepare detailed case narratives and support SAR/STR
documentation. Must have AML Transaction Monitoring, AML investigations,
case management, SAR/STR reporting process knowledge, and retail banking,
commercial banking, or correspondent banking exposure.
"""


def aml_profile(jd=AML_JD, role="AML Transaction Monitoring Investigator (L2)"):
    skills = normalize_jd_skills([], jd)
    return build_jd_profile(jd, {"role": role, "experience_required": "5-7 years"}, skills)


def score_aml(parsed, jd=AML_JD, role="AML Transaction Monitoring Investigator (L2)"):
    profile = aml_profile(jd, role)
    resume_text = " ".join([
        str(parsed.get("designation") or ""),
        " ".join(str(skill) for skill in parsed.get("key_skills") or []),
        " ".join(
            str(exp.get("role") or "") + " " + str(exp.get("description") or "")
            for exp in parsed.get("experience") or []
        ),
        " ".join(str(project.get("description") or "") for project in parsed.get("projects") or []),
    ])
    parsed.update(estimate_relevant_experience_v2(parsed, resume_text, profile))
    return profile, score_candidate(
        parsed,
        jd,
        profile["must_have_skills"],
        {"role": role, "experience_required": "5-7 years"},
        resume_text,
        jd_profile=profile,
    )


def test_aml_jd_profile_is_independent_role_family():
    profile = aml_profile()

    assert profile["role_family"] == "aml_transaction_monitoring"
    assert profile["primary_role"] == "AML Transaction Monitoring Investigator"
    assert "AML Investigator" in profile["secondary_roles"]
    assert "transaction_monitoring" in profile["core_skill_groups"]
    assert "sar_str" in profile["core_skill_groups"]
    assert "KYC Analyst only" in profile["do_not_mix_with"]


def test_strong_aml_transaction_monitoring_l2_scores_high():
    parsed = {
        "full_name": "Strong AML Investigator",
        "designation": "AML Transaction Monitoring Investigator L2",
        "key_skills": [
            "AML Transaction Monitoring", "AML Investigations", "AML Alerts",
            "Case Management", "SAR", "STR", "Retail Banking", "Adverse Media",
        ],
        "total_experience_years": 6,
        "experience": [{
            "company_name": "Retail Bank",
            "role": "AML Transaction Monitoring Investigator L2",
            "duration_years": 6,
            "description": (
                "Conducted AML Transaction Monitoring investigations on escalated AML alerts. "
                "Performed suspicious transaction review, money laundering investigation, and "
                "transaction flow analysis for retail banking customers. Managed case investigation "
                "workflow, case disposition, alert closure, and detailed case narrative documentation. "
                "Supported SAR and STR documentation, suspicious activity reports, source of funds "
                "review, adverse media review, and typologies including smurfing, layering, and structuring."
            ),
        }],
        "projects": [],
        "resume_quality_score": 92,
    }

    profile, result = score_aml(parsed)

    assert profile["role_family"] == "aml_transaction_monitoring"
    assert result["final_score"] >= 85
    assert result["recommendation"] == "shortlisted"
    assert result["recruiter_recommendation"] in {"Shortlist", "Strong shortlist"}


def test_kyc_only_profile_is_capped_below_true_aml_tm():
    parsed = {
        "full_name": "KYC Analyst",
        "designation": "KYC Analyst",
        "key_skills": ["KYC", "CDD", "EDD", "Adverse Media", "Source of Funds", "Sanctions Screening"],
        "total_experience_years": 6,
        "experience": [{
            "company_name": "Bank Operations",
            "role": "KYC Analyst",
            "duration_years": 6,
            "description": (
                "Handled KYC refresh, CDD, EDD, adverse media checks, source of funds review, "
                "PEP screening, and sanctions screening for banking customers."
            ),
        }],
        "projects": [],
        "resume_quality_score": 86,
    }

    _, result = score_aml(parsed)

    assert result["final_score"] <= 65
    assert result["knockout_flags"]["kyc_only_profile"] is True


def test_mia_qwikresume_sar_and_transaction_monitoring_language_scores_high():
    parsed = {
        "full_name": "Mia Taylor",
        "designation": "Assist. AML Analyst",
        "key_skills": ["Risk Assessment", "Transaction Monitoring", "KYC Procedures", "Suspicious Activity Reporting"],
        "total_experience_years": 7.46,
        "experience": [{
            "company_name": "Quantum Solutions LLC",
            "role": "Assist. AML Analyst",
            "duration_years": 5.4,
            "description": (
                "Detail-oriented AML Analyst with 5 years of experience conducting thorough investigations, "
                "analyzing financial transactions, and mitigating money laundering risks. Reported suspicious "
                "activities to the Financial Intelligence Unit (FIU), ensured adherence to Suspicious Activity "
                "Reporting standards, investigated accounts and transactions flagged as high-risk, prepared "
                "detailed Suspicious Activity Reports (SARs), verified documentation and licensing for Foreign "
                "Money Service Businesses (MSBs), performed AML analysis to assess alerts for potential money "
                "laundering risks in client transactions, monitored exception reports for suspicious activities, "
                "and enhanced AML software capabilities to improve transaction monitoring."
            ),
        }],
        "projects": [],
        "resume_quality_score": 88,
    }

    _, result = score_aml(parsed)

    assert result["final_score"] >= 80
    assert result["evidence_group_scores"]["transaction_monitoring"]["score"] >= 60
    assert result["evidence_group_scores"]["sar_str"]["score"] >= 60
    assert result["evidence_group_scores"]["aml_investigations"]["score"] >= 60


def test_sophia_qwikresume_sar_case_management_language_scores_excellent():
    parsed = {
        "full_name": "Sophia Brown",
        "designation": "AML Analyst II",
        "key_skills": ["Regulatory Reporting", "Risk Assessment", "Fraud Detection"],
        "total_experience_years": 7,
        "experience": [{
            "company_name": "Quantum Solutions LLC",
            "role": "AML Analyst II",
            "duration_years": 7,
            "description": (
                "AML Analyst with 7 years of financial services experience detecting and reporting suspicious "
                "activities. Managed investigations from detection to resolution ensuring thorough documentation. "
                "Evaluated cases for closure or escalation, filing Suspicious Activity Reports when necessary. "
                "Created detailed reports and presentations to support complex AML investigations. Reviewed bank "
                "accounts and credit card transactions for money laundering indicators, compiled and summarized "
                "findings in reports for FinCEN compliance, prepared data for Suspicious Activity Report submissions, "
                "and utilized Verafin AML software to assess alerts requiring further investigation."
            ),
        }],
        "projects": [],
        "resume_quality_score": 90,
    }

    _, result = score_aml(parsed)

    assert result["final_score"] >= 85
    assert result["evidence_group_scores"]["sar_str"]["score"] >= 60
    assert result["evidence_group_scores"]["case_management"]["score"] >= 60


def test_rowan_financial_crime_tools_count_as_transaction_monitoring():
    parsed = {
        "full_name": "Rowan Ashford",
        "designation": "Financial Crime Analyst",
        "key_skills": ["Actimize", "FICO", "ACI Worldwide", "Global Radar", "Anti-Money Laundering"],
        "total_experience_years": 13.46,
        "experience": [{
            "company_name": "Connecticut Department of Banking",
            "role": "Financial Crime Analyst",
            "duration_years": 4.5,
            "description": (
                "Analyzed transaction data on Actimize, implemented new data classification in Oracle Financial "
                "Services, designed and deployed automated alerts within Global Radar, and mapped complex financial "
                "crime networks. As an Anti-Money Laundering Analyst, executed FICO-based monitoring systems, "
                "reduced false positives for transaction alerts, expanded the AML software program, built and refined "
                "alerts in ACI Worldwide for accurate tracking and reporting of suspicious activities in real-time, "
                "and processed and analyzed over 251 suspicious transactions per month using SAS to prevent money laundering."
            ),
        }],
        "projects": [],
        "resume_quality_score": 88,
    }

    _, result = score_aml(parsed)

    assert result["final_score"] >= 75
    assert result["evidence_group_scores"]["transaction_monitoring"]["score"] >= 60
    assert result["evidence_group_scores"]["banking_exposure"]["score"] >= 60


def test_aml_role_titles_are_not_valid_company_names():
    result = process_experience([
        {
            "company_name": "Aml",
            "role": "Analyst",
            "start_date": "Dec 2019",
            "end_date": "Dec 2020",
        },
        {
            "company_name": "Assist. AML Analyst",
            "role": "Assist. AML Analyst",
            "start_date": "Dec 2020",
            "end_date": "Present",
        },
        {
            "company_name": "Quantum Solutions LLC",
            "role": "Assist. AML Analyst",
            "start_date": "Dec 2020",
            "end_date": "Present",
        },
    ])

    validity = {item["company_name"]: item["company_valid"] for item in result["extracted_date_ranges_raw"]}
    assert validity["Aml"] is False
    assert validity["Assist. AML Analyst"] is False
    assert validity["Quantum Solutions LLC"] is True
    assert result["last_company_name"] == "Quantum Solutions LLC"


def test_data_analyst_banking_dashboard_does_not_match_aml_strongly():
    parsed = {
        "full_name": "Data Analyst",
        "designation": "Data Analyst",
        "key_skills": ["SQL", "Power BI", "Excel", "Dashboard", "Banking"],
        "total_experience_years": 6,
        "experience": [{
            "company_name": "Bank Analytics",
            "role": "Data Analyst",
            "duration_years": 6,
            "description": "Built SQL and Power BI dashboards for banking operations KPIs and MIS reporting.",
        }],
        "projects": [],
        "resume_quality_score": 84,
    }

    _, result = score_aml(parsed)

    assert result["final_score"] <= 45
    assert result["jd_role_family"] == "aml_transaction_monitoring"


def test_fraud_analyst_without_aml_tm_is_partial_only():
    parsed = {
        "full_name": "Fraud Analyst",
        "designation": "Fraud Analyst",
        "key_skills": ["Fraud Investigation", "Suspicious Transactions", "Banking"],
        "total_experience_years": 6,
        "experience": [{
            "company_name": "Bank Fraud Ops",
            "role": "Fraud Analyst",
            "duration_years": 6,
            "description": (
                "Investigated fraud alerts and suspicious transactions for banking customers. "
                "Reviewed account activity and prepared internal fraud case notes."
            ),
        }],
        "projects": [],
        "resume_quality_score": 85,
    }

    _, result = score_aml(parsed)

    assert 55 <= result["final_score"] <= 70
    assert "partial_fraud_match" in result["risk_flags"]


def test_aml_tm_under_experienced_for_l2_is_flagged_and_below_70():
    parsed = {
        "full_name": "Junior AML Investigator",
        "designation": "AML Transaction Monitoring Analyst",
        "key_skills": ["AML Transaction Monitoring", "AML Investigations", "Case Management", "SAR", "Retail Banking"],
        "total_experience_years": 2,
        "experience": [{
            "company_name": "Retail Bank",
            "role": "AML Transaction Monitoring Analyst",
            "duration_years": 2,
            "description": (
                "Handled AML Transaction Monitoring alerts, AML investigations, case management, "
                "SAR documentation support, and suspicious transaction review in retail banking."
            ),
        }],
        "projects": [],
        "resume_quality_score": 88,
    }

    _, result = score_aml(parsed)

    assert result["final_score"] < 70
    assert result["knockout_flags"]["under_experienced_for_l2"] is True


def test_senior_aml_tm_over_experienced_is_review_not_rejected():
    parsed = {
        "full_name": "Senior AML Investigator",
        "designation": "Senior AML Analyst",
        "key_skills": [
            "AML Transaction Monitoring", "AML Investigations", "Case Management",
            "SAR", "STR", "Correspondent Banking", "Transaction Review",
        ],
        "total_experience_years": 11,
        "experience": [{
            "company_name": "Correspondent Bank",
            "role": "Senior AML Analyst",
            "duration_years": 11,
            "description": (
                "Led AML Transaction Monitoring investigations for correspondent banking. "
                "Reviewed escalated AML alerts, suspicious transaction investigation, money laundering "
                "typologies, case disposition, case narrative writing, SAR and STR documentation, "
                "and transaction flow analysis."
            ),
        }],
        "projects": [],
        "resume_quality_score": 90,
    }

    _, result = score_aml(parsed)

    assert 75 <= result["final_score"] <= 85
    assert result["recommendation"] != "rejected"
    assert result["knockout_flags"]["over_experienced_for_l2"] is True
