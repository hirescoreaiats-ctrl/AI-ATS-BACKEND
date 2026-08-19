from datetime import datetime
import json

import pytest

from backend.experience_engine import process_experience
from backend.models import Job, Resume
from backend.routers.job import _rescore_candidate_from_stored_fields
from backend.services.experience_relevance import _years_from_job, estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.role_taxonomy import match_core_skill_groups
from backend.services.scoring_service import (
    _classify_skill_evidence,
    _is_qa_target,
    score_candidate,
)
from backend.services.taxonomy import known_skills_in_text


EMBEDDED_JD = """
Firmware / Embedded Software Engineer
The engineer will design, develop, test, validate, and maintain firmware and
manufacturing test tools.

Required Qualifications
5-7 years of relevant firmware/embedded software development experience.
Strong programming experience in C.
Experience with microcontrollers and embedded hardware.
Strong firmware and embedded-system debugging skills.
Work with electrical engineers on hardware/software integration.

Preferred Qualifications
RTOS and real-time embedded systems. Python automation testing. RF systems.
Git and JIRA.
"""


QA_JD = """
QA Automation Engineer
Build Selenium automation tests, API tests, regression suites and test cases.
Use Postman, Python, SQL and Jira.
"""


def _embedded_profile():
    return build_jd_profile(EMBEDDED_JD, {"role": "Firmware / Embedded Software Engineer"})


def test_embedded_title_dominates_generic_testing_language_and_qa_caps_do_not_run():
    profile = _embedded_profile()
    assert profile["role_family"] == "embedded_firmware"
    assert profile["role_family"] != "qa_automation"
    assert not _is_qa_target(profile)

    parsed = {
        "designation": "Embedded Firmware Engineer",
        "current_title": "Embedded Firmware Engineer",
        "key_skills": ["Embedded Firmware", "Embedded Hardware", "RTOS", "Debugging"],
        "experience": [{
            "company_name": "Acme Systems",
            "role": "Embedded Firmware Engineer",
            "start_date": "Jan 2022",
            "end_date": "Present",
            "description": "Developed RTOS firmware and debugged embedded hardware integration issues.",
        }],
        "projects": [],
        "education": [{"degree": "Bachelor"}],
        "total_experience_years": 4.5,
        "parser_quality_score": 90,
        "parser_quality_action": "auto_rank_ok",
        "semantic_score": 0.7,
    }
    parsed.update(estimate_relevant_experience_v2(parsed, parsed["experience"][0]["description"], profile))
    result = score_candidate(parsed, EMBEDDED_JD, profile["must_have_skills"], {"role": profile["role_title"]}, parsed["experience"][0]["description"], jd_profile=profile)
    cap_text = " ".join(item["reason"] for item in result["score_caps_applied"])
    assert "QA JD" not in cap_text
    assert "QA core" not in cap_text
    assert result["detected_role_family"] == "embedded_firmware"


def test_qa_role_family_and_guards_still_work():
    profile = build_jd_profile(QA_JD, {"role": "QA Automation Engineer"})
    assert profile["role_family"] == "qa_automation"
    assert _is_qa_target(profile)


def test_embedded_hw_and_fw_normalize_to_both_requirements():
    skills = known_skills_in_text("Embedded HW and FW")
    assert "Embedded Hardware" in skills
    assert "Firmware" in skills
    groups = match_core_skill_groups(
        {"hardware": ["Embedded Hardware"], "firmware": ["Firmware"]},
        skills,
        "Embedded HW and FW",
    )
    assert groups["core_skill_match_percent"] == 100


def test_debugged_work_bullet_is_strong_professional_evidence():
    parsed = {
        "key_skills": [],
        "experience": [{
            "company_name": "Acme Systems",
            "role": "Hardware Engineer",
            "description": "Debugged critical HF and VHF communication systems.",
        }],
    }
    evidence = _classify_skill_evidence(
        "Debugging",
        parsed,
        parsed["experience"][0]["description"],
        role_family="embedded_firmware",
    )
    assert evidence["status"] == "matched"
    assert evidence["evidence_level"] == "professional_strong"
    assert evidence["source"] == "work_experience"


def test_exact_c_is_verify_when_only_embedded_context_exists():
    text = "Built RTOS firmware for resource-constrained real-time embedded systems."
    evidence = _classify_skill_evidence(
        "C",
        {"key_skills": [], "experience": []},
        text,
        role_family="embedded_firmware",
    )
    assert evidence["status"] == "verify"
    assert evidence["evidence_level"] == "contextual_support"


