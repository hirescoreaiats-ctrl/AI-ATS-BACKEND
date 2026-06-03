from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.experience_engine import process_experience
from backend.models import Job, Resume
from backend.services.parsing_service import parse_resume_enterprise
from backend.services.resume_quality_gate import build_parser_quality_report


def audit_candidates(job_id: str | None = None, limit: int | None = None, only_issues: bool = False):
    db = SessionLocal()
    rows = []

    try:
        query = db.query(Resume).filter(Resume.is_active == True, Resume.resume_text.isnot(None))
        if job_id:
            query = query.filter(Resume.job_id == job_id)
        if limit:
            query = query.limit(limit)

        for candidate in query.all():
            job = db.query(Job).filter(Job.id == candidate.job_id).first()
            parsed = parse_resume_enterprise(candidate.resume_text or "")
            exp_data = process_experience(parsed.get("experience") or [])
            parsed["total_experience_years"] = exp_data.get("total_experience_years")
            report = build_parser_quality_report(
                candidate.resume_text or "",
                parsed,
                exp_data,
                {"max_experience_years": None},
            )

            flags = report["parser_quality_flags"]
            if only_issues and not flags:
                continue

            rows.append({
                "candidate_id": candidate.id,
                "job_id": candidate.job_id,
                "job_title": job.job_title if job else "",
                "stored_name": candidate.full_name,
                "parsed_name": parsed.get("full_name"),
                "stored_score": candidate.final_score,
                "parsed_experience_years": exp_data.get("total_experience_years"),
                "parsed_last_company": exp_data.get("last_company_name"),
                "parser_quality_score": report["parser_quality_score"],
                "parser_quality_action": report["parser_quality_action"],
                "flags": flags,
            })

        return rows
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit stored resumes for suspicious parser output.")
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-issues", action="store_true")
    args = parser.parse_args()

    print(json.dumps(
        audit_candidates(job_id=args.job_id, limit=args.limit, only_issues=args.only_issues),
        indent=2,
        ensure_ascii=False,
    ))
