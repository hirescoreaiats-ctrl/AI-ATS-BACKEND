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
    "experience_relevance_label": "experience_relevance_label",
}

JSON_INTELLIGENCE_FIELDS = [
    "missing_core_skill_groups",
    "parser_quality_flags",
    "experience_evidence",
    "experience_warnings",
    "score_caps_applied",
    "recruiter_flags",
    "risk_flags",
    "scoring_breakdown",
    "jd_profile_json",
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
        "experience_relevance_label": getattr(candidate, "experience_relevance_label", None),
        "experience_evidence": from_json_text(getattr(candidate, "experience_evidence", None), []),
        "experience_warnings": from_json_text(getattr(candidate, "experience_warnings", None), []),
        "score_caps_applied": from_json_text(getattr(candidate, "score_caps_applied", None), []),
        "recruiter_flags": from_json_text(getattr(candidate, "recruiter_flags", None), []),
        "risk_flags": from_json_text(getattr(candidate, "risk_flags", None), []),
        "scoring_breakdown": scoring_breakdown,
        "stale_score": stale_score,
        "stale_score_delta": round(score_delta, 2),
        "current_evidence_score": evidence_score,
        "jd_profile_json": from_json_text(getattr(candidate, "jd_profile_json", None), {}),
    }
