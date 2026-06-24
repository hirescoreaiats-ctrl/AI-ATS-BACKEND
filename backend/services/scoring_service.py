import re

from backend.services.semantic_service import cosine_similarity_cached
from backend.services.role_taxonomy import match_core_skill_groups
from backend.services.taxonomy import equivalent_skill, expand_skill_requirements, normalize_skill_list
from backend.services.recruiter_decision import enrich_recruiter_decision


def infer_seniority(title, years=0, experience_text=""):
    title_text = f"{title or ''}".lower()
    text = f"{title or ''} {experience_text or ''}".lower()

    if re.search(r"\b(architect|principal|head\s+of)\b", title_text):
        return "architect"
    if re.search(r"\b(manager|people management|hiring manager)\b", title_text):
        return "manager"
    if re.search(r"\b(team\s+lead|technical\s+lead|lead\s+(?:analyst|engineer|developer))\b", title_text):
        return "lead"
    if re.search(r"\bsenior\s+(?:data|business|bi|mis|credit|revenue|staff)?\s*(?:analyst|engineer|developer|manager|accountant|consultant|associate)\b", title_text) or years >= 6:
        return "senior"
    if years >= 2:
        return "mid-level"
    if any(word in text for word in ["intern", "trainee", "fresher"]):
        return "junior"
    return "junior" if years < 2 else "mid-level"


def _seniority_score(level):
    order = {
        "junior": 1,
        "mid-level": 2,
        "senior": 3,
        "lead": 4,
        "architect": 5,
        "manager": 5,
    }
    return order.get(level, 2)


def _split_skill_values(value):
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n|]+", value) if item.strip()]
    return list(value)


def _evidence_for_skill(skill, text):
    clean_text = re.sub(r"\s+", " ", text or "").strip()
    if not skill or not clean_text:
        return {"count": 0, "project": False, "experience": False, "certification": False, "recent": False, "depth": "missing", "snippet": ""}

    pattern = re.compile(r"\b" + re.escape(skill.lower()) + r"\b")
    lowered = clean_text.lower()
    matches = list(pattern.finditer(lowered))
    if not matches:
        return {"count": 0, "project": False, "experience": False, "recent": False, "snippet": ""}

    first = matches[0]
    start = max(0, first.start() - 90)
    end = min(len(clean_text), first.end() + 140)
    snippet = clean_text[start:end].strip(" ,.;:-")
    context = lowered[max(0, first.start() - 160): min(len(lowered), first.end() + 220)]

    project = bool(re.search(r"\b(project|built|developed|implemented|dashboard|model|system|api|automation)\b", context))
    experience = bool(re.search(r"\b(experience|worked|used|responsible|handled|managed|designed|delivered)\b", context))
    certification = bool(re.search(r"\b(certification|certificate|certified|course|training|bootcamp|coursera|udemy|datacamp)\b", context))
    if experience:
        depth = "work_experience_evidence"
    elif project:
        depth = "project_evidence"
    elif certification:
        depth = "certification_evidence"
    else:
        depth = "keyword_only"

    return {
        "count": len(matches),
        "project": project,
        "experience": experience,
        "certification": certification,
        "recent": bool(re.search(r"\b(202[3-9]|present|current|latest|recent)\b", context)),
        "depth": depth,
        "snippet": snippet[:260],
    }


def _skill_evidence_weight(evidence):
    depth = (evidence or {}).get("depth")
    level = (evidence or {}).get("evidence_level")
    if level:
        return {
            "professional_strong": 1.0,
            "professional_weak": 0.78,
            "project_strong": 0.76,
            "project_weak": 0.52,
            "skills_section_only": 0.36,
            "certification_or_training_only": 0.22,
            "keyword_only": 0.12,
            "employer_name_only": 0.0,
            "missing": 0.0,
        }.get(level, 0.0)
    if depth == "work_experience_evidence":
        return 1.0
    if depth == "project_evidence":
        return 0.85
    if depth == "certification_evidence":
        return 0.65
    if depth == "keyword_only":
        return 0.45
    return 0.0


def _skill_match(required, candidate_skills):
    direct = any(required.lower() == skill.lower() for skill in candidate_skills)
    equivalent = False if direct else any(equivalent_skill(skill, required) for skill in candidate_skills)
    return direct, equivalent


def _skill_pattern(skill):
    return re.compile(r"\b" + re.escape(str(skill or "").lower()).replace(r"\ ", r"\s+") + r"\b", re.I)


def _skill_in_text(skill, text):
    if not skill or not text:
        return False
    return bool(_skill_pattern(skill).search(str(text or "")))


def _skill_snippet(skill, text):
    if not skill or not text:
        return ""
    clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
    match = _skill_pattern(skill).search(clean_text)
    if not match:
        return ""
    return clean_text[max(0, match.start() - 80): min(len(clean_text), match.end() + 150)].strip(" ,.;:-")


def _strong_context(text):
    return bool(re.search(
        r"\b(built|developed|implemented|designed|automated|optimized|created|delivered|integrated|"
        r"configured|customized|handled|managed|analy[sz]ed|reported|deployed|owned|led|improved|reduced|increased|"
        r"\d+(?:%|k|,\d{3}| users?| records?| dashboards?| reports?))\b",
        str(text or ""),
        re.I,
    ))


def _training_context(text):
    return bool(re.search(r"\b(certification|certificate|certified|course|training|trailhead|coursera|udemy|bootcamp|virtual internship)\b", str(text or ""), re.I))


def _classify_skill_evidence(required, parsed, resume_text, candidate_skills=None, equivalent=False):
    parsed = parsed or {}
    candidate_skills = normalize_skill_list(candidate_skills or parsed.get("key_skills", []))
    direct_skill_list = any(required.lower() == skill.lower() for skill in candidate_skills)
    equivalent_skill_list = equivalent or any(equivalent_skill(skill, required) for skill in candidate_skills)

    company_texts = []
    work_texts = []
    for job in parsed.get("experience") or []:
        if not isinstance(job, dict):
            continue
        company = str(job.get("company_name") or job.get("company") or "")
        role = str(job.get("role") or "")
        description = str(job.get("description") or "")
        company_texts.append(company)
        work_texts.append(" ".join([role, description]))

    employer_hit = any(_skill_in_text(required, company) for company in company_texts)
    work_hits = [text for text in work_texts if _skill_in_text(required, text)]
    if work_hits:
        strongest = max(work_hits, key=lambda item: 1 if _strong_context(item) else 0)
        level = "professional_strong" if _strong_context(strongest) else "professional_weak"
        return {
            "skill": required,
            "status": "partial" if equivalent_skill_list and not direct_skill_list else "matched",
            "evidence_level": level,
            "depth": "work_experience_evidence",
            "evidence_text": _skill_snippet(required, strongest) or strongest[:260],
            "source": "work_experience",
            "weight": _skill_evidence_weight({"evidence_level": level}),
            "employer_name_only": False,
        }

    project_records = []
    for project in parsed.get("projects") or []:
        if not isinstance(project, dict):
            continue
        name = str(project.get("name") or project.get("title") or "")
        description = str(project.get("description") or project.get("summary") or "")
        technologies = " ".join(str(item) for item in project.get("technologies") or project.get("tools") or [])
        project_records.append((name, description, technologies))

    for name, description, technologies in project_records:
        if _skill_in_text(required, description):
            level = "project_strong" if _strong_context(description) else "project_weak"
            return {
                "skill": required,
                "status": "project_only",
                "evidence_level": level,
                "depth": "project_evidence",
                "evidence_text": _skill_snippet(required, description) or description[:260],
                "source": "project",
                "weight": _skill_evidence_weight({"evidence_level": level}),
                "employer_name_only": False,
            }
        if _skill_in_text(required, f"{name} {technologies}"):
            level = "project_weak"
            text = " ".join([name, technologies]).strip()
            return {
                "skill": required,
                "status": "project_only",
                "evidence_level": level,
                "depth": "project_evidence",
                "evidence_text": _skill_snippet(required, text) or text[:260],
                "source": "project",
                "weight": _skill_evidence_weight({"evidence_level": level}),
                "employer_name_only": False,
            }

    certifications = " ".join(str(item) for item in parsed.get("certifications") or [])
    education = " ".join(
        " ".join(str(value or "") for value in item.values()) if isinstance(item, dict) else str(item)
        for item in parsed.get("education") or []
    )
    training_text = " ".join([certifications, education])
    if _skill_in_text(required, training_text):
        return {
            "skill": required,
            "status": "training_only",
            "evidence_level": "certification_or_training_only",
            "depth": "certification_evidence",
            "evidence_text": _skill_snippet(required, training_text) or training_text[:260],
            "source": "certification_or_training",
            "weight": _skill_evidence_weight({"evidence_level": "certification_or_training_only"}),
            "employer_name_only": False,
        }

    if employer_hit and not _skill_in_text(required, " ".join(work_texts + [certifications, education])):
        return {
            "skill": required,
            "status": "weak",
            "evidence_level": "employer_name_only",
            "depth": "employer_name_only",
            "evidence_text": next((company for company in company_texts if _skill_in_text(required, company)), "")[:260],
            "source": "company_name",
            "weight": 0.0,
            "employer_name_only": True,
        }

    if direct_skill_list:
        return {
            "skill": required,
            "status": "weak",
            "evidence_level": "keyword_only",
            "depth": "keyword_only",
            "evidence_text": required,
            "source": "skills_section",
            "weight": _skill_evidence_weight({"evidence_level": "keyword_only"}),
            "employer_name_only": False,
        }

    if equivalent_skill_list:
        return {
            "skill": required,
            "status": "partial",
            "evidence_level": "keyword_only",
            "depth": "keyword_only",
            "evidence_text": required,
            "source": "skills_section_equivalent",
            "weight": min(0.12, _skill_evidence_weight({"evidence_level": "keyword_only"})),
            "employer_name_only": False,
        }

    if _skill_in_text(required, resume_text):
        context = _skill_snippet(required, resume_text)
        if _training_context(context):
            level = "certification_or_training_only"
            status = "training_only"
        else:
            level = "keyword_only"
            status = "weak"
        return {
            "skill": required,
            "status": status,
            "evidence_level": level,
            "depth": level,
            "evidence_text": context,
            "source": "resume_text",
            "weight": _skill_evidence_weight({"evidence_level": level}),
            "employer_name_only": False,
        }

    return {
        "skill": required,
        "status": "missing",
        "evidence_level": "missing",
        "depth": "missing",
        "evidence_text": "",
        "source": "",
        "weight": 0.0,
        "employer_name_only": False,
    }


def _resume_evidence_skill_match(required, resume_text):
    text = (resume_text or "").lower()
    skill = (required or "").lower()
    patterns = {
        "data cleaning": [
            r"\bcleaned?\s+(?:large\s+)?data\s*sets?\b",
            r"\bdata\s+preprocessing\b",
            r"\bdata\s+quality\b",
            r"\bremove(?:d)?\s+unwanted\s+characters\b",
            r"\bnormalize(?:d)?\s+(?:addresses|data)\b",
            r"\bdelete\s+extraneous\s+data\b",
        ],
        "data visualization": [
            r"\bdashboards?\b",
            r"\bcharts?\b",
            r"\bgraphs?\b",
            r"\bmaps?\b",
            r"\btableau\b",
            r"\bpower\s*bi\b",
        ],
        "power query": [
            r"\bpower\s+query\b",
            r"\betl\b",
            r"\bextract,\s*transform,\s*load\b",
            r"\bdata\s+transformation\b",
        ],
        "advanced excel": [
            r"\bpivot\s+tables?\b",
            r"\bvlookups?\b",
            r"\bxlookups?\b",
            r"\bmacros?\b",
            r"\bvba\b",
            r"\bformulas?\b",
            r"\bpower\s*pivot\b",
        ],
        "mis reporting": [
            r"\bad[-\s]?hoc\s+reports?\b",
            r"\bmonthly\s+reports?\b",
            r"\bweekly\s+reports?\b",
            r"\bfinancial\s+reports?\b",
            r"\bstakeholder\s+reports?\b",
            r"\breporting\b",
        ],
        "business reporting": [
            r"\bad[-\s]?hoc\s+reports?\b",
            r"\bfinancial\s+reports?\b",
            r"\bstakeholder\s+reports?\b",
            r"\breporting\b",
        ],
        "database design": [
            r"\bdatabase\s+(?:design|schema|schemas|model(?:ing)?)\b",
            r"\bsql\s+schemas?\b",
            r"\b(?:sql|postgres(?:ql)?|mysql|mongo(?:db)?)\s+(?:queries|schemas?|models?|collections?)\b",
            r"\bdata\s+model(?:ing)?\b",
            r"\boptimized?\s+(?:sql\s+)?queries\b",
            r"\bquery\s+optimization\b",
        ],
        "rest api": [
            r"\brest(?:ful)?\s+apis?\b",
            r"\bapis?\s+(?:development|endpoints?)\b",
            r"\b\d+\+?\s+rest\s+apis?\b",
        ],
        "crud": [
            r"\bcrud\b",
            r"\bcreate,\s*read,\s*update,\s*delete\b",
        ],
        "api integration": [
            r"\bapi\s+integration\b",
            r"\bintegrat(?:ed|ion)\s+(?:third[-\s]?party\s+)?apis?\b",
        ],
        "business logic": [
            r"\bbusiness\s+logic\b",
            r"\bserver[-\s]?side\s+(?:logic|applications?)\b",
        ],
        "authentication": [
            r"\bauth(?:entication)?\b",
            r"\blogin\b",
            r"\bsign[-\s]?in\b",
            r"\bjwt\b",
            r"\boauth\b",
            r"\bspring\s+security\b",
            r"\bfirebase\s+auth\b",
            r"\bbcrypt\b",
            r"\btoken(?:s)?\b",
        ],
        "authorization": [
            r"\bauthori[sz]ation\b",
            r"\brbac\b",
            r"\baccess\s+control\b",
            r"\bprotected\s+routes?\b",
        ],
        "spring security": [r"\bspring\s+security\b"],
        "token auth": [
            r"\btoken[-\s]?auth(?:entication)?\b",
            r"\baccess\s+tokens?\b",
            r"\brefresh\s+tokens?\b",
        ],
        "error handling": [
            r"\berror\s+handling\b",
            r"\bexception\s+handling\b",
        ],
        "validation": [r"\bvalidations?\b"],
        "logging": [r"\blogging\b|\blogs?\b"],
        "security": [r"\bsecure\b|\bsecurity\b|\bprotected\s+routes?\b"],
    }
    for key, skill_patterns in patterns.items():
        if key in skill and _has_any(skill_patterns, text):
            return True
    return False


def _education_cert_score(parsed, jd_data):
    education_required = str(jd_data.get("education") or "").lower()
    education_items = parsed.get("education") or []
    certifications = parsed.get("certifications") or []
    text = " ".join(
        [str(item.get("degree", "")) + " " + str(item.get("field", "")) if isinstance(item, dict) else str(item) for item in education_items]
        + [str(item) for item in certifications]
    ).lower()

    if not text:
        return 4

    score = 6
    if any(term in text for term in ["data", "analytics", "computer", "information technology", "statistics", "business analytics", "finance"]):
        score += 2
    if any(term in text for term in ["power bi", "sql", "datacamp", "business analytics", "data science", "certificate", "certification"]):
        score += 2

    if "master" in education_required and any(term in text for term in ["master", "m.sc", "msc", "mtech", "m.tech", "mba"]):
        score = max(score, 9)
    elif "bachelor" in education_required and any(term in text for term in ["bachelor", "b.tech", "btech", "bca", "b.s", "bsba", "be"]):
        score = max(score, 8)

    return min(10, score)


def _append_unique(items, values):
    seen = {str(item).lower() for item in items}

    for value in values:
        key = str(value).lower()
        if value and key not in seen:
            items.append(value)
            seen.add(key)


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _has_any(patterns, text):
    return any(re.search(pattern, text or "", re.I) for pattern in patterns)


QA_TARGET_FAMILIES = {"qa_automation", "manual_qa"}
BUSINESS_ANALYST_TARGET_FAMILIES = {"business_analyst", "business_analysis"}

QA_DIRECT_TITLE_RE = re.compile(
    r"\b("
    r"qa|sqa|sdet|quality\s+assurance|quality\s+engineer|digital\s+quality\s+assurance|"
    r"test\s+automation|automation\s+(?:test|testing|qa)|software\s+testing|"
    r"manual\s+test(?:er|ing)|qa\s+automation"
    r")\b",
    re.I,
)

QA_ADJACENT_TITLE_RE = re.compile(r"\b(test(?:er|ing)?|quality|automation)\b", re.I)

SOFTWARE_DEV_TITLE_RE = re.compile(
    r"\b("
    r"full[-\s]?stack|front[-\s]?end|back[-\s]?end|software|java|python|web|mern|mean|"
    r"react|node(?:\.js)?|developer|programmer"
    r")\b",
    re.I,
)

BUSINESS_ANALYST_DIRECT_TITLE_RE = re.compile(
    r"\b(?:business\s+analyst|functional\s+analyst|it\s+business\s+analyst|"
    r"business\s+systems\s+analyst|requirements?\s+analyst)\b",
    re.I,
)

BUSINESS_ANALYST_ADJACENT_TITLE_RE = re.compile(
    r"\b(?:data|bi|mis|reporting|product|project|operations?)\s+"
    r"(?:analyst|associate|specialist|coordinator|manager)\b",
    re.I,
)

BA_CRITICAL_GROUPS = {
    "requirements_gathering",
    "requirements_documentation",
    "stakeholder_coordination",
    "functional_analysis",
    "uat_change_management",
    "process_workflow",
}


def _is_qa_target(jd_profile):
    family = (jd_profile.get("role_family") or "").lower()
    role_title = jd_profile.get("role_title") or ""
    return family in QA_TARGET_FAMILIES or bool(QA_DIRECT_TITLE_RE.search(role_title))


def _is_business_analyst_target(jd_profile):
    family = (jd_profile.get("role_family") or "").lower()
    role_title = jd_profile.get("role_title") or ""
    return family in BUSINESS_ANALYST_TARGET_FAMILIES or bool(BUSINESS_ANALYST_DIRECT_TITLE_RE.search(role_title))


def _latest_experience_role(parsed):
    for job in parsed.get("experience") or []:
        if isinstance(job, dict) and (job.get("is_current") or str(job.get("end_date") or "").lower() in {"present", "current"}):
            return str(job.get("role") or "")
    for job in parsed.get("experience") or []:
        if isinstance(job, dict) and job.get("role"):
            return str(job.get("role") or "")
    return ""


def _qa_group_evidence_strength(core_skill_groups, skill_evidence):
    levels_by_group = {}
    for group, options in (core_skill_groups or {}).items():
        levels = []
        for option in normalize_skill_list(options or []):
            evidence = skill_evidence.get(option) or {}
            level = evidence.get("evidence_level")
            if not level:
                continue
            levels.append(level)
        if levels:
            levels_by_group[group] = levels

    professional = [
        group for group, levels in levels_by_group.items()
        if any(level in {"professional_strong", "professional_weak"} for level in levels)
    ]
    project = [
        group for group, levels in levels_by_group.items()
        if group not in professional and any(level in {"project_strong", "project_weak"} for level in levels)
    ]
    keyword_only = [
        group for group, levels in levels_by_group.items()
        if group not in professional
        and group not in project
        and any(level in {"keyword_only", "skills_section_only"} for level in levels)
    ]
    training_only = [
        group for group, levels in levels_by_group.items()
        if group not in professional
        and group not in project
        and group not in keyword_only
        and any(level == "certification_or_training_only" for level in levels)
    ]
    return {
        "professional_groups": professional,
        "project_groups": project,
        "keyword_only_groups": keyword_only,
        "training_only_groups": training_only,
        "professional_group_count": len(professional),
        "project_group_count": len(project),
        "keyword_only_group_count": len(keyword_only),
        "training_only_group_count": len(training_only),
    }


def _qa_role_identity(parsed, mandatory_coverage, professional_group_count):
    primary_title = str(parsed.get("current_title") or parsed.get("designation") or "").strip()
    latest_role = _latest_experience_role(parsed)
    title_text = " ".join([primary_title, latest_role]).strip()
    direct_years = _safe_float(parsed.get("direct_relevant_experience_years"))
    relevant_years = _safe_float(parsed.get("relevant_experience_years"))
    evidence = parsed.get("experience_evidence") or []
    direct_blocks = [
        item for item in evidence
        if isinstance(item, dict) and item.get("label") in {"direct", "partial_match", "direct_match", "partial"}
    ]

    primary_is_qa = bool(QA_DIRECT_TITLE_RE.search(primary_title))
    latest_is_qa = bool(QA_DIRECT_TITLE_RE.search(latest_role))
    primary_is_dev = bool(SOFTWARE_DEV_TITLE_RE.search(primary_title)) and not primary_is_qa

    if primary_is_qa or latest_is_qa:
        alignment = "direct"
        reason = "Current or latest title is in the QA/testing role family."
        family = "qa_automation"
    elif primary_is_dev and (direct_years >= 1 or direct_blocks):
        alignment = "adjacent"
        reason = "Primary title is software development, with some QA-relevant work evidence."
        family = "software_engineering"
    elif direct_years > 0 or relevant_years >= 1 or mandatory_coverage >= 55:
        alignment = "transferable"
        reason = "Resume has transferable QA skills, but the primary role is not QA."
        family = "transferable"
    elif QA_ADJACENT_TITLE_RE.search(title_text) or professional_group_count:
        alignment = "weak"
        reason = "Some testing signal exists, but role identity is weak."
        family = "weak_qa_signal"
    else:
        alignment = "mismatch"
        reason = "No reliable QA role identity was found."
        family = "non_qa"

    return {
        "role_alignment": alignment,
        "primary_role_family": family,
        "primary_role_label": primary_title or latest_role,
        "latest_role_label": latest_role,
        "primary_is_developer": primary_is_dev,
        "role_alignment_reason": reason,
        "direct_qa_evidence_blocks": len(direct_blocks),
    }


def _generic_role_identity(parsed, jd_profile, mandatory_coverage, role_relevance, evidence_strength):
    primary_title = str(parsed.get("current_title") or parsed.get("designation") or "").strip()
    latest_role = _latest_experience_role(parsed)
    title_text = f"{primary_title} {latest_role}".lower()
    role_title = str(jd_profile.get("role_title") or "").lower()
    title_tokens = {
        token for token in re.findall(r"[a-z][a-z0-9+#.]{2,}", role_title)
        if token not in {"engineer", "developer", "executive", "associate", "manager", "role"}
    }
    token_hits = [token for token in title_tokens if re.search(r"\b" + re.escape(token) + r"\b", title_text, re.I)]
    primary_family = parsed.get("role_family") or parsed.get("domain") or "unknown"
    direct_years = _safe_float(parsed.get("direct_relevant_experience_years"))
    relevant_years = _safe_float(parsed.get("relevant_experience_years"))

    if token_hits and (role_relevance >= 65 or direct_years >= 1):
        alignment = "direct"
        reason = "Candidate title and work evidence match the JD role family."
    elif role_relevance >= 60 and evidence_strength >= 45:
        alignment = "adjacent"
        reason = "Candidate has related professional evidence for this JD."
    elif relevant_years >= 1 or mandatory_coverage >= 55:
        alignment = "transferable"
        reason = "Candidate has some transferable JD evidence but not a direct role identity."
    elif mandatory_coverage >= 30 or role_relevance >= 30:
        alignment = "weak"
        reason = "Candidate has weak or mostly keyword-based JD overlap."
    else:
        alignment = "mismatch"
        reason = "Candidate profile does not align with this JD."

    return {
        "role_alignment": alignment,
        "primary_role_family": primary_family,
        "primary_role_label": primary_title or latest_role,
        "latest_role_label": latest_role,
        "primary_is_developer": bool(SOFTWARE_DEV_TITLE_RE.search(primary_title)),
        "role_alignment_reason": reason,
        "role_alignment_confidence": round(min(100, max(role_relevance, mandatory_coverage, evidence_strength)), 2),
    }


def _attach_jd_profile_metadata(score_data, jd_profile, parsed=None, role_identity=None):
    score_data = score_data or {}
    jd_profile = jd_profile or {}
    parsed = parsed or {}
    score_data.setdefault("jd_profile_version", jd_profile.get("jd_profile_version"))
    score_data.setdefault("scoring_mode", jd_profile.get("scoring_mode") or "legacy")
    score_data.setdefault("dynamic_profile_used", bool(jd_profile.get("dynamic_profile_used")))
    score_data.setdefault("known_template_used", bool(jd_profile.get("known_template_used")))
    score_data.setdefault("detected_role_family", jd_profile.get("detected_role_family") or jd_profile.get("role_family"))
    score_data.setdefault("normalized_role_label", jd_profile.get("normalized_role_label") or jd_profile.get("role_title") or "")
    score_data.setdefault("profile_confidence", jd_profile.get("profile_confidence"))
    score_data.setdefault("profile_warnings", jd_profile.get("profile_warnings") or [])
    score_data.setdefault("final_score_after_caps", score_data.get("final_score"))
    score_data.setdefault("applied_caps", score_data.get("score_caps_applied") or [])
    score_data.setdefault("applied_boosts", score_data.get("score_boosts_applied") or [])
    score_data.setdefault("total_professional_experience_years", parsed.get("total_experience_years"))
    score_data.setdefault("jd_relevant_experience_years", parsed.get("relevant_experience_years"))
    score_data.setdefault("direct_role_experience_years", parsed.get("direct_relevant_experience_years"))
    score_data.setdefault("adjacent_role_experience_years", parsed.get("transferable_experience_years"))
    total = _safe_float(parsed.get("total_experience_years"))
    relevant = _safe_float(parsed.get("relevant_experience_years"))
    score_data.setdefault("unrelated_experience_years", round(max(0, total - relevant), 2))
    score_data.setdefault("experience_confidence", parsed.get("role_relevance_score"))
    if role_identity:
        score_data.setdefault("primary_role_label", role_identity.get("primary_role_label"))
        score_data.setdefault("primary_role_family", role_identity.get("primary_role_family"))
        score_data.setdefault("role_alignment", role_identity.get("role_alignment"))
        score_data.setdefault("role_alignment_reason", role_identity.get("role_alignment_reason"))
        score_data.setdefault("role_alignment_confidence", role_identity.get("role_alignment_confidence"))
    breakdown = score_data.setdefault("scoring_breakdown", {})
    if isinstance(breakdown, dict):
        breakdown.update({
            "jd_profile_version": score_data.get("jd_profile_version"),
            "scoring_mode": score_data.get("scoring_mode"),
            "dynamic_profile_used": score_data.get("dynamic_profile_used"),
            "known_template_used": score_data.get("known_template_used"),
            "detected_role_family": score_data.get("detected_role_family"),
            "profile_confidence": score_data.get("profile_confidence"),
            "profile_warnings": score_data.get("profile_warnings"),
            "final_score_after_caps": score_data.get("final_score_after_caps"),
            "applied_caps": score_data.get("applied_caps"),
            "applied_boosts": score_data.get("applied_boosts"),
            "role_alignment": score_data.get("role_alignment"),
            "role_alignment_reason": score_data.get("role_alignment_reason"),
        })
    return enrich_recruiter_decision(score_data, jd_profile, parsed)


def _is_data_analyst_jd(jd_text, jd_data, required_skills):
    text = " ".join([
        str(jd_data.get("role") or ""),
        str(jd_data.get("job_title") or ""),
        str(jd_text or ""),
        " ".join(str(item) for item in required_skills or []),
    ]).lower()
    return bool(
        re.search(r"\b(data|mis|business|bi)\s+analyst\b", text)
        or ("power bi" in text and "sql" in text)
        or ("mis reporting" in text and "excel" in text)
    )


def _is_salesforce_jd(jd_text, jd_data, required_skills):
    text = " ".join([
        str(jd_data.get("role") or ""),
        str(jd_data.get("job_title") or ""),
        str(jd_text or ""),
        " ".join(str(item) for item in required_skills or []),
    ]).lower()
    return bool("salesforce" in text or re.search(r"\b(apex|lwc|visualforce|soql|sosl|sales cloud|service cloud|cpq)\b", text))


def _salesforce_core_evidence(matched_skills, resume_text):
    combined = " ".join((matched_skills or []) + [resume_text or ""]).lower()
    return {
        "apex": bool(re.search(r"\bapex\b|\bapex\s+triggers?\b|\bapex\s+classes?\b", combined)),
        "ui": bool(re.search(r"\blwc\b|\blightning\s+web\s+components?\b|\baura\b|\bvisualforce\b", combined)),
        "soql": bool(re.search(r"\bsoql\b", combined)),
    }


def _has_direct_data_role_title(title):
    return bool(re.search(
        r"\b(?:data|business|bi|mis|reporting|analytics?|power\s*bi)\s+"
        r"(?:analyst|specialist|developer|consultant|associate)\b",
        str(title or ""),
        re.I,
    ))


def detect_core_skill_evidence(resume_text, matched_skills=None, candidate_skills=None):
    text = (resume_text or "").lower()
    skill_text = " ".join((matched_skills or []) + (candidate_skills or [])).lower()
    combined = f"{text} {skill_text}"

    evidence = {
        "sql": _has_any([r"\bsql\b", r"\bmysql\b", r"\bpostgres(?:ql)?\b", r"\bsql\s*server\b"], combined),
        "advanced_excel": _has_any([
            r"\badvanced\s+excel\b",
            r"\bexcel\b.*\b(pivot|vlookup|xlookup|lookup|formula|power\s*pivot|macros?)\b",
            r"\b(pivot|vlookup|xlookup|lookup|formula|power\s*pivot|macros?)\b.*\bexcel\b",
        ], combined),
        "excel": _has_any([r"\b(?:ms|microsoft)?\s*excel\b"], combined),
        "power_bi": _has_any([r"\bpower\s*bi\b", r"\bpowerbi\b"], combined),
        "power_query_or_etl": _has_any([r"\bpower\s+query\b", r"\betl\b", r"\bdata\s+pipeline\b", r"\btransform(?:ed|ation|ing)?\b"], combined),
        "dax": _has_any([r"\bdax\b"], combined),
        "mis_or_business_reporting": _has_any([
            r"\bmis\b",
            r"\bbusiness\s+report(?:ing|s)?\b",
            r"\bmanagement\s+report(?:ing|s)?\b",
            r"\bmonthly\s+reports?\b",
            r"\bdaily\s+reports?\b",
        ], combined),
        "kpi_or_dashboard_reporting": _has_any([
            r"\bkpis?\b",
            r"\bdashboard(?:s|ing)?\b",
            r"\breport\s+automation\b",
            r"\bautomated\s+reports?\b",
            r"\bautomation\b.*\breport",
        ], combined),
    }
    evidence["advanced_excel_or_excel"] = evidence["advanced_excel"] or evidence["excel"]
    return evidence


