from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from openai import OpenAI

from backend.core.config import get_settings


SUPPORTED_INTENTS = {
    "create_job",
    "edit_job",
    "share_public_apply_link",
    "upload_resumes",
    "review_ai_ranked_candidates",
    "view_candidate_profile",
    "explain_candidate_score",
    "view_shortlisted_candidates",
    "view_candidates_by_stage",
    "shortlist_candidate",
    "reject_candidate",
    "send_candidate_email",
    "schedule_interview",
    "send_screening_test",
    "view_test_result",
    "invite_pilot_user",
    "deactivate_pilot_user",
    "view_plan_usage_limits",
    "unknown",
}

STAGE_ALIASES = {
    "shortlisted": "shortlisted",
    "shortlist": "shortlisted",
    "selected": "selected",
    "select": "selected",
    "rejected": "rejected",
    "reject": "rejected",
    "reviewed": "reviewed",
    "review": "reviewed",
    "interview pending": "interview_pending",
    "interview_pending": "interview_pending",
    "communication pending": "communication_pending",
    "communication_pending": "communication_pending",
    "test sent": "test_sent",
    "test_sent": "test_sent",
}

DEFAULT_ENTITIES = {
    "job_title": None,
    "candidate_name": None,
    "candidate_group": None,
    "stage": None,
    "date_time": None,
    "email": None,
    "plan": None,
}


