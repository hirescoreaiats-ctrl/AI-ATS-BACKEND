from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.ai.copilot import build_hiring_summary, rejection_reason
from backend.ai.vector_search import enrich_candidate_embedding, find_similar_candidates
from backend.core.security import get_current_user
from backend.database import get_db
from backend.models import Job, Resume

router = APIRouter(prefix="/ai", tags=["ai-ats"])


@router.post("/candidates/{candidate_id}/embed")
def embed_candidate(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    enrich_candidate_embedding(candidate)
    db.commit()
    return {
        "candidate_id": candidate.id,
        "provider": candidate.embedding_provider,
        "model": candidate.embedding_model,
        "ready_for_pgvector": True,
    }


@router.get("/candidates/{candidate_id}/similar")
def similar_candidates(candidate_id: str, limit: int = 10, db=Depends(get_db), user=Depends(get_current_user)):
    candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    matches = find_similar_candidates(db, candidate, limit=limit)
    db.commit()
    return {"candidate_id": candidate_id, "matches": matches}


@router.get("/jobs/{job_id}/hiring-summary")
def hiring_summary(job_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    candidates = db.query(Resume).filter(Resume.job_id == job_id).all()
    return build_hiring_summary(job, candidates)


@router.post("/shortlist-recommendations")
def shortlist_recommendations(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    job_id = data.get("job_id")
    limit = int(data.get("limit") or 10)
    rows = (
        db.query(Resume)
        .filter(Resume.job_id == job_id, Resume.is_active == True, Resume.status.notin_(["Rejected", "Dropped"]))
        .order_by(Resume.final_score.desc())
        .limit(limit)
        .all()
    )
    return {
        "job_id": job_id,
        "recommendations": [
            {
                "resume_id": c.id,
                "name": c.full_name or c.form_full_name,
                "score": c.final_score or 0,
                "confidence": c.confidence_score or 0,
                "reason": c.ranking_reason,
                "recommended_action": "shortlist" if (c.final_score or 0) >= 70 else "review",
            }
            for c in rows
        ],
    }


@router.get("/candidates/{candidate_id}/rejection-reason")
def candidate_rejection_reason(candidate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"candidate_id": candidate_id, "reason": rejection_reason(candidate)}
