import pytest

from backend.experience_engine import looks_like_technical_entity_name, process_experience
from backend.services.canonical_capabilities import capability_evidence
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.parsing_service import _clean_experience_records, _looks_like_bad_company, parse_resume_enterprise
from backend.services.resume_quality_gate import build_parser_quality_report
from backend.services.recruiter_decision import enrich_recruiter_decision
from backend.services.scoring_service import score_candidate
from backend.services.taxonomy import known_skills_in_text


EMBEDDED_JD = """
Firmware / Embedded Software Engineer. Experience: 5-7 Years.
Required: C, embedded firmware, microcontrollers, embedded hardware, debugging,
hardware/software integration, electronic schematics and laboratory equipment.
Preferred: PIC32, PIC18, Freescale, SiLabs, Python, I2C, UART, SPI,
manufacturing testing, RF systems, Git and Jira.
"""


def _evidence(skill, text, source="work"):
    parsed = {
        "key_skills": [text] if source == "skills" else [],
        "experience": [{"role": "Embedded Firmware Engineer", "description": text}] if source == "work" else [],
        "projects": [{"name": "Embedded project", "description": text}] if source == "project" else [],
    }
    return capability_evidence(skill, parsed, text, "embedded_firmware")


@pytest.mark.parametrize("platform", ["STM32F4", "NXP MCU", "ESP32", "AVR", "PIC32", "ARM Cortex-M4"])
def test_contextual_mcu_platforms_infer_microcontrollers(platform):
    item = _evidence("Microcontrollers", f"Developed RTOS firmware on {platform} boards using SPI.")
    assert item["evidence_state"] == "MATCHED"
    assert item["canonical_capability"] == "Microcontrollers"
    assert platform.split()[0].lower() in item["original_evidence"].lower()


def test_generic_arm_processor_does_not_blindly_infer_microcontroller():
    assert _evidence("Microcontrollers", "Deployed a web service on an ARM application processor.") is None


@pytest.mark.parametrize(
    ("skill", "text"),
    [
        ("Embedded Hardware", "Developed MCU firmware and completed board bring-up on a custom PCB."),
        ("Hardware/Software Integration", "Integrated firmware with board peripherals and hardware drivers."),
        ("Debugging", "Performed root-cause analysis and fixed firmware validation failures."),
        ("RF Systems", "Debugged an RF transceiver and broadband radio system."),
        ("Manufacturing Test", "Built factory testing fixtures and production diagnostic tools."),
        ("Continuation Engineering", "Refactored an inherited legacy C firmware codebase."),
        ("Electronic Schematics", "Developed schematics and designed printed circuit boards."),
        ("Laboratory Equipment", "Used an oscilloscope, multimeter and logic analyzer during bring-up."),
    ],
)
def test_professional_capability_normalization(skill, text):
    item = _evidence(skill, text)
    assert item["evidence_state"] == "MATCHED"
    assert item["source"] == "work_experience"


def test_three_state_evidence_skills_verify_professional_matches_and_absence_missing():
    skills_only = _evidence("Laboratory Equipment", "Oscilloscope", source="skills")
    professional = _evidence("Laboratory Equipment", "Used an oscilloscope to debug board signals.")
    absent = _evidence("Laboratory Equipment", "Built REST APIs in Python.")
    assert skills_only["evidence_state"] == "VERIFY"
    assert professional["evidence_state"] == "MATCHED"
    assert absent is None


def test_one_statement_supports_multiple_justified_capabilities():
    text = "Developed firmware in an RTOS environment on STM32 microcontrollers using I2C, SPI and UART peripherals."
    for skill in ["Embedded Firmware", "Microcontrollers", "Peripheral Interfaces", "Hardware/Software Integration"]:
        assert _evidence(skill, text)["evidence_state"] == "MATCHED"