def calculate_experience_fit(parsed, jd_data, is_data_analyst=False):
    years = _safe_float(parsed.get("total_experience_years"))
    relevant_years = _safe_float(parsed.get("relevant_experience_years"), years)
    jd_min = _safe_float(jd_data.get("min_experience_years"))
    jd_max = _safe_float(jd_data.get("max_experience_years"))
    direct_role_signal = _safe_float(parsed.get("direct_relevant_experience_years")) >= 1 or (
        _has_direct_data_role_title(parsed.get("designation")) and relevant_years >= max(jd_min or 0, 1)
    )
    transition_candidate = is_data_analyst and (bool(parsed.get("transition_candidate")) or (
        years > max(jd_max or 0, 3)
        and relevant_years <= max(jd_max or 0, jd_min or 0, 1) + 1
        and not direct_role_signal
    ))

    fit = {
        "label": "unknown",
        "acceptable": True,
        "under_experienced": False,
        "overqualified": False,
        "strong_overqualified": False,
        "years": years,
        "relevant_years": relevant_years,
        "jd_min": jd_min or None,
        "jd_max": jd_max or None,
        "transition_candidate": transition_candidate,
    }

    if not jd_min and not jd_max:
        return fit

    comparison_years = relevant_years
    if jd_min and comparison_years < jd_min:
        fit["label"] = "under_experienced"
        fit["under_experienced"] = True
        fit["acceptable"] = comparison_years >= max(0, jd_min - 1)
        return fit

    if jd_max and years > jd_max and relevant_years <= jd_max and transition_candidate:
        fit["label"] = "transition_review"
        fit["acceptable"] = True
        return fit

    if jd_max and relevant_years > jd_max:
        over_by = relevant_years - jd_max
        if (jd_max <= 3 and relevant_years >= 10) or over_by >= 7:
            fit["label"] = "strong_overqualified"
            fit["strong_overqualified"] = True
            fit["overqualified"] = True
            fit["acceptable"] = False
        elif (jd_max <= 3 and relevant_years >= 7) or over_by >= 4:
            fit["label"] = "overqualified_review"
            fit["overqualified"] = True
            fit["acceptable"] = False
        else:
            fit["label"] = "slightly_over_range"
            fit["acceptable"] = True
        return fit

    fit["label"] = "best_fit"
    return fit


def detect_project_strength(parsed, resume_text):
    project_parts = []
    for project in parsed.get("projects") or []:
        if isinstance(project, dict):
            project_parts.append(" ".join([
                str(project.get("name") or ""),
                str(project.get("description") or ""),
                " ".join(str(item) for item in project.get("technologies") or []),
            ]))
        else:
            project_parts.append(str(project))

    text = " ".join(project_parts + [resume_text or ""]).lower()
    has_project_context = bool(project_parts) or _has_any([r"\bprojects?\b", r"\bbuilt\b", r"\bdeveloped\b", r"\bcreated\b"], text)
    points = 0.0

    signals = [
        (r"\bpower\s*bi\b.*\bdashboard|\bdashboard.*\bpower\s*bi\b", 2.0),
        (r"\bsql\b|\bmysql\b|\bpostgres(?:ql)?\b|\bsql\s*server\b", 1.5),
        (r"\bpower\s+query\b", 1.5),
        (r"\bdax\b", 1.5),
        (r"\badvanced\s+excel\b|\bpivot\s+tables?\b|\bexcel\b", 1.25),
        (r"\betl\b|\bdata\s+pipeline\b|\btransform(?:ed|ation|ing)?\b", 1.5),
        (r"\bkpis?\b|\bkpi\s+dashboard\b|\breport(?:ing)?\s+automation\b", 1.5),
        (r"\bsales\b|\bretail\b|\bfinance\b|\bcrm\b|\berp\b|\bbusiness\s+data\b|\boperations?\b", 1.0),
        (r"\bdata\s+clean(?:ing)?\b|\bdata\s+validat(?:ion|e|ing)\b|\bdata\s+transformation\b", 1.25),
        (r"\b\d{2,}(?:k|,\d{3})?\s+(?:rows|records|transactions)\b|\blarge\s+dataset\b", 1.0),
        (r"\binsights?\b|\brecommendations?\b|\bdecision[-\s]?making\b", 1.0),
    ]
    for pattern, weight in signals:
        if re.search(pattern, text, re.I):
            points += weight

    return {
        "score": round(points, 2),
        "strong": has_project_context and points >= 6,
        "moderate": has_project_context and points >= 3.5,
    }


def apply_score_caps(score_data, core_evidence, experience_fit, project_strength, is_data_analyst):
    final_score = _safe_float(score_data.get("final_score"))
    flags = []
    reasons = []
    caps = []

    all_critical = all([
        core_evidence["sql"],
        core_evidence["advanced_excel_or_excel"],
        core_evidence["power_bi"],
        core_evidence["power_query_or_etl"],
        core_evidence["dax"],
        core_evidence["mis_or_business_reporting"],
        core_evidence["kpi_or_dashboard_reporting"],
        experience_fit["label"] in {"best_fit", "slightly_over_range"} or (
            experience_fit["under_experienced"] and project_strength["strong"]
        ),
    ])

    basic_trio = core_evidence["sql"] and core_evidence["advanced_excel_or_excel"] and core_evidence["power_bi"]
    missing_deeper_core = not all([
        core_evidence["power_query_or_etl"],
        core_evidence["dax"],
        core_evidence["mis_or_business_reporting"],
        core_evidence["kpi_or_dashboard_reporting"],
    ])

    if is_data_analyst and final_score > 94:
        caps.append((94, "Score capped at the recruiter-calibrated ceiling for Data Analyst roles."))
    if is_data_analyst and final_score >= 95 and not all_critical:
        caps.append((94, "Score capped below 95 because not every critical JD requirement has measurable evidence."))
    if is_data_analyst and basic_trio and missing_deeper_core:
        caps.append((89, "Score capped because SQL/Excel/Power BI are present but DAX, Power Query, MIS, or KPI evidence is incomplete."))
    if is_data_analyst and experience_fit["label"] == "slightly_over_range" and missing_deeper_core:
        caps.append((82, "Score capped because the candidate is slightly above the range and still needs validation on deeper analytics requirements."))
    if is_data_analyst and experience_fit.get("transition_candidate") and basic_trio and missing_deeper_core:
        if project_strength["moderate"] and final_score < 68:
            final_score = 68
        caps.append((72, "Score capped because the candidate has transferable reporting exposure, but direct Data Analyst experience and deeper BI/MIS evidence are not proven."))
    foundational_hits = sum([
        bool(core_evidence["sql"]),
        bool(core_evidence["advanced_excel_or_excel"]),
        bool(core_evidence["power_bi"]),
    ])

    if experience_fit["strong_overqualified"]:
        if foundational_hits >= 2 and final_score < 64:
            final_score = 64
        caps.append((72, "Score capped because the candidate appears strongly overqualified for this experience range."))
    elif experience_fit["overqualified"] and not experience_fit["acceptable"]:
        caps.append((77, "Score capped because the candidate is over the target experience range and needs recruiter review."))

    if experience_fit["under_experienced"]:
        if project_strength["strong"]:
            final_score = max(final_score, 78 if core_evidence["sql"] and core_evidence["power_bi"] else 75)
            caps.append((84, "Strong JD-aligned projects boosted the score, but limited professional experience keeps it capped."))
        elif project_strength["moderate"]:
            final_score = max(final_score, 72)
            caps.append((80, "Project evidence helps, but professional experience is still limited."))
        else:
            caps.append((76, "Limited professional experience without strong JD-aligned projects keeps the score capped."))

    for cap, reason in caps:
        if final_score > cap:
            final_score = cap
            reasons.append(reason)

    if reasons:
        flags.append("score_capped")

    score_data["final_score"] = round(max(0, min(100, final_score)), 2)
    return flags, reasons, all_critical


def determine_recruiter_status(score_data, core_evidence, experience_fit, project_strength, is_data_analyst):
    final_score = _safe_float(score_data.get("final_score"))
    core_match = _safe_float(score_data.get("mandatory_skill_coverage") or score_data.get("skill_match_percent"))
    missing = score_data.get("missing_skills") or []

    missing_core_groups = []
    if is_data_analyst:
        group_labels = {
            "sql": "SQL",
            "advanced_excel_or_excel": "Excel",
            "power_bi": "Power BI",
            "power_query_or_etl": "Power Query/ETL",
            "dax": "DAX",
            "mis_or_business_reporting": "MIS/Business Reporting",
            "kpi_or_dashboard_reporting": "KPI/Dashboard Reporting",
        }
        missing_core_groups = [label for key, label in group_labels.items() if not core_evidence.get(key)]

    foundational_hits = sum([
        bool(core_evidence["sql"]),
        bool(core_evidence["advanced_excel_or_excel"]),
        bool(core_evidence["power_bi"]),
    ])
    broad_required_skill_gap = len(missing) >= 5 and core_match < (45 if not is_data_analyst else 100)
    missing_multiple_must_have = (
        (core_match < 25 and (foundational_hits < 2 if is_data_analyst else True))
        or len(missing_core_groups) >= 4
        or (broad_required_skill_gap and foundational_hits < 2 and not project_strength["strong"])
    )
    no_foundational_data_evidence = is_data_analyst and foundational_hits < 2

    flags = []
    if project_strength["strong"]:
        flags.append("good_project_match")
    if experience_fit["under_experienced"]:
        flags.append("under_experienced")
    if experience_fit["overqualified"]:
        flags.append("overqualified")
    if experience_fit.get("transition_candidate"):
        flags.append("transition_candidate")
    if missing_core_groups or missing_multiple_must_have:
        flags.append("missing_core_skills")

    acceptable_experience = experience_fit["acceptable"] or (experience_fit["under_experienced"] and project_strength["strong"])
    core_match_ok = core_match >= 65 or (is_data_analyst and not missing_core_groups and final_score >= 78)

    auto_shortlist = (
        final_score >= 78
        and core_match_ok
        and acceptable_experience
        and not experience_fit["strong_overqualified"]
        and not experience_fit.get("transition_candidate")
        and not missing_multiple_must_have
        and not no_foundational_data_evidence
    )

    if auto_shortlist:
        flags.append("strong_match" if final_score >= 88 else "good_match")
        return "shortlisted", flags, missing_core_groups

    flags.append("review_required")
    if final_score < 60 or missing_multiple_must_have or no_foundational_data_evidence:
        if experience_fit.get("transition_candidate") and foundational_hits >= 2 and final_score >= 55:
            return "in_review", flags, missing_core_groups
        return "rejected", flags, missing_core_groups
    return "in_review", flags, missing_core_groups


def _append_recruiter_calibration_reason(base_reason, flags, cap_reasons, missing_core_groups, experience_fit, project_strength):
    notes = []
    if cap_reasons:
        notes.extend(cap_reasons[:2])
    if project_strength["strong"] and experience_fit["under_experienced"]:
        notes.append("Strong project-based evidence is present, but professional experience is limited.")
    if experience_fit.get("transition_candidate"):
        notes.append("Experience appears transferable rather than direct Data Analyst tenure; validate SQL, Excel, Power BI, and reporting skills before shortlist.")
    if experience_fit["strong_overqualified"]:
        notes.append("Candidate appears strongly overqualified for this JD range; recruiter review is recommended instead of auto-shortlist.")
    elif experience_fit["overqualified"]:
        notes.append("Candidate is above the target experience range, so recruiter review is recommended.")
    elif experience_fit.get("label") == "slightly_over_range":
        notes.append("Candidate is slightly above the target experience range; recruiter review can validate fit without a seniority penalty.")
    if missing_core_groups:
        notes.append(f"Missing or weak core evidence: {', '.join(missing_core_groups[:4])}.")
    if flags:
        notes.append(f"Recruiter flags: {', '.join(flags)}.")

    if not notes:
        return base_reason
    return f"{base_reason} {' '.join(notes)}"


def calibrate_final_score(parsed, jd_text, jd_data, required_skills, resume_text, score_data):
    is_data_analyst = _is_data_analyst_jd(jd_text, jd_data, required_skills)
    is_salesforce = _is_salesforce_jd(jd_text, jd_data, required_skills)
    matched_skills = score_data.get("matched_skills") or []
    candidate_skills = normalize_skill_list(parsed.get("key_skills", []))
    core_evidence = detect_core_skill_evidence(resume_text, matched_skills, candidate_skills)
    experience_fit = calculate_experience_fit(parsed, jd_data, is_data_analyst)
    project_strength = detect_project_strength(parsed, resume_text)

    cap_flags, cap_reasons, all_critical = apply_score_caps(
        score_data,
        core_evidence,
        experience_fit,
        project_strength,
        is_data_analyst,
    )
    recommendation, status_flags, missing_core_groups = determine_recruiter_status(
        score_data,
        core_evidence,
        experience_fit,
        project_strength,
        is_data_analyst,
    )

    flags = []
    _append_unique(flags, status_flags + cap_flags)
    sf_cap_reasons = []
    senior_salesforce_jd = is_salesforce and re.search(r"\bsenior|sr\.?\b", str(jd_data.get("role") or jd_text or ""), re.I)
    if senior_salesforce_jd:
        sf_source = parsed.get("salesforce_experience_years")
        sf_years = _safe_float(sf_source if sf_source is not None else parsed.get("relevant_experience_years"))
        total_years = _safe_float(parsed.get("total_experience_years"))
        cap = None
        if sf_years < 2:
            cap = 50
            recommendation = "rejected"
            sf_cap_reasons.append("Rejected - under experienced for Senior Salesforce Developer: less than 2 years Salesforce-specific experience.")
        elif sf_years < 4:
            cap = 65
            recommendation = "in_review"
            sf_cap_reasons.append("Review - mid-level Salesforce experience, not senior yet.")
        elif sf_years < 5:
            cap = 75
            recommendation = "in_review"
            sf_cap_reasons.append("Review - borderline senior Salesforce experience.")
        if total_years >= 8 and sf_years < 3:
            cap = min(cap or 68, 68)
            sf_cap_reasons.append("Strong total experience but limited Salesforce-specific experience.")
        core = _salesforce_core_evidence(matched_skills, resume_text)
        if not (core["apex"] and core["ui"] and core["soql"]):
            cap = min(cap or 68, 68)
            if recommendation == "shortlisted":
                recommendation = "in_review"
            sf_cap_reasons.append("Senior Salesforce core gate not fully met: requires Apex, SOQL, and one UI framework signal.")
        if cap is not None and _safe_float(score_data.get("final_score")) > cap:
            score_data["final_score"] = round(cap, 2)
            cap_flags.append("score_capped")
            _append_unique(flags, ["score_capped", "salesforce_seniority_gate"])
        elif sf_cap_reasons:
            _append_unique(flags, ["salesforce_seniority_gate"])
        cap_reasons.extend(sf_cap_reasons[:2])

    final_score = _safe_float(score_data.get("final_score"))
    raw_rank = _safe_float(score_data.get("rank_score"))
    if cap_flags and experience_fit.get("transition_candidate"):
        score_data["rank_score"] = round(final_score, 2)
    elif cap_flags:
        score_data["rank_score"] = round(min(raw_rank, final_score + 4), 2)
    elif final_score > raw_rank and (
        project_strength["strong"] or experience_fit["overqualified"] or experience_fit["under_experienced"]
    ):
        score_data["rank_score"] = round(final_score, 2)
    else:
        score_data["rank_score"] = round(max(raw_rank, final_score if project_strength["strong"] else raw_rank), 2)

    score_data["recommendation"] = recommendation
    score_data["fit_band"] = fit_band(
        score_data["rank_score"],
        (_safe_float(score_data.get("mandatory_skill_coverage")) / 100) if score_data.get("mandatory_skill_coverage") is not None else 0,
        _safe_float(score_data.get("confidence_score")),
    )
    score_data["recruiter_flags"] = flags
    score_data["core_skill_evidence"] = core_evidence
    score_data["core_skill_match_percent"] = score_data.get("mandatory_skill_coverage")
    score_data["missing_core_skill_groups"] = missing_core_groups
    score_data["experience_fit"] = experience_fit["label"]
    score_data["project_strength_score"] = project_strength["score"]
    score_data["all_critical_requirements_met"] = all_critical
    base_reason = re.sub(
        r"Rank score [\d.]+/100",
        f"Rank score {score_data['rank_score']}/100",
        score_data.get("ranking_reason", ""),
        count=1,
    )
    score_data["ranking_reason"] = _append_recruiter_calibration_reason(
        base_reason,
        flags,
        cap_reasons,
        missing_core_groups,
        experience_fit,
        project_strength,
    )

    breakdown = score_data.setdefault("scoring_breakdown", {})
    breakdown.update({
        "calibrated_final_score": score_data["final_score"],
        "calibrated_rank_score": score_data["rank_score"],
        "core_skill_match_percent": score_data["core_skill_match_percent"],
        "experience_fit": score_data["experience_fit"],
        "project_strength_score": score_data["project_strength_score"],
        "recruiter_flags": flags,
        "missing_core_skill_groups": missing_core_groups,
    })

    return score_data


def _project_work_evidence_strength(parsed, resume_text, matched_skills, role_family="other"):
    project_text = []
    for project in parsed.get("projects") or []:
        if isinstance(project, dict):
            project_text.append(" ".join([
                str(project.get("name") or ""),
                str(project.get("description") or ""),
                " ".join(str(item) for item in project.get("technologies") or []),
            ]))
        else:
            project_text.append(str(project))
    work_text = " ".join(
        f"{job.get('role', '')} {job.get('description', '')}"
        for job in parsed.get("experience", []) if isinstance(job, dict)
    )
    text = " ".join(project_text + [work_text, resume_text or ""]).lower()
    role_family = (role_family or "other").lower()
    if role_family == "data_analytics":
        action_pattern = r"\b(built|developed|implemented|designed|automated|analyzed|managed|deployed|optimized|created|delivered|reported|visualized|cleaned|extracted)\b"
    elif role_family in {"business_analyst", "business_analysis"}:
        action_pattern = r"\b(gathered|documented|analyzed|validated|coordinated|communicated|created|wrote|mapped|prioritized|facilitated|supported|managed|tracked|clarified|tested)\b"
    elif role_family in {"software_backend", "software_frontend", "full_stack", "mobile_development", "devops_cloud"}:
        action_pattern = r"\b(built|developed|implemented|designed|automated|deployed|optimized|created|delivered|tested|integrated|maintained|debugged)\b"
    elif role_family in {"sales_business_development", "hr_recruitment", "customer_support"}:
        action_pattern = r"\b(managed|coordinated|sourced|screened|closed|converted|communicated|negotiated|delivered|supported|onboarded|tracked)\b"
    else:
        action_pattern = r"\b(built|developed|implemented|designed|automated|managed|created|delivered|supported|coordinated|improved|owned)\b"
    action_hits = len(set(re.findall(action_pattern, text, re.I)))
    skill_hits = sum(1 for skill in matched_skills or [] if skill and re.search(r"\b" + re.escape(str(skill).lower()).replace(r"\ ", r"\s+") + r"\b", text, re.I))
    quantified = len(re.findall(r"\b\d+(?:%|k|,\d{3}| users?| records?| reports?| dashboards?| clients?)\b", text, re.I))
    return min(100, round(action_hits * 8 + skill_hits * 7 + min(quantified, 5) * 6, 2))


def _generic_education_fit(parsed, jd_data):
    text = " ".join(
        [str(item) for item in parsed.get("certifications") or []]
        + [
            " ".join(str(value or "") for value in item.values()) if isinstance(item, dict) else str(item)
            for item in parsed.get("education") or []
        ]
    ).lower()
    required = str((jd_data or {}).get("education") or "").lower()
    if not required:
        return 65 if text else 40
    if not text:
        return 25
    if any(term in required and term in text for term in ["bachelor", "master", "mba", "b.tech", "degree", "graduate"]):
        return 90
    if any(term in text for term in ["bachelor", "master", "mba", "b.tech", "degree", "graduate", "certification", "certificate"]):
        return 70
    return 45


def _generic_recommendation(final_score, mandatory_coverage, confidence, caps, risk_flags):
    if final_score >= 78 and mandatory_coverage >= 65 and confidence >= 65 and not risk_flags:
        return "shortlisted"
    if final_score < 45 or mandatory_coverage < 25 or "seniority_experience_gap" in risk_flags:
        return "rejected"
    if caps or risk_flags:
        return "in_review"
    return "in_review"


FULL_STACK_GROUP_WEIGHTS = {
    "frontend": 0.25,
    "frontend_foundation": 0.10,
    "backend": 0.25,
    "database": 0.20,
    "api_auth": 0.15,
    "auth_security": 0.15,
    "deployment_tools": 0.05,
    "good_to_have": 0.05,
}


BACKEND_GROUP_WEIGHTS = {
    "backend_path": 0.30,
    "api_logic": 0.20,
    "database": 0.15,
    "api_auth": 0.15,
    "tooling_deployment": 0.10,
    "reliability_security": 0.10,
}


FRONTEND_GROUP_WEIGHTS = {
    "frontend_core": 0.18,
    "react_core": 0.18,
    "responsive_ui": 0.14,
    "api_integration": 0.14,
    "state_management": 0.12,
    "frontend_tooling": 0.12,
    "performance_debugging": 0.12,
}


FRONTEND_SKILL_DISPLAY_ORDER = [
    "React", "Next.js", "HTML", "CSS", "JavaScript", "TypeScript",
    "Redux", "Context API", "Zustand", "Jotai", "Recoil", "MobX",
    "REST API", "API Integration", "Fetch", "Axios", "TanStack Query",
    "Responsive Design", "Mobile-first Design", "Browser Compatibility",
    "Git", "GitHub", "GitLab", "Vite", "Webpack", "npm",
    "Jest", "React Testing Library", "Cypress", "Performance Optimization",
    "Web Vitals", "SEO", "Accessibility", "Tailwind CSS", "Bootstrap",
    "Material UI", "Vercel", "Netlify", "AWS", "Node.js", "Express",
]


def _full_stack_group_score(group, options, parsed, resume_text, candidate_skills):
    evidences = []
    for skill in normalize_skill_list(options or []):
        direct = any(skill.lower() == candidate.lower() for candidate in candidate_skills)
        evidence = _classify_skill_evidence(skill, parsed, resume_text, candidate_skills, equivalent=False)
        if evidence.get("evidence_level") in {"missing", "keyword_only"} and _resume_evidence_skill_match(skill, resume_text):
            evidence = {
                **evidence,
                "status": "matched",
                "evidence_level": "professional_weak",
                "depth": "work_experience_evidence",
                "source": "resume_evidence",
                "weight": max(float(evidence.get("weight") or 0), 0.72),
            }
        if not direct and evidence.get("source") == "skills_section_equivalent":
            continue
        if direct and evidence.get("source") in {"skills_section", "resume_text"}:
            evidence = dict(evidence)
            evidence["weight"] = max(float(evidence.get("weight") or 0), 0.38)
            evidence["evidence_level"] = "skills_section_only"
            evidence["depth"] = "skills_section_only"
        if evidence.get("status") != "missing" and evidence.get("weight", 0) > 0:
            evidences.append(evidence)
    if not evidences:
        return {
            "group": group,
            "score": 0.0,
            "matched": [],
            "best_evidence_level": "missing",
            "best_source": "",
            "evidence": [],
        }
    best = max(evidences, key=lambda item: float(item.get("weight") or 0))
    bonus = min(0.16, max(0, len(evidences) - 1) * 0.04)
    score = min(1.0, float(best.get("weight") or 0) + bonus)
    return {
        "group": group,
        "score": round(score, 3),
        "matched": [item.get("skill") for item in evidences],
        "best_evidence_level": best.get("evidence_level") or best.get("depth") or "missing",
        "best_source": best.get("source") or "",
        "evidence": evidences,
    }


def _full_stack_project_work_strength(parsed, resume_text):
    text = " ".join([
        resume_text or "",
        " ".join(
            f"{job.get('role', '')} {job.get('description', '')}"
            for job in parsed.get("experience", []) if isinstance(job, dict)
        ),
        " ".join(
            " ".join(str(value or "") for value in project.values()) if isinstance(project, dict) else str(project)
            for project in parsed.get("projects", [])
        ),
    ]).lower()
    frontend = bool(re.search(r"\b(react|next(?:\.js)?|vue(?:\.js)?|angular(?:js)?|html|css|tailwind|bootstrap|kendo|telerik)\b", text, re.I))
    backend = bool(re.search(r"\b(node(?:\.js)?|express(?:\.js)?|django|fastapi|laravel|spring\s+boot|php|backend|api|c\s*#|\.net|dotnet|asp\s*\.?\s*net|web\s+api|entity\s+framework|linq|ado\s*\.?\s*net)\b", text, re.I))
    database = bool(re.search(r"\b(mongodb|mongo\s*db|mysql|postgres(?:ql)?|sql\s+server|ms\s+sql|t[-\s]?sql|pl\s*/\s*sql|sql|stored\s+procedures?|database|query\s+optimization|performance\s+tuning)\b", text, re.I))
    deployment = bool(re.search(r"\b(deploy(?:ed|ment)?|vercel|netlify|digital\s*ocean|aws|azure|azure\s+devops|docker|ci\s*/\s*cd|jenkins|linux|git)\b", text, re.I))
    production = bool(re.search(r"\b(production|users?|clients?|optimized|performance|scalable|maintained|integrated|authentication|payment|admin\s+dashboard)\b", text, re.I))
    quantified = bool(re.search(r"\b\d+(?:%|k|,\d{3}| users?| clients?| projects?| apis?)\b", text, re.I))
    action_hits = len(set(re.findall(r"\b(built|developed|implemented|designed|deployed|integrated|optimized|maintained|tested|debugged|created)\b", text, re.I)))
    score = action_hits * 8
    score += 18 if frontend and backend else 0
    score += 12 if database else 0
    score += 8 if deployment else 0
    score += 6 if production else 0
    score += 5 if quantified else 0
    return min(100, round(score, 2))


def _backend_project_work_strength(parsed, resume_text):
    text = " ".join([
        resume_text or "",
        " ".join(
            f"{job.get('role', '')} {job.get('description', '')}"
            for job in parsed.get("experience", []) if isinstance(job, dict)
        ),
        " ".join(
            " ".join(str(value or "") for value in project.values()) if isinstance(project, dict) else str(project)
            for project in parsed.get("projects", [])
        ),
    ]).lower()
    backend_path = bool(re.search(r"\b(node(?:\.js)?|express(?:\.js)?|django|fastapi|flask|laravel|spring\s+boot|java|python|php|backend|c\s*#|\.net|dotnet|asp\s*\.?\s*net|entity\s+framework|linq|ado\s*\.?\s*net)\b", text, re.I))
    api = bool(re.search(r"\b(rest(?:ful)?\s+apis?|web\s+apis?|graphql|crud|api\s+integration|business\s+logic|protected\s+routes?)\b", text, re.I))
    database = bool(re.search(r"\b(mongodb|mongo\s*db|mysql|postgres(?:ql)?|sql\s+server|ms\s+sql|t[-\s]?sql|pl\s*/\s*sql|sql|stored\s+procedures?|database|schema|queries?|data\s+model|query\s+optimization|performance\s+tuning)\b", text, re.I))
    auth = bool(re.search(r"\b(jwt|oauth|spring\s+security|firebase\s+auth|auth0|cognito|bcrypt|password\s+hash|authentication|authorization|rbac|session|token|access\s+control)\b", text, re.I))
    deployment = bool(re.search(r"\b(deploy(?:ed|ment)?|render|digital\s*ocean|aws|azure|docker|kubernetes|nginx|linux|ci\s*/\s*cd|server)\b", text, re.I))
    reliability = bool(re.search(r"\b(logging|error\s+handling|exception|validation|rate\s+limiting|secure|security|optimized|performance|scalable|background\s+jobs?|queues?)\b", text, re.I))
    quantified = bool(re.search(r"\b\d+(?:%|k|,\d{3}| users?| clients?| apis?| endpoints?| records?)\b", text, re.I))
    action_hits = len(set(re.findall(r"\b(built|developed|implemented|designed|deployed|integrated|optimized|maintained|tested|debugged|created|secured)\b", text, re.I)))
    score = action_hits * 7
    score += 18 if backend_path and api else 0
    score += 12 if database else 0
    score += 12 if auth else 0
    score += 8 if deployment else 0
    score += 8 if reliability else 0
    score += 5 if quantified else 0
    return min(100, round(score, 2))


def _frontend_project_work_strength(parsed, resume_text):
    text = " ".join([
        resume_text or "",
        " ".join(
            f"{job.get('role', '')} {job.get('description', '')}"
            for job in parsed.get("experience", []) if isinstance(job, dict)
        ),
        " ".join(
            " ".join(str(value or "") for value in project.values()) if isinstance(project, dict) else str(project)
            for project in parsed.get("projects", [])
        ),
    ]).lower()
    frontend_core = bool(re.search(r"\b(html5?|css3?|javascript|es6|scss|sass)\b", text, re.I))
    react = bool(re.search(r"\breact(?:\.js|js)?\b|\bnext(?:\.js)?\b|\bjsx\b", text, re.I))
    responsive = bool(re.search(r"\bresponsive|mobile[-\s]?first|cross[-\s]?browser|ui/ux|accessibility|wcag\b", text, re.I))
    api = bool(re.search(r"\b(rest(?:ful)?\s+apis?|api\s+integration|axios|fetch|tanstack\s+query|react\s+query|dynamic\s+data)\b", text, re.I))
    state = bool(re.search(r"\b(redux|context\s+api|zustand|jotai|recoil|mobx)\b", text, re.I))
    tooling = bool(re.search(r"\b(vite|webpack|npm|git(?:hub|lab)?|chrome\s+devtools|build\s+tools)\b", text, re.I))
    performance = bool(re.search(r"\b(performance|page\s+speed|web\s*vitals|seo|debug(?:ging)?|optimized?|code\s+quality)\b", text, re.I))
    action_hits = len(set(re.findall(r"\b(built|developed|implemented|designed|integrated|optimized|maintained|tested|debugged|created|converted)\b", text, re.I)))
    quantified = bool(re.search(r"\b\d+(?:%|k|,\d{3}| users?| pages?| components?| dashboards?| modules?)\b", text, re.I))
    score = action_hits * 7
    score += 18 if frontend_core and react else 0
    score += 10 if responsive else 0
    score += 12 if api else 0
    score += 10 if state else 0
    score += 8 if tooling else 0
    score += 8 if performance else 0
    score += 5 if quantified else 0
    return min(100, round(score, 2))


