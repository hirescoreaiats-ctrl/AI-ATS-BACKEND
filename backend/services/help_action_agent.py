from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status
from sqlalchemy import false, func, or_

from backend.ai.search import hybrid_candidate_rank
from backend.core.config import get_settings
from backend.core.security import decode_token
from backend.models import AuditLog, CandidateStageHistory, Interview, Job, Resume, User
from backend.repositories.audit_repository import write_audit_log, write_candidate_activity
from backend.services.candidate_intelligence import from_json_text
from backend.services.help_intent import parse_intent


GLOBAL_ROLES = {"admin", "super_admin"}
SERVER_ACTIONS = {
    "filter_candidates",
    "list_active_jobs",
    "list_jobs_needing_attention",
    "get_applicant_metrics",
    "get_sourcing_status",
    "search_talent",
    "find_top_candidates",
    "shortlist_candidates",
    "reject_candidates",
    "move_to_communication",
    "move_to_interview_scheduling",
    "schedule_interview_slot",
}
READ_ONLY_ACTIONS = {
    "filter_candidates", "find_top_candidates", "search_talent", "list_active_jobs",
    "list_jobs_needing_attention", "get_applicant_metrics", "get_sourcing_status",
}
MUTATING_ACTIONS = SERVER_ACTIONS - READ_ONLY_ACTIONS
MAX_MUTATION_CANDIDATES = 25
CONFIRMATION_MINUTES = 10


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", str(value or "").lower()).strip()


def _audit_plan(db, user: User, message: str, result: dict[str, Any]) -> None:
    telemetry = result.get("ai_telemetry") if isinstance(result.get("ai_telemetry"), dict) else {}
    write_audit_log(
        db,
        action="help_agent.intent_planned",
        entity_type="conversation",
        actor_user_id=user.id,
        organization_id=getattr(user, "organization_id", None),
        metadata={
            "message_sha256": hashlib.sha256(message.encode("utf-8", errors="ignore")).hexdigest(),
            "message_chars": len(message),
            "intent": result.get("intent"),
            "response_type": result.get("response_type"),
            "confidence": result.get("confidence"),
            "understanding_source": result.get("understanding_source"),
            "ai_runtime": result.get("ai_runtime"),
            "ai_calls": telemetry.get("calls", 0),
            "input_tokens": telemetry.get("input_tokens", 0),
            "output_tokens": telemetry.get("output_tokens", 0),
            "model": telemetry.get("model"),
            "latency_ms": telemetry.get("latency_ms"),
        },
    )
    db.commit()


def _visible_jobs_query(db, user: User):
    query = db.query(Job)
    if (getattr(user, "role", None) or "").lower() in GLOBAL_ROLES:
        return query
    organization_id = getattr(user, "organization_id", None)
    if not organization_id:
        return query.filter(false())
    return query.filter(Job.organization_id == organization_id)


def _job_options(jobs: list[Job]) -> list[dict[str, Any]]:
    return [
        {
            "id": job.id,
            "job_title": job.job_title,
            "company_name": job.company_name,
            "location": job.location,
            "is_active": bool(job.is_active),
        }
        for job in jobs[:8]
    ]


def _resolve_job(db, user: User, entities: dict[str, Any]) -> tuple[Job | None, list[dict[str, Any]]]:
    job_id = str(entities.get("job_id") or "").strip()
    if job_id:
        job = _visible_jobs_query(db, user).filter(Job.id == job_id).first()
        return job, []

    title = _normalized(entities.get("job_title"))
    jobs = _visible_jobs_query(db, user).order_by(Job.is_active.desc(), Job.created_at.desc()).all()
    if not title:
        return None, _job_options(jobs)

    requested_tokens = set(title.split())
    ranked: list[tuple[float, Job]] = []
    for job in jobs:
        candidate_title = _normalized(job.job_title or job.role)
        if not candidate_title:
            continue
        candidate_tokens = set(candidate_title.split())
        if candidate_title == title:
            score = 100.0
        elif title in candidate_title or candidate_title in title:
            score = 80.0 + min(len(requested_tokens & candidate_tokens), 10)
        else:
            union = requested_tokens | candidate_tokens
            score = (len(requested_tokens & candidate_tokens) / len(union) * 70.0) if union else 0.0
        if score >= 35:
            ranked.append((score, job))

    ranked.sort(key=lambda item: (item[0], bool(item[1].is_active), item[1].created_at or datetime.min), reverse=True)
    if not ranked:
        return None, []
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 8:
        return None, _job_options([item[1] for item in ranked])
    return ranked[0][1], []