def test_multilingual_embedded_terms_preserve_capability_meaning():
    text = "Engenheiro de Hardware e Firmware: sistemas embarcados, microcontroladores, desenvolvimento de esquemático e placas de circuito impresso."
    assert _evidence("Embedded Firmware", text)["evidence_state"] == "MATCHED"
    assert _evidence("Microcontrollers", text)["evidence_state"] == "MATCHED"
    assert _evidence("Electronic Schematics", text)["evidence_state"] == "MATCHED"


@pytest.mark.parametrize("token", ["LIN", "CAN", "UART", "SPI", "I2C", "RTOS", "OEM", "ODM", "STM32", "AUTOSAR"])
def test_technical_entities_are_not_employers(token):
    assert looks_like_technical_entity_name(token)
    assert _looks_like_bad_company(token)


def test_latest_company_ignores_vendor_protocol_responsibility_tokens():
    result = process_experience([
        {"company_name": "Microsoft", "role": "Senior Software Engineer", "start_date": "Jan 2023", "end_date": "Present", "description": "Worked with OEM and ODM vendors using LIN."},
        {"company_name": "ODM", "role": "Engineer", "start_date": "Jan 2024", "end_date": "Dec 2024", "description": "ODM support responsibility."},
    ])
    assert result["last_company_name"] == "Microsoft"


def test_duplicate_work_entries_are_removed_but_simultaneous_distinct_roles_survive():
    records = _clean_experience_records([
        {"company_name": "Acme Systems", "role": "Firmware Engineer", "start_date": "Jan 2022", "end_date": "Dec 2023", "description": "Developed STM32 firmware and drivers."},
        {"company_name": "Acme System", "role": "Embedded Firmware Engineer", "start_date": "Jan 2022", "end_date": "Dec 2023", "description": "Developed STM32 firmware and drivers."},
        {"company_name": "Beta Labs", "role": "Consultant", "start_date": "Jan 2022", "end_date": "Dec 2023", "description": "Concurrent embedded consulting engagement."},
    ])
    assert len(records) == 2
    assert {item["company_name"] for item in records} == {"Acme Systems", "Beta Labs"}


def test_overlapping_periods_do_not_inflate_calendar_experience():
    result = process_experience([
        {"company_name": "Acme Systems", "role": "Engineer", "start_date": "Jan 2020", "end_date": "Dec 2022"},
        {"company_name": "Beta Labs", "role": "Consultant", "start_date": "Jan 2021", "end_date": "Dec 2023"},
    ])
    assert result["total_experience_years"] == pytest.approx(4.0, abs=0.03)


def _score(role, jd, skills, years, *, parser=90, location="India"):
    profile = build_jd_profile(jd, {"role": role, "location": "India"}, skills)
    text = f"Developed and maintained {' '.join(skills)} systems with professional responsibility."
    parsed = {
        "designation": role,
        "current_title": role,
        "location": location,
        "key_skills": skills,
        "experience": [{"company_name": "Acme Systems", "role": role, "description": text}],
        "projects": [],
        "education": [{"degree": "Bachelor"}],
        "total_experience_years": years,
        "relevant_experience_years": years,
        "direct_relevant_experience_years": years,
        "role_relevance_score": 92,
        "parser_quality_score": parser,
        "parser_quality_action": "manual_review_required" if parser < 45 else "auto_rank_ok",
        "resume_quality_score": 90,
        "semantic_score": 0.8,
    }
    result = score_candidate(parsed, jd, profile["must_have_skills"], {"role": role, "location": "India"}, text, jd_profile=profile)
    return enrich_recruiter_decision(result, profile, parsed)


