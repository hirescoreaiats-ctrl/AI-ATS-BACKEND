from __future__ import annotations

import json
import logging
import os
import re
from urllib.parse import urlencode

from openai import OpenAI
from sqlalchemy import or_

from backend.core.config import get_settings
from backend.models import Job


logger = logging.getLogger(__name__)
_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None


ALLOWED_APPLICATION_SOURCES = {
    "linkedin",
    "whatsapp",
    "naukri",
    "referral",
    "website",
    "direct",
    "folder",
    "unknown",
}

TRACKED_APPLICATION_SOURCES = [
    "linkedin",
    "whatsapp",
    "naukri",
    "referral",
    "website",
    "direct",
    "folder",
]


def normalize_application_source(source: str | None) -> str:
    value = (source or "").strip().lower()
    if not value:
        return "direct"
    if value in ALLOWED_APPLICATION_SOURCES:
        return value
    return "unknown"


def resolve_public_base_url() -> str:
    base_url = (
        os.getenv("APP_PUBLIC_BASE_URL")
        or os.getenv("BACKEND_PUBLIC_BASE_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or ""
    ).strip()

    if not base_url:
        settings = get_settings()
        base_url = (settings.frontend_url or "http://127.0.0.1:8000").strip()
        if "127.0.0.1:5500" in base_url or "localhost:5500" in base_url:
            base_url = "http://127.0.0.1:8000"

    return base_url.rstrip("/")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower())
    return slug.strip("-")


def generate_apply_slug(job: Job, db) -> str:
    title = slugify(job.job_title)
    company = slugify(job.company_name)
    job_tail = slugify((job.id or "")[:8])
    base_parts = [part for part in [title, company, job_tail] if part]
    base_slug = "-".join(base_parts) or slugify(job.id) or job.id

    candidate = base_slug
    suffix = 2
    while True:
        existing = (
            db.query(Job)
            .filter(Job.apply_slug == candidate, Job.id != job.id)
            .first()
        )
        if not existing:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def ensure_apply_slug(job: Job, db) -> str:
    if not getattr(job, "apply_slug", None):
        job.apply_slug = generate_apply_slug(job, db)
    return job.apply_slug or job.id


def resolve_job_identifier(identifier: str, db, active_only: bool = False) -> Job | None:
    query = db.query(Job).filter(or_(Job.id == identifier, Job.apply_slug == identifier))
    if active_only:
        query = query.filter(Job.is_active == True)
    return query.first()


def build_apply_links(job: Job, db=None) -> dict[str, str]:
    if db is not None:
        identifier = ensure_apply_slug(job, db)
    else:
        identifier = job.apply_slug or job.id

    main = f"{resolve_public_base_url()}/apply/{identifier}"
    links = {"main": main}
    for source in TRACKED_APPLICATION_SOURCES:
        links[source] = f"{main}?{urlencode({'source': source})}"
    return links


def _line(label: str, value: str | None) -> str:
    value = (value or "").strip()
    return f"{label}: {value}" if value else ""


def generate_linkedin_post(job: Job, apply_links: dict[str, str]) -> str:
    title = (job.job_title or "Open Role").strip()
    hashtag_title = re.sub(r"[^A-Za-z0-9]+", "", title) or "Jobs"
    location_parts = [part for part in [job.location, job.work_mode] if (part or "").strip()]

    lines = [
        f"Hiring: {title}",
        "",
        _line("Company", job.company_name),
        f"Location: {' / '.join(location_parts)}" if location_parts else "",
        _line("Experience", job.experience_required),
        _line("Salary", job.salary_range),
        _line("Skills", job.required_skills),
        "",
        "Apply here:",
        apply_links["linkedin"],
        "",
        f"#Hiring #{hashtag_title} #Jobs #Recruitment #CareerOpportunity",
    ]
    return "\n".join(line for line in lines if line != "").strip()


def generate_whatsapp_message(job: Job, apply_links: dict[str, str]) -> str:
    lines = [
        _line("Hiring", job.job_title),
        _line("Location", job.location),
        _line("Experience", job.experience_required),
        _line("Skills", job.required_skills),
        "",
        "Apply here:",
        apply_links["whatsapp"],
        "",
        "Please share with relevant candidates.",
    ]
    return "\n".join(line for line in lines if line != "").strip()


def generate_naukri_text(job: Job, apply_links: dict[str, str]) -> str:
    naukri_link = apply_links["naukri"]
    return (
        "Naukri External Apply URL:\n"
        f"{naukri_link}\n\n"
        "If your Naukri recruiter panel supports Company URL / External Apply URL / "
        "Apply URL / Redirect URL, paste the above link there.\n\n"
        "Fallback JD text:\n"
        "To apply directly, submit your resume here:\n"
        f"{naukri_link}"
    )


def _clean_ai_post(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"```(?:json)?|```", "", text, flags=re.I).strip()
    return text[:5000].strip() or fallback


