import json
import logging
import os
from openai import OpenAI

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
_client = None

DEFAULT_RESUME_PARSE_MODEL = "gpt-4.1-mini"
DEFAULT_RESUME_REPAIR_MODEL = "gpt-5-mini"


def _get_openai_client():
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("OPENAI_API_KEY") or get_settings().openai_api_key
    if not api_key:
        return None

    _client = OpenAI(api_key=api_key)
    return _client


def _resume_parse_model():
    return os.getenv("OPENAI_RESUME_PARSE_MODEL", DEFAULT_RESUME_PARSE_MODEL)


def _resume_repair_model():
    return os.getenv(
        "OPENAI_RESUME_REPAIR_MODEL",
        os.getenv("OPENAI_RESUME_PARSE_MODEL", DEFAULT_RESUME_REPAIR_MODEL),
    )


# ---------------- BUILD PROMPT ----------------

def build_prompt(text):

    return f"""
    You are a professional ATS resume parsing engine.

    Your task is to extract structured information from the resume.

    STRICT RULES:

    1. Extract ONLY the candidate's actual full name.
    - Do NOT include certifications, titles, or degrees.
    - Remove anything after commas (e.g., PMP, MBA, PhD, etc).
    - Example:
      "Adelina Erimia, PMP, Six Sigma Green Belt" → "Adelina Erimia"

    2. Extract email, phone number, and location exactly as written.

    3. Extract ALL technical skills mentioned anywhere:
    - Skills section
    - Projects
    - Work experience
    - Certifications
    - Tools and technologies

    Examples of skills:
    Python, SQL, Power BI, Tableau, Excel, Pandas, NumPy, Machine Learning,
    Statistics, Data Visualization, TensorFlow, React, Java, AWS.

    4. Extract designation from the MOST RECENT job.

    5. Extract ALL work experience entries.

    6. Extract ALL education records.

    7. Extract ALL projects from the resume.
    - Include academic, personal, internship, freelance, dashboard, analytics, ML, web, automation, or portfolio projects.
    - Capture project name, description, technologies/tools, and outcome if present.
    - Do NOT invent projects. If none are present, return an empty list.

    8. Infer industry_category from company type.

    Examples:
    Hospital → Healthcare
    Bank / NBFC → FinTech
    Software company → Information Technology
    Ecommerce company → E-commerce
    Advertising company → AdTech

    9. Infer domain from job role.

    Examples:
    Data Analyst → Data Analytics
    Python Developer → Backend Development
    HR Executive → Human Resources
    UI Designer → Product Design
    Marketing Manager → Marketing

    IMPORTANT:
    - Always return clean and structured data.
    - Do NOT hallucinate missing information.
    - If something is not found, return null.

    Return STRICT JSON only.

    Structure:

    {{
    "full_name": string or null,
    "email": string or null,
    "phone": string or null,
    "location": string or null,
    "key_skills": list,
    "designation": string,
    "experience": [
    {{
    "company_name": string,
    "role": string,
    "start_date": "Month Year",
    "end_date": "Month Year or Present",
    "description": string
    }}
    ],
    "education": [
    {{
    "degree": string,
    "field": string,
    "institution": string,
    "start_date": string,
    "end_date": string
    }}
    ],
    "projects": [
    {{
    "name": string,
    "description": string,
    "technologies": list,
    "outcome": string
    }}
    ],
    "industry_category": string,
    "domain": string
    }}

    Resume Text:
    {text}
    """


def build_repair_prompt(text, previous_parse=None, issues=None):
    previous_json = json.dumps(previous_parse or {}, ensure_ascii=False)[:6000]
    issue_text = "\n".join(f"- {issue}" for issue in issues or []) or "- Parser output looked suspicious."

    return f"""
    You are repairing a failed ATS resume parse.

    The previous parse was flagged by validation. Fix ONLY the structured extraction.
    Do not invent missing data. If unsure, return null or an empty list.

    Validation issues:
    {issue_text}

    Critical repair rules:
    1. Candidate full_name must be a real person name only, not a section heading or title.
    2. company_name must be an actual employer only, not a paragraph, skill list, school, or project text.
    3. Work experience must include only paid/professional internships/jobs. Do not count education, bootcamp, Coursera, certificates, school, or college dates as work.
    4. Projects must include real project names only. Do not use section names like Education, Technical Skills, Contact, or Other Professional Experience.
    5. Preserve exact email and phone if found.
    6. Return STRICT JSON only using the same schema.

    Previous parse:
    {previous_json}

    Resume Text:
    {text}
    """


