from __future__ import annotations

from backend.models import Job, Resume


def build_hiring_summary(job: Job, candidates: list[Resume]) -> dict:
    active = [c for c in candidates if c.is_active]
    shortlisted = [c for c in active if c.stage == "shortlisted" or c.shortlisted]
    interview = [c for c in active if (c.stage or "").startswith("interview")]
    top = sorted(active, key=lambda c: c.final_score or 0, reverse=True)[:5]

    return {
        "job_id": job.id,
        "job_title": job.job_title,
        "pipeline_health": "healthy" if len(shortlisted) >= 3 else "needs_attention",
        "applicant_count": len(active),
        "shortlisted_count": len(shortlisted),
        "interview_count": len(interview),
        "top_candidates": [
            {
                "resume_id": c.id,
                "name": c.full_name or c.form_full_name,
                "score": c.final_score or 0,
                "reason": c.ranking_reason,
            }
            for c in top
        ],
        "next_best_actions": _next_actions(active, shortlisted, interview),
    }


def _next_actions(active: list[Resume], shortlisted: list[Resume], interview: list[Resume]) -> list[str]:
    actions = []
    if not active:
        actions.append("Publish or share the apply link to build candidate volume.")
    if active and len(shortlisted) < 3:
        actions.append("Review AI shortlist recommendations and add recruiter notes to edge cases.")
    if shortlisted and not interview:
        actions.append("Move interested shortlisted candidates into communication and assessment.")
    if interview:
        actions.append("Collect scorecards within 24 hours to keep the hiring team aligned.")
    return actions


def rejection_reason(candidate: Resume) -> str:
    missing = (candidate.missing_skills or "").split(",") if candidate.missing_skills else []
    if candidate.final_score is not None and candidate.final_score < 38:
        return "Low role fit based on required skills, relevant experience, and semantic JD alignment."
    if missing:
        return f"Missing core requirements: {', '.join([m for m in missing if m][:3])}."
    return "Profile requires additional recruiter review before advancing."
