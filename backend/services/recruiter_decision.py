from __future__ import annotations

import re
from typing import Any

from backend.services.taxonomy import equivalent_skill, normalize_skill_list


CRITICAL_LINE_RE = re.compile(
    r"\b(must(?:\s+have)?|mandatory|critical|non[-\s]?negotiable)\b",
    re.I,
)

SPECIALIZED_ROLE_FAMILIES = {
    "applied_ml_engineer",
    "product_software_architect",
    "m365_migration_sme",
    "aml_transaction_monitoring",
}


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n|]+", value) if item.strip()]
    return [value]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _append_unique(items: list, values: list) -> None:
    seen = {str(item).strip().lower() for item in items if str(item).strip()}
    for value in values or []:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            items.append(text)
            seen.add(key)


def _label_list(value: Any, limit: int = 5) -> list[str]:
    labels = []
    for item in _as_list(value):
        if isinstance(item, dict):
            label = item.get("group") or item.get("name") or item.get("label") or item.get("skill") or item.get("reason")
            if not label and item.get("matched"):
                label = ", ".join(str(skill) for skill in _as_list(item.get("matched"))[:3])
            if not label:
                label = ", ".join(f"{key}: {val}" for key, val in list(item.items())[:2])
        else:
            label = item
        text = str(label or "").strip()
        if text:
            labels.append(text)
        if len(labels) >= limit:
            break
    return labels


def _skill_matches(candidate: str, required: str) -> bool:
    return candidate.lower() == required.lower() or equivalent_skill(candidate, required)


def extract_critical_must_have(jd_profile: dict | None) -> list[str]:
    jd_profile = jd_profile or {}
    explicit = normalize_skill_list(_as_list(jd_profile.get("critical_must_have")))
    if explicit:
        return explicit

    must_have = normalize_skill_list(jd_profile.get("must_have_skills") or jd_profile.get("must_have") or [])
    hard_lines = _as_list(jd_profile.get("hard_requirements"))
    critical = []
    for line in hard_lines:
        line_text = str(line or "")
        if not CRITICAL_LINE_RE.search(line_text):
            continue
        for skill in must_have:
            if re.search(r"\b" + re.escape(skill).replace(r"\ ", r"\s+") + r"\b", line_text, re.I):
                _append_unique(critical, [skill])

    if critical:
        return critical

    return critical[:5]


def _critical_skill_state(score_data: dict, critical_skills: list[str]) -> tuple[list[str], list[str]]:
    evidence = score_data.get("skill_evidence") or {}
    matched_skills = normalize_skill_list(
        (score_data.get("direct_matched_skills") or [])
        + (score_data.get("transferable_skills") or [])
        + (score_data.get("matched_skills") or [])
    )
    missing_skills = normalize_skill_list(score_data.get("missing_skills") or [])
    matched = []
    missing = []

    for required in critical_skills:
        evidence_item = evidence.get(required) or next(
            (
                item
                for skill, item in evidence.items()
                if _skill_matches(str(skill), required) or _skill_matches(required, str(skill))
            ),
            {},
        )
        level = str(evidence_item.get("evidence_level") or "").lower()
        status = str(evidence_item.get("status") or "").lower()
        weight = _safe_float(evidence_item.get("weight"))
        has_real_evidence = level in {"professional_strong", "professional_weak", "project_strong", "project_weak"}
        has_match = any(_skill_matches(skill, required) for skill in matched_skills)
        is_missing = (
            any(_skill_matches(skill, required) for skill in missing_skills)
            or status in {"missing", "weak", "training_only"}
            or level in {"missing", "keyword_only", "skills_section_only", "employer_name_only", "certification_or_training_only"}
            or (not has_match and weight <= 0)
        )
        if has_real_evidence or (has_match and not is_missing and weight >= 0.5):
            _append_unique(matched, [required])
        else:
            _append_unique(missing, [required])

    return matched, missing


def _cap_score(score_data: dict, limit: float, reason: str, flag: str, risk: str | None = None) -> None:
    score = _safe_float(score_data.get("final_score"))
    if score > limit:
        score_data["final_score"] = round(limit, 2)
        score_data["rank_score"] = round(min(_safe_float(score_data.get("rank_score"), limit), limit), 2)
    caps = score_data.setdefault("score_caps_applied", [])
    if isinstance(caps, list) and not any(item.get("reason") == reason for item in caps if isinstance(item, dict)):
        caps.append({"cap": limit, "reason": reason})
    score_data["applied_caps"] = caps
    recruiter_flags = score_data.setdefault("recruiter_flags", [])
    risk_flags = score_data.setdefault("risk_flags", [])
    if isinstance(recruiter_flags, list):
        _append_unique(recruiter_flags, [flag])
    if risk and isinstance(risk_flags, list):
        _append_unique(risk_flags, [risk])


