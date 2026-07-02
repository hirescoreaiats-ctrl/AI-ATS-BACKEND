from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from openai import OpenAI

from backend.core.config import get_settings


SUPPORTED_INTENTS = {
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
    "job_title": None,
    "candidate_name": None,
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


def _norm(value: str | None) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[._-]+", " ", text)
    text = re.sub(r"\bupl\s*aod\b|\buplod\b|\buplaod\b", "upload", text)
    text = re.sub(r"\bcandiate\b|\bcandiadte\b", "candidate", text)
    text = re.sub(r"\bcommincation\b|\bcommuncation\b|\bcomunication\b", "communication", text)
    text = re.sub(r"\bshedule\b|\bsehdule\b", "schedule", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_case_job(value: str | None) -> str | None:
    value = re.sub(
        r"\b(the|this|that|of|for|in|job|jobs|mujhe|muje|please|top|candidate|candidates|candiate|"
        r"want|you|to|give|get|nikal|nikalo|find|show|list|do|de|bhej|send|unha|unhe|unka|aur|and|or|interview|"
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
        r"(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates|resume|profile)s?\s+(?:of|for)\s+([a-z0-9 .+#-]+)",
        r"(?:give|get|show|find|list)\s+(?:me\s+)?(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates|resume|profile)s?\s+(?:of|for)\s+([a-z0-9 .+#-]+)",
        r"(?:candidate|candidates)\s+(?:nikal|nikalo|find|show|list|de do|do)\s+([a-z0-9 .+#-]+?)\s+(?:ke|kai|kay|for)\s*(?:liye|lia|liya)?\b",
        r"([a-z0-9 .+#-]+?)\s+(?:ke|kai|kay)\s+(?:liye|lia|liya)\s+(?:top\s*)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:candidate|candidates|resume|profile)",
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


def _extract_limit(text: str) -> int | None:
    patterns = [
        r"\btop\s+(\d{1,3})\b",
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
    return None


def _target_stage_from_text(text: str) -> str | None:
    if any(term in text for term in ("interview", "schedule call", "meeting schedule", "call schedule")):
        return "interview_scheduling"
    if any(term in text for term in ("communication", "outreach")):
        return "communication"
    return _stage_from_text(text)


def _candidate_selection_requested(text: str) -> bool:
    selection_terms = (
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


def _workflow_tasks(intent: str, entities: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    target_stage = entities.get("target_stage") or entities.get("stage")
    limit = entities.get("limit")

    if intent in {"candidate_workflow", "select_top_candidates", "review_ai_ranked_candidates"}:
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
    context_candidate_ids = context.get("candidate_ids") or context.get("selected_candidate_ids")
    if isinstance(context_candidate_ids, list):
        entities["candidate_ids"] = [str(item).strip() for item in context_candidate_ids if str(item).strip()]

    stage = _stage_from_text(text)
    if stage:
        entities["stage"] = stage
        entities["candidate_group"] = stage

    intent = "unknown"
    confidence = 0.25

    resume_terms = any(term in text for term in ("resume", "cv", "profile"))
    upload_terms = any(term in text for term in ("upload", "add", "dalna", "dalo", "add karna"))
    selection_requested = _candidate_selection_requested(text)
    if selection_requested and entities["target_stage"] in {"communication", "interview_scheduling"}:
        intent, confidence = "candidate_workflow", 0.92
        entities["candidate_group"] = "top_candidates"
    elif selection_requested:
        intent, confidence = "select_top_candidates", 0.88
        entities["candidate_group"] = "top_candidates"
    elif stage == "shortlisted" and _has_any_word(text, ("want", "show", "view", "list", "candidate", "candidates")):
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
    intent = str(data.get("intent") or "unknown").strip()
    if intent not in SUPPORTED_INTENTS:
        intent = "unknown"
    entities = dict(DEFAULT_ENTITIES)
    incoming_entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
    for key in entities:
        value = incoming_entities.get(key)
        if key == "limit":
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
    clarification_needed = bool(data.get("clarification_needed")) or intent == "unknown" or confidence < 0.55
    clarification_question = data.get("clarification_question")
    if clarification_question is not None:
        clarification_question = str(clarification_question).strip() or None

    incoming_tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
    tasks = [
        {
            "intent": str(task.get("intent") or "").strip(),
            "description": str(task.get("description") or "").strip(),
            "entities": task.get("entities") if isinstance(task.get("entities"), dict) else {},
        }
        for task in incoming_tasks
        if isinstance(task, dict) and str(task.get("intent") or "").strip() in SUPPORTED_INTENTS
    ]
    if not tasks:
        tasks = _workflow_tasks(intent, entities)

    incoming_actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    actions = [action for action in incoming_actions if isinstance(action, dict) and action.get("action_id")]
    if not actions:
        actions = _action_plan(tasks, entities)

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
        "You are HireScore AI's helping agent planner. Return JSON only. "
        "Parse the user's intent, entities, multi-step workflow tasks, and action-agent plan. "
        "Do not invent job IDs or candidate IDs when they are not present in current_context. "
        "Understand English, Hinglish, broken English, typos, and ATS/recruitment terms. "
        "Supported intents: " + ", ".join(sorted(SUPPORTED_INTENTS)) + ". "
        "Entity fields: job_title, job_id, candidate_name, candidate_ids, candidate_group, stage, target_stage, date_time, meeting_url, email, plan, limit. "
        "For requests like 'top 10 candidates for Data Analyst and move them to communication', use intent candidate_workflow, "
        "tasks select_top_candidates then move_candidates_to_communication, and action-agent endpoints /results/{job_id} then /move-to-communication. "
        "For interview scheduling requests, include move_candidates_to_interview and schedule_interview tasks, and mark scheduled_at/meeting_url missing if absent. "
        "For shortlisted candidate list requests, use intent view_shortlisted_candidates, candidate_group shortlisted, stage shortlisted, and candidate_name null."
    )
    user_payload = {
        "message": message,
        "current_route": current_route,
        "current_context": current_context or {},
        "response_shape": {
            "intent": "string",
            "entities": DEFAULT_ENTITIES,
            "tasks": [{"intent": "string", "description": "string", "entities": DEFAULT_ENTITIES}],
            "actions": [{"action_id": "string", "actor": "action_agent", "method": "string", "endpoint": "string"}],
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
        response = client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=700,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return normalize_intent_response(parsed)
    except Exception:
        return fallback
