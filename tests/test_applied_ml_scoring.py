from backend.experience_engine import process_experience
from backend.jd_engine import normalize_jd_skills
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


APPLIED_ML_JD = """
Data Scientist / Applied ML Engineer. Experience 4-6 years. Location Delhi / New Delhi.
The role requires Applied ML, Computer Vision, OCR accuracy improvement, Document AI,
LLM, NLP, RAG, VLM, multimodal AI, image enhancement, model benchmarking,
inference optimization, production ML deployment, MLOps, latency/cost optimization,
PyTorch, Hugging Face Transformers, OpenCV, PaddleOCR, DocTR, TrOCR, CLIP, DINO,
Real-ESRGAN, and regression testing for model quality.
"""


def applied_ml_profile():
    skills = normalize_jd_skills([], APPLIED_ML_JD)
    return build_jd_profile(
        APPLIED_ML_JD,
        {"role": "Data Scientist / Applied ML Engineer", "experience_required": "4-6 years"},
        skills,
    )


def score_applied_ml(parsed):
    profile = applied_ml_profile()
    resume_text = " ".join([
        str(parsed.get("designation") or ""),
        " ".join(str(skill) for skill in parsed.get("key_skills") or []),
        " ".join(str(exp.get("description") or "") for exp in parsed.get("experience") or []),
        " ".join(str(project.get("description") or "") for project in parsed.get("projects") or []),
    ])
    parsed.update(estimate_relevant_experience_v2(parsed, resume_text, profile))
    return profile, score_candidate(
        parsed,
        APPLIED_ML_JD,
        profile["must_have_skills"],
        {"role": "Data Scientist / Applied ML Engineer", "experience_required": "4-6 years"},
        resume_text,
        jd_profile=profile,
    )


def test_applied_ml_hybrid_jd_is_not_generic_data_scientist_or_plain_ml():
    profile = applied_ml_profile()

    assert profile["role_family"] == "applied_ml_engineer"
    assert profile["primary_role"] == "Applied ML Engineer"
    assert "Data Scientist" in profile["secondary_roles"]
    assert profile["hybrid_role_detected"] is True
    assert "cv_ocr_document_ai" in profile["core_skill_groups"]
    assert "llm_nlp_vlm_multimodal" in profile["core_skill_groups"]
    assert "production_ml_mlops" in profile["core_skill_groups"]


def test_generic_data_analyst_profile_is_capped_low_for_applied_ml_jd():
    parsed = {
        "full_name": "Generic Analyst",
        "designation": "Data Analyst",
        "key_skills": ["SQL", "Excel", "Power BI", "Dashboard", "A/B Testing", "Statistics"],
        "total_experience_years": 5,
        "relevant_experience_years": 5,
        "role_relevance_score": 35,
        "experience": [{
            "company_name": "Analytics Co",
            "role": "Data Analyst",
            "description": "Built SQL Excel Power BI dashboards, reporting packs, A/B testing analysis, and regression reporting.",
        }],
        "projects": [],
        "resume_quality_score": 85,
    }

    _, result = score_applied_ml(parsed)

    assert result["final_score"] <= 45
    assert result["label"] == "Low Fit"
    assert "generic_data_profile" in result["recruiter_flags"]


def test_llm_rag_without_cv_ocr_cannot_be_strong_match():
    parsed = {
        "full_name": "LLM Engineer",
        "designation": "Generative AI Engineer",
        "key_skills": ["Python", "LLM", "RAG", "LangChain", "Hugging Face", "FastAPI", "Docker", "MLOps"],
        "total_experience_years": 5,
        "relevant_experience_years": 5,
        "role_relevance_score": 82,
        "experience": [{
            "company_name": "GenAI Labs",
            "role": "Generative AI Engineer",
            "description": "Developed RAG pipelines with LangChain, Hugging Face Transformers, LLM prompt engineering, FastAPI model serving, Docker deployment and MLOps monitoring.",
        }],
        "projects": [],
        "resume_quality_score": 88,
    }

    _, result = score_applied_ml(parsed)

    assert result["final_score"] <= 70
    assert result["label"] != "Strong Match"
    assert "missing_cv_ocr_document_ai" in result["recruiter_flags"]


