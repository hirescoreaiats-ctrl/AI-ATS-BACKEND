import argparse
import json
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
from backend.models import Resume
from backend.services.parsing_service import parse_resume_enterprise
from backend.services.resume_quality_gate import apply_parser_quality_gate


NOISE_PATTERN = re.compile(
    r"\b(experience|professional experience|work experience|about me|personalprofile|"
    r"contact|skills|education|projects?)\b",
    re.I,
)


def _text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(str(path))
    if suffix == ".docx":
        return extract_text_from_docx(str(path))
    return path.read_text(encoding="utf-8", errors="ignore")


def _project_text(projects) -> str:
    return " ".join(
        " ".join(str(project.get(key) or "") for key in ("name", "description"))
        for project in projects or []
        if isinstance(project, dict)
    )


def audit_text(name: str, text: str, with_ai: bool = False) -> dict:
    parsed = parse_resume_enterprise(
        (text or "")[:12000],
        ai_parse_override=None if with_ai else {},
    )
    exp_data = process_experience(parsed.get("experience") or [])
    report = apply_parser_quality_gate(parsed, exp_data, {}, text)
    company = exp_data.get("last_company_name") or ""
    project_text = _project_text(parsed.get("projects"))
    heuristic_flags = []
    if NOISE_PATTERN.search(company):
        heuristic_flags.append("company_section_noise")
    if len(str(company).split()) > 8:
        heuristic_flags.append("company_too_long")
    if re.search(r"\b(i am|i enjoy|my wide range|personalprofile|about me)\b", project_text, re.I):
        heuristic_flags.append("project_profile_noise")
    if re.search(r"\b(dataanalyticseducation|dataanalyticsexperience)\b", parsed.get("full_name") or "", re.I):
        heuristic_flags.append("name_section_noise")

    return {
        "source": name,
        "name": parsed.get("full_name"),
        "email": parsed.get("email"),
        "phone": parsed.get("phone"),
        "last_company": company,
        "experience_years": exp_data.get("total_experience_years"),
        "project_names": [
            project.get("name")
            for project in parsed.get("projects") or []
            if isinstance(project, dict)
        ],
        "parser_flags": parsed.get("parser_flags") or [],
        "quality_action": report.get("parser_quality_action"),
        "quality_score": report.get("parser_quality_score"),
        "quality_flags": [item.get("code") for item in report.get("parser_quality_flags") or []],
        "heuristic_flags": heuristic_flags,
    }


def audit_path(path: Path, with_ai: bool = False) -> list[dict]:
    files = [path] if path.is_file() else [
        item for item in path.rglob("*") if item.suffix.lower() in {".pdf", ".docx", ".txt"}
    ]
    results = []
    for item in files:
        try:
            results.append(audit_text(str(item), _text_from_file(item), with_ai=with_ai))
        except Exception as exc:
            results.append({"source": str(item), "error": str(exc)})
    return results


def audit_db(with_ai: bool = False) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(Resume).filter(Resume.is_active == True).all()
        results = []
        for row in rows:
            text = row.resume_text or ""
            result = audit_text(row.resume_file_path or row.id, text, with_ai=with_ai)
            result["resume_id"] = row.id
            result["stored_name"] = row.full_name
            result["stored_last_company"] = row.last_company_name
            result["stored_projects_has_noise"] = bool(NOISE_PATTERN.search(row.projects or ""))
            results.append(result)
        return results
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Batch audit resume parser output.")
    parser.add_argument("--path", help="PDF/DOCX/TXT file or folder to audit")
    parser.add_argument("--db", action="store_true", help="Audit active resumes in resume_ai.db")
    parser.add_argument("--with-ai", action="store_true", help="Use OpenAI JSON extraction during audit")
    parser.add_argument("--only-issues", action="store_true", help="Print only rows with parser/quality flags")
    parser.add_argument("--output", help="Optional JSON output file")
    args = parser.parse_args()

    if not args.path and not args.db:
        parser.error("Provide --path or --db")

    results = audit_db(with_ai=args.with_ai) if args.db else audit_path(Path(args.path), with_ai=args.with_ai)
    if args.only_issues:
        results = [
            item for item in results
            if item.get("error")
            or item.get("heuristic_flags")
            or item.get("quality_action") != "auto_rank_ok"
            or item.get("parser_flags")
        ]

    payload = json.dumps(results, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
