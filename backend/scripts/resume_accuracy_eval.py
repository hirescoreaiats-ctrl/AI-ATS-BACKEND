from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.database import SessionLocal
from backend.experience_engine import process_experience
from backend.extractor import extract_text_from_docx, extract_text_from_pdf
from backend.jd_engine import normalize_jd_skills
from backend.models import Job
from backend.services.pipeline import analyze_resume_for_job
from backend.services.parsing_service import parse_resume_enterprise


def _text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(str(path))
    if suffix == ".docx":
        return extract_text_from_docx(str(path))
    return path.read_text(encoding="utf-8", errors="ignore")


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _as_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _skill_set(value) -> set[str]:
    if isinstance(value, str):
        items = re.split(r"[,;\n|]+", value)
    else:
        items = value or []
    return {_norm(item) for item in items if _norm(item)}


def _score_text(actual, expected, contains=False) -> tuple[float, str]:
    if expected is None:
        return 1.0, "not_labeled"
    actual_norm = _norm(actual)
    expected_norm = _norm(expected)
    if contains:
        ok = bool(expected_norm and expected_norm in actual_norm)
    else:
        ok = actual_norm == expected_norm
    return (1.0 if ok else 0.0), f"actual={actual!r} expected={expected!r}"


def _score_phone(actual, expected) -> tuple[float, str]:
    if expected is None:
        return 1.0, "not_labeled"
    actual_digits = _digits(actual)
    expected_digits = _digits(expected)
    ok = actual_digits.endswith(expected_digits[-10:]) if expected_digits else not actual_digits
    return (1.0 if ok else 0.0), f"actual={actual!r} expected={expected!r}"


def _score_number(actual, expected, tolerance=0.35, min_value=None, max_value=None) -> tuple[float, str]:
    actual_value = _as_float(actual)
    if expected is None and min_value is None and max_value is None:
        return 1.0, "not_labeled"
    if actual_value is None:
        return 0.0, f"actual={actual!r} expected={expected!r}"
    ok = True
    if expected is not None:
        ok = ok and abs(actual_value - float(expected)) <= tolerance
    if min_value is not None:
        ok = ok and actual_value >= float(min_value)
    if max_value is not None:
        ok = ok and actual_value <= float(max_value)
    return (1.0 if ok else 0.0), f"actual={actual_value!r} expected={expected!r} min={min_value!r} max={max_value!r}"


def _score_skills(actual, expected) -> tuple[float, str]:
    expected_set = _skill_set(expected)
    if not expected_set:
        return 1.0, "not_labeled"
    actual_set = _skill_set(actual)
    recall = len(actual_set & expected_set) / max(len(expected_set), 1)
    return recall, f"recall={recall:.2f} actual={sorted(actual_set & expected_set)} expected={sorted(expected_set)}"


def _load_job(job_id: str | None):
    if not job_id:
        return None, [], {}
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise SystemExit(f"Job not found: {job_id}")
        jd_skills = normalize_jd_skills(job.required_skills or "", job.jd_text or "")
        jd_data = {
            "min_experience_years": job.min_experience_years or 0,
            "education": job.education or "",
            "role": job.role or job.job_title or "",
            "preferred_skills": job.preferred_skills or "",
        }
        return job, jd_skills, jd_data
    finally:
        db.close()


def _parse_item(item: dict, job, jd_skills, jd_data, with_ai: bool):
    path = Path(item["path"])
    text = _text_from_file(path)
    if job:
        parsed, exp_data, _ = analyze_resume_for_job(text, job.jd_text or "", jd_skills, dict(jd_data))
    else:
        parsed = parse_resume_enterprise(text, ai_parse_override=None if with_ai else {})
        exp_data = process_experience(parsed.get("experience") or [])
        parsed["total_experience_years"] = exp_data.get("total_experience_years")
    return parsed, exp_data


