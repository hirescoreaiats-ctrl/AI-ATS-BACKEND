import re

from backend.services.semantic_service import cosine_similarity_cached
from backend.services.role_taxonomy import match_core_skill_groups
from backend.services.taxonomy import equivalent_skill, expand_skill_requirements, normalize_skill_list


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
    "deployment_tools": 0.05,
}


def _full_stack_group_score(group, options, parsed, resume_text, candidate_skills):
    evidences = []
    for skill in normalize_skill_list(options or []):
        direct, equiv = _skill_match(skill, candidate_skills)
        evidence = _classify_skill_evidence(skill, parsed, resume_text, candidate_skills, equivalent=equiv)
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
    bonus = min(0.18, max(0, len(evidences) - 1) * 0.06)
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
    frontend = bool(re.search(r"\b(react|next(?:\.js)?|vue(?:\.js)?|angular|html|css|tailwind|bootstrap)\b", text, re.I))
    backend = bool(re.search(r"\b(node(?:\.js)?|express(?:\.js)?|django|fastapi|laravel|spring\s+boot|php|backend|api)\b", text, re.I))
    database = bool(re.search(r"\b(mongodb|mongo\s*db|mysql|postgres(?:ql)?|sql|database)\b", text, re.I))
    deployment = bool(re.search(r"\b(deploy(?:ed|ment)?|vercel|netlify|digital\s*ocean|aws|docker|ci\s*/\s*cd|linux)\b", text, re.I))
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


def _score_candidate_full_stack(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    candidate_skills = normalize_skill_list(parsed.get("key_skills", []))
    core_groups = jd_profile.get("core_skill_groups") or {}
    if not core_groups:
        core_groups = {
            "frontend": ["React", "Next.js", "Vue", "Angular"],
            "frontend_foundation": ["HTML", "CSS", "JavaScript", "TypeScript"],
            "backend": ["Node.js", "Express", "Django", "FastAPI", "PHP", "Laravel", "Spring Boot"],
            "database": ["MongoDB", "MySQL", "PostgreSQL", "SQL"],
            "api_auth": ["REST API", "GraphQL", "JWT", "OAuth"],
            "deployment_tools": ["Git", "GitHub", "Docker", "AWS", "DigitalOcean", "Vercel", "Netlify", "CI/CD"],
        }

    group_results = {
        group: _full_stack_group_score(group, options, parsed, resume_text, candidate_skills)
        for group, options in core_groups.items()
        if group in FULL_STACK_GROUP_WEIGHTS
    }
    if "frontend_foundation" in group_results and "frontend" in group_results:
        # Foundation skills help, but framework evidence carries the real frontend gate.
        group_results["frontend"]["score"] = max(
            group_results["frontend"]["score"],
            min(0.72, group_results["frontend_foundation"]["score"] * 0.75),
        )

    weighted_core = 0.0
    total_weight = 0.0
    for group, weight in FULL_STACK_GROUP_WEIGHTS.items():
        if group not in group_results:
            continue
        weighted_core += group_results[group]["score"] * weight
        total_weight += weight
    core_skill_percent = round((weighted_core / max(total_weight, 0.01)) * 100, 2)
    missing_core_groups = [
        group for group, result in group_results.items()
        if group != "frontend_foundation" and result["score"] < 0.35
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
    if experience_fit["overqualified"]:
        _append_unique(recruiter_flags, ["overqualified", "senior_overqualified"])
    if project_work_strength >= 60:
        _append_unique(recruiter_flags, ["strong_professional_evidence"])

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
    if experience_fit["label"] == "senior_overqualified":
        caps.append({"cap": 78, "reason": "Senior/overqualified for this 1-3 year role; recruiter review recommended."})
    if parsed.get("parser_quality_action") == "manual_review_required":
        caps.append({"cap": 58, "reason": "Parser quality requires manual review."})
        _append_unique(risk_flags, ["parser_quality"])
        _append_unique(recruiter_flags, ["parser_manual_review"])
    for cap in caps:
        final_score = min(final_score, cap["cap"])

    final_score = round(max(0, min(100, final_score)), 2)
    confidence = round(min(100, 35 + core_skill_percent * 0.25 + project_work_strength * 0.22 + role_relevance * 0.18 + _safe_float(parsed.get("resume_quality_score"), 75) * 0.12), 2)
    rank_score = round(min(100, final_score + (3 if confidence >= 65 and not risk_flags else 0)), 2)

    if final_score >= 78 and core_skill_percent >= 68 and not experience_fit["overqualified"] and len(missing_core_groups) <= 1:
        recommendation = "shortlisted"
        _append_unique(recruiter_flags, ["strong_match" if final_score >= 88 else "good_match"])
    elif final_score < 45 or len(missing_core_groups) >= 3:
        recommendation = "rejected"
    else:
        recommendation = "in_review"

    if experience_fit["overqualified"] and recommendation == "shortlisted":
        recommendation = "in_review"

    missing_skills = []
    for group in missing_core_groups:
        missing_skills.append(group.replace("_", " ").title())

    label = "Strong fit" if recommendation == "shortlisted" and final_score >= 84 else "Good match" if recommendation == "shortlisted" else "Senior / overqualified" if experience_fit["overqualified"] else "Junior but promising" if experience_fit["under_experienced"] and final_score >= 55 else "Weak match" if recommendation == "rejected" else "Review required"
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
        "jd_role_family": "full_stack",
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
    if "employer_name_only_match" in flags:
        return "Low match"
    if "missing_core_skill_groups" in flags or "missing_mandatory_skills" in flags:
        return "Rejected - missing core skills" if recommendation == "rejected" else "Skill validation needed"
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


def _score_candidate_role_agnostic(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile):
    if (jd_profile.get("role_family") or "").lower() == "full_stack":
        return _score_candidate_full_stack(parsed, jd_text, jd_skills, jd_data, resume_text, jd_profile)

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

    def cap_at(limit, reason, flag=None, risk=None):
        nonlocal final_score
        if final_score > limit:
            final_score = limit
        caps.append({"cap": limit, "reason": reason})
        if flag:
            _append_unique(recruiter_flags, [flag])
        if risk:
            _append_unique(risk_flags, [risk])

    if parser_action == "manual_review_required":
        cap_at(58, "Parser quality requires manual review.", "parser_manual_review", "parser_quality")
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
    if total_years >= 5 and relevant_years < 1 and (parsed.get("experience_relevance_label") in {"unproven", "needs_validation"}):
        cap_at(70, "High total experience claim needs validation because role-relevant work evidence is weak.", "experience_needs_validation", "experience_needs_validation")

    if missing:
        _append_unique(risk_flags, ["missing_mandatory_skills"])
    if employer_name_only_skills:
        _append_unique(risk_flags, ["employer_name_only_match"])
        _append_unique(recruiter_flags, ["employer_name_only_match"])
    if missing_core_groups:
        _append_unique(risk_flags, ["missing_core_skill_groups"])
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

    return {
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
            "target_role_alignment": parsed.get("target_role_alignment") or "weak",
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