@pytest.mark.parametrize(
    ("role", "jd", "skills"),
    [
        ("Firmware Engineer", "Firmware Engineer. Experience 5-7 years. Required C, firmware, microcontrollers and debugging.", ["C", "Firmware", "Microcontrollers", "Debugging"]),
        ("QA Automation Engineer", "QA Automation Engineer. Experience 5-7 years. Required Selenium, API Testing, SQL and Jira.", ["Selenium", "API Testing", "SQL", "Jira"]),
        ("Backend Developer", "Backend Developer. Experience 5-7 years. Required Python, FastAPI, SQL and REST API.", ["Python", "FastAPI", "SQL", "REST API"]),
        ("Data Engineer", "Data Engineer. Experience 5-7 years. Required Python, SQL, ETL and Data Warehouse.", ["Python", "SQL", "ETL", "Data Warehouse"]),
    ],
)
def test_global_above_range_seniority_has_negligible_score_impact(role, jd, skills):
    within = _score(role, jd, skills, 6)
    above = _score(role, jd, skills, 12)
    assert abs(within["technical_fit_score"] - above["technical_fit_score"]) <= 0.5
    assert "over_jd_experience_range" in above["risk_flags"]
    assert not above["score_caps_applied"]


def test_parser_confidence_changes_decision_certainty_not_technical_score():
    high = _score("Backend Developer", "Backend Developer. Required Python, FastAPI and SQL.", ["Python", "FastAPI", "SQL"], 4, parser=90)
    low = _score("Backend Developer", "Backend Developer. Required Python, FastAPI and SQL.", ["Python", "FastAPI", "SQL"], 4, parser=30)
    assert high["technical_fit_score"] == low["technical_fit_score"]
    assert low["shortlist_decision"] == "Needs Review"


def test_location_changes_eligibility_context_not_frontend_technical_score():
    jd = "Frontend Developer. Experience 1-3 years. India onsite. Required React, JavaScript, HTML, CSS and REST API."
    india = _score("Frontend Developer", jd, ["React", "JavaScript", "HTML", "CSS", "REST API"], 2, location="Noida, India")
    foreign = _score("Frontend Developer", jd, ["React", "JavaScript", "HTML", "CSS", "REST API"], 2, location="London, UK")
    assert india["technical_fit_score"] == foreign["technical_fit_score"]
    assert foreign["location_fit"]["flag"] == "location_budget_mismatch"


def test_decision_state_has_one_canonical_source():
    result = _score("Backend Developer", "Backend Developer. Required Python, FastAPI and SQL.", ["Python", "FastAPI", "SQL"], 4)
    canonical = result["canonical_decision"]
    assert result["shortlist_decision"] == canonical["decision"]
    assert result["recommendation"] == canonical["recommendation"]
    assert result["fit_band"] == canonical["fit_band"]


def test_jd_requirement_tiers_and_soft_experience_band_are_explicit():
    profile = build_jd_profile(EMBEDDED_JD, {"role": "Firmware / Embedded Software Engineer"})
    assert profile["requirement_tiers"]["preferred"]
    assert profile["experience_range_is_hard"] is False
    assert all(not item["hard"] for item in profile["eligibility_constraints"] if item["type"].startswith("experience"))


def test_portuguese_parser_recovers_embedded_role_dates_and_not_about_heading_name():
    text = """
Sobre Mim
Olá! Eu sou Maria Silva Santos. Trabalho com eletrônica.
Experiência Profissional
Engenheiro de Hardware e Firmware em Sistemas Alfa Ltda
Fev, 2020 - Atual
Desenvolvimento de hardware e firmware para sistemas embarcados com microcontroladores ESP32.
Educação
Engenharia Eletrônica
"""
    parsed = parse_resume_enterprise(text, ai_parse_override={})
    assert parsed["full_name"] == "Maria Silva Santos"
    assert parsed["experience"]
    assert parsed["experience"][0]["company_name"] == "Sistemas Alfa Ltda"
    assert "Firmware" in parsed["experience"][0]["role"]


def test_training_responsibility_does_not_cap_consultant_as_internship():
    parsed = {
        "total_experience_years": 6,
        "experience": [{
            "company_name": "Embedded Systems Ltd",
            "role": "Consultant",
            "start_date": "Jan 2020",
            "end_date": "Jan 2026",
            "description": "Developed embedded Linux BSPs, firmware and device drivers; also delivered in-house training.",
        }],
    }
    profile = build_jd_profile("Firmware Engineer. Required embedded firmware, BSP and device drivers.", {"role": "Firmware Engineer"})
    result = estimate_relevant_experience_v2(parsed, "", profile)
    assert result["relevant_experience_years"] > 0.35