def test_cv_ocr_without_llm_vlm_is_capped_for_hybrid_applied_ml_jd():
    parsed = {
        "full_name": "Computer Vision Engineer",
        "designation": "Computer Vision Engineer",
        "key_skills": ["Python", "PyTorch", "OpenCV", "OCR", "YOLO", "R-CNN", "Tesseract", "Docker"],
        "total_experience_years": 5,
        "relevant_experience_years": 5,
        "role_relevance_score": 82,
        "experience": [{
            "company_name": "Vision Systems",
            "role": "Computer Vision Engineer",
            "description": "Built OCR, handwriting recognition, YOLO and R-CNN object detection, image segmentation, OpenCV pipelines and Docker deployed model APIs.",
        }],
        "projects": [],
        "resume_quality_score": 88,
    }

    _, result = score_applied_ml(parsed)

    assert result["final_score"] <= 72
    assert result["label"] != "Strong Match"
    assert "missing_llm_vlm" in result["recruiter_flags"]
    assert result["evidence_group_scores"]["cv_ocr_document_ai"]["evidence_level"] == "professional_strong"


def test_cv_ocr_llm_vlm_and_production_ml_can_score_strong():
    parsed = {
        "full_name": "Applied ML Specialist",
        "designation": "Applied ML Engineer",
        "key_skills": [
            "Python", "PyTorch", "Computer Vision", "OCR", "OpenCV", "YOLO",
            "Document AI", "LLM", "RAG", "LangChain", "Hugging Face",
            "CLIP", "DINO", "MLOps", "MLflow", "FastAPI", "Docker",
        ],
        "total_experience_years": 5,
        "relevant_experience_years": 5,
        "role_relevance_score": 92,
        "experience": [{
            "company_name": "Applied AI Systems",
            "role": "Applied ML Engineer",
            "start_date": "Jan 2021",
            "end_date": "Jan 2026",
            "description": (
                "Developed production OCR and Document AI pipelines with OpenCV, PaddleOCR, TrOCR, "
                "YOLO object detection, image segmentation, CLIP/DINO vision-language models, "
                "RAG with LangChain and Hugging Face Transformers, MLflow benchmarking, FastAPI model serving, "
                "Docker deployment, latency optimization, cost optimization, and regression testing."
            ),
        }],
        "projects": [],
        "resume_quality_score": 92,
    }

    _, result = score_applied_ml(parsed)

    assert result["final_score"] >= 80
    assert result["label"] == "Strong Match"
    assert result["recommendation"] == "shortlisted"
    assert not result["missing_core_skill_groups"]


def test_company_parser_never_uses_ai_tools_models_or_locations_as_company():
    result = process_experience([
        {"company_name": "GPU", "role": "Senior Data Scientist", "start_date": "Jan 2025", "end_date": "Present"},
        {"company_name": "NLTK", "role": "Senior Data Scientist", "start_date": "Jan 2024", "end_date": "Dec 2024"},
        {"company_name": "London", "role": "Founding Engineer", "start_date": "Jan 2023", "end_date": "Dec 2023"},
        {"company_name": "R-CNN", "role": "Senior Data Analyst", "start_date": "Jan 2022", "end_date": "Dec 2022"},
        {"company_name": "KPMG", "role": "Data Scientist Assistant Manager", "start_date": "Jan 2021", "end_date": "Dec 2021"},
    ])

    assert result["last_company_name"] == "KPMG"
    validity = {item["company_name"]: item["company_valid"] for item in result["extracted_date_ranges_raw"]}
    assert validity["GPU"] is False
    assert validity["NLTK"] is False
    assert validity["London"] is False
    assert validity["R-CNN"] is False