def _has_strong_group_evidence(score_data: dict) -> bool:
    breakdown = score_data.get("scoring_breakdown") or {}
    mandatory_status = breakdown.get("mandatory_group_status") or {}
    if _as_list(mandatory_status.get("strong")):
        return True

    for key, groups in breakdown.items():
        if not str(key).endswith("_group_scores") or not isinstance(groups, dict):
            continue
        strong_count = 0
        for group in groups.values():
            if not isinstance(group, dict):
                continue
            evidence_level = str(group.get("evidence_level") or "").lower()
            source = str(group.get("source") or "").lower()
            score = _safe_float(group.get("score"))
            if group.get("strong") or evidence_level == "professional_strong" or (score >= 80 and source in {"work_experience", "title"}):
                strong_count += 1
        if strong_count >= 2:
            return True
    return False


def _decision_for(score_data: dict, missing_critical: list[str]) -> tuple[str, str, str]:
    final_score = _safe_float(score_data.get("final_score"))
    confidence = _safe_float(score_data.get("confidence_score"), 70)
    caps = score_data.get("score_caps_applied") or []
    risk_flags = {str(item).lower() for item in (score_data.get("risk_flags") or [])}
    recruiter_flags = {str(item).lower() for item in (score_data.get("recruiter_flags") or [])}
    cap_text = " ".join(str(item.get("reason") or "") for item in caps if isinstance(item, dict)).lower()
    severe_cap = bool(re.search(r"missing critical|wrong role|parser quality|below 1 year|non-direct|mismatch|cannot exceed", cap_text))
    parser_low = "parser_quality" in risk_flags or "parser_manual_review" in recruiter_flags
    evidence_strength = _safe_float(
        score_data.get("project_strength_score")
        or (score_data.get("scoring_breakdown") or {}).get("project_work_strength")
        or (score_data.get("scoring_breakdown") or {}).get("evidence_strength")
    )

    if parser_low or confidence < 45:
        return "Needs Review", "Parser confidence is low; recruiter validation is required.", "in_review"
    if final_score < 55:
        return "Reject", "Score is below the recruiter fit threshold for this JD.", "rejected"
    if missing_critical and final_score < 70:
        return "Maybe", "Candidate is missing critical must-have evidence; consider only if transferable background matters.", "in_review"
    if final_score >= 85 and not missing_critical and not severe_cap and evidence_strength >= 55 and confidence >= 65:
        return "Strong Match", "High JD fit with strong evidence and no severe recruiter caps.", "shortlisted"
    if final_score >= 70 and not severe_cap:
        return "Good Match", "Most JD requirements are covered with acceptable confidence.", "shortlisted"
    if final_score >= 55:
        return "Maybe", "Partial or transferable fit; recruiter review is recommended.", "in_review"
    return "Reject", "Candidate misses too much of the role-critical evidence.", "rejected"