def test_extracted_mcu_never_finishes_as_missing_microcontrollers():
    assert "Microcontrollers" in known_skills_in_text("STM32, NXP MCU, ARM Cortex-M and FreeRTOS firmware")


def test_long_embedded_history_uses_evidence_across_varied_titles():
    profile = build_jd_profile(EMBEDDED_JD, {"role": "Firmware / Embedded Software Engineer"})
    parsed = {
        "total_experience_years": 18,
        "experience": [
            {"company_name": "Alpha Devices", "role": "Product Engineer", "start_date": "Jan 2006", "end_date": "Dec 2011", "description": "Developed bare-metal C firmware, BSPs and device drivers for ARM microcontrollers."},
            {"company_name": "Beta Radio", "role": "Systems Engineer", "start_date": "Jan 2012", "end_date": "Dec 2017", "description": "Built RTOS firmware, board bring-up diagnostics, I2C and SPI drivers for RF products."},
            {"company_name": "Gamma Networks", "role": "Technical Lead", "start_date": "Jan 2018", "end_date": "Dec 2023", "description": "Led embedded Linux, firmware, hardware debugging and oscilloscope validation for fiber networking."},
        ],
    }
    result = estimate_relevant_experience_v2(parsed, "", profile)
    assert result["direct_relevant_experience_years"] >= 15
    assert result["relevant_experience_years"] >= 15
    assert result["recent_relevant_experience_years"] > 2


def test_visual_studio_and_ddk_fragment_is_not_an_employer():
    assert looks_like_technical_entity_name("Visual Studio 2022, Windows DDK")
    result = process_experience([{"company_name": "Visual Studio 2022, Windows DDK", "role": "Firmware Engineer", "start_date": "2022", "end_date": "2024"}])
    assert result["last_company_name"] is None
    assert result["last_company_needs_review"] is True


def test_hard_location_and_onsite_are_separate_mandatory_checks():
    jd = """Firmware Engineer. Experience 5-7 years. Must be local to Los Angeles and willing to work onsite.
    Required Qualifications: Strong C programming, embedded firmware, microcontrollers and debugging."""
    profile = build_jd_profile(jd, {"role": "Firmware Engineer"})
    text = "Developed C firmware for STM32 microcontrollers and debugged boards using an oscilloscope."
    parsed = {
        "designation": "Firmware Engineer", "location": "Opelika, Alabama", "resume_text": text,
        "key_skills": ["C", "Firmware", "STM32", "Debugging"],
        "experience": [{"company_name": "Device Labs", "role": "Firmware Engineer", "description": text}],
        "total_experience_years": 6, "relevant_experience_years": 6, "direct_relevant_experience_years": 6,
        "role_relevance_score": 95, "parser_quality_score": 92, "semantic_score": 0.9,
    }
    result = score_candidate(parsed, jd, profile["must_have_skills"], {"role": "Firmware Engineer"}, text, jd_profile=profile)
    checks = {item["type"]: item for item in result["mandatory_checks"]}
    assert result["technical_fit_score"] >= 70
    assert checks["location"]["status"] == "FAIL"
    assert checks["work_mode"]["status"] == "UNKNOWN"
    assert result["shortlist_decision"] == "Needs Review"
    assert "Mandatory Constraint" in result["overall_recruiter_status"]