def _fallback_generic_post(job: Job, apply_links: dict[str, str]) -> str:
    title = (job.job_title or "Open Role").strip()
    location_parts = [part for part in [job.location, job.work_mode] if (part or "").strip()]
    lines = [
        f"{title} - {job.company_name or 'Hiring Company'}",
        f"Location: {' / '.join(location_parts)}" if location_parts else "",
        _line("Experience", job.experience_required),
        _line("Employment Type", job.job_type),
        _line("Salary", job.salary_range),
        _line("Key Skills", job.required_skills),
        "",
        "Role Summary:",
        (job.jd_text or "Full job description available on request.")[:1200],
        "",
        "Apply here:",
        apply_links.get("website") or apply_links.get("direct") or apply_links.get("main") or "",
    ]
    return "\n".join(line for line in lines if line != "").strip()


def _fallback_ai_posts(job: Job, apply_links: dict[str, str]) -> dict[str, str]:
    return {
        "linkedin": generate_linkedin_post(job, apply_links),
        "whatsapp": generate_whatsapp_message(job, apply_links),
        "naukri": generate_naukri_text(job, apply_links),
        "generic": _fallback_generic_post(job, apply_links),
    }


def _json_from_ai_response(content: str) -> dict:
    text = (content or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    return {}


def generate_ai_sourcing_posts(job: Job, db=None) -> dict:
    links = build_apply_links(job, db)
    fallback = _fallback_ai_posts(job, links)
    if not _openai_client:
        return {"generated": False, "apply_links": links, "generated_posts": fallback}

    jd_text = (job.jd_text or "").strip()
    skills = (job.required_skills or "").strip()
    prompt_payload = {
        "job_title": job.job_title,
        "company": job.company_name,
        "department": job.department,
        "location": job.location,
        "work_mode": job.work_mode,
        "experience": job.experience_required,
        "salary": job.salary_range,
        "job_type": job.job_type,
        "skills": skills,
        "jd_text": jd_text[:3500],
        "apply_links": {
            "linkedin": links.get("linkedin"),
            "whatsapp": links.get("whatsapp"),
            "naukri": links.get("naukri"),
            "generic": links.get("website") or links.get("direct") or links.get("main"),
        },
    }
    system_prompt = (
        "You are an expert recruiter copywriter for Indian and global job platforms. "
        "Write accurate, attractive, recruiter-ready hiring posts. Do not invent benefits, salary, remote policy, "
        "requirements, or company facts that are not supplied. Keep apply links exactly as supplied."
    )
    user_prompt = (
        "Generate platform-specific job post copy as JSON only with keys: linkedin, whatsapp, naukri, generic.\n"
        "Rules:\n"
        "- linkedin: polished social post, engaging but professional, 120-180 words, clear CTA, 4-6 relevant hashtags.\n"
        "- whatsapp: short forwardable message, mobile friendly, concise bullets, include apply link.\n"
        "- naukri: formal job-board text. Start with 'External Apply URL:' and the Naukri link, then title, company, "
        "location, experience, skills, responsibilities/summary, and CTA.\n"
        "- generic: universal post for job boards/social platforms, clean sections, include generic apply link.\n"
        "- Use only supplied information. If a value is missing, omit that line instead of writing 'N/A'.\n"
        "- Return valid JSON only. No markdown fences.\n\n"
        f"Job data:\n{json.dumps(prompt_payload, ensure_ascii=False)}"
    )

    try:
        response = _openai_client.chat.completions.create(
            model=os.getenv("OPENAI_JOB_POST_MODEL", os.getenv("OPENAI_RECOMMENDATION_MODEL", "gpt-4o-mini")),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.55,
        )
        content = response.choices[0].message.content or ""
        parsed = _json_from_ai_response(content)
        posts = {
            "linkedin": _clean_ai_post(parsed.get("linkedin"), fallback["linkedin"]),
            "whatsapp": _clean_ai_post(parsed.get("whatsapp"), fallback["whatsapp"]),
            "naukri": _clean_ai_post(parsed.get("naukri"), fallback["naukri"]),
            "generic": _clean_ai_post(parsed.get("generic"), fallback["generic"]),
        }
        return {"generated": True, "apply_links": links, "generated_posts": posts}
    except Exception:
        logger.exception("AI sourcing post generation failed")
        return {"generated": False, "apply_links": links, "generated_posts": fallback}


def ensure_generated_sourcing_content(job: Job, db) -> dict[str, str]:
    links = build_apply_links(job, db)
    job.generated_linkedin_post = generate_linkedin_post(job, links)
    job.generated_whatsapp_message = generate_whatsapp_message(job, links)
    job.generated_naukri_text = generate_naukri_text(job, links)
    return links


def sourcing_payload(job: Job, db=None) -> dict:
    links = build_apply_links(job, db)
    return {
        "apply_slug": job.apply_slug or job.id,
        "apply_links": links,
        "generated_posts": {
            "linkedin": job.generated_linkedin_post or generate_linkedin_post(job, links),
            "whatsapp": job.generated_whatsapp_message or generate_whatsapp_message(job, links),
            "naukri": job.generated_naukri_text or generate_naukri_text(job, links),
        },
    }
