from fastapi import APIRouter, Body, Depends, Query, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse, RedirectResponse
import csv
import base64
import hashlib
import html
import io
import json
import logging
import mimetypes
import os
import re
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlencode
import requests
from sqlalchemy import func

from backend.jd_engine import extract_structured_jd, normalize_jd_skills
from backend.extractor import extract_text_from_docx, extract_text_from_pdf, normalize_extracted_text
from backend.database import SessionLocal
from backend.models import Assessment, CandidateAssessment, CandidateActivity, CandidateNote, CandidateStageHistory, CandidateTag, Interview, Job, Resume, User
from backend.domain_engine import detect_domain
from backend.experience_engine import process_experience
from backend.services.candidate_intelligence import apply_resume_intelligence_fields, resume_intelligence_payload
from backend.services.explanation_service import generate_recruiter_explanation
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.parsing_service import parse_resume_enterprise
from backend.services.pipeline import analyze_resume_for_job
from backend.services.scoring_service import score_candidate
from backend.services.semantic_service import cosine_similarity_cached
from backend.services.storage import download_supabase_file, is_supabase_uri, persist_resume_file
from backend.services.sourcing import (
    TRACKED_APPLICATION_SOURCES,
    build_apply_links,
    ensure_apply_slug,
    ensure_generated_sourcing_content,
    generate_ai_sourcing_posts,
    normalize_application_source,
    resolve_job_identifier,
    sourcing_payload,
)
from backend.core.config import get_settings
from backend.core.security import bearer_token, create_candidate_tracking_token, decode_candidate_tracking_token, decode_token, require_roles
from backend.utils.sanitize import sanitize_text

router = APIRouter()
LEGACY_RECRUITER_DEPENDENCIES = [Depends(require_roles("admin", "recruiter", "hiring_manager"))]
logger = logging.getLogger(__name__)

REQUIRED_GOOGLE_ASSESSMENT_SCOPES = {
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
}


def _text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _email_from_request_token(request: Request) -> str:
    try:
        token = bearer_token(request)
        if not token:
            return ""
        payload = decode_token(token)
        return (payload.get("email") or "").strip().lower()
    except HTTPException:
        return ""


def _google_token_has_assessment_scopes(access_token: str) -> bool:
    if not access_token:
        return False
    try:
        token_info = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": access_token},
            timeout=10,
        )
        if token_info.status_code >= 300:
            return False
        scopes = set((token_info.json().get("scope") or "").split())
        return REQUIRED_GOOGLE_ASSESSMENT_SCOPES.issubset(scopes)
    except Exception:
        return False


def _user_from_request_token(request: Request, db) -> User | None:
    try:
        token = bearer_token(request)
        if not token:
            return None
        payload = decode_token(token)
    except HTTPException:
        return None

    user_id = payload.get("user_id") or payload.get("sub")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user

    email = (payload.get("email") or "").strip().lower()
    if email:
        return db.query(User).filter(User.email == email).first()

    return None


def _resolve_recruiter(request: Request, db, recruiter_email: str) -> User | None:
    token_user = _user_from_request_token(request, db)
    if token_user:
        return token_user

    if recruiter_email:
        return db.query(User).filter(User.email == recruiter_email).first()

    return None


def _workflow_status_for_stage(stage: str | None, status: str | None = None) -> str:
    mapping = {
        "applied": "Applied",
        "review": "In Review",
        "recruiter_review": "Recruiter Review",
        "shortlisted": "Shortlisted",
        "communication": "Communication",
        "interview_scheduling": "Interview Scheduling",
        "rejected": "Rejected",
        "dropped": "Dropped",
        "archived": "Archived",
    }
    return status or mapping.get(stage or "", "Review")


def _record_candidate_workflow_event(
    db,
    candidate: Resume,
    *,
    activity_type: str,
    title: str,
    from_stage: str | None = None,
    to_stage: str | None = None,
    body: str | None = None,
    reason: str | None = None,
) -> None:
    """Record legacy workflow actions in the enterprise timeline tables."""
    try:
        db.add(
            CandidateActivity(
                candidate_id=candidate.id,
                job_id=candidate.job_id,
                actor_user_id=None,
                activity_type=activity_type,
                title=title,
                body=body,
            )
        )
        if to_stage and from_stage != to_stage:
            db.add(
                CandidateStageHistory(
                    candidate_id=candidate.id,
                    job_id=candidate.job_id,
                    from_stage=from_stage,
                    to_stage=to_stage,
                    actor_user_id=None,
                    reason=reason or title,
                )
            )
    except Exception:
        logger.exception("Workflow event logging failed")


def _json_loads_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _candidate_projects(candidate: Resume):
    projects = _json_loads_list(candidate.projects)
    if projects:
        return projects

    if candidate.resume_text:
        try:
            parsed = parse_resume_enterprise(candidate.resume_text, ai_parse_override={})
            projects = parsed.get("projects") or []
            if projects:
                candidate.projects = json.dumps(projects, ensure_ascii=False)
                return projects
        except Exception:
            logger.exception("Project extraction fallback failed")

    return []


def _education_label(education):
    labels = []
    seen = set()
    for item in education or []:
        if not isinstance(item, dict):
            continue
        degree = (item.get("degree") or "").strip()
        field = (item.get("field") or "").strip()
        institution = (item.get("institution") or "").strip(" -")
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


def _stored_profile_needs_repair(candidate: Resume):
    text = " ".join([
        str(candidate.full_name or ""),
        str(candidate.last_company_name or ""),
        str(candidate.phone or ""),
        str(candidate.education or ""),
        str(candidate.projects or ""),
        str(candidate.ranking_reason or ""),
    ])
    if not candidate.resume_text:
        return False
    return any([
        bool(re.search(r"\b(19|20)\d{2}\s*(?:-|\u2013|\u2014|to)\s*(19|20)\d{2}\b", str(candidate.phone or ""))),
        (candidate.total_experience_years or 0) <= 0 and re.search(r"\b(VITALITYLIVING|WILES\s*\+\s*TAYLOR|HABERCORPORATION|SESAC)\b", candidate.resume_text, re.I),
        bool(re.search(r"\bWorked on a collaborative team|JUYPTER|JUPYTER|NASHVILLE SOFTWARE SCHOOL WILES|Project evidence contains resume section noise|Experience:\s*0\.0?\s*years\b", text, re.I)),
        bool(re.search(r"\b(Dataanalyticseducation|Data\s+Analyticseducation|DATAANALYTICSEDUCATION|Recent company:\s*NSS\b|last company:\s*NSS\b)\b", text, re.I)),
        bool(re.search(r"\b(?:professional experience|work experience|employment history|experience)\s*:?\s+[A-Z][A-Za-z0-9&.,'() -]{2,}", str(candidate.last_company_name or ""), re.I)),
        bool(re.search(r"\b(PERSONALPROFILE|ABOUT ME|I am a|I enjoy|my wide range|left- and right)\b", str(candidate.projects or ""), re.I)),
        bool(re.search(r"\b(Data Analytics program covering|UNIVERSITY OF FLORIDA|Bachelor of Science|Minors?\s+in)\b", str(candidate.projects or ""), re.I)),
    ])


def _safe_profile_phone(*values):
    for value in values:
        phone = str(value or "").strip()
        if not phone:
            continue
        digits = re.sub(r"\D+", "", phone)
        if not 10 <= len(digits) <= 15:
            continue
        if re.search(r"\b(19|20)\d{2}\s*(?:-|\u2013|\u2014|to)\s*(19|20)\d{2}\b", phone):
            continue
        return phone
    return ""


def _candidate_value_is_polluted(value, kind: str = "text") -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return False
    if kind == "phone":
        digits = re.sub(r"\D+", "", text)
        year_range = bool(re.search(r"\b(19|20)\d{2}\s*(?:-|\u2013|\u2014|to)\s*(19|20)\d{2}\b", text))
        return not 10 <= len(digits) <= 15 or year_range
    if re.search(r"(https?://|www\.|linkedin\.com|github\.com|tableau\s+public|/capstone|/project|profile\s*:)", text, re.I):
        return True
    if kind == "name":
        return len(text.split()) > 5 or bool(re.search(
            r"\b(resume|candidate|profile|summary|objective|education|experience|skills?|projects?|contact|phone|email)\b",
            text,
            re.I,
        ))
    if kind == "location":
        if len(text.split()) > 6:
            return True
        return bool(re.search(
            r"\b(resume|candidate|profile|summary|education|experience|skills?|projects?|contact|email|phone)\b",
            text,
            re.I,
        ))
    if kind == "company":
        if re.search(r"^\s*(experience|work experience|professional experience|employment history)\b", text, re.I):
            return True
        if len(text.split()) > 8:
            return True
        if re.search(r"\b(linkedin|github|tableau\s+public|capstone|python|excel|sql|power\s*bi)\b", text, re.I):
            return True
        return bool(re.search(r"\b(using|created|developed|worked|analy[sz]ed|managed|presented)\b", text, re.I))
    if kind == "education":
        return bool(re.search(
            r"\b(managed|worked|created|developed|improved|delivered|responsible|secured|customers|accounts)\b",
            text,
            re.I,
        ))
    if kind == "project":
        if re.fullmatch(r"(personal|language|supply chain|data analysis|contact website|website)", text, re.I):
            return True
        if re.search(r"\b(?:cid:\d+|achievements?|designation|location|manpower strength)\b", text, re.I):
            return True
        if re.search(r"\b(UNIVERSITY OF|Bachelor of Science|Minors?\s+in|Data Analytics program covering|LANGUAGE:|SUPPLY CHAIN:)\b", text, re.I):
            return True
        analytics_evidence = bool(re.search(
            r"\b(python|sql|tableau|power\s*bi|excel|dashboard|data|cleaned|analy[sz]ed|database)\b",
            text,
            re.I,
        ))
        job_bullet = bool(re.search(
            r"\b(met with customers|customers|service|taught incoming employees|employees|install(?:ed)?|"
            r"equipment|tires?|worked remotely|zoom|slack|secured|responsible|managed|delivered|"
            r"created|developed|worked|presented)\b",
            text,
            re.I,
        ))
        section_noise = bool(re.search(
            r"(?:^|\n)\s*(work experience|professional experience|education|technical skills|technical tools|summary|profile)\s*:?\s*(?:\n|$)",
            str(value or ""),
            re.I,
        ))
        skill_items = [item for item in re.split(r"[,|;/]+", text) if item.strip()]
        return section_noise or (len(skill_items) >= 8 and not analytics_evidence) or (job_bullet and not analytics_evidence)
    return False