FRONTEND_API_PRODUCT_EVIDENCE_RE = re.compile(
    r"\b(rest(?:ful)?\s+apis?|api\s+integration|axios|fetch|tanstack\s+query|react\s+query|"
    r"dynamic\s+data|data[-\s]?driven\s+ui|server[-\s]?side\s+data|backend[-\s]?connected|"
    r"integrat(?:e|ed|ion|ing)\s+(?:api|backend|payment|payments?|gateway|webview|webviews?)|"
    r"payment\s+(?:methods?|gateway|integration)|prepaid\s+payment|upi|cards?|net\s+banking|"
    r"webviews?|role[-\s]?based\s+dashboards?|dashboards?|listing\s+pages?|customer[-\s]?facing|"
    r"react\s+hook\s+form|forms?|checkout|cart|order\s+flow|admin\s+panel)\b",
    re.I,
)


def _frontend_api_integration_signal(parsed, resume_text):
    text = " ".join([
        resume_text or "",
        " ".join(
            f"{job.get('role', '')} {job.get('description', '')}"
            for job in parsed.get("experience", []) if isinstance(job, dict)
        ),
        " ".join(
            " ".join(str(value or "") for value in project.values()) if isinstance(project, dict) else str(project)
            for project in parsed.get("projects", [])
        ),
    ])
    hits = sorted({match.group(0) for match in FRONTEND_API_PRODUCT_EVIDENCE_RE.finditer(text)})
    frontend_context = bool(
        re.search(
            r"\b(react(?:\.js|js)?|next(?:\.js)?|vue(?:\.js)?|angular|javascript|typescript|"
            r"html5?|css3?|frontend|front[-\s]?end|ui|web\s+app(?:lication)?s?)\b",
            text,
            re.I,
        )
    )
    return hits if frontend_context and hits else []


def _frontend_experience_fit(parsed, jd_profile):
    relevant = _safe_float(parsed.get("relevant_experience_years"))
    total = _safe_float(parsed.get("total_experience_years"))
    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    if relevant <= 0 and role_relevance >= 65:
        relevant = min(total, 1.0) if total else 0.5

    jd_min = _safe_float(jd_profile.get("min_experience_years")) or 1.0
    jd_max = _safe_float(jd_profile.get("max_experience_years")) or 3.0
    label = "unknown"
    score = 55
    overqualified = False
    strong_overqualified = False
    under = False

    if relevant <= 0:
        label = "fresher_or_intern_risk"
        under = True
        score = 40
    elif relevant < jd_min:
        label = "junior_review"
        under = True
        score = min(70, 48 + (relevant / max(jd_min, 1)) * 22)
    elif relevant <= jd_max:
        label = "ideal_1_3_years"
        score = 94
    elif relevant <= 4.5:
        label = "slightly_over_range"
        score = 84
        overqualified = True
    elif relevant <= 6:
        label = "overqualified_review"
        score = 70
        overqualified = True
    elif relevant <= 8:
        label = "senior_overqualified"
        score = 58
        overqualified = True
        strong_overqualified = True
    else:
        label = "senior_overqualified"
        score = 48
        overqualified = True
        strong_overqualified = True

    if jd_max <= 3 and total >= 10:
        label = "senior_overqualified"
        score = min(score, 45)
        overqualified = True
        strong_overqualified = True
    elif jd_max <= 3 and total >= 8:
        label = "senior_overqualified"
        score = min(score, 55)
        overqualified = True
        strong_overqualified = True
    elif jd_max <= 3 and total >= 6:
        label = "overqualified_review"
        score = min(score, 65)
        overqualified = True

    return {
        "score": round(score, 2),
        "label": label,
        "relevant_years": relevant,
        "total_years": total,
        "overqualified": overqualified,
        "strong_overqualified": strong_overqualified,
        "under_experienced": under,
        "jd_min": jd_min or None,
        "jd_max": jd_max or None,
    }


def _frontend_location_fit(parsed, jd_data, jd_text):
    candidate_location = str(parsed.get("location") or parsed.get("current_location") or "").lower()
    jd_location = " ".join([
        str((jd_data or {}).get("location") or ""),
        str((jd_data or {}).get("work_mode") or ""),
        jd_text or "",
    ]).lower()
    india_jd = bool(re.search(r"\b(noida|gurugram|gurgaon|delhi|ncr|india|hybrid|onsite)\b", jd_location))
    global_remote = bool(re.search(r"\bglobal\s+remote|worldwide|anywhere\b", jd_location))
    india_candidate = bool(re.search(r"\b(india|noida|gurugram|gurgaon|delhi|ncr|mumbai|bengaluru|bangalore|hyderabad|pune|chennai|kolkata|mangalore)\b", candidate_location))
    ncr_candidate = bool(re.search(r"\b(noida|gurugram|gurgaon|delhi|ncr)\b", candidate_location))
    foreign_candidate = bool(re.search(r"\b(los angeles|california|san francisco|usa|united states|greece|london|uk|poland|malaysia|idaho|new york|austin|tx|ca)\b", candidate_location))

    if not candidate_location:
        return {"score": 65, "label": "location_needs_validation", "flag": "location_needs_validation"}
    if global_remote:
        return {"score": 85, "label": "global_remote_acceptable", "flag": ""}
    if india_jd and ncr_candidate:
        return {"score": 100, "label": "location_strong_fit", "flag": ""}
    if india_jd and india_candidate:
        return {"score": 85, "label": "india_remote_fit", "flag": ""}
    if india_jd and foreign_candidate:
        return {"score": 35, "label": "location_budget_mismatch", "flag": "location_budget_mismatch"}
    return {"score": 70, "label": "location_unclear", "flag": "location_needs_validation"}


def _frontend_salary_fit(parsed, jd_data, jd_text, location_fit):
    text = " ".join([
        str((jd_data or {}).get("salary") or ""),
        str((jd_data or {}).get("salary_range") or ""),
        jd_text or "",
    ]).lower()
    low_budget_india = bool(re.search(r"\b(?:4\s*[-–]\s*5|4\s*to\s*5)\s*lpa\b|\b5\s*lpa\b", text, re.I))
    candidate_salary = str(parsed.get("expected_salary") or parsed.get("salary") or "").lower()
    if candidate_salary and low_budget_india and re.search(r"\b([6-9]|1\d)\s*lpa\b", candidate_salary):
        return {"score": 35, "label": "salary_above_budget", "flag": "salary_budget_mismatch"}
    if low_budget_india and location_fit.get("flag") == "location_budget_mismatch":
        return {"score": 30, "label": "salary_location_mismatch", "flag": "salary_budget_mismatch"}
    if low_budget_india:
        return {"score": 70, "label": "salary_needs_validation", "flag": "salary_needs_validation"}
    return {"score": 75, "label": "salary_not_specified", "flag": "salary_needs_validation"}


def _ordered_frontend_skills(skills):
    normalized = normalize_skill_list(skills or [])
    lower_map = {skill.lower(): skill for skill in normalized}
    ordered = []
    for skill in FRONTEND_SKILL_DISPLAY_ORDER:
        value = lower_map.get(skill.lower())
        if value and value not in ordered:
            ordered.append(value)
    for skill in normalized:
        if skill not in ordered:
            ordered.append(skill)
    return ordered


def _full_stack_experience_fit(parsed, jd_profile):
    relevant = _safe_float(parsed.get("relevant_experience_years"))
    total = _safe_float(parsed.get("total_experience_years"))
    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    if relevant <= 0 and role_relevance >= 55:
        relevant = min(total, 1.0) if total else 0.5

    jd_min = _safe_float(jd_profile.get("min_experience_years"))
    jd_max = _safe_float(jd_profile.get("max_experience_years"))
    label = "unknown"
    score = 55
    overqualified = False
    under = False
    if jd_min and relevant < jd_min:
        under = True
        label = "junior_project_only" if relevant > 0 else "under_experienced"
        score = 45 if relevant <= 0 else min(68, 45 + (relevant / jd_min) * 25)
    elif jd_max and relevant > jd_max:
        overqualified = True
        if relevant <= jd_max + 2:
            label = "experienced_above_range"
            score = 82
        else:
            label = "senior_overqualified"
            score = 70 if relevant < 8 else 62
    else:
        label = "best_fit"
        score = 92 if relevant else 65
    return {
        "score": round(score, 2),
        "label": label,
        "relevant_years": relevant,
        "total_years": total,
        "overqualified": overqualified,
        "under_experienced": under,
        "jd_min": jd_min or None,
        "jd_max": jd_max or None,
    }


def _backend_experience_fit(parsed, jd_profile):
    relevant = _safe_float(parsed.get("relevant_experience_years"))
    total = _safe_float(parsed.get("total_experience_years"))
    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    if relevant <= 0 and role_relevance >= 65:
        relevant = min(total, 1.0) if total else 0.5

    jd_min = _safe_float(jd_profile.get("min_experience_years"))
    jd_max = _safe_float(jd_profile.get("max_experience_years")) or 3.0
    label = "unknown"
    score = 55
    overqualified = False
    under = False
    if relevant <= 0:
        label = "fresher_or_intern_risk"
        under = True
        score = 38
    elif relevant < 0.5:
        label = "fresher_or_intern_risk"
        under = True
        score = 45
    elif relevant < max(jd_min, 1.0):
        label = "junior_review"
        under = True
        score = 58
    elif relevant <= jd_max:
        label = "ideal_1_3_years"
        score = 92
    elif relevant <= 5:
        label = "strong_slightly_senior"
        score = 82
        overqualified = True
    elif relevant <= 8:
        label = "overqualified_review"
        score = 68
        overqualified = True
    else:
        label = "senior_overqualified"
        score = 58
        overqualified = True
    return {
        "score": round(score, 2),
        "label": label,
        "relevant_years": relevant,
        "total_years": total,
        "overqualified": overqualified,
        "under_experienced": under,
        "jd_min": jd_min or None,
        "jd_max": jd_max or None,
    }


def _score_candidate_frontend(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    candidate_skills = normalize_skill_list(parsed.get("key_skills", []))
    core_groups = {
        group: options
        for group, options in (jd_profile.get("core_skill_groups") or {}).items()
        if group in FRONTEND_GROUP_WEIGHTS or group == "good_to_have"
    }
    if not core_groups:
        core_groups = {
            "frontend_core": ["HTML", "CSS", "JavaScript"],
            "react_core": ["React", "JSX", "Component-based Development"],
            "responsive_ui": ["Responsive Design", "Mobile-first Design", "Browser Compatibility", "UI/UX"],
            "api_integration": ["REST API", "API Integration", "Fetch", "Axios"],
            "state_management": ["Redux", "Context API", "Zustand"],
            "frontend_tooling": ["Git", "GitHub", "npm", "Vite", "Webpack"],
            "performance_debugging": ["Performance Optimization", "Page Speed", "Web Vitals", "Debugging"],
            "good_to_have": ["TypeScript", "Next.js", "Tailwind CSS", "Bootstrap", "Material UI", "Jest", "Cypress", "Vercel", "Netlify", "AWS", "Node.js", "Express"],
        }

    group_results = {
        group: _full_stack_group_score(group, options, parsed, resume_text, candidate_skills)
        for group, options in core_groups.items()
    }
    api_product_hits = _frontend_api_integration_signal(parsed, resume_text)
    if api_product_hits and (group_results.get("api_integration") or {}).get("score", 0) < 0.5:
        group_results["api_integration"] = {
            "group": "api_integration",
            "score": 0.62,
            "matched": ["API Integration"],
            "best_evidence_level": "professional_weak",
            "best_source": "frontend_product_evidence",
            "evidence": [{
                "skill": "API Integration",
                "status": "matched",
                "evidence_level": "professional_weak",
                "depth": "work_experience_evidence",
                "source": "frontend_product_evidence",
                "weight": 0.62,
                "matched_terms": api_product_hits[:8],
            }],
        }

    weighted_core = 0.0
    total_weight = 0.0
    for group, weight in FRONTEND_GROUP_WEIGHTS.items():
        if group not in group_results:
            continue
        weighted_core += group_results[group]["score"] * weight
        total_weight += weight
    core_skill_percent = round((weighted_core / max(total_weight, 0.01)) * 100, 2)
    missing_core_groups = [
        group for group, result in group_results.items()
        if group in FRONTEND_GROUP_WEIGHTS and result["score"] < 0.35
    ]
    senior_react_profile = (
        _safe_float(parsed.get("total_experience_years")) >= 5
        and (group_results.get("react_core") or {}).get("score", 0) >= 0.55
    )
    state_management_soft_gap = False
    if senior_react_profile and "state_management" in missing_core_groups:
        missing_core_groups = [group for group in missing_core_groups if group != "state_management"]
        state_management_soft_gap = True

    matched_skill_evidence = []
    matched_skills = []
    for group in FRONTEND_GROUP_WEIGHTS:
        result = group_results.get(group) or {}
        matched_skills.extend(result.get("matched") or [])
        matched_skill_evidence.extend(result.get("evidence") or [])
    good_to_have_result = group_results.get("good_to_have") or {}
    preferred_skills = good_to_have_result.get("matched") or []
    matched_skills = _ordered_frontend_skills(matched_skills + preferred_skills)

    project_work_strength = _frontend_project_work_strength(parsed, resume_text)
    experience_fit = _frontend_experience_fit(parsed, jd_profile)
    location_fit = _frontend_location_fit(parsed, jd_data or {}, jd_text or "")
    salary_fit = _frontend_salary_fit(parsed, jd_data or {}, jd_text or "", location_fit)
    designation = str(parsed.get("designation") or parsed.get("current_title") or "")
    role_relevance = max(
        _safe_float(parsed.get("role_relevance_score")),
        94 if re.search(r"\b(front[-\s]?end|frontend|react|ui\s+developer|web\s+developer)\b", designation, re.I) else 0,
        80 if re.search(r"\b(full[-\s]?stack|software\s+(?:engineer|developer)|sde)\b", designation, re.I) and core_skill_percent >= 60 else 0,
    )
    good_to_have_score = (good_to_have_result.get("score") or 0) * 100

    final_score = (
        core_skill_percent * 0.40
        + experience_fit["score"] * 0.20
        + project_work_strength * 0.15
        + location_fit["score"] * 0.10
        + salary_fit["score"] * 0.10
        + good_to_have_score * 0.05
    )

    risk_flags = []
    recruiter_flags = []
    caps = []
    if missing_core_groups:
        _append_unique(risk_flags, ["missing_core_skill_groups"])
        _append_unique(recruiter_flags, ["missing_core_skills"])
    if experience_fit["under_experienced"]:
        _append_unique(recruiter_flags, ["under_experienced"])
        _append_unique(risk_flags, ["below_jd_experience_range"])
    if experience_fit["overqualified"]:
        _append_unique(recruiter_flags, ["overqualified", "overqualified_review"])
        _append_unique(risk_flags, ["over_jd_experience_range"])
    if experience_fit.get("strong_overqualified"):
        _append_unique(recruiter_flags, ["strongly_overqualified"])
    if location_fit.get("flag"):
        _append_unique(recruiter_flags, [location_fit["flag"]])
        if location_fit["flag"] == "location_budget_mismatch":
            _append_unique(risk_flags, ["location_budget_mismatch"])
    if salary_fit.get("flag"):
        _append_unique(recruiter_flags, [salary_fit["flag"]])
    if project_work_strength >= 55:
        _append_unique(recruiter_flags, ["frontend_project_evidence", "strong_professional_evidence"])
    if state_management_soft_gap:
        _append_unique(recruiter_flags, ["state_management_validation"])

    if len(missing_core_groups) >= 4:
        caps.append({"cap": 58, "reason": "Four or more frontend core groups are missing."})
    elif len(missing_core_groups) >= 3:
        caps.append({"cap": 68, "reason": "Three frontend core groups need validation."})
    elif len(missing_core_groups) >= 2:
        caps.append({"cap": 76, "reason": "Two frontend core groups need validation."})
    if experience_fit["label"] == "fresher_or_intern_risk":
        caps.append({"cap": 58, "reason": "No proven professional frontend experience; recruiter review required."})
    elif experience_fit["label"] == "junior_review":
        caps.append({"cap": 76, "reason": "Below the frontend JD experience band; validate project depth."})
    elif experience_fit["label"] == "slightly_over_range":
        caps.append({"cap": 86, "reason": "Slightly above the 1-3 year frontend range; validate budget fit."})
    elif experience_fit["label"] == "overqualified_review":
        caps.append({"cap": 74, "reason": "Above the 1-3 year frontend range; recruiter review recommended."})
    elif experience_fit["label"] == "senior_overqualified":
        caps.append({"cap": 64 if experience_fit.get("strong_overqualified") else 70, "reason": "Senior/overqualified for this 1-3 year frontend role; recruiter review recommended."})
    if location_fit.get("flag") == "location_budget_mismatch":
        caps.append({"cap": 72, "reason": "Location/budget mismatch for this India frontend role."})
    if parsed.get("parser_quality_action") == "manual_review_required":
        caps.append({"cap": 58, "reason": "Parser quality requires manual review."})
        _append_unique(risk_flags, ["parser_quality"])
        _append_unique(recruiter_flags, ["parser_manual_review"])

    for cap in caps:
        final_score = min(final_score, cap["cap"])

    final_score = round(max(0, min(100, final_score)), 2)
    confidence = round(min(100, 35 + core_skill_percent * 0.27 + project_work_strength * 0.20 + role_relevance * 0.14 + _safe_float(parsed.get("resume_quality_score"), 75) * 0.12 + experience_fit["score"] * 0.10), 2)
    rank_score = round(min(100, final_score + (3 if confidence >= 70 and not risk_flags else 0)), 2)

    if (
        final_score >= 78
        and core_skill_percent >= 68
        and experience_fit["label"] in {"ideal_1_3_years", "slightly_over_range"}
        and len(missing_core_groups) <= 1
        and location_fit.get("flag") != "location_budget_mismatch"
    ):
        recommendation = "shortlisted"
        _append_unique(recruiter_flags, ["strong_match" if final_score >= 86 else "good_match"])
    elif final_score < 42 or (len(missing_core_groups) >= 4 and final_score < 58):
        recommendation = "rejected"
    else:
        recommendation = "in_review"

    if experience_fit["overqualified"] and recommendation == "shortlisted":
        recommendation = "in_review"

    missing_skills = [group.replace("_", " ").title() for group in missing_core_groups]
    label = (
        "Strong fit" if recommendation == "shortlisted" and final_score >= 84
        else "Good fit" if recommendation == "shortlisted"
        else "Location/Budget Mismatch" if location_fit.get("flag") == "location_budget_mismatch"
        else "Overqualified review" if experience_fit["overqualified"]
        else "Below experience range" if experience_fit["under_experienced"]
        else "Skill validation needed" if missing_core_groups
        else "Review required"
    )
    ranking_reason = (
        f"Rank score {rank_score}/100 with {confidence}% confidence: "
        f"{core_skill_percent}% frontend group coverage, {experience_fit['relevant_years']:g}/{experience_fit['total_years']:g} relevant/total years, "
        f"location fit {location_fit['label']}, salary fit {salary_fit['label']}."
    )
    if missing_core_groups:
        ranking_reason += f" Missing frontend groups: {', '.join(missing_core_groups)}."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    return {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": "strong_match" if final_score >= 84 else "good_match" if final_score >= 68 else "review" if final_score >= 45 else "low_match",
        "skill_score": round(core_skill_percent * 0.40, 2),
        "experience_score": round(experience_fit["score"] * 0.20, 2),
        "semantic_score": parsed.get("semantic_score", 0),
        "semantic_weight": 0,
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(role_relevance * 0.14, 2),
        "education_score": 0,
        "matched_skills": matched_skills,
        "direct_matched_skills": matched_skills,
        "transferable_skills": [],
        "preferred_matched_skills": _ordered_frontend_skills(preferred_skills),
        "missing_skills": missing_skills,
        "skill_evidence_depth": {skill: evidence.get("depth", evidence.get("evidence_level", "")) for evidence in matched_skill_evidence for skill in [evidence.get("skill")] if skill},
        "skill_evidence": {skill: evidence for evidence in matched_skill_evidence for skill in [evidence.get("skill")] if skill},
        "matched_skill_evidence": matched_skill_evidence,
        "missing_or_weak_skills": [
            {"skill": group.replace("_", " ").title(), "status": "missing", "evidence_level": "missing"}
            for group in missing_core_groups
        ],
        "employer_name_only_skills": [],
        "skill_match_percent": core_skill_percent,
        "mandatory_skill_coverage": core_skill_percent,
        "preferred_skill_coverage": round(good_to_have_score, 2),
        "core_skill_match_percent": core_skill_percent,
        "matched_core_skill_groups": [group for group, result in group_results.items() if group in FRONTEND_GROUP_WEIGHTS and result["score"] >= 0.35],
        "missing_core_skill_groups": missing_core_groups,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), experience_fit["relevant_years"]),
        "target_seniority_level": jd_profile.get("seniority_level"),
        "recommendation": recommendation,
        "label": label,
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "ranking_reason": ranking_reason,
        "experience_fit": experience_fit["label"],
        "project_strength_score": project_work_strength,
        "all_critical_requirements_met": not missing_core_groups,
        "jd_role_family": "software_frontend",
        "jd_skill_groups": core_groups,
        "evidence_group_scores": group_results,
        "role_relevance_label": parsed.get("experience_relevance_label") or "",
        "experience_fit_label": experience_fit["label"],
        "location_fit": location_fit,
        "salary_budget_fit": salary_fit,
        "scoring_breakdown": {
            "frontend_group_component": round(core_skill_percent * 0.40, 2),
            "experience_fit_component": round(experience_fit["score"] * 0.20, 2),
            "project_work_component": round(project_work_strength * 0.15, 2),
            "location_fit_component": round(location_fit["score"] * 0.10, 2),
            "salary_budget_component": round(salary_fit["score"] * 0.10, 2),
            "good_to_have_component": round(good_to_have_score * 0.05, 2),
            "evidence_group_scores": group_results,
            "missing_core_skill_groups": missing_core_groups,
            "score_caps_applied": caps,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("current_title") or parsed.get("designation") or "",
            "target_role_alignment": "strong" if role_relevance >= 75 else "partial" if role_relevance >= 45 else "weak",
            "total_experience_years": experience_fit["total_years"],
            "jd_relevant_experience_years": experience_fit["relevant_years"],
            "seniority_fit": experience_fit["label"],
            "location_fit": location_fit["label"],
            "salary_budget_fit": salary_fit["label"],
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "label": label,
            "matched_skills": matched_skill_evidence,
            "missing_or_weak_skills": missing_skills,
            "risk_flags": risk_flags,
            "parser_quality_flags": parsed.get("parser_quality_flags") or [],
        },
    }