def test_severe_overqualification_changes_recruiter_fit_not_technical_fit():
    jd = "Firmware Engineer. Experience 5-7 years. Required Qualifications: C programming, firmware, microcontrollers and debugging."
    profile = build_jd_profile(jd, {"role": "Firmware Engineer"})
    text = "Developed C firmware for STM32 microcontrollers and debugged embedded hardware."
    parsed = {
        "designation": "Principal Firmware Engineer", "key_skills": ["C", "Firmware", "STM32", "Debugging"],
        "experience": [{"company_name": "Device Labs", "role": "Principal Firmware Engineer", "description": text}],
        "total_experience_years": 20, "relevant_experience_years": 20, "direct_relevant_experience_years": 20,
        "role_relevance_score": 96, "parser_quality_score": 95, "semantic_score": 0.9,
    }
    result = score_candidate(parsed, jd, profile["must_have_skills"], {"role": "Firmware Engineer"}, text, jd_profile=profile)
    assert result["technical_fit_score"] > result["overall_recruiter_fit_score"]
    assert result["experience_alignment"] == "Severely above target"
    assert result["seniority_score_adjustment"] == -12
    assert "seniority_review" in result["recruiter_flags"]


def test_coverage_uses_core_groups_not_only_three_generic_hits():
    profile = build_jd_profile(EMBEDDED_JD, {"role": "Firmware / Embedded Software Engineer"})
    text = "Used Python, Git and validation tooling."
    parsed = {
        "designation": "Software Engineer", "key_skills": ["Python", "Git", "Validation"],
        "experience": [{"company_name": "Software Co", "role": "Software Engineer", "description": text}],
        "total_experience_years": 6, "relevant_experience_years": 1, "direct_relevant_experience_years": 0,
        "role_relevance_score": 25, "parser_quality_score": 90, "semantic_score": 0.3,
    }
    result = score_candidate(parsed, EMBEDDED_JD, profile["must_have_skills"], {"role": profile["role_title"]}, text, jd_profile=profile)
    assert result["skill_match_percent"] < 100
    assert result["requirement_coverage"]["overall_weighted_percent"] < 100


def test_overlapping_relevant_roles_do_not_double_count_relevant_tenure():
    profile = build_jd_profile("Firmware Engineer. Required embedded firmware and microcontrollers.", {"role": "Firmware Engineer"})
    parsed = {
        "total_experience_years": 4,
        "experience": [
            {"company_name": "Alpha", "role": "Firmware Engineer", "start_date": "Jan 2020", "end_date": "Dec 2022", "description": "Developed STM32 embedded firmware."},
            {"company_name": "Beta", "role": "Embedded Consultant", "start_date": "Jan 2021", "end_date": "Dec 2023", "description": "Developed ESP32 firmware and device drivers."},
        ],
    }
    result = estimate_relevant_experience_v2(parsed, "", profile)
    assert result["relevant_experience_years"] == pytest.approx(4.0, abs=0.05)
    assert result["direct_relevant_experience_years"] <= 4.05


def test_capability_evidence_preserves_role_company_and_source_snippet():
    parsed = {"experience": [{"company_name": "CoachComm", "role": "Senior Product Engineer - Firmware", "start_date": "2023", "end_date": "Present", "description": "Root cause analysis of I2C issues during board bring-up."}]}
    item = capability_evidence("Peripheral Interfaces", parsed, "", "embedded_firmware")
    assert item["evidence_state"] == "MATCHED"
    assert item["role"] == "Senior Product Engineer - Firmware"
    assert item["company"] == "CoachComm"
    assert "I2C" in item["evidence_text"]


def test_ai_parser_failure_preserves_fallback_fields_but_reduces_confidence(monkeypatch):
    text = """Jane Engineer\njane@example.com\nProfessional Experience\nFirmware Engineer, Acme Devices\nJan 2020 - Dec 2024\nDeveloped STM32 C firmware and SPI drivers.\nEducation\nBachelor of Engineering"""
    monkeypatch.setattr("backend.services.parsing_service.parse_resume", lambda _text: {"__ai_parse_status": "failed api error"})
    parsed = parse_resume_enterprise(text)
    report = build_parser_quality_report(text, parsed, {"total_experience_years": 5})
    assert parsed["ai_parse_status"] == "failed api error"
    assert parsed["experience"]
    assert parsed["email"] == "jane@example.com"
    assert any(item["code"] == "ai_parse_fallback" for item in report["parser_quality_flags"])
    assert report["parser_quality_score"] < parsed["resume_quality_score"]
