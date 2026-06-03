from __future__ import annotations

from backend.ai.copilot import build_hiring_summary, rejection_reason
from backend.models import Job, Resume


def recruiter_chat_response(message: str, job: Job | None, candidates: list[Resume]) -> dict:
    lower = (message or "").lower()
    if "bottleneck" in lower:
        return bottleneck_analysis(candidates)
    if "compare" in lower:
        return compare_candidates(candidates[:3])
    if "reject" in lower and candidates:
        return {"intent": "rejection_reasoning", "answer": rejection_reason(candidates[0])}
    if job:
        summary = build_hiring_summary(job, candidates)
        return {
            "intent": "hiring_summary",
            "answer": f"{summary['job_title']} has {summary['applicant_count']} active applicants and {summary['shortlisted_count']} shortlisted candidates.",
            "summary": summary,
        }
    return {"intent": "general", "answer": "I can help shortlist, compare candidates, analyze bottlenecks, and prepare interviews."}


def compare_candidates(candidates: list[Resume]) -> dict:
    return {
        "intent": "candidate_comparison",
        "candidates": [
            {
                "resume_id": c.id,
                "name": c.full_name or c.form_full_name,
                "score": c.final_score or 0,
                "confidence": c.confidence_score or 0,
                "strength": c.ranking_reason,
                "risk": "Low AI confidence" if (c.confidence_score or 0) < 60 else "No major AI confidence concern",
            }
            for c in sorted(candidates, key=lambda row: row.final_score or 0, reverse=True)
        ],
    }


def bottleneck_analysis(candidates: list[Resume]) -> dict:
    stages = {}
    for candidate in candidates:
        stages[candidate.stage or "review"] = stages.get(candidate.stage or "review", 0) + 1
    bottleneck = max(stages.items(), key=lambda item: item[1])[0] if stages else "none"
    return {
        "intent": "bottleneck_analysis",
        "stage_counts": stages,
        "bottleneck": bottleneck,
        "answer": f"The largest candidate concentration is currently in {bottleneck}.",
    }


def interview_prep(candidate: Resume, job: Job | None) -> dict:
    skills = [skill.strip() for skill in (candidate.matched_skills or candidate.key_skills or "").split(",") if skill.strip()]
    missing = [skill.strip() for skill in (candidate.missing_skills or "").split(",") if skill.strip()]
    return {
        "candidate_id": candidate.id,
        "focus_areas": skills[:5],
        "risk_checks": missing[:5],
        "questions": [
            f"Walk through a recent project where you used {skill}."
            for skill in skills[:3]
        ]
        + ["Describe a production incident you helped resolve.", "What tradeoffs would you make in the first 90 days for this role?"],
        "job_title": job.job_title if job else None,
    }