def _score_candidate_full_stack(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    candidate_skills = normalize_skill_list(parsed.get("key_skills", []))
    core_groups = jd_profile.get("core_skill_groups") or {}
    if not core_groups:
        core_groups = {
            "frontend": ["React", "Next.js", "Vue", "Angular"],
            "frontend_foundation": ["HTML", "CSS", "JavaScript", "TypeScript"],
            "backend": ["Node.js", "Express", "Django", "FastAPI", "PHP", "Laravel", "Spring Boot"],
            "database": ["MongoDB", "Mongoose", "MySQL", "PostgreSQL", "SQL", "SQL Server", "Firebase", "Firestore", "Prisma", "Sequelize"],
            "api_auth": ["REST API", "GraphQL", "JWT", "OAuth", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Clerk Auth", "Password Hashing"],
            "deployment_tools": ["Git", "GitHub", "GitHub Actions", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Vercel", "Netlify", "Render", "Heroku", "Nginx", "Linux", "VPS", "CI/CD"],
        }

    group_results = {
        group: _full_stack_group_score(group, options, parsed, resume_text, candidate_skills)
        for group, options in core_groups.items()
        if group in FULL_STACK_GROUP_WEIGHTS
    }
    role_family = (jd_profile.get("role_family") or "full_stack").lower()
    dotnet_target = role_family == "dotnet_full_stack"
    if "frontend_foundation" in group_results and "frontend" in group_results:
        # Foundation skills help, but framework evidence carries the real frontend gate.
        group_results["frontend"]["score"] = max(
            group_results["frontend"]["score"],
            min(0.72, group_results["frontend_foundation"]["score"] * 0.75),
        )

    weighted_core = 0.0
    total_weight = 0.0
    optional_core_groups = {"auth_security", "good_to_have"} if dotnet_target else set()
    for group, weight in FULL_STACK_GROUP_WEIGHTS.items():
        if group not in group_results:
            continue
        if group in optional_core_groups:
            continue
        weighted_core += group_results[group]["score"] * weight
        total_weight += weight
    core_skill_percent = round((weighted_core / max(total_weight, 0.01)) * 100, 2)
    missing_core_groups = [
        group for group, result in group_results.items()
        if group not in {"frontend_foundation", "good_to_have"} and result["score"] < 0.35
    ]

    matched_skill_evidence = []
    matched_skills = []
    for result in group_results.values():
        matched_skills.extend(result.get("matched") or [])
        matched_skill_evidence.extend(result.get("evidence") or [])
    matched_skills = normalize_skill_list(matched_skills)

    project_work_strength = _full_stack_project_work_strength(parsed, resume_text)
    experience_fit = _full_stack_experience_fit(parsed, jd_profile)
    role_relevance = max(
        _safe_float(parsed.get("role_relevance_score")),
        85 if re.search(r"\b(full[-\s]?stack|mern|web\s+developer|software\s+engineer)\b", str(parsed.get("designation") or ""), re.I) else 0,
        92 if dotnet_target and re.search(r"\b(software\s+engineer|software\s+developer|lead\s+engineer|\.net|dotnet|asp\.?\s*net|c#)\b", str(parsed.get("designation") or ""), re.I) else 0,
    )
    deployment_score = (group_results.get("deployment_tools") or {}).get("score", 0) * 100

    risk_flags = []
    recruiter_flags = []
    caps = []
    if missing_core_groups:
        _append_unique(risk_flags, ["missing_core_skill_groups"])
        _append_unique(recruiter_flags, ["missing_core_skills"])
    if experience_fit["under_experienced"]:
        _append_unique(recruiter_flags, ["under_experienced"])
        if (experience_fit.get("jd_min") or 0) >= 2:
            _append_unique(risk_flags, ["below_jd_experience_range"])
    if experience_fit["overqualified"]:
        _append_unique(recruiter_flags, ["overqualified", "senior_overqualified"])
        _append_unique(risk_flags, ["over_jd_experience_range"])
    if project_work_strength >= 60:
        _append_unique(recruiter_flags, ["strong_professional_evidence"])

    if dotnet_target:
        seniority_score = 92 if re.search(r"\b(senior|sr\.?|lead|tech\s+lead|architect|mentor|code\s+review)\b", " ".join([
            str(parsed.get("designation") or ""),
            " ".join(str((job or {}).get("role") or "") for job in parsed.get("experience") or [] if isinstance(job, dict)),
        ]), re.I) else 70
        good_to_have_score = (group_results.get("good_to_have") or {}).get("score", 0) * 100
        final_score = (
            core_skill_percent * 0.40
            + experience_fit["score"] * 0.25
            + project_work_strength * 0.15
            + seniority_score * 0.10
            + min(100, deployment_score) * 0.05
            + good_to_have_score * 0.05
        )
    else:
        seniority_score = 0
        good_to_have_score = 0
        final_score = (
            core_skill_percent * 0.35
            + project_work_strength * 0.25
            + experience_fit["score"] * 0.15
            + role_relevance * 0.15
            + deployment_score * 0.05
            + _safe_float(parsed.get("parser_quality_score"), parsed.get("resume_quality_score") or 70) * 0.05
        )

    if len(missing_core_groups) >= 3:
        caps.append({"cap": 60, "reason": "Three or more full-stack core groups are missing."})
    elif len(missing_core_groups) >= 2:
        caps.append({"cap": 72, "reason": "Two full-stack core groups need validation."})
    if experience_fit["under_experienced"] and (experience_fit.get("jd_min") or 0) >= 2:
        if experience_fit["relevant_years"] < 1:
            caps.append({"cap": 60, "reason": "JD-related professional experience is below 1 year for a role requiring at least 2 years."})
        else:
            caps.append({"cap": 72, "reason": "JD-related professional experience is below the minimum required range."})
    if experience_fit["label"] == "senior_overqualified":
        caps.append({"cap": 88 if dotnet_target else 78, "reason": "Senior/overqualified for this role; recruiter review recommended."})
    if parsed.get("parser_quality_action") == "manual_review_required":
        caps.append({"cap": 58, "reason": "Parser quality requires manual review."})
        _append_unique(risk_flags, ["parser_quality"])
        _append_unique(recruiter_flags, ["parser_manual_review"])
    for cap in caps:
        final_score = min(final_score, cap["cap"])

    final_score = round(max(0, min(100, final_score)), 2)
    confidence = round(min(100, 35 + core_skill_percent * 0.25 + project_work_strength * 0.22 + role_relevance * 0.18 + _safe_float(parsed.get("resume_quality_score"), 75) * 0.12), 2)
    rank_score = round(min(100, final_score + (3 if confidence >= 65 and not risk_flags else 0)), 2)

    if final_score >= 78 and core_skill_percent >= 68 and not experience_fit["under_experienced"] and (dotnet_target or not experience_fit["overqualified"]) and len(missing_core_groups) <= 1:
        recommendation = "shortlisted"
        _append_unique(recruiter_flags, ["strong_match" if final_score >= 88 else "good_match"])
    elif final_score < 45 or (len(missing_core_groups) >= 3 and final_score < 60):
        recommendation = "rejected"
    else:
        recommendation = "in_review"

    if experience_fit["overqualified"] and recommendation == "shortlisted" and not dotnet_target:
        recommendation = "in_review"

    missing_skills = []
    for group in missing_core_groups:
        missing_skills.append(group.replace("_", " ").title())

    label = "Strong fit" if recommendation == "shortlisted" and final_score >= 84 else "Good match" if recommendation == "shortlisted" else "Overqualified review" if experience_fit["overqualified"] else "Below experience range" if "below_jd_experience_range" in risk_flags else "Junior but promising" if experience_fit["under_experienced"] and final_score >= 55 else "Weak match" if recommendation == "rejected" else "Review required"
    ranking_reason = (
        f"Rank score {rank_score}/100 with {confidence}% confidence: "
        f"{core_skill_percent}% full-stack group coverage, {experience_fit['relevant_years']:g}/{experience_fit['total_years']:g} relevant/total years, "
        f"role relevance {role_relevance:g}/100."
    )
    if missing_core_groups:
        ranking_reason += f" Missing full-stack groups: {', '.join(missing_core_groups)}."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    return {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": "strong_match" if final_score >= 84 else "good_match" if final_score >= 68 else "review" if final_score >= 45 else "low_match",
        "skill_score": round(core_skill_percent * 0.35, 2),
        "experience_score": round(experience_fit["score"] * 0.15, 2),
        "semantic_score": parsed.get("semantic_score", 0),
        "semantic_weight": 0,
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(role_relevance * 0.15, 2),
        "education_score": 0,
        "matched_skills": matched_skills,
        "direct_matched_skills": matched_skills,
        "transferable_skills": [],
        "preferred_matched_skills": [],
        "missing_skills": missing_skills,
        "skill_evidence_depth": {skill: evidence.get("depth", evidence.get("evidence_level", "")) for evidence in matched_skill_evidence for skill in [evidence.get("skill")] if skill},
        "skill_evidence": {skill: evidence for evidence in matched_skill_evidence for skill in [evidence.get("skill")] if skill},
        "matched_skill_evidence": matched_skill_evidence,
        "missing_or_weak_skills": [
            {"skill": group.replace("_", " ").title(), "status": "missing", "evidence_level": "missing"}
            for group in missing_core_groups
        ],
        "employer_name_only_skills": [],
        "skill_match_percent": core_skill_percent,
        "mandatory_skill_coverage": core_skill_percent,
        "preferred_skill_coverage": 0,
        "core_skill_match_percent": core_skill_percent,
        "matched_core_skill_groups": [group for group, result in group_results.items() if result["score"] >= 0.35],
        "missing_core_skill_groups": missing_core_groups,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), experience_fit["relevant_years"]),
        "target_seniority_level": jd_profile.get("seniority_level"),
        "recommendation": recommendation,
        "label": label,
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "ranking_reason": ranking_reason,
        "experience_fit": experience_fit["label"],
        "project_strength_score": project_work_strength,
        "all_critical_requirements_met": not missing_core_groups,
        "jd_role_family": role_family,
        "jd_skill_groups": core_groups,
        "evidence_group_scores": group_results,
        "role_relevance_label": parsed.get("experience_relevance_label") or "",
        "experience_fit_label": experience_fit["label"],
        "scoring_breakdown": {
            "full_stack_group_component": round(core_skill_percent * 0.35, 2),
            "project_work_component": round(project_work_strength * 0.25, 2),
            "experience_fit_component": round(experience_fit["score"] * 0.15, 2),
            "role_relevance_component": round(role_relevance * 0.15, 2),
            "deployment_tools_component": round(deployment_score * 0.05, 2),
            "dotnet_weights_applied": dotnet_target,
            "mandatory_skill_coverage_component": round(core_skill_percent * (0.40 if dotnet_target else 0.35), 2),
            "seniority_component": round(seniority_score * 0.10, 2) if dotnet_target else 0,
            "good_to_have_component": round(good_to_have_score * 0.05, 2) if dotnet_target else 0,
            "evidence_group_scores": group_results,
            "missing_core_skill_groups": missing_core_groups,
            "score_caps_applied": caps,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("current_title") or parsed.get("designation") or "",
            "target_role_alignment": "strong" if role_relevance >= 75 else "partial" if role_relevance >= 45 else "weak",
            "total_experience_years": experience_fit["total_years"],
            "jd_relevant_experience_years": experience_fit["relevant_years"],
            "seniority_fit": experience_fit["label"],
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "label": label,
            "matched_skills": matched_skill_evidence,
            "missing_or_weak_skills": missing_skills,
            "risk_flags": risk_flags,
            "parser_quality_flags": parsed.get("parser_quality_flags") or [],
        },
    }


def _score_candidate_backend(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    candidate_skills = normalize_skill_list(parsed.get("key_skills", []))
    core_groups = jd_profile.get("core_skill_groups") or {}
    if not core_groups:
        core_groups = {
            "backend_path": ["Node.js", "Express", "Python", "Django", "FastAPI", "Flask", "Java", "Spring Boot", "PHP", "Laravel"],
            "api_logic": ["REST API", "GraphQL", "CRUD", "API Integration", "Business Logic"],
            "database": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "SQL Server", "Database Design"],
            "api_auth": ["JWT", "OAuth", "Spring Security", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Auth0", "AWS Cognito", "Clerk Auth", "Password Hashing", "Access Control", "Token Auth", "MFA"],
            "tooling_deployment": ["Git", "GitHub", "Postman", "Swagger", "OpenAPI", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Render", "Nginx", "Linux", "CI/CD"],
            "reliability_security": ["Logging", "Error Handling", "Validation", "Rate Limiting", "Security"],
        }

    core_groups = {
        group: options
        for group, options in core_groups.items()
        if group in BACKEND_GROUP_WEIGHTS
    }
    group_results = {
        group: _full_stack_group_score(group, options, parsed, resume_text, candidate_skills)
        for group, options in core_groups.items()
    }

    weighted_core = 0.0
    total_weight = 0.0
    for group, weight in BACKEND_GROUP_WEIGHTS.items():
        if group not in group_results:
            continue
        weighted_core += group_results[group]["score"] * weight
        total_weight += weight
    core_skill_percent = round((weighted_core / max(total_weight, 0.01)) * 100, 2)
    missing_core_groups = [
        group for group, result in group_results.items()
        if result["score"] < 0.35
    ]

    matched_skill_evidence = []
    matched_skills = []
    for result in group_results.values():
        matched_skills.extend(result.get("matched") or [])
        matched_skill_evidence.extend(result.get("evidence") or [])
    matched_skills = normalize_skill_list(matched_skills)

    project_work_strength = _backend_project_work_strength(parsed, resume_text)
    experience_fit = _backend_experience_fit(parsed, jd_profile)
    designation = str(parsed.get("designation") or parsed.get("current_title") or "")
    role_relevance = max(
        _safe_float(parsed.get("role_relevance_score")),
        90 if re.search(r"\b(back[-\s]?end|backend\s+developer|java\s+developer|spring\s+boot|api\s+developer)\b", designation, re.I) else 0,
        76 if re.search(r"\b(software\s+(?:engineer|developer)|sde)\b", designation, re.I) and project_work_strength >= 45 else 0,
    )

    technical_match_score = round(core_skill_percent * 0.72 + project_work_strength * 0.28, 2)
    experience_fit_score = experience_fit["score"]
    final_score = (
        core_skill_percent * 0.42
        + project_work_strength * 0.23
        + experience_fit_score * 0.17
        + role_relevance * 0.10
        + _safe_float(parsed.get("parser_quality_score"), parsed.get("resume_quality_score") or 70) * 0.08
    )

    risk_flags = []
    recruiter_flags = []
    caps = []
    professional_years = _safe_float(parsed.get("professional_role_experience_years"))
    project_only = _safe_float(parsed.get("project_only_exposure"))
    has_professional_backend = experience_fit["relevant_years"] >= 1 or professional_years >= 1
    strong_project_only = project_work_strength >= 55 and project_only and not has_professional_backend

    if missing_core_groups:
        _append_unique(risk_flags, ["missing_core_skill_groups"])
        _append_unique(recruiter_flags, ["missing_core_skills"])
    if experience_fit["under_experienced"]:
        _append_unique(recruiter_flags, ["under_experienced"])
    if experience_fit["overqualified"]:
        _append_unique(recruiter_flags, ["overqualified", "senior_profile", "overqualified_review"])
        if experience_fit["label"] in {"senior_overqualified", "overqualified_review"}:
            _append_unique(risk_flags, ["overqualified_review"])
    if project_work_strength >= 55:
        _append_unique(recruiter_flags, ["backend_project_evidence"])
    if strong_project_only:
        _append_unique(recruiter_flags, ["project_strong", "junior_project_review"])
        _append_unique(risk_flags, ["project_only_exposure"])

    if len(missing_core_groups) >= 3:
        caps.append({"cap": 58, "reason": "Three or more backend core groups are missing."})
    elif len(missing_core_groups) >= 2:
        caps.append({"cap": 68, "reason": "Two backend core groups need validation."})
    if experience_fit["label"] == "fresher_or_intern_risk" and not strong_project_only:
        caps.append({"cap": 58, "reason": "No proven professional backend experience; recruiter review required."})
    elif strong_project_only:
        caps.append({"cap": 74, "reason": "Strong backend projects found, but professional experience is not proven."})
    if experience_fit["label"] == "senior_overqualified":
        caps.append({"cap": 78, "reason": "Senior/overqualified for this 1-3 year backend role; recruiter review recommended."})
    elif experience_fit["label"] == "overqualified_review":
        caps.append({"cap": 82, "reason": "Above target experience range for this 1-3 year backend role."})
    if parsed.get("parser_quality_action") == "manual_review_required":
        caps.append({"cap": 58, "reason": "Parser quality requires manual review."})
        _append_unique(risk_flags, ["parser_quality"])
        _append_unique(recruiter_flags, ["parser_manual_review"])

    for cap in caps:
        final_score = min(final_score, cap["cap"])

    final_score = round(max(0, min(100, final_score)), 2)
    confidence = round(min(100, 35 + core_skill_percent * 0.26 + project_work_strength * 0.22 + role_relevance * 0.16 + _safe_float(parsed.get("resume_quality_score"), 75) * 0.12), 2)
    rank_score = round(min(100, final_score + (3 if confidence >= 65 and not risk_flags else 0)), 2)

    if (
        final_score >= 78
        and core_skill_percent >= 68
        and has_professional_backend
        and not experience_fit["overqualified"]
        and len(missing_core_groups) <= 1
    ):
        recommendation = "shortlisted"
        _append_unique(recruiter_flags, ["strong_match" if final_score >= 88 else "good_match"])
    elif final_score < 42 or (len(missing_core_groups) >= 3 and final_score < 58):
        recommendation = "rejected"
    else:
        recommendation = "in_review"

    if experience_fit["overqualified"] or strong_project_only:
        recommendation = "in_review"

    missing_skills = [group.replace("_", " ").title() for group in missing_core_groups]
    label = (
        "Strong fit" if recommendation == "shortlisted" and final_score >= 84
        else "Good match" if recommendation == "shortlisted"
        else "Overqualified review" if experience_fit["overqualified"]
        else "Junior/project review" if strong_project_only or experience_fit["under_experienced"]
        else "Weak match" if recommendation == "rejected"
        else "Review required"
    )
    ranking_reason = (
        f"Rank score {rank_score}/100 with {confidence}% confidence: "
        f"{core_skill_percent}% backend group coverage, {experience_fit['relevant_years']:g}/{experience_fit['total_years']:g} relevant/total years, "
        f"role relevance {role_relevance:g}/100."
    )
    if missing_core_groups:
        ranking_reason += f" Missing backend groups: {', '.join(missing_core_groups)}."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    return {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": "strong_match" if final_score >= 84 else "good_match" if final_score >= 68 else "review" if final_score >= 45 else "low_match",
        "skill_score": round(core_skill_percent * 0.42, 2),
        "experience_score": round(experience_fit_score * 0.17, 2),
        "semantic_score": parsed.get("semantic_score", 0),
        "semantic_weight": 0,
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(role_relevance * 0.10, 2),
        "education_score": 0,
        "technical_match_score": technical_match_score,
        "experience_fit_score": experience_fit_score,
        "matched_skills": matched_skills,
        "direct_matched_skills": matched_skills,
        "transferable_skills": [],
        "preferred_matched_skills": [],
        "missing_skills": missing_skills,
        "skill_evidence_depth": {skill: evidence.get("depth", evidence.get("evidence_level", "")) for evidence in matched_skill_evidence for skill in [evidence.get("skill")] if skill},
        "skill_evidence": {skill: evidence for evidence in matched_skill_evidence for skill in [evidence.get("skill")] if skill},
        "matched_skill_evidence": matched_skill_evidence,
        "missing_or_weak_skills": [
            {"skill": group.replace("_", " ").title(), "status": "missing", "evidence_level": "missing"}
            for group in missing_core_groups
        ],
        "employer_name_only_skills": [],
        "skill_match_percent": core_skill_percent,
        "mandatory_skill_coverage": core_skill_percent,
        "preferred_skill_coverage": 0,
        "core_skill_match_percent": core_skill_percent,
        "matched_core_skill_groups": [group for group, result in group_results.items() if result["score"] >= 0.35],
        "missing_core_skill_groups": missing_core_groups,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), experience_fit["relevant_years"]),
        "target_seniority_level": jd_profile.get("seniority_level"),
        "recommendation": recommendation,
        "label": label,
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "ranking_reason": ranking_reason,
        "experience_fit": experience_fit["label"],
        "project_strength_score": project_work_strength,
        "all_critical_requirements_met": not missing_core_groups,
        "jd_role_family": "software_backend",
        "jd_skill_groups": core_groups,
        "evidence_group_scores": group_results,
        "role_relevance_label": parsed.get("experience_relevance_label") or "",
        "experience_fit_label": experience_fit["label"],
        "scoring_breakdown": {
            "technical_match_score": technical_match_score,
            "experience_fit_score": experience_fit_score,
            "backend_group_component": round(core_skill_percent * 0.42, 2),
            "project_work_component": round(project_work_strength * 0.23, 2),
            "experience_fit_component": round(experience_fit_score * 0.17, 2),
            "role_relevance_component": round(role_relevance * 0.10, 2),
            "evidence_group_scores": group_results,
            "missing_core_skill_groups": missing_core_groups,
            "score_caps_applied": caps,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("current_title") or parsed.get("designation") or "",
            "target_role_alignment": "strong" if role_relevance >= 75 else "partial" if role_relevance >= 45 else "weak",
            "total_experience_years": experience_fit["total_years"],
            "jd_relevant_experience_years": experience_fit["relevant_years"],
            "seniority_fit": experience_fit["label"],
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "label": label,
            "matched_skills": matched_skill_evidence,
            "missing_or_weak_skills": missing_skills,
            "risk_flags": risk_flags,
            "parser_quality_flags": parsed.get("parser_quality_flags") or [],
        },
    }


def _recommendation_label(recommendation, recruiter_flags, risk_flags, final_score, mandatory_coverage, seniority_fit):
    flags = set(recruiter_flags or []) | set(risk_flags or [])
    if "below_jd_experience_range" in flags or "no_valid_professional_work_dates" in flags:
        if "project_only_exposure" in flags:
            return "Project-only match"
        if "training_only_exposure" in flags:
            return "Training-only exposure"
        return "Below experience range"
    if "primary_role_mismatch" in flags or "qa_transferable_only" in flags or "qa_role_identity_gap" in flags:
        return "Role mismatch review"
    if "employer_name_only_match" in flags:
        return "Low match"
    if "missing_core_skill_groups" in flags or "missing_mandatory_skills" in flags:
        return "Rejected - missing core skills" if recommendation == "rejected" else "Skill validation needed"
    if "over_jd_experience_range" in flags or seniority_fit == "over":
        return "Overqualified review"
    if seniority_fit == "under" and final_score >= 65:
        return "Under-experienced but technically relevant"
    if "seniority_experience_gap" in flags and final_score >= 65:
        return "Strong technical match but below seniority"
    if "training_only_exposure" in flags:
        return "Training-only exposure"
    if "project_only_exposure" in flags:
        return "Project-only match"
    if recommendation == "rejected":
        return "Low match" if mandatory_coverage >= 25 else "Rejected - no relevant experience"
    if recommendation == "shortlisted":
        return "Strong match" if final_score >= 88 else "Good match"
    if final_score >= 70:
        return "Moderate match"
    return "Review required"


APPLIED_ML_GROUP_WEIGHTS = {
    "ml_dl_fundamentals": 0.20,
    "cv_ocr_document_ai": 0.30,
    "llm_nlp_vlm_multimodal": 0.25,
    "production_ml_mlops": 0.20,
}

APPLIED_ML_GROUP_PATTERNS = {
    "ml_dl_fundamentals": re.compile(
        r"\b(machine\s+learning|deep\s+learning|model\s+(?:training|evaluation|benchmarking)|"
        r"regression\s+testing|pytorch|tensorflow|scikit[-\s]?learn|keras|xgboost|random\s+forest)\b",
        re.I,
    ),
    "cv_ocr_document_ai": re.compile(
        r"\b(computer\s+vision|ocr|document\s+(?:ai|intelligence|extraction|understanding)|"
        r"opencv|image\s+(?:processing|enhancement|classification|recognition)|object\s+detection|"
        r"segmentation|yolo(?:v\d+)?|r[-\s]?cnn|faster\s+r[-\s]?cnn|mask\s+r[-\s]?cnn|"
        r"vit|monai|medical\s+imaging|mri|ct\s+segmentation|retinal|ultrasound|"
        r"paddle\s*ocr|tesseract|trocr|doctr|easy\s*ocr|omr|handwriting\s+recognition|"
        r"form\s+recognition|table\s+(?:recognition|extraction|structure)|receipt\s+extraction|"
        r"invoice\s+extraction|(?:vial\s+)?label\s+extraction|qr\s+extraction|lcd\s+panel\s+extraction|"
        r"document\s+vqa|document\s+visual\s+question\s+answering|layout\s+detection|real[-\s]?esrgan)\b",
        re.I,
    ),
    "llm_nlp_vlm_multimodal": re.compile(
        r"\b(nlp|natural\s+language\s+processing|llms?|large\s+language\s+models?|generative\s+ai|genai|"
        r"rag|langchain|llama\s*index|gpt|llama|mistral|mixtral|gemini|deepseek|hugging\s*face|"
        r"transformers?|vllm|prompt\s+engineering|fine[-\s]?tun(?:e|ed|ing)|lora|qlora|"
        r"vector\s+(?:db|database)|embeddings?|chroma|pinecone|faiss|multimodal|multi[-\s]?modal|"
        r"vision[-\s]?language\s+models?|vlms?|clip|dino|blip)\b",
        re.I,
    ),
    "production_ml_mlops": re.compile(
        r"\b(mlops|llmops|mlflow|docker|kubernetes|fastapi|flask|model\s+(?:deployment|serving|lifecycle)|"
        r"inference\s+(?:pipeline|service|optimization)|ci/cd|github\s+actions|sagemaker|bedrock|"
        r"vertex\s+ai|azure\s+ml|cloud\s+run|lambda|production|deployed|monitoring|latency\s+optimization|"
        r"cost\s+optimization|autoscaling|api\s+deployment)\b",
        re.I,
    ),
}


PRODUCT_ARCHITECT_GROUP_WEIGHTS = {
    "architecture_system_design": 0.30,
    "hands_on_backend": 0.25,
    "product_startup_ownership": 0.20,
    "technical_leadership": 0.15,
    "devops_delivery": 0.05,
}


PRODUCT_ARCHITECT_GROUP_PATTERNS = {
    "architecture_system_design": re.compile(
        r"\b(system\s+design|software\s+architecture|backend\s+architecture|api\s+design|"
        r"distributed\s+systems?|scalab(?:le|ility)|performance\s+optimization|security|"
        r"high[-\s]?scale\s+systems?|architected|architecture\s+(?:decisions?|patterns?))\b",
        re.I,
    ),
    "hands_on_backend": re.compile(
        r"\b(node(?:\.js)?|python|express(?:\.js)?|fastapi|django|rest(?:ful)?\s+apis?|"
        r"sql|postgres(?:ql)?|mongodb|database\s+design|microservices?|backend\s+(?:api|service|services))\b",
        re.I,
    ),
    "devops_delivery": re.compile(
        r"\b(docker(?:i[sz]ed)?|kubernetes|ci/cd|github\s+actions|jenkins|aws|azure|cloud\s+architecture|"
        r"deployment|deployed|containeri[sz]ed|release\s+pipeline)\b",
        re.I,
    ),
    "product_startup_ownership": re.compile(
        r"\b(product\s+engineering|product\s+startup|startup|0[-\s]?to[-\s]?1|zero\s+to\s+one|"
        r"b2b\s+saas|founder|ownership|owned|end[-\s]?to[-\s]?end|product\s+roadmap|"
        r"built\s+(?:from\s+scratch|0))\b",
        re.I,
    ),
    "technical_leadership": re.compile(
        r"\b(technical\s+leadership|tech\s+lead|code\s+reviews?|mentored|mentorship|"
        r"architecture\s+review|design\s+review|led\s+(?:team|engineers?)|guided|"
        r"reviewed\s+code|coding\s+standards)\b",
        re.I,
    ),
}


PRODUCT_ARCHITECT_WRONG_ROLE_PATTERNS = {
    "civil_construction_architect": re.compile(
        r"\b(civil|construction|building|interior|landscape|urban|real\s+estate)\s+architect\b|"
        r"\b(autocad|revit|bim|site\s+supervision|floor\s+plan|structural\s+design)\b",
        re.I,
    ),
    "project_delivery_manager": re.compile(
        r"\b(project\s+manager|delivery\s+manager|scrum\s+master|program\s+manager|pmo|"
        r"people\s+manager|resource\s+manager|non[-\s]?technical\s+manager)\b",
        re.I,
    ),
    "cloud_only_architect": re.compile(
        r"\b(cloud\s+architect|aws\s+architect|azure\s+architect|infrastructure\s+architect|"
        r"devops\s+architect|solution\s+architect)\b",
        re.I,
    ),
    "enterprise_no_coding": re.compile(
        r"\b(enterprise\s+architect|governance|togaf|roadmap|stakeholder\s+alignment|vendor\s+management)\b",
        re.I,
    ),
}

M365_MIGRATION_GROUP_WEIGHTS = {
    "m365_migration": 0.25,
    "exchange_migration": 0.15,
    "workload_migration": 0.15,
    "tenant_identity": 0.15,
    "tools_scripting": 0.15,
    "seniority_delivery": 0.10,
}

M365_MIGRATION_GROUP_PATTERNS = {
    "m365_migration": re.compile(
        r"\b(microsoft\s+365\s+migration|m365\s+migration|office\s+365\s+migration|o365\s+migration|"
        r"tenant[-\s]?to[-\s]?tenant\s+migration|cross[-\s]?tenant\s+migration|workload\s+migration|"
        r"mailbox\s+migration|migration\s+batches|cutover|coexistence|migration\s+waves?)\b",
        re.I,
    ),
    "exchange_migration": re.compile(
        r"\b(exchange\s+online\s+migration|on[-\s]?prem(?:ises)?\s+exchange\s+migration|"
        r"exchange\s+server\s+migration|hybrid\s+exchange|exchange\s+online|mailbox\s+migration|"
        r"eac|exchange\s+powershell|mx\s+records|autodiscover|smtp\s+routing)\b",
        re.I,
    ),
    "workload_migration": re.compile(
        r"\b(teams\s+migration|sharepoint\s+migration|onedrive\s+migration|permissions\s+migration|"
        r"site\s+migration|document\s+library\s+migration|teams\s+channels?|sharepoint\s+online)\b",
        re.I,
    ),
    "tenant_identity": re.compile(
        r"\b(tenant[-\s]?to[-\s]?tenant|cross[-\s]?tenant|source\s+tenant|target\s+tenant|domain\s+move|"
        r"identity\s+mapping|entra\s+id|azure\s+ad|azure\s+active\s+directory|azure\s+ad\s+connect|"
        r"identity\s+sync|conditional\s+access|mfa)\b",
        re.I,
    ),
    "tools_scripting": re.compile(
        r"\b(quest\s+odm|quest\s+on\s+demand\s+migration|powershell(?:\s+scripting)?|"
        r"migrationwiz|bittitan|sharegate|avepoint|microsoft\s+graph|automation\s+scripts?)\b",
        re.I,
    ),
    "seniority_delivery": re.compile(
        r"\b(sme|consultant|lead|senior\s+engineer|enterprise\s+migration|migration\s+planning|"
        r"cutover\s+support|hypercare|post[-\s]?migration\s+validation|rollback\s+plan|"
        r"stakeholder\s+coordination|us\s+shift)\b",
        re.I,
    ),
}

M365_MIGRATION_PROOF_RE = re.compile(
    r"\b(migration|migrate[sd]?|migrating|tenant[-\s]?to[-\s]?tenant|cross[-\s]?tenant|"
    r"cutover|coexistence|migration\s+batches|quest\s+odm|migrationwiz|bittitan|"
    r"sharegate|avepoint|post[-\s]?migration|hypercare)\b",
    re.I,
)

M365_WRONG_ROLE_PATTERNS = {
    "generic_support": re.compile(
        r"\b(help\s*desk|service\s+desk|desktop\s+support|technical\s+support|it\s+support|"
        r"ticket(?:ing)?|windows\s+troubleshooting|printer\s+support|hardware\s+support)\b",
        re.I,
    ),
    "generic_admin_without_migration": re.compile(
        r"\b(m365|microsoft\s+365|office\s+365|o365|exchange|teams|sharepoint)\s+"
        r"(?:administrator|admin|support)\b|"
        r"\b(users?|licenses?|mailboxes?|groups?|permissions?)\s+(?:management|administration|provisioning)\b",
        re.I,
    ),
    "azure_only": re.compile(
        r"\b(azure\s+(?:cloud|infrastructure|devops|engineer|administrator)|terraform|aks|vnet|"
        r"virtual\s+machines?|landing\s+zones?|resource\s+groups?)\b",
        re.I,
    ),
    "sharepoint_dev_only": re.compile(
        r"\b(sharepoint\s+developer|spfx|power\s*apps?|power\s+automate|workflow\s+development|"
        r"webparts?|canvas\s+apps?)\b",
        re.I,
    ),
    "project_manager_only": re.compile(
        r"\b(project\s+manager|delivery\s+manager|program\s+manager|scrum\s+master|pmo|"
        r"resource\s+planning|status\s+reporting|project\s+governance)\b",
        re.I,
    ),
    "iam_only": re.compile(
        r"\b(iam\s+(?:engineer|analyst|administrator)|identity\s+governance|okta|sailpoint|"
        r"access\s+reviews?)\b",
        re.I,
    ),
}

AML_TM_GROUP_WEIGHTS = {
    "role_fit": 0.25,
    "transaction_monitoring": 0.12,
    "aml_investigations": 0.10,
    "case_management": 0.06,
    "sar_str": 0.07,
    "banking_exposure": 0.10,
    "nice_to_have": 0.05,
}

AML_TM_GROUP_PATTERNS = {
    "role_fit": re.compile(
        r"\b(aml\s+transaction\s+monitoring\s+(?:investigator|analyst|specialist|officer|l2)|"
        r"transaction\s+monitoring\s+(?:investigator|analyst|specialist|officer)|"
        r"aml\s+(?:case\s+)?investigator|(?:assist\.?\s+|assistant\s+)?aml\s+analyst(?:\s+ii|\s+i{1,3})?|"
        r"anti[-\s]?money\s+laundering\s+analyst|financial\s+crime\s+analyst|financial\s+crimes\s+specialist|"
        r"financial\s+crime\s+investigator|senior\s+aml\s+analyst|aml\s+compliance\s+(?:analyst|investigator))\b",
        re.I,
    ),
    "transaction_monitoring": re.compile(
        r"\b(aml\s+transaction\s+monitoring|transaction\s+monitoring|tm\s+alerts?|aml\s+alerts?|"
        r"monitoring\s+alerts?|escalated\s+alerts?|alert\s+investigation|transaction\s+review|"
        r"transaction\s+alerts?|monitoring\s+systems?|monitoring\s+techniques?|exception\s+reports?|"
        r"suspicious\s+transactions?|suspicious\s+transfers?|client\s+transactions?|flagged\s+(?:clients?|transactions?)|"
        r"high[-\s]?risk\s+(?:accounts?|transactions?)|processed\s+(?:and\s+analy[sz]ed\s+)?suspicious\s+transactions?|"
        r"verafin|actimize|global\s+radar|aci\s+worldwide|fico(?:[-\s]?based)?\s+monitoring\s+systems?|aml\s+software\s+(?:alerts?|program)|"
        r"suspicious\s+transaction\s+monitoring)\b",
        re.I,
    ),
    "aml_investigations": re.compile(
        r"\b(aml\s+investigations?|case\s+investigation|financial\s+crime\s+investigation|"
        r"money\s+laundering\s+investigation|suspicious\s+(?:activity|transaction)\s+investigation|"
        r"suspicious\s+(?:activity|transaction)\s+review|investigated\s+(?:accounts?|transactions?)|"
        r"investigat(?:e|ed|ing)\s+suspicious\s+(?:fraudulent\s+)?(?:behavior|activity|transactions?)|"
        r"high[-\s]?risk\s+account\s+investigation|detection\s+to\s+resolution|"
        r"evaluated\s+cases?\s+for\s+(?:closure|escalation)|case\s+(?:closure|escalation)|"
        r"further\s+investigation|investigation\s+unit|complex\s+aml\s+investigations?|"
        r"money\s+laundering|reported\s+suspicious\s+activities|identified\s+and\s+reported\s+\d+\+?\s+suspicious\s+activities)\b",
        re.I,
    ),
    "case_management": re.compile(
        r"\b(case\s+(?:management|handling|review|disposition|closure|narrative|documentation)|"
        r"managed\s+investigations?\s+from\s+detection\s+to\s+resolution|alert\s+closure|investigation\s+workflow|"
        r"evaluated\s+cases?|document(?:ed|ing)?\s+findings?|document\s+research\s+and\s+information|"
        r"detailed\s+(?:reports?|case\s+narratives?)|"
        r"prepared\s+detailed\s+suspicious\s+activity\s+reports?|verify\s+documentation|verified\s+documentation|"
        r"documentation\s+and\s+licensing|reporting\s+accuracy|investigation\s+time|"
        r"case\s+notes?|investigation\s+documentation|thorough\s+documentation|reports?\s+and\s+presentations|"
        r"reporting\s+of\s+suspicious\s+activities|successful\s+prosecutions|"
        r"summari[sz]ed\s+findings?|compiled\s+and\s+summari[sz]ed\s+findings?|narrative|"
        r"escalation\s+rationale|supporting\s+documentation|prepared\s+concise\s+case\s+notes)\b",
        re.I,
    ),
    "sar_str": re.compile(
        r"\b(uars?|sars?|strs?|suspicious\s+activity\s+reports?|suspicious\s+activity\s+reporting(?:\s+standards?)?|"
        r"suspicious\s+transaction\s+reports?|suspicious\s+transaction\s+reporting|"
        r"report(?:ed|ing)?\s+suspicious\s+activit(?:y|ies)|"
        r"sar\s+(?:filing|reporting|documentation|submissions?|process)|str\s+(?:filing|reporting|documentation|submissions?|process)|"
        r"fiu\s+reporting|financial\s+intelligence\s+unit|fincen\s+compliance|"
        r"prepared\s+(?:data\s+for\s+)?suspicious\s+activity\s+report\s+submissions?|"
        r"regulatory\s+reporting\s+for\s+suspicious\s+activity|regulatory\s+reporting)\b",
        re.I,
    ),
    "banking_exposure": re.compile(
        r"\b(retail\s+banking|commercial\s+banking|correspondent\s+banking|banking|banks?|financial\s+institution|bfsi|"
        r"financial\s+services|bank\s+accounts?|credit\s+card\s+transactions?|global\s+banking\s+and\s+markets|"
        r"department\s+of\s+banking|money\s+service\s+business(?:es)?|msbs?|financial\s+transactions?|"
        r"bank\s+secrecy\s+act|bsa)\b",
        re.I,
    ),
    "nice_to_have": re.compile(
        r"\b(kyc|cdd|edd|customer\s+due\s+diligence|enhanced\s+due\s+diligence|source\s+of\s+funds|"
        r"source\s+of\s+wealth|adverse\s+media|pep\s+screening|sanctions\s+screening|smurfing|layering|"
        r"structuring|money\s+mule|shell\s+compan(?:y|ies)|round\s+tripping|placement|integration|"
        r"terrorist\s+financing|ofac|314\(a\)|watch\s+list|high[-\s]?risk\s+clients?|msbs?|"
        r"us\s+aml|international\s+aml|verafin|actimize|global\s+radar|aci\s+worldwide|fico)\b",
        re.I,
    ),
}

AML_TM_CORE_PROOF_RE = re.compile(
    r"\b(aml\s+transaction\s+monitoring|transaction\s+monitoring|aml\s+alerts?|tm\s+alerts?|"
    r"aml\s+investigations?|alert\s+investigation|case\s+investigation|suspicious\s+(?:activity|transaction)\s+investigation|"
    r"suspicious\s+transaction\s+monitoring|sar|str)\b",
    re.I,
)

AML_TM_KYC_RE = re.compile(
    r"\b(kyc|cdd|edd|customer\s+due\s+diligence|enhanced\s+due\s+diligence|source\s+of\s+funds|"
    r"source\s+of\s+wealth|adverse\s+media|pep\s+screening|sanctions\s+screening)\b",
    re.I,
)

AML_TM_GENERIC_BANKING_RE = re.compile(
    r"\b(banking\s+operations|branch\s+banking|loan\s+officer|customer\s+support|customer\s+service|"
    r"account\s+opening|back\s+office|banking\s+process|retail\s+banking|commercial\s+banking)\b",
    re.I,
)

AML_TM_FRAUD_RE = re.compile(r"\b(fraud\s+(?:analyst|investigator|investigation)|fraud\s+alerts?|fraud\s+monitoring)\b", re.I)

AML_TM_TOOL_RE = re.compile(
    r"\b(actimize|global\s+radar|aci\s+worldwide|fico(?:[-\s]?based)?\s+monitoring\s+systems?|"
    r"verafin|oracle\s+financial\s+services|sas|palantir|eastnets|safewatch|aml\s+software|monitoring\s+software|monitoring\s+systems?)\b",
    re.I,
)

AML_TM_ROLE_EVIDENCE_RE = re.compile(
    r"\b(financial\s+crime\s+analyst|financial\s+crimes\s+specialist|aml\s+analyst|"
    r"anti[-\s]?money\s+laundering\s+analyst|transaction\s+monitoring\s+analyst|"
    r"aml\s+compliance\s+analyst|aml\s+transaction\s+monitoring\s+(?:investigator|analyst|specialist))\b",
    re.I,
)

AML_TM_TRANSACTION_EVIDENCE_RE = re.compile(
    r"\b(suspicious\s+transactions?|transaction\s+alerts?|aml\s+alerts?|monitoring\s+systems?|"
    r"suspicious\s+transfers?|processed\s+(?:and\s+analy[sz]ed\s+)?suspicious\s+transactions?|"
    r"transaction\s+review|suspicious\s+account\s+activity|transaction\s+monitoring)\b",
    re.I,
)

AML_TM_FCRM_EVIDENCE_RE = re.compile(
    r"\b(sars?|strs?|suspicious\s+activity\s+reports?|suspicious\s+activity\s+reporting|"
    r"suspicious\s+transaction\s+reports?|suspicious\s+transaction\s+reporting|bsa\s*/?\s*aml|"
    r"bank\s+secrecy\s+act|aml\s+investigations?|transaction\s+monitoring|tm\s+alerts?|"
    r"transaction\s+alerts?|monitor\s+suspicious\s+account\s+activity|suspicious\s+account\s+activity|"
    r"suspicious\s+(?:activity|transaction|transfer)s?|financial\s+crime\s+(?:analyst|investigator|activity)|"
    r"anti[-\s]?money\s+laundering\s+(?:analyst|division)|aml\s+(?:analyst|division|alerts?))\b",
    re.I,
)

AML_TM_SYNTHETIC_PROFILE_RE = re.compile(
    r"\b(ai\s+digital\s+worker|digital\s+worker|ai\s+worker|as\s+an\s+ai\b|"
    r"trained\s+to\s+complete\s+transaction\s+monitoring|system\s+integrations\s+responsibilities|"
    r"no\s+human\s+employment\s+history)\b",
    re.I,
)

AML_TM_JD_UPLOAD_MARKER_RE = re.compile(
    r"\b(job\s*description|job\s+title|purpose\s+of\s+role|primary\s+responsibilities(?:\s+of\s+role)?|"
    r"person\s+specification|department|direct\s+reports|budget\s+responsibility|certified\s+person)\b",
    re.I,
)

AML_TM_RESUME_IDENTITY_RE = re.compile(
    r"\b(work\s+experience|professional\s+experience|employment\s+history|education|skills|"
    r"resume|curriculum\s+vitae|linkedin|email|phone)\b",
    re.I,
)

AML_TM_WRONG_ROLE_PATTERNS = {
    "data_analyst_only": re.compile(r"\b(data\s+analyst|sql|power\s*bi|tableau|dashboard|dashboards?|business\s+intelligence)\b", re.I),
    "business_analyst_only": re.compile(r"\b(business\s+analyst|requirements?\s+gathering|brd|frd|uat|user\s+stories)\b", re.I),
    "financial_analyst_only": re.compile(r"\b(financial\s+analyst|budgeting|forecasting|variance\s+analysis|financial\s+model(?:ing)?)\b", re.I),
    "risk_or_compliance_only": re.compile(r"\b(risk\s+analyst|compliance\s+officer|policy\s+compliance|operational\s+risk)\b", re.I),
}


def _applied_ml_text_sections(parsed, resume_text):
    work = []
    projects = []
    for job in parsed.get("experience") or []:
        if isinstance(job, dict):
            work.append(" ".join(str(job.get(key) or "") for key in ("role", "company_name", "description")))
    for project in parsed.get("projects") or []:
        if isinstance(project, dict):
            projects.append(" ".join(str(value or "") for value in project.values()))
        else:
            projects.append(str(project or ""))
    skills = " ".join(str(skill or "") for skill in parsed.get("key_skills") or [])
    return {
        "work": "\n".join(work),
        "projects": "\n".join(projects),
        "skills": skills,
        "all": "\n".join([resume_text or "", "\n".join(work), "\n".join(projects), skills]),
    }


def _group_strength_from_text(group, sections):
    pattern = APPLIED_ML_GROUP_PATTERNS[group]
    work_hits = sorted({match.group(0) for match in pattern.finditer(sections["work"])})
    project_hits = sorted({match.group(0) for match in pattern.finditer(sections["projects"])})
    skill_hits = sorted({match.group(0) for match in pattern.finditer(sections["skills"])})
    all_hits = sorted({match.group(0) for match in pattern.finditer(sections["all"])})

    if work_hits:
        level = "professional_strong" if _strong_context(sections["work"]) else "professional_weak"
        score = min(100, 52 + len(work_hits) * 12 + (12 if level == "professional_strong" else 0))
        source = "work_experience"
    elif project_hits:
        level = "project_strong" if _strong_context(sections["projects"]) else "project_weak"
        score = min(82, 38 + len(project_hits) * 10 + (10 if level == "project_strong" else 0))
        source = "project"
    elif skill_hits:
        level = "keyword_only"
        score = min(38, 16 + len(skill_hits) * 5)
        source = "skills_section"
    elif all_hits:
        level = "keyword_only"
        score = min(32, 14 + len(all_hits) * 4)
        source = "resume_text"
    else:
        level = "missing"
        score = 0
        source = ""

    return {
        "group": group,
        "score": round(score, 2),
        "evidence_level": level,
        "source": source,
        "matched_terms": all_hits[:12],
        "matched": all_hits[:12],
        "strong": score >= 60 and level in {"professional_strong", "professional_weak", "project_strong"},
        "missing": score <= 0,
    }


def _applied_ml_experience_fit(parsed, jd_profile):
    relevant = _safe_float(parsed.get("relevant_experience_years"))
    total = _safe_float(parsed.get("total_experience_years"))
    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    if relevant <= 0 and role_relevance >= 65:
        relevant = min(total, 1.0) if total else 0.5
    min_years = _safe_float(jd_profile.get("min_experience_years")) or 4.0
    max_years = _safe_float(jd_profile.get("max_experience_years")) or 6.0
    if relevant <= 0:
        return {"score": 25, "label": "unproven", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < 3:
        return {"score": 42, "label": "under_experienced", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < min_years:
        return {"score": 72, "label": "slight_experience_gap", "relevant_years": relevant, "total_years": total, "fit": "slight_under"}
    if relevant <= max_years:
        return {"score": 100, "label": "ideal_4_6_years", "relevant_years": relevant, "total_years": total, "fit": "within"}
    if relevant <= 8:
        return {"score": 78, "label": "senior_review", "relevant_years": relevant, "total_years": total, "fit": "over"}
    return {"score": 58, "label": "over_experienced", "relevant_years": relevant, "total_years": total, "fit": "over"}


def _score_candidate_applied_ml(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    parsed = parsed or {}
    sections = _applied_ml_text_sections(parsed, resume_text)
    group_results = {
        group: _group_strength_from_text(group, sections)
        for group in APPLIED_ML_GROUP_WEIGHTS
    }
    weighted_groups = sum(group_results[group]["score"] * weight for group, weight in APPLIED_ML_GROUP_WEIGHTS.items())
    experience_fit = _applied_ml_experience_fit(parsed, jd_profile)
    final_score = weighted_groups + experience_fit["score"] * 0.05

    mandatory_groups = ["cv_ocr_document_ai", "llm_nlp_vlm_multimodal", "production_ml_mlops"]
    strong_mandatory = [group for group in mandatory_groups if group_results[group]["strong"]]
    missing_mandatory = [group for group in mandatory_groups if group_results[group]["score"] < 25]
    weak_mandatory = [group for group in mandatory_groups if group not in missing_mandatory and group_results[group]["score"] < 60]
    caps = []
    risk_flags = []
    recruiter_flags = []

    def cap_at(limit, reason, flag=None, risk=None):
        nonlocal final_score
        if final_score > limit:
            final_score = limit
        caps.append({"cap": limit, "reason": reason})
        if flag:
            _append_unique(recruiter_flags, [flag])
        if risk:
            _append_unique(risk_flags, [risk])

    if "cv_ocr_document_ai" in missing_mandatory:
        cap_at(70, "Computer Vision/OCR/Document AI evidence is missing for this Applied ML JD.", "missing_cv_ocr_document_ai", "mandatory_group_gap")
    if "llm_nlp_vlm_multimodal" in missing_mandatory:
        cap_at(72, "LLM/NLP/VLM/Multimodal evidence is missing for this Applied ML JD.", "missing_llm_vlm", "mandatory_group_gap")
    if "production_ml_mlops" in missing_mandatory:
        cap_at(75, "Production ML/MLOps evidence is missing for this Applied ML JD.", "missing_production_ml", "mandatory_group_gap")
    if len(strong_mandatory) <= 1:
        cap_at(62, "Only one Applied ML mandatory group has strong evidence.", "applied_ml_mandatory_group_gap", "mandatory_group_gap")
    elif weak_mandatory:
        cap_at(78, "Two mandatory groups are strong but at least one Applied ML group needs validation.", "applied_ml_partial_group_gap", "mandatory_group_gap")

    proven_groups = [
        group for group, result in group_results.items()
        if result["evidence_level"] in {"professional_strong", "professional_weak", "project_strong", "project_weak"}
    ]
    keyword_groups = [
        group for group, result in group_results.items()
        if result["evidence_level"] == "keyword_only"
    ]
    if keyword_groups and len(keyword_groups) >= max(1, len(proven_groups)):
        cap_at(60, "Applied ML match is mostly keyword-only with weak work/project proof.", "skill_match_mostly_listed_only", "keyword_only_match")

    generic_data_only = (
        group_results["ml_dl_fundamentals"]["score"] < 45
        and all(group_results[group]["score"] < 25 for group in mandatory_groups)
        and re.search(r"\b(sql|excel|power\s*bi|tableau|dashboards?|reporting|a/b\s+testing|regression|statistics)\b", sections["all"], re.I)
    )
    if generic_data_only:
        cap_at(45, "Generic analytics/data-science overlap without Applied ML core evidence.", "generic_data_profile", "role_relevance")
    if group_results["ml_dl_fundamentals"]["score"] >= 60 and group_results["cv_ocr_document_ai"]["score"] < 25 and group_results["llm_nlp_vlm_multimodal"]["score"] < 25:
        cap_at(55, "Pure ML evidence without OCR/CV/LLM depth cannot rank highly for this Applied ML JD.", "pure_ml_without_applied_depth", "mandatory_group_gap")
    if experience_fit["fit"] == "under":
        cap_at(70, "JD-related Applied ML experience is below the target range.", "under_experienced", "below_jd_experience_range")
    elif experience_fit["fit"] == "over":
        _append_unique(recruiter_flags, ["over_experienced"])
        _append_unique(risk_flags, ["over_jd_experience_range"])

    final_score = round(max(0, min(100, final_score)), 2)
    mandatory_coverage = round((sum(group_results[group]["score"] for group in mandatory_groups) / 300) * 100, 2)
    core_percent = round((sum(group["score"] for group in group_results.values()) / 400) * 100, 2)
    confidence = round(min(100, 38 + core_percent * 0.25 + mandatory_coverage * 0.30 + _safe_float(parsed.get("parser_quality_score"), parsed.get("resume_quality_score") or 70) * 0.18), 2)
    rank_score = round(min(100, final_score + (3 if not risk_flags and confidence >= 70 else 0)), 2)

    if final_score >= 80 and not missing_mandatory and len(strong_mandatory) == 3:
        recommendation = "shortlisted"
        label = "Strong Match"
        _append_unique(recruiter_flags, ["strong_match"])
    elif final_score >= 70 and len(strong_mandatory) >= 2 and not missing_mandatory:
        recommendation = "shortlisted"
        label = "Good Match"
        _append_unique(recruiter_flags, ["good_match"])
    elif final_score < 50:
        recommendation = "rejected"
        label = "Low Fit"
    elif experience_fit["fit"] == "under":
        recommendation = "in_review"
        label = "Experience Gap"
    elif experience_fit["fit"] == "over":
        recommendation = "in_review"
        label = "Overqualified Review"
    else:
        recommendation = "in_review"
        label = "Partial Fit - Validate Core Skills" if missing_mandatory or weak_mandatory else "Review Required"

    matched_groups = {group: result for group, result in group_results.items() if result["score"] >= 25}
    matched_skills = normalize_skill_list([
        term
        for result in group_results.values()
        for term in result.get("matched_terms") or []
    ])
    missing_skills = [group.replace("_", " ").title() for group in missing_mandatory + weak_mandatory]
    ranking_reason = (
        f"Rank score {rank_score}/100: Applied ML groups "
        f"ML/DL {group_results['ml_dl_fundamentals']['score']}/100, "
        f"CV/OCR/Document AI {group_results['cv_ocr_document_ai']['score']}/100, "
        f"LLM/VLM {group_results['llm_nlp_vlm_multimodal']['score']}/100, "
        f"Production ML {group_results['production_ml_mlops']['score']}/100, "
        f"{experience_fit['relevant_years']:g}/{experience_fit['total_years']:g} relevant/total years."
    )
    if missing_mandatory:
        ranking_reason += f" Missing mandatory groups: {', '.join(missing_mandatory)}."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    result = {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": "strong_match" if final_score >= 80 else "good_match" if final_score >= 70 else "review" if final_score >= 50 else "low_match",
        "skill_score": round(weighted_groups, 2),
        "experience_score": round(experience_fit["score"] * 0.05, 2),
        "semantic_score": parsed.get("semantic_score", 0),
        "semantic_weight": 0,
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(_safe_float(parsed.get("role_relevance_score")) * 0.10, 2),
        "education_score": 0,
        "matched_skills": matched_skills,
        "direct_matched_skills": matched_skills,
        "transferable_skills": [],
        "preferred_matched_skills": [],
        "missing_skills": missing_skills,
        "skill_evidence_depth": {group: data["evidence_level"] for group, data in group_results.items()},
        "skill_evidence": group_results,
        "matched_skill_evidence": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "matched" if data["score"] >= 25 else "missing",
                "evidence_level": data["evidence_level"],
                "source": data["source"],
                "weight": round(data["score"] / 100, 2),
                "matched_terms": data["matched_terms"],
            }
            for group, data in group_results.items()
        ],
        "missing_or_weak_skills": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "missing" if group in missing_mandatory else "weak",
                "evidence_level": group_results[group]["evidence_level"],
            }
            for group in missing_mandatory + weak_mandatory
        ],
        "employer_name_only_skills": [],
        "skill_match_percent": mandatory_coverage,
        "mandatory_skill_coverage": mandatory_coverage,
        "preferred_skill_coverage": 0,
        "core_skill_match_percent": core_percent,
        "matched_core_skill_groups": matched_groups,
        "missing_core_skill_groups": missing_mandatory + weak_mandatory,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), experience_fit["relevant_years"]),
        "target_seniority_level": jd_profile.get("seniority_level"),
        "recommendation": recommendation,
        "label": label,
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "ranking_reason": ranking_reason,
        "experience_fit": experience_fit["label"],
        "all_critical_requirements_met": not missing_mandatory and not weak_mandatory,
        "jd_role_family": "applied_ml_engineer",
        "jd_skill_groups": jd_profile.get("core_skill_groups") or {},
        "evidence_group_scores": group_results,
        "role_relevance_label": parsed.get("experience_relevance_label") or "",
        "experience_fit_label": experience_fit["label"],
        "scoring_breakdown": {
            "applied_ml_group_scores": group_results,
            "mandatory_group_status": {
                "strong": strong_mandatory,
                "weak": weak_mandatory,
                "missing": missing_mandatory,
            },
            "experience_fit": experience_fit,
            "score_caps_applied": caps,
            "missing_core_skill_groups": missing_mandatory + weak_mandatory,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("designation") or parsed.get("current_title") or "",
            "total_experience_years": experience_fit["total_years"],
            "jd_relevant_experience_years": experience_fit["relevant_years"],
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "label": label,
            "matched_mandatory_groups": strong_mandatory,
            "missing_mandatory_groups": missing_mandatory,
            "risk_flags": risk_flags,
        },
    }
    role_identity = _generic_role_identity(parsed, jd_profile, mandatory_coverage, _safe_float(parsed.get("role_relevance_score")), core_percent)
    return _attach_jd_profile_metadata(result, jd_profile, parsed, role_identity)


