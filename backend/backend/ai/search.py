from __future__ import annotations

import re

from backend.ai.vector_search import cosine, deserialize_vector, vector_for_text
from backend.models import Resume


BOOLEAN_OPERATORS = {"AND", "OR", "NOT"}


def parse_boolean_terms(query: str) -> dict:
    tokens = re.findall(r'"[^"]+"|\bAND\b|\bOR\b|\bNOT\b|[\w.+#-]+', query or "", flags=re.I)
    required = []
    excluded = []
    optional = []
    mode = "optional"
    for token in tokens:
        clean = token.strip('"')
        upper = clean.upper()
        if upper in BOOLEAN_OPERATORS:
            mode = "required" if upper == "AND" else "excluded" if upper == "NOT" else "optional"
            continue
        if mode == "required":
            required.append(clean.lower())
        elif mode == "excluded":
            excluded.append(clean.lower())
        else:
            optional.append(clean.lower())
    return {"required": required, "optional": optional, "excluded": excluded}


def hybrid_candidate_rank(query: str, rows: list[Resume]) -> list[dict]:
    parsed = parse_boolean_terms(query)
    query_vector = vector_for_text(query)
    ranked = []

    for row in rows:
        haystack = " ".join(
            [
                row.full_name or "",
                row.designation or "",
                row.key_skills or "",
                row.domain or "",
                row.resume_text or "",
            ]
        ).lower()
        if any(term not in haystack for term in parsed["required"]):
            continue
        if any(term in haystack for term in parsed["excluded"]):
            continue

        keyword_hits = sum(1 for term in parsed["required"] + parsed["optional"] if term in haystack)
        keyword_score = min(1.0, keyword_hits / max(len(parsed["required"]) + len(parsed["optional"]), 1))
        semantic_score = cosine(query_vector, deserialize_vector(row.embedding_vector_json))
        ats_score = (row.rank_score or row.final_score or 0) / 100
        confidence = (row.confidence_score or 0) / 100
        rank_score = round((semantic_score * 0.42) + (keyword_score * 0.28) + (ats_score * 0.2) + (confidence * 0.1), 4)

        ranked.append(
            {
                "resume_id": row.id,
                "full_name": row.full_name or row.form_full_name,
                "email": row.email or row.form_email,
                "designation": row.designation,
                "stage": row.stage,
                "final_score": row.final_score or 0,
                "recruiter_rank_score": row.rank_score or row.final_score or 0,
                "fit_band": row.fit_band,
                "confidence_score": row.confidence_score or 0,
                "semantic_score": semantic_score,
                "keyword_score": round(keyword_score, 4),
                "rank_score": rank_score,
                "ranking_reason": row.ranking_reason,
            }
        )

    return sorted(ranked, key=lambda item: item["rank_score"], reverse=True)