def _trim_project_evidence_noise(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    markers = [
        r"\bData Analytics program covering\b",
        r"\bPERSONAL\s*PROFILE\b",
        r"\bPERSONALPROFILE\b",
        r"\bI have always been motivated\b",
        r"\bUNIVERSITY OF\b",
        r"\bBachelor of Science\b",
        r"\bMinors?\s+in\b",
        r"\bLANGUAGE:\b",
        r"\bSUPPLY CHAIN:\b",
        r"\bPERSONAL:\b",
    ]
    for marker in markers:
        match = re.search(marker, text, re.I)
        if match and match.start() > 25:
            text = text[:match.start()].strip(" .,\n")
            break
    return text


def _safe_candidate_projects(projects):
    safe_projects = []
    for project in projects or []:
        if isinstance(project, str):
            body = project
            name = project[:90]
            description = _trim_project_evidence_noise(project)
            technologies = []
        elif isinstance(project, dict):
            name = re.sub(r"\s+", " ", str(project.get("name") or "").strip())
            description = _trim_project_evidence_noise(str(project.get("description") or "").strip())
            body = " ".join(part for part in [name, description] if part)
            technologies = project.get("technologies") if isinstance(project.get("technologies"), list) else []
        else:
            continue

        if not body or _candidate_value_is_polluted(body, "project"):
            continue
        safe_projects.append({
            "name": name or "Project evidence",
            "description": description or name,
            "technologies": technologies,
        })

    return safe_projects


def _safe_education_display(value):
    raw_items = [
        item.strip()
        for item in re.split(r"\s*,\s*|\n+", str(value or ""))
        if item.strip()
    ]
    safe_items = [item for item in raw_items if not _candidate_value_is_polluted(item, "education")]
    return ", ".join(safe_items)


def _candidate_experience_meta(candidate: Resume):
    meta = {}
    try:
        payload = json.loads(
            getattr(candidate, "ai_confidence_reason", None)
            or getattr(candidate, "explanation", None)
            or "{}"
        )
        if isinstance(payload, dict) and isinstance(payload.get("experience_summary"), dict):
            meta = dict(payload.get("experience_summary") or {})
    except (TypeError, ValueError, json.JSONDecodeError):
        meta = {}

    total = candidate.total_experience_years
    if total is not None and meta.get("total_years") is None:
        meta["total_years"] = total
    if getattr(candidate, "relevant_experience_years", None) is not None:
        meta["relevant_years"] = candidate.relevant_experience_years
    if getattr(candidate, "direct_relevant_experience_years", None) is not None:
        meta["direct_relevant_years"] = candidate.direct_relevant_experience_years
    if getattr(candidate, "transferable_experience_years", None) is not None:
        meta["transferable_years"] = candidate.transferable_experience_years
        meta["transferable_reporting_years"] = candidate.transferable_experience_years
    if getattr(candidate, "experience_relevance_label", None):
        meta["label"] = candidate.experience_relevance_label
    return meta


def _format_candidate_experience(meta):
    def _num(value):
        try:
            number = float(value)
            return number if number >= 0 else None
        except (TypeError, ValueError):
            return None

    total = _num(meta.get("total_years"))
    relevant = _num(meta.get("relevant_years"))
    direct = _num(meta.get("direct_relevant_years"))
    transition = bool(meta.get("transition_candidate")) or meta.get("label") == "transferable_reporting"

    if relevant is not None and (transition or (total is not None and abs(total - relevant) > 0.25)):
        label = f"{relevant:g} years JD-related"
        if total is not None:
            label += f" ({total:g} total)"
        if direct == 0:
            label += "; direct DA not proven"
        return label
    if total is not None:
        return f"{total:g} years"
    return "Needs validation"


def _candidate_safe_display(candidate: Resume):
    raw_projects = _candidate_projects(candidate)
    projects = _safe_candidate_projects(raw_projects)
    project_labels = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        label = re.sub(r"\s+", " ", str(project.get("name") or project.get("description") or "").strip())
        body = " ".join(str(project.get(key) or "") for key in ("name", "description"))
        if label and not _candidate_value_is_polluted(body, "project"):
            project_labels.append(label[:120])

    name = re.sub(r"\s+", " ", str(getattr(candidate, "full_name", None) or getattr(candidate, "form_full_name", None) or "").strip())
    email = re.sub(r"\s+", " ", str(getattr(candidate, "email", None) or getattr(candidate, "form_email", None) or "").strip())
    location = re.sub(r"\s+", " ", str(getattr(candidate, "location", None) or getattr(candidate, "form_location", None) or "").strip())
    phone = _safe_profile_phone(candidate.phone, candidate.form_phone)
    company = re.sub(r"\s+", " ", str(candidate.last_company_name or "").strip())
    education = re.sub(r"\s+", " ", str(candidate.education or "").strip())
    flags = []
    confidence = {
        "name": 0.9,
        "email": 0.9,
        "phone": 0.95 if phone else 0.2,
        "location": 0.8,
        "last_company": 0.85,
        "education": 0.85,
        "project_evidence": 0.85 if project_labels else 0.45,
    }

    if not name or _candidate_value_is_polluted(name, "name"):
        name = ""
        confidence["name"] = 0.25
        flags.append("name_needs_review")
    if not email or not re.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", email):
        email = ""
        confidence["email"] = 0.25
        flags.append("email_needs_review")
    if _candidate_value_is_polluted(candidate.phone, "phone") or not phone:
        flags.append("phone_needs_review")
    if not location or location in {"-", "N/A", "NA"} or _candidate_value_is_polluted(location, "location"):
        location = ""
        confidence["location"] = 0.35
        flags.append("location_needs_review")
    if not company or _candidate_value_is_polluted(company, "company"):
        company = ""
        confidence["last_company"] = 0.3
        flags.append("company_needs_review")
    safe_education = _safe_education_display(education)
    if not education or not safe_education:
        education = ""
        confidence["education"] = 0.35
        flags.append("education_needs_review")
    if not project_labels:
        flags.append("project_noise_detected")
    if any(value < 0.5 for value in confidence.values()):
        flags.append("profile_needs_review")

    experience_label = _format_candidate_experience(_candidate_experience_meta(candidate))
    return {
        "safe_display": {
            "name": name or "Needs manual review",
            "email": email or "Needs manual review",
            "phone": phone or "Needs validation",
            "location": location or "Needs manual review",
            "last_company": company or "Needs validation",
            "education": safe_education or "Needs validation",
            "project_evidence": ", ".join(project_labels[:3]) or "Needs manual review",
            "experience": experience_label,
        },
        "projects": projects,
        "field_confidence": confidence,
        "parser_flags": sorted(set(flags)),
        "profile_extraction_quality": "Needs review" if flags else "Clean",
    }


def _repair_stored_candidate_profile(candidate: Resume, job: Job, force: bool = False):
    if not force and not _stored_profile_needs_repair(candidate):
        return False
    try:
        resume_file = _candidate_resume_file(candidate)
        fresh_text = ""
        if resume_file:
            fresh_text = (
                extract_text_from_pdf(str(resume_file))
                if str(resume_file).lower().endswith(".pdf")
                else extract_text_from_docx(str(resume_file))
                if str(resume_file).lower().endswith(".docx")
                else ""
            )
        if force and fresh_text:
            candidate.resume_text = fresh_text[:12000]
        elif not candidate.resume_text and fresh_text:
            candidate.resume_text = fresh_text[:12000]
        if not candidate.resume_text:
            return False

        jd_skills = normalize_jd_skills(job.required_skills or "", job.jd_text or "")
        min_years, max_years = _parse_experience_range(job.experience_required)
        jd_data = {
            "min_experience_years": job.min_experience_years if job.min_experience_years is not None else min_years,
            "max_experience_years": max_years,
            "education": job.education,
            "role": job.role or job.job_title or "",
            "preferred_skills": job.preferred_skills or "",
        }
        parsed, exp_data, score_data = analyze_resume_for_job(
            candidate.resume_text[:12000],
            job.jd_text or "",
            jd_skills,
            jd_data,
        )

        candidate.full_name = parsed.get("full_name") or candidate.form_full_name or candidate.full_name
        candidate.email = (parsed.get("email") or candidate.form_email or candidate.email or "").strip().lower()
        candidate.phone = _safe_profile_phone(parsed.get("phone"), candidate.form_phone)
        candidate.location = parsed.get("location") or candidate.form_location or candidate.location
        candidate.key_skills = ", ".join(parsed.get("key_skills", [])) if parsed.get("key_skills") else candidate.key_skills
        cleaned_projects = _safe_candidate_projects(parsed.get("projects") or [])
        candidate.projects = json.dumps(cleaned_projects or parsed.get("projects") or [], ensure_ascii=False)
        candidate.designation = parsed.get("designation") or candidate.designation
        candidate.total_experience_years = parsed.get("total_experience_years")
        candidate.last_company_name = exp_data.get("last_company_name")
        candidate.last_working_date = exp_data.get("last_working_date")
        candidate.education = _education_label(parsed.get("education") or [])
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
        candidate.ai_confidence_reason = json.dumps(generate_recruiter_explanation(parsed, jd_data, score_data), ensure_ascii=False)
        candidate.explanation = candidate.ai_confidence_reason
        candidate.matched_skills = ",".join(parsed.get("matched_skills", []))
        candidate.missing_skills = ",".join(parsed.get("missing_skills", []))
        candidate.skill_match_percent = parsed.get("skill_match_percent")
        apply_resume_intelligence_fields(candidate, parsed)
        return True
    except Exception:
        logger.exception("Stored candidate profile repair failed for %s", candidate.id)
        return False


def _candidate_result_payload(candidate: Resume, job: Job, note_map=None, tag_map=None):
    resume_file = _candidate_resume_file(candidate)
    trust = _candidate_recruiter_trust(candidate, job)
    notes = sorted((note_map or {}).get(candidate.id, []), key=lambda note: note.created_at or datetime.min, reverse=True)
    tags = (tag_map or {}).get(candidate.id, [])
    safe_meta = _candidate_safe_display(candidate)
    experience_meta = _candidate_experience_meta(candidate)
    payload = {
        "resume_id": candidate.id,
        "id": candidate.id,
        "job_id": candidate.job_id,
        "full_name": candidate.full_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "key_skills": candidate.key_skills,
        "projects": safe_meta["projects"],
        "raw_projects": _candidate_projects(candidate),
        "designation": candidate.designation,
        "industry": candidate.industry,
        "domain": candidate.domain,
        "total_experience_years": candidate.total_experience_years,
        "relevant_experience_years": experience_meta.get("relevant_years"),
        "direct_relevant_experience_years": experience_meta.get("direct_relevant_years"),
        "transferable_reporting_experience_years": experience_meta.get("transferable_reporting_years"),
        "experience_relevance_label": experience_meta.get("label"),
        "transition_candidate": bool(experience_meta.get("transition_candidate")),
        "last_company_name": candidate.last_company_name,
        "last_working_date": candidate.last_working_date,
        "education": candidate.education,
        "final_score": candidate.final_score,
        "rank_score": candidate.rank_score,
        "fit_band": candidate.fit_band,
        "skill_score": candidate.skill_score,
        "matched_skills": candidate.matched_skills,
        "missing_skills": candidate.missing_skills,
        "skill_match_percent": candidate.skill_match_percent,
        "experience_score": candidate.experience_score,
        "confidence_score": candidate.confidence_score,
        "resume_quality_score": candidate.resume_quality_score,
        "ai_recommendation": candidate.ai_recommendation,
        "ranking_reason": candidate.ranking_reason,
        "recruiter_trust": trust,
        "client_summary": trust["client_summary"],
        "risk_points": trust["risk_points"],
        "evidence_points": trust["evidence_points"],
        "note_count": len(notes),
        "latest_note": notes[0].body if notes else "",
        "tags": [{"tag": tag.tag, "color": tag.color} for tag in tags],
        "explanation": candidate.explanation,
        "resume_available": bool(resume_file),
        "resume_original_filename": candidate.resume_original_filename,
        "resume_content_type": candidate.resume_content_type,
        "application_source": candidate.application_source or "direct",
        "apply_tracking_url": candidate.apply_tracking_url,
        "status": candidate.status,
        "stage": candidate.stage,
        "mail_status": candidate.mail_status,
        "response_status": candidate.response_status,
        "safe_display": safe_meta["safe_display"],
        "field_confidence": safe_meta["field_confidence"],
        "parser_flags": safe_meta["parser_flags"],
        "profile_extraction_quality": safe_meta["profile_extraction_quality"],
    }
    payload.update(resume_intelligence_payload(candidate))
    return payload


def _split_skill_text(value):
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[,;\n|]+", str(value))
    seen = set()
    items = []
    for item in raw_items:
        skill = str(item).strip()
        key = skill.lower()
        if skill and key not in seen:
            seen.add(key)
            items.append(skill)
    return items


def _parse_experience_range(value):
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", str(value or ""))]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        return numbers[0], 0
    return 0, 0


def _manual_project_records(value):
    if not value:
        return []
    if isinstance(value, list):
        records = []
        for item in value:
            if isinstance(item, dict):
                name = sanitize_text(str(item.get("name") or item.get("title") or "")).strip()
                description = sanitize_text(str(item.get("description") or item.get("summary") or "")).strip()
                technologies = _split_skill_text(item.get("technologies") or item.get("tools") or "")
                if name or description:
                    records.append({
                        "name": name or description[:80],
                        "description": description or name,
                        "technologies": technologies,
                    })
            else:
                text = sanitize_text(str(item)).strip()
                if text:
                    records.append({"name": text[:80], "description": text, "technologies": []})
        return records[:12]

    text = sanitize_text(str(value))
    lines = [line.strip(" -\t") for line in re.split(r"[\r\n]+", text) if line.strip(" -\t")]
    if not lines and text.strip():
        lines = [text.strip()]
    return [{"name": line[:80], "description": line, "technologies": []} for line in lines[:12]]


def _projects_text(projects):
    lines = []
    for project in projects or []:
        if not isinstance(project, dict):
            continue
        technologies = project.get("technologies") or []
        if isinstance(technologies, list):
            technologies = ", ".join(str(item) for item in technologies)
        lines.append(" ".join(str(project.get(key) or "") for key in ("name", "description")) + " " + str(technologies or ""))
    return "\n".join(lines)


def _rescore_candidate_from_stored_fields(candidate: Resume, job: Job):
    min_years, max_years = _parse_experience_range(job.experience_required)
    jd_data = {
        "min_experience_years": job.min_experience_years if job.min_experience_years is not None else min_years,
        "max_experience_years": max_years,
        "education": job.education,
        "role": job.role or job.job_title or "",
        "preferred_skills": job.preferred_skills or "",
    }
    projects = _candidate_projects(candidate)
    parsed = {
        "full_name": candidate.full_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "designation": candidate.designation,
        "key_skills": _split_skill_text(candidate.key_skills),
        "projects": projects,
        "education": [{"degree": candidate.education or "", "field": "", "institution": ""}] if candidate.education else [],
        "total_experience_years": candidate.total_experience_years or 0,
        "experience": [{
            "company_name": candidate.last_company_name or "",
            "role": candidate.designation or "",
            "description": candidate.ranking_reason or "",
        }],
        "resume_quality_score": candidate.resume_quality_score or 70,
        "domain": candidate.domain,
    }
    review_text = "\n".join([
        candidate.resume_text or "",
        candidate.full_name or "",
        candidate.designation or "",
        candidate.key_skills or "",
        candidate.education or "",
        candidate.last_company_name or "",
        _projects_text(projects),
    ])
    parsed["semantic_score"] = cosine_similarity_cached(job.jd_text or "", review_text)
    parsed["role_similarity"] = cosine_similarity_cached(jd_data["role"], candidate.designation or "") if jd_data["role"] and candidate.designation else 0
    jd_skills = normalize_jd_skills(job.required_skills or "", job.jd_text or "")
    jd_profile = build_jd_profile(job.jd_text or "", jd_data, jd_skills)
    parsed.update(estimate_relevant_experience_v2(parsed, review_text, jd_profile))
    parsed["role_family"] = jd_profile.get("role_family")
    parsed["role_family_confidence"] = jd_profile.get("role_family_confidence")
    parsed["jd_profile_json"] = jd_profile
    score_data = score_candidate(
        parsed,
        job.jd_text or "",
        jd_profile.get("must_have_skills") or jd_skills,
        jd_data,
        review_text,
        jd_profile=jd_profile,
    )
    parsed.update(score_data)

    candidate.final_score = parsed.get("final_score")
    candidate.rank_score = parsed.get("rank_score")
    candidate.fit_band = parsed.get("fit_band")
    candidate.skill_score = parsed.get("skill_score")
    candidate.experience_score = parsed.get("experience_score")
    candidate.confidence_score = parsed.get("confidence_score")
    candidate.resume_quality_score = parsed.get("resume_quality_score")
    candidate.ai_recommendation = parsed.get("recommendation")
    candidate.ranking_reason = parsed.get("ranking_reason")
    candidate.ai_confidence_reason = json.dumps(generate_recruiter_explanation(parsed, jd_data, score_data), ensure_ascii=False)
    candidate.explanation = candidate.ai_confidence_reason
    candidate.matched_skills = ",".join(parsed.get("matched_skills", []))
    candidate.missing_skills = ",".join(parsed.get("missing_skills", []))
    candidate.skill_match_percent = parsed.get("skill_match_percent")
    apply_resume_intelligence_fields(candidate, parsed)
    return score_data


def _score_band(score):
    score = float(score or 0)
    if score >= 80:
        return "Strong client-ready match"
    if score >= 65:
        return "Good recruiter-review match"
    if score >= 50:
        return "Borderline, validate gaps"
    return "Low match, keep as backup"


def _candidate_recruiter_trust(candidate: Resume, job: Job | None = None):
    matched = _split_skill_text(candidate.matched_skills or candidate.key_skills)
    missing = _split_skill_text(candidate.missing_skills)
    required = _split_skill_text(job.required_skills if job else "")
    preferred = _split_skill_text(job.preferred_skills if job else "")
    score = candidate.rank_score if candidate.rank_score is not None else candidate.final_score
    skill_match = candidate.skill_match_percent or 0
    confidence = candidate.confidence_score or 0
    experience_meta = _candidate_experience_meta(candidate)
    experience_label = _format_candidate_experience(experience_meta)

    evidence = []
    if matched:
        evidence.append(f"Matched skills: {', '.join(matched[:8])}.")
    if experience_label != "Needs validation":
        evidence.append(f"JD-related experience: {experience_label}.")
    if candidate.last_company_name:
        evidence.append(f"Recent company: {candidate.last_company_name}.")
    if candidate.designation:
        evidence.append(f"Current/target role signal: {candidate.designation}.")
    if candidate.ranking_reason:
        evidence.append(candidate.ranking_reason)

    risk_points = []
    if missing:
        risk_points.append(f"Missing or weak skills: {', '.join(missing[:8])}.")
    if required and skill_match < 60:
        risk_points.append("Mandatory skill coverage needs manual validation.")
    if confidence and confidence < 55:
        risk_points.append("AI confidence is moderate/low, review resume evidence before client submission.")
    if not candidate.email and not candidate.form_email:
        risk_points.append("Candidate email is missing.")

    recommendation = "send_to_client" if (score or 0) >= 75 and not risk_points[:1] else "recruiter_review"
    if (score or 0) < 50:
        recommendation = "backup_only"

    return {
        "rank_score": score or 0,
        "fit_band": candidate.fit_band or _score_band(score),
        "score_band": _score_band(score),
        "skill_match_percent": skill_match,
        "confidence_score": confidence,
        "matched_skills": matched[:12],
        "missing_skills": missing[:12],
        "required_skills": required[:20],
        "preferred_skills": preferred[:20],
        "experience_summary": experience_meta,
        "evidence_points": evidence[:6],
        "risk_points": risk_points[:5],
        "recruiter_recommendation": recommendation,
        "client_summary": _client_candidate_summary(candidate, matched, missing, score),
    }


def _client_candidate_summary(candidate: Resume, matched: list[str], missing: list[str], score):
    name = candidate.full_name or candidate.form_full_name or "Candidate"
    role = candidate.designation or "candidate"
    exp_text = ""
    experience_label = _format_candidate_experience(_candidate_experience_meta(candidate))
    if experience_label != "Needs validation":
        exp_text = f" with {experience_label}"
    match_text = f" Key matching skills include {', '.join(matched[:5])}." if matched else ""
    gap_text = f" Validate gaps around {', '.join(missing[:3])}." if missing else ""
    return f"{name} is a {role}{exp_text} with a recruiter score of {round(float(score or 0), 1)}.{match_text}{gap_text}"


def _candidate_notes_and_tags(db, candidate_ids):
    if not candidate_ids:
        return {}, {}
    notes = db.query(CandidateNote).filter(CandidateNote.candidate_id.in_(candidate_ids)).all()
    tags = db.query(CandidateTag).filter(CandidateTag.candidate_id.in_(candidate_ids)).all()
    note_map = {}
    tag_map = {}
    for note in notes:
        note_map.setdefault(note.candidate_id, []).append(note)
    for tag in tags:
        tag_map.setdefault(tag.candidate_id, []).append(tag)
    return note_map, tag_map


def _shortlist_candidate_payload(candidate: Resume, job: Job | None, note_map: dict, tag_map: dict):
    trust = _candidate_recruiter_trust(candidate, job)
    notes = sorted(note_map.get(candidate.id, []), key=lambda note: note.created_at or datetime.min, reverse=True)
    tags = tag_map.get(candidate.id, [])
    return {
        "id": candidate.id,
        "job_id": candidate.job_id,
        "name": candidate.full_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "designation": candidate.designation,
        "experience": candidate.total_experience_years,
        "last_company": candidate.last_company_name,
        "last_working_date": candidate.last_working_date,
        "matched_skills": candidate.matched_skills,
        "missing_skills": candidate.missing_skills,
        "skill_match_percent": candidate.skill_match_percent,
        "industry": candidate.industry,
        "domain": candidate.domain,
        "education": candidate.education,
        "score": candidate.final_score,
        "rank_score": candidate.rank_score,
        "fit_band": candidate.fit_band,
        "confidence_score": candidate.confidence_score,
        "resume_quality_score": candidate.resume_quality_score,
        "ai_recommendation": candidate.ai_recommendation,
        "ranking_reason": candidate.ranking_reason,
        "recruiter_trust": trust,
        "client_summary": trust["client_summary"],
        "risk_points": trust["risk_points"],
        "evidence_points": trust["evidence_points"],
        "note_count": len(notes),
        "latest_note": notes[0].body if notes else "",
        "tags": [{"tag": tag.tag, "color": tag.color} for tag in tags],
        "status": candidate.status,
    }


def _load_local_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _safe_upload_file(path: Path, upload_root: Path):
    try:
        resolved = path.resolve()
        root = upload_root.resolve()
    except Exception:
        return None

    if root in resolved.parents or resolved == root:
        return resolved if resolved.exists() and resolved.is_file() else None

    return None


def _resume_public_filename(file_path: Path):
    filename = file_path.name
    return re.sub(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}_",
        "",
        filename,
    )


def _resume_match_token(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _resume_file_score(candidate: Resume, file_path: Path):
    file_token = _resume_match_token(file_path.stem)
    score = 0

    name = _resume_match_token(candidate.full_name)
    if name and name in file_token:
        score += 80

    for token in re.findall(r"[a-z0-9]+", (candidate.full_name or "").lower()):
        if len(token) >= 3 and token in file_token:
            score += 18

    email_user = _resume_match_token((candidate.email or "").split("@")[0])
    if len(email_user) >= 4 and email_user in file_token:
        score += 70

    phone = re.sub(r"\D+", "", candidate.phone or "")
    if len(phone) >= 6 and phone in file_token:
        score += 60

    return score


def _candidate_resume_file(candidate: Resume):
    settings = get_settings()
    upload_root = Path(settings.upload_dir).resolve()

    stored_path = getattr(candidate, "resume_file_path", None)
    if stored_path:
        safe_file = _safe_upload_file(Path(stored_path), upload_root)
        if safe_file:
            return safe_file

    allowed_suffixes = {".pdf", ".doc", ".docx", ".rtf", ".txt"}
    matches = []

    for file_path in upload_root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in allowed_suffixes:
            continue
        score = _resume_file_score(candidate, file_path)
        if score > 0:
            matches.append((score, file_path.stat().st_mtime, file_path))

    if not matches:
        return None

    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    matched_file = _safe_upload_file(matches[0][2], upload_root)

    if matched_file:
        candidate.resume_file_path = str(matched_file)
        candidate.resume_original_filename = _resume_public_filename(matched_file)
        candidate.resume_content_type = mimetypes.guess_type(str(matched_file))[0] or "application/octet-stream"

    return matched_file


_load_local_env()


# ---------------- REQUEST MODEL ----------------

class JobCreate(BaseModel):

    job_title: str
    company_name: str
    department: str | None = None
    location: str
    work_mode: str | None = None
    job_type: str
    salary_range: str
    experience_required: str | None = None
    application_deadline: str | None = None
    hiring_manager: str | None = None
    jd_text: str
    shortlist_score: int = 70
    public_apply_enabled: bool = True
    source_tracking_enabled: bool = True


class ShortlistFilterRequest(BaseModel):
    job_id: str
    min_score: float | None = None


class JDTextParseRequest(BaseModel):
    jd_text: str


class ResumeFolderRequest(BaseModel):
    folder_path: str


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text or "", flags=re.I)
    return match.group(1).strip(" :-\n\t") if match else ""


