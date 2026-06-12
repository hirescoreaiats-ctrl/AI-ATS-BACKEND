from __future__ import annotations

import copy
import json
import re
from typing import Any

from backend.experience_engine import process_experience
from backend.extractor import normalize_extracted_text
from backend.services.parsing_service import parse_resume_enterprise
from backend.services.resume_quality_gate import build_parser_quality_report
from backend.validation_scoring import validate_email, validate_phone


SAFE_FIELD_THRESHOLDS = {
    "full_name": 0.60,
    "phone": 0.85,
    "education": 0.50,
    "projects": 0.60,
    "experience": 0.50,
    "last_company": 0.60,
}


def _as_jsonable(value: Any):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def _safe_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unsafe_person_name(value: Any) -> bool:
    text = _safe_text(value)
    if not text:
        return False
    lowered = text.lower().strip(" :-|")
    if lowered in {
        "city state",
        "city state gpa",
        "data analyst",
        "business analyst",
        "digitalrealty usa remote",
        "suffolk university boston ma",
        "preferred full name",
    }:
        return True
    if len(text) > 70 or len(text.split()) > 5:
        return True
    if re.search(r"\s[-\u2013\u2014]\s", text) or re.search(r"\b(entri|elevate|cohort|coursework)\b", text, re.I):
        return True
    if re.search(r"\b(gpa|university|college|school|bachelor|master|degree|major|minor)\b", text, re.I):
        return True
    if re.search(r"\b(remote|hybrid|onsite|usa|u\.s\.a?|city|state)\b", text, re.I) and len(text.split()) <= 4:
        return True
    if re.search(r"\b(data|business|qa|software|full\s*stack|java|python)\s+(analyst|engineer|developer|tester)\b", text, re.I):
        return True
    parts = text.split()
    if len(parts) >= 4 and sum(1 for part in parts if len(part.strip(".-")) <= 2) >= 2:
        return True
    return bool(re.search(
        r"@|\b(email|e-mail|objective|career objective|preferred full name|job title|company name|department|"
        r"hiring manager|application form|position applied|resume|profile|summary|skills?|"
        r"education|experience|projects?|contact|developer\s+at|engineer\s+at|cv|about|github|github\.com|"
        r"coursework|main developer|nilaya|nagar|road|street|layout|address)\b",
        text,
        re.I,
    ))


def _text_extraction_quality(text: str) -> dict:
    normalized = normalize_extracted_text(text or "")
    words = re.findall(r"\w+", normalized)
    section_hits = len(set(re.findall(
        r"\b(summary|profile|experience|work experience|education|skills|projects|certifications)\b",
        normalized,
        re.I,
    )))
    line_count = len([line for line in normalized.splitlines() if line.strip()])
    score = 100
    flags = []
    if len(words) < 80:
        score -= 35
        flags.append("very_short_text")
    elif len(words) < 140:
        score -= 18
        flags.append("short_text")
    if section_hits < 2:
        score -= 15
        flags.append("few_section_markers")
    if line_count < 8:
        score -= 10
        flags.append("low_line_count")
    if re.search(r"(cid:\d+|�|(?:[A-Za-z]\s+){8,}[A-Za-z])", normalized):
        score -= 15
        flags.append("layout_or_ocr_noise")
    score = max(0, min(100, score))
    if score < 50:
        label = "poor"
    elif score < 70:
        label = "needs_review"
    else:
        label = "clean"
    return {
        "score": score,
        "label": label,
        "word_count": len(words),
        "line_count": line_count,
        "section_hits": section_hits,
        "flags": flags,
    }


def _field_sources(parsed: dict) -> dict:
    flags = set(parsed.get("parser_flags") or [])
    sections = parsed.get("sections") or {}
    sources = {
        "email": "deterministic_regex",
        "phone": "strict_phone_parser",
        "links": "deterministic_url_regex",
        "skills": "taxonomy_and_resume_text",
        "full_name": "header_or_ai_cross_checked",
        "experience": "ai_plus_section_recovery",
        "education": "ai_plus_education_section",
        "projects": "project_section_or_validated_ai",
    }
    if "name_needs_review" in flags:
        sources["full_name"] = "low_confidence_recovery"
    if "company_needs_review" in flags:
        sources["last_company"] = "low_confidence_experience_section"
    elif sections.get("experience"):
        sources["last_company"] = "experience_section"
    if "project_noise_detected" in flags:
        sources["projects"] = "rejected_noisy_project_parse"
    return sources