def _product_architect_text_sections(parsed, resume_text):
    work = []
    projects = []
    for job in parsed.get("experience") or []:
        if isinstance(job, dict):
            work.append(" ".join(str(job.get(key) or "") for key in ("role", "company_name", "description")))
    for project in parsed.get("projects") or []:
        if isinstance(project, dict):
            projects.append(" ".join(str(value or "") for value in project.values()))
        else:
            projects.append(str(project or ""))
    skills = " ".join(str(skill or "") for skill in parsed.get("key_skills") or [])
    title = " ".join(str(parsed.get(key) or "") for key in ("designation", "current_title", "headline"))
    return {
        "work": "\n".join(work),
        "projects": "\n".join(projects),
        "skills": skills,
        "title": title,
        "all": "\n".join([resume_text or "", title, "\n".join(work), "\n".join(projects), skills]),
    }


def _product_architect_group_strength(group, sections):
    pattern = PRODUCT_ARCHITECT_GROUP_PATTERNS[group]
    work_hits = sorted({match.group(0) for match in pattern.finditer(sections["work"])})
    project_hits = sorted({match.group(0) for match in pattern.finditer(sections["projects"])})
    skill_hits = sorted({match.group(0) for match in pattern.finditer(sections["skills"])})
    all_hits = sorted({match.group(0) for match in pattern.finditer(sections["all"])})

    if work_hits:
        level = "professional_strong" if _strong_context(sections["work"]) else "professional_weak"
        score = min(100, 50 + len(work_hits) * 10 + (12 if level == "professional_strong" else 0))
        source = "work_experience"
    elif project_hits:
        level = "project_strong" if _strong_context(sections["projects"]) else "project_weak"
        score = min(82, 36 + len(project_hits) * 9 + (10 if level == "project_strong" else 0))
        source = "project"
    elif skill_hits:
        level = "keyword_only"
        score = min(36, 15 + len(skill_hits) * 5)
        source = "skills_section"
    elif all_hits:
        level = "keyword_only"
        score = min(30, 12 + len(all_hits) * 4)
        source = "resume_text"
    else:
        level = "missing"
        score = 0
        source = ""

    return {
        "group": group,
        "score": round(score, 2),
        "evidence_level": level,
        "source": source,
        "matched_terms": all_hits[:12],
        "matched": all_hits[:12],
        "strong": score >= 60 and level in {"professional_strong", "professional_weak", "project_strong"},
        "missing": score <= 0,
    }


def _product_architect_experience_fit(parsed, jd_profile):
    relevant = _safe_float(parsed.get("relevant_experience_years"))
    total = _safe_float(parsed.get("total_experience_years"))
    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    if relevant <= 0 and role_relevance >= 65:
        relevant = min(total, 1.0) if total else 0.5
    min_years = _safe_float(jd_profile.get("min_experience_years")) or 8.0
    max_years = _safe_float(jd_profile.get("max_experience_years")) or 10.0
    if relevant <= 0:
        return {"score": 20, "label": "unproven", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < 6:
        return {"score": 38, "label": "under_experienced", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < min_years:
        return {"score": 70, "label": "slight_experience_gap", "relevant_years": relevant, "total_years": total, "fit": "slight_under"}
    if relevant <= max_years:
        return {"score": 100, "label": "ideal_8_10_years", "relevant_years": relevant, "total_years": total, "fit": "within"}
    if relevant <= max_years + 2:
        return {"score": 82, "label": "senior_review", "relevant_years": relevant, "total_years": total, "fit": "over"}
    return {"score": 58, "label": "over_experienced", "relevant_years": relevant, "total_years": total, "fit": "over"}


def _product_architect_wrong_role_flags(sections, group_results):
    text = sections["all"]
    flags = []
    for name, pattern in PRODUCT_ARCHITECT_WRONG_ROLE_PATTERNS.items():
        if pattern.search(text):
            flags.append(name)
    has_backend = group_results["hands_on_backend"]["score"] >= 25
    has_product = group_results["product_startup_ownership"]["score"] >= 25
    has_architecture = group_results["architecture_system_design"]["score"] >= 25
    if "cloud_only_architect" in flags and (has_backend or has_product):
        flags.remove("cloud_only_architect")
    if "enterprise_no_coding" in flags and (has_backend and has_architecture):
        flags.remove("enterprise_no_coding")
    return flags


def _score_candidate_product_architect(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    parsed = parsed or {}
    sections = _product_architect_text_sections(parsed, resume_text)
    group_results = {
        group: _product_architect_group_strength(group, sections)
        for group in PRODUCT_ARCHITECT_GROUP_WEIGHTS
    }
    weighted_groups = sum(group_results[group]["score"] * weight for group, weight in PRODUCT_ARCHITECT_GROUP_WEIGHTS.items())
    experience_fit = _product_architect_experience_fit(parsed, jd_profile)
    final_score = weighted_groups + experience_fit["score"] * 0.05

    mandatory_groups = [
        "architecture_system_design",
        "hands_on_backend",
        "devops_delivery",
        "product_startup_ownership",
        "technical_leadership",
    ]
    strong_mandatory = [group for group in mandatory_groups if group_results[group]["strong"]]
    missing_mandatory = [group for group in mandatory_groups if group_results[group]["score"] < 25]
    weak_mandatory = [group for group in mandatory_groups if group not in missing_mandatory and group_results[group]["score"] < 60]
    caps = []
    risk_flags = []
    recruiter_flags = []

    def cap_at(limit, reason, flag=None, risk=None):
        nonlocal final_score
        if final_score > limit:
            final_score = limit
        caps.append({"cap": limit, "reason": reason})
        if flag:
            _append_unique(recruiter_flags, [flag])
        if risk:
            _append_unique(risk_flags, [risk])

    if "architecture_system_design" in missing_mandatory:
        cap_at(62, "System design/software architecture evidence is missing for this Product Architect JD.", "missing_architecture_system_design", "mandatory_group_gap")
    if "hands_on_backend" in missing_mandatory:
        cap_at(68, "Hands-on backend coding evidence with Node.js or Python is missing.", "missing_hands_on_backend", "mandatory_group_gap")
    if not re.search(r"\b(node(?:\.js)?|python)\b", sections["work"] + "\n" + sections["projects"], re.I):
        cap_at(70, "JD requires hands-on Node.js or Python evidence, not only title match.", "missing_node_or_python_evidence", "mandatory_group_gap")
    if "devops_delivery" in missing_mandatory:
        cap_at(78, "Docker/devops delivery evidence is missing for this architect role.", "missing_docker_delivery", "mandatory_group_gap")
    if "product_startup_ownership" in missing_mandatory:
        cap_at(72, "Product/startup ownership evidence is missing.", "missing_product_startup_ownership", "role_relevance")
    if "technical_leadership" in missing_mandatory:
        cap_at(75, "Technical leadership, code review, or mentorship evidence is missing.", "missing_technical_leadership", "role_relevance")

    wrong_role_flags = _product_architect_wrong_role_flags(sections, group_results)
    for flag in wrong_role_flags:
        if flag == "civil_construction_architect":
            cap_at(38, "Civil/construction architecture is a wrong-role match for this software product architecture JD.", flag, "wrong_role")
        elif flag == "project_delivery_manager":
            cap_at(48, "Project/delivery management without product software architecture ownership is a wrong-role match.", flag, "wrong_role")
        elif flag == "cloud_only_architect":
            cap_at(58, "Cloud-only architect evidence without hands-on product/backend coding is capped.", flag, "wrong_role")
        elif flag == "enterprise_no_coding":
            cap_at(58, "Enterprise architecture/governance without hands-on product engineering is capped.", flag, "wrong_role")

    generic_engineer_title = bool(re.search(r"\b(senior\s+software\s+engineer|software\s+engineer|developer)\b", sections["title"], re.I))
    no_arch_ownership = group_results["architecture_system_design"]["score"] < 60 and group_results["technical_leadership"]["score"] < 45
    if generic_engineer_title and no_arch_ownership:
        cap_at(62, "Generic senior engineer title lacks architecture ownership evidence.", "generic_engineer_without_architecture_ownership", "role_relevance")

    title_only = (
        re.search(r"\barchitect\b", sections["title"], re.I)
        and len([group for group in mandatory_groups if group_results[group]["score"] >= 25]) <= 2
    )
    if title_only:
        cap_at(55, "Architect title alone is not enough without JD-specific evidence.", "title_match_only", "keyword_only_match")

    proven_groups = [
        group for group, result in group_results.items()
        if result["evidence_level"] in {"professional_strong", "professional_weak", "project_strong", "project_weak"}
    ]
    keyword_groups = [group for group, result in group_results.items() if result["evidence_level"] == "keyword_only"]
    if keyword_groups and len(keyword_groups) >= max(1, len(proven_groups)):
        cap_at(60, "Product architect match is mostly keyword-only with weak work/project proof.", "skill_match_mostly_listed_only", "keyword_only_match")
    if len(strong_mandatory) <= 2:
        cap_at(70, "Fewer than three mandatory Product Architect groups have strong evidence.", "product_architect_mandatory_group_gap", "mandatory_group_gap")
    elif weak_mandatory:
        cap_at(82, "Strong architecture fit but one or more Product Architect groups need validation.", "product_architect_partial_group_gap", "mandatory_group_gap")
    if experience_fit["fit"] == "under":
        cap_at(70, "JD-related product/software architecture experience is below the 8-10 year target.", "under_experienced", "below_jd_experience_range")
    elif experience_fit["fit"] == "over":
        _append_unique(recruiter_flags, ["over_experienced"])
        _append_unique(risk_flags, ["over_jd_experience_range"])

    final_score = round(max(0, min(100, final_score)), 2)
    mandatory_coverage = round((sum(group_results[group]["score"] for group in mandatory_groups) / 500) * 100, 2)
    core_percent = round((sum(group["score"] for group in group_results.values()) / 500) * 100, 2)
    confidence = round(min(
        100,
        38
        + core_percent * 0.26
        + mandatory_coverage * 0.30
        + _safe_float(parsed.get("parser_quality_score"), parsed.get("resume_quality_score") or 70) * 0.16,
    ), 2)
    rank_score = round(min(100, final_score + (3 if not risk_flags and confidence >= 70 else 0)), 2)

    if final_score >= 82 and not missing_mandatory and len(strong_mandatory) >= 4 and not wrong_role_flags:
        recommendation = "shortlisted"
        label = "Strong Match"
        _append_unique(recruiter_flags, ["strong_match"])
    elif final_score >= 72 and len(strong_mandatory) >= 3 and not wrong_role_flags:
        recommendation = "shortlisted"
        label = "Good Match"
        _append_unique(recruiter_flags, ["good_match"])
    elif final_score < 50 or wrong_role_flags:
        recommendation = "rejected"
        label = "Low Fit"
    elif experience_fit["fit"] == "under":
        recommendation = "in_review"
        label = "Experience Gap"
    elif experience_fit["fit"] == "over":
        recommendation = "in_review"
        label = "Overqualified Review"
    else:
        recommendation = "in_review"
        label = "Partial Fit - Validate Core Skills" if missing_mandatory or weak_mandatory else "Review Required"

    matched_groups = {group: result for group, result in group_results.items() if result["score"] >= 25}
    matched_skills = normalize_skill_list([
        term
        for result in group_results.values()
        for term in result.get("matched_terms") or []
    ])
    missing_skills = [group.replace("_", " ").title() for group in missing_mandatory + weak_mandatory]
    ranking_reason = (
        f"Rank score {rank_score}/100: Product Architect groups "
        f"Architecture/System Design {group_results['architecture_system_design']['score']}/100, "
        f"Hands-on Backend {group_results['hands_on_backend']['score']}/100, "
        f"Product/Startup Ownership {group_results['product_startup_ownership']['score']}/100, "
        f"Technical Leadership {group_results['technical_leadership']['score']}/100, "
        f"Docker/Delivery {group_results['devops_delivery']['score']}/100, "
        f"{experience_fit['relevant_years']:g}/{experience_fit['total_years']:g} relevant/total years."
    )
    if missing_mandatory:
        ranking_reason += f" Missing mandatory groups: {', '.join(missing_mandatory)}."
    if wrong_role_flags:
        ranking_reason += f" Wrong-role flags: {', '.join(wrong_role_flags)}."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    result = {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": "strong_match" if final_score >= 82 else "good_match" if final_score >= 72 else "review" if final_score >= 50 else "low_match",
        "skill_score": round(weighted_groups, 2),
        "experience_score": round(experience_fit["score"] * 0.05, 2),
        "semantic_score": parsed.get("semantic_score", 0),
        "semantic_weight": 0,
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(_safe_float(parsed.get("role_relevance_score")) * 0.10, 2),
        "education_score": 0,
        "matched_skills": matched_skills,
        "direct_matched_skills": matched_skills,
        "transferable_skills": [],
        "preferred_matched_skills": [],
        "missing_skills": missing_skills,
        "skill_evidence_depth": {group: data["evidence_level"] for group, data in group_results.items()},
        "skill_evidence": group_results,
        "matched_skill_evidence": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "matched" if data["score"] >= 25 else "missing",
                "evidence_level": data["evidence_level"],
                "source": data["source"],
                "weight": round(data["score"] / 100, 2),
                "matched_terms": data["matched_terms"],
            }
            for group, data in group_results.items()
        ],
        "missing_or_weak_skills": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "missing" if group in missing_mandatory else "weak",
                "evidence_level": group_results[group]["evidence_level"],
            }
            for group in missing_mandatory + weak_mandatory
        ],
        "employer_name_only_skills": [],
        "skill_match_percent": mandatory_coverage,
        "mandatory_skill_coverage": mandatory_coverage,
        "preferred_skill_coverage": 0,
        "core_skill_match_percent": core_percent,
        "matched_core_skill_groups": matched_groups,
        "missing_core_skill_groups": missing_mandatory + weak_mandatory,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), experience_fit["relevant_years"]),
        "target_seniority_level": jd_profile.get("seniority_level"),
        "recommendation": recommendation,
        "label": label,
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "ranking_reason": ranking_reason,
        "experience_fit": experience_fit["label"],
        "all_critical_requirements_met": not missing_mandatory and not weak_mandatory and not wrong_role_flags,
        "jd_role_family": "product_software_architect",
        "jd_skill_groups": jd_profile.get("core_skill_groups") or {},
        "evidence_group_scores": group_results,
        "role_relevance_label": parsed.get("experience_relevance_label") or "",
        "experience_fit_label": experience_fit["label"],
        "scoring_breakdown": {
            "product_architect_group_scores": group_results,
            "mandatory_group_status": {
                "strong": strong_mandatory,
                "weak": weak_mandatory,
                "missing": missing_mandatory,
            },
            "wrong_role_flags": wrong_role_flags,
            "experience_fit": experience_fit,
            "score_caps_applied": caps,
            "missing_core_skill_groups": missing_mandatory + weak_mandatory,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("designation") or parsed.get("current_title") or "",
            "total_experience_years": experience_fit["total_years"],
            "jd_relevant_experience_years": experience_fit["relevant_years"],
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "label": label,
            "matched_mandatory_groups": strong_mandatory,
            "missing_mandatory_groups": missing_mandatory,
            "wrong_role_flags": wrong_role_flags,
            "risk_flags": risk_flags,
        },
    }
    role_identity = _generic_role_identity(parsed, jd_profile, mandatory_coverage, _safe_float(parsed.get("role_relevance_score")), core_percent)
    return _attach_jd_profile_metadata(result, jd_profile, parsed, role_identity)


