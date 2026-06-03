from __future__ import annotations

import json
import math
from typing import Iterable

from backend.models import Resume
from backend.services.semantic_service import embedding_for_text


def vector_for_text(text: str) -> list[float]:
    return list(embedding_for_text(text or ""))


def serialize_vector(vector: Iterable[float]) -> str:
    return json.dumps([round(float(x), 8) for x in vector])


def deserialize_vector(value: str | None) -> list[float]:
    if not value:
        return []
    try:
        return [float(x) for x in json.loads(value)]
    except Exception:
        return []


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return round(dot / (left_norm * right_norm), 4)


def enrich_candidate_embedding(candidate: Resume) -> None:
    payload = " ".join(
        [
            candidate.full_name or "",
            candidate.designation or "",
            candidate.key_skills or "",
            candidate.domain or "",
            candidate.resume_text or "",
        ]
    )
    candidate.embedding_provider = "sentence-transformers"
    candidate.embedding_model = "all-MiniLM-L6-v2"
    candidate.embedding_vector_json = serialize_vector(vector_for_text(payload[:4000]))


def find_similar_candidates(db, candidate: Resume, limit: int = 10) -> list[dict]:
    if not candidate.embedding_vector_json:
        enrich_candidate_embedding(candidate)
        db.flush()

    source_vector = deserialize_vector(candidate.embedding_vector_json)
    candidates = (
        db.query(Resume)
        .filter(Resume.id != candidate.id, Resume.is_active == True)
        .limit(500)
        .all()
    )

    ranked = []
    for row in candidates:
        row_vector = deserialize_vector(row.embedding_vector_json)
        if not row_vector and row.resume_text:
            enrich_candidate_embedding(row)
            row_vector = deserialize_vector(row.embedding_vector_json)
        score = cosine(source_vector, row_vector)
        if score:
            ranked.append(
                {
                    "resume_id": row.id,
                    "full_name": row.full_name or row.form_full_name,
                    "email": row.email or row.form_email,
                    "designation": row.designation,
                    "job_id": row.job_id,
                    "similarity": score,
                    "final_score": row.final_score or 0,
                }
            )

    return sorted(ranked, key=lambda item: item["similarity"], reverse=True)[:limit]
