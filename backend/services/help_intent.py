from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import lru_cache
from typing import Any

from openai import OpenAI

from backend.core.config import get_settings


logger = logging.getLogger(__name__)
AGENT_CONTRACT_VERSION = "2026-07-general-v1"


SUPPORTED_INTENTS = {
    "filter_candidates",
    "view_active_jobs",
    "jobs_needing_attention",
    "applicant_metrics",
    "view_sourcing_status",
    "search_talent",
    "candidate_workflow",
    "create_job",
    "edit_job",
    "share_public_apply_link",
    "upload_resumes",
    "select_top_candidates",
    "review_ai_ranked_candidates",
    "view_candidate_profile",
    "explain_candidate_score",
    "view_shortlisted_candidates",
    "view_candidates_by_stage",
    "shortlist_candidate",
    "reject_candidate",
    "move_candidates_to_communication",
    "move_candidates_to_interview",
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
    "communication": "communication",
    "commincation": "communication",
    "communcation": "communication",
    "outreach": "communication",
    "interview": "interview_scheduling",
    "interview scheduling": "interview_scheduling",
    "test sent": "test_sent",
    "test_sent": "test_sent",
}

DEFAULT_ENTITIES = {
    "filters": None,
    "search_query": None,
    "job_title": None,
    "candidate_name": None,
    "candidate_id": None,
    "candidate_group": None,
    "stage": None,
    "target_stage": None,
    "date_time": None,
    "meeting_url": None,
    "email": None,
    "plan": None,
    "limit": None,
    "job_id": None,
    "candidate_ids": None,
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
}

GREETING_PATTERN = re.compile(
    r"^\s*(?:hi|hello|hey|hii+|heyy+|namaste|namaskar|good\s+(?:morning|afternoon|evening))"
    r"(?:\s+(?:there|bhai|bro|sir|team))?[!.?\s]*$",
    flags=re.I,
)


def _conversation_fallback(message: str) -> dict[str, Any] | None:
    if not GREETING_PATTERN.match(str(message or "")):
        return None
    return normalize_intent_response({
        "response_type": "conversation",
        "intent": "unknown",
        "confidence": 1.0,
        "clarification_needed": False,
        "assistant_reply": (
            "Hello! How can I help with your hiring workflow today? You can ask me to find candidates, "
            "upload resumes, shortlist profiles, send outreach, or schedule interviews."
        ),
    })