def _m365_text_sections(parsed, resume_text):
    work = []
    projects = []
    for job in parsed.get("experience") or []:
        if isinstance(job, dict):
            work.append(" ".join(str(job.get(key) or "") for key in ("role", "company_name", "description")))
    for project in parsed.get("projects") or []:
        if isinstance(project, dict):
            projects.append(" ".join(str(value or "") for value in project.values()))
        else:
            projects.append(str(project or ""))
    skills = " ".join(str(skill or "") for skill in parsed.get("key_skills") or [])
    title = " ".join(str(parsed.get(key) or "") for key in ("designation", "current_title", "headline"))
    return {
        "work": "\n".join(work),
        "projects": "\n".join(projects),
        "skills": skills,
        "title": title,
        "all": "\n".join([resume_text or "", title, "\n".join(work), "\n".join(projects), skills]),
    }


def _m365_group_strength(group, sections):
    pattern = M365_MIGRATION_GROUP_PATTERNS[group]
    work_hits = sorted({match.group(0) for match in pattern.finditer(sections["work"])})
    project_hits = sorted({match.group(0) for match in pattern.finditer(sections["projects"])})
    skill_hits = sorted({match.group(0) for match in pattern.finditer(sections["skills"])})
    all_hits = sorted({match.group(0) for match in pattern.finditer(sections["all"])})

    if work_hits:
        level = "professional_strong" if _strong_context(sections["work"]) else "professional_weak"
        score = min(100, 50 + len(work_hits) * 10 + (10 if level == "professional_strong" else 0))
        source = "work_experience"
    elif project_hits:
        level = "project_strong" if _strong_context(sections["projects"]) else "project_weak"
        score = min(82, 36 + len(project_hits) * 9 + (10 if level == "project_strong" else 0))
        source = "project"
    elif skill_hits:
        level = "keyword_only"
        score = min(36, 14 + len(skill_hits) * 5)
        source = "skills_section"
    elif all_hits:
        level = "keyword_only"
        score = min(30, 12 + len(all_hits) * 4)
        source = "resume_text"
    else:
        level = "missing"
        score = 0
        source = ""

    return {
        "group": group,
        "score": round(score, 2),
        "evidence_level": level,
        "source": source,
        "matched_terms": all_hits[:12],
        "matched": all_hits[:12],
        "strong": score >= 60 and level in {"professional_strong", "professional_weak", "project_strong"},
        "missing": score <= 0,
    }


def _m365_experience_fit(parsed, jd_profile):
    relevant = _safe_float(parsed.get("relevant_experience_years"))
    total = _safe_float(parsed.get("total_experience_years"))
    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    if relevant <= 0 and role_relevance >= 65:
        relevant = min(total, 1.0) if total else 0.5
    min_years = _safe_float(jd_profile.get("min_experience_years")) or 8.0
    max_years = _safe_float(jd_profile.get("max_experience_years")) or 10.0
    if relevant <= 0:
        return {"score": 20, "label": "unproven", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < 5:
        return {"score": 36, "label": "under_experienced", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < min_years:
        return {"score": 70, "label": "slight_experience_gap", "relevant_years": relevant, "total_years": total, "fit": "slight_under"}
    if relevant <= max_years:
        return {"score": 100, "label": "ideal_8_10_years", "relevant_years": relevant, "total_years": total, "fit": "within"}
    if relevant <= max_years + 2:
        return {"score": 82, "label": "senior_review", "relevant_years": relevant, "total_years": total, "fit": "over"}
    return {"score": 58, "label": "over_experienced", "relevant_years": relevant, "total_years": total, "fit": "over"}


def _m365_wrong_role_flags(sections, group_results):
    text = sections["all"]
    flags = []
    for name, pattern in M365_WRONG_ROLE_PATTERNS.items():
        if pattern.search(text):
            flags.append(name)

    has_migration = group_results["m365_migration"]["score"] >= 25 and bool(M365_MIGRATION_PROOF_RE.search(sections["work"] + "\n" + sections["projects"]))
    has_exchange = group_results["exchange_migration"]["score"] >= 25
    has_workload = group_results["workload_migration"]["score"] >= 25
    has_tools = group_results["tools_scripting"]["score"] >= 25

    if "generic_admin_without_migration" in flags and has_migration:
        flags.remove("generic_admin_without_migration")
    if "azure_only" in flags and has_migration and (has_exchange or has_workload):
        flags.remove("azure_only")
    if "sharepoint_dev_only" in flags and has_migration and (has_workload or has_tools):
        flags.remove("sharepoint_dev_only")
    if "project_manager_only" in flags and has_migration and has_tools:
        flags.remove("project_manager_only")
    if "iam_only" in flags and has_migration and has_exchange:
        flags.remove("iam_only")
    return flags


def _score_candidate_m365_migration(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    parsed = parsed or {}
    sections = _m365_text_sections(parsed, resume_text)
    group_results = {
        group: _m365_group_strength(group, sections)
        for group in M365_MIGRATION_GROUP_WEIGHTS
    }
    weighted_groups = sum(group_results[group]["score"] * weight for group, weight in M365_MIGRATION_GROUP_WEIGHTS.items())
    experience_fit = _m365_experience_fit(parsed, jd_profile)
    final_score = weighted_groups + experience_fit["score"] * 0.05

    mandatory_groups = [
        "m365_migration",
        "exchange_migration",
        "workload_migration",
        "tenant_identity",
        "tools_scripting",
        "seniority_delivery",
    ]
    strong_mandatory = [group for group in mandatory_groups if group_results[group]["strong"]]
    missing_mandatory = [group for group in mandatory_groups if group_results[group]["score"] < 25]
    weak_mandatory = [group for group in mandatory_groups if group not in missing_mandatory and group_results[group]["score"] < 60]
    caps = []
    risk_flags = []
    recruiter_flags = []

    def cap_at(limit, reason, flag=None, risk=None):
        nonlocal final_score
        if final_score > limit:
            final_score = limit
        caps.append({"cap": limit, "reason": reason})
        if flag:
            _append_unique(recruiter_flags, [flag])
        if risk:
            _append_unique(risk_flags, [risk])

    work_project_text = sections["work"] + "\n" + sections["projects"]
    has_professional_migration = bool(M365_MIGRATION_PROOF_RE.search(work_project_text))
    if "m365_migration" in missing_mandatory:
        cap_at(62, "Microsoft 365 migration evidence is missing; generic M365 keywords are not enough.", "missing_m365_migration_evidence", "mandatory_group_gap")
    if not has_professional_migration:
        cap_at(60, "No work/project migration proof found (tenant migration, cutover, batches, coexistence, or migration tooling).", "missing_work_migration_proof", "keyword_only_match")
    if "tenant_identity" in missing_mandatory:
        cap_at(75, "Tenant/cross-tenant or Entra ID/Azure AD migration context is missing.", "missing_tenant_identity", "mandatory_group_gap")
    if "exchange_migration" in missing_mandatory:
        cap_at(78, "Exchange Online/on-prem Exchange migration evidence is missing.", "missing_exchange_migration", "mandatory_group_gap")
    if "workload_migration" in missing_mandatory:
        cap_at(80, "Teams, SharePoint, or OneDrive migration evidence is missing.", "missing_workload_migration", "mandatory_group_gap")
    if "tools_scripting" in missing_mandatory:
        cap_at(78, "Quest ODM/equivalent migration tooling or PowerShell scripting evidence is missing.", "missing_tools_scripting", "mandatory_group_gap")
    if "seniority_delivery" in missing_mandatory:
        cap_at(82, "SME/lead/consultant delivery ownership, cutover, validation, or hypercare evidence is missing.", "missing_sme_delivery", "seniority_delivery_gap")

    wrong_role_flags = _m365_wrong_role_flags(sections, group_results)
    for flag in wrong_role_flags:
        if flag == "generic_support":
            cap_at(42, "Helpdesk/desktop support is a wrong-role match for this M365 Migration SME JD.", flag, "wrong_role")
        elif flag == "azure_only":
            cap_at(58, "Azure infrastructure/cloud-only profile lacks hands-on Microsoft 365 migration proof.", flag, "wrong_role")
        elif flag == "sharepoint_dev_only":
            cap_at(55, "SharePoint development without migration ownership is capped.", flag, "wrong_role")
        elif flag == "project_manager_only":
            cap_at(48, "Project/delivery management without hands-on migration execution is capped.", flag, "wrong_role")
        elif flag == "iam_only":
            cap_at(55, "IAM-only evidence without M365 migration execution is capped.", flag, "wrong_role")
        elif flag == "generic_admin_without_migration":
            cap_at(65, "M365/Exchange/Teams admin evidence without migration execution cannot rank high.", flag, "wrong_role")

    proven_groups = [
        group for group, result in group_results.items()
        if result["evidence_level"] in {"professional_strong", "professional_weak", "project_strong", "project_weak"}
    ]
    keyword_groups = [group for group, result in group_results.items() if result["evidence_level"] == "keyword_only"]
    if keyword_groups and len(keyword_groups) >= max(1, len(proven_groups)):
        cap_at(60, "M365 match is mostly keyword-only with weak work/project proof.", "skill_match_mostly_listed_only", "keyword_only_match")
    if len(strong_mandatory) <= 2:
        cap_at(70, "Fewer than three mandatory M365 migration groups have strong evidence.", "m365_migration_mandatory_group_gap", "mandatory_group_gap")
    elif weak_mandatory:
        cap_at(82, "Strong M365 migration fit but one or more groups need validation.", "m365_migration_partial_group_gap", "mandatory_group_gap")
    if experience_fit["fit"] == "under":
        cap_at(70, "JD-related M365 migration experience is below the 8-10 year target.", "under_experienced", "below_jd_experience_range")
    elif experience_fit["fit"] == "over":
        _append_unique(recruiter_flags, ["over_experienced"])
        _append_unique(risk_flags, ["over_jd_experience_range"])

    final_score = round(max(0, min(100, final_score)), 2)
    mandatory_coverage = round((sum(group_results[group]["score"] for group in mandatory_groups) / 600) * 100, 2)
    core_percent = round((sum(group["score"] for group in group_results.values()) / 600) * 100, 2)
    confidence = round(min(
        100,
        38
        + core_percent * 0.26
        + mandatory_coverage * 0.30
        + _safe_float(parsed.get("parser_quality_score"), parsed.get("resume_quality_score") or 70) * 0.16,
    ), 2)
    rank_score = round(min(100, final_score + (3 if not risk_flags and confidence >= 70 else 0)), 2)

    if final_score >= 82 and not missing_mandatory and len(strong_mandatory) >= 4 and not wrong_role_flags:
        recommendation = "shortlisted"
        label = "Strong Match"
        _append_unique(recruiter_flags, ["strong_match"])
    elif final_score >= 72 and len(strong_mandatory) >= 3 and not wrong_role_flags:
        recommendation = "shortlisted"
        label = "Good Match"
        _append_unique(recruiter_flags, ["good_match"])
    elif final_score < 50 or wrong_role_flags:
        recommendation = "rejected"
        label = "Low Fit"
    elif experience_fit["fit"] == "under":
        recommendation = "in_review"
        label = "Experience Gap"
    elif experience_fit["fit"] == "over":
        recommendation = "in_review"
        label = "Overqualified Review"
    else:
        recommendation = "in_review"
        label = "Partial Fit - Validate Core Skills" if missing_mandatory or weak_mandatory else "Review Required"

    matched_groups = {group: result for group, result in group_results.items() if result["score"] >= 25}
    matched_skills = normalize_skill_list([
        term
        for result in group_results.values()
        for term in result.get("matched_terms") or []
    ])
    missing_skills = [group.replace("_", " ").title() for group in missing_mandatory + weak_mandatory]
    ranking_reason = (
        f"Rank score {rank_score}/100: M365 Migration groups "
        f"M365 Migration {group_results['m365_migration']['score']}/100, "
        f"Exchange Migration {group_results['exchange_migration']['score']}/100, "
        f"Workload Migration {group_results['workload_migration']['score']}/100, "
        f"Tenant/Identity {group_results['tenant_identity']['score']}/100, "
        f"Tools/Scripting {group_results['tools_scripting']['score']}/100, "
        f"SME Delivery {group_results['seniority_delivery']['score']}/100, "
        f"{experience_fit['relevant_years']:g}/{experience_fit['total_years']:g} relevant/total years."
    )
    if missing_mandatory:
        ranking_reason += f" Missing mandatory groups: {', '.join(missing_mandatory)}."
    if wrong_role_flags:
        ranking_reason += f" Wrong-role flags: {', '.join(wrong_role_flags)}."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    result = {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": "strong_match" if final_score >= 82 else "good_match" if final_score >= 72 else "review" if final_score >= 50 else "low_match",
        "skill_score": round(weighted_groups, 2),
        "experience_score": round(experience_fit["score"] * 0.05, 2),
        "semantic_score": parsed.get("semantic_score", 0),
        "semantic_weight": 0,
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(_safe_float(parsed.get("role_relevance_score")) * 0.10, 2),
        "education_score": 0,
        "matched_skills": matched_skills,
        "direct_matched_skills": matched_skills,
        "transferable_skills": [],
        "preferred_matched_skills": [],
        "missing_skills": missing_skills,
        "skill_evidence_depth": {group: data["evidence_level"] for group, data in group_results.items()},
        "skill_evidence": group_results,
        "matched_skill_evidence": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "matched" if data["score"] >= 25 else "missing",
                "evidence_level": data["evidence_level"],
                "source": data["source"],
                "weight": round(data["score"] / 100, 2),
                "matched_terms": data["matched_terms"],
            }
            for group, data in group_results.items()
        ],
        "missing_or_weak_skills": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "missing" if group in missing_mandatory else "weak",
                "evidence_level": group_results[group]["evidence_level"],
            }
            for group in missing_mandatory + weak_mandatory
        ],
        "employer_name_only_skills": [],
        "skill_match_percent": mandatory_coverage,
        "mandatory_skill_coverage": mandatory_coverage,
        "preferred_skill_coverage": 0,
        "core_skill_match_percent": core_percent,
        "matched_core_skill_groups": matched_groups,
        "missing_core_skill_groups": missing_mandatory + weak_mandatory,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), experience_fit["relevant_years"]),
        "target_seniority_level": jd_profile.get("seniority_level"),
        "recommendation": recommendation,
        "label": label,
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "ranking_reason": ranking_reason,
        "experience_fit": experience_fit["label"],
        "all_critical_requirements_met": not missing_mandatory and not weak_mandatory and not wrong_role_flags,
        "jd_role_family": "m365_migration_sme",
        "jd_skill_groups": jd_profile.get("core_skill_groups") or {},
        "evidence_group_scores": group_results,
        "role_relevance_label": parsed.get("experience_relevance_label") or "",
        "experience_fit_label": experience_fit["label"],
        "scoring_breakdown": {
            "m365_migration_group_scores": group_results,
            "mandatory_group_status": {
                "strong": strong_mandatory,
                "weak": weak_mandatory,
                "missing": missing_mandatory,
            },
            "wrong_role_flags": wrong_role_flags,
            "experience_fit": experience_fit,
            "score_caps_applied": caps,
            "missing_core_skill_groups": missing_mandatory + weak_mandatory,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("designation") or parsed.get("current_title") or "",
            "total_experience_years": experience_fit["total_years"],
            "jd_relevant_experience_years": experience_fit["relevant_years"],
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "label": label,
            "matched_mandatory_groups": strong_mandatory,
            "missing_mandatory_groups": missing_mandatory,
            "wrong_role_flags": wrong_role_flags,
            "risk_flags": risk_flags,
        },
    }
    role_identity = _generic_role_identity(parsed, jd_profile, mandatory_coverage, _safe_float(parsed.get("role_relevance_score")), core_percent)
    return _attach_jd_profile_metadata(result, jd_profile, parsed, role_identity)


def _aml_text_sections(parsed, resume_text):
    work = []
    projects = []
    for job in parsed.get("experience") or []:
        if isinstance(job, dict):
            work.append(" ".join(str(job.get(key) or "") for key in ("role", "company_name", "description")))
    for project in parsed.get("projects") or []:
        if isinstance(project, dict):
            projects.append(" ".join(str(value or "") for value in project.values()))
        else:
            projects.append(str(project or ""))
    skill_sources = []
    for key in ("key_skills", "matched_skills", "direct_matched_skills", "preferred_matched_skills"):
        value = parsed.get(key) or []
        if isinstance(value, str):
            skill_sources.append(value)
        else:
            skill_sources.extend(str(skill or "") for skill in value)
    skills = " ".join(skill_sources)
    title = " ".join(str(parsed.get(key) or "") for key in ("designation", "current_title", "headline"))
    return {
        "work": "\n".join(work),
        "projects": "\n".join(projects),
        "skills": skills,
        "title": title,
        "all": "\n".join([resume_text or "", title, "\n".join(work), "\n".join(projects), skills]),
    }


def _aml_group_strength(group, sections):
    pattern = AML_TM_GROUP_PATTERNS[group]
    title_hits = sorted({match.group(0) for match in pattern.finditer(sections["title"])})
    work_hits = sorted({match.group(0) for match in pattern.finditer(sections["work"])})
    project_hits = sorted({match.group(0) for match in pattern.finditer(sections["projects"])})
    skill_hits = sorted({match.group(0) for match in pattern.finditer(sections["skills"])})
    all_hits = sorted({match.group(0) for match in pattern.finditer(sections["all"])})

    if group == "role_fit" and title_hits:
        level = "professional_strong" if (work_hits or AML_TM_CORE_PROOF_RE.search(sections["work"])) else "professional_weak"
        score = 88 if level == "professional_strong" else 72
        source = "title"
    elif work_hits:
        level = "professional_strong" if _strong_context(sections["work"]) else "professional_weak"
        score = min(100, 52 + len(work_hits) * 10 + (10 if level == "professional_strong" else 0))
        source = "work_experience"
    elif project_hits:
        level = "project_strong" if _strong_context(sections["projects"]) else "project_weak"
        score = min(82, 36 + len(project_hits) * 9 + (10 if level == "project_strong" else 0))
        source = "project"
    elif skill_hits:
        level = "keyword_only"
        score = min(36, 14 + len(skill_hits) * 5)
        source = "skills_section"
    elif all_hits:
        level = "keyword_only"
        score = min(30, 12 + len(all_hits) * 4)
        source = "resume_text"
    else:
        level = "missing"
        score = 0
        source = ""

    return {
        "group": group,
        "score": round(score, 2),
        "evidence_level": level,
        "source": source,
        "matched_terms": all_hits[:12],
        "matched": all_hits[:12],
        "strong": score >= 60 and level in {"professional_strong", "professional_weak", "project_strong"},
        "missing": score <= 0,
    }


def _aml_relevant_years_from_jobs(parsed, sections):
    relevant = _safe_float(parsed.get("relevant_experience_years") or parsed.get("jd_related_experience_years"))
    if relevant > 0:
        return relevant
    total = 0.0
    for job in parsed.get("experience") or []:
        if not isinstance(job, dict):
            continue
        block_text = " ".join(str(job.get(key) or "") for key in ("role", "company_name", "description"))
        if not AML_TM_CORE_PROOF_RE.search(block_text):
            continue
        years = _safe_float(job.get("duration_years") or job.get("years") or job.get("experience_years"))
        total += years
    if total > 0:
        return total
    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    total_years = _safe_float(parsed.get("total_experience_years"))
    if role_relevance >= 70 and AML_TM_CORE_PROOF_RE.search(sections["work"]):
        return total_years
    return 0.0


