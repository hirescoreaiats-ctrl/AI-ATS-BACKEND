import json


INTELLIGENCE_FIELD_MAP = {
    "relevant_experience_years": "relevant_experience_years",
    "direct_relevant_experience_years": "direct_relevant_experience_years",
    "transferable_experience_years": "transferable_experience_years",
    "senior_role_experience_years": "senior_role_experience_years",
    "role_family": "role_family",
    "role_family_confidence": "role_family_confidence",
    "role_relevance_score": "role_relevance_score",
    "mandatory_skill_coverage": "mandatory_skill_coverage",
    "core_skill_match_percent": "core_skill_match_percent",
    "parser_quality_score": "parser_quality_score",
    "parser_quality_action": "parser_quality_action",
    "profile_extraction_quality": "profile_extraction_quality",
    "experience_relevance_label": "experience_relevance_label",
}

JSON_INTELLIGENCE_FIELDS = [
    "missing_core_skill_groups",
    "parser_quality_flags",
    "raw_parsed_json",
    "safe_parsed_json",
    "field_confidence_json",
    "field_sources_json",
    "text_extraction_quality",
    "experience_evidence",
    "experience_warnings",
    "score_caps_applied",
    "recruiter_flags",
    "risk_flags",
    "scoring_breakdown",
    "jd_profile_json",
    "jd_profile_snapshot_json",
]


def to_json_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def from_json_text(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default if default is not None else value


def apply_resume_intelligence_fields(resume, parsed):
    parsed = parsed or {}
    for attr, key in INTELLIGENCE_FIELD_MAP.items():
        if hasattr(resume, attr) and key in parsed:
            setattr(resume, attr, parsed.get(key))
    for field in JSON_INTELLIGENCE_FIELDS:
        if hasattr(resume, field):
            setattr(resume, field, to_json_text(parsed.get(field)))


def resume_intelligence_payload(candidate):
    scoring_breakdown = from_json_text(getattr(candidate, "scoring_breakdown", None), {})
    experience_evidence = from_json_text(getattr(candidate, "experience_evidence", None), [])
    stored_score = getattr(candidate, "final_score", None)
    evidence_score = None
    if isinstance(scoring_breakdown, dict):
        evidence_score = (
            scoring_breakdown.get("calibrated_final_score")
            or scoring_breakdown.get("current_evidence_score")
            or scoring_breakdown.get("final_score")
        )
    try:
        score_delta = abs(float(stored_score or 0) - float(evidence_score)) if evidence_score is not None else 0
    except (TypeError, ValueError):
        score_delta = 0
    stale_score = bool(evidence_score is not None and score_delta > 10)

    return {
        "relevant_experience_years": getattr(candidate, "relevant_experience_years", None),
        "direct_relevant_experience_years": getattr(candidate, "direct_relevant_experience_years", None),
        "transferable_experience_years": getattr(candidate, "transferable_experience_years", None),
        "senior_role_experience_years": getattr(candidate, "senior_role_experience_years", None),
        "role_family": getattr(candidate, "role_family", None),
        "role_family_confidence": getattr(candidate, "role_family_confidence", None),
        "role_relevance_score": getattr(candidate, "role_relevance_score", None),
        "mandatory_skill_coverage": getattr(candidate, "mandatory_skill_coverage", None),
        "core_skill_match_percent": getattr(candidate, "core_skill_match_percent", None),
        "missing_core_skill_groups": from_json_text(getattr(candidate, "missing_core_skill_groups", None), []),
        "parser_quality_score": getattr(candidate, "parser_quality_score", None),
        "parser_quality_action": getattr(candidate, "parser_quality_action", None),
        "parser_quality_flags": from_json_text(getattr(candidate, "parser_quality_flags", None), []),
        "profile_extraction_quality": getattr(candidate, "profile_extraction_quality", None),
        "raw_parsed_json": from_json_text(getattr(candidate, "raw_parsed_json", None), {}),
        "safe_parsed_json": from_json_text(getattr(candidate, "safe_parsed_json", None), {}),
        "field_confidence_json": from_json_text(getattr(candidate, "field_confidence_json", None), {}),
        "field_sources_json": from_json_text(getattr(candidate, "field_sources_json", None), {}),
        "text_extraction_quality": from_json_text(getattr(candidate, "text_extraction_quality", None), {}),
        "experience_relevance_label": getattr(candidate, "experience_relevance_label", None),
        "experience_evidence": experience_evidence,
        "experience_warnings": from_json_text(getattr(candidate, "experience_warnings", None), []),
        "score_caps_applied": from_json_text(getattr(candidate, "score_caps_applied", None), []),
        "recruiter_flags": from_json_text(getattr(candidate, "recruiter_flags", None), []),
        "risk_flags": from_json_text(getattr(candidate, "risk_flags", None), []),
        "scoring_breakdown": scoring_breakdown,
        "stale_score": stale_score,
        "stale_score_delta": round(score_delta, 2),
        "current_evidence_score": evidence_score,
        "jd_profile_json": from_json_text(getattr(candidate, "jd_profile_json", None), {}),
        "domain_specific_experience_years": scoring_breakdown.get("domain_specific_experience_years"),
        "professional_role_experience_years": scoring_breakdown.get("professional_role_experience_years"),
        "training_or_certification_exposure": scoring_breakdown.get("training_or_certification_exposure"),
        "project_only_exposure": scoring_breakdown.get("project_only_exposure"),
        "current_title": scoring_breakdown.get("current_title") or getattr(candidate, "designation", None),
        "most_relevant_title": scoring_breakdown.get("most_relevant_role"),
        "target_role_alignment": scoring_breakdown.get("target_role_alignment"),
        "seniority_fit": scoring_breakdown.get("seniority_fit") or scoring_breakdown.get("experience_fit"),
        "matched_skill_evidence": scoring_breakdown.get("matched_skill_evidence") or [],
        "missing_or_weak_skills": scoring_breakdown.get("missing_or_weak_skills") or [],
        "jd_aligned_work_evidence": scoring_breakdown.get("jd_aligned_work_evidence") or experience_evidence,
        "jd_aligned_project_evidence": scoring_breakdown.get("jd_aligned_project_evidence") or [],
        "non_jd_projects": scoring_breakdown.get("non_jd_projects") or [],
    }
