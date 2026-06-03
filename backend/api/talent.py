from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.ai.search import hybrid_candidate_rank
from backend.ai.vector_search import enrich_candidate_embedding
from backend.core.cache import cache_get_json, cache_set_json
from backend.core.security import get_current_user
from backend.database import get_db
from backend.models import Resume, SavedSearch, TalentPool, TalentPoolCandidate

router = APIRouter(prefix="/talent", tags=["talent-discovery"])


@router.get("/search")
def talent_search(
    q: str,
    stage: str = "all",
    page: int = 1,
    page_size: int = 25,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    cache_key = f"talent-search:{user.organization_id}:{q}:{stage}:{page}:{page_size}"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    query = db.query(Resume).filter(Resume.is_active == True)
    if user.organization_id:
        query = query.filter((Resume.organization_id == user.organization_id) | (Resume.organization_id == None))
    if stage != "all":
        query = query.filter(Resume.stage == stage)

    rows = query.order_by(Resume.created_at.desc()).limit(500).all()
    for row in rows:
        if row.resume_text and not row.embedding_vector_json:
            enrich_candidate_embedding(row)
    ranked = hybrid_candidate_rank(q, rows)
    db.commit()

    start = (max(page, 1) - 1) * page_size
    result = {"query": q, "total": len(ranked), "page": page, "page_size": page_size, "results": ranked[start : start + page_size]}
    cache_set_json(cache_key, result, ttl_seconds=180)
    return result


@router.post("/saved-searches")
def save_search(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    search = SavedSearch(
        organization_id=user.organization_id,
        owner_user_id=user.id,
        name=data.get("name") or data.get("query") or "Saved search",
        query=data.get("query") or "",
        filters_json=json.dumps(data.get("filters") or {}),
    )
    db.add(search)
    db.commit()
    db.refresh(search)
    return {"id": search.id, "name": search.name, "query": search.query}


@router.get("/saved-searches")
def list_saved_searches(db=Depends(get_db), user=Depends(get_current_user)):
    rows = (
        db.query(SavedSearch)
        .filter((SavedSearch.owner_user_id == user.id) | (SavedSearch.organization_id == user.organization_id))
        .order_by(SavedSearch.created_at.desc())
        .limit(100)
        .all()
    )
    return [{"id": row.id, "name": row.name, "query": row.query, "filters": json.loads(row.filters_json or "{}")} for row in rows]


@router.post("/pools")
def create_talent_pool(data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    pool = TalentPool(
        organization_id=user.organization_id,
        owner_user_id=user.id,
        name=data.get("name") or "Talent pool",
        description=data.get("description"),
    )
    db.add(pool)
    db.commit()
    db.refresh(pool)
    return {"id": pool.id, "name": pool.name, "description": pool.description}


@router.post("/pools/{pool_id}/candidates")
def add_candidate_to_pool(pool_id: str, data: dict = Body(...), db=Depends(get_db), user=Depends(get_current_user)):
    candidate_id = data.get("candidate_id")
    if not db.query(Resume).filter(Resume.id == candidate_id).first():
        raise HTTPException(status_code=404, detail="Candidate not found")
    existing = db.query(TalentPoolCandidate).filter(
        TalentPoolCandidate.talent_pool_id == pool_id,
        TalentPoolCandidate.candidate_id == candidate_id,
    ).first()
    if existing:
        return {"id": existing.id, "status": "already_added"}
    row = TalentPoolCandidate(talent_pool_id=pool_id, candidate_id=candidate_id, added_by_user_id=user.id)
    db.add(row)
    db.commit()
    return {"id": row.id, "status": "added"}
