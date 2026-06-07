from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.jd_engine import normalize_jd_skills
from backend.services.jd_profile_engine import build_jd_profile


def _clean_value(value: Any):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return str(value).strip()


def _stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def job_jd_hash(job) -> str:
    """Stable fingerprint for the JD fields that affect one job's score."""
    payload = {
        "job_id": _clean_value(getattr(job, "id", "")),
        "job_title": _clean_value(getattr(job, "job_title", "")),
        "role": _clean_value(getattr(job, "role", "")),
        "jd_text": _clean_value(getattr(job, "jd_text", "")),
        "required_skills": _clean_value(getattr(job, "required_skills", "")),
        "preferred_skills": _clean_value(getattr(job, "preferred_skills", "")),
        "experience_required": _clean_value(getattr(job, "experience_required", "")),
        "min_experience_years": _clean_value(getattr(job, "min_experience_years", "")),
        "education": _clean_value(getattr(job, "education", "")),
    }
    return _stable_hash(payload)


def build_job_jd_profile(job) -> dict:
    jd_skills = normalize_jd_skills(getattr(job, "required_skills", "") or "", getattr(job, "jd_text", "") or "")
    jd_data = {
        "job_title": getattr(job, "job_title", "") or "",
        "role": getattr(job, "role", None) or getattr(job, "job_title", "") or "",
        "required_skills": getattr(job, "required_skills", "") or "",
        "preferred_skills": getattr(job, "preferred_skills", "") or "",
        "experience_required": getattr(job, "experience_required", "") or "",
        "min_experience_years": getattr(job, "min_experience_years", None),
        "education": getattr(job, "education", "") or "",
    }
    return build_jd_profile(getattr(job, "jd_text", "") or "", jd_data, jd_skills)


def apply_job_scoring_snapshot(resume, job, jd_profile: dict | None = None) -> dict:
    profile = jd_profile or build_job_jd_profile(job)
    if hasattr(resume, "score_job_id"):
        resume.score_job_id = getattr(job, "id", None)
    if hasattr(resume, "score_jd_hash"):
        resume.score_jd_hash = job_jd_hash(job)
    if hasattr(resume, "jd_profile_json"):
        resume.jd_profile_json = json.dumps(profile or {}, ensure_ascii=False)
    if hasattr(resume, "jd_profile_snapshot_json"):
        resume.jd_profile_snapshot_json = json.dumps(profile or {}, ensure_ascii=False)
    return profile


def apply_job_jd_snapshot(job, jd_profile: dict | None = None) -> dict:
    profile = jd_profile or build_job_jd_profile(job)
    if hasattr(job, "jd_hash"):
        job.jd_hash = job_jd_hash(job)
    if hasattr(job, "jd_profile_json"):
        job.jd_profile_json = json.dumps(profile or {}, ensure_ascii=False)
    return profile