def evaluate(gold_path: Path, job_id: str | None = None, with_ai: bool = False) -> dict:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    job, jd_skills, jd_data = _load_job(job_id or gold.get("job_id"))

    field_scores: dict[str, list[float]] = {}
    rows = []

    def add_score(row, field, score, detail):
        field_scores.setdefault(field, []).append(score)
        row["checks"][field] = {"score": round(score, 3), "detail": detail}

    for item in gold.get("items", []):
        expected = item.get("expected", {})
        row = {"id": item.get("id") or item.get("path"), "checks": {}}
        try:
            parsed, exp_data = _parse_item(item, job, jd_skills, jd_data, with_ai)
            actual_skills = parsed.get("matched_skills") or parsed.get("key_skills") or []

            checks = [
                ("full_name", parsed.get("full_name"), expected.get("full_name"), False),
                ("email", parsed.get("email"), expected.get("email"), False),
                ("location", parsed.get("location"), expected.get("location"), False),
                ("designation", parsed.get("designation"), expected.get("designation"), False),
                ("designation_contains", parsed.get("designation"), expected.get("designation_contains"), True),
                ("last_company_name", exp_data.get("last_company_name"), expected.get("last_company_name"), False),
            ]
            for field, actual, exp, contains in checks:
                if exp is not None:
                    add_score(row, field, *_score_text(actual, exp, contains=contains))
            if expected.get("phone") is not None:
                add_score(row, "phone", *_score_phone(parsed.get("phone"), expected.get("phone")))

            add_score(
                row,
                "total_experience_years",
                *_score_number(
                    parsed.get("total_experience_years") or exp_data.get("total_experience_years"),
                    expected.get("total_experience_years"),
                    expected.get("total_experience_tolerance", 0.5),
                    expected.get("min_total_experience_years"),
                    expected.get("max_total_experience_years"),
                ),
            )
            if "salesforce_experience_years" in expected or "max_salesforce_experience_years" in expected:
                add_score(
                    row,
                    "salesforce_experience_years",
                    *_score_number(
                        parsed.get("salesforce_experience_years"),
                        expected.get("salesforce_experience_years"),
                        expected.get("salesforce_experience_tolerance", 0.5),
                        expected.get("min_salesforce_experience_years"),
                        expected.get("max_salesforce_experience_years"),
                    ),
                )
            if "expected_recommendation" in expected:
                add_score(row, "recommendation", *_score_text(parsed.get("recommendation"), expected.get("expected_recommendation")))
            if expected.get("must_have_skills"):
                add_score(row, "must_have_skills", *_score_skills(actual_skills, expected.get("must_have_skills")))

            if expected.get("must_not_have_matched_skills"):
                forbidden = _skill_set(expected["must_not_have_matched_skills"])
                actual = _skill_set(actual_skills)
                ok = not (actual & forbidden)
                add_score(row, "must_not_have_matched_skills", 1.0 if ok else 0.0, f"bad_matches={sorted(actual & forbidden)}")
        except Exception as exc:
            row["error"] = str(exc)
            field_scores.setdefault("_parse_errors", []).append(0.0)
        rows.append(row)

    summary = {
        field: round((sum(values) / len(values)) * 100, 2)
        for field, values in sorted(field_scores.items())
        if values
    }
    summary["overall"] = round(sum(summary.values()) / max(len(summary), 1), 2) if summary else 0
    return {"dataset": gold.get("dataset"), "job_id": job_id or gold.get("job_id"), "summary": summary, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description="Evaluate resume parser/ranker accuracy against golden labels.")
    parser.add_argument("--gold", required=True, help="Gold label JSON file")
    parser.add_argument("--job-id", default=None, help="Optional job id for role-specific scoring evaluation")
    parser.add_argument("--with-ai", action="store_true", help="Allow LLM parse call. Default uses deterministic parser only.")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    result = evaluate(Path(args.gold), job_id=args.job_id, with_ai=args.with_ai)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
