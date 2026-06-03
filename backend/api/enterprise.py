from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.core.security import get_current_user, require_roles
from backend.database import get_db
from backend.models import CandidateActivity, CandidateNote, CandidateStageHistory, CandidateTag, Interview, InterviewScorecard, Offer, OfferApproval, PipelineStage, Resume
from backend.repositories.audit_repository import write_audit_log, write_candidate_activity
from backend.utils.sanitize import sanitize_text

router = APIRouter(prefix="/enterprise", tags=["enterprise-ats"])


@router.post("/candidates/{candidate_id}/notes")
def add_candidate_note(
    candidate_id: str,
    data: dict = Body(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    candidate = db.query(Resume).filter(Resume.id == candidate_id, Resume.is_active == True).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    body = sanitize_text(data.get("body"))
    if not body:
        raise HTTPException(status_code=400, detail="Note body is required")

    note = CandidateNote(
        candidate_id=candidate.id,
        job_id=candidate.job_id,
        author_user_id=user.id,
        body=body,
        visibility=data.get("visibility") or "team",
    )
    db.add(note)
    write_candidate_activity(
        db,
        candidate_id=candidate.id,
        job_id=candidate.job_id,
        actor_user_id=user.id,
        activity_type="note_added",
        title="Recruiter note added",
        body=body[:300],
    )
    write_audit_log(db, action="candidate.note_added", entity_type="candidate", entity_id=candidate.id, actor_user_id=user.id)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "candidate_id": candidate.id, "body": note.body, "created_at": note.created_at}


@router.get("/candidates/{candidate_id}/timeline")
def candidate_timeline(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    activities = (
        db.query(CandidateActivity)
        .filter(CandidateActivity.candidate_id == candidate_id)
        .order_by(CandidateActivity.created_at.desc())
        .limit(100)
        .all()
    )
    notes = (
        db.query(CandidateNote)
        .filter(CandidateNote.candidate_id == candidate_id)
        .order_by(CandidateNote.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "candidate_id": candidate_id,
        "activities": [
            {"id": a.id, "type": a.activity_type, "title": a.title, "body": a.body, "created_at": a.created_at}
            for a in activities
        ],
        "notes": [{"id": n.id, "body": n.body, "visibility": n.visibility, "created_at": n.created_at} for n in notes],
    }


@router.get("/candidates/search")
def advanced_candidate_search(
    q: str = "",
    stage: str = "all",
    page: int = 1,
    page_size: int = 25,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = db.query(Resume).filter(Resume.is_active == True)
    if stage != "all":
        query = query.filter(Resume.stage == stage)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Resume.full_name.ilike(like))
            | (Resume.email.ilike(like))
            | (Resume.key_skills.ilike(like))
            | (Resume.designation.ilike(like))
        )
    total = query.count()
    rows = (
        query.order_by(Resume.final_score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "results": [
            {
                "resume_id": row.id,
                "full_name": row.full_name or row.form_full_name,
                "email": row.email or row.form_email,
                "designation": row.designation,
                "stage": row.stage,
                "final_score": row.final_score or 0,
                "confidence_score": row.confidence_score or 0,
                "ranking_reason": row.ranking_reason,
            }
            for row in rows
        ],
    }


@router.post("/candidates/{candidate_id}/tags")
def add_candidate_tag(candidate_id: str, data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    tag_value = (data.get("tag") or "").strip().lower()
    if not tag_value:
        raise HTTPException(status_code=400, detail="tag is required")
    candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    tag = db.query(CandidateTag).filter(CandidateTag.candidate_id == candidate_id, CandidateTag.tag == tag_value).first()
    if not tag:
        tag = CandidateTag(candidate_id=candidate_id, tag=tag_value, color=data.get("color"))
        db.add(tag)
    write_candidate_activity(
        db,
        candidate_id=candidate_id,
        job_id=candidate.job_id,
        actor_user_id=user.id,
        activity_type="tag_added",
        title=f"Tag added: {tag_value}",
    )
    db.commit()
    return {"candidate_id": candidate_id, "tag": tag_value}


@router.post("/pipeline/move")
def move_candidate_stage(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    candidate_id = data.get("candidate_id")
    stage = data.get("stage")
    status = data.get("status") or _status_for_stage(stage)
    allowed = {
        "applied",
        "ai_screening",
        "recruiter_review",
        "hiring_manager_review",
        "technical_interview",
        "assessment",
        "final_interview",
        "offer",
        "hired",
        "rejected",
        "archived",
        "review",
        "shortlisted",
        "communication",
        "interview_scheduling",
        "dropped",
    }
    if stage not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported pipeline stage")
    candidate = db.query(Resume).filter(Resume.id == candidate_id, Resume.is_active == True).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    previous_stage = candidate.stage
    candidate.stage = stage
    candidate.status = status
    candidate.shortlisted = stage in {"shortlisted", "hiring_manager_review", "technical_interview", "assessment", "final_interview", "offer", "hired"} or candidate.shortlisted
    db.add(
        CandidateStageHistory(
            candidate_id=candidate.id,
            job_id=candidate.job_id,
            from_stage=previous_stage,
            to_stage=stage,
            actor_user_id=user.id,
            reason=data.get("reason"),
        )
    )
    write_candidate_activity(
        db,
        candidate_id=candidate.id,
        job_id=candidate.job_id,
        actor_user_id=user.id,
        activity_type="stage_changed",
        title=f"Moved to {status}",
    )
    write_audit_log(db, action="candidate.stage_changed", entity_type="candidate", entity_id=candidate.id, actor_user_id=user.id, metadata={"stage": stage})
    db.commit()
    return {"message": "Candidate moved", "candidate_id": candidate.id, "stage": stage, "status": status}


@router.get("/pipeline/stages")
def list_pipeline_stages(job_id: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    query = db.query(PipelineStage)
    if job_id:
        query = query.filter((PipelineStage.job_id == job_id) | (PipelineStage.job_id == None))
    elif user.organization_id:
        query = query.filter((PipelineStage.organization_id == user.organization_id) | (PipelineStage.organization_id == None))
    rows = query.order_by(PipelineStage.position.asc()).all()
    if not rows:
        return {"stages": default_pipeline_stages()}
    return {
        "stages": [
            {"id": row.id, "key": row.key, "name": row.name, "position": row.position, "is_terminal": row.is_terminal}
            for row in rows
        ]
    }


@router.post("/pipeline/stages")
def upsert_pipeline_stage(data: dict = Body(...), db=Depends(get_db), user=Depends(require_roles("admin", "recruiter"))):
    stage = PipelineStage(
        organization_id=user.organization_id,
        job_id=data.get("job_id"),
        key=data.get("key"),
        name=data.get("name"),
        position=int(data.get("position") or 0),
        rules_json=data.get("rules_json"),
        is_terminal=bool(data.get("is_terminal")),
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return {"id": stage.id, "key": stage.key, "name": stage.name, "position": stage.position}


@router.get("/candidates/{candidate_id}/stage-history")
def candidate_stage_history(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    rows = (
        db.query(CandidateStageHistory)
        .filter(CandidateStageHistory.candidate_id == candidate_id)
        .order_by(CandidateStageHistory.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "candidate_id": candidate_id,
        "history": [
            {
                "id": row.id,
                "from_stage": row.from_stage,
                "to_stage": row.to_stage,
                "reason": row.reason,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.post("/pipeline/bulk-move")
def bulk_move_candidates(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    candidate_ids = data.get("candidate_ids") or []
    stage = data.get("stage")
    status = data.get("status") or _status_for_stage(stage)
    rows = db.query(Resume).filter(Resume.id.in_(candidate_ids), Resume.is_active == True).all()
    for candidate in rows:
        previous_stage = candidate.stage
        candidate.stage = stage
        candidate.status = status
        db.add(
            CandidateStageHistory(
                candidate_id=candidate.id,
                job_id=candidate.job_id,
                from_stage=previous_stage,
                to_stage=stage,
                actor_user_id=user.id,
                reason=data.get("reason") or "Bulk candidate action",
            )
        )
        write_candidate_activity(
            db,
            candidate_id=candidate.id,
            job_id=candidate.job_id,
            actor_user_id=user.id,
            activity_type="bulk_stage_changed",
            title=f"Bulk moved to {status}",
        )
    db.commit()
    return {"message": "Candidates moved", "updated": len(rows), "stage": stage}


@router.post("/interviews")
def schedule_interview(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    scheduled_at = data.get("scheduled_at")
    if isinstance(scheduled_at, str) and scheduled_at:
        scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))

    interview = Interview(
        candidate_id=data.get("candidate_id"),
        job_id=data.get("job_id"),
        interviewer_user_id=data.get("interviewer_user_id") or user.id,
        interview_type=data.get("interview_type") or "technical",
        scheduled_at=scheduled_at,
        duration_minutes=int(data.get("duration_minutes") or 45),
        meeting_url=data.get("meeting_url"),
    )
    db.add(interview)
    write_candidate_activity(
        db,
        candidate_id=interview.candidate_id,
        job_id=interview.job_id,
        actor_user_id=user.id,
        activity_type="interview_scheduled",
        title="Interview scheduled",
    )
    db.commit()
    db.refresh(interview)
    return {"id": interview.id, "status": interview.status}


@router.post("/scorecards")
def submit_scorecard(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    scorecard = InterviewScorecard(
        interview_id=data.get("interview_id"),
        candidate_id=data.get("candidate_id"),
        reviewer_user_id=user.id,
        recommendation=data.get("recommendation") or "mixed",
        technical_score=data.get("technical_score"),
        communication_score=data.get("communication_score"),
        culture_score=data.get("culture_score"),
        notes=data.get("notes"),
    )
    db.add(scorecard)
    write_candidate_activity(
        db,
        candidate_id=scorecard.candidate_id,
        actor_user_id=user.id,
        activity_type="scorecard_submitted",
        title=f"Scorecard submitted: {scorecard.recommendation}",
    )
    db.commit()
    db.refresh(scorecard)
    return {"id": scorecard.id, "recommendation": scorecard.recommendation}


@router.post("/offers")
def create_offer(data: dict = Body(...), db=Depends(get_db), user=Depends(require_roles("admin", "recruiter"))):
    offer = Offer(
        candidate_id=data.get("candidate_id"),
        job_id=data.get("job_id"),
        compensation=data.get("compensation"),
        start_date=data.get("start_date"),
        status=data.get("status") or "draft",
    )
    db.add(offer)
    db.flush()
    for index, approver_id in enumerate(data.get("approver_user_ids") or []):
        db.add(OfferApproval(offer_id=offer.id, approver_user_id=approver_id, step_order=index))
    write_candidate_activity(
        db,
        candidate_id=offer.candidate_id,
        job_id=offer.job_id,
        actor_user_id=user.id,
        activity_type="offer_created",
        title="Offer workflow started",
    )
    db.commit()
    db.refresh(offer)
    return {"id": offer.id, "status": offer.status, "approval_status": offer.approval_status}


@router.get("/offers/{offer_id}/approvals")
def offer_approvals(offer_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    rows = (
        db.query(OfferApproval)
        .filter(OfferApproval.offer_id == offer_id)
        .order_by(OfferApproval.step_order.asc())
        .all()
    )
    return {
        "offer_id": offer_id,
        "approvals": [
            {
                "id": row.id,
                "approver_user_id": row.approver_user_id,
                "step_order": row.step_order,
                "status": row.status,
                "notes": row.notes,
                "decided_at": row.decided_at,
            }
            for row in rows
        ],
    }


@router.post("/offers/{offer_id}/approvals/{approval_id}/decision")
def decide_offer_approval(
    offer_id: str,
    approval_id: str,
    data: dict = Body(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    approval = db.query(OfferApproval).filter(OfferApproval.id == approval_id, OfferApproval.offer_id == offer_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval step not found")
    if approval.approver_user_id and approval.approver_user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You are not assigned to this approval")
    decision = data.get("status")
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be approved or rejected")
    approval.status = decision
    approval.notes = sanitize_text(data.get("notes"), 2000)
    approval.decided_at = datetime.utcnow()

    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    approvals = db.query(OfferApproval).filter(OfferApproval.offer_id == offer_id).all()
    if offer:
        if any(row.status == "rejected" for row in approvals):
            offer.approval_status = "rejected"
        elif approvals and all(row.status == "approved" for row in approvals):
            offer.approval_status = "approved"
        else:
            offer.approval_status = "pending"
    write_audit_log(db, action="offer.approval_decided", entity_type="offer", entity_id=offer_id, actor_user_id=user.id, metadata={"decision": decision})
    db.commit()
    return {"offer_id": offer_id, "approval_id": approval_id, "status": decision, "offer_approval_status": offer.approval_status if offer else None}


@router.get("/pipeline/analytics")
def pipeline_analytics(job_id: str | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    query = db.query(Resume).filter(Resume.is_active == True)
    if job_id:
        query = query.filter(Resume.job_id == job_id)
    if user.organization_id:
        query = query.filter((Resume.organization_id == user.organization_id) | (Resume.organization_id == None))
    rows = query.limit(5000).all()
    stage_counts = {}
    total_score = 0
    for row in rows:
        stage_counts[row.stage or "review"] = stage_counts.get(row.stage or "review", 0) + 1
        total_score += row.final_score or 0
    bottleneck = max(stage_counts.items(), key=lambda item: item[1])[0] if stage_counts else None
    return {
        "total_candidates": len(rows),
        "stage_counts": stage_counts,
        "average_ai_score": round(total_score / max(len(rows), 1), 2),
        "bottleneck_stage": bottleneck,
        "interview_count": sum(count for stage, count in stage_counts.items() if "interview" in stage),
        "offer_count": stage_counts.get("offer", 0),
        "hired_count": stage_counts.get("hired", 0),
    }


def _status_for_stage(stage: str | None) -> str:
    return {
        "applied": "Applied",
        "ai_screening": "AI Screening",
        "recruiter_review": "Recruiter Review",
        "hiring_manager_review": "Hiring Manager Review",
        "technical_interview": "Technical Interview",
        "review": "Review",
        "shortlisted": "Shortlisted",
        "communication": "Communication",
        "assessment": "Assessment",
        "interview_scheduling": "Interview Scheduling",
        "final_interview": "Final Interview",
        "offer": "Offer",
        "hired": "Hired",
        "rejected": "Rejected",
        "archived": "Archived",
        "dropped": "Dropped",
    }.get(stage or "", "Review")


def default_pipeline_stages():
    return [
        {"key": "applied", "name": "Applied", "position": 10},
        {"key": "ai_screening", "name": "AI Screening", "position": 20},
        {"key": "recruiter_review", "name": "Recruiter Review", "position": 30},
        {"key": "hiring_manager_review", "name": "Hiring Manager Review", "position": 40},
        {"key": "technical_interview", "name": "Technical Interview", "position": 50},
        {"key": "assessment", "name": "Assessment", "position": 60},
        {"key": "final_interview", "name": "Final Interview", "position": 70},
        {"key": "offer", "name": "Offer", "position": 80},
        {"key": "hired", "name": "Hired", "position": 90, "is_terminal": True},
        {"key": "rejected", "name": "Rejected", "position": 100, "is_terminal": True},
        {"key": "archived", "name": "Archived", "position": 110, "is_terminal": True},
    ]
