from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.ai.recruiter_copilot import bottleneck_analysis, compare_candidates, interview_prep, recruiter_chat_response
from backend.core.metrics import timed_ai
from backend.core.security import get_current_user
from backend.database import get_db
from backend.models import Job, Resume

router = APIRouter(prefix="/copilot", tags=["ai-recruiter-copilot"])


@router.post("/chat")
@timed_ai("copilot_chat")
def copilot_chat(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    job_id = data.get("job_id")
    job = db.query(Job).filter(Job.id == job_id).first() if job_id else None
    candidates = db.query(Resume).filter(Resume.job_id == job_id).order_by(Resume.final_score.desc()).limit(50).all() if job_id else []
    return recruiter_chat_response(data.get("message") or "", job, candidates)


@router.post("/compare")
@timed_ai("candidate_compare")
def compare(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    ids = data.get("candidate_ids") or []
    candidates = db.query(Resume).filter(Resume.id.in_(ids)).all()
    return compare_candidates(candidates)


@router.get("/jobs/{job_id}/bottlenecks")
def bottlenecks(job_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    candidates = db.query(Resume).filter(Resume.job_id == job_id, Resume.is_active == True).all()
    return bottleneck_analysis(candidates)


@router.get("/candidates/{candidate_id}/interview-prep")
def candidate_interview_prep(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    job = db.query(Job).filter(Job.id == candidate.job_id).first() if candidate.job_id else None
    return interview_prep(candidate, job)


@router.get("/candidates/{candidate_id}/confidence")
def candidate_confidence_analysis(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    missing = [item.strip() for item in (candidate.missing_skills or "").split(",") if item.strip()]
    matched = [item.strip() for item in (candidate.matched_skills or "").split(",") if item.strip()]
    confidence = candidate.confidence_score or 0
    return {
        "candidate_id": candidate.id,
        "confidence_score": confidence,
        "confidence_band": "high" if confidence >= 75 else "medium" if confidence >= 55 else "low",
        "positive_signals": matched[:6],
        "risk_signals": missing[:6],
        "recommendation": "advance" if confidence >= 75 and (candidate.final_score or 0) >= 70 else "review",
    }


@router.post("/outreach")
def generate_outreach(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    candidate = db.query(Resume).filter(Resume.id == data.get("candidate_id")).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    job = db.query(Job).filter(Job.id == candidate.job_id).first() if candidate.job_id else None
    name = candidate.full_name or candidate.form_full_name or "there"
    role = job.job_title if job else "the role"
    strengths = candidate.ranking_reason or "your background looks aligned with our hiring needs"
    return {
        "subject": f"{role} - next step",
        "body": (
            f"Hi {name},\n\n"
            f"Thanks for your interest in {role}. {strengths}\n\n"
            "We would like to move you to the next step in the process. "
            "Please share a few time windows that work for you this week.\n\n"
            f"Best,\n{user.name}"
        ),
    }
