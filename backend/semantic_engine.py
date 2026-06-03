from backend.services.semantic_service import cosine_similarity_cached

def calculate_semantic_similarity(jd_text, resume_text):
    return cosine_similarity_cached(jd_text, resume_text)
