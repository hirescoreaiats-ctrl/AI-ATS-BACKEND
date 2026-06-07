from __future__ import annotations

import re

from backend.jd_engine import extract_experience, extract_structured_jd, normalize_jd_skills
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.role_taxonomy import role_family_default_nice_to_have
from backend.services.taxonomy import normalize_skill_list


def _as_list(value):
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n|]+", value) if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _first_text(*values):
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _clean_education(value):
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _dedupe_without_required(values, required):
    required_keys = {item.lower() for item in normalize_skill_list(required or [])}
    result = []
    seen = set()
    for skill in normalize_skill_list(values or []):
        key = skill.lower()
        if key in required_keys or key in seen:
            continue
        seen.add(key)
        result.append(skill)
    return result


def enrich_jd_for_scoring(jd_text: str, job_data: dict | None = None, structured_jd: dict | None = None) -> dict:
    """
    Convert a pasted JD into the canonical profile used by scoring.

    OpenAI extraction is used inside extract_structured_jd when an API key is present.
    The deterministic role taxonomy then fills recruiter-vague gaps such as title-only
    "Salesforce Developer" or "Data Analyst" JDs.
    """
    job_data = job_data or {}
    structured = structured_jd or extract_structured_jd(jd_text or "")

    role = _first_text(
        structured.get("role"),
        job_data.get("role"),
        job_data.get("job_title"),
        job_data.get("title"),
    )
    min_years = structured.get("min_experience_years")
    if not min_years:
        min_years = extract_experience(job_data.get("experience_required") or jd_text)

    profile_input = {
        **job_data,
        "role": role,
        "job_title": job_data.get("job_title") or role,
        "min_experience_years": min_years or 0,
        "education": _clean_education(structured.get("education")) or job_data.get("education") or "",
        "preferred_skills": structured.get("preferred_skills") or job_data.get("preferred_skills") or [],
    }

    extracted_required = normalize_jd_skills(structured.get("required_skills") or [], jd_text or "")
    extracted_preferred = normalize_jd_skills(structured.get("preferred_skills") or [])
    profile = build_jd_profile(jd_text or role, profile_input, extracted_required)

    required_skills = normalize_skill_list(profile.get("must_have_skills") or extracted_required)
    family_nice_to_have = role_family_default_nice_to_have(profile.get("role_family"))
    preferred_skills = _dedupe_without_required(
        extracted_preferred
        + (profile.get("nice_to_have_skills") or [])
        + family_nice_to_have,
        required_skills,
    )

    profile = build_jd_profile(
        jd_text or role,
        {**profile_input, "required_skills": required_skills, "preferred_skills": preferred_skills},
        required_skills,
    )

    return {
        "structured_jd": structured,
        "jd_profile": profile,
        "role": profile.get("role_title") or role,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "min_experience_years": profile.get("min_experience_years") or min_years or 0,
        "max_experience_years": profile.get("max_experience_years") or 0,
        "education": profile_input.get("education") or "",
        "role_family": profile.get("role_family"),
        "role_family_confidence": profile.get("role_family_confidence"),
        "core_skill_groups": profile.get("core_skill_groups") or {},
        "seniority_level": profile.get("seniority_level"),
        "enrichment_source": "openai_extract_plus_taxonomy" if structured_jd is None else "structured_extract_plus_taxonomy",
    }