def _safe_parsed(parsed: dict, quality_action: str) -> dict:
    confidence = dict(parsed.get("field_confidence") or {})
    safe_display = dict(parsed.get("safe_display") or {})
    safe = {
        "full_name": parsed.get("full_name") or "",
        "email": validate_email(parsed.get("email")) or "",
        "phone": validate_phone(parsed.get("phone")) or "",
        "location": parsed.get("location") or "",
        "designation": parsed.get("designation") or "",
        "key_skills": parsed.get("key_skills") or [],
        "education": parsed.get("education") or [],
        "projects": parsed.get("projects") or [],
        "experience": parsed.get("experience") or [],
        "safe_display": safe_display,
    }
    if confidence.get("name", 1) < SAFE_FIELD_THRESHOLDS["full_name"]:
        safe["full_name"] = ""
    if confidence.get("phone", 1) < SAFE_FIELD_THRESHOLDS["phone"]:
        safe["phone"] = ""
    if confidence.get("education", 1) < SAFE_FIELD_THRESHOLDS["education"]:
        safe["education"] = []
    if confidence.get("project_evidence", 1) < SAFE_FIELD_THRESHOLDS["projects"]:
        safe["projects"] = []
    if confidence.get("experience", 1) < SAFE_FIELD_THRESHOLDS["experience"] and quality_action == "manual_review_required":
        safe["experience"] = []
    return safe


def apply_safe_primary_fields(parsed: dict) -> dict:
    """Keep scoring metadata, but remove unsafe primary display values on critical parses."""
    action = parsed.get("parser_quality_action")
    if action != "manual_review_required":
        return parsed
    safe = parsed.get("safe_parsed_json") or {}
    confidence = parsed.get("field_confidence") or {}
    if confidence.get("name", 1) < SAFE_FIELD_THRESHOLDS["full_name"]:
        parsed["full_name"] = safe.get("full_name") or ""
    if confidence.get("phone", 1) < SAFE_FIELD_THRESHOLDS["phone"]:
        parsed["phone"] = safe.get("phone") or ""
    if confidence.get("education", 1) < SAFE_FIELD_THRESHOLDS["education"]:
        parsed["education"] = safe.get("education") or []
    if confidence.get("project_evidence", 1) < SAFE_FIELD_THRESHOLDS["projects"]:
        parsed["projects"] = safe.get("projects") or []
    parsed["profile_extraction_quality"] = "Needs review"
    parsed["recommendation"] = "in_review"
    return parsed


def parse_resume_document(text: str, job_context: dict | None = None, mode: str = "application", ai_parse_override=None) -> dict:
    normalized_text = normalize_extracted_text(text or "")
    parsed = parse_resume_enterprise(normalized_text, ai_parse_override=ai_parse_override)
    parsed["email"] = validate_email(parsed.get("email")) or ""
    parsed["phone"] = validate_phone(parsed.get("phone")) or ""
    if _unsafe_person_name(parsed.get("full_name")):
        flags = set(parsed.get("parser_flags") or [])
        flags.add("name_needs_review")
        parsed["parser_flags"] = sorted(flags)
        confidence = dict(parsed.get("field_confidence") or {})
        confidence["name"] = min(float(confidence.get("name") or 0.25), 0.25)
        parsed["field_confidence"] = confidence
        parsed["full_name"] = ""

    exp_data = process_experience(parsed.get("experience", []))
    raw_parsed = copy.deepcopy(parsed)
    quality_report = build_parser_quality_report(normalized_text, parsed, exp_data, job_context or {})
    parsed.update({
        "parser_quality_score": quality_report.get("parser_quality_score"),
        "parser_quality_action": quality_report.get("parser_quality_action"),
        "parser_quality_flags": quality_report.get("parser_quality_flags"),
    })
    text_quality = _text_extraction_quality(normalized_text)
    if text_quality["label"] == "poor":
        flags = list(parsed.get("parser_quality_flags") or [])
        flags.append({
            "code": "poor_text_extraction",
            "severity": "critical",
            "message": "Resume text extraction quality is poor; recruiter validation is required.",
            "penalty": 25,
        })
        parsed["parser_quality_flags"] = flags
        parsed["parser_quality_score"] = min(float(parsed.get("parser_quality_score") or 0), 45)
        parsed["parser_quality_action"] = "manual_review_required"

    safe = _safe_parsed(parsed, parsed.get("parser_quality_action"))
    parsed.update({
        "raw_parsed_json": _as_jsonable(raw_parsed),
        "safe_parsed_json": _as_jsonable(safe),
        "field_confidence_json": _as_jsonable(parsed.get("field_confidence") or {}),
        "field_sources_json": _as_jsonable(_field_sources(parsed)),
        "text_extraction_quality": _as_jsonable(text_quality),
        "profile_extraction_quality": "Needs review"
        if parsed.get("parser_quality_action") in {"manual_review_required", "review_before_shortlist"}
        else "Clean",
        "canonical_parse_mode": mode,
    })
    return apply_safe_primary_fields(parsed)
