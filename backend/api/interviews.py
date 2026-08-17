from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.core.security import get_current_user
from backend.database import get_db
from backend.models import Interview, InterviewKit, InterviewScorecard, Job, Resume
from backend.core.tenancy import current_organization_id, require_candidate, require_job
from backend.repositories.audit_repository import write_candidate_activity

router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.post("/kits")
def create_interview_kit(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    organization_id = current_organization_id(user)
    job = require_job(db, data.get("job_id"), user)
    kit = InterviewKit(
        organization_id=organization_id,
        job_id=data.get("job_id"),
        name=data.get("name") or "Interview kit",
        competencies_json=json.dumps(data.get("competencies") or []),
        questions_json=json.dumps(data.get("questions") or []),
        scorecard_template_json=json.dumps(data.get("scorecard_template") or {}),
    )
    db.add(kit)
    db.commit()
    db.refresh(kit)
    return {"id": kit.id, "name": kit.name, "job_id": kit.job_id}


@router.post("/panel")
def schedule_panel_interview(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    current_organization_id(user)
    candidate = require_candidate(db, data.get("candidate_id"), user)
    job = require_job(db, data.get("job_id") or candidate.job_id, user)
    scheduled_at = data.get("scheduled_at")
    if isinstance(scheduled_at, str) and scheduled_at:
        scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    interview = Interview(
        candidate_id=candidate.id,
        job_id=job.id,
        interviewer_user_id=user.id,
        interview_type=data.get("interview_type") or "panel",
        scheduled_at=scheduled_at,
        duration_minutes=int(data.get("duration_minutes") or 60),
        meeting_url=data.get("meeting_url"),
        panel_json=json.dumps(data.get("panel") or []),
        candidate_availability_json=json.dumps(data.get("candidate_availability") or []),
    )
    db.add(interview)
    write_candidate_activity(
        db,
        candidate_id=candidate.id,
        job_id=interview.job_id,
        actor_user_id=user.id,
        activity_type="panel_interview_scheduled",
        title="Panel interview scheduled",
    )
    db.commit()
    db.refresh(interview)
    return {"id": interview.id, "status": interview.status, "panel": json.loads(interview.panel_json or "[]")}


@router.get("/analytics")
def interview_analytics(job_id: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    organization_id = current_organization_id(user)
    query = db.query(Interview).join(Job, Interview.job_id == Job.id).filter(Job.organization_id == organization_id)
    if job_id:
        require_job(db, job_id, user)
        query = query.filter(Interview.job_id == job_id)
    interviews = query.limit(1000).all()
    scorecards = db.query(InterviewScorecard).join(Interview, InterviewScorecard.interview_id == Interview.id).join(Job, Interview.job_id == Job.id).filter(Job.organization_id == organization_id).limit(1000).all()
    completed = len([i for i in interviews if i.status in {"completed", "done"}])
    return {
        "scheduled": len(interviews),
        "completed": completed,
        "scorecards": len(scorecards),
        "feedback_completion_rate": round((len(scorecards) / max(completed, 1)) * 100, 2),
    }