def _aml_experience_fit(parsed, jd_profile, sections):
    relevant = _aml_relevant_years_from_jobs(parsed, sections)
    total = _safe_float(parsed.get("total_experience_years"))
    min_years = _safe_float(jd_profile.get("min_experience_years")) or 5.0
    max_years = _safe_float(jd_profile.get("max_experience_years")) or 7.0
    if relevant <= 0:
        return {"score": 18, "label": "unproven_aml_tm_experience", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < 3:
        return {"score": 36, "label": "under_experienced_for_l2", "relevant_years": relevant, "total_years": total, "fit": "under"}
    if relevant < min_years:
        return {"score": 68, "label": "slightly_under_5_7_years", "relevant_years": relevant, "total_years": total, "fit": "slight_under"}
    if relevant <= max_years:
        return {"score": 100, "label": "ideal_5_7_years", "relevant_years": relevant, "total_years": total, "fit": "within"}
    if relevant <= 9:
        return {"score": 84, "label": "slightly_over_5_7_years", "relevant_years": relevant, "total_years": total, "fit": "over"}
    return {"score": 70, "label": "over_experienced_for_l2", "relevant_years": relevant, "total_years": total, "fit": "over"}


def _aml_wrong_role_flags(sections, group_results):
    text = sections["all"]
    flags = []
    has_core_aml = (
        group_results["transaction_monitoring"]["score"] >= 25
        or group_results["aml_investigations"]["score"] >= 25
    )
    for name, pattern in AML_TM_WRONG_ROLE_PATTERNS.items():
        if pattern.search(text) and not has_core_aml:
            flags.append(name)
    return flags


def _aml_jd_uploaded_as_resume(parsed, sections):
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", sections.get("all") or "")
    head = text[:2500]
    jd_markers = {match.group(0).lower() for match in AML_TM_JD_UPLOAD_MARKER_RE.finditer(head)}
    if len(jd_markers) < 3:
        return False

    full_name = str((parsed or {}).get("full_name") or "").strip().lower()
    has_candidate_name = bool(full_name and full_name not in {"candidate", "unnamed candidate", "unknown"})
    experience = [
        job for job in (parsed or {}).get("experience") or []
        if isinstance(job, dict) and (job.get("role") or job.get("company_name") or job.get("duration_years"))
    ]
    has_resume_identity = bool(AML_TM_RESUME_IDENTITY_RE.search(head))
    has_work_history = bool(experience) or bool(re.search(r"\b\d{4}\s*(?:-|to)\s*(?:present|current|\d{4})\b", text, re.I))

    return not (has_candidate_name and has_work_history and has_resume_identity)


def _aml_distinct_tool_count(text):
    tool_patterns = {
        "actimize": r"\b(?:nice\s+)?actimize\b",
        "global_radar": r"\bglobal\s+radar\b",
        "aci_worldwide": r"\baci\s+worldwide\b",
        "fico": r"\bfico(?:[-\s]?based)?(?:\s+monitoring\s+systems?)?\b",
        "verafin": r"\bverafin\b",
        "oracle_financial_services": r"\boracle\s+financial\s+services\b",
        "palantir": r"\bpalantir\b",
        "eastnets": r"\beastnets\b",
        "safewatch": r"\bsafewatch\b",
        "aml_software": r"\baml\s+software\b",
        "monitoring_systems": r"\bmonitoring\s+systems?\b",
    }
    return sum(1 for pattern in tool_patterns.values() if re.search(pattern, text or "", re.I))


def _aml_jd_is_senior_l2_exempt(jd_text, jd_data, jd_profile):
    text = " ".join([
        str(jd_text or ""),
        str((jd_data or {}).get("role") or ""),
        str((jd_profile or {}).get("primary_role") or ""),
    ])
    return bool(re.search(r"\b(senior|lead|manager|principal|head\s+of|team\s+lead)\b", text, re.I))


def _aml_recruiter_recommendation(final_score, recommendation, risk_flags, experience_fit):
    if "synthetic_or_non_human_profile" in risk_flags or "invalid_document_or_jd_uploaded" in risk_flags:
        return "Reject for this role"
    if "kyc_only_profile" in risk_flags or "generic_banking_only" in risk_flags:
        return "Hold"
    if experience_fit["fit"] in {"under", "over"}:
        return "Review manually"
    if recommendation == "rejected" or final_score < 50:
        return "Reject for this role"
    if final_score < 60:
        return "Hold"
    if final_score >= 90:
        return "Strong shortlist"
    if final_score >= 80:
        return "Shortlist"
    if final_score >= 70:
        return "Review manually"
    return "Hold"


def _score_candidate_aml_transaction_monitoring(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    parsed = parsed or {}
    sections = _aml_text_sections(parsed, resume_text)
    group_results = {
        group: _aml_group_strength(group, sections)
        for group in AML_TM_GROUP_WEIGHTS
    }
    weighted_groups = sum(group_results[group]["score"] * weight for group, weight in AML_TM_GROUP_WEIGHTS.items())
    experience_fit = _aml_experience_fit(parsed, jd_profile, sections)
    final_score = weighted_groups + experience_fit["score"] * 0.25

    mandatory_groups = ["transaction_monitoring", "aml_investigations", "case_management", "sar_str"]
    strong_mandatory = [group for group in mandatory_groups if group_results[group]["strong"]]
    missing_mandatory = [group for group in mandatory_groups if group_results[group]["score"] < 25]
    weak_mandatory = [group for group in mandatory_groups if group not in missing_mandatory and group_results[group]["score"] < 60]
    caps = []
    risk_flags = []
    recruiter_flags = []

    def cap_at(limit, reason, flag=None, risk=None):
        nonlocal final_score
        if final_score > limit:
            final_score = limit
        caps.append({"cap": limit, "reason": reason})
        if flag:
            _append_unique(recruiter_flags, [flag])
        if risk:
            _append_unique(risk_flags, [risk])

    has_tm = group_results["transaction_monitoring"]["score"] >= 25
    has_investigation = group_results["aml_investigations"]["score"] >= 25
    has_sar_str = group_results["sar_str"]["score"] >= 25
    has_case = group_results["case_management"]["score"] >= 25
    has_banking = group_results["banking_exposure"]["score"] >= 25
    has_kyc = bool(AML_TM_KYC_RE.search(sections["all"]))
    has_generic_banking = bool(AML_TM_GENERIC_BANKING_RE.search(sections["all"]))
    has_fraud = bool(AML_TM_FRAUD_RE.search(sections["all"]))
    aml_tool_count = _aml_distinct_tool_count(sections["all"])
    has_aml_tools = aml_tool_count >= 2
    has_role_evidence = bool(AML_TM_ROLE_EVIDENCE_RE.search(sections["all"]))
    has_transaction_evidence = bool(AML_TM_TRANSACTION_EVIDENCE_RE.search(sections["all"]))
    has_fcrm_evidence = bool(AML_TM_FCRM_EVIDENCE_RE.search(sections["all"]))
    has_aml_or_fcrm_evidence = has_tm or has_investigation or has_sar_str or has_fcrm_evidence
    synthetic_profile = bool(AML_TM_SYNTHETIC_PROFILE_RE.search(sections["all"]))
    invalid_jd_upload = _aml_jd_uploaded_as_resume(parsed, sections)
    senior_l2_exempt = _aml_jd_is_senior_l2_exempt(jd_text, jd_data, jd_profile)
    over_l2_experience = (
        not senior_l2_exempt
        and (
            experience_fit["total_years"] > 10
            or experience_fit["relevant_years"] > 7.5
        )
    )

    if not has_tm:
        cap_at(65, "AML Transaction Monitoring evidence is missing.", "missing_aml_transaction_monitoring", "missing_aml_transaction_monitoring")
    if not has_investigation:
        cap_at(72, "AML investigation or suspicious activity investigation evidence is missing.", "missing_aml_investigation", "missing_aml_investigation")
    if not has_sar_str:
        cap_at(82, "SAR/STR process evidence is missing or weak.", "missing_sar_str", "missing_sar_str")
    if not has_case:
        cap_at(78, "Case management, case closure, or case narrative evidence is missing.", "no_case_management_evidence", "no_case_management_evidence")
    if not has_banking:
        cap_at(84, "Retail, commercial, correspondent banking, or financial institution exposure is missing.", "no_banking_environment_evidence", "no_banking_environment_evidence")

    if invalid_jd_upload:
        cap_at(18, "Document appears to be a job description rather than a candidate resume.", "invalid_document_or_jd_uploaded", "invalid_document_or_jd_uploaded")
    if synthetic_profile:
        cap_at(45, "Document describes an AI/digital worker rather than a human employment profile.", "synthetic_or_non_human_profile", "synthetic_or_non_human_profile")

    if has_kyc and not has_aml_or_fcrm_evidence:
        cap_at(65, "KYC/CDD/EDD evidence without AML Transaction Monitoring or AML investigation is KYC-only for this JD.", "kyc_only_profile", "kyc_only_profile")
    if has_generic_banking and not has_aml_or_fcrm_evidence:
        cap_at(60, "Generic banking operations without AML investigation cannot rank high for this L2 investigator JD.", "generic_banking_only", "generic_banking_only")
    if has_fraud and not has_tm:
        cap_at(70, "Fraud investigation is only a partial match without AML Transaction Monitoring evidence.", "fraud_only_partial_match", "partial_fraud_match")

    wrong_role_flags = _aml_wrong_role_flags(sections, group_results)
    for flag in wrong_role_flags:
        cap_at(45, "Generic analyst evidence without AML Transaction Monitoring is a wrong-role match.", flag, "wrong_role")

    proven_groups = [
        group for group, result in group_results.items()
        if result["evidence_level"] in {"professional_strong", "professional_weak", "project_strong", "project_weak"}
    ]
    keyword_groups = [group for group, result in group_results.items() if result["evidence_level"] == "keyword_only"]
    if keyword_groups and len(keyword_groups) >= max(1, len(proven_groups)):
        cap_at(66, "AML match is mostly keyword-only with weak work/project proof.", "skill_match_mostly_listed_only", "keyword_only_match")
    if len(strong_mandatory) <= 1 and not (has_fraud and has_banking):
        cap_at(70, "Fewer than two mandatory AML/TM groups have strong evidence.", "aml_tm_mandatory_group_gap", "mandatory_group_gap")
    elif weak_mandatory:
        cap_at(85, "AML/TM fit is promising but one or more mandatory groups need validation.", "aml_tm_partial_group_gap", "mandatory_group_gap")

    if experience_fit["fit"] == "under":
        cap_at(69, "JD-related AML Transaction Monitoring experience is below the L2 5-7 year target.", "under_experienced_for_l2", "under_experienced_for_l2")
    elif experience_fit["fit"] == "over":
        _append_unique(recruiter_flags, ["over_experienced_for_l2"])
        _append_unique(risk_flags, ["over_experienced_for_l2"])
        if experience_fit["relevant_years"] > 10:
            cap_at(85, "Candidate is above the L2 5-7 year band; review for overqualification but do not auto-reject.", "over_experienced_for_l2", "over_experienced_for_l2")
    if over_l2_experience:
        _append_unique(recruiter_flags, ["over_experienced_for_l2"])
        _append_unique(risk_flags, ["over_experienced_for_l2"])

    fraud_partial_only = has_fraud and has_banking and group_results["role_fit"]["score"] < 25 and not has_sar_str
    if fraud_partial_only and final_score < 55:
        final_score = 58
        _append_unique(recruiter_flags, ["fraud_only_partial_match"])
        _append_unique(risk_flags, ["partial_fraud_match"])

    disqualifying_profile = bool(
        synthetic_profile
        or invalid_jd_upload
        or wrong_role_flags
        or "kyc_only_profile" in risk_flags
        or "generic_banking_only" in risk_flags
    )
    parsed_skill_match = _safe_float(parsed.get("skill_match_percent") or parsed.get("mandatory_skill_coverage"))
    current_mandatory_coverage = round((sum(group_results[group]["score"] for group in mandatory_groups) / 400) * 100, 2)
    financial_crime_tool_profile = (
        not disqualifying_profile
        and (group_results["role_fit"]["score"] >= 60 or has_role_evidence)
        and (group_results["transaction_monitoring"]["score"] >= 60 or has_transaction_evidence)
        and has_aml_tools
        and has_aml_or_fcrm_evidence
        and (has_banking or parsed_skill_match >= 70 or current_mandatory_coverage >= 60)
        and experience_fit["relevant_years"] >= 4.5
    )
    if financial_crime_tool_profile:
        _append_unique(recruiter_flags, ["aml_fcrm_tool_profile"])
    if financial_crime_tool_profile and final_score < 70:
        final_score = 70
    if financial_crime_tool_profile and not has_sar_str and final_score > 78:
        final_score = 78
        caps.append({"cap": 78, "reason": "Financial crime tool profile is strong, but SAR/STR process evidence still needs verification."})
    if over_l2_experience and not has_sar_str and final_score > 78:
        final_score = 78
        caps.append({"cap": 78, "reason": "Candidate is over the L2 5-7 year band and SAR/STR evidence needs verification."})
    if over_l2_experience and not senior_l2_exempt and final_score >= 85:
        final_score = 84
        caps.append({"cap": 84, "reason": "Candidate is over the L2 5-7 year band; senior/lead/manager JD not detected."})

    short_aml_banking_profile = (
        not disqualifying_profile
        and 0 < experience_fit["relevant_years"] < 3.0
        and group_results["role_fit"]["score"] >= 60
        and has_tm
        and has_banking
        and (has_kyc or has_fcrm_evidence)
    )
    if short_aml_banking_profile:
        if final_score < 42:
            final_score = 42
        if final_score > 55:
            final_score = 55
        _append_unique(recruiter_flags, ["short_aml_banking_profile"])

    final_score = round(max(0, min(100, final_score)), 2)
    mandatory_coverage = round((sum(group_results[group]["score"] for group in mandatory_groups) / 400) * 100, 2)
    core_percent = round((sum(group["score"] for group in group_results.values()) / 700) * 100, 2)
    confidence = round(min(
        100,
        36
        + mandatory_coverage * 0.34
        + core_percent * 0.24
        + _safe_float(parsed.get("parser_quality_score"), parsed.get("resume_quality_score") or 70) * 0.12,
    ), 2)
    rank_score = round(min(100, final_score + (3 if not risk_flags and confidence >= 70 else 0)), 2)

    if synthetic_profile or invalid_jd_upload:
        recommendation = "rejected"
        label = "Invalid Profile" if invalid_jd_upload else "Synthetic Profile"
    elif final_score >= 85 and has_tm and has_investigation and has_sar_str and has_case and experience_fit["fit"] == "within":
        recommendation = "shortlisted"
        label = "Strong Match"
        _append_unique(recruiter_flags, ["strong_match"])
    elif final_score >= 70 and (financial_crime_tool_profile or over_l2_experience or not has_sar_str):
        recommendation = "in_review"
        label = "Recruiter Review"
    elif final_score >= 75 and has_tm and has_investigation and has_sar_str and not wrong_role_flags and not over_l2_experience:
        recommendation = "shortlisted"
        label = "Good Match"
        _append_unique(recruiter_flags, ["good_match"])
    elif final_score < 55 or wrong_role_flags:
        recommendation = "rejected"
        label = "Low Fit"
    elif experience_fit["fit"] == "under":
        recommendation = "in_review"
        label = "Experience Gap"
    elif experience_fit["fit"] == "over":
        recommendation = "in_review"
        label = "Overqualified Review"
    else:
        recommendation = "in_review"
        label = "Partial Fit - Validate AML Evidence" if missing_mandatory or weak_mandatory else "Review Required"

    matched_groups = {group: result for group, result in group_results.items() if result["score"] >= 25}
    matched_skills = normalize_skill_list([
        term
        for result in group_results.values()
        for term in result.get("matched_terms") or []
    ])
    missing_skills = [group.replace("_", " ").title() for group in missing_mandatory + weak_mandatory]
    recruiter_recommendation = _aml_recruiter_recommendation(final_score, recommendation, risk_flags, experience_fit)
    ranking_reason = (
        f"Rank score {rank_score}/100: AML Transaction Monitoring L2 groups "
        f"Role Fit {group_results['role_fit']['score']}/100, "
        f"Transaction Monitoring {group_results['transaction_monitoring']['score']}/100, "
        f"AML Investigations {group_results['aml_investigations']['score']}/100, "
        f"Case Management {group_results['case_management']['score']}/100, "
        f"SAR/STR {group_results['sar_str']['score']}/100, "
        f"Banking Exposure {group_results['banking_exposure']['score']}/100, "
        f"{experience_fit['relevant_years']:g}/{experience_fit['total_years']:g} AML-TM relevant/total years."
    )
    if missing_mandatory:
        ranking_reason += f" Missing mandatory groups: {', '.join(missing_mandatory)}."
    if wrong_role_flags:
        ranking_reason += f" Wrong-role flags: {', '.join(wrong_role_flags)}."
    if invalid_jd_upload:
        ranking_reason += " Document appears to be a JD uploaded as a resume."
    if synthetic_profile:
        ranking_reason += " Document appears to describe an AI/digital worker profile."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    knockout_flags = {
        "missing_aml_transaction_monitoring": "missing_aml_transaction_monitoring" in risk_flags,
        "missing_aml_investigation": "missing_aml_investigation" in risk_flags,
        "missing_sar_str": "missing_sar_str" in risk_flags,
        "kyc_only_profile": "kyc_only_profile" in risk_flags,
        "generic_banking_only": "generic_banking_only" in risk_flags,
        "under_experienced_for_l2": "under_experienced_for_l2" in risk_flags,
        "over_experienced_for_l2": "over_experienced_for_l2" in risk_flags,
        "no_case_management_evidence": "no_case_management_evidence" in risk_flags,
        "no_banking_environment_evidence": "no_banking_environment_evidence" in risk_flags,
        "synthetic_or_non_human_profile": "synthetic_or_non_human_profile" in risk_flags,
        "invalid_document_or_jd_uploaded": "invalid_document_or_jd_uploaded" in risk_flags,
    }

    result = {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": "excellent_match" if final_score >= 90 else "strong_match" if final_score >= 80 else "good_review" if final_score >= 70 else "partial_match" if final_score >= 60 else "low_match",
        "skill_score": round(
            group_results["transaction_monitoring"]["score"] * 0.34
            + group_results["aml_investigations"]["score"] * 0.29
            + group_results["case_management"]["score"] * 0.17
            + group_results["sar_str"]["score"] * 0.20,
            2,
        ),
        "experience_score": round(experience_fit["score"] * 0.25, 2),
        "semantic_score": parsed.get("semantic_score", 0),
        "semantic_weight": round(group_results["role_fit"]["score"] * 0.18 + group_results["banking_exposure"]["score"] * 0.07, 2),
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(group_results["role_fit"]["score"] * 0.25, 2),
        "education_score": 0,
        "matched_skills": matched_skills,
        "direct_matched_skills": matched_skills,
        "transferable_skills": ["Fraud Investigation"] if has_fraud and not has_tm else [],
        "preferred_matched_skills": group_results["nice_to_have"]["matched_terms"],
        "missing_skills": missing_skills,
        "skill_evidence_depth": {group: data["evidence_level"] for group, data in group_results.items()},
        "skill_evidence": group_results,
        "matched_skill_evidence": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "matched" if data["score"] >= 25 else "missing",
                "evidence_level": data["evidence_level"],
                "source": data["source"],
                "weight": round(data["score"] / 100, 2),
                "matched_terms": data["matched_terms"],
            }
            for group, data in group_results.items()
        ],
        "missing_or_weak_skills": [
            {
                "skill": group.replace("_", " ").title(),
                "status": "missing" if group in missing_mandatory else "weak",
                "evidence_level": group_results[group]["evidence_level"],
            }
            for group in missing_mandatory + weak_mandatory
        ],
        "employer_name_only_skills": [],
        "skill_match_percent": mandatory_coverage,
        "mandatory_skill_coverage": mandatory_coverage,
        "preferred_skill_coverage": group_results["nice_to_have"]["score"],
        "core_skill_match_percent": core_percent,
        "matched_core_skill_groups": matched_groups,
        "missing_core_skill_groups": missing_mandatory + weak_mandatory,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), experience_fit["relevant_years"]),
        "target_seniority_level": jd_profile.get("seniority_level"),
        "recommendation": recommendation,
        "recruiter_recommendation": recruiter_recommendation,
        "label": label,
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "knockout_flags": knockout_flags,
        "kyc_only_profile": knockout_flags["kyc_only_profile"],
        "generic_banking_only": knockout_flags["generic_banking_only"],
        "ranking_reason": ranking_reason,
        "experience_fit": experience_fit["label"],
        "all_critical_requirements_met": not missing_mandatory and not weak_mandatory and not wrong_role_flags and experience_fit["fit"] == "within",
        "jd_role_family": "aml_transaction_monitoring",
        "jd_skill_groups": jd_profile.get("core_skill_groups") or {},
        "evidence_group_scores": group_results,
        "role_relevance_label": parsed.get("experience_relevance_label") or "",
        "experience_fit_label": experience_fit["label"],
        "scoring_breakdown": {
            "aml_transaction_monitoring_group_scores": group_results,
            "mandatory_group_status": {
                "strong": strong_mandatory,
                "weak": weak_mandatory,
                "missing": missing_mandatory,
            },
            "wrong_role_flags": wrong_role_flags,
            "experience_fit": experience_fit,
            "aml_tool_count": aml_tool_count,
            "financial_crime_tool_profile": financial_crime_tool_profile,
            "over_l2_experience": over_l2_experience,
            "senior_l2_exempt": senior_l2_exempt,
            "score_caps_applied": caps,
            "missing_core_skill_groups": missing_mandatory + weak_mandatory,
            "knockout_flags": knockout_flags,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("designation") or parsed.get("current_title") or "",
            "total_experience_years": experience_fit["total_years"],
            "jd_relevant_experience_years": experience_fit["relevant_years"],
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "recruiter_recommendation": recruiter_recommendation,
            "label": label,
            "matched_mandatory_groups": strong_mandatory,
            "missing_mandatory_groups": missing_mandatory,
            "wrong_role_flags": wrong_role_flags,
            "risk_flags": risk_flags,
        },
    }
    role_identity = _generic_role_identity(parsed, jd_profile, mandatory_coverage, _safe_float(parsed.get("role_relevance_score")), core_percent)
    return _attach_jd_profile_metadata(result, jd_profile, parsed, role_identity)