def _infer_work_mode(text: str) -> str:
    value = text or ""
    if re.search(r"\bremote\b|work\s+from\s+home|\bwfh\b", value, re.I):
        return "Remote"
    if re.search(r"\bhybrid\b", value, re.I):
        return "Hybrid"
    if re.search(r"\bonsite\b|on-site|work\s+from\s+office|\bwfo\b", value, re.I):
        return "Onsite"
    return ""


def _infer_job_type(text: str) -> str:
    value = text or ""
    if re.search(r"\bintern(ship)?\b", value, re.I):
        return "Internship"
    if re.search(r"\bcontract\b|consultant", value, re.I):
        return "Contract"
    if re.search(r"\bpart[-\s]?time\b", value, re.I):
        return "Part Time"
    if re.search(r"\bfull[-\s]?time\b|permanent", value, re.I):
        return "Full Time"
    return ""


def _infer_salary(text: str) -> str:
    return _first_match(
        r"(?:salary|ctc|compensation|package)\s*[:\-]?\s*([^\n\r]{2,80})",
        text,
    )


def _infer_department(role: str, text: str) -> str:
    explicit = _first_match(r"(?:department|function|team)\s*[:\-]?\s*([^\n\r]{2,60})", text)
    if explicit:
        return explicit
    value = f"{role} {text}".lower()
    if any(token in value for token in ["developer", "engineer", "python", "java", "react", "backend", "frontend"]):
        return "Engineering"
    if any(token in value for token in ["analyst", "analytics", "data", "power bi", "sql"]):
        return "Analytics"
    if any(token in value for token in ["recruiter", "hr", "human resource", "talent acquisition"]):
        return "Human Resources"
    if any(token in value for token in ["sales", "business development"]):
        return "Sales"
    return ""


