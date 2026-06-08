from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from typing import List
import os
import uuid
import hashlib
import json
import tempfile
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from difflib import SequenceMatcher

from backend.database import SessionLocal
from backend.models import Job, Resume

from backend.extractor import extract_text_from_pdf, extract_text_from_docx
from backend.services.pipeline import analyze_resume_for_job
from backend.services.canonical_parser import parse_resume_document
from backend.ai.vector_search import enrich_candidate_embedding
from backend.jd_engine import normalize_jd_skills
from backend.services.candidate_intelligence import apply_resume_intelligence_fields, resume_intelligence_payload
from backend.services.document_classifier import classify_resume_document
from backend.services.jd_enrichment import enrich_jd_for_scoring
from backend.services.sourcing import build_apply_links, normalize_application_source, resolve_job_identifier
from backend.core.config import get_settings
from backend.services.storage import materialize_resume_file, persist_resume_file
from backend.services.storage_service import upload_resume_file
from backend.services.scoring_context import apply_job_scoring_snapshot
from backend.utils.upload_security import malware_scan, secure_upload_path, validate_upload
from backend.core.security import require_roles


router = APIRouter()
LEGACY_RECRUITER_DEPENDENCIES = [Depends(require_roles("admin", "recruiter", "hiring_manager"))]
logger = logging.getLogger(__name__)
_batch_size = get_settings().resume_processing_batch_size
_resume_processing_executor = ThreadPoolExecutor(max_workers=_batch_size)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _normalize_duplicate_phone(value: str | None) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    return digits[-10:] if len(digits) >= 10 else digits


def _identity_mismatch_reason(form_name="", form_email="", form_phone="", parsed=None):
    parsed = parsed or {}
    reasons = []
    parsed_email = (parsed.get("email") or "").strip().lower()
    parsed_phone = _normalize_duplicate_phone(parsed.get("phone"))
    form_email = (form_email or "").strip().lower()
    form_phone = _normalize_duplicate_phone(form_phone)
    if form_email and parsed_email and form_email != parsed_email:
        reasons.append("email mismatch")
    if form_phone and parsed_phone and form_phone != parsed_phone:
        reasons.append("phone mismatch")
    form_name_clean = re.sub(r"[^a-z]+", " ", str(form_name or "").lower()).strip()
    parsed_name_clean = re.sub(r"[^a-z]+", " ", str(parsed.get("full_name") or "").lower()).strip()
    if form_name_clean and parsed_name_clean:
        similarity = SequenceMatcher(None, form_name_clean, parsed_name_clean).ratio()
        if similarity < 0.58:
            reasons.append("name mismatch")
    return ", ".join(reasons)


def _find_existing_application(db, job_id: str, email: str | None = "", phone: str | None = "", exclude_id: str | None = None):
    email = (email or "").strip().lower()
    phone_digits = _normalize_duplicate_phone(phone)
    if not email and not phone_digits:
        return None

    query = db.query(Resume).filter(Resume.job_id == job_id, Resume.is_active == True)
    if exclude_id:
        query = query.filter(Resume.id != exclude_id)

    for candidate in query.all():
        candidate_email = ((candidate.email or candidate.form_email or "").strip().lower())
        candidate_phone = _normalize_duplicate_phone(candidate.phone or candidate.form_phone)
        if email and candidate_email and candidate_email == email:
            return candidate
        if phone_digits and candidate_phone and candidate_phone == phone_digits:
            return candidate
    return None


def _education_label(education):
    labels = []
    seen = set()
    for item in education or []:
        if not isinstance(item, dict):
            continue
        degree = (item.get("degree") or "").strip()
        field = (item.get("field") or "").strip()
        institution = (item.get("institution") or "").strip(" •-")
        dates = "-".join(str(part).strip() for part in [item.get("start_date"), item.get("end_date")] if part)
        main = " ".join(part for part in [degree, field] if part).strip()
        if institution:
            main = f"{main}, {institution}" if main else institution
        if dates:
            main = f"{main}, {dates}" if main else dates
        key = " ".join(main.lower().split())
        if main and key not in seen:
            seen.add(key)
            labels.append(main)
    return ", ".join(labels)


