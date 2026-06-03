import math
import os
import re
from collections import Counter
from functools import lru_cache


_model = None


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _semantic_model_enabled():
    return os.getenv("ENABLE_SENTENCE_TRANSFORMER_SCORING", "false").strip().lower() in {"1", "true", "yes", "on"}


def _token_vector(text):
    tokens = re.findall(r"[a-z0-9+#.]+", (text or "").lower())
    stopwords = {
        "and", "or", "the", "a", "an", "to", "of", "in", "for", "with", "on", "by",
        "from", "as", "is", "are", "be", "this", "that", "using", "use", "used",
    }
    return Counter(token for token in tokens if len(token) > 1 and token not in stopwords)


def _lexical_cosine(left, right):
    left_vector = _token_vector(left)
    right_vector = _token_vector(right)
    if not left_vector or not right_vector:
        return 0
    common = set(left_vector) & set(right_vector)
    dot = sum(left_vector[token] * right_vector[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    if not left_norm or not right_norm:
        return 0
    return round(dot / (left_norm * right_norm), 2)


@lru_cache(maxsize=2048)
def embedding_for_text(text):
    model = _load_model()
    clean = (text or "")[:4000]
    return tuple(float(x) for x in model.encode([clean])[0])


def cosine_similarity_cached(left, right):
    if not _semantic_model_enabled():
        return _lexical_cosine(left, right)
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        left_vector = [embedding_for_text(left)]
        right_vector = [embedding_for_text(right)]
        return round(float(cosine_similarity(left_vector, right_vector)[0][0]), 2)
    except Exception:
        return 0


def candidate_embedding_payload(candidate_text, jd_text):
    return {
        "provider": "sentence-transformers",
        "model": "all-MiniLM-L6-v2",
        "candidate_text_length": len(candidate_text or ""),
        "jd_text_length": len(jd_text or ""),
        "ready_for_pgvector": True,
    }