# ---------------- CLEAN GPT RESPONSE ----------------

def clean_response(content: str):

    content = content.strip()

    if content.startswith("```"):
        content = content.replace("```json", "")
        content = content.replace("```", "")

    return content.strip()


FIELD_GROUPS = {
    "identity": {"full_name", "email", "phone", "location"},
    "experience": {"designation", "experience", "industry_category", "domain"},
    "education": {"education"},
    "projects": {"projects"},
    "skills": {"key_skills"},
}


def build_prompt(text):
    return f"""
You are a production ATS resume parsing engine. Extract evidence-backed data only.
Return STRICT valid JSON only. No markdown, comments, prose, or trailing commas.

Rules:
1. Use only facts present in the resume text. Do not invent missing companies, dates, degrees, projects, or skills.
2. full_name is only the person's name. Exclude title, city, degree, certification, address, and section headings.
3. Prefer the first-page/header name. If the header is unclear, use LinkedIn/portfolio identity, then email local-part only when it clearly resembles a name. Never return "Unnamed Candidate".
4. Extract email and phone exactly as written in the resume text. Do not change letters or guess missing characters.
5. Clean icon prefixes from contact fields. Example: "/envelopejohn@gmail.com" becomes "john@gmail.com".
6. designation is the latest professional title, not a skill and not an old internship when a newer role exists.
7. Extract experience only from structured work headers such as:
   Company | Title | Date Range; Company - Title - Date Range; Title at Company, Date Range;
   Company, Location newline Title newline Date Range; Title | Company | Date Range.
8. Never use bullet sentences, responsibilities, project text, school names, bootcamps, certifications, or skill lists as company_name.
9. Never use locations as companies. Examples: Noida, Gurgaon, Gurugram, Bengaluru, London, Ontario, Remote, India, USA.
10. Never use technical terms, stacks, modules, or project names as companies. Examples: MVC, MERN, REST, API, React, Node, Express, MongoDB, GraphQL, AWS, Azure, CI/CD, FAM, client businesses.
11. In "Software Developer / Credin / Noida, Uttar Pradesh / Dec 2025 - Present", company_name is "Credin" and location is "Noida, Uttar Pradesh".
12. In "System Engineer, TCS ... Project Details: FAM", company_name is "TCS"; FAM is a project/module, not company_name.
13. Internships can be experience entries. Training/certification dates are not work experience.
14. Projects must be real projects only. Do not use section headings, work roles, education entries, or skill names as project names.
15. Capture project evidence when present, especially MERN/JWT/OAuth/RBAC/REST API/CRUD/deployment projects. Do not say no project proof when a project section has this evidence.
16. key_skills must be explicitly mentioned in skills, work, projects, tools, or certifications.
17. domain priority: current title, recent professional experience, repeated professional skills, projects, education.
    Old internships should not override current role. Salesforce CRM/tool usage is not Salesforce Developer domain unless Apex/LWC/SOQL/Flow/customization evidence appears.

Use null for unknown scalar fields and [] for unknown lists.

Return exactly this JSON shape:
{{
  "full_name": string|null,
  "email": string|null,
  "phone": string|null,
  "location": string|null,
  "key_skills": [string],
  "designation": string|null,
  "experience": [
    {{
      "company_name": string|null,
      "role": string|null,
      "start_date": string|null,
      "end_date": string|null,
      "description": string|null
    }}
  ],
  "education": [
    {{
      "degree": string|null,
      "field": string|null,
      "institution": string|null,
      "start_date": string|null,
      "end_date": string|null
    }}
  ],
  "projects": [
    {{
      "name": string|null,
      "description": string|null,
      "technologies": [string],
      "outcome": string|null
    }}
  ],
  "industry_category": string|null,
  "domain": string|null
}}

Resume Text:
{text}
"""


def _problem_fields_from_flags(flags_or_issues):
    fields = set()
    for item in flags_or_issues or []:
        code = item.get("code", "") if isinstance(item, dict) else ""
        message = item.get("message", "") if isinstance(item, dict) else str(item)
        text = f"{code} {message}".lower()
        if any(term in text for term in ["name", "email", "phone", "location"]):
            fields.update(FIELD_GROUPS["identity"])
        if any(term in text for term in ["company", "experience", "work", "designation", "seniority"]):
            fields.update(FIELD_GROUPS["experience"])
        if "education" in text:
            fields.update(FIELD_GROUPS["education"])
        if "project" in text:
            fields.update(FIELD_GROUPS["projects"])
        if "skill" in text:
            fields.update(FIELD_GROUPS["skills"])
    return sorted(fields or {"full_name", "email", "phone", "designation", "experience"})