def _score_candidate_role_agnostic(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    if (jd_profile.get("role_family") or "").lower() == "applied_ml_engineer":
        return _score_candidate_applied_ml(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)
    if (jd_profile.get("role_family") or "").lower() == "product_software_architect":
        return _score_candidate_product_architect(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)
    if (jd_profile.get("role_family") or "").lower() == "m365_migration_sme":
        return _score_candidate_m365_migration(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)
    if (jd_profile.get("role_family") or "").lower() == "aml_transaction_monitoring":
        return _score_candidate_aml_transaction_monitoring(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)
    if (jd_profile.get("role_family") or "").lower() == "software_frontend":
        result = _score_candidate_frontend(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)
        role_identity = _generic_role_identity(
            parsed,
            jd_profile,
            result.get("mandatory_skill_coverage") or result.get("skill_match_percent") or 0,
            _safe_float(parsed.get("role_relevance_score")),
            _safe_float(result.get("project_strength_score")),
        )
        return _attach_jd_profile_metadata(result, jd_profile, parsed, role_identity)
    if (jd_profile.get("role_family") or "").lower() in {"full_stack", "dotnet_full_stack"}:
        result = _score_candidate_full_stack(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)
        role_identity = _generic_role_identity(
            parsed,
            jd_profile,
            result.get("mandatory_skill_coverage") or result.get("skill_match_percent") or 0,
            _safe_float(parsed.get("role_relevance_score")),
            _safe_float((result.get("scoring_breakdown") or {}).get("project_work_strength")),
        )
        return _attach_jd_profile_metadata(result, jd_profile, parsed, role_identity)
    if (jd_profile.get("role_family") or "").lower() == "software_backend":
        result = _score_candidate_backend(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)
        role_identity = _generic_role_identity(
            parsed,
            jd_profile,
            result.get("mandatory_skill_coverage") or result.get("skill_match_percent") or 0,
            _safe_float(parsed.get("role_relevance_score")),
            _safe_float((result.get("scoring_breakdown") or {}).get("project_work_strength")),
        )
        return _attach_jd_profile_metadata(result, jd_profile, parsed, role_identity)

    candidate_skills = normalize_skill_list(parsed.get("key_skills", []))
    required_skills = normalize_skill_list(jd_profile.get("must_have_skills") or expand_skill_requirements(jd_skills))
    preferred_skills = normalize_skill_list(jd_profile.get("nice_to_have_skills") or _split_skill_values((jd_data or {}).get("preferred_skills")))

    matched = []
    transferable = []
    missing = []
    evidence = {}
    mandatory_coverage_points = 0.0
    skill_evidence_depth = {}
    matched_skill_evidence = []
    employer_name_only_skills = []
    for required in required_skills:
        direct, equiv = _skill_match(required, candidate_skills)
        skill_evidence = _classify_skill_evidence(required, parsed, resume_text, candidate_skills, equivalent=equiv)
        resume_hit = _resume_evidence_skill_match(required, resume_text)
        if resume_hit and skill_evidence.get("evidence_level") in {"missing", "keyword_only"}:
            skill_evidence = {
                **skill_evidence,
                "status": "matched",
                "evidence_level": "professional_weak",
                "depth": "work_experience_evidence",
                "source": "resume_evidence",
                "weight": max(skill_evidence.get("weight") or 0, 0.72),
            }

        weight = float(skill_evidence.get("weight") or 0)
        status = skill_evidence.get("status") or "missing"
        if skill_evidence.get("employer_name_only"):
            _append_unique(employer_name_only_skills, [required])
            _append_unique(missing, [required])
        elif status != "missing" and weight > 0:
            _append_unique(matched, [required])
            mandatory_coverage_points += weight
            matched_skill_evidence.append(skill_evidence)
        elif equiv and not skill_evidence.get("employer_name_only"):
            _append_unique(transferable, [required])
            mandatory_coverage_points += max(weight, 0.30)
            matched_skill_evidence.append({**skill_evidence, "status": "partial", "weight": max(weight, 0.30)})
        else:
            _append_unique(missing, [required])
        evidence[required] = skill_evidence
        skill_evidence_depth[required] = skill_evidence.get("depth", "missing")

    preferred_matched = []
    for preferred in preferred_skills:
        direct, equiv = _skill_match(preferred, candidate_skills)
        if direct or equiv or _contains_skill_text(preferred, resume_text):
            _append_unique(preferred_matched, [preferred])

    required_count = max(len(required_skills), 1)
    mandatory_coverage = round((mandatory_coverage_points / required_count) * 100, 2)
    core_match = match_core_skill_groups(
        jd_profile.get("core_skill_groups") or {},
        candidate_skills,
        resume_text,
    )
    core_percent = core_match["core_skill_match_percent"]
    direct_match_percent = round(((len(matched) + len(transferable) * 0.55) / required_count) * 100, 2)

    min_years = _safe_float(jd_profile.get("min_experience_years") or (jd_data or {}).get("min_experience_years"))
    max_years = _safe_float(jd_profile.get("max_experience_years") or (jd_data or {}).get("max_experience_years"))
    relevant_years = _safe_float(parsed.get("relevant_experience_years"))
    total_years = _safe_float(parsed.get("total_experience_years"))
    if not missing and direct_match_percent >= 80 and core_percent >= 80:
        coverage_floor = 75
        if relevant_years >= max(min_years or 0, 1):
            coverage_floor = 82
        if (jd_profile.get("role_family") or "") == "data_analytics" and relevant_years >= max(min_years or 0, 1):
            coverage_floor = 85
        mandatory_coverage = max(mandatory_coverage, min(coverage_floor, direct_match_percent))
    if min_years:
        experience_fit_percent = min(100, round((relevant_years / min_years) * 100, 2))
    else:
        experience_fit_percent = min(100, round((relevant_years / 2) * 100, 2)) if relevant_years else 35
    if max_years and total_years > max_years + 3 and relevant_years > max_years:
        experience_fit_percent = max(35, experience_fit_percent - min(30, (total_years - max_years) * 4))
    over_target_years = max(0, total_years - max_years) if max_years else 0
    overqualified_penalty = 0
    if max_years and over_target_years > 1:
        comparison_years = relevant_years if relevant_years > 0 else total_years
        if comparison_years > max_years:
            overqualified_penalty = min(18, round((over_target_years - 1) * 1.6, 2))
            experience_fit_percent = max(25, experience_fit_percent - overqualified_penalty)

    role_relevance = _safe_float(parsed.get("role_relevance_score"))
    evidence_strength = _project_work_evidence_strength(
        parsed,
        resume_text,
        matched + transferable + preferred_matched,
        jd_profile.get("role_family") or "other",
    )
    education_fit = _generic_education_fit(parsed, jd_data or {})
    semantic_raw = parsed.get("semantic_score")
    if semantic_raw is None:
        semantic_raw = cosine_similarity_cached(jd_text, resume_text)
    semantic_percent = max(0, min(100, float(semantic_raw or 0) * 100))

    final_score = (
        mandatory_coverage * 0.30
        + core_percent * 0.20
        + experience_fit_percent * 0.20
        + role_relevance * 0.10
        + evidence_strength * 0.10
        + education_fit * 0.05
        + semantic_percent * 0.05
    )

    confidence = min(100, round(
        30
        + mandatory_coverage * 0.25
        + core_percent * 0.18
        + min(100, role_relevance) * 0.18
        + min(100, evidence_strength) * 0.14
        + _safe_float(parsed.get("parser_quality_score"), parsed.get("resume_quality_score") or 70) * 0.15,
        2,
    ))
    family_confidence = _safe_float(jd_profile.get("role_family_confidence"), 0)
    if (jd_profile.get("role_family") or "other") == "other" or family_confidence < 40:
        confidence = min(confidence, 78)

    caps = []
    recruiter_flags = []
    risk_flags = []
    seniority = (jd_profile.get("seniority_level") or "unknown").lower()
    missing_core_groups = core_match["missing_core_skill_groups"]
    parser_action = parsed.get("parser_quality_action")
    if min_years and relevant_years < min_years:
        seniority_fit = "under"
    elif max_years and relevant_years > max_years:
        seniority_fit = "over"
    elif min_years or max_years:
        seniority_fit = "within"
    else:
        seniority_fit = "unclear"

    qa_target = _is_qa_target(jd_profile)
    qa_evidence = _qa_group_evidence_strength(jd_profile.get("core_skill_groups") or {}, evidence) if qa_target else {
        "professional_groups": [],
        "project_groups": [],
        "keyword_only_groups": [],
        "training_only_groups": [],
        "professional_group_count": 0,
        "project_group_count": 0,
        "keyword_only_group_count": 0,
        "training_only_group_count": 0,
    }
    ba_target = _is_business_analyst_target(jd_profile)
    ba_evidence = _qa_group_evidence_strength(jd_profile.get("core_skill_groups") or {}, evidence) if ba_target else {
        "professional_groups": [],
        "project_groups": [],
        "keyword_only_groups": [],
        "training_only_groups": [],
        "professional_group_count": 0,
        "project_group_count": 0,
        "keyword_only_group_count": 0,
        "training_only_group_count": 0,
    }
    role_identity = (
        _qa_role_identity(parsed, mandatory_coverage, qa_evidence["professional_group_count"])
        if qa_target
        else _generic_role_identity(parsed, jd_profile, mandatory_coverage, role_relevance, evidence_strength)
    )
    applied_boosts = []
    if qa_target:
        alignment = role_identity["role_alignment"]
        professional_group_count = qa_evidence["professional_group_count"]
        if alignment == "direct" and core_percent >= 70 and professional_group_count >= 4 and mandatory_coverage < 65:
            uplift = round((65 - mandatory_coverage) * 0.30, 2)
            mandatory_coverage = 65
            final_score += uplift
            applied_boosts.append({"boost": uplift, "reason": "Direct QA professional evidence covers most core groups despite missing optional tool keywords."})
        if alignment == "direct" and mandatory_coverage >= 60 and professional_group_count >= 3:
            boost = 7 if seniority_fit != "over" else 4
            final_score += boost
            applied_boosts.append({"boost": boost, "reason": "Direct QA title with professional evidence across core QA groups."})
        if alignment == "direct" and min_years and relevant_years >= min_years and professional_group_count >= 2:
            boost = 3
            final_score += boost
            applied_boosts.append({"boost": boost, "reason": "Direct QA experience satisfies the JD minimum."})
        if alignment == "direct" and role_identity.get("latest_role_label") and QA_DIRECT_TITLE_RE.search(role_identity["latest_role_label"]):
            boost = 2
            final_score += boost
            applied_boosts.append({"boost": boost, "reason": "Latest role is QA/testing aligned."})

    if ba_target:
        alignment = role_identity["role_alignment"]
        critical_professional = [group for group in ba_evidence["professional_groups"] if group in BA_CRITICAL_GROUPS]
        critical_project = [group for group in ba_evidence["project_groups"] if group in BA_CRITICAL_GROUPS]
        critical_count = len(set(critical_professional + critical_project))
        title_text = " ".join([
            str(role_identity.get("primary_role_label") or ""),
            str(role_identity.get("latest_role_label") or ""),
        ])
        direct_ba_title = bool(BUSINESS_ANALYST_DIRECT_TITLE_RE.search(title_text))
        if direct_ba_title and critical_count >= 2 and mandatory_coverage < 65:
            uplift = round((65 - mandatory_coverage) * 0.25, 2)
            mandatory_coverage = 65
            final_score += uplift
            applied_boosts.append({"boost": uplift, "reason": "Direct Business Analyst role evidence covers core BA responsibilities."})
        if direct_ba_title and critical_count >= 3:
            boost = 7 if seniority_fit != "over" else 4
            final_score += boost
            applied_boosts.append({"boost": boost, "reason": "Direct Business Analyst title with requirements/stakeholder evidence."})
        elif alignment in {"adjacent", "transferable"} and critical_count >= 3 and mandatory_coverage >= 55:
            boost = 4
            final_score += boost
            applied_boosts.append({"boost": boost, "reason": "Adjacent analyst profile has strong BA responsibility evidence."})

    final_score_before_caps = round(max(0, min(100, final_score)), 2)

    def cap_at(limit, reason, flag=None, risk=None):
        nonlocal final_score
        if final_score > limit:
            final_score = limit
        caps.append({"cap": limit, "reason": reason})
        if flag:
            _append_unique(recruiter_flags, [flag])
        if risk:
            _append_unique(risk_flags, [risk])

    has_valid_work_date = any(
        isinstance(job, dict) and (job.get("start_date") or job.get("end_date"))
        for job in parsed.get("experience") or []
    )

    if parser_action == "manual_review_required":
        cap_at(58, "Parser quality requires manual review.", "parser_manual_review", "parser_quality")
    if min_years and not has_valid_work_date:
        cap_at(58, "No valid professional work dates were found for a JD that requires professional experience.", "no_valid_work_dates", "no_valid_professional_work_dates")
    if min_years and relevant_years < min_years:
        if min_years >= 2 and relevant_years < 1:
            cap_at(60, "JD-related professional experience is below 1 year for a role requiring at least 2 years.", "under_experienced", "below_jd_experience_range")
        else:
            cap_at(72, "JD-related professional experience is below the minimum required range.", "under_experienced", "below_jd_experience_range")
    if max_years and seniority_fit == "over":
        if relevant_years >= max_years + 2 or total_years >= max_years + 3:
            cap_at(77, "Candidate is above the JD experience range and needs recruiter review.", "over_experienced", "over_jd_experience_range")
        else:
            cap_at(82, "Candidate is slightly above the JD experience range; review before client shortlist.", "slightly_over_range", "over_jd_experience_range")
    if max_years and max_years <= 3 and total_years > 12:
        cap_at(65, "Candidate is strongly overqualified for a junior 1-3 year JD.", "strongly_overqualified", "over_jd_experience_range")
    elif max_years and max_years <= 3 and total_years > 8:
        cap_at(72, "Candidate is overqualified for a junior 1-3 year JD.", "over_experienced", "over_jd_experience_range")
    if seniority in {"senior", "lead", "manager", "architect"} and relevant_years < 2:
        cap_at(50, "Senior-level role but relevant experience is below 2 years.", "under_experienced", "seniority_experience_gap")
    elif seniority in {"senior", "lead", "manager", "architect"} and relevant_years < 4:
        cap_at(65, "Senior-level role but relevant experience is below 4 years.", "seniority_review", "seniority_experience_gap")
    if mandatory_coverage < 25:
        cap_at(50, "Mandatory skill coverage is below 25%.", "missing_core_skills", "mandatory_skill_gap")
    elif mandatory_coverage < 40:
        cap_at(60, "Mandatory skill coverage is below 40%.", "missing_core_skills", "mandatory_skill_gap")
    if len(missing_core_groups) >= 2:
        cap_at(65, "Two or more JD core skill groups are missing.", "missing_core_skills", "core_group_gap")
    if role_relevance < 35 and relevant_years < 1:
        cap_at(55, "Current role/domain is weakly related and relevant experience is below 1 year.", "role_domain_gap", "role_relevance")
    elif role_relevance < 50:
        cap_at(65, "Role fit is partial or weak for the JD role family.", "partial_role_match", "role_relevance")
    if total_years >= 5 and relevant_years < 1 and (parsed.get("experience_relevance_label") in {"unproven", "needs_validation"}):
        cap_at(70, "High total experience claim needs validation because role-relevant work evidence is weak.", "experience_needs_validation", "experience_needs_validation")

    if qa_target:
        alignment = role_identity["role_alignment"]
        professional_group_count = qa_evidence["professional_group_count"]
        project_group_count = qa_evidence["project_group_count"]
        keyword_group_count = qa_evidence["keyword_only_group_count"]
        if alignment == "mismatch":
            cap_at(45, "QA JD requires QA/testing role identity; candidate role is not QA-aligned.", "primary_role_mismatch", "qa_role_identity_gap")
        elif alignment == "weak":
            cap_at(55, "QA role identity is weak and needs recruiter validation.", "qa_role_weak", "qa_role_identity_gap")
        elif alignment == "transferable":
            limit = 58 if mandatory_coverage < 75 or professional_group_count < 3 else 64
            cap_at(limit, "QA match is transferable but not a direct QA automation profile.", "qa_transferable_only", "qa_role_identity_gap")
        elif alignment == "adjacent":
            if mandatory_coverage < 75:
                cap_at(58, "Primary role is software development and QA mandatory coverage is below 75%.", "primary_role_mismatch", "qa_role_identity_gap")
            elif professional_group_count < 3:
                cap_at(62, "Primary role is software development and professional QA evidence is thin.", "qa_professional_evidence_gap", "qa_evidence_gap")
            else:
                cap_at(72, "Adjacent software profile with QA evidence needs recruiter review for a QA role.", "qa_adjacent_profile", "qa_role_identity_gap")

        if core_percent < 40:
            cap_at(50, "QA core group coverage is below 40%.", "qa_core_group_gap", "mandatory_skill_gap")
        elif core_percent < 60:
            cap_at(58, "QA core group coverage is below 60%.", "qa_core_group_gap", "mandatory_skill_gap")
        elif core_percent < 75 and alignment != "direct":
            cap_at(62, "Non-direct QA profile is missing at least two QA core groups.", "qa_core_group_gap", "mandatory_skill_gap")

        if role_identity.get("primary_is_developer") and mandatory_coverage < 75:
            cap_at(58, "Developer-primary profile lacks enough mandatory QA coverage for this role.", "primary_role_mismatch", "qa_role_identity_gap")
        if professional_group_count + project_group_count < 2:
            cap_at(55, "QA tools are not backed by enough professional or project evidence.", "qa_professional_evidence_gap", "qa_evidence_gap")
        elif professional_group_count < 3 and alignment != "direct":
            cap_at(58, "Non-direct QA profile lacks professional evidence across enough core QA groups.", "qa_professional_evidence_gap", "qa_evidence_gap")
        if keyword_group_count >= max(2, professional_group_count + project_group_count) and alignment != "direct":
            cap_at(60, "Most QA skill matches are keyword/listed-only instead of work evidence.", "skill_match_mostly_listed_only", "qa_evidence_gap")

        if max_years and max_years <= 3:
            if total_years > 12:
                cap_at(60, "Candidate is strongly overqualified for a junior QA Automation role.", "strongly_overqualified", "over_jd_experience_range")
            elif total_years > 8:
                cap_at(64, "Candidate is overqualified for a junior QA Automation role.", "over_experienced", "over_jd_experience_range")
            elif total_years > 5 and alignment == "direct":
                cap_at(68, "Direct QA profile is above the junior QA experience band.", "over_experienced", "over_jd_experience_range")
            elif total_years > 4 and alignment != "direct":
                cap_at(62, "Non-direct profile is above the junior QA experience band.", "over_experienced", "over_jd_experience_range")

    if ba_target:
        alignment = role_identity["role_alignment"]
        critical_groups = set(ba_evidence["professional_groups"] + ba_evidence["project_groups"]) & BA_CRITICAL_GROUPS
        critical_count = len(critical_groups)
        keyword_group_count = ba_evidence["keyword_only_group_count"]
        title_text = " ".join([
            str(role_identity.get("primary_role_label") or ""),
            str(role_identity.get("latest_role_label") or ""),
        ])
        direct_ba_title = bool(BUSINESS_ANALYST_DIRECT_TITLE_RE.search(title_text))
        adjacent_analytics_title = bool(BUSINESS_ANALYST_ADJACENT_TITLE_RE.search(title_text))

        if adjacent_analytics_title and critical_count < 2:
            cap_at(52, "Analytics/dashboard profile lacks Business Analyst core responsibility evidence.", "analytics_only_for_ba", "ba_core_evidence_gap")

        if critical_count == 0:
            cap_at(52, "Business Analyst JD requires requirements, documentation, stakeholder, UAT, or process-flow evidence.", "ba_core_evidence_gap", "mandatory_skill_gap")
        elif critical_count < 2 and not direct_ba_title:
            cap_at(55, "Candidate has limited BA core responsibility evidence for this JD.", "ba_core_evidence_gap", "mandatory_skill_gap")

        if alignment in {"weak", "mismatch"}:
            cap_at(48, "Candidate role identity is not Business Analyst aligned.", "primary_role_mismatch", "ba_role_identity_gap")
        elif alignment == "transferable" and critical_count < 3:
            cap_at(58, "Transferable profile lacks enough BA core responsibility coverage.", "ba_transferable_only", "ba_role_identity_gap")

        if core_percent < 45:
            cap_at(52, "Business Analyst core group coverage is below 45%.", "ba_core_group_gap", "mandatory_skill_gap")
        elif core_percent < 65 and alignment != "direct":
            cap_at(60, "Non-direct BA profile is missing multiple BA core groups.", "ba_core_group_gap", "mandatory_skill_gap")

        if keyword_group_count >= max(2, ba_evidence["professional_group_count"] + ba_evidence["project_group_count"]) and not direct_ba_title:
            cap_at(58, "Most BA matches are keyword/listed-only instead of work evidence.", "skill_match_mostly_listed_only", "ba_evidence_gap")

    scoring_mode = jd_profile.get("scoring_mode") or "legacy"
    profile_confidence = _safe_float(jd_profile.get("profile_confidence"), _safe_float(jd_profile.get("role_family_confidence")))
    if scoring_mode == "dynamic" and profile_confidence < 75:
        alignment = role_identity["role_alignment"]
        if alignment != "direct":
            cap_at(62, "Dynamic JD profile is low confidence; non-direct candidates cannot exceed review range.", "dynamic_profile_review", "dynamic_profile_low_confidence")
        if len(missing_core_groups) >= max(1, len((jd_profile.get("core_skill_groups") or {})) // 2):
            cap_at(58, "Dynamic JD profile has critical mandatory group gaps.", "dynamic_mandatory_gap", "mandatory_skill_gap")
        dynamic_keyword_matches = [
            item for item in evidence.values()
            if item.get("status") in {"matched", "partial", "project_only", "weak"}
            and item.get("evidence_level") in {"skills_section_only", "keyword_only"}
        ]
        dynamic_proven_matches = [
            item for item in evidence.values()
            if item.get("status") in {"matched", "partial", "project_only"}
            and item.get("evidence_level") in {"professional_strong", "professional_weak", "project_strong", "project_weak"}
        ]
        if dynamic_keyword_matches and len(dynamic_keyword_matches) >= max(1, len(dynamic_proven_matches)):
            cap_at(55, "Dynamic JD match is mostly keyword-only.", "skill_match_mostly_listed_only", "dynamic_keyword_only")

    if missing:
        _append_unique(risk_flags, ["missing_mandatory_skills"])
    if employer_name_only_skills:
        _append_unique(risk_flags, ["employer_name_only_match"])
        _append_unique(recruiter_flags, ["employer_name_only_match"])
    if missing_core_groups:
        _append_unique(risk_flags, ["missing_core_skill_groups"])
    skill_section_only_matches = [
        item for item in evidence.values()
        if item.get("status") in {"matched", "partial", "project_only"}
        and item.get("evidence_level") in {"skills_section_only", "keyword_only"}
    ]
    proven_matches = [
        item for item in evidence.values()
        if item.get("status") in {"matched", "partial", "project_only"}
        and item.get("evidence_level") in {"professional_strong", "professional_weak", "project_strong", "project_weak"}
    ]
    if skill_section_only_matches and len(skill_section_only_matches) > len(proven_matches):
        _append_unique(recruiter_flags, ["skill_match_mostly_listed_only"])
        _append_unique(risk_flags, ["skill_match_mostly_listed_only"])
    if parsed.get("experience_warnings"):
        _append_unique(risk_flags, ["experience_warnings"])
    if (jd_profile.get("role_family") or "other") == "other" or family_confidence < 40:
        _append_unique(risk_flags, ["unknown_role_family"])
    if not caps and final_score >= 72:
        _append_unique(recruiter_flags, ["role_aligned"])
    if evidence_strength >= 60:
        _append_unique(recruiter_flags, ["strong_evidence"])
        _append_unique(recruiter_flags, ["strong_professional_evidence"])
    if relevant_years and total_years and relevant_years < total_years * 0.5:
        _append_unique(recruiter_flags, ["partial_relevance"])
    if _safe_float(parsed.get("project_only_exposure")) and not _safe_float(parsed.get("professional_role_experience_years")):
        _append_unique(recruiter_flags, ["project_only_exposure"])
        _append_unique(risk_flags, ["project_only_exposure"])
    if _safe_float(parsed.get("training_or_certification_exposure")) and not relevant_years:
        _append_unique(recruiter_flags, ["training_only_exposure"])
        _append_unique(risk_flags, ["training_only_exposure"])
    if seniority_fit == "under":
        _append_unique(recruiter_flags, ["under_experienced"])
        risk_flags = [flag for flag in risk_flags if flag != "over_experienced"]
    elif seniority_fit == "over":
        _append_unique(recruiter_flags, ["over_experienced"])
        risk_flags = [flag for flag in risk_flags if flag != "under_experienced"]
    elif seniority_fit == "within":
        _append_unique(recruiter_flags, ["within_experience_range"])

    final_score = round(max(0, min(100, final_score)), 2)
    rank_score = round(min(100, final_score + min(5, confidence / 25 if not risk_flags else 0)), 2)
    if qa_target:
        if role_identity["role_alignment"] == "direct" and "missing_mandatory_skills" not in risk_flags:
            rank_score = round(min(100, max(rank_score, final_score + 3)), 2)
        elif role_identity["role_alignment"] in {"adjacent", "transferable", "weak", "mismatch"}:
            rank_score = round(min(rank_score, final_score), 2)
    if ba_target:
        if role_identity["role_alignment"] == "direct" and len(set(ba_evidence["professional_groups"] + ba_evidence["project_groups"]) & BA_CRITICAL_GROUPS) >= 2:
            rank_score = round(min(100, max(rank_score, final_score + 2)), 2)
        elif role_identity["role_alignment"] in {"adjacent", "transferable", "weak", "mismatch"}:
            rank_score = round(min(rank_score, final_score), 2)
    recommendation = _generic_recommendation(final_score, mandatory_coverage, confidence, caps, risk_flags)
    band = fit_band(rank_score, mandatory_coverage / 100, confidence)

    ranking_reason = (
        f"Rank score {rank_score}/100 with {confidence}% confidence: "
        f"{mandatory_coverage}% mandatory skill coverage, {core_percent}% core group coverage, "
        f"{relevant_years:g}/{total_years:g} relevant/total years, role relevance {role_relevance:g}/100."
    )
    if missing:
        ranking_reason += f" Missing skills: {', '.join(missing[:4])}."
    if missing_core_groups:
        ranking_reason += f" Missing core groups: {', '.join(missing_core_groups[:4])}."
    if overqualified_penalty and max_years:
        ranking_reason += f" Candidate is over target experience range for this JD (max {max_years:g} years)."
    if caps:
        ranking_reason += " Caps applied: " + " ".join(item["reason"] for item in caps[:2])

    score_result = {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": band,
        "skill_score": round(mandatory_coverage * 0.30 + core_percent * 0.20, 2),
        "experience_score": round(experience_fit_percent * 0.20, 2),
        "semantic_score": float(semantic_raw or 0),
        "semantic_weight": round(semantic_percent * 0.05, 2),
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": round(role_relevance * 0.10, 2),
        "education_score": round(education_fit * 0.05, 2),
        "overqualified_penalty": overqualified_penalty,
        "experience_target_max_years": max_years or None,
        "experience_over_target_years": round(over_target_years, 2),
        "role_alignment": role_identity["role_alignment"],
        "primary_role_family": role_identity["primary_role_family"],
        "primary_role_label": role_identity["primary_role_label"],
        "role_alignment_reason": role_identity["role_alignment_reason"],
        "professional_qa_group_count": qa_evidence["professional_group_count"],
        "keyword_only_qa_group_count": qa_evidence["keyword_only_group_count"],
        "qa_evidence_groups": qa_evidence,
        "business_analyst_evidence_groups": ba_evidence,
        "final_score_before_caps": final_score_before_caps,
        "score_boosts_applied": applied_boosts,
        "matched_skills": matched + transferable,
        "direct_matched_skills": matched,
        "transferable_skills": transferable,
        "preferred_matched_skills": preferred_matched,
        "missing_skills": missing,
        "skill_evidence_depth": skill_evidence_depth,
        "skill_evidence": evidence,
        "matched_skill_evidence": matched_skill_evidence,
        "missing_or_weak_skills": [
            item for item in evidence.values()
            if item.get("status") in {"missing", "weak", "training_only"} or item.get("evidence_level") in {"skills_section_only", "keyword_only", "employer_name_only"}
        ],
        "employer_name_only_skills": employer_name_only_skills,
        "skill_match_percent": mandatory_coverage,
        "mandatory_skill_coverage": mandatory_coverage,
        "preferred_skill_coverage": round((len(preferred_matched) / max(len(preferred_skills), 1)) * 100, 2) if preferred_skills else 0,
        "core_skill_match_percent": core_percent,
        "matched_core_skill_groups": core_match["matched_core_skill_groups"],
        "missing_core_skill_groups": missing_core_groups,
        "confidence_score": confidence,
        "seniority_level": parsed.get("seniority_level") or infer_seniority(parsed.get("designation"), relevant_years),
        "target_seniority_level": seniority,
        "recommendation": recommendation,
        "label": _recommendation_label(recommendation, recruiter_flags, risk_flags, final_score, mandatory_coverage, seniority_fit),
        "score_caps_applied": caps,
        "recruiter_flags": recruiter_flags,
        "risk_flags": risk_flags,
        "ranking_reason": ranking_reason,
        "scoring_breakdown": {
            "mandatory_skill_coverage_component": round(mandatory_coverage * 0.30, 2),
            "core_skill_group_component": round(core_percent * 0.20, 2),
            "relevant_experience_component": round(experience_fit_percent * 0.20, 2),
            "role_title_domain_component": round(role_relevance * 0.10, 2),
            "evidence_strength_component": round(evidence_strength * 0.10, 2),
            "education_certification_component": round(education_fit * 0.05, 2),
            "semantic_component": round(semantic_percent * 0.05, 2),
            "experience_fit_percent": experience_fit_percent,
            "evidence_strength": evidence_strength,
            "skill_evidence_depth": skill_evidence_depth,
            "matched_skill_evidence": matched_skill_evidence,
            "employer_name_only_skills": employer_name_only_skills,
            "overqualified_penalty": overqualified_penalty,
            "experience_target_max_years": max_years or None,
            "experience_over_target_years": round(over_target_years, 2),
            "seniority_fit": seniority_fit,
            "role_alignment": role_identity["role_alignment"],
            "primary_role_family": role_identity["primary_role_family"],
            "primary_role_label": role_identity["primary_role_label"],
            "role_alignment_reason": role_identity["role_alignment_reason"],
            "qa_evidence_groups": qa_evidence,
            "business_analyst_evidence_groups": ba_evidence,
            "final_score_before_caps": final_score_before_caps,
            "score_boosts_applied": applied_boosts,
            "domain_specific_experience_years": parsed.get("domain_specific_experience_years"),
            "professional_role_experience_years": parsed.get("professional_role_experience_years"),
            "training_or_certification_exposure": parsed.get("training_or_certification_exposure"),
            "project_only_exposure": parsed.get("project_only_exposure"),
            "current_title": parsed.get("current_title") or parsed.get("designation"),
            "most_relevant_role": parsed.get("most_relevant_role"),
            "target_role_alignment": parsed.get("target_role_alignment"),
            "jd_aligned_work_evidence": parsed.get("jd_aligned_work_evidence") or [],
            "jd_aligned_project_evidence": parsed.get("jd_aligned_project_evidence") or [],
            "non_jd_projects": parsed.get("non_jd_projects") or [],
            "missing_or_weak_skills": [
                item for item in evidence.values()
                if item.get("status") in {"missing", "weak", "training_only"} or item.get("evidence_level") in {"skills_section_only", "keyword_only", "employer_name_only"}
            ],
            "score_caps_applied": caps,
        },
        "candidate_screening_summary": {
            "candidate_name": parsed.get("full_name") or "",
            "current_title": parsed.get("current_title") or parsed.get("designation") or "",
            "most_relevant_title": parsed.get("most_relevant_role") or "",
            "target_role_alignment": role_identity["role_alignment"],
            "primary_role_family": role_identity["primary_role_family"],
            "role_alignment_reason": role_identity["role_alignment_reason"],
            "qa_evidence_groups": qa_evidence,
            "business_analyst_evidence_groups": ba_evidence,
            "total_experience_years": total_years,
            "jd_relevant_experience_years": relevant_years,
            "seniority_fit": seniority_fit,
            "final_score": final_score,
            "confidence": confidence,
            "recommendation": recommendation,
            "label": _recommendation_label(recommendation, recruiter_flags, risk_flags, final_score, mandatory_coverage, seniority_fit),
            "matched_skills": matched_skill_evidence,
            "missing_or_weak_skills": [
                item for item in evidence.values()
                if item.get("status") in {"missing", "weak", "training_only"} or item.get("evidence_level") in {"skills_section_only", "keyword_only", "employer_name_only"}
            ],
            "jd_aligned_work_evidence": parsed.get("jd_aligned_work_evidence") or [],
            "jd_aligned_project_evidence": parsed.get("jd_aligned_project_evidence") or [],
            "non_jd_projects": parsed.get("non_jd_projects") or [],
            "risk_flags": risk_flags,
            "parser_quality_flags": parsed.get("parser_quality_flags") or [],
        },
    }
    return _attach_jd_profile_metadata(score_result, jd_profile, parsed, role_identity)


def _contains_skill_text(skill, text):
    if not skill or not text:
        return False
    pattern = re.escape(str(skill).lower()).replace(r"\ ", r"\s+")
    return bool(re.search(r"\b" + pattern + r"\b", text.lower(), re.I))


def score_candidate(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile=None):
    if jd_profile:
        return _score_candidate_role_agnostic(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)

    candidate_skills = normalize_skill_list(parsed.get("key_skills", []))
    required_skills = expand_skill_requirements(jd_skills)
    preferred_skills = expand_skill_requirements(
        _split_skill_values(jd_data.get("preferred_skills") or jd_data.get("nice_to_have_skills"))
    )

    matched = []
    transferable = []
    missing = []
    preferred_matched = []
    preferred_transferable = []
    evidence = {}

    for required in required_skills:
        direct, equivalent = _skill_match(required, candidate_skills)

        if direct:
            _append_unique(matched, [required])
        elif equivalent:
            _append_unique(transferable, [required])
        elif _resume_evidence_skill_match(required, resume_text):
            _append_unique(transferable, [required])
        else:
            _append_unique(missing, [required])

    for preferred in preferred_skills:
        direct, equivalent = _skill_match(preferred, candidate_skills)
        if direct:
            _append_unique(preferred_matched, [preferred])
        elif equivalent:
            _append_unique(preferred_transferable, [preferred])

    required_count = max(len(required_skills), 1)
    preferred_count = max(len(preferred_skills), 1)
    mandatory_coverage = (len(matched) + len(transferable) * 0.55) / required_count
    preferred_coverage = (len(preferred_matched) + len(preferred_transferable) * 0.5) / preferred_count if preferred_skills else 0

    evidence_points = 0.0
    evidence_skills = matched + transferable + preferred_matched + preferred_transferable
    for skill in evidence_skills[:14]:
        skill_evidence = _evidence_for_skill(skill, resume_text)
        evidence[skill] = skill_evidence
        if skill_evidence["count"]:
            evidence_points += min(skill_evidence["count"], 4) * 0.55
            evidence_points += 0.8 if skill_evidence["experience"] else 0
            evidence_points += 0.8 if skill_evidence["project"] else 0
            evidence_points += 0.4 if skill_evidence["recent"] else 0

    skill_score = min(40, round((mandatory_coverage * 36) + (preferred_coverage * 2) + min(evidence_points, 8) * 0.25, 2))

    years = float(parsed.get("total_experience_years") or 0)
    required_years = float(jd_data.get("min_experience_years") or 0)
    max_years = float(jd_data.get("max_experience_years") or 0)
    relevant_years = float(parsed.get("relevant_experience_years") or 0)
    is_data_analyst_role = _is_data_analyst_jd(jd_text, jd_data, required_skills)
    direct_role_signal = _safe_float(parsed.get("direct_relevant_experience_years")) >= 1 or (
        _has_direct_data_role_title(parsed.get("designation")) and relevant_years >= max(required_years or 0, 1)
    )
    transition_candidate = bool(parsed.get("transition_candidate")) or (
        is_data_analyst_role
        and years > max(max_years or 0, 3)
        and relevant_years <= max(max_years or 0, required_years or 0, 1) + 1
        and not direct_role_signal
    )

    if required_years:
        experience_ratio = min(relevant_years / required_years, 1.25)
    else:
        experience_ratio = min(years / 3, 1.15)

    progression_text = " ".join(
        f"{job.get('role', '')} {job.get('description', '')}"
        for job in parsed.get("experience", []) if isinstance(job, dict)
    )
    leadership_signal = bool(re.search(r"\b(lead|managed|mentor|stakeholder|architecture|owned)\b", progression_text, re.I))
    recent_signal = bool(re.search(r"\b(202[3-9]|present|current)\b", progression_text, re.I))
    range_years = relevant_years if transition_candidate else years
    over_target_years = max(0, range_years - max_years) if max_years else 0
    over_target_ratio = over_target_years / max(max_years, 1) if max_years else 0
    tenure_credit_years = min(years, 6) if not transition_candidate else min(years, 2) * 0.25
    experience_score = min(
        30,
        round((experience_ratio * 24) + (3 if leadership_signal else 0) + (2 if recent_signal else 0) + tenure_credit_years * 0.35, 2),
    )
    if max_years and over_target_years > 1:
        experience_score = max(10, round(experience_score - min(10, over_target_years * 0.7), 2))
    if years <= 0 and (matched or transferable):
        experience_score = max(experience_score, 6)

    semantic_score_raw = parsed.get("semantic_score")
    if semantic_score_raw is None:
        semantic_score_raw = cosine_similarity_cached(jd_text, resume_text)
    semantic_score = min(20, round(8 + float(semantic_score_raw or 0) * 14 + min(4, mandatory_coverage * 4), 2))

    seniority_years = relevant_years if transition_candidate else years
    candidate_level = infer_seniority(parsed.get("designation"), seniority_years, progression_text)
    jd_level = infer_seniority(jd_data.get("role"), required_years, "")
    seniority_gap = _seniority_score(jd_level) - _seniority_score(candidate_level)
    over_seniority_gap = max(0, _seniority_score(candidate_level) - _seniority_score(jd_level))
    seniority_score = max(0, 4 - max(seniority_gap, 0) * 2)
    overqualified_penalty = 0
    if max_years and over_target_years > 1:
        overqualified_penalty = min(18, (over_target_years - 1) * 1.6 + over_seniority_gap * 2.5)
    elif required_years and years > required_years + 3 and not transition_candidate:
        overqualified_penalty = min(10, (years - required_years - 3) * 1.2)

    quality_score_raw = float(parsed.get("resume_quality_score") or 70)
    quality_score = round((quality_score_raw / 100) * 2, 2)
    education_score = _education_cert_score(parsed, jd_data)

    spam_penalty = 0
    if len(candidate_skills) > 45 and len(matched) / max(len(candidate_skills), 1) < 0.25:
        spam_penalty = 8

    missing_core_penalty = 0
    if required_skills:
        if len(matched) == 0 and len(transferable) <= 1:
            missing_core_penalty = 22
        elif mandatory_coverage < 0.45:
            missing_core_penalty = 10

    evidence_penalty = 0
    if matched and not any(item.get("experience") or item.get("project") for item in evidence.values()):
        evidence_penalty = 6

    final_score = skill_score + experience_score + education_score + semantic_score + seniority_score + quality_score
    final_score -= spam_penalty + (missing_core_penalty * 0.45) + (evidence_penalty * 0.5) + overqualified_penalty
    final_score = max(0, min(100, round(final_score, 2)))

    evidence_confidence = min(18, sum(1 for item in evidence.values() if item["count"]) * 3)
    gap_penalty = max(0, len(missing) - 1) * 3
    confidence_score = max(
        0,
        min(
            100,
            round(
                35
                + quality_score_raw * 0.22
                + min(28, mandatory_coverage * 28)
                + evidence_confidence
                + (5 if preferred_matched or preferred_transferable else 0)
                - gap_penalty
                - (12 if parsed.get("malformed_resume") else 0),
                2,
            ),
        ),
    )

    rank_score = calculate_rank_score(
        final_score=final_score,
        mandatory_coverage=mandatory_coverage,
        preferred_coverage=preferred_coverage,
        evidence_points=evidence_points,
        confidence_score=confidence_score,
        seniority_gap=max(seniority_gap, 0),
        missing_core_penalty=missing_core_penalty * 0.45,
        overqualified_penalty=overqualified_penalty,
    )
    rank_score = round((rank_score * 0.35) + (final_score * 0.65), 2)

    recommendation = "in_review"
    if rank_score >= 72 and mandatory_coverage >= 0.7 and confidence_score >= 62 and not parsed.get("malformed_resume"):
        recommendation = "shortlisted"
    elif rank_score < 38 or missing_core_penalty >= 22:
        recommendation = "rejected"

    score_data = {
        "final_score": final_score,
        "rank_score": rank_score,
        "fit_band": fit_band(rank_score, mandatory_coverage, confidence_score),
        "skill_score": skill_score,
        "experience_score": experience_score,
        "semantic_score": float(semantic_score_raw or 0),
        "semantic_weight": semantic_score,
        "role_similarity": parsed.get("role_similarity", 0),
        "role_weight": seniority_score,
        "education_score": education_score,
        "seniority_penalty": max(seniority_gap, 0) * 3,
        "overqualified_penalty": overqualified_penalty,
        "experience_target_max_years": max_years or None,
        "experience_over_target_years": round(over_target_years, 2),
        "matched_skills": matched + transferable,
        "direct_matched_skills": matched,
        "transferable_skills": transferable,
        "preferred_matched_skills": preferred_matched + preferred_transferable,
        "missing_skills": missing,
        "skill_match_percent": round(mandatory_coverage * 100, 2),
        "mandatory_skill_coverage": round(mandatory_coverage * 100, 2),
        "preferred_skill_coverage": round(preferred_coverage * 100, 2),
        "resume_quality_score": quality_score_raw,
        "confidence_score": confidence_score,
        "seniority_level": candidate_level,
        "target_seniority_level": jd_level,
        "recommendation": recommendation,
        "ranking_reason": build_ranking_reason(
            rank_score,
            matched,
            transferable,
            preferred_matched + preferred_transferable,
            missing,
            candidate_level,
            confidence_score,
            evidence,
            overqualified_penalty,
            max_years,
        ),
        "scoring_breakdown": {
            "skill_score": skill_score,
            "experience_score": experience_score,
            "semantic_score": semantic_score,
            "seniority_score": seniority_score,
            "resume_quality_score": quality_score,
            "education_score": education_score,
            "overqualified_penalty": overqualified_penalty,
            "experience_target_max_years": max_years or None,
            "experience_over_target_years": round(over_target_years, 2),
            "spam_penalty": spam_penalty,
            "missing_core_penalty": missing_core_penalty,
            "evidence_penalty": evidence_penalty,
            "mandatory_skill_coverage": round(mandatory_coverage * 100, 2),
            "preferred_skill_coverage": round(preferred_coverage * 100, 2),
            "rank_score": rank_score,
        }
    }

    return calibrate_final_score(parsed, jd_text, jd_data, required_skills, resume_text, score_data)


def calculate_rank_score(
    final_score,
    mandatory_coverage,
    preferred_coverage,
    evidence_points,
    confidence_score,
    seniority_gap,
    missing_core_penalty,
    overqualified_penalty=0,
):
    rank_score = (
        final_score * 0.48
        + min(100, mandatory_coverage * 100) * 0.28
        + min(100, preferred_coverage * 100) * 0.06
        + min(100, evidence_points * 7) * 0.08
        + confidence_score * 0.10
    )
    rank_score -= seniority_gap * 2.5
    rank_score -= min(18, missing_core_penalty * 0.55)
    rank_score -= min(14, overqualified_penalty * 0.75)
    return max(0, min(100, round(rank_score, 2)))


def fit_band(rank_score, mandatory_coverage, confidence_score):
    if rank_score >= 82 and mandatory_coverage >= 0.8 and confidence_score >= 70:
        return "strong_match"
    if rank_score >= 68 and mandatory_coverage >= 0.6:
        return "good_match"
    if rank_score >= 48:
        return "review"
    return "low_match"


def build_ranking_reason(score, matched, transferable, preferred, missing, seniority, confidence, evidence, overqualified_penalty=0, max_years=None):
    strengths = []
    if matched:
        strengths.append(f"direct match on {', '.join(matched[:4])}")
    if transferable:
        strengths.append(f"transferable coverage for {', '.join(transferable[:3])}")
    if preferred:
        strengths.append(f"preferred-skill signal in {', '.join(preferred[:3])}")
    if seniority:
        strengths.append(f"{seniority} seniority signal")

    evidence_skills = [
        skill for skill, item in evidence.items()
        if item.get("experience") or item.get("project")
    ]
    if evidence_skills:
        strengths.append(f"resume evidence for {', '.join(evidence_skills[:3])}")

    gap = f"missing {', '.join(missing[:3])}" if missing else "no major required-skill gap"
    if overqualified_penalty and max_years:
        gap += f"; over target experience range for this JD (max {max_years:g} years)"
    return f"Rank score {score}/100 with {confidence}% confidence: {', '.join(strengths) or 'limited direct evidence'}; {gap}."