def _candidate_payload(candidate: Resume) -> dict[str, Any]:
    def list_field(value: Any) -> list[str]:
        parsed = from_json_text(value, [])
        if isinstance(parsed, str):
            parsed = [item.strip() for item in parsed.split(",") if item.strip()]
        return [str(item).strip() for item in (parsed or []) if str(item).strip()][:6]

    return {
        "id": candidate.id,
        "job_id": candidate.job_id,
        "full_name": candidate.full_name or candidate.form_full_name or "Candidate",
        "email": candidate.email or candidate.form_email,
        "designation": candidate.designation,
        "final_score": candidate.final_score or 0,
        "rank_score": candidate.rank_score or candidate.final_score or 0,
        "fit_band": candidate.fit_band,
        "stage": candidate.stage,
        "status": candidate.status,
        "ranking_reason": candidate.ranking_reason,
        "recruiter_explanation": candidate.recruiter_explanation or candidate.ranking_reason or candidate.decision_reason,
        "strengths": list_field(candidate.strengths),
        "concerns": list_field(candidate.concerns),
        "matched_skills": list_field(candidate.matched_skills),
        "missing_skills": list_field(candidate.missing_skills),
        "recommendation": candidate.ai_recommendation or candidate.shortlist_decision or candidate.status,
        "relevant_experience_years": (
            candidate.direct_relevant_experience_years
            or candidate.relevant_experience_years
            or candidate.total_experience_years
        ),
        "location": candidate.location or candidate.form_location,
    }