def _norm(value: str | None) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[._-]+", " ", text)
    text = re.sub(r"\bupl\s*aod\b|\buplod\b|\buplaod\b", "upload", text)
    text = re.sub(r"\bcandiate\b|\bcandiadte\b", "candidate", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_case_job(value: str | None) -> str | None:
    value = re.sub(r"\b(the|this|that|of|for|in)\b", " ", str(value or ""), flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" .,-")
    if not value:
        return None
    return " ".join(part.upper() if part.upper() in {"QA", "AI", "ML", "UI", "UX"} else part.capitalize() for part in value.split())


def _extract_job_title(message: str) -> str | None:
    patterns = [
        r"(?:of|for|in)\s+([a-z0-9 .+#-]+?)\s+job\b",
        r"([a-z0-9 .+#-]+?)\s+wali\s+job",
        r"([a-z0-9 .+#-]+?)\s+job\s+me",
        r"job\s+(?:of|for)\s+([a-z0-9 .+#-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.I)
        if match:
            return _title_case_job(match.group(1))
    return None


def _extract_candidate_name(message: str) -> str | None:
    match = re.search(
        r"\b([A-Z][a-z]{2,})\s+(?:ka|ke|ki)?\s*(?:interview|mail|email|test|profile|score|shortlist|reject)",
        message,
    )
    if match:
        return match.group(1)
    match = re.search(r"\b(?:candidate|profile)\s+([A-Za-z]{2,})\b", message, flags=re.I)
    return match.group(1).capitalize() if match else None


def _stage_from_text(text: str) -> str | None:
    for label, stage in STAGE_ALIASES.items():
        if label in text:
            return stage
    return None


def _has_any_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(r"\b" + re.escape(word) + r"\b", text) for word in words)


def fallback_parse_intent(message: str, current_route: str | None = None, current_context: dict | None = None) -> dict:
    raw = str(message or "")
    text = _norm(raw)
    entities = dict(DEFAULT_ENTITIES)
    entities["job_title"] = _extract_job_title(raw)
    entities["candidate_name"] = _extract_candidate_name(raw)
    entities["email"] = (re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", raw, re.I) or [None])[0]

    stage = _stage_from_text(text)
    if stage:
        entities["stage"] = stage
        entities["candidate_group"] = stage

    intent = "unknown"
    confidence = 0.25

    resume_terms = any(term in text for term in ("resume", "cv", "profile"))
    upload_terms = any(term in text for term in ("upload", "add", "dalna", "dalo", "add karna"))
    if stage == "shortlisted" and _has_any_word(text, ("want", "show", "view", "list", "candidate", "candidates")):
        intent, confidence = "view_shortlisted_candidates", 0.9
    elif stage and _has_any_word(text, ("show", "view", "list", "candidate", "candidates")):
        intent, confidence = "view_candidates_by_stage", 0.86
    elif resume_terms and upload_terms:
        intent, confidence = "upload_resumes", 0.9
    elif any(term in text for term in ("new job", "create job", "job create", "jd add", "jd banana", "opening create")):
        intent, confidence = "create_job", 0.88
    elif any(term in text for term in ("apply link", "public link", "share link")):
        intent, confidence = "share_public_apply_link", 0.85
    elif any(term in text for term in ("score", "ranking", "ranked", "ai score", "top score")):
        intent, confidence = ("explain_candidate_score" if "explain" in text else "review_ai_ranked_candidates"), 0.82
    elif any(term in text for term in ("mail", "email", "message", "bhejna")):
        intent, confidence = "send_candidate_email", 0.84
    elif any(term in text for term in ("shortlist", "select", "top candidate", "top candidates")):
        intent, confidence = "shortlist_candidate", 0.84
    elif any(term in text for term in ("reject", "not fit")):
        intent, confidence = "reject_candidate", 0.82
    elif any(term in text for term in ("interview", "call", "meeting", "schedule")):
        intent, confidence = "schedule_interview", 0.86
    elif any(term in text for term in ("test", "assessment", "screening")):
        intent, confidence = "send_screening_test", 0.84
    elif any(term in text for term in ("client access", "pilot", "invite user", "access dena")):
        intent, confidence = "invite_pilot_user", 0.84
    elif any(term in text for term in ("plan", "limit", "usage", "billing")):
        intent, confidence = "view_plan_usage_limits", 0.86
        entities["plan"] = "usage"

    return normalize_intent_response({
        "intent": intent,
        "entities": entities,
        "confidence": confidence,
        "clarification_needed": intent == "unknown" or confidence < 0.55,
        "clarification_question": "Which workflow do you mean?" if intent == "unknown" else None,
    })


def normalize_intent_response(data: dict[str, Any] | None) -> dict:
    data = data or {}
    intent = str(data.get("intent") or "unknown").strip()
    if intent not in SUPPORTED_INTENTS:
        intent = "unknown"
    entities = dict(DEFAULT_ENTITIES)
    incoming_entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
    for key in entities:
        value = incoming_entities.get(key)
        entities[key] = str(value).strip() if isinstance(value, str) and value.strip() else None

    if intent == "view_shortlisted_candidates":
        entities["candidate_group"] = entities["candidate_group"] or "shortlisted"
        entities["stage"] = entities["stage"] or "shortlisted"

    try:
        confidence = float(data.get("confidence", 0.2))
    except (TypeError, ValueError):
        confidence = 0.2
    confidence = max(0.0, min(1.0, confidence))
    clarification_needed = bool(data.get("clarification_needed")) or intent == "unknown" or confidence < 0.55
    clarification_question = data.get("clarification_question")
    if clarification_question is not None:
        clarification_question = str(clarification_question).strip() or None

    return {
        "intent": intent,
        "entities": entities,
        "confidence": confidence,
        "clarification_needed": clarification_needed,
        "clarification_question": clarification_question,
    }


@lru_cache(maxsize=1)
def _client():
    api_key = os.getenv("OPENAI_API_KEY") or get_settings().openai_api_key
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=12, max_retries=1)


def _model() -> str:
    return os.getenv("OPENAI_HELP_INTENT_MODEL", "gpt-4.1-mini")


def parse_intent(message: str, current_route: str | None = None, current_context: dict | None = None) -> dict:
    fallback = fallback_parse_intent(message, current_route, current_context)
    client = _client()
    if client is None:
        return fallback

    system = (
        "You are HireScore AI's intent parser. Return JSON only. "
        "Only parse the user's intent and entities. Do not invent job IDs, candidate IDs, routes, or actions. "
        "Understand English, Hinglish, broken English, typos, and ATS/recruitment terms. "
        "Supported intents: " + ", ".join(sorted(SUPPORTED_INTENTS)) + ". "
        "Entity fields: job_title, candidate_name, candidate_group, stage, date_time, email, plan. "
        "For shortlisted candidate list requests, use intent view_shortlisted_candidates, candidate_group shortlisted, stage shortlisted, and candidate_name null."
    )
    user_payload = {
        "message": message,
        "current_route": current_route,
        "current_context": current_context or {},
        "response_shape": {
            "intent": "string",
            "entities": DEFAULT_ENTITIES,
            "confidence": "number 0..1",
            "clarification_needed": "boolean",
            "clarification_question": "string or null",
        },
    }
    try:
        response = client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=260,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return normalize_intent_response(parsed)
    except Exception:
        return fallback
