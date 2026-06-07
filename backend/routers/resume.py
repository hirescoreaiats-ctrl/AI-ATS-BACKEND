from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from typing import List
import os
import uuid
import hashlib
import json
import tempfile
import re
import logging
from difflib import SequenceMatcher

from backend.database import SessionLocal
from backend.models import Job, Resume

from backend.extractor import extract_text_from_pdf, extract_text_from_docx
from backend.services.pipeline import analyze_resume_for_job
from backend.services.canonical_parser import parse_resume_document
from backend.ai.vector_search import enrich_candidate_embedding
from backend.jd_engine import normalize_jd_skills
from backend.services.candidate_intelligence import apply_resume_intelligence_fields, resume_intelligence_payload
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
    if mode in {"inline", "background"}:
        return mode

    legacy_inline = os.getenv("PROCESS_RESUMES_INLINE")
    if legacy_inline is not None and legacy_inline.strip().lower() in {"0", "false", "no", "background"}:
        return "background"
    return "inline"


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
    safe_tracking_url = (apply_tracking_url or "").strip()
    if not safe_tracking_url:
        safe_tracking_url = build_apply_links(job, db).get(safe_application_source) or build_apply_links(job, db)["main"]

    processed_count = 0
    duplicate_count = 0
    processed_resume_ids = []

    for file in files:
        contents = await file.read()
        validate_upload(file, len(contents))

        candidate_email = (form_email or "").strip().lower()
        candidate_phone = (form_phone or "").strip()
        identity_source = candidate_email or candidate_phone or f"{file.filename}|{len(contents)}"
        duplicate_key_source = f"{job_id}|{identity_source}"
        duplicate_key = hashlib.sha256(duplicate_key_source.encode()).hexdigest()
        duplicate_of = (
            _find_existing_application(db, job_id, candidate_email, candidate_phone)
            or db.query(Resume).filter(Resume.job_id == job_id, Resume.duplicate_key == duplicate_key, Resume.is_active == True).first()
        )
        if duplicate_of:
            duplicate_count += 1
            continue

        resume_id = str(uuid.uuid4())
        file_path = ""
        stored_file_path = ""
        blob_metadata = None

        if get_settings().use_vercel_blob_storage:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "")[1]) as temp_file:
                    temp_file.write(contents)
                    file_path = temp_file.name
                malware_scan(file_path)

                blob_metadata = upload_resume_file(
                    contents,
                    file.filename,
                    job_id,
                    resume_id,
                    organization_id=job.organization_id or "default_org",
                    mime_type=file.content_type,
                )
                stored_file_path = blob_metadata.storage_uri
                logger.info(
                    "Resume file stored: resume_id=%s job_id=%s storage=vercel_blob key=%s size=%s",
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
            file_path = secure_upload_path(file.filename)
            with open(file_path, "wb") as f:
                f.write(contents)
            malware_scan(file_path)
            stored_file_path = persist_resume_file(file_path, file.filename, file.content_type, job_id)
            logger.info(
                "Resume file stored: resume_id=%s job_id=%s storage=local path=%s size=%s",
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
            ranking_reason="Application received. AI screening is running in background.",
            ai_confidence_reason="Application received. AI screening is running in background.",
            duplicate_key=duplicate_key,
            duplicate_of_id=duplicate_of.id if duplicate_of else None,
            resume_file_path=stored_file_path,
            resume_file_url=blob_metadata.url if blob_metadata else None,
            resume_file_key=blob_metadata.key if blob_metadata else None,
            resume_original_filename=file.filename,
            resume_content_type=file.content_type,
            original_filename=file.filename,
            file_size=len(contents),
            mime_type=blob_metadata.mime_type if blob_metadata else file.content_type,
            uploaded_at=blob_metadata.uploaded_at if blob_metadata else None,
            explanation="Application received. AI screening is running in background.",
            shortlisted=False,
            shortlisted_auto=False,
            shortlisted_manual=False,
            status="Processing",
            stage="applied",
            is_active=True,
        )
        db.add(resume_entry)
        db.flush()
        logger.info(
            "Resume candidate row created: resume_id=%s job_id=%s filename=%s file_path=%s",
            resume_entry.id,
            job_id,
            file.filename,
            stored_file_path,
        )
        processed_resume_ids.append(resume_entry.id)
        processed_count += 1

    db.commit()
    logger.info(
        "Resume upload transaction committed: job_id=%s created=%s duplicates=%s",
        job_id,
        processed_count,
        duplicate_count,
    )
    db.close()

    processing_mode = _resume_processing_mode()
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
    else:
        for resume_id in processed_resume_ids:
            background_tasks.add_task(_process_resume_application_background, resume_id)

    if processed_count == 0 and duplicate_count:
        return {
            "message": "Application already submitted for this job.",
            "total_resumes": 0,
            "duplicates": duplicate_count,
            "processing": False,
        }

    if processed_count == 0:
        raise HTTPException(status_code=422, detail="No resume could be saved. Please upload a PDF or DOCX resume.")

    processing_failures = processing_results.count(False) if process_inline else 0
    if process_inline and processing_failures:
        message = f"Application received, but {processing_failures} resume(s) need manual review. Check backend logs."
    else:
        message = "Application processed successfully." if process_inline else "Application submitted. AI screening is running in background."

    return {
        "message": message,
        "total_resumes": processed_count,
        "duplicates": duplicate_count,
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