def _resume_snippets_for_fields(text, fields):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    snippets = {"header_contact": "\n".join(lines[:35])}
    field_text = " ".join(fields).lower()
    section_names = []
    if any(item in field_text for item in ["experience", "designation", "company", "domain"]):
        section_names.extend(["experience", "work experience", "professional experience", "internship"])
    if "education" in field_text:
        section_names.extend(["education", "certification"])
    if "projects" in field_text:
        section_names.extend(["project", "projects"])
    if "key_skills" in field_text:
        section_names.extend(["skills", "technical skills", "tools"])

    for section in section_names:
        for index, line in enumerate(lines):
            if section in line.lower():
                snippets[section] = "\n".join(lines[index:index + 70])
                break
    return "\n\n".join(f"[{name}]\n{body}" for name, body in snippets.items() if body)[:9000]


def build_field_repair_prompt(text, previous_parse=None, validation_flags=None, fields=None):
    fields = fields or _problem_fields_from_flags(validation_flags)
    previous_json = json.dumps(previous_parse or {}, ensure_ascii=False)[:5000]
    issue_text = "\n".join(
        f"- {(item.get('code') + ': ') if isinstance(item, dict) and item.get('code') else ''}"
        f"{item.get('message') if isinstance(item, dict) else item}"
        for item in validation_flags or []
    ) or "- Validator found low-confidence fields."
    snippets = _resume_snippets_for_fields(text, fields)

    return f"""
You are verifying only low-confidence ATS parse fields.

Return STRICT JSON only. Return a PATCH object containing ONLY these fields:
{", ".join(fields)}

Do not re-parse the whole resume. Do not include fields outside the requested list.
Keep correct previous values only if supported by the resume snippets.
Use null or [] when the snippets do not prove a value.

Validation problems:
{issue_text}

Rules:
- company_name must be a real employer from a structured work header, never a bullet sentence.
- designation must be the latest professional title, not a skill.
- experience entries must have company_name, role, dates, and short evidence description when present.
- schools/bootcamps/certifications are education, not work experience, unless explicitly an employer.
- projects must be real project names, not headings or skills.
- Salesforce CRM/tool usage is not Salesforce Developer experience unless Apex/LWC/SOQL/Flow/customization evidence appears.

Previous parse:
{previous_json}

Resume snippets:
{snippets}
"""


def merge_parse_patch(previous_parse, patch, allowed_fields=None):
    if not isinstance(patch, dict):
        return previous_parse
    allowed = set(allowed_fields or patch.keys())
    merged = dict(previous_parse or {})
    for key, value in patch.items():
        if key in allowed:
            merged[key] = value
    return merged


# ---------------- PARSE RESUME ----------------

def parse_resume(text, retries=2):

    client = _get_openai_client()
    if not client:
        return None

    prompt = build_prompt(text)

    for _ in range(retries):

        try:

            response = client.chat.completions.create(
                model=_resume_parse_model(),
                messages=[
                    {"role": "system", "content": "Return strictly valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )

            content = clean_response(response.choices[0].message.content)

            return json.loads(content)

        except Exception:

            logger.exception("Resume parsing failed")

            prompt = f"""
Return ONLY valid JSON.

Resume Text:
{text}
"""

    return None


def repair_parse_resume(text, previous_parse=None, issues=None, retries=1):
    client = _get_openai_client()
    if not client:
        return None

    prompt = build_repair_prompt(text, previous_parse, issues)

    for _ in range(retries):
        try:
            response = client.chat.completions.create(
                model=_resume_repair_model(),
                messages=[
                    {"role": "system", "content": "Return strictly valid JSON only. Repair suspicious resume extraction."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            content = clean_response(response.choices[0].message.content)
            return json.loads(content)
        except Exception:
            logger.exception("Resume repair parsing failed")

    return None


def repair_parse_fields(text, previous_parse=None, validation_flags=None, retries=1):
    client = _get_openai_client()
    if not client:
        return None

    fields = _problem_fields_from_flags(validation_flags)
    prompt = build_field_repair_prompt(text, previous_parse, validation_flags, fields)

    for _ in range(retries):
        try:
            response = client.chat.completions.create(
                model=_resume_repair_model(),
                messages=[
                    {"role": "system", "content": "Return strictly valid JSON only. Produce only the requested patch fields."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            content = clean_response(response.choices[0].message.content)
            patch = json.loads(content)
            return merge_parse_patch(previous_parse, patch, fields)
        except Exception:
            logger.exception("Resume field repair failed")

    return None
