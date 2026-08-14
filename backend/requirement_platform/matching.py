from __future__ import annotations

import json

from backend.requirement_platform.models import ProfileTaxonomyValue, RequirementSkill, TrustScore


def _normalized(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _taxonomy(db, profile_id: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in db.query(ProfileTaxonomyValue).filter(ProfileTaxonomyValue.profile_id == profile_id).all():
        result.setdefault(row.taxonomy, set()).add(_normalized(row.value))
    return result


def _skills(db, requirement_id: str) -> set[str]:
    return {
        _normalized(row.skill_normalized or row.skill)
        for row in db.query(RequirementSkill).filter(RequirementSkill.requirement_id == requirement_id).all()
    }


def match_requirement_to_profile(db, requirement, profile) -> dict:
    taxonomy = _taxonomy(db, profile.id)
    requirement_skills = _skills(db, requirement.id)
    specializations = taxonomy.get("specialization", set())
    industries = taxonomy.get("industry", set())
    markets = taxonomy.get("market", set())
    employment_types = taxonomy.get("employment_type", set())

    score = 0.0
    reasons: list[str] = []
    skill_overlap = requirement_skills & specializations
    if requirement_skills:
        skill_ratio = len(skill_overlap) / len(requirement_skills)
        score += 35 * min(skill_ratio * 1.5, 1)
        if skill_overlap:
            reasons.append(f"Specialization overlap: {', '.join(sorted(skill_overlap)[:3])}")
    if _normalized(requirement.industry) in industries:
        score += 15
        reasons.append(f"Industry experience: {requirement.industry}")
    if _normalized(requirement.country) in markets or _normalized(requirement.country) == _normalized(profile.country):
        score += 15
        reasons.append(f"Market match: {requirement.country}")
    if _normalized(requirement.employment_type) in employment_types:
        score += 10
        reasons.append(f"Employment type experience: {requirement.employment_type}")
    if profile.availability == "available_now":
        score += 10
        reasons.append("Available now")
    elif profile.availability == "limited_availability":
        score += 5
    if profile.status == "verified":
        score += 10
        reasons.append("HireScore Verified")
    trust = db.query(TrustScore).filter(TrustScore.profile_id == profile.id).first()
    if trust:
        score += min(max(trust.score, 0), 100) * 0.05
        if trust.score >= 80:
            reasons.append(f"Trust Score {trust.score}")
    return {"match_percentage": round(min(score, 100)), "reasons": reasons[:5] or ["General profile compatibility"]}


def safe_json(value: str | None, fallback):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback
