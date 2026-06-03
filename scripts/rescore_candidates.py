import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.jd_engine import normalize_jd_skills
from backend.models import Job, Resume
from backend.services.pipeline import analyze_resume_for_job
from sqlalchemy import inspect, text
import json


def education_label(education):
    labels = []
    seen = set()
    for item in education or []:
        if not isinstance(item, dict):
            continue
        degree = (item.get("degree") or "").strip()
        field = (item.get("field") or "").strip()
        institution = (item.get("institution") or "").strip(" •-")
        dates = " - ".join(part for part in [item.get("start_date"), item.get("end_date")] if part)
        main = " ".join(part for part in [degree, field] if part).strip()
        if institution:
            main = f"{main} - {institution}" if main else institution
        if dates:
            main = f"{main} ({dates})" if main else dates
        key = " ".join(main.lower().split())
        if main and key not in seen:
            seen.add(key)
            labels.append(main)
    return ", ".join(labels)


def ensure_scoring_columns(db):
    inspector = inspect(db.bind)
    resume_columns = {column["name"] for column in inspector.get_columns("resumes")}
    job_columns = {column["name"] for column in inspector.get_columns("jobs")}

    def add_column(table, existing_columns, column_name, definition):
        if column_name not in existing_columns:
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {definition}"))
            existing_columns.add(column_name)

    add_column("resumes", resume_columns, "rank_score", "FLOAT")
    add_column("resumes", resume_columns, "fit_band", "VARCHAR")
    add_column("jobs", job_columns, "preferred_skills", "TEXT")
    db.commit()


def rescore_candidates(job_id=None, limit=None):
    db = SessionLocal()
    processed = 0

    try:
        ensure_scoring_columns(db)
        query = db.query(Resume).filter(Resume.is_active == True, Resume.resume_text.isnot(None))
        if job_id:
            query = query.filter(Resume.job_id == job_id)
        if limit:
            query = query.limit(limit)

        for candidate in query.all():
            job = db.query(Job).filter(Job.id == candidate.job_id).first()
            if not job or not candidate.resume_text:
                continue

            jd_skills = normalize_jd_skills(job.required_skills or "", job.jd_text or "")
            jd_data = {
                "min_experience_years": job.min_experience_years or 0,
                "education": job.education or "",
                "role": job.role or job.job_title or "",
                "preferred_skills": job.preferred_skills or "",
            }

            parsed, exp_data, _ = analyze_resume_for_job(candidate.resume_text, job.jd_text or "", jd_skills, jd_data)

            candidate.full_name = parsed.get("full_name") or candidate.full_name
            candidate.email = parsed.get("email") or candidate.email
            candidate.phone = parsed.get("phone") or candidate.phone
            candidate.location = parsed.get("location") or candidate.location
            candidate.designation = parsed.get("designation") or candidate.designation
            candidate.key_skills = ", ".join(parsed.get("key_skills") or []) or candidate.key_skills
            candidate.projects = json.dumps(parsed.get("projects") or [], ensure_ascii=False)
            candidate.total_experience_years = parsed.get("total_experience_years")
            candidate.last_company_name = exp_data.get("last_company_name")
            candidate.last_working_date = exp_data.get("last_working_date")
            candidate.education = education_label(parsed.get("education") or []) or candidate.education
            candidate.industry = parsed.get("industry_category") or candidate.industry
            candidate.domain = parsed.get("domain") or candidate.domain
            candidate.final_score = parsed.get("final_score")
            candidate.rank_score = parsed.get("rank_score")
            candidate.fit_band = parsed.get("fit_band")
            candidate.skill_score = parsed.get("skill_score")
            candidate.experience_score = parsed.get("experience_score")
            candidate.confidence_score = parsed.get("confidence_score")
            candidate.resume_quality_score = parsed.get("resume_quality_score")
            candidate.ai_recommendation = parsed.get("recommendation")
            candidate.ranking_reason = parsed.get("ranking_reason")
            candidate.ai_confidence_reason = str(parsed.get("ai_recruiter_explanation") or "")
            candidate.matched_skills = ",".join(parsed.get("matched_skills") or [])
            candidate.missing_skills = ",".join(parsed.get("missing_skills") or [])
            candidate.skill_match_percent = parsed.get("skill_match_percent")

            recruiter_score = parsed.get("rank_score") or parsed.get("final_score") or 0
            threshold = job.shortlist_score or 70
            if parsed.get("recommendation") == "rejected":
                candidate.shortlisted = False
                candidate.shortlisted_auto = False
                candidate.status = "Rejected"
                candidate.stage = "rejected"
            elif parsed.get("recommendation") == "shortlisted" or (
                not parsed.get("recommendation") and recruiter_score >= threshold
            ):
                candidate.shortlisted = True
                candidate.shortlisted_auto = True
                candidate.status = "Shortlisted"
                candidate.stage = "shortlisted"
            elif parsed.get("recommendation") == "in_review":
                candidate.shortlisted = bool(candidate.shortlisted_manual)
                candidate.shortlisted_auto = False
                if not candidate.shortlisted_manual:
                    candidate.status = "In Review"
                    candidate.stage = "review"
            elif candidate.stage in {None, "", "applied", "review"}:
                candidate.shortlisted = False
                candidate.shortlisted_auto = False
                candidate.status = "In Review"
                candidate.stage = "review"

            processed += 1

        db.commit()
        return processed
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Re-score existing candidates with the recruiter-style scoring engine.")
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    count = rescore_candidates(job_id=args.job_id, limit=args.limit)
    print(f"Re-scored {count} candidate(s).")
