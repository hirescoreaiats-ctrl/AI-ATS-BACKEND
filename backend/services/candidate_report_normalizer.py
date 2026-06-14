import json
import re
from typing import Any


EMPTY_REPORT = {
    "summary": "",
    "strengths": [],
    "concerns": [],
    "recommendation": "",
    "ranking_reason": "",
    "experience_summary": {},
    "follow_up_questions": [],
    "data_quality_notes": [],
}


PARSER_FLAG_MESSAGES = {
    "ai_parse_recovered": "Resume parse was repaired after an initial extraction issue.",
    "phone_needs_review": "Phone number may need manual verification.",
    "name_needs_review": "Candidate name may need manual verification.",
    "company_needs_review": "Company name may need manual verification.",
    "education_needs_review": "Education details may need manual verification.",
    "experience_needs_review": "Experience dates or work-history details may need manual verification.",
    "profile_needs_review": "Profile details may need recruiter verification.",
    "missing_mandatory_skills": "Some mandatory skills need recruiter validation.",
    "keyword_only_match": "Some matched skills appear only as keywords and should be verified.",
    "parser_manual_review": "Resume extraction quality requires manual recruiter review.",
    "section_boundary_low_confidence": "Resume sections were difficult to separate; review extracted fields.",
    "project_noise_detected": "Some project details may include noisy extracted text.",
}


def normalize_candidate_report(value: Any, candidate: dict | None = None) -> dict:
    candidate = candidate or {}
    parsed = _parse_input(value)
    if parsed is None:
        report = dict(EMPTY_REPORT)
    elif isinstance(parsed, dict):
        report = _normalize_object(parsed)
    elif isinstance(parsed, list):
        report = {**EMPTY_REPORT, "strengths": _normalize_list(parsed)}
    else:
        report = _normalize_plain_text(str(parsed or ""))

    flags = _normalize_list(
        candidate.get("parser_flags")
        or candidate.get("parser_quality_flags")
        or candidate.get("recruiter_flags")
        or []
    )
    report["data_quality_notes"] = _unique([
        *report.get("data_quality_notes", []),
        *[_humanize_parser_flag(flag) for flag in flags if _is_parser_flag(flag)],
    ])
    report["concerns"] = [item for item in _normalize_list(report.get("concerns")) if not _is_parser_flag(item)]
    return report


def serialize_candidate_report(value: Any, candidate: dict | None = None) -> str:
    return json.dumps(normalize_candidate_report(value, candidate), ensure_ascii=False)


def _parse_input(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = _try_parse_json_deep(text)
    return parsed if parsed is not None else text


def _try_parse_json_deep(text: str) -> Any:
    value: Any = text
    for _ in range(3):
        if not isinstance(value, str):
            return value
        clean = value.strip()
        if not ((clean.startswith("{") and clean.endswith("}")) or (clean.startswith("[") and clean.endswith("]"))):
            return None
        try:
            value = json.loads(clean)
        except Exception:
            extracted = _extract_json(clean)
            if not extracted:
                return None
            try:
                value = json.loads(extracted)
            except Exception:
                return None
    return value


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    return text[start:end + 1] if start >= 0 and end > start else ""


def _normalize_object(data: dict) -> dict:
    raw_concerns = _normalize_list(data.get("concerns") or data.get("gaps") or data.get("risks"))
    notes = _unique([
        *_normalize_list(data.get("data_quality_notes") or data.get("parser_notes")),
        *[_humanize_parser_flag(item) for item in raw_concerns if _is_parser_flag(item)],
        *[_humanize_parser_flag(item) for item in _normalize_list(data.get("parser_flags") or data.get("parser_quality_flags"))],
    ])
    return {
        "summary": _clean_text(data.get("summary") or data.get("overall_summary") or data.get("profile_summary")),
        "strengths": _normalize_list(data.get("strengths") or data.get("key_strengths") or data.get("evidence")),
        "concerns": [_clean_text(item) for item in raw_concerns if not _is_parser_flag(item)],
        "recommendation": _clean_text(data.get("recommendation") or data.get("verdict")),
        "ranking_reason": _clean_text(data.get("ranking_reason") or data.get("reason")),
        "experience_summary": _normalize_experience(data.get("experience_summary") or {}),
        "follow_up_questions": _normalize_list(data.get("follow_up_questions") or data.get("next_steps") or data.get("questions")),
        "data_quality_notes": notes,
    }


def _normalize_plain_text(text: str) -> dict:
    sections = _section_text(text)
    return {
        **EMPTY_REPORT,
        "summary": _clean_text(sections.get("summary") or _first_sentence(text)),
        "strengths": _normalize_list(sections.get("strengths")),
        "concerns": [item for item in _normalize_list(sections.get("gaps")) if not _is_parser_flag(item)],
        "recommendation": _clean_text(sections.get("verdict")),
        "data_quality_notes": _parser_notes_from_text(text),
    }


def _section_text(text: str) -> dict:
    result = {}
    matches = list(re.finditer(r"(Summary|Strengths|Gaps|Verdict)\s*:?", text or "", re.I))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1).lower()] = text[start:end].strip()
    return result


def _first_sentence(text: str) -> str:
    clean = _clean_text(text)
    return re.split(r"(?<=\.)\s+", clean)[0] if clean else ""


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parsed = _try_parse_json_deep(value.strip())
        if parsed is not None:
            return _normalize_list(parsed)
        parts = re.split(r"\n+\s*(?:[-*]|\d+[.)])\s+|\s+-\s+(?=[A-Z0-9])", value)
        if len(parts) <= 1:
            parts = re.split(r"(?<=\.)\s+(?=[A-Z])", value)
        return [_clean_text(part) for part in parts if _clean_text(part)]
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                items.append(_clean_text(item.get("summary") or item.get("description") or item.get("text") or item.get("reason")))
            else:
                items.extend(_normalize_list(str(item)))
        return _unique([item for item in items if item])
    if isinstance(value, dict):
        return _normalize_list(list(value.values()))
    return [_clean_text(value)]


def _normalize_experience(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        "total_years": value.get("total_years") or value.get("total_experience_years"),
        "relevant_years": value.get("relevant_years") or value.get("jd_relevant_experience_years"),
        "label": _clean_text(value.get("label") or value.get("experience_fit") or value.get("experience_relevance_label")),
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    text = str(value).replace("\\n", "\n").replace('\\"', '"')
    text = re.sub(r'^\s*[-*"\':,]+|["\',\s]+$', "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_parser_flag(value: Any) -> bool:
    text = str(value or "")
    return bool(re.search(r"parser flag|ai_parse_recovered|phone_needs_review|name_needs_review|missing_mandatory_skills|keyword_only_match|needs_review", text, re.I))


def _humanize_parser_flag(value: Any) -> str:
    raw = re.sub(r"^parser flag:\s*", "", str(value or ""), flags=re.I).strip()
    key = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return PARSER_FLAG_MESSAGES.get(key) or raw.replace("_", " ").strip()


def _parser_notes_from_text(text: str) -> list[str]:
    notes = []
    for flag, message in PARSER_FLAG_MESSAGES.items():
        if re.search(rf"\b{re.escape(flag)}\b", text or "", re.I):
            notes.append(message)
    return _unique(notes)


def _unique(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        clean = _clean_text(item)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            output.append(clean)
    return output