def test_seasonal_terms_use_stable_three_month_policy_and_do_not_fill_gaps():
    records = [
        {"company_name": "Acme Systems", "role": "Engineer", "start_date": "Summer 2023", "end_date": "Summer 2023"},
        {"company_name": "Beta Systems", "role": "Engineer", "start_date": "Fall 2021", "end_date": "Fall 2021"},
        {"company_name": "Gamma Systems", "role": "Engineer", "start_date": "Winter 2021", "end_date": "Winter 2021"},
    ]
    result = process_experience(records)
    assert result["total_experience_years"] == pytest.approx(0.75, abs=0.02)

    split_terms = process_experience([{
        "company_name": "Acme Systems",
        "role": "Hardware Engineer",
        "start_date": "Summer 2022",
        "end_date": "Winter 2023",
    }])
    assert split_terms["total_experience_years"] == pytest.approx(0.5, abs=0.02)


def test_present_role_uses_actual_elapsed_duration():
    expected = (datetime.now() - datetime(2024, 8, 1)).days / 365
    years = _years_from_job({"start_date": "August 2024", "end_date": "Present"})
    assert years == pytest.approx(expected, abs=0.02)
    assert years > 1


def test_generic_leadership_title_gets_relevance_from_embedded_responsibilities():
    profile = _embedded_profile()
    parsed = {
        "total_experience_years": 2,
        "experience": [{
            "company_name": "Acme Systems",
            "role": "Head of Engineering",
            "start_date": "August 2024",
            "end_date": "Present",
            "description": "Designed phased-array embedded hardware and RF communication systems.",
        }],
    }
    relevance = estimate_relevant_experience_v2(parsed, parsed["experience"][0]["description"], profile)
    assert relevance["relevant_experience_years"] >= 1
    assert relevance["experience_evidence"][0]["label"] in {"direct", "partial"}
    assert relevance["candidate_role_affinity"]["embedded_firmware"] >= 0.55


def test_rereview_uses_stored_full_timeline_instead_of_collapsing_to_latest_title():
    candidate = Resume(
        full_name="Stored Candidate",
        designation="Head of Engineering",
        key_skills="Embedded HW and FW, RTOS",
        total_experience_years=3.0,
        resume_text="Embedded HW and FW. RTOS firmware. Debugged RF communication systems.",
        parser_quality_score=90,
        parser_confidence=90,
        parser_quality_action="auto_rank_ok",
        raw_parsed_json=json.dumps({
            "experience": [
                {
                    "company_name": "Acme Systems",
                    "role": "Embedded Firmware Engineer",
                    "start_date": "Jan 2022",
                    "end_date": "Dec 2023",
                    "description": "Developed RTOS firmware and debugged embedded hardware.",
                },
                {
                    "company_name": "Current Systems",
                    "role": "Head of Engineering",
                    "start_date": "Jan 2024",
                    "end_date": "Present",
                    "description": "Designed embedded RF hardware systems.",
                },
            ]
        }),
    )
    job = Job(
        id="embedded-job",
        role="Firmware / Embedded Software Engineer",
        job_title="Firmware / Embedded Software Engineer",
        jd_text=EMBEDDED_JD,
        experience_required="5-7 years",
        required_skills="C, Firmware, Embedded Hardware, Microcontrollers, Debugging",
    )

    result = _rescore_candidate_from_stored_fields(candidate, job)

    assert result["detected_role_family"] == "embedded_firmware"
    assert candidate.relevant_experience_years >= 2
    assert "QA JD" not in " ".join(item["reason"] for item in result["score_caps_applied"])


@pytest.mark.parametrize(
    ("title", "text", "expected_qa"),
    [
        ("Firmware Engineer", EMBEDDED_JD, False),
        ("QA Automation Engineer", QA_JD, True),
        ("Java Backend Engineer", "Build Java Spring Boot REST APIs and SQL services.", False),
        ("Data Engineer", "Build Python SQL ETL pipelines and data warehouses.", False),
    ],
)
def test_family_specific_qa_rules_never_leak(title, text, expected_qa):
    profile = build_jd_profile(text, {"role": title})
    assert _is_qa_target(profile) is expected_qa
