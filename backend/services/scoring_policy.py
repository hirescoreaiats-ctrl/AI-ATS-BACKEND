from __future__ import annotations

import re

from backend.services.canonical_capabilities import capability_evidence


NON_TECHNICAL_CAP_RE = re.compile(
    r"\b(?:overqualif|above\s+(?:the\s+)?(?:jd|target|experience)|below\s+(?:the\s+)?(?:jd|target|experience)|"
    r"experience\s+(?:range|band|minimum|gap)|senior[-\s]?level|parser\s+(?:quality|confidence)|"
    r"location|onsite|on[-\s]?site|salary|budget|work\s+authori[sz]ation|no\s+valid\s+professional\s+work\s+dates)\b",
    re.I,
)

INVALID_DOCUMENT_RE = re.compile(r"\b(?:not\s+a\s+resume|job\s+description\s+rather|non[-\s]?human|invalid\s+document)\b", re.I)
SPECIALIZED_ROLE_FAMILIES = {
    "applied_ml_engineer",
    "product_software_architect",
    "m365_migration_sme",
    "aml_transaction_monitoring",
}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def apply_global_scoring_policy(result: dict, jd_profile: dict | None, parsed: dict | None) -> dict:
    """Keep technical capability independent from confidence and recruiter context.

    Family scorers may still record guardrail findings, but non-technical caps do
    not alter the technical score. Missing capabilities are already represented
    continuously by weighted coverage and evidence-depth components.
    """
    result = result or {}
    jd_profile = jd_profile or {}
    parsed = parsed or {}
    relevant_years = _number(parsed.get("relevant_experience_years"))
    min_years = _number(jd_profile.get("min_experience_years"))
    max_years = _number(jd_profile.get("max_experience_years"))
    recruiter_flags = result.setdefault("recruiter_flags", [])
    risk_flags = result.setdefault("risk_flags", [])
    if max_years and relevant_years > max_years:
        if "over_experienced" not in recruiter_flags:
            recruiter_flags.append("over_experienced")
        if "over_jd_experience_range" not in risk_flags:
            risk_flags.append("over_jd_experience_range")
    elif min_years and relevant_years < min_years:
        if "under_experienced" not in recruiter_flags:
            recruiter_flags.append("under_experienced")
        if "below_jd_experience_range" not in risk_flags:
            risk_flags.append("below_jd_experience_range")
    missing = list(result.get("missing_skills") or [])
    verification = list(result.get("verification_required_skills") or [])
    evidence_map = result.setdefault("skill_evidence", {})
    contradiction_flags = []
    for required in list(missing):
        inferred = capability_evidence(required, parsed, str(parsed.get("resume_text") or ""), str(jd_profile.get("role_family") or "other"))
        if not inferred:
            continue
        missing.remove(required)
        if inferred.get("status") == "verify" and required not in verification:
            verification.append(required)
        evidence_map[required] = inferred
        contradiction_flags.append(f"resolved_false_missing:{required}")
    if contradiction_flags:
        result["missing_skills"] = missing
        result["verification_required_skills"] = verification
        result.setdefault("consistency_flags", []).extend(contradiction_flags)
    original_final = _number(result.get("final_score"))
    before_caps = _number(result.get("final_score_before_caps"), original_final)
    caps = [item for item in result.get("score_caps_applied") or [] if isinstance(item, dict)]

    active_caps = []
    review_findings = list(result.get("review_findings") or [])
    for item in caps:
        reason = str(item.get("reason") or "")
        if INVALID_DOCUMENT_RE.search(reason):
            active_caps.append(item)
        else:
            review_findings.append({
                "category": "recruiter_context" if NON_TECHNICAL_CAP_RE.search(reason) else "capability_gap",
                "reason": reason,
                "legacy_cap": item.get("cap"),
                "score_effect": 0,
            })

    technical_score = before_caps
    if active_caps:
        technical_score = min(technical_score, *[_number(item.get("cap"), technical_score) for item in active_caps])
    technical_score = round(max(0, min(100, technical_score)), 2)

    # Older generic scoring embedded a penalty before final_score_before_caps.
    # Restore it; an above-range flag is still retained for recruiter context.
    embedded_over_penalty = _number(result.get("overqualified_penalty"))
    if embedded_over_penalty:
        technical_score = round(min(100, technical_score + min(0.5, embedded_over_penalty)), 2)

    # Role-family identity is capability evidence, so a genuine cross-family
    # mismatch receives a proportional adjustment rather than a ceiling.  Do
    # not apply it when embedded professional evidence itself proves the role.
    alignment = str(result.get("role_alignment") or "").lower()
    mandatory = _number(result.get("mandatory_skill_coverage") or result.get("skill_match_percent"))
    evidence_strength = _number(
        result.get("project_strength_score")
        or (result.get("scoring_breakdown") or {}).get("evidence_strength")
        or (result.get("scoring_breakdown") or {}).get("project_work_strength")
    )
    embedded_proven = (
        str(jd_profile.get("role_family") or "").lower() == "embedded_firmware"
        and mandatory >= 50
        and evidence_strength >= 45
    )
    alignment_factor = 1.0
    if str(jd_profile.get("role_family") or "").lower() not in SPECIALIZED_ROLE_FAMILIES and not embedded_proven:
        alignment_factor = {"mismatch": 0.75, "weak": 0.85, "adjacent": 0.85, "transferable": 0.95}.get(alignment, 1.0)
    if alignment_factor < 1:
        adjusted = round(technical_score * alignment_factor, 2)
        review_findings.append({
            "category": "role_family_alignment",
            "reason": f"{alignment.title()} role-family alignment; capability score adjusted proportionally.",
            "score_effect": round(adjusted - technical_score, 2),
        })
        technical_score = adjusted

    result.update({
        "technical_fit_score": technical_score,
        "final_score": technical_score,
        "rank_score": technical_score,
        "technical_score_before_policy": before_caps,
        "seniority_score_adjustment": 0.0,
        "location_score_adjustment": 0.0,
        "parser_confidence_score_adjustment": 0.0,
        "score_caps_applied": active_caps,
        "applied_caps": active_caps,
        "review_findings": review_findings,
        "consistency_flags": result.get("consistency_flags") or [],
    })
    breakdown = result.setdefault("scoring_breakdown", {})
    if isinstance(breakdown, dict):
        breakdown.update({
            "technical_fit_score": technical_score,
            "seniority_score_adjustment": 0.0,
            "location_score_adjustment": 0.0,
            "parser_confidence_score_adjustment": 0.0,
            "review_findings": review_findings,
            "score_caps_applied": active_caps,
        })
    return result