def enrich_recruiter_decision(score_data: dict, jd_profile: dict | None = None, parsed: dict | None = None) -> dict:
    score_data = score_data or {}
    jd_profile = jd_profile or {}
    parsed = parsed or {}

    critical_skills = extract_critical_must_have(jd_profile)
    matched_critical, missing_critical = _critical_skill_state(score_data, critical_skills)
    score_data["critical_must_have"] = critical_skills
    score_data["matched_critical_skills"] = matched_critical
    score_data["missing_critical_skills"] = missing_critical

    role_alignment = str(score_data.get("role_alignment") or (score_data.get("scoring_breakdown") or {}).get("role_alignment") or "").lower()
    relevant_years = _safe_float(parsed.get("relevant_experience_years") or score_data.get("jd_relevant_experience_years"))
    min_years = _safe_float(jd_profile.get("min_experience_years"))
    confidence = _safe_float(score_data.get("confidence_score"), 70)
    parser_action = str(parsed.get("parser_quality_action") or score_data.get("parser_quality_action") or "").lower()
    role_family = str(jd_profile.get("role_family") or score_data.get("detected_role_family") or "").lower()
    mandatory_coverage = _safe_float(score_data.get("mandatory_skill_coverage") or score_data.get("skill_match_percent"))
    core_coverage = _safe_float(score_data.get("core_skill_match_percent"))
    evidence_strength = _safe_float(
        score_data.get("project_strength_score")
        or (score_data.get("scoring_breakdown") or {}).get("project_work_strength")
        or (score_data.get("scoring_breakdown") or {}).get("evidence_strength")
    )
    missing_core_groups = score_data.get("missing_core_skill_groups") or []

    if missing_critical and role_family not in SPECIALIZED_ROLE_FAMILIES:
        transferable_ok = evidence_strength >= 80 and relevant_years >= max(min_years or 0, 1)
        _cap_score(
            score_data,
            75 if transferable_ok else 65,
            "Missing critical must-have skill evidence: " + ", ".join(missing_critical[:4]),
            "missing_critical_must_have",
            "critical_skill_gap",
        )
    if role_alignment in {"mismatch", "weak"}:
        _cap_score(score_data, 55, "Candidate role family does not align with the JD.", "wrong_role_family", "role_family_mismatch")
    elif role_alignment == "transferable":
        if mandatory_coverage < 75 or core_coverage < 65:
            _cap_score(score_data, 68, "Candidate fit is transferable rather than a direct role-family match.", "transferable_role_fit", "role_family_transferable")
    if min_years and relevant_years < min_years and role_family not in SPECIALIZED_ROLE_FAMILIES:
        limit = 60 if relevant_years < max(1, min_years * 0.5) else 72
        _cap_score(score_data, limit, "Relevant experience is below the JD minimum.", "below_jd_minimum_experience", "below_jd_experience_range")
    if parser_action == "manual_review_required" or confidence < 45:
        _cap_score(score_data, 58, "Parser confidence is low; score cannot be trusted for auto-shortlist.", "parser_manual_review", "parser_quality")
    if evidence_strength < 35 and not _has_strong_group_evidence(score_data) and _safe_float(score_data.get("final_score")) >= 70:
        _cap_score(score_data, 78, "No strong project/work evidence was found for the core JD skills.", "weak_core_work_evidence", "evidence_gap")
    if len(missing_core_groups) >= 2 and role_family not in SPECIALIZED_ROLE_FAMILIES:
        _cap_score(score_data, min(65, _safe_float(score_data.get("final_score"), 65)), "Multiple JD core skill groups are missing.", "missing_core_skill_groups", "core_group_gap")

    decision, reason, recommendation = _decision_for(score_data, missing_critical)
    score_data["shortlist_decision"] = decision
    score_data["decision_reason"] = reason
    if not score_data.get("recommendation"):
        score_data["recommendation"] = recommendation
    score_data["fit_band"] = {
        "Strong Match": "strong_match",
        "Good Match": "good_match",
        "Maybe": "maybe",
        "Reject": "reject",
        "Needs Review": "needs_review",
    }.get(decision, score_data.get("fit_band"))
    score_data["cap_reason"] = "; ".join(
        str(item.get("reason") or "")
        for item in score_data.get("score_caps_applied") or []
        if isinstance(item, dict) and item.get("reason")
    )

    strengths = []
    concerns = []
    if matched_critical:
        strengths.append("Critical must-have evidence: " + ", ".join(matched_critical[:5]))
    if score_data.get("matched_core_skill_groups"):
        strengths.append("Matched core groups: " + ", ".join(_label_list(score_data.get("matched_core_skill_groups"), 5)))
    if relevant_years:
        strengths.append(f"{relevant_years:g} years of JD-relevant experience detected.")
    if missing_critical:
        concerns.append("Missing critical must-have evidence: " + ", ".join(missing_critical[:5]))
    if missing_core_groups:
        concerns.append("Missing core groups: " + ", ".join(_label_list(missing_core_groups, 5)))
    if parser_action == "manual_review_required":
        concerns.append("Parser quality requires manual review.")
    if role_alignment in {"mismatch", "weak", "transferable"}:
        concerns.append(score_data.get("role_alignment_reason") or "Role alignment needs recruiter validation.")

    score_data["strengths"] = strengths[:6]
    score_data["concerns"] = concerns[:6]
    score_data["confidence"] = confidence
    score_data["recruiter_explanation"] = reason
    score_data["score_breakdown"] = score_data.get("scoring_breakdown") or {}

    breakdown = score_data.get("scoring_breakdown")
    if isinstance(breakdown, dict):
        breakdown.update({
            "shortlist_decision": decision,
            "decision_reason": reason,
            "critical_must_have": critical_skills,
            "matched_critical_skills": matched_critical,
            "missing_critical_skills": missing_critical,
            "cap_reason": score_data.get("cap_reason"),
        })
    return score_data
