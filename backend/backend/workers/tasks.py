from __future__ import annotations

from backend.ai.vector_search import enrich_candidate_embedding
from backend.database import SessionLocal
from backend.models import Resume
from backend.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def refresh_candidate_embeddings(self, candidate_id: str):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == candidate_id).first()
        if not candidate:
            return {"status": "missing", "candidate_id": candidate_id}
        enrich_candidate_embedding(candidate)
        db.commit()
        return {"status": "updated", "candidate_id": candidate_id}
    finally:
        db.close()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def parse_resume_task(self, candidate_id: str):
    return refresh_candidate_embeddings(candidate_id)