def _candidate_fit_reply(candidate: Resume, job: Job | None) -> str:
    payload = _candidate_payload(candidate)
    name = payload["full_name"]
    role = (job.job_title or job.role) if job else "this role"
    try:
        score = float(payload.get("rank_score") or payload.get("final_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    fit_band = str(payload.get("fit_band") or "review").strip()
    reason = str(payload.get("recruiter_explanation") or payload.get("ranking_reason") or "").strip()
    strengths = payload.get("strengths") or []
    concerns = payload.get("concerns") or []
    matched = payload.get("matched_skills") or []
    parts = [f"{name} is rated {score:g}/100 ({fit_band}) for {role} based on stored ATS evidence."]
    if reason:
        parts.append(reason)
    if matched:
        parts.append("Matched skills: " + ", ".join(matched) + ".")
    if strengths:
        parts.append("Key strengths: " + "; ".join(strengths) + ".")
    if concerns:
        parts.append("Points to verify: " + "; ".join(concerns) + ".")
    return " ".join(parts)


def _job_payload(db, job: Job) -> dict[str, Any]:
    candidates = db.query(Resume).filter(Resume.job_id == job.id, Resume.is_active == True).all()
    scores = [float(item.rank_score or item.final_score or 0) for item in candidates]
    waiting = sum(1 for item in candidates if str(item.stage or "").lower() in {"", "review", "reviewed"})
    return {
        "id": job.id,
        "job_title": job.job_title or job.role or "Untitled Job",
        "company_name": job.company_name,
        "location": job.location,
        "work_mode": job.work_mode,
        "status": job.status or ("active" if job.is_active else "inactive"),
        "is_active": bool(job.is_active),
        "applicant_count": len(candidates),
        "top_score": max(scores) if scores else None,
        "waiting_for_action": waiting,
        "sourcing_requested": bool(job.sourcing_requested),
        "sourcing_approval_status": job.sourcing_approval_status,
    }


def _agent_ui_contract(result: dict[str, Any]) -> dict[str, Any]:
    candidates = result.get("candidate_preview") if isinstance(result.get("candidate_preview"), list) else []
    jobs = result.get("job_preview") if isinstance(result.get("job_preview"), list) else []
    confirmation = result.get("confirmation") if isinstance(result.get("confirmation"), dict) else None
    if confirmation:
        kind = "confirmation_request"
    elif candidates:
        kind = "candidate_results"
    elif jobs:
        kind = "job_results"
    elif result.get("status") == "completed":
        kind = "completed_action"
    elif result.get("response_type") == "clarification":
        kind = "recovery"
    else:
        kind = "conversational_answer"
    navigation = result.get("navigation") if isinstance(result.get("navigation"), dict) else None
    return {
        **result,
        "result_schema_version": "2026-08-agent-ui-v1",
        "ui": {
            "kind": kind,
            "candidate_cards": candidates,
            "job_cards": jobs,
            "navigation": navigation,
            "confirmation": confirmation,
            "metrics": result.get("metrics") if isinstance(result.get("metrics"), dict) else {},
        },
    }


def _candidate_query(db, user: User, job_id: str | None = None):
    query = db.query(Resume).join(Job, Resume.job_id == Job.id).filter(Resume.is_active == True)
    if (getattr(user, "role", None) or "").lower() not in GLOBAL_ROLES:
        organization_id = getattr(user, "organization_id", None)
        if not organization_id:
            query = query.filter(false())
        else:
            query = query.filter(Job.organization_id == organization_id)
    if job_id:
        query = query.filter(Resume.job_id == job_id)
    return query


def _resolve_candidates(
    db,
    user: User,
    result: dict[str, Any],
    job: Job | None,
    action_ids: list[str],
) -> list[Resume]:
    entities = result.get("entities") or {}
    explicit_ids = [str(item) for item in (entities.get("candidate_ids") or []) if str(item).strip()]
    query = _candidate_query(db, user, job.id if job else None)
    if explicit_ids:
        query = query.filter(Resume.id.in_(explicit_ids)).order_by(
            func.coalesce(Resume.rank_score, Resume.final_score, 0).desc()
        )
        requested_limit = entities.get("limit")
        if requested_limit is not None:
            query = query.limit(min(max(int(requested_limit), 1), 100))
        return query.all()

    candidate_name = _normalized(entities.get("candidate_name"))
    if candidate_name:
        rows = query.filter(
            func.lower(func.coalesce(Resume.full_name, Resume.form_full_name, "")).like(f"%{candidate_name}%")
        ).limit(20).all()
        if len(rows) == 1:
            return rows
        return []

    if result.get("intent") == "filter_candidates" or "filter_candidates" in action_ids:
        filters = entities.get("filters") if isinstance(entities.get("filters"), dict) else {}
        allowed = {
            "relevant_experience_min", "relevant_experience_max", "location", "score_min", "score_max", "skills", "recency_days"
        }
        filters = {key: value for key, value in filters.items() if key in allowed}
        relevant_years = func.coalesce(
            Resume.direct_relevant_experience_years,
            Resume.relevant_experience_years,
            Resume.total_experience_years,
            0,
        )
        if filters.get("relevant_experience_min") is not None:
            query = query.filter(relevant_years >= float(filters["relevant_experience_min"]))
        if filters.get("relevant_experience_max") is not None:
            query = query.filter(relevant_years <= float(filters["relevant_experience_max"]))
        if filters.get("score_min") is not None:
            query = query.filter(func.coalesce(Resume.rank_score, Resume.final_score, 0) >= float(filters["score_min"]))
        if filters.get("score_max") is not None:
            query = query.filter(func.coalesce(Resume.rank_score, Resume.final_score, 0) < float(filters["score_max"]))
        location = str(filters.get("location") or "").strip()
        if location:
            pattern = f"%{location.lower()}%"
            query = query.filter(or_(
                func.lower(func.coalesce(Resume.location, "")).like(pattern),
                func.lower(func.coalesce(Resume.form_location, "")).like(pattern),
                func.lower(func.coalesce(Resume.preferred_location, "")).like(pattern),
            ))
        skills = filters.get("skills") if isinstance(filters.get("skills"), list) else []
        for skill in [str(item).strip().lower() for item in skills[:10] if str(item).strip()]:
            pattern = f"%{skill}%"
            query = query.filter(or_(
                func.lower(func.coalesce(Resume.key_skills, "")).like(pattern),
                func.lower(func.coalesce(Resume.matched_skills, "")).like(pattern),
                func.lower(func.coalesce(Resume.designation, "")).like(pattern),
            ))
        if filters.get("recency_days") is not None:
            days = min(max(int(filters["recency_days"]), 1), 3650)
            query = query.filter(Resume.created_at >= datetime.utcnow() - timedelta(days=days))
        limit = min(max(int(entities.get("limit") or 10), 1), 100)
        return query.order_by(func.coalesce(Resume.rank_score, Resume.final_score, 0).desc()).limit(limit).all()

    intent = result.get("intent")
    if intent == "search_talent" or "search_talent" in action_ids:
        search_query = str(entities.get("search_query") or "").strip()
        if not search_query:
            return []
        rows = query.order_by(Resume.created_at.desc()).limit(500).all()
        limit = min(max(int(entities.get("limit") or 10), 1), 25)
        terms = [term for term in _normalized(search_query).split() if len(term) > 2]
        lexical_ranked: list[tuple[float, str]] = []
        for row in rows:
            haystack = _normalized(" ".join([
                row.designation or "", row.key_skills or "", row.domain or "", (row.resume_text or "")[:12000]
            ]))
            hits = sum(1 for term in terms if term in haystack)
            if not hits:
                continue
            lexical_score = (hits / max(len(terms), 1)) + ((row.rank_score or row.final_score or 0) / 500)
            lexical_ranked.append((lexical_score, row.id))
        lexical_ranked.sort(reverse=True)
        if lexical_ranked:
            ranked_ids = [candidate_id for _, candidate_id in lexical_ranked[:limit]]
        else:
            ranked = hybrid_candidate_rank(search_query, rows)
            ranked_ids = [
                item["resume_id"]
                for item in ranked
                if float(item.get("semantic_score") or 0) >= 0.25
            ][:limit]
        rows_by_id = {row.id: row for row in rows}
        return [rows_by_id[candidate_id] for candidate_id in ranked_ids if candidate_id in rows_by_id]
    if not job:
        return []
    if intent == "view_shortlisted_candidates":
        query = query.filter((Resume.stage == "shortlisted") | (Resume.status == "Shortlisted"))
    elif intent == "view_candidates_by_stage" and entities.get("stage"):
        query = query.filter(Resume.stage == entities["stage"])
    elif "find_top_candidates" in action_ids:
        query = query.filter(~Resume.status.in_(["Rejected", "Dropped", "Communication"]))
    else:
        return []

    limit = min(max(int(entities.get("limit") or 10), 1), 100)
    return query.order_by(
        func.coalesce(Resume.rank_score, Resume.final_score, 0).desc(),
        Resume.created_at.asc(),
    ).limit(limit).all()


def _confirmation_token(user: User, job: Job, candidates: list[Resume], action_ids: list[str], entities: dict[str, Any]) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.utcnow() + timedelta(minutes=CONFIRMATION_MINUTES)
    payload = {
        "purpose": "help_action_confirmation",
        "sub": user.id,
        "organization_id": getattr(user, "organization_id", None),
        "job_id": job.id,
        "candidate_ids": [candidate.id for candidate in candidates],
        "actions": action_ids,
        "parameters": {
            "scheduled_at": entities.get("date_time"),
            "meeting_url": entities.get("meeting_url"),
        },
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_at


def _prepare_action_agent(
    *,
    message: str,
    current_route: str | None,
    current_context: dict[str, Any] | None,
    db,
    user: User,
) -> dict[str, Any]:
    result = parse_intent(message, current_route, current_context or {})
    _audit_plan(db, user, message, result)
    if result.get("response_type") != "workflow":
        result["tasks"] = []
        result["actions"] = []
        result["candidate_preview"] = []
        result["job_options"] = []
        result["confirmation"] = None
        result["missing_fields"] = []
        result["requires_confirmation"] = False
        result["ready_for_action_agent"] = False
        result["clarification_needed"] = result.get("response_type") == "clarification"
        result["action_agent_plan"] = {
            "enabled": False,
            "actions": [],
            "missing_fields": [],
            "requires_confirmation": False,
        }
        return result
    entities = dict(result.get("entities") or {})
    raw_actions = result.get("actions") if isinstance(result.get("actions"), list) else []
    action_ids = [
        action.get("action_id")
        for action in raw_actions
        if isinstance(action, dict) and action.get("action_id") in SERVER_ACTIONS
    ]

    if result.get("intent") in {"view_active_jobs", "jobs_needing_attention", "applicant_metrics"}:
        jobs = _visible_jobs_query(db, user).filter(Job.is_active == True).order_by(Job.created_at.desc()).limit(50).all()
        job_cards = [_job_payload(db, job) for job in jobs]
        if result.get("intent") == "jobs_needing_attention":
            job_cards = [
                item for item in job_cards
                if item["waiting_for_action"] > 0 or item.get("sourcing_approval_status") == "pending"
            ]
            job_cards.sort(key=lambda item: (item["waiting_for_action"], item["applicant_count"]), reverse=True)
        metrics: dict[str, Any] = {}
        if result.get("intent") == "applicant_metrics":
            today = datetime.utcnow().date()
            today_count = _candidate_query(db, user).filter(Resume.created_at >= datetime.combine(today, datetime.min.time())).count()
            metrics = {"applicants_today": today_count, "active_jobs": len(job_cards)}
            result["assistant_reply"] = f"{today_count} candidate(s) applied today across {len(job_cards)} active job(s)."
        else:
            result["assistant_reply"] = (
                f"I found {len(job_cards)} active job(s)."
                if result.get("intent") == "view_active_jobs"
                else f"{len(job_cards)} job(s) currently need recruiter attention."
            )
        result.update({
            "job_preview": job_cards[:12],
            "candidate_preview": [],
            "job_options": [],
            "confirmation": None,
            "metrics": metrics,
            "missing_fields": [],
            "requires_confirmation": False,
            "ready_for_action_agent": False,
            "clarification_needed": False,
            "navigation": {"page": "dashboard", "label": "Open Jobs"},
        })
        return result

    is_talent_search = result.get("intent") == "search_talent"
    is_filter = result.get("intent") == "filter_candidates"
    job, job_options = (None, []) if is_talent_search else _resolve_job(db, user, entities)
    if job:
        entities["job_id"] = job.id
        entities["job_title"] = job.job_title or job.role

    candidates = _resolve_candidates(db, user, {**result, "entities": entities}, job, action_ids)
    if candidates:
        entities["candidate_ids"] = [candidate.id for candidate in candidates]
    if result.get("intent") == "explain_candidate_score" and candidates:
        result["assistant_reply"] = _candidate_fit_reply(candidates[0], job)
        result["guidance"] = result["assistant_reply"]

    if result.get("intent") == "view_sourcing_status":
        if not job:
            result.update({
                "job_options": job_options, "candidate_preview": [], "job_preview": [], "confirmation": None,
                "missing_fields": ["job"], "requires_confirmation": False, "ready_for_action_agent": False,
                "clarification_needed": True, "clarification_question": "Which job should I check sourcing for?",
            })
            return result
        card = _job_payload(db, job)
        result.update({
            "job_preview": [card], "candidate_preview": [], "job_options": [], "confirmation": None,
            "missing_fields": [], "requires_confirmation": False, "ready_for_action_agent": False,
            "clarification_needed": False,
            "assistant_reply": f"Sourcing for {card['job_title']} is {card.get('sourcing_approval_status') or 'not requested'}.",
            "navigation": {"page": "dashboard", "job_id": job.id, "label": "Open Job"},
        })
        return result

    if is_filter:
        result["entities"] = entities
        result["candidate_preview"] = [_candidate_payload(candidate) for candidate in candidates]
        result["job_options"] = []
        result["confirmation"] = None
        result["actions"] = [action for action in raw_actions if action.get("action_id") == "filter_candidates"]
        result["missing_fields"] = [] if entities.get("filters") else ["filters"]
        result["requires_confirmation"] = False
        result["ready_for_action_agent"] = False
        result["clarification_needed"] = not bool(entities.get("filters"))
        result["assistant_reply"] = f"I found {len(candidates)} candidate(s) matching the validated filters."
        result["guidance"] = result["assistant_reply"]
        result["action_agent_plan"] = {
            "enabled": False,
            "actions": result["actions"],
            "missing_fields": result["missing_fields"],
            "requires_confirmation": False,
        }
        return result

    if is_talent_search:
        query_label = entities.get("search_query") or "your search"
        result["entities"] = entities
        result["candidate_preview"] = [_candidate_payload(candidate) for candidate in candidates]
        result["job_options"] = []
        result["confirmation"] = None
        result["tasks"] = result.get("tasks") or []
        result["actions"] = []
        result["missing_fields"] = [] if entities.get("search_query") else ["search_query"]
        result["requires_confirmation"] = False
        result["ready_for_action_agent"] = False
        result["clarification_needed"] = not bool(entities.get("search_query"))
        result["clarification_question"] = None if entities.get("search_query") else "Which role or skills should I search for?"
        result["assistant_reply"] = (
            f"I found {len(candidates)} candidate match{'es' if len(candidates) != 1 else ''} for {query_label}."
            if candidates
            else f"I could not find a strong candidate match for {query_label}. Try adding core skills, seniority, or location."
        )
        result["guidance"] = result["assistant_reply"]
        result["action_agent_plan"] = {
            "enabled": False,
            "actions": [],
            "missing_fields": result["missing_fields"],
            "requires_confirmation": False,
        }
        return result

    missing_fields = [
        field
        for field in (result.get("missing_fields") or [])
        if field not in {"job", "job_id", "job_title_or_job_id", "candidate_ids"}
    ]
    needs_job = (bool(action_ids) and not is_talent_search) or result.get("intent") in {
        "view_shortlisted_candidates",
        "view_candidates_by_stage",
        "review_ai_ranked_candidates",
    }
    if needs_job and not job:
        missing_fields.append("job")
    if result.get("intent") in {"explain_candidate_score", "view_candidate_profile"} and not candidates:
        missing_fields.append("candidate_ids")
    if any(action_id in MUTATING_ACTIONS for action_id in action_ids) and not candidates:
        missing_fields.append("candidate_ids")
    if len(candidates) > MAX_MUTATION_CANDIDATES and any(action_id in MUTATING_ACTIONS for action_id in action_ids):
        missing_fields.append(f"candidate_limit_max_{MAX_MUTATION_CANDIDATES}")

    unavailable = [
        action.get("action_id")
        for action in raw_actions
        if isinstance(action, dict) and action.get("action_id") and action.get("action_id") not in SERVER_ACTIONS
    ]
    if unavailable:
        missing_fields.extend(f"tool_unavailable:{action_id}" for action_id in unavailable)

    missing_fields = list(dict.fromkeys(missing_fields))
    mutating_action_ids = [action_id for action_id in action_ids if action_id in MUTATING_ACTIONS]
    confirmation = None
    if job and candidates and mutating_action_ids and not missing_fields:
        token, expires_at = _confirmation_token(user, job, candidates, action_ids, entities)
        confirmation = {
            "required": True,
            "token": token,
            "expires_at": expires_at.isoformat() + "Z",
            "summary": f"Run {len(mutating_action_ids)} action(s) for {len(candidates)} candidate(s) in {job.job_title or job.role}?",
        }

    result["entities"] = entities
    result["candidate_preview"] = [_candidate_payload(candidate) for candidate in candidates]
    result["job_options"] = job_options
    result["confirmation"] = confirmation
    result["missing_fields"] = missing_fields
    result["requires_confirmation"] = bool(mutating_action_ids)
    result["ready_for_action_agent"] = bool(action_ids) and not missing_fields
    result["clarification_needed"] = bool(result.get("intent") == "unknown" or missing_fields)
    if "job" in missing_fields:
        if job_options:
            result["clarification_question"] = "I found more than one matching job. Which one should I use?"
        elif entities.get("job_title"):
            result["clarification_question"] = f"I could not find an active job named {entities['job_title']}. Which job should I use?"
        else:
            result["clarification_question"] = "What is the job title?"
    elif "candidate_ids" in missing_fields:
        result["clarification_question"] = "Which candidate or candidate group should I use?"
    result["action_agent_plan"] = {
        **(result.get("action_agent_plan") or {}),
        "enabled": result["ready_for_action_agent"],
        "actions": [action for action in raw_actions if action.get("action_id") in SERVER_ACTIONS],
        "missing_fields": missing_fields,
        "requires_confirmation": bool(mutating_action_ids),
    }
    return result


def prepare_action_agent(
    *, message: str, current_route: str | None, current_context: dict[str, Any] | None, db, user: User
) -> dict[str, Any]:
    return _agent_ui_contract(_prepare_action_agent(
        message=message,
        current_route=current_route,
        current_context=current_context,
        db=db,
        user=user,
    ))


def _require_visible_job(db, user: User, job_id: str) -> Job:
    job = _visible_jobs_query(db, user).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _record_stage_change(db, user: User, candidate: Resume, stage: str, status_label: str, action: str) -> bool:
    if candidate.stage == stage and candidate.status == status_label:
        return False
    previous_stage = candidate.stage
    candidate.stage = stage
    candidate.status = status_label
    if stage == "shortlisted":
        candidate.shortlisted = True
        candidate.shortlisted_manual = True
    db.add(CandidateStageHistory(
        candidate_id=candidate.id,
        job_id=candidate.job_id,
        from_stage=previous_stage,
        to_stage=stage,
        actor_user_id=user.id,
        reason="Confirmed Action Agent workflow",
    ))
    write_candidate_activity(
        db,
        candidate_id=candidate.id,
        job_id=candidate.job_id,
        actor_user_id=user.id,
        activity_type=action,
        title=f"Action Agent moved candidate to {status_label}",
    )
    return True


def _completed_confirmation(db, user: User, confirmation_jti: str) -> dict[str, Any] | None:
    """Return a prior receipt so retrying the same signed confirmation is harmless."""
    if not confirmation_jti:
        return None
    rows = db.query(AuditLog).filter(
        AuditLog.actor_user_id == user.id,
        AuditLog.organization_id == getattr(user, "organization_id", None),
        AuditLog.action.like("help_agent.%"),
        AuditLog.metadata_json.like(f"%{confirmation_jti}%"),
    ).order_by(AuditLog.created_at.asc()).all()
    receipts = []
    candidate_ids: list[str] = []
    for row in rows:
        try:
            metadata = json.loads(row.metadata_json or "{}")
        except (TypeError, ValueError):
            continue
        if metadata.get("confirmation_jti") != confirmation_jti:
            continue
        candidate_ids = candidate_ids or [str(item) for item in metadata.get("candidate_ids") or []]
        receipts.append({
            "action_id": row.action.removeprefix("help_agent."),
            "status": "already_completed",
            "count": int(metadata.get("changed") or 0),
        })
    if not receipts:
        return None
    return {"candidate_ids": candidate_ids, "receipts": receipts}


def execute_confirmed_action(*, confirmation_token: str, db, user: User) -> dict[str, Any]:
    payload = decode_token(confirmation_token)
    if payload.get("purpose") != "help_action_confirmation" or payload.get("sub") != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This confirmation is not valid for the current user")
    if payload.get("organization_id") != getattr(user, "organization_id", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context changed; create a new action preview")

    job = _require_visible_job(db, user, str(payload.get("job_id") or ""))
    completed = _completed_confirmation(db, user, str(payload.get("jti") or ""))
    if completed:
        return _agent_ui_contract({
            "status": "already_completed",
            "idempotent_replay": True,
            "job": {"id": job.id, "job_title": job.job_title or job.role},
            "candidate_count": len(completed["candidate_ids"]),
            **completed,
            "navigation": {"page": "jobResult", "job_id": job.id, "label": "View Updated Candidates"},
        })
    candidate_ids = [str(item) for item in (payload.get("candidate_ids") or [])]
    actions = [str(item) for item in (payload.get("actions") or []) if str(item) in SERVER_ACTIONS]
    if not candidate_ids or not actions:
        raise HTTPException(status_code=400, detail="Confirmed action plan is empty")
    if len(candidate_ids) > MAX_MUTATION_CANDIDATES:
        raise HTTPException(status_code=400, detail=f"Action Agent can change at most {MAX_MUTATION_CANDIDATES} candidates at once")

    candidates = _candidate_query(db, user, job.id).filter(Resume.id.in_(candidate_ids)).all()
    if len(candidates) != len(set(candidate_ids)):
        raise HTTPException(status_code=409, detail="Candidate context changed; create a new action preview")

    receipts: list[dict[str, Any]] = []
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    try:
        for action_id in actions:
            changed = 0
            if action_id == "find_top_candidates":
                receipts.append({"action_id": action_id, "status": "completed", "count": len(candidates)})
                continue
            if action_id == "shortlist_candidates":
                changed = sum(_record_stage_change(db, user, candidate, "shortlisted", "Shortlisted", "agent_shortlisted") for candidate in candidates)
            elif action_id == "reject_candidates":
                changed = sum(_record_stage_change(db, user, candidate, "rejected", "Rejected", "agent_rejected") for candidate in candidates)
            elif action_id == "move_to_communication":
                changed = sum(_record_stage_change(db, user, candidate, "communication", "Communication", "agent_moved_to_communication") for candidate in candidates)
            elif action_id == "move_to_interview_scheduling":
                changed = sum(_record_stage_change(db, user, candidate, "interview_scheduling", "Interview Scheduling", "agent_moved_to_interview") for candidate in candidates)
            elif action_id == "schedule_interview_slot":
                scheduled_at_value = str(parameters.get("scheduled_at") or "").strip()
                meeting_url = str(parameters.get("meeting_url") or "").strip()
                if not scheduled_at_value or not re.match(r"^https?://", meeting_url, re.I):
                    raise HTTPException(status_code=400, detail="A valid interview date/time and meeting URL are required")
                scheduled_at = datetime.fromisoformat(scheduled_at_value.replace("Z", "+00:00")).replace(tzinfo=None)
                for candidate in candidates:
                    existing = db.query(Interview).filter(
                        Interview.candidate_id == candidate.id,
                        Interview.job_id == job.id,
                        Interview.scheduled_at == scheduled_at,
                        Interview.status == "scheduled",
                    ).first()
                    if existing:
                        continue
                    db.add(Interview(
                        candidate_id=candidate.id,
                        job_id=job.id,
                        interviewer_user_id=user.id,
                        scheduled_at=scheduled_at,
                        duration_minutes=45,
                        meeting_url=meeting_url,
                    ))
                    write_candidate_activity(
                        db,
                        candidate_id=candidate.id,
                        job_id=job.id,
                        actor_user_id=user.id,
                        activity_type="agent_interview_scheduled",
                        title="Action Agent scheduled interview",
                    )
                    changed += 1

            write_audit_log(
                db,
                action=f"help_agent.{action_id}",
                entity_type="job",
                entity_id=job.id,
                actor_user_id=user.id,
                organization_id=getattr(user, "organization_id", None),
                metadata={"candidate_ids": candidate_ids, "changed": changed, "confirmation_jti": payload.get("jti")},
            )
            receipts.append({"action_id": action_id, "status": "completed", "count": changed})
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except (TypeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Invalid action parameters: {exc}") from exc
    except Exception:
        db.rollback()
        raise

    return _agent_ui_contract({
        "status": "completed",
        "job": {"id": job.id, "job_title": job.job_title or job.role},
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "receipts": receipts,
        "navigation": {"page": "jobResult", "job_id": job.id, "label": "View Updated Candidates"},
    })