def _norm(value: str | None) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9+#]+", " ", text)
    text = re.sub(r"\bshort\s*(?:list|ist|lst|lis)\b", "shortlist", text)
    text = re.sub(r"\bupl\s*aod\b|\buplod\b|\buplaod\b", "upload", text)
    text = re.sub(r"\bcandiate\b|\bcandiadte\b", "candidate", text)
    text = re.sub(r"\bcommincation\b|\bcommuncation\b|\bcomunication\b", "communication", text)
    text = re.sub(r"\bshedule\b|\bsehdule\b", "schedule", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _friendly_user_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(
        r"(?:please\s+)?(?:provide|specify|share|enter|confirm)\s+(?:the\s+)?job[\s_-]*id(?:\s+or)?",
        "please tell me the job title or choose the matching job below",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bjob[\s_-]*id\b", "job title", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _title_case_job(value: str | None) -> str | None:
    value = re.sub(
        r"\b(the|this|that|of|for|in|job|jobs|mujhe|muje|please|top|candidate|candidates|candiate|"
        r"want|need|you|to|give|get|nikal|nikalo|find|show|list|do|de|bhej|send|unha|unhe|unka|aur|and|or|interview|"
        r"schedule|communication|mai|me|mein|ke|kai|kay|liye|lia|liya)\b",
        " ",
        str(value or ""),
        flags=re.I,
    )
    value = re.sub(r"\s+", " ", value).strip(" .,-")
    if not value:
        return None
    return " ".join(part.upper() if part.upper() in {"QA", "AI", "ML", "UI", "UX"} else part.capitalize() for part in value.split())


def _extract_job_title(message: str) -> str | None:
    patterns = [
        r"(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates|resume|resumes|profile|profiles)s?\s+(?:of|for|in)\s+(.+?)(?:\s+(?:job|role|opening)\b|$)",
        r"(?:give|get|show|find|list|shortlist|select|review)\s+(?:me\s+)?(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates|resume|resumes|profile|profiles)?\s*(?:of|for|in)\s+(.+?)(?:\s+(?:job|role|opening)\b|$)",
        r"(?:candidate|candidates)\s+(?:nikal|nikalo|find|show|list|de do|do)\s+(.+?)\s+(?:ke|kai|kay|for)\s*(?:liye|lia|liya)?\b",
        r"(.+?)\s+(?:ke|kai|kay)\s+(?:liye|lia|liya)\s+(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates|resume|profile)",
        r"(.+?)(?:\s+job)?\s+(?:ke|ka|ki|kai|kay)\s+(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates|resume|resumes|profile|profiles)",
        r"(?:of|for|in)\s+(.+?)\s+(?:job|role|opening)\b",
        r"(.+?)\s+wali\s+job",
        r"(.+?)\s+job\s+me",
        r"job\s+(?:of|for)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.I)
        if match:
            return _title_case_job(match.group(1))
    return None


def _extract_limit(text: str) -> int | None:
    patterns = [
        r"\btop\s+(\d{1,3})\b",
        r"\bbest\s+(\d{1,3})\b",
        r"\b(\d{1,3})\s+top\s+(?:candidate|candidates|resume|resumes|profile|profiles)\b",
        r"\b(\d{1,3})\s+(?:candidate|candidates|resume|resumes|profile|profiles)\b",
        r"\b(?:top\s+)?(" + "|".join(NUMBER_WORDS) + r")\s+(?:candidate|candidates|resume|resumes|profile|profiles)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        raw = match.group(1).lower()
        limit = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)
        if limit:
            return max(1, min(limit, 100))
    if re.search(r"\btop\s+(?:candidate|resume|profile)\b", text, flags=re.I):
        return 1
    return None


def _target_stage_from_text(text: str) -> str | None:
    if any(term in text for term in ("interview", "schedule call", "meeting schedule", "call schedule")):
        return "interview_scheduling"
    if any(term in text for term in ("communication", "outreach")):
        return "communication"
    return _stage_from_text(text)


def _candidate_selection_requested(text: str) -> bool:
    selection_terms = (
        "shortlist candidate",
        "shortlist candidates",
        "shortlist resume",
        "shortlist resumes",
        "select candidate",
        "select candidates",
        "candidate nikal",
        "candidates nikal",
        "candidate find",
        "candidates find",
        "candidate show",
        "candidates show",
        "top candidate",
        "top candidates",
        "best candidate",
        "best candidates",
        "ranked candidate",
        "ranked candidates",
    )
    return any(term in text for term in selection_terms) or bool(
        re.search(r"\b\d{1,3}\s+(?:candidate|candidates|resume|resumes|profile|profiles)\b", text)
    )


def _shortlist_action_requested(text: str) -> bool:
    return bool(re.search(r"\b(?:candidate|candidates|resume|resumes)\s+shortlist\b", text)) or any(
        term in text
        for term in (
            "shortlist candidate",
            "shortlist candidates",
            "shortlist resume",
            "shortlist resumes",
            "select candidate",
            "select candidates",
        )
    )


def _view_shortlisted_requested(text: str) -> bool:
    return "shortlisted" in text or any(
        term in text
        for term in (
            "view shortlist",
            "show shortlist",
            "list shortlist",
            "shortlist list",
            "shortlisted candidate",
            "shortlisted candidates",
        )
    )


def _workflow_tasks(intent: str, entities: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    target_stage = entities.get("target_stage") or entities.get("stage")
    limit = entities.get("limit")

    if intent in {"view_active_jobs", "jobs_needing_attention", "applicant_metrics", "view_sourcing_status"}:
        tasks.append({
            "intent": intent,
            "description": "Retrieve current ATS job and applicant data from the authorized workspace.",
            "entities": entities,
        })

    if entities.get("filters") and intent in {"filter_candidates", "candidate_workflow"}:
        tasks.append({
            "intent": "filter_candidates",
            "description": "Filter stored candidates using validated ATS fields.",
            "entities": {"filters": entities.get("filters") or {}, "limit": limit or 10},
        })

    if intent == "search_talent":
        tasks.append({
            "intent": "search_talent",
            "description": "Search the organization-wide candidate database by role, skills, and resume evidence.",
            "entities": {"search_query": entities.get("search_query"), "limit": limit or 10},
        })

    if intent in {"candidate_workflow", "select_top_candidates", "review_ai_ranked_candidates"} and not entities.get("filters"):
        tasks.append(
            {
                "intent": "select_top_candidates",
                "description": "Find the highest ranked candidates for the requested job.",
                "entities": {
                    "job_title": entities.get("job_title"),
                    "job_id": entities.get("job_id"),
                    "limit": limit or 10,
                },
            }
        )

    if target_stage == "shortlisted" and intent in {"candidate_workflow", "select_top_candidates"}:
        if not any(task["intent"] == "shortlist_candidate" for task in tasks):
            tasks.append(
                {
                    "intent": "shortlist_candidate",
                    "description": "Shortlist the selected candidates after recruiter review.",
                    "entities": {
                        "job_title": entities.get("job_title"),
                        "job_id": entities.get("job_id"),
                        "candidate_ids": entities.get("candidate_ids"),
                    },
                }
            )

    if intent == "move_candidates_to_communication" or target_stage == "communication":
        if not any(task["intent"] == "shortlist_candidate" for task in tasks):
            tasks.append(
                {
                    "intent": "shortlist_candidate",
                    "description": "Shortlist the selected candidates so they can enter Communication.",
                    "entities": {
                        "job_title": entities.get("job_title"),
                        "job_id": entities.get("job_id"),
                        "candidate_ids": entities.get("candidate_ids"),
                    },
                }
            )
        tasks.append(
            {
                "intent": "move_candidates_to_communication",
                "description": "Move the selected candidate list into Communication.",
                "entities": {
                    "job_title": entities.get("job_title"),
                    "job_id": entities.get("job_id"),
                    "candidate_ids": entities.get("candidate_ids"),
                },
            }
        )

    if intent == "move_candidates_to_interview" or target_stage == "interview_scheduling":
        if not any(task["intent"] == "move_candidates_to_communication" for task in tasks):
            if not any(task["intent"] == "shortlist_candidate" for task in tasks):
                tasks.append(
                    {
                        "intent": "shortlist_candidate",
                        "description": "Shortlist the selected candidates so they can enter Communication.",
                        "entities": {
                            "job_title": entities.get("job_title"),
                            "job_id": entities.get("job_id"),
                            "candidate_ids": entities.get("candidate_ids"),
                        },
                    }
                )
            tasks.append(
                {
                    "intent": "move_candidates_to_communication",
                    "description": "Ensure selected candidates are in Communication before interview scheduling.",
                    "entities": {
                        "job_title": entities.get("job_title"),
                        "job_id": entities.get("job_id"),
                        "candidate_ids": entities.get("candidate_ids"),
                    },
                }
            )
        tasks.extend(
            [
                {
                    "intent": "move_candidates_to_interview",
                    "description": "Move selected candidates into the interview scheduling pipeline.",
                    "entities": {
                        "job_title": entities.get("job_title"),
                        "job_id": entities.get("job_id"),
                        "candidate_ids": entities.get("candidate_ids"),
                    },
                },
                {
                    "intent": "schedule_interview",
                    "description": "Schedule interview slots once date/time and meeting link are available.",
                    "entities": {
                        "date_time": entities.get("date_time"),
                        "meeting_url": entities.get("meeting_url"),
                        "candidate_ids": entities.get("candidate_ids"),
                    },
                },
            ]
        )

    if target_stage == "rejected" and intent == "candidate_workflow":
        tasks.append({
            "intent": "reject_candidate",
            "description": "Reject only the candidates returned by the validated filter after confirmation.",
            "entities": {"job_id": entities.get("job_id"), "candidate_ids": entities.get("candidate_ids")},
        })

    if not tasks and intent in SUPPORTED_INTENTS and intent != "unknown":
        tasks.append({"intent": intent, "description": "Handle the requested ATS workflow.", "entities": entities})

    return tasks


def _action_plan(tasks: list[dict[str, Any]], entities: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for task in tasks:
        task_intent = task.get("intent")
        if task_intent == "select_top_candidates":
            actions.append(
                {
                    "action_id": "find_top_candidates",
                    "actor": "action_agent",
                    "method": "GET",
                    "endpoint": "/results/{job_id}",
                    "needs": ["job_id"],
                    "params": {
                        "job_title": entities.get("job_title"),
                        "limit": entities.get("limit") or 10,
                        "sort": "final_score_desc",
                    },
                    "output": "candidate_ids",
                    "requires_confirmation": False,
                }
            )
        elif task_intent == "search_talent":
            actions.append(
                {
                    "action_id": "search_talent",
                    "actor": "action_agent",
                    "method": "GET",
                    "endpoint": "/api/v1/talent/search",
                    "needs": ["search_query"],
                    "params": {"q": entities.get("search_query"), "limit": entities.get("limit") or 10},
                    "requires_confirmation": False,
                }
            )

        elif task_intent == "view_active_jobs":
            actions.append({
                "action_id": "list_active_jobs", "actor": "action_agent", "method": "GET",
                "endpoint": "/jobs", "needs": [], "params": {"status": "active"}, "requires_confirmation": False,
            })
        elif task_intent == "jobs_needing_attention":
            actions.append({
                "action_id": "list_jobs_needing_attention", "actor": "action_agent", "method": "GET",
                "endpoint": "/jobs", "needs": [], "params": {}, "requires_confirmation": False,
            })
        elif task_intent == "applicant_metrics":
            actions.append({
                "action_id": "get_applicant_metrics", "actor": "action_agent", "method": "GET",
                "endpoint": "/jobs", "needs": [], "params": {"period": "today"}, "requires_confirmation": False,
            })
        elif task_intent == "view_sourcing_status":
            actions.append({
                "action_id": "get_sourcing_status", "actor": "action_agent", "method": "GET",
                "endpoint": "/jobs/{job_id}", "needs": ["job_id"], "params": {}, "requires_confirmation": False,
            })
        elif task_intent == "filter_candidates":
            actions.append(
                {
                    "action_id": "filter_candidates",
                    "actor": "action_agent",
                    "method": "GET",
                    "endpoint": "/api/v1/help/chat",
                    "needs": ["filters"],
                    "params": {"filters": entities.get("filters") or {}, "limit": entities.get("limit") or 10},
                    "requires_confirmation": False,
                }
            )
        elif task_intent == "shortlist_candidate":
            actions.append(
                {
                    "action_id": "shortlist_candidates",
                    "actor": "action_agent",
                    "method": "POST",
                    "endpoint": "/shortlist/{candidate_id}",
                    "needs": ["candidate_ids"],
                    "payload_template": {},
                    "batch": True,
                    "requires_confirmation": True,
                }
            )
        elif task_intent == "move_candidates_to_communication":
            actions.append(
                {
                    "action_id": "move_to_communication",
                    "actor": "action_agent",
                    "method": "POST",
                    "endpoint": "/move-to-communication",
                    "needs": ["job_id"],
                    "params": {"job_id": "{job_id}"},
                    "batch": False,
                    "requires_confirmation": True,
                }
            )
        elif task_intent == "move_candidates_to_interview":
            actions.append(
                {
                    "action_id": "move_to_interview_scheduling",
                    "actor": "action_agent",
                    "method": "POST",
                    "endpoint": "/move-to-interview-scheduling",
                    "needs": ["job_id", "candidate_ids"],
                    "payload_template": {
                        "job_id": "{job_id}",
                        "candidate_id": "{candidate_id}",
                        "force_without_test": False,
                    },
                    "batch": True,
                    "requires_confirmation": True,
                }
            )
        elif task_intent == "schedule_interview":
            actions.append(
                {
                    "action_id": "schedule_interview_slot",
                    "actor": "action_agent",
                    "method": "POST",
                    "endpoint": "/schedule-interview-slot",
                    "needs": ["job_id", "candidate_ids", "scheduled_at", "meeting_url"],
                    "payload_template": {
                        "job_id": "{job_id}",
                        "candidate_id": "{candidate_id}",
                        "scheduled_at": entities.get("date_time") or "{scheduled_at}",
                        "meeting_url": entities.get("meeting_url") or "{meeting_url}",
                        "duration_minutes": 45,
                    },
                    "batch": True,
                    "requires_confirmation": True,
                }
            )
        elif task_intent == "send_candidate_email":
            actions.append(
                {
                    "action_id": "send_mail",
                    "actor": "action_agent",
                    "method": "POST",
                    "endpoint": "/send-mail",
                    "needs": ["candidate_ids"],
                    "payload_template": {"candidate_id": "{candidate_id}", "job_id": "{job_id}"},
                    "batch": True,
                    "requires_confirmation": True,
                }
            )
        elif task_intent == "reject_candidate":
            actions.append(
                {
                    "action_id": "reject_candidates",
                    "actor": "action_agent",
                    "method": "POST",
                    "endpoint": "/api/v1/help/execute",
                    "needs": ["candidate_ids"],
                    "batch": True,
                    "requires_confirmation": True,
                }
            )
    return actions


def _missing_fields_for_actions(actions: list[dict[str, Any]], entities: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if any("job_id" in action.get("needs", []) for action in actions) and not (entities.get("job_id") or entities.get("job_title")):
        missing.append("job_title_or_job_id")
    if any("candidate_ids" in action.get("needs", []) for action in actions) and not entities.get("candidate_ids"):
        if not any(action.get("action_id") == "find_top_candidates" for action in actions):
            missing.append("candidate_ids")
    if any("scheduled_at" in action.get("needs", []) for action in actions) and not entities.get("date_time"):
        missing.append("scheduled_at")
    if any("meeting_url" in action.get("needs", []) for action in actions) and not entities.get("meeting_url"):
        missing.append("meeting_url")
    if any("search_query" in action.get("needs", []) for action in actions) and not entities.get("search_query"):
        missing.append("search_query")
    if any("filters" in action.get("needs", []) for action in actions) and not entities.get("filters"):
        missing.append("filters")
    return missing


def _guidance(intent: str, entities: dict[str, Any], tasks: list[dict[str, Any]], missing_fields: list[str]) -> str:
    job_label = entities.get("job_title") or "selected job"
    limit = entities.get("limit") or 10
    if intent == "candidate_workflow":
        base = f"I will prepare an action-agent plan for top {limit} candidates for {job_label}."
        if entities.get("target_stage") == "communication":
            base += " It will find ranked candidates and move them to Communication after confirmation."
        elif entities.get("target_stage") == "interview_scheduling":
            base += " It will find ranked candidates, move them through Communication/Interview Scheduling, then schedule interviews once slot details are available."
        if missing_fields:
            base += " Missing: " + ", ".join(missing_fields) + "."
        return base
    if tasks:
        return tasks[0].get("description") or "I can guide this workflow."
    return "I can help with jobs, candidates, communication, tests, interviews, and hiring workflow actions."


def _tour_step(target: str, title: str, body: str, route: str | None = None) -> dict[str, Any]:
    return {"target": target, "title": title, "body": body, "route": route}


def _visual_tour(intent: str, tasks: list[dict[str, Any]], entities: dict[str, Any]) -> dict[str, Any]:
    task_intents = [task.get("intent") for task in tasks]
    steps: list[dict[str, Any]] = []

    if "select_top_candidates" in task_intents:
        steps.extend(
            [
                _tour_step("jobs-menu", "Open Recruiter", "Go to the recruiter results for the selected job.", "results"),
                _tour_step("ai-score-column", "Review AI Ranking", "Use final score, rank score, fit band, and evidence before selecting candidates.", "results"),
                _tour_step("candidates-table", "Select Top Candidates", f"Select the top {entities.get('limit') or 10} candidates for this workflow.", "results"),
            ]
        )
    elif intent in {"view_shortlisted_candidates", "view_candidates_by_stage", "review_ai_ranked_candidates"}:
        steps.extend(
            [
                _tour_step("jobs-menu", "Open Recruiter", "Open the job's candidate results.", "results"),
                _tour_step("candidates-table", "Review Candidates", "Use stage, score, and evidence filters to inspect candidates.", "results"),
            ]
        )

    if "shortlist_candidate" in task_intents:
        steps.append(
            _tour_step("shortlist-button", "Shortlist Candidates", "Shortlist only after reviewing the score evidence and candidate fit.", "results")
        )
    if "move_candidates_to_communication" in task_intents:
        steps.extend(
            [
                _tour_step("communication-email-button", "Open Communication", "Move shortlisted candidates into Communication/Outreach.", "communication"),
                _tour_step("communication-email-button", "Preview Outreach", "Check candidate group and message before sending any email.", "communication"),
            ]
        )
    if "move_candidates_to_interview" in task_intents or "schedule_interview" in task_intents:
        steps.extend(
            [
                _tour_step("schedule-interview-button", "Open Interview Dashboard", "Move ready candidates into interview scheduling.", "interviewDashboard"),
                _tour_step("schedule-interview-button", "Add Slot Details", "Add date, time, meeting link, round, and interviewer before scheduling.", "interviewDashboard"),
            ]
        )

    if not steps:
        steps = [
            _tour_step("help-agent-button", "Help Agent", "I will show the right page and guide each step visually."),
            _tour_step("jobs-menu", "Choose Workflow", "Open the related workflow from the dashboard navigation."),
        ]

    return {
        "mode": "visual_tour",
        "summary": _guidance(intent, entities, tasks, []),
        "steps": steps,
        "primary_route": next((step.get("route") for step in steps if step.get("route")), None),
    }


def _extract_candidate_name(message: str) -> str | None:
    if re.search(r"\b(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates)\s+(?:of|for)\b", message, flags=re.I):
        return None
    match = re.search(
        r"\b([A-Z][a-z]{2,})\s+(?:ka|ke|ki)?\s*(?:interview|mail|email|test|profile|score|shortlist|reject)",
        message,
    )
    if match:
        return match.group(1)
    match = re.search(r"\b(?:candidate|profile)\s+([A-Za-z]{2,})\b", message, flags=re.I)
    if not match:
        return None
    value = match.group(1).capitalize()
    return None if value.lower() in {"shortlist", "select", "reject", "show", "find", "list", "upload"} else value


def _stage_from_text(text: str) -> str | None:
    for label, stage in STAGE_ALIASES.items():
        if label in text:
            return stage
    return None


def _has_any_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(r"\b" + re.escape(word) + r"\b", text) for word in words)


def fallback_parse_intent(message: str, current_route: str | None = None, current_context: dict | None = None) -> dict:
    conversation = _conversation_fallback(message)
    if conversation:
        return conversation
    raw = str(message or "")
    text = _norm(raw)
    context = current_context if isinstance(current_context, dict) else {}
    entities = dict(DEFAULT_ENTITIES)
    entities["job_title"] = (
        _extract_job_title(text)
        or _extract_job_title(raw)
        or context.get("job_title")
        or context.get("current_job_title")
    )
    entities["candidate_name"] = _extract_candidate_name(raw)
    entities["email"] = (re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", raw, re.I) or [None])[0]
    entities["limit"] = _extract_limit(text)
    entities["target_stage"] = _target_stage_from_text(text)
    entities["job_id"] = context.get("job_id") or context.get("current_job_id")
    entities["candidate_id"] = context.get("candidate_id")
    context_candidate_ids = context.get("candidate_ids") or context.get("selected_candidate_ids")
    if isinstance(context_candidate_ids, list):
        entities["candidate_ids"] = [str(item).strip() for item in context_candidate_ids if str(item).strip()]
    elif entities["candidate_id"]:
        entities["candidate_ids"] = [str(entities["candidate_id"]).strip()]

    stage = _stage_from_text(text)
    if stage:
        entities["stage"] = stage
        entities["candidate_group"] = stage

    intent = "unknown"
    confidence = 0.25

    filters: dict[str, Any] = {}
    experience_range = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|to|\s)\s*(\d+(?:\.\d+)?)\s*years?", text)
    if experience_range:
        filters["relevant_experience_min"] = float(experience_range.group(1))
        filters["relevant_experience_max"] = float(experience_range.group(2))
    minimum_experience = re.search(r"(?:at\s+least\s+)?(\d+(?:\.\d+)?)\s*\+\s*years?", raw, re.I)
    if minimum_experience and "relevant_experience_min" not in filters:
        filters["relevant_experience_min"] = float(minimum_experience.group(1))
    location_match = re.search(
        r"(?:local\s+to|from|in)\s+([a-z][a-z .-]*?)(?=\s+(?:candidate|candidates|with|having|who|and)\b|$)",
        text,
    )
    if not location_match:
        location_match = re.search(r"(?:show\s+me|find|filter)\s+([a-z][a-z .-]*?)\s+candidates?\b", text)
    if location_match:
        filters["location"] = location_match.group(1).strip().title()
    score_match = re.search(r"(?:score|fit)\s*(?:above|over|>=|at\s+least)\s*(\d+(?:\.\d+)?)", text)
    if score_match:
        filters["score_min"] = float(score_match.group(1))
    score_max_match = re.search(r"(?:score|fit)\s*(?:below|under|<|less\s+than)\s*(\d+(?:\.\d+)?)", text)
    if score_max_match:
        filters["score_max"] = float(score_max_match.group(1))
    skill_match = re.search(r"years?\s+([a-z0-9+#. -]+?)\s+experience\b", text)
    if skill_match:
        skill_phrase = re.sub(r"\b(?:of|in|with|and)\b", " ", skill_match.group(1))
        filters["skills"] = [part for part in skill_phrase.split() if len(part) > 1][:8]
    if not filters:
        with_skill = re.search(
            r"(?:only\s+show|show|find|filter)?\s*(?:me\s+)?(?:the\s+)?(?:top\s+\d+\s+)?candidates?\s+with\s+([a-z0-9+#. -]+?)(?=\s+(?:and|who|with|having)\b|$)",
            text,
        )
        if with_skill:
            filters["skills"] = [part for part in with_skill.group(1).split() if len(part) > 1][:8]
    if filters:
        entities["filters"] = filters

    resume_terms = any(term in text for term in ("resume", "cv", "profile"))
    upload_terms = any(term in text for term in ("upload", "add", "dalna", "dalo", "add karna"))
    selection_requested = _candidate_selection_requested(text)
    all_candidates_requested = bool(re.search(
        r"\b(?:all|every|saare|sare|sabhi|sabi)\s+(?:candidate|candidates|resume|resumes|profile|profiles)\b",
        text,
    ))
    shortlist_action = _shortlist_action_requested(text)
    view_shortlisted = _view_shortlisted_requested(text)
    discovery_match = re.search(
        r"^(?:i\s+want|show\s+me|find|search|get|give\s+me|mujhe)?\s*(.+?)\s+(?:candidate|candidates|profiles|resumes)\s*$",
        text,
    )
    discovery_query = _title_case_job(discovery_match.group(1)) if discovery_match else None
    if re.search(r"\b(?:which|show|list|find)\s+(?:of\s+)?(?:my\s+)?jobs?\s+(?:need|needs|needing|require)\s+attention\b", text):
        intent, confidence = "jobs_needing_attention", 0.96
    elif re.search(r"\b(?:show|list|open)\s+(?:me\s+)?(?:my\s+)?active\s+jobs?\b", text):
        intent, confidence = "view_active_jobs", 0.96
    elif re.search(r"\b(?:how\s+many|show)\s+(?:candidates?|applicants?)\s+(?:applied|today)\b", text):
        intent, confidence = "applicant_metrics", 0.92
    elif re.search(r"\b(?:is|show|check).*\bsourcing\s+(?:approved|approval|status)\b", text):
        intent, confidence = "view_sourcing_status", 0.92
    elif filters and re.search(r"\breject\b", text):
        intent, confidence = "candidate_workflow", 0.94
        entities["candidate_group"] = "filtered"
        entities["target_stage"] = "rejected"
    elif filters and _has_any_word(text, ("show", "find", "filter", "candidate", "candidates", "profiles")):
        intent, confidence = "filter_candidates", 0.93
        entities["candidate_group"] = "filtered"
    elif discovery_query and not any(term in text for term in ("top ", "shortlist", "reject", " job", " of ", " for ")):
        intent, confidence = "search_talent", 0.9
        entities["search_query"] = discovery_query
        entities["candidate_group"] = "all"
        entities["job_id"] = None
        entities["job_title"] = None
    elif all_candidates_requested:
        intent, confidence = "view_candidates_by_stage", 0.94
        entities["candidate_group"] = "all"
        entities["stage"] = None
    elif selection_requested and entities["target_stage"] in {"communication", "interview_scheduling"}:
        intent, confidence = "candidate_workflow", 0.92
        entities["candidate_group"] = "top_candidates"
    elif shortlist_action:
        intent, confidence = "candidate_workflow", 0.9
        entities["candidate_group"] = "top_candidates"
        entities["target_stage"] = "shortlisted"
    elif selection_requested:
        intent, confidence = "select_top_candidates", 0.88
        entities["candidate_group"] = "top_candidates"
    elif view_shortlisted and _has_any_word(text, ("want", "show", "view", "list", "candidate", "candidates")):
        intent, confidence = "view_shortlisted_candidates", 0.9
        entities["stage"] = "shortlisted"
        entities["candidate_group"] = "shortlisted"
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
    elif entities["target_stage"] == "communication":
        intent, confidence = "move_candidates_to_communication", 0.82
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
    response_type = str(data.get("response_type") or "").strip().lower()
    intent = str(data.get("intent") or "unknown").strip()
    if intent not in SUPPORTED_INTENTS:
        intent = "unknown"
    if response_type not in {"conversation", "workflow", "clarification"}:
        response_type = "workflow" if intent != "unknown" else "clarification"
    assistant_reply = _friendly_user_text(data.get("assistant_reply") or data.get("reply"))
    if response_type == "conversation":
        intent = "unknown"
    entities = dict(DEFAULT_ENTITIES)
    incoming_entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
    for key in entities:
        value = incoming_entities.get(key)
        if key == "filters":
            validated_filters: dict[str, Any] = {}
            if isinstance(value, dict):
                for numeric_key in (
                    "relevant_experience_min", "relevant_experience_max", "score_min", "score_max", "recency_days"
                ):
                    try:
                        if value.get(numeric_key) is not None:
                            validated_filters[numeric_key] = max(0.0, float(value[numeric_key]))
                    except (TypeError, ValueError):
                        pass
                location = _friendly_user_text(value.get("location"))
                if location:
                    validated_filters["location"] = location[:120]
                skills = value.get("skills")
                if isinstance(skills, list):
                    validated_filters["skills"] = [
                        str(item).strip()[:80] for item in skills[:10] if str(item).strip()
                    ]
            entities[key] = validated_filters or None
        elif key == "limit":
            try:
                entities[key] = max(1, min(int(value), 100)) if value is not None and str(value).strip() else None
            except (TypeError, ValueError):
                entities[key] = None
        elif key == "candidate_ids":
            if isinstance(value, list):
                entities[key] = [str(item).strip() for item in value if str(item).strip()]
            elif isinstance(value, str) and value.strip():
                entities[key] = [item.strip() for item in value.split(",") if item.strip()]
            else:
                entities[key] = None
        else:
            entities[key] = str(value).strip() if isinstance(value, str) and value.strip() else None

    if intent == "view_shortlisted_candidates":
        entities["candidate_group"] = entities["candidate_group"] or "shortlisted"
        entities["stage"] = entities["stage"] or "shortlisted"
    if intent in {"candidate_workflow", "select_top_candidates"}:
        entities["candidate_group"] = entities["candidate_group"] or "top_candidates"

    try:
        confidence = float(data.get("confidence", 0.2))
    except (TypeError, ValueError):
        confidence = 0.2
    confidence = max(0.0, min(1.0, confidence))
    clarification_needed = response_type == "clarification" or (
        response_type == "workflow" and (bool(data.get("clarification_needed")) or intent == "unknown" or confidence < 0.55)
    )
    clarification_question = data.get("clarification_question")
    if clarification_question is not None:
        clarification_question = _friendly_user_text(clarification_question)

    incoming_tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
    model_tasks = [
        {
            "intent": str(task.get("intent") or "").strip(),
            "description": str(task.get("description") or "").strip(),
            "entities": task.get("entities") if isinstance(task.get("entities"), dict) else {},
        }
        for task in incoming_tasks
        if isinstance(task, dict) and str(task.get("intent") or "").strip() in SUPPORTED_INTENTS
    ]
    tasks = _workflow_tasks(intent, entities) if response_type == "workflow" else []
    known_task_intents = {task["intent"] for task in tasks}
    for task in model_tasks:
        if task["intent"] not in known_task_intents:
            tasks.append(task)
            known_task_intents.add(task["intent"])

    # Language understanding belongs to AI; executable endpoint compilation
    # belongs to the trusted backend and is never accepted from model output.
    actions = _action_plan(tasks, entities) if response_type == "workflow" else []

    missing_fields = data.get("missing_fields") if isinstance(data.get("missing_fields"), list) else []
    missing_fields = [str(item).strip() for item in missing_fields if str(item).strip()]
    for field in _missing_fields_for_actions(actions, entities):
        if field not in missing_fields:
            missing_fields.append(field)

    requires_confirmation = bool(data.get("requires_confirmation")) or any(
        bool(action.get("requires_confirmation")) for action in actions
    )
    ready_for_action_agent = bool(actions) and not missing_fields and not clarification_needed
    visual_tour = data.get("visual_tour") if isinstance(data.get("visual_tour"), dict) else _visual_tour(intent, tasks, entities)

    return {
        "agent_contract_version": AGENT_CONTRACT_VERSION,
        "understanding_source": str(data.get("understanding_source") or "deterministic"),
        "response_type": response_type,
        "assistant_reply": assistant_reply,
        "agent_mode": "guide",
        "intent": intent,
        "entities": entities,
        "confidence": confidence,
        "tasks": tasks,
        "visual_tour": visual_tour,
        "actions": actions,
        "action_agent_plan": {
            "enabled": ready_for_action_agent,
            "requires_confirmation": requires_confirmation,
            "actions": actions,
            "missing_fields": missing_fields,
        },
        "missing_fields": missing_fields,
        "requires_confirmation": requires_confirmation,
        "ready_for_action_agent": ready_for_action_agent,
        "clarification_needed": clarification_needed or bool(missing_fields),
        "clarification_question": clarification_question,
        "guidance": str(data.get("guidance") or "").strip() or _guidance(intent, entities, tasks, missing_fields),
    }


def _merge_with_fallback(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    """Keep AI intent, but never drop deterministic entities extracted from the same text."""
    if not fallback:
        return primary
    if fallback.get("response_type") == "conversation":
        return fallback
    merged = dict(primary)
    if (
        primary.get("response_type") == "clarification"
        and fallback.get("response_type") == "workflow"
        and float(fallback.get("confidence") or 0) >= 0.8
    ):
        merged.update({
            "response_type": "workflow",
            "intent": fallback.get("intent"),
            "tasks": fallback.get("tasks") or [],
            "actions": fallback.get("actions") or [],
            "missing_fields": fallback.get("missing_fields") or [],
            "clarification_needed": False,
            "clarification_question": None,
            "assistant_reply": None,
            "guidance": fallback.get("guidance"),
            "confidence": fallback.get("confidence"),
        })
    primary_entities = dict(primary.get("entities") or {})
    fallback_entities = fallback.get("entities") or {}
    for key, value in fallback_entities.items():
        has_primary = primary_entities.get(key) not in (None, "", [])
        has_fallback = value not in (None, "", [])
        if not has_primary and has_fallback:
            primary_entities[key] = value

    if primary.get("intent") in {"unknown", None, ""} and fallback.get("intent") not in {"unknown", None, ""}:
        merged["intent"] = fallback["intent"]
        merged["confidence"] = max(float(primary.get("confidence") or 0), float(fallback.get("confidence") or 0))
        merged["clarification_needed"] = fallback.get("clarification_needed", False)
        merged["clarification_question"] = fallback.get("clarification_question")

    merged["entities"] = primary_entities
    normalized = normalize_intent_response(merged)
    clarification_text = " ".join(filter(None, [
        normalized.get("assistant_reply"),
        normalized.get("clarification_question"),
    ])).lower()
    if (
        normalized.get("response_type") == "clarification"
        and normalized["entities"].get("job_title")
        and not normalized["entities"].get("candidate_name")
        and "candidate" in clarification_text
        and any(term in clarification_text for term in ("all", "top", "shortlist", "specific"))
    ):
        normalized = normalize_intent_response({
            **normalized,
            "response_type": "workflow",
            "intent": "view_candidates_by_stage",
            "entities": {**normalized["entities"], "candidate_group": "all", "stage": None},
            "assistant_reply": f"I’ll show all candidates for the {normalized['entities']['job_title']} job.",
            "clarification_needed": False,
            "clarification_question": None,
            "confidence": max(float(normalized.get("confidence") or 0), 0.8),
        })
    fallback_group = (fallback.get("entities") or {}).get("candidate_group")
    if (
        fallback_group in {"top_candidates", "all", "shortlisted"}
        and not normalized["entities"].get("candidate_name")
        and normalized.get("intent") in {"view_candidate_profile", "explain_candidate_score"}
    ):
        group_intent = "view_shortlisted_candidates" if fallback_group == "shortlisted" else "review_ai_ranked_candidates"
        normalized = normalize_intent_response({
            **fallback,
            "response_type": "workflow",
            "intent": group_intent,
            "entities": {**fallback.get("entities", {}), **normalized.get("entities", {})},
            "assistant_reply": primary.get("assistant_reply"),
            "guidance": primary.get("guidance") or fallback.get("guidance"),
            "confidence": max(float(normalized.get("confidence") or 0), float(fallback.get("confidence") or 0)),
            "clarification_needed": False,
            "clarification_question": None,
        })
    if fallback.get("intent") == "candidate_workflow" and primary.get("intent") in {"shortlist_candidate", "view_shortlisted_candidates", "unknown"}:
        normalized = normalize_intent_response({**normalized, "intent": "candidate_workflow", "entities": normalized["entities"], "confidence": max(normalized["confidence"], 0.9)})
    return normalized


@lru_cache(maxsize=1)
def _client():
    api_key = os.getenv("OPENAI_API_KEY") or get_settings().openai_api_key
    if not api_key:
        return None
    return OpenAI(api_key=api_key, timeout=12, max_retries=1)


def _model() -> str:
    return os.getenv("OPENAI_HELP_INTENT_MODEL", "gpt-4.1")


def parse_intent(message: str, current_route: str | None = None, current_context: dict | None = None) -> dict:
    fallback = fallback_parse_intent(message, current_route, current_context)
    client = _client()
    if client is None:
        return {
            **fallback,
            "understanding_source": "fallback",
            "ai_runtime": "not_configured",
            "ai_telemetry": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "model": None},
        }

    system = (
        "You are HireScore AI's conversational hiring copilot and task planner. Return JSON only. "
        "First classify response_type as conversation, workflow, or clarification. "
        "Respond like a capable, concise hiring copilot, not a menu bot. Use conversation_history for follow-ups and references. "
        "For greetings, thanks, casual conversation, product questions, or how-to questions, use response_type conversation and write a useful natural assistant_reply, "
        "set intent unknown, and return no tasks or actions. Never select a job for a greeting. "
        "For an actionable ATS request, use response_type workflow and parse the user's intent, entities, and ordered semantic tasks. "
        "The backend compiles executable actions; do not invent methods, endpoints, or payloads. "
        "For an ambiguous ATS request, use response_type clarification with assistant_reply containing one focused question and no executable actions. "
        "Never ask the user for internal job_id or candidate_id values. Users know job titles, company names, locations, and candidate names; "
        "the server resolves internal IDs. If titles are ambiguous, ask the user to choose a friendly job option. "
        "If the user asks for all candidates of a named job, use response_type workflow, intent view_candidates_by_stage, candidate_group all, "
        "extract the job_title, and do not ask for job_id because the server resolves exact titles. "
        "Candidate cardinality is strict: top N, all, shortlisted, or plural candidate requests are groups, not one candidate. "
        "For score explanations of a group, use review_ai_ranked_candidates with candidate_group and limit; never ask the user to choose one candidate. "
        "If a user simply asks to see candidates for a named job without a requested action or filter, default to intent view_candidates_by_stage "
        "with candidate_group all. Do not ask whether they mean all/top/shortlisted unless their wording genuinely conflicts. "
        "Do not invent job IDs or candidate IDs when they are not present in current_context. "
        "Understand English, Hinglish, broken English, typos, and ATS/recruitment terms. "
        "Supported intents: " + ", ".join(sorted(SUPPORTED_INTENTS)) + ". "
        "Entity fields: job_title, job_id, candidate_name, candidate_ids, candidate_group, stage, target_stage, date_time, meeting_url, email, plan, limit. "
        "For candidate filters, use intent filter_candidates and entities.filters with only relevant_experience_min, relevant_experience_max, location, score_min, skills, and recency_days. "
        "For requests such as 'data science candidates', 'find Python profiles', or role/skill candidate discovery without a specific job, "
        "use intent search_talent and put the natural role/skill phrase in entities.search_query. This searches candidates across jobs. "
        "For requests like 'top 10 candidates for Data Analyst and move them to communication', use intent candidate_workflow "
        "with semantic tasks select_top_candidates then move_candidates_to_communication. "
        "For requests like 'shortlist candidate of Data Analyst job', use intent candidate_workflow, entities.job_title Data Analyst, candidate_group top_candidates, and do not use view_shortlisted_candidates. "
        "For interview scheduling requests, include move_candidates_to_interview and schedule_interview tasks, and mark scheduled_at/meeting_url missing if absent. "
        "Only for already-shortlisted candidate list requests like 'show shortlisted candidates', use intent view_shortlisted_candidates, candidate_group shortlisted, stage shortlisted, and candidate_name null."
    )
    user_payload = {
        "message": message,
        "current_route": current_route,
        "current_context": current_context or {},
        "response_shape": {
            "response_type": "conversation | workflow | clarification",
            "assistant_reply": "natural language response to show the user",
            "intent": "string",
            "entities": DEFAULT_ENTITIES,
            "tasks": [{"intent": "string", "description": "string", "entities": DEFAULT_ENTITIES}],
            "missing_fields": ["string"],
            "requires_confirmation": "boolean",
            "ready_for_action_agent": "boolean",
            "confidence": "number 0..1",
            "clarification_needed": "boolean",
            "clarification_question": "string or null",
            "guidance": "string",
        },
    }
    try:
        started_at = time.perf_counter()
        response = client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.15,
            max_tokens=1200,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        parsed["understanding_source"] = "openai"
        result = _merge_with_fallback(normalize_intent_response(parsed), fallback)
        result["understanding_source"] = "openai"
        result["ai_runtime"] = "active"
        usage = getattr(response, "usage", None)
        result["ai_telemetry"] = {
            "calls": 1,
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "model": _model(),
            "latency_ms": round((time.perf_counter() - started_at) * 1000),
        }
        return result
    except Exception as exc:
        logger.warning("Help Agent AI planning failed; using deterministic fallback: %s", exc.__class__.__name__)
        return {
            **fallback,
            "understanding_source": "fallback",
            "ai_runtime": "error",
            "ai_telemetry": {"calls": 1, "input_tokens": 0, "output_tokens": 0, "model": _model()},
        }
