from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status
from sqlalchemy import false, func

from backend.core.config import get_settings
from backend.core.security import decode_token
from backend.models import CandidateStageHistory, Interview, Job, Resume, User
from backend.repositories.audit_repository import write_audit_log, write_candidate_activity
from backend.services.candidate_intelligence import from_json_text
from backend.services.help_intent import parse_intent


GLOBAL_ROLES = {"admin", "super_admin"}
SERVER_ACTIONS = {
    "find_top_candidates",
    "shortlist_candidates",
    "reject_candidates",
    "move_to_communication",
    "move_to_interview_scheduling",
    "schedule_interview_slot",
}
MUTATING_ACTIONS = SERVER_ACTIONS - {"find_top_candidates"}
MAX_MUTATION_CANDIDATES = 25
CONFIRMATION_MINUTES = 10


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", str(value or "").lower()).strip()


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
        return query.filter(Resume.id.in_(explicit_ids)).all()

    candidate_name = _normalized(entities.get("candidate_name"))
    if candidate_name:
        rows = query.filter(
            func.lower(func.coalesce(Resume.full_name, Resume.form_full_name, "")).like(f"%{candidate_name}%")
        ).limit(20).all()
        if len(rows) == 1:
            return rows
        return []

    intent = result.get("intent")
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


def prepare_action_agent(
    *,
    message: str,
    current_route: str | None,
    current_context: dict[str, Any] | None,
    db,
    user: User,
) -> dict[str, Any]:
    result = parse_intent(message, current_route, current_context or {})
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

    job, job_options = _resolve_job(db, user, entities)
    if job:
        entities["job_id"] = job.id
        entities["job_title"] = job.job_title or job.role

    candidates = _resolve_candidates(db, user, {**result, "entities": entities}, job, action_ids)
    if candidates:
        entities["candidate_ids"] = [candidate.id for candidate in candidates]

    missing_fields = [
        field
        for field in (result.get("missing_fields") or [])
        if field not in {"job", "job_id", "job_title_or_job_id", "candidate_ids"}
    ]
    needs_job = bool(action_ids) or result.get("intent") in {
        "view_shortlisted_candidates",
        "view_candidates_by_stage",
        "review_ai_ranked_candidates",
    }
    if needs_job and not job:
        missing_fields.append("job")
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


def execute_confirmed_action(*, confirmation_token: str, db, user: User) -> dict[str, Any]:
    payload = decode_token(confirmation_token)
    if payload.get("purpose") != "help_action_confirmation" or payload.get("sub") != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This confirmation is not valid for the current user")
    if payload.get("organization_id") != getattr(user, "organization_id", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context changed; create a new action preview")

    job = _require_visible_job(db, user, str(payload.get("job_id") or ""))
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

    return {
        "status": "completed",
        "job": {"id": job.id, "job_title": job.job_title or job.role},
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "receipts": receipts,
    }