def _parse_jd_upload_text(filename: str, contents: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(status_code=400, detail="Upload a PDF, DOCX, or TXT job description.")

    if suffix == ".txt":
        return normalize_extracted_text(contents.decode("utf-8", errors="ignore"))

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(contents)
        temp_path = temp_file.name

    try:
        if suffix == ".pdf":
            return extract_text_from_pdf(temp_path)
        return extract_text_from_docx(temp_path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _jd_autofill_payload(jd_text: str) -> dict:
    structured = extract_structured_jd(jd_text)
    role = structured.get("role") or _first_match(r"(?:job\s*title|role|position)\s*[:\-]?\s*([^\n\r]{2,80})", jd_text)
    location = structured.get("location") or _first_match(r"(?:location|job\s*location)\s*[:\-]?\s*([^\n\r]{2,80})", jd_text)
    experience_years = structured.get("min_experience_years") or 0
    explicit_experience = _first_match(
        r"(?:experience|exp)\s*[:\-]?\s*([^\n\r]{2,60})",
        jd_text,
    )
    experience_required = explicit_experience or (f"{experience_years}+ Years" if experience_years else "")

    return {
        "job_title": role,
        "department": _infer_department(role, jd_text),
        "location": location,
        "work_mode": _infer_work_mode(jd_text),
        "job_type": _infer_job_type(jd_text),
        "salary_range": _infer_salary(jd_text),
        "experience_required": experience_required,
        "required_skills": ", ".join(structured.get("required_skills") or []),
    }


@router.post("/parse-jd-text", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def parse_jd_text(data: JDTextParseRequest):
    jd_text = normalize_extracted_text(data.jd_text or "")
    if len(jd_text.split()) < 8:
        raise HTTPException(status_code=400, detail="Paste a longer job description to autofill fields.")

    return {
        "fields": _jd_autofill_payload(jd_text),
    }


@router.post("/parse-jd-file", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
async def parse_jd_file(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded JD file is empty.")
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="JD file must be 8MB or smaller.")

    jd_text = _parse_jd_upload_text(file.filename or "", contents)
    if not jd_text or len(jd_text.split()) < 8:
        raise HTTPException(status_code=422, detail="Could not extract readable job description text from this file.")

    return {
        "jd_text": jd_text,
        "fields": _jd_autofill_payload(jd_text),
    }


# ---------------- CREATE JOB ----------------

@router.post("/create-job", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def create_job(job: JobCreate):

    db = SessionLocal()

    try:
        structured_jd = extract_structured_jd(job.jd_text)

        edu = structured_jd.get("education")
        if isinstance(edu, list):
            edu = ",".join(edu)

        new_job = Job(

            job_title=job.job_title,
            company_name=job.company_name,

            department=job.department,
            location=job.location,
            work_mode=job.work_mode,

            job_type=job.job_type,
            salary_range=job.salary_range,

            experience_required=job.experience_required,
            application_deadline=job.application_deadline,
            hiring_manager=job.hiring_manager,

            jd_text=job.jd_text,

            shortlist_score=job.shortlist_score,
            public_apply_enabled=job.public_apply_enabled,
            source_tracking_enabled=job.source_tracking_enabled,

            role=structured_jd.get("role"),
            required_skills=",".join(structured_jd.get("required_skills", [])),
            preferred_skills=",".join(structured_jd.get("preferred_skills", [])),
            min_experience_years=structured_jd.get("min_experience_years"),
            education=edu
        )

        db.add(new_job)
        db.flush()
        links = ensure_generated_sourcing_content(new_job, db)
        db.commit()
        db.refresh(new_job)

        payload = sourcing_payload(new_job)
        return {
            "job_id": new_job.id,
            "apply_link": links["main"],
            **payload,
        }
    finally:
        db.close()


# ---------------- APPLY PAGE (FOR CANDIDATES) ----------------

@router.get("/apply/{job_identifier}", response_class=HTMLResponse)
def apply_page(job_identifier: str, source: str | None = Query(default=None)):

    db = SessionLocal()

    try:
        job = resolve_job_identifier(job_identifier, db, active_only=True)
        if not job:
            return "<h2>Job not found</h2>"
        if job.public_apply_enabled is False:
            return "<h2>This public apply page is not enabled for this job.</h2>"

        if not getattr(job, "apply_slug", None):
            ensure_apply_slug(job, db)
            db.commit()
            db.refresh(job)

        safe_source = normalize_application_source(source)
        query = urlencode({"job_id": job.apply_slug or job.id, "source": safe_source})
        return RedirectResponse(url=f"/frontend/apply.html?{query}", status_code=302)
    finally:
        db.close()


# ---------------- PUBLIC JOB (JSON API) ----------------

@router.get("/public-job/{job_identifier}")
def public_job(job_identifier: str):

    db = SessionLocal()

    job = resolve_job_identifier(job_identifier, db, active_only=True)

    if not job:
        db.close()
        return {"error": "Job not found"}
    if job.public_apply_enabled is False:
        db.close()
        return {"error": "Public apply page is not enabled for this job"}
    ensure_apply_slug(job, db)
    if not job.generated_linkedin_post or not job.generated_whatsapp_message or not job.generated_naukri_text:
        ensure_generated_sourcing_content(job, db)
    db.commit()

    jd_fields = _jd_autofill_payload(job.jd_text or "")

    data = {
        "job_id": job.id,
        "job_title": job.job_title or jd_fields.get("job_title"),
        "company": job.company_name,
        "department": job.department or jd_fields.get("department"),
        "location": jd_fields.get("location") or job.location,
        "work_mode": jd_fields.get("work_mode") or job.work_mode,
        "salary": job.salary_range or jd_fields.get("salary_range"),
        "job_type": jd_fields.get("job_type") or job.job_type,
        "experience_required": jd_fields.get("experience_required") or job.experience_required,
        "application_deadline": job.application_deadline,
        "hiring_manager": job.hiring_manager,
        "description": job.jd_text,
        "public_apply_enabled": job.public_apply_enabled if job.public_apply_enabled is not None else True,
        "source_tracking_enabled": job.source_tracking_enabled if job.source_tracking_enabled is not None else True,
        **sourcing_payload(job)
    }

    db.close()

    return data


@router.post("/jobs/{job_id}/ai-posts", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def generate_job_ai_posts(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        ensure_apply_slug(job, db)
        payload = generate_ai_sourcing_posts(job, db)
        posts = payload.get("generated_posts") or {}

        job.generated_linkedin_post = posts.get("linkedin") or job.generated_linkedin_post
        job.generated_whatsapp_message = posts.get("whatsapp") or job.generated_whatsapp_message
        job.generated_naukri_text = posts.get("naukri") or job.generated_naukri_text
        db.commit()
        db.refresh(job)

        return {
            "job_id": job.id,
            "generated": bool(payload.get("generated")),
            "apply_links": payload.get("apply_links") or build_apply_links(job, db),
            "generated_posts": {
                "linkedin": job.generated_linkedin_post,
                "whatsapp": job.generated_whatsapp_message,
                "naukri": job.generated_naukri_text,
                "generic": posts.get("generic") or "",
            },
        }
    finally:
        db.close()


# ---------------- GET RESULTS ----------------

@router.get("/results/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_results(job_id: str):

    db = SessionLocal()

    try:
        job = db.query(Job).filter(Job.id == job_id).first()

        if not job:
            return {"error": "Job not found"}

        # 🔥 FETCH RESUMES
        resumes = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.is_active == True
        ).all()

        # 🔥 REMOVE DUPLICATES (BEST LOGIC)

        unique = {}

        for r in resumes:
            _repair_stored_candidate_profile(r, job)

            key = (
                r.email.strip().lower() if r.email else None,
                r.phone.strip() if r.phone else None
            )
            if key == (None, None):
                key = (r.id, None)

            def result_priority(row):
                status_priority = {
                    "Interview Scheduling": 60,
                    "Communication": 50,
                    "Shortlisted": 40,
                    "Review": 20,
                    "Rejected": 10,
                    "Dropped": 0,
                }
                workflow_signal = (5 if row.mail_status else 0) + (5 if row.response_status else 0)
                return (status_priority.get(row.status or "", 0), workflow_signal, row.final_score or 0)

            if key not in unique or result_priority(r) > result_priority(unique[key]):
                unique[key] = r

        resumes = list(unique.values())

        # 🔥 BUILD RESULT LIST
        result_list = []
        note_map, tag_map = _candidate_notes_and_tags(db, [r.id for r in resumes])

        for r in resumes:
            candidate_notes = sorted(note_map.get(r.id, []), key=lambda note: note.created_at or datetime.min, reverse=True)
            candidate_tags = tag_map.get(r.id, [])
            result_list.append(_candidate_result_payload(r, job, {r.id: candidate_notes}, {r.id: candidate_tags}))

        db.commit()

        # 🔥 SORT
        sorted_resumes = sorted(
            result_list,
            key=lambda x: (
                x.get("final_score") or x.get("rank_score") or 0,
                x.get("confidence_score") or 0,
                x.get("skill_match_percent") or 0,
            ),
            reverse=True
        )

        # 🔥 RANK + TOP FLAG
        TOP_N = 10

        for i, resume in enumerate(sorted_resumes):
            resume["rank"] = i + 1
            recruiter_score = resume.get("final_score") or resume.get("rank_score") or 0
            resume["top_candidate"] = i < TOP_N and recruiter_score >= 55

        db.commit()

        return {
            "job_id": job_id,
            "results": sorted_resumes
        }

    finally:
        db.close()


@router.post("/candidate-reparse/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def reparse_candidate_profile(resume_id: str):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        job = db.query(Job).filter(Job.id == candidate.job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        changed = _repair_stored_candidate_profile(candidate, job, force=True)
        if not changed:
            raise HTTPException(status_code=422, detail="Could not re-parse this candidate. Resume text or file is missing.")

        db.commit()
        db.refresh(candidate)
        note_map, tag_map = _candidate_notes_and_tags(db, [candidate.id])
        return {
            "message": "Candidate profile re-parsed",
            "candidate": _candidate_result_payload(candidate, job, note_map, tag_map),
        }
    finally:
        db.close()


@router.post("/candidate-update/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def update_candidate_profile(resume_id: str, data: dict = Body(...)):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id, Resume.is_active == True).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        job = db.query(Job).filter(Job.id == candidate.job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        text_fields = {
            "full_name": "full_name",
            "email": "email",
            "phone": "phone",
            "location": "location",
            "designation": "designation",
            "last_company_name": "last_company_name",
            "education": "education",
        }
        for input_key, attr in text_fields.items():
            if input_key in data:
                value = sanitize_text(str(data.get(input_key) or "")).strip()
                if attr == "email":
                    value = value.lower()
                setattr(candidate, attr, value)

        if "total_experience_years" in data:
            try:
                candidate.total_experience_years = max(0, float(data.get("total_experience_years") or 0))
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Experience must be a number")

        if "key_skills" in data:
            candidate.key_skills = ", ".join(_split_skill_text(data.get("key_skills")))
        if "matched_skills" in data:
            candidate.matched_skills = ",".join(_split_skill_text(data.get("matched_skills")))
        if "missing_skills" in data:
            candidate.missing_skills = ",".join(_split_skill_text(data.get("missing_skills")))
        if "projects" in data:
            candidate.projects = json.dumps(_manual_project_records(data.get("projects")), ensure_ascii=False)

        should_review = bool(data.get("review", True))
        if should_review:
            _rescore_candidate_from_stored_fields(candidate, job)

        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="manual_profile_update",
            title="Candidate profile manually edited",
            body="Recruiter edited stored candidate data and refreshed review signals." if should_review else "Recruiter edited stored candidate data.",
        )

        db.commit()
        db.refresh(candidate)
        note_map, tag_map = _candidate_notes_and_tags(db, [candidate.id])
        return {
            "message": "Candidate profile updated",
            "candidate": _candidate_result_payload(candidate, job, note_map, tag_map),
        }
    finally:
        db.close()


@router.post("/candidate-rereview/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def rereview_candidate_profile(resume_id: str):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id, Resume.is_active == True).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        job = db.query(Job).filter(Job.id == candidate.job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        repaired = _repair_stored_candidate_profile(candidate, job, force=False)
        if not repaired:
            _rescore_candidate_from_stored_fields(candidate, job)
        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="manual_rereview",
            title="Candidate profile re-reviewed",
            body=(
                "Recruiter repaired polluted stored profile data and refreshed review signals."
                if repaired
                else "Recruiter refreshed scoring from the current stored candidate data."
            ),
        )
        db.commit()
        db.refresh(candidate)
        note_map, tag_map = _candidate_notes_and_tags(db, [candidate.id])
        return {
            "message": "Candidate profile re-reviewed",
            "candidate": _candidate_result_payload(candidate, job, note_map, tag_map),
        }
    finally:
        db.close()


def _safe_json_from_ai(content: str):
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def _fallback_candidate_recommendation(job: Job, candidate: Resume):
    score = candidate.final_score or 0
    matched = candidate.matched_skills or candidate.key_skills or "Relevant resume signals found"
    missing = candidate.missing_skills or "Verify mandatory JD skills during recruiter review"
    verdict = "Shortlist" if score >= 65 else "Review" if score >= 50 else "Reject"
    projects = _candidate_projects(candidate)
    project_evidence = []
    for project in projects[:4]:
        if isinstance(project, dict):
            name = project.get("name") or "Project"
            description = project.get("description") or ""
            technologies = project.get("technologies") or []
            tech_text = f" Tools: {', '.join(map(str, technologies[:6]))}." if technologies else ""
            project_evidence.append(f"{name}: {description[:180]}{tech_text}".strip())
        else:
            project_evidence.append(str(project)[:220])

    return {
        "verdict": verdict,
        "summary": candidate.ranking_reason or f"Candidate scored {score}/100 against the JD.",
        "detailed_assessment": (
            f"Score is {score}/100. Review the candidate against the JD using matched skills, "
            "missing skills, education, and any project evidence found in the resume."
        ),
        "strengths": [
            f"Matched evidence: {matched}",
            f"Role alignment: {candidate.designation or job.job_title or 'candidate profile'}",
            f"Experience signal: {candidate.total_experience_years or 0} years listed",
        ],
        "project_evidence": project_evidence or [
            "Project details were not clearly available in the stored resume text."
        ],
        "gaps": [
            missing,
        ],
    }


def _normalize_candidate_recommendation(data: dict, fallback: dict):
    if not isinstance(data, dict):
        return fallback

    verdict = data.get("verdict") or fallback["verdict"]
    summary = data.get("summary") or fallback["summary"]
    detailed_assessment = data.get("detailed_assessment") or fallback["detailed_assessment"]
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else fallback["strengths"]
    project_evidence = data.get("project_evidence") if isinstance(data.get("project_evidence"), list) else fallback["project_evidence"]
    gaps = data.get("gaps") if isinstance(data.get("gaps"), list) else fallback["gaps"]

    return {
        "verdict": str(verdict)[:40],
        "summary": str(summary)[:500],
        "detailed_assessment": str(detailed_assessment)[:900],
        "strengths": [str(item)[:180] for item in strengths[:4] if str(item).strip()],
        "project_evidence": [str(item)[:220] for item in project_evidence[:4] if str(item).strip()],
        "gaps": [str(item)[:180] for item in gaps[:3] if str(item).strip()],
    }


@router.get("/top-candidate-recommendation/{job_id}/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def top_candidate_recommendation(job_id: str, resume_id: str):
    db = SessionLocal()

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        candidate = db.query(Resume).filter(
            Resume.id == resume_id,
            Resume.job_id == job_id,
            Resume.is_active == True,
        ).first()

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        projects = _candidate_projects(candidate)
        if projects:
            db.commit()

        fallback = _fallback_candidate_recommendation(job, candidate)

        if not client:
            return fallback

        prompt = f"""
Return ONLY valid JSON for an ATS top-candidate recommendation.

JSON shape:
{{
  "verdict": "Shortlist" | "Review" | "Reject",
  "summary": "one concise recruiter-facing sentence",
  "detailed_assessment": "4 to 6 recruiter-facing sentences comparing JD requirements with resume evidence",
  "strengths": ["2 to 4 specific strengths based on the JD and resume"],
  "project_evidence": ["1 to 4 concrete project/work examples from the resume text, or say if no project evidence is found"],
  "gaps": ["1 to 3 specific gaps or validation points"]
}}

Rules:
- Use the job description as the source of role requirements.
- Use the candidate data as evidence only; do not invent projects or experience.
- Focus on actual resume evidence: projects, tools used, work responsibilities, education, and candidate experience.
- Do not write generic points like "manual validation recommended" unless you also explain exactly what to validate and why.
- Be detailed enough for a recruiter to decide the next action, but avoid fluff.
- If the score is low, do not recommend shortlist unless the evidence clearly supports it.

Job title: {job.job_title}
Job description:
{(job.jd_text or "")[:3500]}

Candidate:
Name: {candidate.full_name}
Designation: {candidate.designation}
Experience years: {candidate.total_experience_years}
Education: {candidate.education}
Skills: {candidate.key_skills}
Matched skills: {candidate.matched_skills}
Missing skills: {candidate.missing_skills}
Final score: {candidate.final_score}
Existing ranking reason: {candidate.ranking_reason}
Extracted projects:
{json.dumps(projects, ensure_ascii=False)[:2500]}

Resume text:
{(candidate.resume_text or "")[:2500]}
"""

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_RECOMMENDATION_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a strict hiring analyst. Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        content = response.choices[0].message.content or ""
        recommendation = _normalize_candidate_recommendation(_safe_json_from_ai(content), fallback)

        candidate.ai_recommendation = recommendation["verdict"]
        candidate.ranking_reason = recommendation["summary"]
        db.commit()

        return recommendation

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Top candidate AI recommendation failed")
        if "job" in locals() and "candidate" in locals() and job and candidate:
            return _fallback_candidate_recommendation(job, candidate)
        raise HTTPException(status_code=500, detail="AI recommendation failed")
    finally:
        db.close()


@router.get("/download-resume/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def download_resume(resume_id: str):
    db = SessionLocal()

    try:
        candidate = db.query(Resume).filter(
            Resume.id == resume_id,
            Resume.is_active == True,
        ).first()

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        stored_path = candidate.resume_file_path or ""
        if is_supabase_uri(stored_path):
            filename = candidate.resume_original_filename or "resume"
            db.commit()
            return StreamingResponse(
                io.BytesIO(download_supabase_file(stored_path)),
                media_type=candidate.resume_content_type or "application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        file_path = _candidate_resume_file(candidate)
        if not file_path:
            raise HTTPException(status_code=404, detail="Original resume file is not available for this candidate")

        filename = candidate.resume_original_filename or file_path.name
        db.commit()
        return FileResponse(
            path=str(file_path),
            media_type=candidate.resume_content_type or "application/octet-stream",
            filename=filename,
        )
    finally:
        db.close()

# ---------------- DOWNLOAD CSV ----------------

@router.get("/download-csv/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def download_csv(job_id: str):

    db = SessionLocal()

    resumes = db.query(Resume).filter(
        Resume.job_id == job_id,
        Resume.is_active == True
    ).all()

    if not resumes:
        db.close()
        return {"error": "No resumes found"}

    resumes = sorted(resumes, key=lambda x: x.final_score or 0, reverse=True)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Rank",
        "Full Name",
        "Email",
        "Final Score"
    ])

    for index, r in enumerate(resumes, start=1):

        writer.writerow([
            index,
            r.full_name or "",
            r.email or "",
            r.final_score or 0
        ])

    output.seek(0)
    db.close()

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=job_{job_id}_results.csv"
        }
    )
# ---------------- GET ALL JOBS (FOR ATS DASHBOARD) ----------------

@router.get("/jobs", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_jobs():

    db = SessionLocal()

    jobs = db.query(Job).order_by(Job.created_at.desc()).all()

    result = []

    for job in jobs:

        resumes = db.query(Resume).filter(
            Resume.job_id == job.id,
            Resume.is_active == True
        ).all()

        total_applicants = len(resumes)
        shortlisted_count = len([
            r for r in resumes
            if r.shortlisted and r.status != "Communication"
        ])
        communication_count = len([
            r for r in resumes
            if r.status == "Communication" or r.stage == "communication"
        ])

        top_score = 0
        if resumes:
            top_score = max([r.final_score or 0 for r in resumes])
        ensure_apply_slug(job, db)
        if not job.generated_linkedin_post or not job.generated_whatsapp_message or not job.generated_naukri_text:
            ensure_generated_sourcing_content(job, db)
        source_counts = {source: 0 for source in [*TRACKED_APPLICATION_SOURCES, "unknown"]}
        for resume in resumes:
            source = normalize_application_source(resume.application_source)
            source_counts[source] = source_counts.get(source, 0) + 1

        result.append({

            "id": job.id,
            "job_title": job.job_title,
            "company_name": job.company_name,
            "location": job.location,
            "salary_range": job.salary_range,
            "job_type": job.job_type,
            "jd_text": job.jd_text,
            "required_skills": ",".join(
                normalize_jd_skills(job.required_skills or "", job.jd_text or "")
            ),

            "is_active": job.is_active,

            "total_applicants": total_applicants,
            "top_score": top_score,
            "shortlisted_count": shortlisted_count,
            "communication_count": communication_count,
            "public_apply_enabled": job.public_apply_enabled if job.public_apply_enabled is not None else True,
            "source_tracking_enabled": job.source_tracking_enabled if job.source_tracking_enabled is not None else True,
            "resume_folder_path": job.resume_folder_path,
            "applications_by_source": source_counts,
            **sourcing_payload(job)

        })

    db.commit()
    db.close()

    return result


def _extract_folder_resume_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(str(file_path))
    if suffix == ".docx":
        return extract_text_from_docx(str(file_path))
    if suffix == ".txt":
        return normalize_extracted_text(file_path.read_text(encoding="utf-8", errors="ignore"))
    return ""


def _copy_folder_resume_to_uploads(source_path: Path, job_id: str) -> Path:
    settings = get_settings()
    upload_root = Path(settings.upload_dir).resolve()
    target_dir = upload_root / "resume_folders" / job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(
        f"{source_path.resolve()}|{source_path.stat().st_mtime_ns}|{source_path.stat().st_size}".encode()
    ).hexdigest()[:16]
    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", source_path.name).strip(" .") or f"{fingerprint}{source_path.suffix}"
    target_path = target_dir / f"{fingerprint}_{safe_name}"
    if not target_path.exists():
        shutil.copy2(source_path, target_path)
    return target_path


def _persist_folder_resume(source_path: Path, job_id: str) -> str:
    stored_path = _copy_folder_resume_to_uploads(source_path, job_id)
    content_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"
    return persist_resume_file(str(stored_path), source_path.name, content_type, job_id)


def _save_folder_resume_application(db, job: Job, source_path: Path) -> tuple[bool, str]:
    text = _extract_folder_resume_text(source_path)
    if not text.strip():
        return False, "text extraction failed"

    jd_skills = normalize_jd_skills(job.required_skills or "", job.jd_text or "")
    jd_data = {
        "min_experience_years": job.min_experience_years,
        "education": job.education,
        "role": job.role or job.job_title or "",
        "preferred_skills": job.preferred_skills or "",
    }
    parsed, exp_data, _score_data = analyze_resume_for_job(text[:12000], job.jd_text or "", jd_skills, jd_data)

    candidate_email = (parsed.get("email") or "").strip().lower()
    candidate_phone = (parsed.get("phone") or "").strip()
    file_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    duplicate_key_source = f"{job.id}|{candidate_email or file_hash}|{candidate_phone or file_hash}"
    duplicate_key = hashlib.sha256(duplicate_key_source.encode()).hexdigest()
    duplicate = db.query(Resume).filter(Resume.job_id == job.id, Resume.duplicate_key == duplicate_key).first()
    if duplicate:
        return False, "duplicate skipped"

    stored_path = _persist_folder_resume(source_path, job.id)
    score = parsed.get("rank_score") or parsed.get("final_score") or 0
    shortlist_threshold = job.shortlist_score or 70
    recommendation = parsed.get("recommendation")
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

    resume_entry = Resume(
        job_id=job.id,
        organization_id=job.organization_id,
        full_name=parsed.get("full_name"),
        email=candidate_email,
        phone=candidate_phone,
        location=parsed.get("location"),
        key_skills=", ".join(parsed.get("key_skills", [])) if parsed.get("key_skills") else "",
        projects=json.dumps(parsed.get("projects") or [], ensure_ascii=False),
        designation=parsed.get("designation"),
        total_experience_years=parsed.get("total_experience_years"),
        last_company_name=exp_data.get("last_company_name"),
        last_working_date=exp_data.get("last_working_date"),
        education=_education_label(parsed.get("education") or []),
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
        matched_skills=",".join(parsed.get("matched_skills", [])),
        missing_skills=",".join(parsed.get("missing_skills", [])),
        skill_match_percent=parsed.get("skill_match_percent"),
        resume_text=text[:12000],
        resume_file_path=str(stored_path),
        resume_original_filename=source_path.name,
        resume_content_type=mimetypes.guess_type(str(source_path))[0] or "application/octet-stream",
        explanation=_text_value(parsed.get("ai_recruiter_explanation")),
        application_source="folder",
        shortlisted=ai_shortlisted,
        shortlisted_auto=ai_shortlisted,
        shortlisted_manual=False,
        status=status,
        stage=stage,
        is_active=True,
    )
    apply_resume_intelligence_fields(resume_entry, parsed)
    db.add(resume_entry)
    return True, "imported"


@router.post("/jobs/{job_id}/resume-folder", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def configure_resume_folder(job_id: str, payload: ResumeFolderRequest):
    folder = Path(payload.folder_path or "").expanduser()
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Folder path does not exist or is not a directory.")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.resume_folder_path = str(folder.resolve())
        db.commit()
        return {"job_id": job.id, "resume_folder_path": job.resume_folder_path}
    finally:
        db.close()


@router.post("/jobs/{job_id}/resume-folder/sync", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def sync_resume_folder(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        folder = Path(job.resume_folder_path or "").expanduser()
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail="Configure a valid resume folder first.")

        allowed = {".pdf", ".docx", ".txt"}
        files = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in allowed)
        imported = 0
        skipped = 0
        failed = 0
        messages = []
        for file_path in files:
            try:
                created, reason = _save_folder_resume_application(db, job, file_path)
                if created:
                    imported += 1
                else:
                    skipped += 1
                messages.append({"file": file_path.name, "status": reason})
            except Exception as exc:
                failed += 1
                logger.exception("Resume folder import failed for %s", file_path)
                messages.append({"file": file_path.name, "status": f"failed: {exc}"})

        db.commit()
        return {
            "job_id": job.id,
            "folder": str(folder.resolve()),
            "scanned": len(files),
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "messages": messages[:50],
        }
    finally:
        db.close()


@router.get("/analytics/applications-by-source", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def applications_by_source(job_id: str | None = Query(default=None)):
    db = SessionLocal()

    try:
        query = db.query(Resume.application_source, func.count(Resume.id)).filter(Resume.is_active == True)
        if job_id:
            job = resolve_job_identifier(job_id, db)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            query = query.filter(Resume.job_id == job.id)

        counts = {source: 0 for source in [*TRACKED_APPLICATION_SOURCES, "unknown"]}
        for source, count in query.group_by(Resume.application_source).all():
            counts[normalize_application_source(source)] += int(count or 0)

        return counts
    finally:
        db.close()

@router.put("/deactivate-job/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def deactivate_job(job_id: str):

    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        db.close()
        return {"error": "Job not found"}

    job.is_active = False

    db.commit()
    db.refresh(job)   # ⭐ IMPORTANT


    db.close()

    return {"message": "Job deactivated"}
@router.get("/top-candidate", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_top_candidate():

    db = SessionLocal()

    candidate = db.query(Resume)\
        .filter(Resume.is_active == True)\
        .order_by(Resume.final_score.desc())\
        .first()

    if not candidate:
        db.close()
        return {"name": "None"}

    job = db.query(Job).filter(Job.id == candidate.job_id).first()

    result = {
        "name": candidate.full_name,
        "score": candidate.final_score,
        "experience": candidate.total_experience_years,
        "job": job.job_title if job else ""
    }

    db.close()

    return result
@router.post("/shortlist/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def shortlist_candidate(resume_id: str):

    db = SessionLocal()

    candidate = db.query(Resume).filter(
        Resume.id == resume_id
    ).first()

    if not candidate:
        db.close()
        return {"error": "Candidate not found"}

    if candidate.status == "Shortlisted":
        db.close()
        return {"message": "Already shortlisted"}

    previous_stage = candidate.stage
    candidate.shortlisted = True
    candidate.shortlisted_manual = True
    candidate.status = "Shortlisted"
    candidate.stage = "shortlisted"
    _record_candidate_workflow_event(
        db,
        candidate,
        activity_type="candidate_shortlisted",
        title="Candidate shortlisted",
        from_stage=previous_stage,
        to_stage="shortlisted",
        reason="Manual shortlist action",
    )

    db.commit()
    db.refresh(candidate)
    db.close()

    return {"message": "Candidate shortlisted"}

@router.delete("/shortlist/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def remove_shortlist(resume_id: str):

    db = SessionLocal()

    candidate = db.query(Resume).filter(
        Resume.id == resume_id
    ).first()

    if not candidate:
        db.close()
        return {"error": "Candidate not found"}

    candidate.shortlisted = False

    # ⭐ ADD THIS LINE
    candidate.status = "Review"
    candidate.stage = "review"

    db.commit()
    db.close()

    return {"message": "Shortlist removed"}

@router.post("/shortlist-by-filter", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def shortlist_by_filter(data: ShortlistFilterRequest = Body(...)):

    db = SessionLocal()

    try:
        job_id = data.job_id
        min_score = data.min_score

        candidates = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.is_active == True
        ).all()

        # 🔥 REMOVE DUPLICATES (IMPORTANT)
        unique = {}

        for c in candidates:

            key = (
                c.email.strip().lower() if c.email else None,
                c.phone.strip() if c.phone else None
            )

            if key not in unique or (c.final_score or 0) > (unique[key].final_score or 0):
                unique[key] = c

        candidates = list(unique.values())

        count = 0

        for c in candidates:


            if c.status in ["Rejected", "Communication"] or c.stage == "communication":
                continue

            score = c.final_score or 0

            if min_score is None or score >= min_score:
                previous_stage = c.stage
                c.shortlisted = True
                c.shortlisted_manual = True
                c.status = "Shortlisted"
                count += 1
                c.stage = "shortlisted"
                _record_candidate_workflow_event(
                    db,
                    c,
                    activity_type="candidate_shortlisted_by_filter",
                    title="Candidate shortlisted by score filter",
                    from_stage=previous_stage,
                    to_stage="shortlisted",
                    reason=f"Minimum score filter: {min_score}",
                )
            else:
                previous_stage = c.stage
                c.shortlisted = False
                c.status = "Review"
                c.stage = "review"
                if previous_stage == "shortlisted":
                    _record_candidate_workflow_event(
                        db,
                        c,
                        activity_type="candidate_removed_by_filter",
                        title="Candidate returned to review by score filter",
                        from_stage=previous_stage,
                        to_stage="review",
                        reason=f"Below minimum score filter: {min_score}",
                    )

        db.commit()

        return {
            "message": f"{count} candidates shortlisted (unique only)"
        }

    finally:
        db.close()

from fastapi import HTTPException

class JobUpdate(BaseModel):
    job_title: str
    company_name: str
    location: str
    salary_range: str
    job_type: str
    jd_text: str


@router.put("/edit-job/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def edit_job(job_id: str, job_data: JobUpdate):

    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        db.close()
        raise HTTPException(status_code=404, detail="Job not found")

    if job_data.job_title:
        job.job_title = job_data.job_title

    if job_data.company_name:
        job.company_name = job_data.company_name

    if job_data.location:
        job.location = job_data.location

    if job_data.salary_range:
        job.salary_range = job_data.salary_range

    if job_data.job_type:
        job.job_type = job_data.job_type

    if job_data.jd_text:
        job.jd_text = job_data.jd_text

    db.commit()
    db.close()

    return {"message": "Job updated successfully"}


@router.put("/activate-job/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def activate_job(job_id: str):

    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        db.close()
        return {"error": "Job not found"}

    job.is_active = True

    db.commit()
    db.refresh(job)
    db.close()

    return {"status": "activated"}


@router.get("/jobs/{job_identifier}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_job_detail(job_identifier: str):
    db = SessionLocal()

    try:
        job = resolve_job_identifier(job_identifier, db)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        ensure_apply_slug(job, db)
        if not job.generated_linkedin_post or not job.generated_whatsapp_message or not job.generated_naukri_text:
            ensure_generated_sourcing_content(job, db)
        db.commit()
        db.refresh(job)

        resumes = db.query(Resume).filter(Resume.job_id == job.id, Resume.is_active == True).all()
        source_counts = {source: 0 for source in [*TRACKED_APPLICATION_SOURCES, "unknown"]}
        for resume in resumes:
            source = normalize_application_source(resume.application_source)
            source_counts[source] = source_counts.get(source, 0) + 1

        return {
            "id": job.id,
            "job_id": job.id,
            "job_title": job.job_title,
            "company_name": job.company_name,
            "department": job.department,
            "location": job.location,
            "work_mode": job.work_mode,
            "job_type": job.job_type,
            "salary_range": job.salary_range,
            "experience_required": job.experience_required,
            "application_deadline": job.application_deadline,
            "hiring_manager": job.hiring_manager,
            "jd_text": job.jd_text,
            "required_skills": job.required_skills,
            "public_apply_enabled": job.public_apply_enabled if job.public_apply_enabled is not None else True,
            "source_tracking_enabled": job.source_tracking_enabled if job.source_tracking_enabled is not None else True,
            "applications_by_source": source_counts,
            **sourcing_payload(job),
        }
    finally:
        db.close()


@router.delete("/jobs/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def delete_job(job_id: str):

    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        db.close()
        return {"error": "Job not found"}

    db.delete(job)
    db.commit()
    db.close()

    return {"status": "deleted"}

def _candidate_tracking_payload(resume_id: str):
    db = SessionLocal()

    candidate = db.query(Resume).filter(
        Resume.id == resume_id
    ).first()

    if not candidate:
        db.close()
        return {"error": "Candidate not found"}

    candidate_email = (candidate.email or candidate.form_email or "").strip().lower()
    if candidate_email and candidate.job_id:
        same_candidate_rows = db.query(Resume).filter(
            Resume.job_id == candidate.job_id,
            Resume.is_active == True,
        ).all()

        def same_person(row):
            row_email = (row.email or row.form_email or "").strip().lower()
            return row_email and row_email == candidate_email

        def tracking_priority(row):
            status_priority = {
                "Interview Scheduling": 60,
                "Communication": 50,
                "Shortlisted": 40,
                "Review": 20,
                "Rejected": 10,
                "Dropped": 0,
            }
            mail_priority = 5 if row.mail_status else 0
            response_priority = 5 if row.response_status else 0
            return (
                status_priority.get(row.status or "", 0),
                mail_priority + response_priority,
                row.final_score or 0,
            )

        matching_rows = [row for row in same_candidate_rows if same_person(row)]
        if matching_rows:
            candidate = sorted(matching_rows, key=tracking_priority, reverse=True)[0]
            effective_mail_status = candidate.mail_status or next((row.mail_status for row in matching_rows if row.mail_status), None)
            effective_response_status = candidate.response_status or next((row.response_status for row in matching_rows if row.response_status), None)
        else:
            effective_mail_status = candidate.mail_status
            effective_response_status = candidate.response_status
    else:
        effective_mail_status = candidate.mail_status
        effective_response_status = candidate.response_status

    if not effective_mail_status and effective_response_status and effective_response_status != "Pending":
        effective_mail_status = "Mail Sent"

    stage_map = {
        "Review": "Screening",
        "Shortlisted": "Shortlisted",
        "Communication": "Communication",
        "Interview Scheduling": "Interview",
        "Rejected": "Rejected",
        "Dropped": "Dropped",
    }
    stages = ["Applied", "Screening", "Shortlisted", "Communication", "Interview", "Selected"]

    current_stage = stage_map.get(candidate.status, candidate.status or "Applied")
    current_index = stages.index(current_stage) if current_stage in stages else 0

    timeline = []

    for i, stage in enumerate(stages):
        timeline.append({
            "stage": stage,
            "done": i <= current_index,
            "active": i == current_index,
        })

    job = db.query(Job).filter(Job.id == candidate.job_id).first() if candidate.job_id else None

    db.close()

    return {
        "id": candidate.id,
        "job_id": candidate.job_id,
        "name": candidate.full_name or candidate.form_full_name,
        "email": candidate.email or candidate.form_email,
        "phone": candidate.phone or candidate.form_phone,
        "location": candidate.location or candidate.form_location,
        "job_title": job.job_title if job else "",
        "company_name": job.company_name if job else "",
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "final_score": candidate.final_score,
        "rank_score": candidate.rank_score,
        "fit_band": candidate.fit_band,
        "score": candidate.final_score,
        "confidence_score": candidate.confidence_score,
        "status": candidate.status,
        "stage": candidate.stage,
        "mail_status": effective_mail_status,
        "response_status": effective_response_status,
        "designation": candidate.designation,
        "experience": candidate.total_experience_years,
        "total_experience_years": candidate.total_experience_years,
        "last_company": candidate.last_company_name,
        "last_company_name": candidate.last_company_name,
        "education": candidate.education,
        "industry": candidate.industry,
        "domain": candidate.domain,
        "matched_skills": candidate.matched_skills,
        "key_skills": candidate.key_skills,
        "missing_skills": candidate.missing_skills,
        "skill_match_percent": candidate.skill_match_percent,
        "resume_quality_score": candidate.resume_quality_score,
        "current_stage": current_stage,
        "timeline": timeline
    }


@router.get("/candidate/tracking-link/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def candidate_tracking_link(resume_id: str):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        token = create_candidate_tracking_token(candidate.id, candidate.job_id)
        frontend_url = get_settings().frontend_url.rstrip("/")
        return {
            "candidate_id": candidate.id,
            "token": token,
            "tracking_url": f"{frontend_url}/candidate-tracking.html?token={token}",
            "expires_in_days": get_settings().candidate_tracking_token_days,
        }
    finally:
        db.close()


@router.get("/candidate/track-token/{token}")
def track_candidate_by_token(token: str):
    payload = decode_candidate_tracking_token(token)
    return _candidate_tracking_payload(payload["candidate_id"])


@router.get("/candidate/track/{resume_id}")
def track_candidate(resume_id: str):
    if not get_settings().allow_legacy_candidate_tracking:
        raise HTTPException(status_code=401, detail="Candidate tracking token required")
    return _candidate_tracking_payload(resume_id)


@router.get("/candidate-workspace/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def candidate_workspace(resume_id: str):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id, Resume.is_active == True).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        notes = (
            db.query(CandidateNote)
            .filter(CandidateNote.candidate_id == resume_id)
            .order_by(CandidateNote.created_at.desc())
            .limit(50)
            .all()
        )
        tags = (
            db.query(CandidateTag)
            .filter(CandidateTag.candidate_id == resume_id)
            .order_by(CandidateTag.created_at.desc())
            .all()
        )
        job = db.query(Job).filter(Job.id == candidate.job_id).first() if candidate.job_id else None
        return {
            "candidate_id": candidate.id,
            "job_id": candidate.job_id,
            "recruiter_trust": _candidate_recruiter_trust(candidate, job),
            "notes": [
                {
                    "id": note.id,
                    "body": note.body,
                    "visibility": note.visibility,
                    "created_at": note.created_at.isoformat() if note.created_at else None,
                }
                for note in notes
            ],
            "tags": [{"id": tag.id, "tag": tag.tag, "color": tag.color} for tag in tags],
            "assigned_recruiter_id": candidate.assigned_recruiter_id,
        }
    finally:
        db.close()


@router.post("/candidate-note/{resume_id}")
def add_legacy_candidate_note(resume_id: str, data: dict = Body(...), user: User = Depends(require_roles("admin", "recruiter", "hiring_manager"))):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id, Resume.is_active == True).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        body = sanitize_text(data.get("body"))
        if not body:
            raise HTTPException(status_code=400, detail="Note body is required")
        note = CandidateNote(
            candidate_id=candidate.id,
            job_id=candidate.job_id,
            author_user_id=user.id,
            body=body,
            visibility=data.get("visibility") or "team",
        )
        db.add(note)
        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="note_added",
            title="Recruiter note added",
            body=body[:300],
        )
        db.commit()
        db.refresh(note)
        return {
            "id": note.id,
            "candidate_id": candidate.id,
            "body": note.body,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        }
    finally:
        db.close()


@router.post("/candidate-tag/{resume_id}")
def add_legacy_candidate_tag(resume_id: str, data: dict = Body(...), user: User = Depends(require_roles("admin", "recruiter", "hiring_manager"))):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id, Resume.is_active == True).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        tag_value = sanitize_text(data.get("tag")).strip().lower()
        if not tag_value:
            raise HTTPException(status_code=400, detail="Tag is required")
        tag = db.query(CandidateTag).filter(CandidateTag.candidate_id == candidate.id, CandidateTag.tag == tag_value).first()
        if not tag:
            tag = CandidateTag(candidate_id=candidate.id, tag=tag_value, color=data.get("color"))
            db.add(tag)
            _record_candidate_workflow_event(
                db,
                candidate,
                activity_type="tag_added",
                title=f"Tag added: {tag_value}",
            )
        db.commit()
        return {"candidate_id": candidate.id, "tag": tag_value}
    finally:
        db.close()


@router.post("/candidate-assign-me/{resume_id}")
def assign_candidate_to_me(resume_id: str, user: User = Depends(require_roles("admin", "recruiter", "hiring_manager"))):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id, Resume.is_active == True).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        candidate.assigned_recruiter_id = user.id
        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="candidate_assigned",
            title=f"Candidate assigned to {user.name}",
        )
        db.commit()
        return {"candidate_id": candidate.id, "assigned_recruiter_id": user.id, "assigned_recruiter_name": user.name}
    finally:
        db.close()


@router.get("/client-shortlist-report/{job_id}", response_class=HTMLResponse, dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def client_shortlist_report(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        candidates = (
            db.query(Resume)
            .filter(
                Resume.job_id == job_id,
                Resume.shortlisted == True,
                Resume.is_active == True,
                Resume.status != "Communication",
            )
            .all()
        )
        candidates = sorted(candidates, key=lambda row: row.rank_score or row.final_score or 0, reverse=True)
        rows = []
        for index, candidate in enumerate(candidates, start=1):
            trust = _candidate_recruiter_trust(candidate, job)
            rows.append(
                f"""
                <tr>
                    <td>#{index}</td>
                    <td><strong>{html.escape(candidate.full_name or candidate.form_full_name or "Candidate")}</strong><br><span>{html.escape(candidate.designation or "")}</span></td>
                    <td>{html.escape(str(candidate.total_experience_years or "-"))}</td>
                    <td>{html.escape(str(round(float(trust["rank_score"] or 0), 1)))}</td>
                    <td>{html.escape(trust["score_band"])}</td>
                    <td>{html.escape(", ".join(trust["matched_skills"][:6]) or "-")}</td>
                    <td>{html.escape(trust["client_summary"])}</td>
                </tr>
                """
            )
        report_date = datetime.utcnow().strftime("%Y-%m-%d")
        return f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Client Shortlist Report</title>
            <style>
                body{{font-family:Arial,sans-serif;color:#111827;margin:32px;}}
                header{{border-bottom:2px solid #111827;padding-bottom:18px;margin-bottom:24px;}}
                h1{{margin:0 0 8px;font-size:28px;}}
                .meta{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px;}}
                .meta div{{border:1px solid #e5e7eb;padding:12px;border-radius:6px;}}
                table{{width:100%;border-collapse:collapse;margin-top:22px;font-size:13px;}}
                th,td{{border:1px solid #d1d5db;padding:10px;text-align:left;vertical-align:top;}}
                th{{background:#f3f4f6;}}
                span{{color:#6b7280;}}
                .actions{{margin:18px 0;}}
                button{{padding:10px 14px;border:0;background:#111827;color:white;border-radius:6px;cursor:pointer;}}
                @media print{{.actions{{display:none}} body{{margin:12mm}}}}
            </style>
        </head>
        <body>
            <header>
                <h1>{html.escape(job.job_title or "Shortlist")} - Client Shortlist Report</h1>
                <p>{html.escape(job.company_name or "")} | {html.escape(job.location or "")} | Generated {report_date}</p>
                <div class="meta">
                    <div><strong>{len(candidates)}</strong><br><span>Shortlisted candidates</span></div>
                    <div><strong>{html.escape(str(job.shortlist_score or 70))}</strong><br><span>Shortlist threshold</span></div>
                    <div><strong>{html.escape(", ".join(_split_skill_text(job.required_skills)[:5]) or "-")}</strong><br><span>Core required skills</span></div>
                </div>
            </header>
            <div class="actions"><button onclick="window.print()">Print or Save as PDF</button></div>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Candidate</th>
                        <th>Years</th>
                        <th>Score</th>
                        <th>Fit</th>
                        <th>Matched Skills</th>
                        <th>Client Summary</th>
                    </tr>
                </thead>
                <tbody>{''.join(rows) if rows else '<tr><td colspan="7">No shortlisted candidates available.</td></tr>'}</tbody>
            </table>
        </body>
        </html>
        """
    finally:
        db.close()

@router.get("/shortlisted", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_shortlisted(job_id: str, min_score: float | None = None):

    db = SessionLocal()

    try:
        query = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.shortlisted == True,
            Resume.status != "Communication",
            Resume.is_active == True
        )

        if min_score is not None:
            query = query.filter(Resume.final_score >= min_score)

        candidates = query.order_by(Resume.final_score.desc()).all()

        # 🔥 REMOVE DUPLICATES


        unique = {}

        for c in candidates:

            key = (
                c.email.strip().lower() if c.email else None,
                c.phone.strip() if c.phone else None
            )

            if key not in unique or (c.final_score or 0) > (unique[key].final_score or 0):
                unique[key] = c

        candidates = sorted(
            unique.values(),
            key=lambda c: c.rank_score or c.final_score or 0,
            reverse=True
        )

        # 🔥 RESPONSE
        job = db.query(Job).filter(Job.id == job_id).first()
        note_map, tag_map = _candidate_notes_and_tags(db, [c.id for c in candidates])

        return [_shortlist_candidate_payload(c, job, note_map, tag_map) for c in candidates]

    finally:
        db.close()


@router.get("/workflow-overview/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def workflow_overview(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        candidates = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.is_active == True,
        ).all()

        stage_counts = {
            "applied": 0,
            "review": 0,
            "shortlisted": 0,
            "communication": 0,
            "interview_scheduling": 0,
            "rejected": 0,
        }

        for candidate in candidates:
            stage = candidate.stage or (candidate.status or "review").lower().replace(" ", "_")
            if stage not in stage_counts:
                stage = "review"
            stage_counts[stage] += 1

        shortlist_ready = len([
            c for c in candidates
            if c.stage in {"review", "applied"} and (c.final_score or 0) >= (job.shortlist_score or 70)
        ])
        outreach_pending = len([
            c for c in candidates
            if c.stage == "communication" and (c.response_status or "Pending") == "Pending"
        ])
        interview_ready = len([
            c for c in candidates
            if c.stage == "interview_scheduling"
        ])

        next_actions = []
        if shortlist_ready:
            next_actions.append(f"Review {shortlist_ready} score-qualified candidate(s) for shortlist.")
        if stage_counts["shortlisted"]:
            next_actions.append(f"Move {stage_counts['shortlisted']} shortlisted candidate(s) to communication after recruiter review.")
        if outreach_pending:
            next_actions.append(f"Follow up with {outreach_pending} candidate(s) waiting in communication.")
        if interview_ready:
            next_actions.append(f"Schedule interviews for {interview_ready} ready candidate(s).")
        if not next_actions:
            next_actions.append("Pipeline is clear. Add candidates or review archived decisions.")

        return {
            "job_id": job.id,
            "job_title": job.job_title,
            "shortlist_score": job.shortlist_score or 70,
            "total_active_candidates": len(candidates),
            "stage_counts": stage_counts,
            "next_actions": next_actions,
            "workflow": [
                {"key": "applied", "label": "Applied"},
                {"key": "review", "label": "Review"},
                {"key": "shortlisted", "label": "Shortlisted"},
                {"key": "communication", "label": "Communication"},
                {"key": "interview_scheduling", "label": "Interview"},
                {"key": "selected", "label": "Selected"},
            ],
        }
    finally:
        db.close()


@router.get("/candidate-workflow/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def candidate_workflow(resume_id: str):
    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(Resume.id == resume_id).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        history = db.query(CandidateStageHistory).filter(
            CandidateStageHistory.candidate_id == resume_id
        ).order_by(CandidateStageHistory.created_at.desc()).limit(50).all()
        activities = db.query(CandidateActivity).filter(
            CandidateActivity.candidate_id == resume_id
        ).order_by(CandidateActivity.created_at.desc()).limit(50).all()

        return {
            "candidate_id": candidate.id,
            "job_id": candidate.job_id,
            "name": candidate.full_name or candidate.form_full_name,
            "status": _workflow_status_for_stage(candidate.stage, candidate.status),
            "stage": candidate.stage,
            "mail_status": candidate.mail_status,
            "response_status": candidate.response_status,
            "history": [
                {
                    "from_stage": item.from_stage,
                    "to_stage": item.to_stage,
                    "reason": item.reason,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in history
            ],
            "activities": [
                {
                    "type": item.activity_type,
                    "title": item.title,
                    "body": item.body,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in activities
            ],
        }
    finally:
        db.close()

@router.delete("/shortlist/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def remove_shortlist(resume_id: str):

    db = SessionLocal()

    candidate = db.query(Resume).filter(
        Resume.id == resume_id
    ).first()

    if not candidate:
        db.close()
        return {"error": "Candidate not found"}

    # ✅ ONLY REMOVE FROM SHORTLIST
    previous_stage = candidate.stage
    previous_stage = candidate.stage
    candidate.shortlisted = False
    candidate.status = "Review"
    candidate.stage = "review"
    _record_candidate_workflow_event(
        db,
        candidate,
        activity_type="candidate_removed_from_shortlist",
        title="Candidate moved back to review",
        from_stage=previous_stage,
        to_stage="review",
        reason="Removed from shortlist",
    )
    _record_candidate_workflow_event(
        db,
        candidate,
        activity_type="candidate_removed_from_shortlist",
        title="Candidate moved back to review",
        from_stage=previous_stage,
        to_stage="review",
        reason="Removed from shortlist",
    )

    db.commit()
    db.close()

    return {"message": "Removed from shortlist"}

@router.post("/reject/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def reject_candidate(resume_id: str):

    db = SessionLocal()

    candidate = db.query(Resume).filter(
        Resume.id == resume_id
    ).first()

    if not candidate:
        db.close()
        return {"error": "Candidate not found"}

    previous_stage = candidate.stage
    candidate.status = "Rejected"
    candidate.stage = "rejected"
    candidate.shortlisted = False
    _record_candidate_workflow_event(
        db,
        candidate,
        activity_type="candidate_rejected",
        title="Candidate rejected",
        from_stage=previous_stage,
        to_stage="rejected",
        reason="Recruiter rejected candidate",
    )

    db.commit()
    db.refresh(candidate)   # 👈 VERY IMPORTANT

    db.close()

    return {"message": "Candidate rejected"}


@router.post("/drop-candidate/{resume_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def drop_candidate(resume_id: str):
    db = SessionLocal()

    try:
        candidate = db.query(Resume).filter(
            Resume.id == resume_id,
            Resume.is_active == True,
        ).first()

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        previous_stage = candidate.stage
        candidate.is_active = False
        candidate.status = "Dropped"
        candidate.stage = "dropped"
        candidate.shortlisted = False
        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="candidate_dropped",
            title="Candidate dropped from active workflow",
            from_stage=previous_stage,
            to_stage="dropped",
            reason="Recruiter dropped candidate",
        )

        db.commit()

        return {"message": "Candidate dropped"}
    finally:
        db.close()


@router.post("/move-to-communication", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def move_to_communication(job_id: str):

    db = SessionLocal()

    try:
        candidates = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.shortlisted == True,
            Resume.status != "Communication",
            Resume.is_active == True
        ).all()

        count = 0

        for c in candidates:

            # ❗ already moved ko skip kar
            if c.status == "Communication":
                continue

            # 🔥 MOVE
            previous_stage = c.stage
            c.status = "Communication"
            c.stage = "communication"
            c.shortlisted = False   # shortlist se hata do
            c.mail_status = c.mail_status or "Not Contacted"
            c.response_status = c.response_status or "Pending"
            _record_candidate_workflow_event(
                db,
                c,
                activity_type="candidate_moved_to_communication",
                title="Candidate moved to communication",
                from_stage=previous_stage,
                to_stage="communication",
                reason="Moved from shortlist to communication",
            )

            count += 1

        db.commit()

        return {
            "message": f"{count} candidates moved to Communication",
            "count": count
        }

    finally:
        db.close()


@router.post("/move-all-to-communication", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def move_all_to_communication(job_id: str):
    return move_to_communication(job_id)


@router.get("/communication", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_communication(job_id: str):

    db = SessionLocal()

    try:
        candidates = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.status == "Communication",   # 🔥 MAIN FILTER
            Resume.is_active == True
        ).all()

        return [
            {
                "id": c.id,
                "name": c.full_name,
                "email": c.email,
                "status": c.status,
                "final_score": c.final_score or 0,
                "confidence_score": c.confidence_score or 0,
                "next_step": "Send outreach" if (c.mail_status or "Not Contacted") == "Not Contacted" else "Await response",
                "mail_status": c.mail_status or "Not Contacted",
                "response_status": c.response_status or "Pending"
            }
            for c in candidates
        ]

    finally:
        db.close()


@router.get("/communication-filter", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_communication_filter(job_id: str):

    db = SessionLocal()

    try:
        candidates = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.status == "Communication",
            Resume.is_active == True
        ).all()

        result = {
            "pending": [],
            "interested": [],
            "not_interested": []
        }

        for c in candidates:
            response_status = c.response_status or "Pending"
            mail_status = c.mail_status or "Not Contacted"
            candidate_test = db.query(CandidateAssessment).filter(
                CandidateAssessment.candidate_id == c.id,
                CandidateAssessment.job_id == c.job_id,
            ).order_by(CandidateAssessment.sent_at.desc()).first()

            item = {
                "id": c.id,
                "name": c.full_name,
                "email": c.email,
                "mail_status": mail_status,
                "response_status": response_status,
                "final_score": c.final_score or 0,
                "confidence_score": c.confidence_score or 0,
                "next_step": "Send outreach" if mail_status == "Not Contacted" else "Await response",
                "status": mail_status if mail_status == "Not Contacted" else response_status,
                "test_status": candidate_test.status if candidate_test else None,
                "test_score": candidate_test.score if candidate_test else None,
                "test_max_score": candidate_test.max_score if candidate_test else None,
                "test_percentage": candidate_test.percentage if candidate_test else None,
                "test_result_status": candidate_test.result_status if candidate_test else None,
                "interview_status": candidate_test.interview_status if candidate_test else None,
            }

            normalized = response_status.strip().lower()

            if normalized == "interested":
                item["status"] = "Interested"
                result["interested"].append(item)
            elif normalized in ["not interested", "not_interested"]:
                item["status"] = "Not Interested"
                result["not_interested"].append(item)
            else:
                result["pending"].append(item)

        return result

    finally:
        db.close()


@router.get("/ai-candidate-search", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def ai_candidate_search(query: str, job_id: str | None = None, limit: int = 20):
    db = SessionLocal()

    try:
        filters = [Resume.is_active == True]
        if job_id:
            filters.append(Resume.job_id == job_id)

        candidates = db.query(Resume).filter(*filters).all()

        ranked = []
        for candidate in candidates:
            searchable_text = " ".join([
                candidate.designation or "",
                candidate.key_skills or "",
                candidate.resume_text or "",
                candidate.ranking_reason or "",
            ])
            similarity = cosine_similarity_cached(query, searchable_text)
            ranked.append({
                "id": candidate.id,
                "job_id": candidate.job_id,
                "name": candidate.full_name,
                "email": candidate.email,
                "designation": candidate.designation,
                "final_score": candidate.final_score,
                "rank_score": candidate.rank_score,
                "fit_band": candidate.fit_band,
                "confidence_score": candidate.confidence_score,
                "status": candidate.status,
                "semantic_search_score": similarity,
                "ranking_reason": candidate.ranking_reason,
            })

        ranked.sort(
            key=lambda item: (
                item["semantic_search_score"] or 0,
                item["rank_score"] or item["final_score"] or 0,
                item["confidence_score"] or 0,
            ),
            reverse=True
        )

        return {
            "query": query,
            "total": len(ranked),
            "results": ranked[:max(1, min(limit, 100))],
            "vector_ready": True
        }

    finally:
        db.close()

from openai import OpenAI
import smtplib
from email.mime.text import MIMEText

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None


def _fallback_ai_hiring_summary(job: Job, candidate: Resume):
    projects = _candidate_projects(candidate)
    project_items = []
    for project in projects[:4]:
        if isinstance(project, dict):
            name = project.get("name") or "Project"
            description = project.get("description") or ""
            technologies = project.get("technologies") or []
            tech_text = f" Tools: {', '.join(map(str, technologies[:6]))}." if technologies else ""
            project_items.append(f"{name}: {description[:220]}{tech_text}".strip())
        else:
            project_items.append(str(project)[:260])

    score = candidate.final_score or 0
    if score >= 70:
        verdict = "Strong shortlist candidate"
    elif score >= 50:
        verdict = "Review before shortlist"
    else:
        verdict = "Low-match profile"

    return {
        "generated": False,
        "candidate_name": candidate.full_name or "Candidate",
        "verdict": verdict,
        "overall_summary": (
            f"{candidate.full_name or 'This candidate'} scored {score}/100 for the "
            f"{job.job_title or 'selected'} role. Review the resume evidence, matched skills, "
            "missing skills, projects, and experience before making a shortlist decision."
        ),
        "profile_summary": (
            f"Profile shows designation '{candidate.designation or 'not listed'}', "
            f"{candidate.total_experience_years or 0} years of experience, education '{candidate.education or 'not listed'}', "
            f"and skills: {candidate.key_skills or 'not clearly listed'}."
        ),
        "jd_alignment": (
            f"Matched skills: {candidate.matched_skills or 'not listed'}. "
            f"Missing or validation skills: {candidate.missing_skills or 'not listed'}."
        ),
        "evidence": [
            f"AI score: {score}/100",
            f"Skill match: {candidate.skill_match_percent or 0}%",
            f"Ranking reason: {candidate.ranking_reason or 'No ranking reason stored'}",
        ],
        "projects": project_items or ["No concrete project details were found in the stored resume text."],
        "risks": [
            candidate.missing_skills or "Validate mandatory JD skills during recruiter review.",
            "Confirm hands-on depth through screening because stored resume data may be incomplete.",
        ],
        "next_steps": [
            "Review the full resume before outreach.",
            "Validate missing mandatory JD skills in recruiter screening.",
            "Use project evidence to prepare role-specific interview questions.",
        ],
    }


def _normalize_ai_hiring_summary(data: dict, fallback: dict):
    if not isinstance(data, dict):
        return fallback

    def clean_text(value, fallback_value="", limit=1200):
        text = str(value or fallback_value or "").strip()
        return text[:limit]

    def clean_list(value, fallback_value, limit=5, item_limit=280):
        items = value if isinstance(value, list) else fallback_value
        cleaned = [str(item).strip()[:item_limit] for item in (items or []) if str(item).strip()]
        return cleaned[:limit] or fallback_value[:limit]

    return {
        "generated": True,
        "candidate_name": clean_text(data.get("candidate_name"), fallback.get("candidate_name"), 120),
        "verdict": clean_text(data.get("verdict"), fallback.get("verdict"), 80),
        "overall_summary": clean_text(data.get("overall_summary"), fallback.get("overall_summary"), 1200),
        "profile_summary": clean_text(data.get("profile_summary"), fallback.get("profile_summary"), 1200),
        "jd_alignment": clean_text(data.get("jd_alignment"), fallback.get("jd_alignment"), 1200),
        "evidence": clean_list(data.get("evidence"), fallback.get("evidence", []), 6, 260),
        "projects": clean_list(data.get("projects"), fallback.get("projects", []), 5, 320),
        "risks": clean_list(data.get("risks"), fallback.get("risks", []), 5, 260),
        "next_steps": clean_list(data.get("next_steps"), fallback.get("next_steps", []), 5, 260),
    }


def _fallback_shortlist_explanation(job_data: dict, candidates: list[dict]):
    scores = [float(candidate.get("score") or candidate.get("final_score") or 0) for candidate in candidates]
    total = len(candidates)
    avg_score = round(sum(scores) / total, 1) if total else 0
    top_candidate = sorted(candidates, key=lambda row: float(row.get("score") or row.get("final_score") or 0), reverse=True)[0] if candidates else {}
    skill_counts = {}

    for candidate in candidates:
        skills = candidate.get("matched_skills") or candidate.get("key_skills") or ""
        if isinstance(skills, str):
            skill_items = [item.strip() for item in skills.replace("|", ",").split(",") if item.strip()]
        else:
            skill_items = [str(item).strip() for item in skills or [] if str(item).strip()]
        for skill in skill_items:
            skill_counts[skill] = skill_counts.get(skill, 0) + 1

    top_skills = sorted(skill_counts.items(), key=lambda item: item[1], reverse=True)[:6]

    return {
        "generated": False,
        "headline": f"{total} shortlisted candidates ready for recruiter review",
        "executive_summary": (
            f"The shortlist for {job_data.get('job_title') or 'the selected role'} contains {total} candidates "
            f"with an average AI score of {avg_score}. The strongest current profile is "
            f"{top_candidate.get('name') or top_candidate.get('full_name') or 'not listed'} based on stored table data."
        ),
        "shortlist_quality": (
            "Use this shortlist as a recruiter review queue. Prioritize the highest scores first, then validate "
            "JD-critical skills, experience claims, and communication fit before outreach."
        ),
        "candidate_priorities": [
            f"Start with {top_candidate.get('name') or top_candidate.get('full_name') or 'the top-ranked candidate'} for first review.",
            f"Average score is {avg_score}, so compare score with mandatory JD evidence before moving candidates forward.",
            "Review hidden table columns such as matched skills, missing skills, education, and last company before final decisions.",
        ],
        "skill_observations": [
            f"{skill} appears in {count} shortlisted candidate(s)." for skill, count in top_skills
        ] or ["No repeated matched-skill evidence was available in the table payload."],
        "risks": [
            "Some shortlisted rows may be missing hidden-column evidence, so validate resume details manually.",
            "Score alone should not decide outreach; confirm mandatory JD skills and experience depth.",
        ],
        "next_steps": [
            "Review top-scoring candidates first.",
            "Validate missing JD skills during screening.",
            "Move strongest candidates to communication after recruiter review.",
        ],
    }


def _normalize_shortlist_explanation(data: dict, fallback: dict):
    if not isinstance(data, dict):
        return fallback

    def clean_text(value, fallback_value="", limit=1400):
        return str(value or fallback_value or "").strip()[:limit]

    def clean_list(value, fallback_value, limit=6, item_limit=320):
        items = value if isinstance(value, list) else fallback_value
        cleaned = [str(item).strip()[:item_limit] for item in (items or []) if str(item).strip()]
        return cleaned[:limit] or fallback_value[:limit]

    return {
        "generated": True,
        "headline": clean_text(data.get("headline"), fallback.get("headline"), 160),
        "executive_summary": clean_text(data.get("executive_summary"), fallback.get("executive_summary")),
        "shortlist_quality": clean_text(data.get("shortlist_quality"), fallback.get("shortlist_quality")),
        "candidate_priorities": clean_list(data.get("candidate_priorities"), fallback.get("candidate_priorities", [])),
        "skill_observations": clean_list(data.get("skill_observations"), fallback.get("skill_observations", [])),
        "risks": clean_list(data.get("risks"), fallback.get("risks", [])),
        "next_steps": clean_list(data.get("next_steps"), fallback.get("next_steps", [])),
    }


@router.post("/ai-shortlist-explanation", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def ai_shortlist_explanation(data: dict = Body(...)):
    job_id = data.get("job_id")
    candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    job_data = data.get("job") if isinstance(data.get("job"), dict) else {}

    db = SessionLocal()

    try:
        if job_id:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job_data = {
                    "id": job.id,
                    "job_title": job.job_title,
                    "company_name": job.company_name,
                    "location": job.location,
                    "required_skills": job.required_skills,
                    "experience_required": job.experience_required or job.min_experience_years,
                    "education": job.education,
                    "jd_text": job.jd_text,
                    **job_data,
                }

        fallback = _fallback_shortlist_explanation(job_data, candidates)

        if not candidates:
            return {
                **fallback,
                "headline": "No shortlisted candidate data available",
                "executive_summary": "Select a job and load shortlisted candidates before generating AI explanation.",
            }

        if not client:
            return fallback

        compact_candidates = []
        for candidate in candidates[:30]:
            compact_candidates.append({
                "rank": candidate.get("rank"),
                "name": candidate.get("name") or candidate.get("full_name"),
                "email": candidate.get("email"),
                "location": candidate.get("location"),
                "experience": candidate.get("experience"),
                "score": candidate.get("score") or candidate.get("final_score"),
                "status": candidate.get("status"),
                "matched_skills": candidate.get("matched_skills"),
                "missing_skills": candidate.get("missing_skills"),
                "skill_match_percent": candidate.get("skill_match_percent"),
                "education": candidate.get("education"),
                "last_company": candidate.get("last_company") or candidate.get("last_company_name"),
                "designation": candidate.get("designation"),
                "industry": candidate.get("industry"),
                "domain": candidate.get("domain"),
            })

        prompt = f"""
Return ONLY valid JSON for a recruiter-facing AI explanation page for this shortlisted candidate table.

JSON shape:
{{
  "headline": "short headline",
  "executive_summary": "5-7 sentence explanation of the shortlist quality using the JD and table data",
  "shortlist_quality": "specific assessment of how strong this shortlist is for the JD",
  "candidate_priorities": ["3-6 candidate prioritization observations"],
  "skill_observations": ["3-6 observations about matched skills and skill gaps"],
  "risks": ["2-5 validation risks tied to the JD"],
  "next_steps": ["2-5 recruiter next actions"]
}}

Rules:
- Use the JD as the role requirement source.
- Use only the table candidate data below; do not invent resumes, projects, companies, skills, or scores.
- Compare candidates as a shortlist, not one candidate at a time.
- Mention where hidden table columns are missing or weak.
- Keep it recruiter-ready and action-oriented.
- Do not include markdown. Return JSON only.

JOB DATA:
{json.dumps(job_data, ensure_ascii=False)[:9000]}

SHORTLISTED TABLE DATA:
{json.dumps(compact_candidates, ensure_ascii=False)[:12000]}
"""

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_RECOMMENDATION_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a senior ATS hiring analyst. Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        content = response.choices[0].message.content or ""
        return _normalize_shortlist_explanation(_safe_json_from_ai(content), fallback)

    except Exception:
        logger.exception("AI shortlist explanation failed")
        return _fallback_shortlist_explanation(job_data, candidates)
    finally:
        db.close()


@router.get("/ai-hiring-recommendation/{job_id}", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def ai_hiring_recommendation(job_id: str, resume_id: str | None = Query(default=None)):
    db = SessionLocal()

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        query = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.is_active == True,
        )

        if resume_id:
            candidate = query.filter(Resume.id == resume_id).first()
        else:
            candidates = query.all()
            candidate = sorted(candidates, key=lambda row: row.final_score or 0, reverse=True)[0] if candidates else None

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        projects = _candidate_projects(candidate)
        if projects:
            db.commit()

        fallback = _fallback_ai_hiring_summary(job, candidate)
        if not client:
            return fallback

        prompt = f"""
Return ONLY valid JSON for an ATS hiring recommendation panel.

JSON shape:
{{
  "candidate_name": "candidate name",
  "verdict": "short recruiter verdict",
  "overall_summary": "5-7 sentence recruiter-ready candidate summary",
  "profile_summary": "candidate profile summary using resume evidence: role, skills, education, experience, projects/work examples",
  "jd_alignment": "specific comparison of JD requirements vs candidate evidence",
  "evidence": ["4-6 concrete evidence points from the resume and scoring fields"],
  "projects": ["1-5 project/work examples with tools/impact if present; do not invent"],
  "risks": ["2-5 gaps or validation points tied to JD requirements"],
  "next_steps": ["2-5 recruiter next actions"]
}}

Rules:
- Use the JD as the source of job requirements.
- Use only candidate data and resume text as evidence; do not invent projects, employers, tools, or years.
- Mention project/work evidence when present in the resume text.
- Be detailed and useful for a recruiter deciding whether to shortlist or call.
- If evidence is weak or score is low, say that clearly and explain what must be validated.
- Do not include markdown. Return JSON only.

JOB DATA
Title: {job.job_title}
Company: {job.company_name}
Required skills: {job.required_skills}
Experience required: {job.experience_required or job.min_experience_years}
Education requirement: {job.education}
JD:
{(job.jd_text or "")[:7000]}

CANDIDATE STRUCTURED DATA
Name: {candidate.full_name}
Email: {candidate.email}
Location: {candidate.location}
Designation: {candidate.designation}
Experience years: {candidate.total_experience_years}
Last company: {candidate.last_company_name}
Education: {candidate.education}
Industry: {candidate.industry}
Domain: {candidate.domain}
Skills: {candidate.key_skills}
Matched skills: {candidate.matched_skills}
Missing skills: {candidate.missing_skills}
Skill match percent: {candidate.skill_match_percent}
Final score: {candidate.final_score}
Skill score: {candidate.skill_score}
Experience score: {candidate.experience_score}
Confidence score: {candidate.confidence_score}
Resume quality score: {candidate.resume_quality_score}
Existing ranking reason: {candidate.ranking_reason}
Extracted projects JSON:
{json.dumps(projects, ensure_ascii=False)[:3500]}

FULL STORED RESUME TEXT
{(candidate.resume_text or "")[:12000]}
"""

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_RECOMMENDATION_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a senior ATS hiring analyst. Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        content = response.choices[0].message.content or ""
        summary = _normalize_ai_hiring_summary(_safe_json_from_ai(content), fallback)
        candidate.ranking_reason = summary.get("overall_summary") or candidate.ranking_reason
        db.commit()
        return summary

    except HTTPException:
        raise
    except Exception:
        logger.exception("AI hiring recommendation failed")
        if "job" in locals() and "candidate" in locals() and job and candidate:
            return _fallback_ai_hiring_summary(job, candidate)
        raise HTTPException(status_code=500, detail="AI hiring recommendation failed")
    finally:
        db.close()


def _candidate_email_body(name: str, job_title: str, company_name: str | None, hiring_manager: str | None) -> str:
    company = company_name or "our company"
    sender = hiring_manager or "Recruiting Team"
    fallback = (
        f"Hi {name or 'Candidate'},\n\n"
        f"Thank you for applying for the {job_title or 'open'} role at {company}. "
        "We reviewed your profile and would like to move you to the next step in our hiring process.\n\n"
        "Please reply to this email with one of the following options:\n"
        "1. Interested - if you would like to continue with the next round.\n"
        "2. Not Interested - if you do not want to proceed at this time.\n\n"
        "If you are interested, we will share the next steps and schedule details shortly.\n\n"
        f"Best regards,\n{sender}"
    )

    if not client:
        return fallback

    prompt = f"""
Write a short, professional recruiter outreach email.

Candidate: {name or 'Candidate'}
Role: {job_title or 'Open Role'}
Company: {company}
Sender: {sender}

The candidate has moved to the communication stage.
Ask the candidate to reply with either "Interested" or "Not Interested".
Keep it warm, concise, and clear.
"""
    try:
        ai_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,
        )
        return ai_res.choices[0].message.content or fallback
    except Exception:
        return fallback


def _mark_mail_sent(job_id: str | None, email: str, db):
    if not job_id or not email:
        return

    normalized = email.strip().lower()
    candidate = (
        db.query(Resume)
        .filter(Resume.job_id == job_id)
        .filter((Resume.email == normalized) | (Resume.form_email == normalized))
        .first()
    )

    if not candidate:
        candidate = (
            db.query(Resume)
            .filter(Resume.job_id == job_id)
            .filter((Resume.email == email) | (Resume.form_email == email))
            .first()
        )

    if candidate:
        candidate.mail_status = "Mail Sent"
        candidate.response_status = candidate.response_status or "Pending"
        candidate.status = "Communication"
        candidate.stage = "communication"
        db.commit()


def _refresh_google_token(user: User, db):
    if not user.google_refresh_token:
        return None

    if user.google_access_token and user.google_token_expires_at and user.google_token_expires_at > datetime.utcnow():
        if _google_token_has_assessment_scopes(user.google_access_token):
            return user.google_access_token
        return None

    res = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "refresh_token": user.google_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if res.status_code >= 300:
        return None

    token_data = res.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return None
    if not _google_token_has_assessment_scopes(access_token):
        return None

    user.google_access_token = access_token
    expires_in = int(token_data.get("expires_in") or 3600)
    user.google_token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
    db.commit()
    return access_token


def _find_outreach_google_user(db, sender_email: str) -> User | None:
    email = (sender_email or "").strip().lower()
    if not email:
        return None
    return (
        db.query(User)
        .filter((User.outreach_sender_email == email) | (User.email == email))
        .first()
    )


def _send_with_recruiter_gmail(recruiter_email: str, to_email: str, subject: str, body: str, db):
    if not recruiter_email:
        return None

    user = _find_outreach_google_user(db, recruiter_email)
    if not user:
        return None

    access_token = _refresh_google_token(user, db)
    if not access_token:
        return None

    sender_email = user.outreach_sender_email or user.email
    msg = MIMEText(body)
    msg["To"] = to_email
    msg["From"] = sender_email
    msg["Subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    res = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"raw": raw},
        timeout=20,
    )

    if res.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Gmail send failed: {res.text}")

    result = res.json()
    result["sender_email"] = sender_email
    return result


def _detect_candidate_response(text: str):
    normalized = (text or "").lower()
    if any(phrase in normalized for phrase in ["not interested", "not intrested", "not interested.", "no longer interested", "not proceed"]):
        return "Not Interested"
    if any(phrase in normalized for phrase in ["interested", "intrested", "i am interested", "yes interested"]):
        return "Interested"
    return None


def _sync_gmail_reply_for_candidate(user: User, candidate: Resume, access_token: str):
    candidate_email = (candidate.email or candidate.form_email or "").strip()
    if not candidate_email:
        return None

    query = f"from:{candidate_email} newer_than:30d"
    list_res = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "maxResults": 10},
        timeout=20,
    )

    if list_res.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Gmail reply sync failed: {list_res.text}")

    for message in list_res.json().get("messages", []):
        msg_res = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message['id']}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            timeout=20,
        )
        if msg_res.status_code >= 300:
            continue

        msg = msg_res.json()
        text = f"{msg.get('snippet', '')} {msg.get('payload', {}).get('headers', [])}"
        detected = _detect_candidate_response(text)
        if detected:
            return detected

    return None


def _assessment_question_count() -> int:
    try:
        value = int(os.getenv("ASSESSMENT_QUESTION_COUNT", "20"))
    except ValueError:
        return 20
    return 30 if value >= 30 else 20


def _assessment_duration_minutes() -> int:
    try:
        return max(10, min(int(os.getenv("ASSESSMENT_DURATION_MINUTES", "30")), 180))
    except ValueError:
        return 30


def _assessment_pass_percent() -> float:
    try:
        return max(0, min(float(os.getenv("ASSESSMENT_PASS_PERCENT", "60")), 100))
    except ValueError:
        return 60


def _fallback_assessment_questions(job: Job, question_count: int):
    skills = [skill.strip() for skill in (job.required_skills or "").split(",") if skill.strip()]
    if not skills:
        skills = ["role fundamentals", "problem solving", "communication", "practical judgment"]

    questions = []
    for index in range(question_count):
        skill = skills[index % len(skills)]
        questions.append(
            {
                "question": f"For the {job.job_title or 'open'} role, which option best demonstrates {skill} in a real work scenario?",
                "options": [
                    f"Apply {skill} with clear reasoning and measurable outcomes",
                    f"Mention {skill} without showing practical usage",
                    "Avoid validating the approach with stakeholders",
                    "Ignore the job requirements and use a generic solution",
                ],
                "answer": f"Apply {skill} with clear reasoning and measurable outcomes",
            }
        )
    return questions


def _generate_assessment_questions(job: Job, question_count: int):
    fallback = _fallback_assessment_questions(job, question_count)
    if not client:
        return fallback

    prompt = f"""
Create a job-specific candidate screening test from this job description.

Role: {job.job_title or job.role or 'Open Role'}
Required skills: {job.required_skills or 'Not specified'}
Experience: {job.experience_required or job.min_experience_years or 'Not specified'}
JD:
{(job.jd_text or '')[:5000]}

Return strict JSON only:
{{
  "questions": [
    {{
      "question": "clear multiple choice question",
      "options": ["A", "B", "C", "D"],
      "answer": "exact option text"
    }}
  ]
}}

Generate exactly {question_count} questions. Make them practical, role-relevant, and suitable for a 30 minute screening test.
"""
    try:
        ai_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.25,
        )
        raw = ai_res.choices[0].message.content or ""
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        questions = data.get("questions") if isinstance(data, dict) else None
        clean_questions = []
        for item in questions or []:
            options = item.get("options") if isinstance(item, dict) else None
            answer = item.get("answer") if isinstance(item, dict) else None
            question = item.get("question") if isinstance(item, dict) else None
            if question and isinstance(options, list) and len(options) >= 2 and answer in options:
                clean_questions.append(
                    {
                        "question": str(question)[:300],
                        "options": [str(option)[:160] for option in options[:4]],
                        "answer": str(answer)[:160],
                    }
                )
        return clean_questions[:question_count] if len(clean_questions) >= question_count else fallback
    except Exception:
        return fallback


def _create_google_quiz_form(user: User, assessment_title: str, questions: list[dict], duration_minutes: int, db):
    access_token = _refresh_google_token(user, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Connect Gmail/Google again and approve Gmail + Google Forms permissions. "
                "Your saved Google token does not include assessment permissions."
            ),
        )

    create_res = requests.post(
        "https://forms.googleapis.com/v1/forms",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"info": {"title": assessment_title, "documentTitle": assessment_title}},
        timeout=30,
    )
    if create_res.status_code >= 300:
        try:
            google_error = create_res.json().get("error", {})
            google_message = google_error.get("message") or create_res.text
        except Exception:
            google_message = create_res.text
        raise HTTPException(
            status_code=502,
            detail=(
                "Google Forms setup failed. Reconnect Google with Forms permission and "
                f"enable Google Forms API. Google response: {google_message[:300]}"
            ),
        )

    form = create_res.json()
    form_id = form.get("formId")
    if not form_id:
        raise HTTPException(status_code=502, detail="Google Forms did not return a form id.")

    requests_payload = [
        {
            "updateSettings": {
                "settings": {"quizSettings": {"isQuiz": True}},
                "updateMask": "quizSettings.isQuiz",
            }
        }
    ]
    requests_payload.append(
        {
            "createItem": {
                "item": {
                    "title": "Candidate email",
                    "description": "Use the same email address where you received this test invitation.",
                    "questionItem": {
                        "question": {
                            "required": True,
                            "textQuestion": {"paragraph": False},
                        }
                    },
                },
                "location": {"index": 0},
            }
        }
    )
    for index, item in enumerate(questions):
        requests_payload.append(
            {
                "createItem": {
                    "item": {
                        "title": item["question"],
                        "questionItem": {
                            "question": {
                                "required": True,
                                "grading": {
                                    "pointValue": 1,
                                    "correctAnswers": {"answers": [{"value": item["answer"]}]},
                                },
                                "choiceQuestion": {
                                    "type": "RADIO",
                                    "options": [{"value": option} for option in item["options"]],
                                    "shuffle": True,
                                },
                            }
                        },
                    },
                    "location": {"index": index + 1},
                }
            }
        )

    update_res = requests.post(
        f"https://forms.googleapis.com/v1/forms/{form_id}:batchUpdate",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "includeFormInResponse": False,
            "requests": requests_payload,
        },
        timeout=30,
    )
    if update_res.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Google Forms quiz update failed: {update_res.text}")

    return {
        "form_id": form_id,
        "form_url": f"https://docs.google.com/forms/d/{form_id}/viewform",
        "edit_url": f"https://docs.google.com/forms/d/{form_id}/edit",
    }


def _get_or_create_assessment(job: Job, recruiter: User, db):
    assessment = db.query(Assessment).filter(Assessment.job_id == job.id).first()
    if assessment:
        return assessment, False

    question_count = _assessment_question_count()
    duration_minutes = _assessment_duration_minutes()
    title = f"{job.job_title or job.role or 'Candidate'} Screening Test - {job.company_name or 'AI ATS'}"
    questions = _generate_assessment_questions(job, question_count)
    form_data = _create_google_quiz_form(recruiter, title, questions, duration_minutes, db)

    assessment = Assessment(
        job_id=job.id,
        title=title,
        question_count=question_count,
        duration_minutes=duration_minutes,
        questions_json=json.dumps(questions),
        google_form_id=form_data["form_id"],
        google_form_url=form_data["form_url"],
        google_form_edit_url=form_data["edit_url"],
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment, True


def _assessment_email_body(candidate: Resume, job: Job, assessment: Assessment):
    name = candidate.full_name or candidate.form_full_name or "Candidate"
    company = job.company_name or "our company"
    return (
        f"Hi {name},\n\n"
        f"Thank you for confirming your interest in the {job.job_title or job.role or 'open'} role at {company}.\n\n"
        f"Please complete this role-based screening test:\n{assessment.google_form_url}\n\n"
        f"Test details:\n"
        f"- Questions: {assessment.question_count}\n"
        f"- Time limit: {assessment.duration_minutes} minutes\n"
        "- Use the same email address that received this invitation.\n"
        "- Keep your camera/screen-proctoring setup ready if your organization uses a proctoring extension with Google Forms.\n\n"
        "Best regards,\nRecruiting Team"
    )


def _send_assessment_email(recruiter: User, candidate: Resume, job: Job, assessment: Assessment, db):
    to_email = (candidate.email or candidate.form_email or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="Candidate email is missing or invalid.")

    body = _assessment_email_body(candidate, job, assessment)
    subject = f"Screening test for {job.job_title or job.role or 'your application'}"
    gmail_result = _send_with_recruiter_gmail(recruiter.email, to_email, subject, body, db)
    if gmail_result:
        return gmail_result
    raise HTTPException(status_code=401, detail="Recruiter Gmail is not connected. Connect Gmail/Google before sending tests.")


def _parse_google_time(value: str | None):
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.utcnow()


def _extract_response_email(response: dict):
    email = (response.get("respondentEmail") or "").strip().lower()
    if email:
        return email

    for answer in (response.get("answers") or {}).values():
        text_answers = answer.get("textAnswers") or {}
        for item in text_answers.get("answers") or []:
            value = (item.get("value") or "").strip().lower()
            if "@" in value:
                return value
    return ""


def _sync_assessment_results_for_job(job_id: str, recruiter: User, db):
    access_token = _refresh_google_token(recruiter, db)
    if not access_token:
        raise HTTPException(status_code=401, detail="Connect Google again before syncing test results.")

    assessments = db.query(Assessment).filter(Assessment.job_id == job_id).all()
    updated = 0
    pass_percent = _assessment_pass_percent()

    for assessment in assessments:
        if not assessment.google_form_id:
            continue

        res = requests.get(
            f"https://forms.googleapis.com/v1/forms/{assessment.google_form_id}/responses",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if res.status_code >= 300:
            raise HTTPException(
                status_code=502,
                detail="Google Forms result sync failed. Reconnect Google with Forms response permission.",
            )

        for response in res.json().get("responses") or []:
            response_email = _extract_response_email(response)
            if not response_email:
                continue

            candidate_test = db.query(CandidateAssessment).filter(
                CandidateAssessment.assessment_id == assessment.id,
                CandidateAssessment.sent_to_email == response_email,
            ).first()
            if not candidate_test:
                candidate_test = db.query(CandidateAssessment).filter(
                    CandidateAssessment.assessment_id == assessment.id,
                    CandidateAssessment.sent_to_email.ilike(response_email),
                ).first()
            if not candidate_test:
                continue

            score = float(response.get("totalScore") or 0)
            max_score = float(assessment.question_count or 1)
            percentage = round((score / max_score) * 100, 2) if max_score else 0
            result_status = "Passed" if percentage >= pass_percent else "Needs Review"

            if candidate_test.response_id == response.get("responseId") and candidate_test.percentage == percentage:
                continue

            candidate_test.response_id = response.get("responseId")
            candidate_test.score = score
            candidate_test.max_score = max_score
            candidate_test.percentage = percentage
            candidate_test.result_status = result_status
            candidate_test.completed_at = _parse_google_time(response.get("lastSubmittedTime") or response.get("createTime"))
            candidate_test.status = "Test Done"
            if result_status == "Passed" and not candidate_test.interview_status:
                candidate_test.interview_status = "Ready"
            updated += 1

    db.commit()
    return updated


@router.post("/sync-gmail-responses", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def sync_gmail_responses(data: dict = Body(...)):
    job_id = data.get("job_id")
    recruiter_email = (data.get("recruiter_email") or "").strip().lower()

    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    if not recruiter_email:
        raise HTTPException(status_code=400, detail="recruiter_email is required")

    db = SessionLocal()
    try:
        user = _find_outreach_google_user(db, recruiter_email)
        if not user:
            raise HTTPException(status_code=404, detail="Recruiter account not found")

        access_token = _refresh_google_token(user, db)
        if not access_token:
            raise HTTPException(status_code=401, detail="Gmail is not connected. Connect Gmail for Outreach again.")

        candidates = db.query(Resume).filter(
            Resume.job_id == job_id,
            Resume.status == "Communication",
            Resume.is_active == True,
        ).all()

        updated = 0
        for candidate in candidates:
            detected = _sync_gmail_reply_for_candidate(user, candidate, access_token)
            if detected and candidate.response_status != detected:
                candidate.response_status = detected
                candidate.mail_status = candidate.mail_status or "Mail Sent"
                updated += 1

        db.commit()
        return {"message": "Gmail replies synced", "updated": updated}
    finally:
        db.close()


@router.post("/communication-response", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def update_communication_response(data: dict = Body(...)):
    candidate_id = data.get("candidate_id")
    response_status = (data.get("response_status") or "").strip()

    allowed_statuses = {
        "Interested": "Interested",
        "Not Interested": "Not Interested",
        "not_interested": "Not Interested",
    }

    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id is required")
    if response_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="response_status must be Interested or Not Interested")

    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(
            Resume.id == candidate_id,
            Resume.status == "Communication",
            Resume.is_active == True,
        ).first()

        if not candidate:
            raise HTTPException(status_code=404, detail="Communication candidate not found")

        candidate.response_status = allowed_statuses[response_status]
        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="communication_response_updated",
            title=f"Communication response: {candidate.response_status}",
            body=f"Recruiter marked candidate response as {candidate.response_status}.",
        )
        db.commit()
        db.refresh(candidate)

        return {
            "message": "Candidate response updated",
            "id": candidate.id,
            "response_status": candidate.response_status,
        }
    finally:
        db.close()


@router.post("/send-assessment-test", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def send_assessment_test(request: Request, data: dict = Body(...)):
    candidate_id = data.get("candidate_id")
    job_id = data.get("job_id")
    recruiter_email = (data.get("recruiter_email") or _email_from_request_token(request)).strip().lower()

    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id is required")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    if not recruiter_email:
        raise HTTPException(status_code=400, detail="recruiter_email is required")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id, Job.is_active == True).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        candidate = db.query(Resume).filter(
            Resume.id == candidate_id,
            Resume.job_id == job_id,
            Resume.status == "Communication",
            Resume.is_active == True,
        ).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Interested candidate not found")

        if (candidate.response_status or "").strip().lower() != "interested":
            raise HTTPException(status_code=400, detail="Test can be sent only after candidate is Interested")

        recruiter = _resolve_recruiter(request, db, recruiter_email)
        if not recruiter:
            raise HTTPException(status_code=404, detail="Recruiter account not found")

        assessment, created = _get_or_create_assessment(job, recruiter, db)
        existing_send = db.query(CandidateAssessment).filter(
            CandidateAssessment.candidate_id == candidate.id,
            CandidateAssessment.assessment_id == assessment.id,
        ).first()

        if existing_send:
            return {
                "message": "Test already sent to candidate",
                "assessment_created": created,
                "test_status": existing_send.status,
                "form_url": assessment.google_form_url,
                "edit_url": assessment.google_form_edit_url,
            }

        _send_assessment_email(recruiter, candidate, job, assessment, db)

        candidate_test = CandidateAssessment(
            job_id=job.id,
            candidate_id=candidate.id,
            assessment_id=assessment.id,
            sent_to_email=(candidate.email or candidate.form_email or "").strip().lower(),
            status="Test Sent",
        )
        db.add(candidate_test)
        db.commit()

        return {
            "message": "Test sent successfully",
            "assessment_created": created,
            "test_status": "Test Sent",
            "form_url": assessment.google_form_url,
            "edit_url": assessment.google_form_edit_url,
        }
    finally:
        db.close()


@router.post("/sync-assessment-results", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def sync_assessment_results(request: Request, data: dict = Body(...)):
    job_id = data.get("job_id")
    recruiter_email = (data.get("recruiter_email") or _email_from_request_token(request)).strip().lower()

    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    if not recruiter_email:
        raise HTTPException(status_code=400, detail="recruiter_email is required")

    db = SessionLocal()
    try:
        recruiter = _resolve_recruiter(request, db, recruiter_email)
        if not recruiter:
            raise HTTPException(status_code=404, detail="Recruiter account not found")

        updated = _sync_assessment_results_for_job(job_id, recruiter, db)
        return {"message": "Assessment results synced", "updated": updated}
    finally:
        db.close()


@router.post("/move-to-interview-scheduling", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def move_to_interview_scheduling(data: dict = Body(...)):
    candidate_id = data.get("candidate_id")
    job_id = data.get("job_id")

    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id is required")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(
            Resume.id == candidate_id,
            Resume.job_id == job_id,
            Resume.status == "Communication",
            Resume.is_active == True,
        ).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate_test = db.query(CandidateAssessment).filter(
            CandidateAssessment.candidate_id == candidate.id,
            CandidateAssessment.job_id == job_id,
            CandidateAssessment.status == "Test Done",
        ).order_by(CandidateAssessment.completed_at.desc()).first()
        if not candidate_test or candidate_test.percentage is None:
            raise HTTPException(status_code=400, detail="Candidate test result is not available yet")

        previous_stage = candidate.stage
        candidate.status = "Interview Scheduling"
        candidate.stage = "interview_scheduling"
        candidate_test.interview_status = "Interview Scheduling"
        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="candidate_moved_to_interview",
            title="Candidate moved to interview scheduling",
            from_stage=previous_stage,
            to_stage="interview_scheduling",
            reason="Assessment passed",
        )
        db.commit()

        return {"message": "Candidate moved to interview scheduling"}
    finally:
        db.close()


@router.get("/interview-dashboard", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def get_interview_dashboard():
    db = SessionLocal()
    try:
        rows = db.query(Resume, Job).join(
            Job,
            Resume.job_id == Job.id,
        ).filter(
            Resume.is_active == True,
            Resume.stage == "interview_scheduling",
        ).order_by(Resume.created_at.desc()).all()

        result = []
        for candidate, job in rows:
            candidate_test = db.query(CandidateAssessment).filter(
                CandidateAssessment.candidate_id == candidate.id,
                CandidateAssessment.job_id == candidate.job_id,
            ).order_by(CandidateAssessment.completed_at.desc(), CandidateAssessment.sent_at.desc()).first()
            interview = db.query(Interview).filter(
                Interview.candidate_id == candidate.id,
                Interview.job_id == candidate.job_id,
            ).order_by(Interview.created_at.desc()).first()
            interview_status = candidate_test.interview_status if candidate_test else candidate.status
            if interview:
                interview_status = "Scheduled" if (interview.status or "").lower() == "scheduled" else interview.status.title()
            result.append(
                {
                    "id": candidate.id,
                    "name": candidate.full_name or candidate.form_full_name,
                    "email": candidate.email or candidate.form_email,
                    "job_id": job.id if job else candidate.job_id,
                    "job_title": job.job_title if job else "",
                    "company_name": job.company_name if job else "",
                    "final_score": candidate.final_score or 0,
                    "test_score": candidate_test.score if candidate_test else None,
                    "test_max_score": candidate_test.max_score if candidate_test else None,
                    "test_percentage": candidate_test.percentage if candidate_test else None,
                    "test_result_status": candidate_test.result_status if candidate_test else None,
                    "interview_status": interview_status,
                    "scheduled_at": interview.scheduled_at.isoformat() if interview and interview.scheduled_at else None,
                    "duration_minutes": interview.duration_minutes if interview else None,
                    "meeting_url": interview.meeting_url if interview else None,
                    "interview_type": interview.interview_type if interview else "technical",
                    "status": candidate.status,
                }
            )

        return {"total": len(result), "candidates": result}
    finally:
        db.close()


@router.post("/schedule-interview-slot", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def schedule_interview_slot(data: dict = Body(...)):
    candidate_id = data.get("candidate_id")
    job_id = data.get("job_id")
    meeting_url = (data.get("meeting_url") or "").strip()
    scheduled_at_value = (data.get("scheduled_at") or "").strip()
    duration_minutes = int(data.get("duration_minutes") or 45)

    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id is required")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    if not meeting_url:
        raise HTTPException(status_code=400, detail="meeting_url is required")
    if not re.match(r"^https?://", meeting_url, re.I):
        raise HTTPException(status_code=400, detail="meeting_url must start with http:// or https://")

    scheduled_at = None
    if scheduled_at_value:
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            raise HTTPException(status_code=400, detail="scheduled_at is invalid")

    db = SessionLocal()
    try:
        candidate = db.query(Resume).filter(
            Resume.id == candidate_id,
            Resume.job_id == job_id,
            Resume.stage == "interview_scheduling",
            Resume.is_active == True,
        ).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Interview candidate not found")

        interview = db.query(Interview).filter(
            Interview.candidate_id == candidate.id,
            Interview.job_id == job_id,
            Interview.status == "scheduled",
        ).order_by(Interview.created_at.desc()).first()
        if not interview:
            interview = Interview(
                candidate_id=candidate.id,
                job_id=job_id,
                interview_type=data.get("interview_type") or "technical",
            )
            db.add(interview)

        interview.meeting_url = meeting_url
        interview.scheduled_at = scheduled_at
        interview.duration_minutes = duration_minutes
        interview.status = "scheduled"

        candidate_test = db.query(CandidateAssessment).filter(
            CandidateAssessment.candidate_id == candidate.id,
            CandidateAssessment.job_id == job_id,
        ).order_by(CandidateAssessment.completed_at.desc(), CandidateAssessment.sent_at.desc()).first()
        if candidate_test:
            candidate_test.interview_status = "Scheduled"

        candidate.status = "Interview Scheduled"
        _record_candidate_workflow_event(
            db,
            candidate,
            activity_type="interview_slot_scheduled",
            title="Interview slot scheduled",
            body=f"Meeting link added for {scheduled_at.isoformat() if scheduled_at else 'a pending time slot'}.",
        )
        db.commit()
        db.refresh(interview)
        return {
            "message": "Interview slot saved",
            "id": interview.id,
            "meeting_url": interview.meeting_url,
            "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else None,
            "status": "Scheduled",
        }
    finally:
        db.close()


@router.post("/send-mail", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def send_mail(data: dict = Body(...)):
    to_email = (data.get("email") or "").strip()
    name = data.get("name") or "Candidate"
    job_id = data.get("job_id")
    job_title = data.get("job_title") or "the role"
    company_name = data.get("company_name")
    hiring_manager = data.get("hiring_manager")
    recruiter_email = (data.get("recruiter_email") or "").strip()
    recruiter_name = data.get("recruiter_name") or hiring_manager

    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="Valid candidate email is required")

    email_body = _candidate_email_body(name, job_title, company_name, hiring_manager)
    subject = f"{job_title} - Next Step"

    resend_key = os.getenv("RESEND_API_KEY")
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("RESEND_FROM") or os.getenv("SMTP_FROM") or smtp_user
    reply_to = recruiter_email if "@" in recruiter_email else None

    if not resend_key and not (smtp_host and smtp_user and smtp_password and sender):
        if recruiter_email:
            db = SessionLocal()
            try:
                google_user = _find_outreach_google_user(db, recruiter_email)
                has_gmail_token = bool(google_user and (google_user.google_access_token or google_user.google_refresh_token))
            finally:
                db.close()
            if not has_gmail_token:
                raise HTTPException(
                    status_code=401,
                    detail="Recruiter Gmail is not connected. Sign in with Google again and approve Gmail send permission.",
                )
        else:
            raise HTTPException(
                status_code=500,
                detail="Email provider is not configured. Set RESEND_API_KEY and RESEND_FROM, SMTP credentials, or sign in with Google.",
            )

    try:
        db = SessionLocal()
        try:
            gmail_result = _send_with_recruiter_gmail(recruiter_email, to_email, subject, email_body, db)
            if gmail_result:
                _mark_mail_sent(job_id, to_email, db)
                return {
                    "message": "Mail sent",
                    "provider": "gmail",
                    "email": to_email,
                    "from": gmail_result.get("sender_email") or recruiter_email,
                    "reply_to": gmail_result.get("sender_email") or recruiter_email,
                    "recruiter_name": recruiter_name,
                    "gmail_message": gmail_result,
                    "ai_preview": email_body,
                }
        finally:
            db.close()

        if resend_key:
            res = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": sender or "onboarding@resend.dev",
                    "to": [to_email],
                    "subject": subject,
                    "html": f"<pre style='font-family:Arial,sans-serif;white-space:pre-wrap'>{email_body}</pre>",
                    **({"reply_to": reply_to} if reply_to else {}),
                },
                timeout=20,
            )
            if res.status_code >= 300:
                raise HTTPException(status_code=502, detail=f"Email provider failed: {res.text}")
            provider = "resend"
        else:
            msg = MIMEText(email_body)
            msg["Subject"] = subject
            smtp_from = recruiter_email if recruiter_email and smtp_user and recruiter_email.lower() == smtp_user.lower() else sender
            msg["From"] = smtp_from
            msg["To"] = to_email
            if reply_to and reply_to.lower() != (smtp_from or "").lower():
                msg["Reply-To"] = reply_to

            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            provider = "smtp"

        db = SessionLocal()
        try:
            _mark_mail_sent(job_id, to_email, db)
        finally:
            db.close()

        return {
            "message": "Mail sent",
            "provider": provider,
            "email": to_email,
            "from": sender,
            "reply_to": reply_to,
            "recruiter_name": recruiter_name,
            "ai_preview": email_body,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Mail failed: {str(e)}")


@router.post("/send-mail-legacy-smtp", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def send_mail_legacy_smtp(data: dict = Body(...)):

    to_email = data.get("email")
    name = data.get("name")
    job_title = data.get("job_title")

    # 🔥 AI PROMPT
    prompt = f"""
Write a professional HR email.

Candidate Name: {name}
Job Role: {job_title}

The candidate has been shortlisted for the next round.

Keep it short, professional, and friendly.
"""

    # 🔥 AI RESPONSE
    if client:
        ai_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        email_body = ai_res.choices[0].message.content
    else:
        email_body = f"Hi {name}, your profile has been shortlisted for the {job_title} role. Our recruiting team will contact you with the next steps."

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user

    if not (smtp_user and smtp_password and smtp_from):
        raise HTTPException(status_code=500, detail="SMTP credentials are not configured")

    msg = MIMEText(email_body)
    msg["Subject"] = f"{job_title} - Next Step"
    msg["From"] = smtp_from
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)

        server.send_message(msg)
        server.quit()

        return {
            "message": "AI Email sent",
            "preview": email_body
        }

    except Exception as e:
        return {"error": str(e)}

@router.post("/send-mail-legacy-preview", dependencies=LEGACY_RECRUITER_DEPENDENCIES)
def send_mail_legacy_preview(data: dict = Body(...)):

    to_email = data.get("email")
    name = data.get("name")
    job_title = data.get("job_title")

    # 🤖 AI EMAIL
    prompt = f"""
    Write a professional HR email.

    Candidate Name: {name}
    Job Role: {job_title}

    Candidate is shortlisted for next round.
    Keep it short and professional.
    """

    ai_res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    email_body = ai_res.choices[0].message.content

    # 🔥 RESEND
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        return {
            "message": "Mail preview generated",
            "ai_preview": email_body
        }

    res = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "from": "onboarding@resend.dev",
            "to": [to_email],
            "subject": f"{job_title} - Next Round",
            "html": f"<p>{email_body}</p>"
        }
    )

    return {
        "message": "Mail Sent",
        "ai_preview": email_body
    }