def _extract_resume_text_from_upload(filename: str, contents: bytes) -> str:
    suffix = os.path.splitext(filename or "")[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(contents)
        temp_path = temp_file.name

    try:
        if suffix == ".pdf":
            return extract_text_from_pdf(temp_path)
        if suffix == ".docx":
            return extract_text_from_docx(temp_path)
        return ""
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _preclassify_upload_resume(filename: str, contents: bytes):
    suffix = os.path.splitext(filename or "")[1].lower()
    if suffix not in {".pdf", ".docx"}:
        return None
    try:
        text = _extract_resume_text_from_upload(filename, contents)
    except Exception:
        logger.exception("Resume upload pre-classification extraction failed: filename=%s", filename)
        return None
    classification = classify_resume_document(text, filename=filename)
    logger.info(
        "Resume upload pre-classified: filename=%s label=%s positive=%s negative=%s reason=%s",
        filename,
        classification.label,
        classification.positive_signals,
        classification.negative_signals,
        classification.reason,
    )
    return classification


@router.post("/parse-resume-autofill")
async def parse_resume_autofill(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Resume file is empty")

    validate_upload(file, len(contents))
    text = _extract_resume_text_from_upload(file.filename or "", contents)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not read text from this resume")

    parsed = parse_resume_document(text[:12000], mode="autofill")
    safe_parsed = parsed.get("safe_parsed_json") or {}
    links = {
        "linkedin": parsed.get("linkedin") or "",
        "github": parsed.get("github") or "",
        "portfolio": parsed.get("portfolio") or "",
    }
    profile_url = links["linkedin"] or links["portfolio"] or links["github"]

    return {
        "fields": {
            "form_full_name": safe_parsed.get("full_name") or parsed.get("full_name") or "",
            "form_email": parsed.get("email") or "",
            "form_phone": safe_parsed.get("phone") or parsed.get("phone") or "",
            "form_location": parsed.get("location") or "",
            "linkedin": profile_url,
        },
        "safe_display": parsed.get("safe_display") or {},
        "field_confidence": parsed.get("field_confidence") or {},
        "field_sources": parsed.get("field_sources_json") or {},
        "parser_quality_score": parsed.get("parser_quality_score"),
        "parser_quality_action": parsed.get("parser_quality_action"),
        "parser_quality_flags": parsed.get("parser_quality_flags") or [],
        "profile_extraction_quality": parsed.get("profile_extraction_quality"),
        "text_extraction_quality": parsed.get("text_extraction_quality") or {},
    }


# ---------------- APPLY LINK RESUME UPLOAD ----------------


def _resume_processing_mode() -> str:
    mode = (os.getenv("RESUME_PROCESSING_MODE") or "").strip().lower()
    if mode in {"inline", "background", "queued"}:
        return mode

    legacy_inline = os.getenv("PROCESS_RESUMES_INLINE")
    if legacy_inline is not None and legacy_inline.strip().lower() in {"0", "false", "no", "background"}:
        return "background"
    if legacy_inline is not None and legacy_inline.strip().lower() in {"1", "true", "yes", "inline"}:
        return "inline"
    return "queued"


_HIDDEN_SYSTEM_UPLOADS = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
}


def _upload_filename(file: UploadFile) -> str:
    return (file.filename or "resume").replace("\\", "/")


def _skip_upload_reason(filename: str) -> str | None:
    basename = os.path.basename((filename or "").replace("\\", "/")).strip()
    lower = basename.lower()
    if not basename:
        return "File name is missing."
    if lower in _HIDDEN_SYSTEM_UPLOADS or basename.startswith("._"):
        return "Hidden/system file skipped."
    if basename.startswith("."):
        return "Hidden file skipped."
    if lower.endswith((".lnk", ".url")):
        return "Shortcut/link files are not resumes."
    return None


def _upload_result(
    filename: str,
    status: str,
    reason: str = "",
    resume_id: str | None = None,
    queued: bool = False,
    retryable: bool = False,
) -> dict:
    result = {
        "file": filename,
        "filename": filename,
        "status": status,
        "queued": queued,
    }
    if reason:
        result["reason"] = reason
    if resume_id:
        result["resume_id"] = resume_id
    if retryable:
        result["retryable"] = True
    return result


def _exception_reason(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return f"{type(exc).__name__}: {exc}"


def _queue_resume_processing(resume_id: str) -> None:
    logger.info("Resume processing queued: resume_id=%s", resume_id)
    _resume_processing_executor.submit(_process_resume_application_background, resume_id)


def _queue_resume_processing_batch(resume_ids: list[str]) -> None:
    if not resume_ids:
        return
    batch_size = get_settings().resume_processing_batch_size
    logger.info("Resume processing batch queued: total=%s batch_size=%s", len(resume_ids), batch_size)
    for index in range(0, len(resume_ids), batch_size):
        chunk = resume_ids[index:index + batch_size]
        logger.info(
            "Resume processing batch started: batch_number=%s batch_size=%s resume_ids=%s",
            (index // batch_size) + 1,
            len(chunk),
            chunk,
        )
        for resume_id in chunk:
            _queue_resume_processing(resume_id)


def _extract_resume_text_from_file_path(file_path: str, resume_id: str = "", original_filename: str | None = None) -> str:
    logger.info("Resume processing file materialize started: resume_id=%s path=%s", resume_id, file_path)
    local_path, should_cleanup = materialize_resume_file(file_path, original_filename=original_filename)
    logger.info(
        "Resume processing file materialized: resume_id=%s local_path=%s cleanup=%s",
        resume_id,
        local_path,
        should_cleanup,
    )
    try:
        lower = (local_path or "").lower()
        if lower.endswith(".pdf"):
            text = extract_text_from_pdf(local_path)
        elif lower.endswith(".docx"):
            text = extract_text_from_docx(local_path)
        else:
            text = ""
        logger.info("Resume text extracted: resume_id=%s length=%s", resume_id, len(text or ""))
        return text
    finally:
        if should_cleanup:
            try:
                os.remove(local_path)
            except OSError:
                pass


def _mark_resume_needs_review(db, resume: Resume, reason: str, resume_text: str = "") -> None:
    resume.resume_text = (resume_text or resume.resume_text or "")[:12000]
    resume.final_score = resume.final_score or 0
    resume.rank_score = resume.rank_score or 0
    resume.fit_band = resume.fit_band or "Needs Review"
    resume.ai_recommendation = "review"
    resume.ranking_reason = reason
    resume.ai_confidence_reason = reason
    resume.explanation = reason
    resume.processing_status = "failed"
    resume.processing_error = reason
    resume.processing_completed_at = datetime.utcnow()
    resume.status = "Needs Review"
    resume.stage = "review"
    db.commit()
    logger.warning("Resume marked Needs Review: resume_id=%s reason=%s", resume.id, reason)


def _process_resume_application_background(resume_id: str) -> bool:
    db = SessionLocal()
    resume = None
    try:
        logger.info("Resume processing started: resume_id=%s", resume_id)
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            logger.warning("Resume processing skipped; row not found: resume_id=%s", resume_id)
            return False

        logger.info(
            "Resume processing loaded row: resume_id=%s job_id=%s file_path=%s",
            resume.id,
            resume.job_id,
            resume.resume_file_path,
        )
        resume.processing_status = "processing"
        resume.processing_error = None
        resume.processing_started_at = datetime.utcnow()
        resume.processing_completed_at = None
        resume.status = "Processing"
        db.commit()

        job = db.query(Job).filter(Job.id == resume.job_id).first()
        if not job:
            _mark_resume_needs_review(db, resume, "Application received, but matching job was not found.")
            return False

        try:
            text = _extract_resume_text_from_file_path(
                resume.resume_file_path or "",
                resume_id=resume.id,
                original_filename=resume.original_filename or resume.resume_original_filename,
            )
        except Exception as exc:
            logger.exception("Resume text extraction failed for resume_id=%s path=%s", resume.id, resume.resume_file_path)
            resume.risk_flags = json.dumps(["resume_file_download_or_extract_failed"], ensure_ascii=False)
            resume.parser_quality_action = "manual_review_required"
            resume.parser_quality_flags = json.dumps([{
                "code": "resume_file_download_or_extract_failed",
                "severity": "critical",
                "message": f"Could not download or extract resume file: {type(exc).__name__}",
                "penalty": 100,
            }], ensure_ascii=False)
            db.commit()
            text = ""

        if not text.strip():
            _mark_resume_needs_review(db, resume, "Resume uploaded, but text could not be extracted. Recruiter review required.")
            return False

        resume_text = text[:12000]
        jd_skills = normalize_jd_skills(job.required_skills or "", job.jd_text or "")
        jd_data = {
            "min_experience_years": job.min_experience_years,
            "education": job.education,
            "role": job.role,
            "preferred_skills": job.preferred_skills or "",
        }

        try:
            logger.info("Resume parsing/scoring started: resume_id=%s job_id=%s", resume.id, job.id)
            parsed, exp_data, score_data = analyze_resume_for_job(
                text,
                job.jd_text or "",
                jd_skills,
                jd_data,
            )
            logger.info(
                "Resume parsing/scoring completed: resume_id=%s name=%s email=%s rank_score=%s final_score=%s",
                resume.id,
                parsed.get("full_name") if parsed else None,
                parsed.get("email") if parsed else None,
                parsed.get("rank_score") if parsed else None,
                parsed.get("final_score") if parsed else None,
            )
        except Exception as exc:
            logger.exception("Resume AI parsing/scoring failed for resume_id=%s", resume.id)
            resume.risk_flags = json.dumps(["resume_ai_parse_failed"], ensure_ascii=False)
            resume.parser_quality_action = "manual_review_required"
            resume.parser_quality_flags = json.dumps([{
                "code": "resume_ai_parse_failed",
                "severity": "critical",
                "message": f"AI parse/scoring failed: {type(exc).__name__}",
                "penalty": 100,
            }], ensure_ascii=False)
            db.commit()
            parsed, exp_data, score_data = None, {}, {}

        if not parsed:
            _mark_resume_needs_review(db, resume, "Resume uploaded, but AI parsing failed. Recruiter review required.", resume_text)
            return False

        mismatch_reason = _identity_mismatch_reason(resume.form_full_name, resume.form_email, resume.form_phone, parsed)
        if mismatch_reason:
            _mark_resume_needs_review(
                db,
                resume,
                f"Resume/result mismatch detected ({mismatch_reason}). Please re-parse correct resume.",
                resume_text,
            )
            resume.parser_quality_action = "manual_review_required"
            resume.parser_quality_flags = json.dumps([{
                "code": "identity_mismatch",
                "severity": "critical",
                "message": "Resume/result mismatch detected. Please re-parse correct resume.",
                "penalty": 100,
            }], ensure_ascii=False)
            resume.risk_flags = json.dumps(["identity_mismatch", "parser_quality_gate", "manual_review_required"], ensure_ascii=False)
            db.commit()
            return False

        parsed_email = (parsed.get("email") or resume.form_email or resume.email or "").strip().lower()
        parsed_phone = (parsed.get("phone") or resume.form_phone or resume.phone or "").strip()
        duplicate = _find_existing_application(db, resume.job_id, parsed_email, parsed_phone, exclude_id=resume.id)
        if duplicate:
            resume.email = parsed_email or resume.email
            resume.phone = parsed_phone or resume.phone
            resume.duplicate_of_id = duplicate.id
            resume.is_active = False
            resume.status = "Duplicate"
            resume.stage = "duplicate"
            resume.ranking_reason = "Duplicate application skipped. Candidate already applied for this job."
            resume.ai_confidence_reason = resume.ranking_reason
            resume.explanation = resume.ranking_reason
            resume.processing_status = "completed"
            resume.processing_error = None
            resume.processing_completed_at = datetime.utcnow()
            db.commit()
            logger.info("Resume processing completed as duplicate: resume_id=%s duplicate_of_id=%s", resume.id, duplicate.id)
            return True

        recommendation = parsed.get("recommendation")
        score = parsed.get("rank_score") or parsed.get("final_score") or 0
        shortlist_threshold = job.shortlist_score or 70
        ai_shortlisted = recommendation == "shortlisted" if recommendation else score >= shortlist_threshold

        if ai_shortlisted:
            status = "Shortlisted"
            stage = "shortlisted"
        elif recommendation == "rejected":
            status = "Rejected"
            stage = "rejected"
        else:
            status = "In Review"
            stage = "review"

        edu_string = _education_label(parsed.get("education") or [])
        resume.full_name = parsed.get("full_name") or resume.form_full_name or resume.full_name
        resume.email = (parsed.get("email") or resume.form_email or resume.email or "").strip().lower()
        resume.phone = (parsed.get("phone") or resume.form_phone or resume.phone or "").strip()
        resume.location = parsed.get("location") or resume.form_location or resume.location
        resume.key_skills = ", ".join(parsed.get("key_skills", [])) if parsed.get("key_skills") else ""
        resume.projects = json.dumps(parsed.get("projects") or [], ensure_ascii=False)
        resume.designation = parsed.get("designation")
        resume.total_experience_years = parsed.get("total_experience_years")
        resume.last_company_name = (exp_data or {}).get("last_company_name")
        resume.last_working_date = (exp_data or {}).get("last_working_date")
        resume.education = edu_string
        resume.industry = parsed.get("industry_category")
        resume.domain = parsed.get("domain")
        resume.final_score = parsed.get("final_score")
        resume.rank_score = parsed.get("rank_score")
        resume.fit_band = parsed.get("fit_band")
        resume.skill_score = parsed.get("skill_score")
        resume.experience_score = parsed.get("experience_score")
        resume.confidence_score = parsed.get("confidence_score")
        resume.resume_quality_score = parsed.get("resume_quality_score")
        resume.ai_recommendation = parsed.get("recommendation")
        resume.ranking_reason = parsed.get("ranking_reason")
        resume.ai_confidence_reason = _text_value(parsed.get("ai_recruiter_explanation"))
        resume.matched_skills = ",".join(parsed.get("matched_skills", []))
        resume.missing_skills = ",".join(parsed.get("missing_skills", []))
        resume.skill_match_percent = parsed.get("skill_match_percent")
        apply_resume_intelligence_fields(resume, parsed)
        apply_job_scoring_snapshot(resume, job, parsed.get("jd_profile_json"))
        resume.resume_text = resume_text
        resume.explanation = _text_value(parsed.get("ai_recruiter_explanation"))
        resume.shortlisted = ai_shortlisted
        resume.shortlisted_auto = ai_shortlisted
        resume.shortlisted_manual = False
        resume.status = status
        resume.stage = stage
        resume.processing_status = "completed"
        resume.processing_error = None
        resume.processing_completed_at = datetime.utcnow()

        try:
            enrich_candidate_embedding(resume)
        except Exception:
            pass

        db.commit()
        logger.info(
            "Resume DB candidate updated: resume_id=%s name=%s email=%s score=%s status=%s stage=%s",
            resume.id,
            resume.full_name,
            resume.email,
            resume.rank_score or resume.final_score,
            resume.status,
            resume.stage,
        )
        return True
    except Exception as exc:
        logger.exception("Resume processing failed with exception: resume_id=%s", resume_id)
        db.rollback()
        try:
            failed_resume = db.query(Resume).filter(Resume.id == resume_id).first()
            if failed_resume:
                _mark_resume_needs_review(
                    db,
                    failed_resume,
                    f"Resume processing failed: {type(exc).__name__}. Check backend logs for details.",
                )
        except Exception:
            logger.exception("Failed to mark resume Needs Review after processing exception: resume_id=%s", resume_id)
        return False
    finally:
        db.close()


@router.post("/upload-resumes/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
@router.post("/public-upload-resumes/{job_id}")
async def upload_resumes(

    job_id: str,
    background_tasks: BackgroundTasks,

    form_full_name: str = Form(None),
    form_email: str = Form(None),
    form_phone: str = Form(None),
    form_location: str = Form(None),

    expected_salary: str = Form(None),
    preferred_location: str = Form(None),
    notice_period: str = Form(None),

    linkedin: str = Form(None),
    github: str = Form(None),
    portfolio: str = Form(None),
    application_source: str = Form(None),
    apply_tracking_url: str = Form(None),
    folder_total_count: int = Form(None),

    files: List[UploadFile] = File(...)
):

    db = SessionLocal()

    job = resolve_job_identifier(job_id, db)

    if not job:
        db.close()
        raise HTTPException(status_code=404, detail="Job not found")
    job_id = job.id
    safe_application_source = normalize_application_source(application_source)
    if job.source_tracking_enabled is False:
        safe_application_source = "direct"
    max_resume_upload_count = get_settings().max_resume_upload_count
    if safe_application_source == "folder":
        requested_count = folder_total_count or len(files)
        if requested_count > max_resume_upload_count:
            db.close()
            raise HTTPException(status_code=413, detail=f"Maximum {max_resume_upload_count} resumes can be synced at once.")
        logger.info(
            "Folder sync upload started: job_id=%s requested_count=%s batch_size=%s",
            job_id,
            requested_count,
            get_settings().resume_processing_batch_size,
        )
    elif len(files) > max_resume_upload_count:
        db.close()
        raise HTTPException(status_code=413, detail=f"Maximum {max_resume_upload_count} resumes can be uploaded at once.")
    safe_tracking_url = (apply_tracking_url or "").strip()
    if not safe_tracking_url:
        safe_tracking_url = build_apply_links(job, db).get(safe_application_source) or build_apply_links(job, db)["main"]

    request_id = uuid.uuid4().hex[:12]
    processed_count = 0
    duplicate_count = 0
    skipped_count = 0
    failed_count = 0
    upload_messages = []
    processed_resume_ids = []
    seen_duplicate_keys = set()

    logger.info(
        "Resume upload request started: request_id=%s job_id=%s total_files=%s source=%s",
        request_id,
        job_id,
        len(files),
        safe_application_source,
    )

    try:
        for file in files:
            filename = _upload_filename(file)
            logger.info(
                "Resume upload file received: request_id=%s job_id=%s filename=%s content_type=%s",
                request_id,
                job_id,
                filename,
                file.content_type,
            )
            skip_reason = _skip_upload_reason(filename)
            if skip_reason:
                skipped_count += 1
                upload_messages.append(_upload_result(filename, "skipped", skip_reason))
                logger.info(
                    "Resume upload skipped before read: request_id=%s job_id=%s filename=%s reason=%s",
                    request_id,
                    job_id,
                    filename,
                    skip_reason,
                )
                continue

            contents = b""
            file_path = ""
            try:
                contents = await file.read()
                if not contents:
                    skipped_count += 1
                    upload_messages.append(_upload_result(filename, "skipped", "File is empty."))
                    logger.info(
                        "Resume upload skipped empty file: request_id=%s job_id=%s filename=%s",
                        request_id,
                        job_id,
                        filename,
                    )
                    continue

                validate_upload(file, len(contents))

                # Single candidate submissions still get the lightweight document guard.
                # Folder/bulk sync skips it so upload returns quickly and parsing happens in the worker.
                if safe_application_source != "folder" and len(files) == 1:
                    classification = _preclassify_upload_resume(filename, contents)
                    if classification and not classification.is_resume:
                        skipped_count += 1
                        upload_messages.append(_upload_result(filename, "skipped", classification.reason))
                        logger.warning(
                            "Resume upload skipped non-resume document: request_id=%s job_id=%s filename=%s reason=%s",
                            request_id,
                            job_id,
                            filename,
                            classification.reason,
                        )
                        continue

                candidate_email = (form_email or "").strip().lower()
                candidate_phone = (form_phone or "").strip()
                file_hash = hashlib.sha256(contents).hexdigest()
                identity_source = candidate_email or candidate_phone or f"file|{file_hash}"
                duplicate_key_source = f"{job_id}|{identity_source}"
                duplicate_key = hashlib.sha256(duplicate_key_source.encode()).hexdigest()
                file_duplicate_key = hashlib.sha256(f"{job_id}|file|{file_hash}".encode()).hexdigest()
                if duplicate_key in seen_duplicate_keys or file_duplicate_key in seen_duplicate_keys:
                    duplicate_count += 1
                    upload_messages.append(_upload_result(filename, "duplicate", "Duplicate resume skipped."))
                    logger.info(
                        "Resume upload duplicate skipped within request: request_id=%s job_id=%s filename=%s",
                        request_id,
                        job_id,
                        filename,
                    )
                    continue
                duplicate_of = (
                    _find_existing_application(db, job_id, candidate_email, candidate_phone)
                    or db.query(Resume).filter(Resume.job_id == job_id, Resume.duplicate_key == duplicate_key, Resume.is_active == True).first()
                    or db.query(Resume).filter(Resume.job_id == job_id, Resume.duplicate_key == file_duplicate_key, Resume.is_active == True).first()
                )
                if duplicate_of:
                    duplicate_count += 1
                    upload_messages.append(_upload_result(filename, "duplicate", "Candidate already exists for this job."))
                    logger.info(
                        "Resume upload duplicate skipped in database: request_id=%s job_id=%s filename=%s duplicate_of_id=%s",
                        request_id,
                        job_id,
                        filename,
                        duplicate_of.id,
                    )
                    continue

                resume_id = str(uuid.uuid4())
                stored_file_path = ""
                blob_metadata = None

                if get_settings().use_vercel_blob_storage:
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                            temp_file.write(contents)
                            file_path = temp_file.name
                        malware_scan(file_path)

                        blob_metadata = upload_resume_file(
                            contents,
                            filename,
                            job_id,
                            resume_id,
                            organization_id=job.organization_id or "default_org",
                            mime_type=file.content_type,
                        )
                        stored_file_path = blob_metadata.storage_uri
                        logger.info(
                            "Resume file stored: request_id=%s resume_id=%s job_id=%s storage=vercel_blob key=%s size=%s",
                            request_id,
                            resume_id,
                            job_id,
                            blob_metadata.key,
                            blob_metadata.file_size,
                        )
                    finally:
                        if file_path:
                            try:
                                os.remove(file_path)
                            except OSError:
                                pass
                else:
                    file_path = secure_upload_path(filename)
                    with open(file_path, "wb") as f:
                        f.write(contents)
                    malware_scan(file_path)
                    stored_file_path = persist_resume_file(file_path, filename, file.content_type, job_id)
                    logger.info(
                        "Resume file stored: request_id=%s resume_id=%s job_id=%s storage=local path=%s size=%s",
                        request_id,
                        resume_id,
                        job_id,
                        stored_file_path,
                        len(contents),
                    )
                    file_path = ""

                resume_entry = Resume(
                    id=resume_id,
                    job_id=job_id,
                    organization_id=job.organization_id,
                    full_name=form_full_name,
                    email=candidate_email,
                    phone=candidate_phone,
                    location=form_location,
                    form_full_name=form_full_name,
                    form_email=form_email,
                    form_phone=form_phone,
                    form_location=form_location,
                    expected_salary=expected_salary,
                    preferred_location=preferred_location,
                    notice_period=notice_period,
                    linkedin=linkedin,
                    github=github,
                    portfolio=portfolio,
                    application_source=safe_application_source,
                    apply_tracking_url=safe_tracking_url,
                    final_score=0,
                    rank_score=0,
                    fit_band="Processing",
                    ai_recommendation="processing",
                    ranking_reason="Application received. AI screening is pending.",
                    ai_confidence_reason="Application received. AI screening is pending.",
                    duplicate_key=duplicate_key,
                    duplicate_of_id=duplicate_of.id if duplicate_of else None,
                    resume_file_path=stored_file_path,
                    resume_file_url=blob_metadata.url if blob_metadata else None,
                    resume_file_key=blob_metadata.key if blob_metadata else None,
                    resume_original_filename=filename,
                    resume_content_type=file.content_type,
                    original_filename=filename,
                    file_size=len(contents),
                    mime_type=blob_metadata.mime_type if blob_metadata else file.content_type,
                    uploaded_at=blob_metadata.uploaded_at if blob_metadata else None,
                    processing_status="pending",
                    processing_error=None,
                    explanation="Application received. AI screening is pending.",
                    shortlisted=False,
                    shortlisted_auto=False,
                    shortlisted_manual=False,
                    status="Pending Processing" if safe_application_source == "folder" else "Processing",
                    stage="applied",
                    is_active=True,
                )
                db.add(resume_entry)
                db.flush()
                db.commit()
                logger.info(
                    "Resume candidate row created: request_id=%s resume_id=%s job_id=%s filename=%s file_path=%s",
                    request_id,
                    resume_entry.id,
                    job_id,
                    filename,
                    stored_file_path,
                )
                processed_resume_ids.append(resume_entry.id)
                upload_messages.append(_upload_result(filename, "uploaded", resume_id=resume_entry.id, queued=True))
                seen_duplicate_keys.add(duplicate_key)
                seen_duplicate_keys.add(file_duplicate_key)
                processed_count += 1
            except HTTPException as exc:
                db.rollback()
                status_label = "skipped" if exc.status_code in {400, 413, 415, 422} else "failed"
                if status_label == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
                upload_messages.append(_upload_result(filename, status_label, _exception_reason(exc), retryable=exc.status_code >= 500))
                logger.exception(
                    "Resume upload file failed: request_id=%s job_id=%s filename=%s status=%s reason=%s",
                    request_id,
                    job_id,
                    filename,
                    status_label,
                    _exception_reason(exc),
                )
            except Exception as exc:
                db.rollback()
                failed_count += 1
                upload_messages.append(_upload_result(filename, "failed", _exception_reason(exc), retryable=True))
                logger.exception(
                    "Resume upload file failed with traceback: request_id=%s job_id=%s filename=%s",
                    request_id,
                    job_id,
                    filename,
                )
    except Exception as exc:
        db.rollback()
        logger.exception("Resume upload batch failed unexpectedly: request_id=%s job_id=%s", request_id, job_id)
        failed_count += max(1, len(files) - processed_count - duplicate_count - skipped_count)
        upload_messages.append(_upload_result("batch", "failed", _exception_reason(exc), retryable=True))

    logger.info(
        "Resume upload transaction completed: request_id=%s job_id=%s created=%s duplicates=%s skipped=%s failed=%s",
        request_id,
        job_id,
        processed_count,
        duplicate_count,
        skipped_count,
        failed_count,
    )
    db.close()

    processing_mode = _resume_processing_mode()
    if (safe_application_source == "folder" or len(files) > 1) and processing_mode == "inline":
        processing_mode = (os.getenv("FOLDER_RESUME_PROCESSING_MODE") or "queued").strip().lower()
        if processing_mode not in {"queued", "inline", "background"}:
            processing_mode = "queued"
    process_inline = processing_mode == "inline"
    processing_results = []
    logger.info(
        "Resume upload processing dispatch: job_id=%s mode=%s resume_ids=%s",
        job_id,
        processing_mode,
        processed_resume_ids,
    )
    if process_inline:
        for resume_id in processed_resume_ids:
            processing_results.append(_process_resume_application_background(resume_id))
    elif processing_mode == "queued":
        _queue_resume_processing_batch(processed_resume_ids)
    else:
        for resume_id in processed_resume_ids:
            background_tasks.add_task(_process_resume_application_background, resume_id)

    processing_failures = processing_results.count(False) if process_inline else 0
    if process_inline and processing_failures:
        message = f"Application received, but {processing_failures} resume(s) need manual review. Check backend logs."
    elif processed_count == 0 and duplicate_count:
        message = "Application already submitted for this job."
    elif processed_count == 0:
        message = "No resume could be saved. Please upload valid PDF, DOC, or DOCX resumes."
    else:
        message = "Application processed successfully." if process_inline else f"{processed_count} resume(s) uploaded. Processing has started."

    overall_status = "success"
    if failed_count or skipped_count or duplicate_count or processing_failures:
        overall_status = "partial_success" if processed_count else "failed"

    return {
        "request_id": request_id,
        "status": overall_status,
        "message": message,
        "uploaded": processed_count,
        "failed": failed_count,
        "queued": len(processed_resume_ids) if not process_inline else 0,
        "total_resumes": processed_count,
        "duplicates": duplicate_count,
        "skipped": skipped_count,
        "messages": upload_messages[:50],
        "files": upload_messages,
        "processing": not process_inline,
        "processing_mode": processing_mode,
        "processing_failures": processing_failures,
    }

    jd_text = job.jd_text

    jd_skills = normalize_jd_skills(job.required_skills or "", job.jd_text or "")

    jd_data = {
        "min_experience_years": job.min_experience_years,
        "education": job.education,
        "role": job.role,
        "preferred_skills": job.preferred_skills or ""
    }

    processed_count = 0

    def save_basic_application(file, file_path: str, resume_text: str, reason: str) -> None:
        nonlocal processed_count
        candidate_email = (form_email or "").strip().lower()
        candidate_phone = (form_phone or "").strip()
        identity_source = candidate_email or candidate_phone or f"{file.filename}|{resume_text[:500]}"
        duplicate_key_source = f"{job_id}|{identity_source}"
        duplicate_key = hashlib.sha256(duplicate_key_source.encode()).hexdigest()
        duplicate_of = db.query(Resume).filter(Resume.job_id == job_id, Resume.duplicate_key == duplicate_key).first()

        resume_entry = Resume(
            job_id=job_id,
            organization_id=job.organization_id,
            full_name=form_full_name,
            email=candidate_email,
            phone=candidate_phone,
            location=form_location,
            form_full_name=form_full_name,
            form_email=form_email,
            form_phone=form_phone,
            form_location=form_location,
            expected_salary=expected_salary,
            preferred_location=preferred_location,
            notice_period=notice_period,
            linkedin=linkedin,
            github=github,
            portfolio=portfolio,
            application_source=safe_application_source,
            apply_tracking_url=safe_tracking_url,
            final_score=0,
            rank_score=0,
            fit_band="Needs Review",
            ai_recommendation="review",
            ranking_reason=reason,
            ai_confidence_reason=reason,
            duplicate_key=duplicate_key,
            duplicate_of_id=duplicate_of.id if duplicate_of else None,
            resume_text=(resume_text or "")[:12000],
            resume_file_path=file_path,
            resume_original_filename=file.filename,
            resume_content_type=file.content_type,
            explanation=reason,
            shortlisted=False,
            shortlisted_auto=False,
            shortlisted_manual=False,
            status="Needs Review",
            stage="review",
            is_active=True,
        )
        db.add(resume_entry)
        processed_count += 1

    for file in files:

        contents = await file.read()
        validate_upload(file, len(contents))
        file_path = secure_upload_path(file.filename)

        with open(file_path, "wb") as f:
            f.write(contents)
        malware_scan(file_path)

        try:
            if file.filename.lower().endswith(".pdf"):
                text = extract_text_from_pdf(file_path)
            elif file.filename.lower().endswith(".docx"):
                text = extract_text_from_docx(file_path)
            else:
                text = ""
        except Exception:
            text = ""

        if not text.strip():
            save_basic_application(file, file_path, "", "Resume uploaded, but text could not be extracted. Recruiter review required.")
            continue
        # 🔥 SAVE FULL RESUME TEXT (IMPORTANT)
        resume_text = text[:12000]

        try:
            parsed, exp_data, score_data = analyze_resume_for_job(
                text,
                jd_text,
                jd_skills,
                jd_data
            )
        except Exception:
            parsed, exp_data, score_data = None, {}, {}

        if not parsed:
            save_basic_application(file, file_path, resume_text, "Resume uploaded, but AI parsing failed. Recruiter review required.")
            continue

        last_company = exp_data.get("last_company_name")
        last_working_date = exp_data.get("last_working_date")
        # -------- GET JOB --------
        job = db.query(Job).filter(Job.id == job_id).first()

        # -------- AUTO SHORTLIST --------

        score = parsed.get("rank_score") or parsed.get("final_score") or 0
        shortlist_threshold = job.shortlist_score or 70

        # 🤖 AI SHORTLIST
        recommendation = parsed.get("recommendation")

        if recommendation == "shortlisted" if recommendation else score >= shortlist_threshold:
            ai_shortlisted = True
        else:
            ai_shortlisted = False

        # 📊 STATUS
        if ai_shortlisted:
            status = "Shortlisted"
            stage = "shortlisted"
        elif recommendation == "rejected":
            status = "Rejected"
            stage = "rejected"
        else:
            status = "In Review"
            stage = "review"


        # ---------- EDUCATION FORMAT ----------

        edu_list = parsed.get("education") or []

        edu_string = _education_label(edu_list)


        # ---------- SAVE TO DATABASE ----------

        candidate_email = (parsed.get("email") or form_email or "").strip().lower()
        candidate_phone = (parsed.get("phone") or form_phone or "").strip()
        identity_fallback = hashlib.sha256(text[:3000].encode(errors="ignore")).hexdigest()
        duplicate_key_source = f"{job_id}|{candidate_email or identity_fallback}|{candidate_phone or identity_fallback}"
        duplicate_key = hashlib.sha256(duplicate_key_source.encode()).hexdigest()
        duplicate_of = db.query(Resume).filter(Resume.job_id == job_id, Resume.duplicate_key == duplicate_key).first()

        resume_entry = Resume(

    job_id=job_id,
    organization_id=job.organization_id,

    full_name=parsed.get("full_name"),
    email=parsed.get("email"),
    phone=parsed.get("phone"),
    location=parsed.get("location"),

    form_full_name=form_full_name,
    form_email=form_email,
    form_phone=form_phone,
    form_location=form_location,

    expected_salary=expected_salary,
    preferred_location=preferred_location,
    notice_period=notice_period,

    linkedin=linkedin,
    github=github,
    portfolio=portfolio,
    application_source=safe_application_source,
    apply_tracking_url=safe_tracking_url,

    key_skills=", ".join(parsed.get("key_skills", []))
    if parsed.get("key_skills") else "",
    projects=json.dumps(parsed.get("projects") or [], ensure_ascii=False),

    designation=parsed.get("designation"),

    total_experience_years=parsed.get("total_experience_years"),

    last_company_name=last_company,
    last_working_date=last_working_date,

    education=edu_string,
    industry=parsed.get("industry_category"),
    domain=parsed.get("domain"),

    final_score=parsed.get("final_score"),
    rank_score=parsed.get("rank_score"),
    fit_band=parsed.get("fit_band"),
    skill_score=parsed.get("skill_score"),
    experience_score=parsed.get("experience_score"),
    confidence_score=parsed.get("confidence_score"),
    resume_quality_score=parsed.get("resume_quality_score"),
    ai_recommendation=parsed.get("recommendation"),
    ranking_reason=parsed.get("ranking_reason"),
    ai_confidence_reason=_text_value(parsed.get("ai_recruiter_explanation")),
    duplicate_key=duplicate_key,
    duplicate_of_id=duplicate_of.id if duplicate_of else None,

    matched_skills=",".join(parsed.get("matched_skills", [])),
    missing_skills=",".join(parsed.get("missing_skills", [])),
    skill_match_percent=parsed.get("skill_match_percent"),
    resume_text=resume_text,
    resume_file_path=file_path,
    resume_original_filename=file.filename,
    resume_content_type=file.content_type,
    explanation=_text_value(parsed.get("ai_recruiter_explanation")),

    # 🔥 FIXED
    shortlisted=ai_shortlisted,
    shortlisted_auto=ai_shortlisted,
    shortlisted_manual=False,
    status=status,
    stage=stage,

    is_active=True
)
        apply_resume_intelligence_fields(resume_entry, parsed)
        apply_job_scoring_snapshot(resume_entry, job, parsed.get("jd_profile_json"))
        enrich_candidate_embedding(resume_entry)
        db.add(resume_entry)

        processed_count += 1

    db.commit()
    db.close()

    if processed_count == 0:
        raise HTTPException(status_code=422, detail="No resume could be saved. Please upload a PDF or DOCX resume.")

    return {
        "message": "Resumes processed successfully",
        "total_resumes": processed_count
    }


@router.get("/resume-processing-progress/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def resume_processing_progress(job_id: str):
    db = SessionLocal()
    try:
        job = resolve_job_identifier(job_id, db)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        rows = db.query(Resume).filter(Resume.job_id == job.id, Resume.is_active == True).all()
        total = len(rows)
        pending = sum(1 for row in rows if (row.processing_status or "").lower() == "pending")
        processing = sum(1 for row in rows if (row.processing_status or "").lower() == "processing")
        failed = sum(1 for row in rows if (row.processing_status or "").lower() == "failed")
        completed = sum(1 for row in rows if (row.processing_status or "").lower() == "completed")
        needs_review = sum(1 for row in rows if (row.status or "").lower() == "needs review" or (row.processing_status or "").lower() == "failed")
        done = completed + failed
        percent = int(round((done / total) * 100)) if total else 0
        return {
            "job_id": job.id,
            "total": total,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "needs_review": needs_review,
            "percent": percent,
        }
    finally:
        db.close()


# ---------------- BULK RESUME ANALYZER ----------------

@router.post("/bulk-analyze", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
async def bulk_analyze(
    jd_text: str = Form(...),
    files: List[UploadFile] = File(...)
):

    results = []

    enrichment = enrich_jd_for_scoring(jd_text)
    jd_skills = enrichment.get("required_skills") or normalize_jd_skills([], jd_text)

    jd_data = {
        "min_experience_years": enrichment.get("min_experience_years", 0),
        "education": enrichment.get("education", ""),
        "role": enrichment.get("role", ""),
        "preferred_skills": enrichment.get("preferred_skills", [])
    }

    for file in files:

        contents = await file.read()
        validate_upload(file, len(contents))
        file_path = secure_upload_path(file.filename)

        with open(file_path, "wb") as f:
            f.write(contents)
        malware_scan(file_path)

        if file.filename.lower().endswith(".pdf"):
            text = extract_text_from_pdf(file_path)

        elif file.filename.lower().endswith(".docx"):
            text = extract_text_from_docx(file_path)

        else:
            continue

        if not text.strip():
            continue

        parsed, exp_data, score_data = analyze_resume_for_job(
            text,
            jd_text,
            jd_skills,
            jd_data
        )




        results.append({

            "file_name": file.filename,

            "full_name": parsed.get("full_name"),
            "email": parsed.get("email"),
            "phone": parsed.get("phone"),
            "location": parsed.get("location"),

            "designation": parsed.get("designation"),

            "total_experience_years": parsed.get("total_experience_years"),

            "last_company_name": exp_data["last_company_name"],
            "last_working_date": exp_data["last_working_date"],

            "matched_skills": parsed.get("matched_skills"),
            "missing_skills": parsed.get("missing_skills"),
            "skill_match_percent": parsed.get("skill_match_percent"),

            "industry": parsed.get("industry_category"),
            "domain": parsed.get("domain"),

            "education": parsed.get("education"),

            "final_score": parsed.get("final_score"),
            "rank_score": parsed.get("rank_score"),
            "fit_band": parsed.get("fit_band"),

            "semantic_score": parsed.get("semantic_score"),
            "confidence_score": parsed.get("confidence_score"),
            "seniority_level": parsed.get("seniority_level"),
            "recommendation": parsed.get("recommendation"),
            "ranking_reason": parsed.get("ranking_reason"),
            "resume_quality_score": parsed.get("resume_quality_score"),
            "relevant_experience_years": parsed.get("relevant_experience_years"),
            "direct_relevant_experience_years": parsed.get("direct_relevant_experience_years"),
            "transferable_experience_years": parsed.get("transferable_experience_years"),
            "senior_role_experience_years": parsed.get("senior_role_experience_years"),
            "role_family": parsed.get("role_family"),
            "role_relevance_score": parsed.get("role_relevance_score"),
            "mandatory_skill_coverage": parsed.get("mandatory_skill_coverage"),
            "core_skill_match_percent": parsed.get("core_skill_match_percent"),
            "missing_core_skill_groups": parsed.get("missing_core_skill_groups"),
            "parser_quality_score": parsed.get("parser_quality_score"),
            "parser_quality_action": parsed.get("parser_quality_action"),
            "parser_quality_flags": parsed.get("parser_quality_flags"),
            "profile_extraction_quality": parsed.get("profile_extraction_quality"),
            "safe_display": parsed.get("safe_display"),
            "field_confidence": parsed.get("field_confidence"),
            "field_sources": parsed.get("field_sources_json"),
            "text_extraction_quality": parsed.get("text_extraction_quality"),
            "safe_parsed_json": parsed.get("safe_parsed_json"),
            "score_caps_applied": parsed.get("score_caps_applied"),
            "recruiter_flags": parsed.get("recruiter_flags"),
            "risk_flags": parsed.get("risk_flags"),
            "scoring_breakdown": parsed.get("scoring_breakdown"),
            "jd_profile_json": parsed.get("jd_profile_json"),
            "transferable_skills": parsed.get("transferable_skills"),
            "projects": parsed.get("projects"),
            "ai_recruiter_explanation": parsed.get("ai_recruiter_explanation")

        })

    sorted_results = sorted(
        results,
        key=lambda x: x.get("rank_score") or x.get("final_score") or 0,
        reverse=True
    )
    return {
        "total_resumes": len(sorted_results),
        "results": sorted_results
    }

from pydantic import BaseModel
from backend.explanation_service import generate_candidate_explanation

class CandidateExplainRequest(BaseModel):
    candidate: dict
    jd_text: str


@router.post("/candidate-ai-explain", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
async def candidate_ai_explain(data: CandidateExplainRequest):

    explanation = generate_candidate_explanation(
        data.candidate,
        data.jd_text
    )

    return {
        "explanation": explanation
    }

from datetime import datetime

from fastapi import Query
from datetime import datetime

@router.get("/ai-explanation/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_ai_explanation(resume_id: str, force: bool = Query(False)):

    db = SessionLocal()

    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id).first()

        if not candidate:
            return {"error": "Candidate not found"}

        job = db.query(Job).filter(Job.id == candidate.job_id).first()
        projects = []
        if candidate.projects:
            try:
                parsed_projects = json.loads(candidate.projects)
                projects = parsed_projects if isinstance(parsed_projects, list) else []
            except Exception:
                projects = []

        candidate_payload = {
            "id": candidate.id,
            "job_id": candidate.job_id,
            "name": candidate.full_name or candidate.form_full_name,
            "email": candidate.email or candidate.form_email,
            "phone": candidate.phone or candidate.form_phone,
            "location": candidate.location or candidate.form_location,
            "job_title": job.job_title if job else "",
            "company_name": job.company_name if job else "",
            "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
            "explanation_generated_at": candidate.explanation_generated_at.isoformat() if candidate.explanation_generated_at else None,
            "final_score": candidate.final_score,
            "rank_score": candidate.rank_score,
            "fit_band": candidate.fit_band,
            "score": candidate.final_score,
            "confidence_score": candidate.confidence_score,
            "status": candidate.status,
            "stage": candidate.stage,
            "current_stage": candidate.status or candidate.stage or "Review",
            "designation": candidate.designation,
            "experience": candidate.total_experience_years,
            "total_experience_years": candidate.total_experience_years,
            "last_company": candidate.last_company_name,
            "last_company_name": candidate.last_company_name,
            "last_working_date": candidate.last_working_date,
            "education": candidate.education,
            "industry": candidate.industry,
            "domain": candidate.domain,
            "matched_skills": candidate.matched_skills or candidate.key_skills,
            "key_skills": candidate.key_skills,
            "missing_skills": candidate.missing_skills,
            "skill_match_percent": candidate.skill_match_percent,
            "skill_score": candidate.skill_score,
            "experience_score": candidate.experience_score,
            "resume_quality_score": candidate.resume_quality_score,
            "ranking_reason": candidate.ranking_reason,
            "ai_recommendation": candidate.ai_recommendation,
        }
        candidate_payload.update(resume_intelligence_payload(candidate))

        # 🔹 NORMAL MODE (NO NEW CALL)
        if candidate.explanation and not force:
            return {
                "explanation": candidate.explanation,
                "projects": projects,
                "candidate": candidate_payload,
                "cached": True,
                "generated_at": candidate.explanation_generated_at.isoformat() if candidate.explanation_generated_at else None,
            }

        # 🔥 FORCE MODE (NEW AI CALL)
        candidate_data = {
            "full_name": candidate.full_name,
            "designation": candidate.designation,
            "total_experience_years": candidate.total_experience_years,
            "matched_skills": candidate.matched_skills,
            "missing_skills": candidate.missing_skills,
            "skill_match_percent": candidate.skill_match_percent,
            "final_score": candidate.final_score,
            "projects": projects,
            "resume_text": (candidate.resume_text or "")[:3000]
        }

        explanation = generate_candidate_explanation(
            candidate_data,
            job.jd_text if job else ""
        )

        # 🔥 REPLACE OLD
        candidate.explanation = explanation
        candidate.explanation_generated_at = datetime.utcnow()

        db.commit()

        return {
            "explanation": explanation,
            "projects": projects,
            "candidate": candidate_payload,
            "cached": False,
            "generated_at": candidate.explanation_generated_at.isoformat() if candidate.explanation_generated_at else None,
        }

    finally:
        db.close()
