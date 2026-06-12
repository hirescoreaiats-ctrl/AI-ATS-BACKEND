import re
from calendar import monthrange
from datetime import datetime

from backend.services.role_taxonomy import ROLE_FAMILIES
from backend.services.taxonomy import known_skills_in_text, normalize_skill_list
from backend.validation_scoring import parse_date


DIRECT_ANALYST_ROLE_RE = re.compile(
    r"\b(?:data|business|bi|mis|reporting|analytics?|power\s*bi)\s+"
    r"(?:analyst|apprentice|specialist|developer|consultant|associate)\b",
    re.I,
)

TRANSFERABLE_ROLE_RE = re.compile(
    r"\b(?:administrative|admin|customer\s+support|support\s+rep|accountant|"
    r"revenue|operations?|coordinator|assistant|manager|transcriber|sales)\b",
    re.I,
)

ANALYTICS_SIGNAL_RE = re.compile(
    r"\b(?:report(?:ing|s)?|spreadsheet|dashboard|kpi|metrics?|analysis|analy[sz]ed|"
    r"data\s+accuracy|data\s+validation|automate[sd]?|visuali[sz]ation|"
    r"sql|power\s*bi|tableau|excel|python|forecast(?:ing|ed)?|retention|"
    r"year[-\s]?over[-\s]?year|leadership|decision\s+makers?)\b",
    re.I,
)


def _safe_years(job):
    start = _parse_relevance_date((job or {}).get("start_date"))
    end = _parse_relevance_date((job or {}).get("end_date"), is_end=True)
    if not start:
        return 0.0
    if not end:
        from datetime import datetime

        end = datetime.now()
    if end < start:
        return 0.0
    return max(0.0, (end - start).days / 365)


def _parse_relevance_date(value, is_end=False):
    text = str(value or "").strip().replace("’", "'").replace("‘", "'")
    season = re.fullmatch(r"(summer|winter|spring|autumn|fall)\s*'?\s*(\d{2,4})", text, re.I)
    if season:
        year_text = season.group(2)
        year = int(year_text if len(year_text) == 4 else f"20{year_text}")
        start_month, end_month = {
            "winter": (1, 2),
            "spring": (3, 5),
            "summer": (6, 8),
            "autumn": (9, 11),
            "fall": (9, 11),
        }[season.group(1).lower()]
        month = end_month if is_end else start_month
        return datetime(year, month, monthrange(year, month)[1] if is_end else 1)
    return parse_date(text)


def _is_data_analyst_jd(jd_skills=None, jd_data=None, jd_text=""):
    text = " ".join([
        str((jd_data or {}).get("role") or ""),
        str((jd_data or {}).get("job_title") or ""),
        " ".join(str(item) for item in jd_skills or []),
        str(jd_text or ""),
    ]).lower()
    return bool(
        re.search(r"\b(data|mis|business|bi)\s+analyst\b", text)
        or ("power bi" in text and "sql" in text)
        or ("mis reporting" in text and "excel" in text)
    )


def _is_salesforce_jd(jd_skills=None, jd_data=None, jd_text=""):
    text = " ".join([
        str((jd_data or {}).get("role") or ""),
        str((jd_data or {}).get("job_title") or ""),
        " ".join(str(item) for item in jd_skills or []),
        str(jd_text or ""),
    ]).lower()
    return "salesforce" in text or re.search(r"\b(apex|lwc|visualforce|soql|sosl|sales cloud|service cloud|cpq)\b", text)


SALESFORCE_ROLE_RE = re.compile(
    r"\b(?:senior\s+|lead\s+|principal\s+|jr\.?\s+|junior\s+)?"
    r"(?:salesforce|crm|sfdc)\s+"
    r"(?:developer|engineer|administrator|admin|consultant|architect|specialist)\b",
    re.I,
)

SALESFORCE_DEV_SIGNAL_RE = re.compile(
    r"\b(?:salesforce|sfdc|apex|trigger|triggers|lwc|lightning\s+web\s+components?|aura|"
    r"visualforce|soql|sosl|flows?|flow\s+builder|sales\s+cloud|service\s+cloud|cpq|"
    r"experience\s+cloud|salesforce\s+org|data\s+loader|sfdx|permission\s+sets?|profiles?)\b",
    re.I,
)

SALESFORCE_DEV_SPECIFIC_RE = re.compile(
    r"\b(?:apex|trigger|triggers|lwc|lightning\s+web\s+components?|aura|visualforce|soql|sosl|"
    r"flows?|flow\s+builder|sales\s+cloud|service\s+cloud|cpq|experience\s+cloud|"
    r"salesforce\s+org|custom\s+objects?|validation\s+rules?|data\s+loader|sfdx|"
    r"permission\s+sets?|profiles?)\b",
    re.I,
)

SENIOR_ROLE_RE = re.compile(r"\b(senior|sr\.?|lead|principal|architect|manager|tech\s+lead)\b", re.I)
INTERNSHIP_RE = re.compile(r"\b(intern|internship|trainee|training|certification|trailhead)\b", re.I)
DIRECT_ROLE_PATTERNS = {
    "qa_automation": re.compile(
        r"\b(?:qa\s*/\s*automation|qa\s+automation(?:\s+engineer)?|automation\s+(?:test|testing|qa)\s+engineer|"
        r"test\s+automation\s+engineer|sdet|software\s+development\s+engineer\s+in\s+test|"
        r"senior\s+quality\s+engineer|quality\s+engineer|sqa\s+engineer|"
        r"software\s+testing\s+engineer|digital\s+quality\s+assurance|qa\s+engineer)\b",
        re.I,
    ),
    "manual_qa": re.compile(
        r"\b(?:manual\s+qa|manual\s+tester|qa\s+engineer|test\s+engineer|"
        r"quality\s+assurance\s+analyst|software\s+testing\s+engineer)\b",
        re.I,
    ),
    "software_backend": re.compile(
        r"\b(?:backend|back[-\s]?end|api|python|java|node\.?js|software)\s+"
        r"(?:developer|engineer)\b",
        re.I,
    ),
    "full_stack": re.compile(r"\b(?:full[-\s]?stack|mern|mean)\s+(?:developer|engineer)\b", re.I),
    "data_analytics": DIRECT_ANALYST_ROLE_RE,
    "salesforce_crm": SALESFORCE_ROLE_RE,
}

FULL_STACK_ROLE_RE = re.compile(
    r"\b(full[-\s]?stack|mern|mean|web\s+developer|software\s+engineer|software\s+developer|"
    r"frontend|front[-\s]?end|backend|back[-\s]?end)\b",
    re.I,
)

BUSINESS_ANALYST_DIRECT_ROLE_RE = re.compile(
    r"\b(?:junior\s+|associate\s+|assistant\s+|senior\s+|sr\.?\s+)?"
    r"(?:business\s+analyst|functional\s+analyst|it\s+business\s+analyst|"
    r"business\s+systems\s+analyst|requirements?\s+analyst)\b",
    re.I,
)

BUSINESS_ANALYST_ADJACENT_ROLE_RE = re.compile(
    r"\b(?:data|bi|mis|reporting|product|project|operations?|customer\s+support)\s+"
    r"(?:analyst|associate|specialist|coordinator|manager|intern)\b",
    re.I,
)

BUSINESS_ANALYST_EVIDENCE_RE = re.compile(
    r"\b(?:business\s+requirements?|requirements?\s+(?:gathering|analysis|documentation)|"
    r"gather(?:ed|ing)?\s+requirements?|document(?:ed|ing)?\s+requirements?|"
    r"brd|frd|srs|user\s+stor(?:y|ies)|use\s+cases?|acceptance\s+criteria|"
    r"functional\s+specifications?|stakeholder(?:s)?|uat|user\s+acceptance\s+testing|"
    r"change\s+requests?|gap\s+analysis|process\s+flows?|workflow\s+diagrams?|"
    r"business\s+process\s+mapping|requirement\s+traceability\s+matrix|rtm|"
    r"backlog\s+grooming|sprint\s+planning|defect\s+clarification|wireframes?)\b",
    re.I,
)

ANALYTICS_ONLY_RE = re.compile(
    r"\b(?:dashboard|dashboards|reporting|reports?|kpi|metrics?|power\s*bi|tableau|"
    r"excel|sql|data\s+cleaning|data\s+visuali[sz]ation|etl|mis)\b",
    re.I,
)

DIRECT_ROLE_PATTERNS.update({
    "business_analyst": BUSINESS_ANALYST_DIRECT_ROLE_RE,
    "business_analysis": BUSINESS_ANALYST_DIRECT_ROLE_RE,
})

FULL_STACK_SIGNAL_RE = re.compile(
    r"\b(react|next(?:\.js)?|vue(?:\.js)?|angular|node(?:\.js)?|express(?:\.js)?|django|fastapi|"
    r"laravel|spring\s+boot|java|rest\s+api|api|apis|graphql|authentication|authorization|"
    r"frontend|front[-\s]?end|backend|back[-\s]?end|database|mongodb|mysql|postgres(?:ql)?|sql|"
    r"html|css|tailwind|bootstrap|docker|aws|azure|vercel|netlify|digital\s*ocean|git)\b",
    re.I,
)


def estimate_salesforce_experience_years(parsed, resume_text=""):
    sf_years = 0.0
    senior_years = 0.0
    role_relevance = 0
    has_direct = False

    for job in (parsed or {}).get("experience") or []:
        if not isinstance(job, dict):
            continue
        years = _safe_years(job)
        if years <= 0:
            continue
        role = str(job.get("role") or "")
        description = str(job.get("description") or "")
        combined = f"{role} {description}"
        direct_role = bool(SALESFORCE_ROLE_RE.search(role))
        signal_count = len({m.group(0).lower() for m in SALESFORCE_DEV_SIGNAL_RE.finditer(combined)})
        dev_signal_count = len({m.group(0).lower() for m in SALESFORCE_DEV_SPECIFIC_RE.finditer(combined)})
        internship = bool(INTERNSHIP_RE.search(role))

        if direct_role or dev_signal_count >= 2:
            has_direct = has_direct or direct_role
            credit = years
            if internship:
                credit = min(credit, 0.35)
            sf_years += credit
            if SENIOR_ROLE_RE.search(role) or re.search(r"\b(owned|led|architected|mentored|designed)\b", description, re.I):
                senior_years += credit
            role_relevance = max(role_relevance, 90 if direct_role and not internship else 55)
        elif signal_count:
            role_relevance = max(role_relevance, 35)

    parsed["salesforce_experience_years"] = round(sf_years, 2)
    parsed["senior_role_experience_years"] = round(senior_years, 2)
    parsed["role_relevance_score"] = role_relevance
    parsed["experience_relevance_label"] = "direct_salesforce" if has_direct else ("salesforce_tooling" if role_relevance else "unproven")
    return round(sf_years, 2)


def _work_section_text(resume_text):
    text = str(resume_text or "")
    start_match = re.search(
        r"w\s*o\s*r\s*k\s+e\s*x\s*p\s*e\s*r\s*i\s*e\s*n\s*c\s*e|\bwork\s+experience\b",
        text,
        re.I,
    )
    if not start_match:
        start_match = re.search(r"\bexperience\b", text, re.I)
    if not start_match:
        return text
    section = text[start_match.start():]
    end_match = re.search(r"\btechnologies\b|\beducation\b|\bprojects?\b", section[250:], re.I)
    if end_match:
        section = section[:250 + end_match.start()]
    return section


def estimate_relevant_experience_years(parsed, resume_text, jd_skills=None, jd_data=None, jd_text=""):
    if _is_salesforce_jd(jd_skills, jd_data, jd_text):
        return estimate_salesforce_experience_years(parsed, resume_text)

    if not _is_data_analyst_jd(jd_skills, jd_data, jd_text):
        return None

    direct_years = 0.0
    transferable_years = 0.0
    has_direct_role = False
    has_transferable_reporting = False
    work_section = _work_section_text(resume_text)
    total_years = 0.0
    try:
        total_years = float((parsed or {}).get("total_experience_years") or 0)
    except (TypeError, ValueError):
        total_years = 0.0

    for job in (parsed or {}).get("experience") or []:
        if not isinstance(job, dict):
            continue

        years = _safe_years(job)
        if years <= 0:
            continue

        role = str(job.get("role") or "")
        description = str(job.get("description") or "")
        text = f"{role} {description}"

        if DIRECT_ANALYST_ROLE_RE.search(role):
            direct_years += years
            has_direct_role = True
            continue

        signals = ANALYTICS_SIGNAL_RE.findall(text)
        if TRANSFERABLE_ROLE_RE.search(role) and len(signals) < 2:
            signals = ANALYTICS_SIGNAL_RE.findall(work_section)
        if len(set(item.lower() for item in signals)) >= 3 or (
            TRANSFERABLE_ROLE_RE.search(role) and len(signals) >= 2
        ):
            has_transferable_reporting = True
            transferable_years += min(years * 0.2, 1.0)

    apprentice_match = re.search(
        r"\bdata\s+analyst\s+apprentice\s*\|\s*nashville\s+software\s+school[\s.]*"
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)[a-z]*\s*"
        r"(?:-|\u2013|\u2014|to)\s*"
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)[a-z]*\s+"
        r"\d{4}\b",
        resume_text or "",
        re.I,
    )
    if apprentice_match and direct_years < 0.25:
        direct_years += 0.25
        has_direct_role = True

    relevant_years = direct_years
    if direct_years > 0:
        relevant_years += min(transferable_years, 0.5)
    elif has_transferable_reporting:
        relevant_years = min(max(transferable_years, 0.5), 1.0)

    parsed["direct_relevant_experience_years"] = round(direct_years, 2)
    parsed["transferable_reporting_experience_years"] = round(transferable_years, 2)
    parsed["transition_candidate"] = bool((has_transferable_reporting or total_years > 3) and direct_years < 1)
    parsed["experience_relevance_label"] = (
        "direct_data_analyst"
        if has_direct_role
        else "transferable_reporting"
        if has_transferable_reporting
        else "unproven"
    )

    return round(relevant_years, 2)


def _score_ratio(value, maximum):
    if maximum <= 0:
        return 0
    return max(0, min(100, round((value / maximum) * 100, 2)))


def _years_from_job(job):
    years = 0.0
    for key in ("duration_years", "years", "experience_years"):
        try:
            years = max(years, float((job or {}).get(key) or 0))
        except (TypeError, ValueError):
            pass
    return max(years, _safe_years(job))


def _contains_any(text, values):
    haystack = (text or "").lower()
    return [value for value in values or [] if value and re.search(r"\b" + re.escape(str(value).lower()).replace(r"\ ", r"\s+") + r"\b", haystack, re.I)]


def _family_role_terms(role_family):
    config = ROLE_FAMILIES.get(role_family) or {}
    terms = []
    for pattern in config.get("patterns") or []:
        cleaned = re.sub(r"\\b|\\s\+|\(\?:|\)|\[|\]|\?|\.|\+|\*", " ", pattern)
        cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", cleaned)
        terms.extend(part for part in cleaned.split() if len(part) > 2)
    return sorted(set(terms))


def _recency_score(job):
    end = _parse_relevance_date((job or {}).get("end_date"), is_end=True)
    if not end:
        end_text = str((job or {}).get("end_date") or "")
        if re.search(r"\b(present|current|now)\b", end_text, re.I):
            return 100
        return 45
    age_years = max(0, (datetime.now() - end).days / 365)
    if age_years <= 2:
        return 100
    if age_years <= 5:
        return 75
    if age_years <= 8:
        return 45
    return 25


def _seniority_block_score(job, target_seniority):
    target = (target_seniority or "unknown").lower()
    text = " ".join([
        str((job or {}).get("role") or ""),
        str((job or {}).get("description") or ""),
    ])
    senior_signal = bool(SENIOR_ROLE_RE.search(text))
    lead_signal = bool(re.search(r"\b(lead|managed|mentored|architected|owned|strategy|stakeholder)\b", text, re.I))
    if target in {"unknown", "junior", "intern"}:
        return 70
    if target in {"senior", "lead", "manager", "architect"}:
        return 100 if senior_signal or lead_signal else 45
    return 80 if not re.search(r"\b(intern|trainee|training)\b", text, re.I) else 35


def estimate_relevant_experience_v2(parsed, resume_text, jd_profile):
    parsed = parsed or {}
    jd_profile = jd_profile or {}
    role_family = jd_profile.get("role_family") or "other"
    role_title = jd_profile.get("role_title") or ""
    target_seniority = jd_profile.get("seniority_level") or "unknown"
    must_have = normalize_skill_list(jd_profile.get("must_have_skills") or [])
    family_skills = normalize_skill_list((ROLE_FAMILIES.get(role_family) or {}).get("skills") or [])
    required_signals = [str(item).lower() for item in jd_profile.get("responsibility_signals") or []]
    domain_context = str(jd_profile.get("domain_context") or role_family or "").replace("_", " ")
    target_accepts_junior = target_seniority in {"intern", "junior", "unknown"}

    parsed_total_years = 0.0
    try:
        parsed_total_years = float(parsed.get("total_experience_years") or 0)
    except (TypeError, ValueError):
        parsed_total_years = 0.0
    summed_total_years = 0.0
    direct_years = 0.0
    transferable_years = 0.0
    senior_years = 0.0
    evidence = []
    warnings = []
    block_scores = []

    role_terms = set(_family_role_terms(role_family))
    role_terms.update(part.lower() for part in re.split(r"\W+", role_title or "") if len(part) > 2)
    family_signal_skills = normalize_skill_list(must_have + family_skills)

    for job in parsed.get("experience") or []:
        if not isinstance(job, dict):
            continue

        years = _years_from_job(job)
        if years <= 0:
            continue
        summed_total_years += years

        role = str(job.get("role") or "")
        company = str(job.get("company_name") or job.get("company") or "")
        description = str(job.get("description") or "")
        block_text = " ".join([role, company, description])
        block_lower = block_text.lower()

        if re.search(r"\b(education|certification|bootcamp|course|coursework|training program)\b", company, re.I):
            warnings.append(f"Skipped education/certification block as work experience: {company or role}")
            continue

        internship = bool(INTERNSHIP_RE.search(block_text))
        role_hits = [term for term in role_terms if term and re.search(r"\b" + re.escape(term) + r"\b", role.lower())]
        role_title_score = _score_ratio(len(role_hits), min(max(len(role_terms), 1), 4))
        direct_role_match = bool((DIRECT_ROLE_PATTERNS.get(role_family) or re.compile(r"a^")).search(role))
        if direct_role_match:
            role_title_score = 100
        if role_family == "data_analytics" and DIRECT_ANALYST_ROLE_RE.search(role):
            role_title_score = 100
        elif role_family == "salesforce_crm" and SALESFORCE_ROLE_RE.search(role):
            role_title_score = 100
        elif role_family == "full_stack":
            full_stack_signals = {match.group(0).lower() for match in FULL_STACK_SIGNAL_RE.finditer(block_text)}
            direct_full_stack_role = bool(FULL_STACK_ROLE_RE.search(role))
            if re.search(r"\b(full[-\s]?stack|mern|mean)\b", role, re.I):
                role_title_score = 100
            elif direct_full_stack_role and len(full_stack_signals) >= 2:
                role_title_score = max(role_title_score, 90)
            elif direct_full_stack_role:
                role_title_score = max(role_title_score, 72)

        ba_evidence_hits = set()
        ba_direct_role = False
        ba_adjacent_role = False
        ba_analytics_only = False
        if role_family in {"business_analyst", "business_analysis"}:
            ba_evidence_hits = {match.group(0).lower() for match in BUSINESS_ANALYST_EVIDENCE_RE.finditer(block_text)}
            ba_direct_role = bool(BUSINESS_ANALYST_DIRECT_ROLE_RE.search(role))
            ba_adjacent_role = bool(BUSINESS_ANALYST_ADJACENT_ROLE_RE.search(role))
            ba_analytics_only = bool(ANALYTICS_ONLY_RE.search(block_text)) and not ba_evidence_hits
            if ba_direct_role:
                role_title_score = 100
            elif ba_adjacent_role and ba_evidence_hits:
                role_title_score = max(role_title_score, 74)
            elif ba_adjacent_role:
                role_title_score = max(role_title_score, 34)

        block_skills = normalize_skill_list(known_skills_in_text(block_text))
        skill_hits = []
        for required in family_signal_skills:
            if any(required.lower() == skill.lower() for skill in block_skills) or _contains_any(block_text, [required]):
                skill_hits.append(required)
        skill_evidence_score = _score_ratio(len(set(skill_hits)), min(max(len(must_have), 1), 5))

        responsibility_hits = [signal for signal in required_signals if signal and re.search(r"\b" + re.escape(signal) + r"\w*\b", block_lower)]
        responsibility_match_score = _score_ratio(len(set(responsibility_hits)), min(max(len(required_signals), 1), 5))
        if ba_evidence_hits:
            responsibility_match_score = max(responsibility_match_score, min(100, len(ba_evidence_hits) * 24))

        domain_hits = 0
        if domain_context and domain_context.lower() in block_lower:
            domain_hits += 1
        if role_family != "other" and any(term in block_lower for term in role_family.split("_")):
            domain_hits += 1
        if skill_hits:
            domain_hits += 1
        if role_family == "full_stack" and len({match.group(0).lower() for match in FULL_STACK_SIGNAL_RE.finditer(block_text)}) >= 3:
            domain_hits += 2
        domain_match_score = min(100, domain_hits * 35)
        if role_family in {"business_analyst", "business_analysis"}:
            if ba_evidence_hits:
                domain_match_score = max(domain_match_score, min(100, 35 + len(ba_evidence_hits) * 15))
            elif ba_analytics_only:
                skill_evidence_score = min(skill_evidence_score, 38)
                domain_match_score = min(domain_match_score, 30)

        seniority_signal_score = _seniority_block_score(job, target_seniority)
        recency_score = _recency_score(job)

        final_block_score = round(
            role_title_score * 0.25
            + skill_evidence_score * 0.30
            + responsibility_match_score * 0.18
            + domain_match_score * 0.12
            + seniority_signal_score * 0.08
            + recency_score * 0.07,
            2,
        )
        if role_title_score >= 75 and domain_match_score >= 35:
            final_block_score = max(final_block_score, 78)
        if direct_role_match and (skill_evidence_score >= 25 or responsibility_match_score >= 20):
            final_block_score = max(final_block_score, 82)
        if role_family in {"business_analyst", "business_analysis"}:
            if ba_direct_role and len(ba_evidence_hits) >= 2:
                final_block_score = max(final_block_score, 86)
            elif ba_direct_role:
                final_block_score = max(final_block_score, 70)
            elif ba_adjacent_role and len(ba_evidence_hits) >= 2:
                final_block_score = max(final_block_score, 72)
            elif len(ba_evidence_hits) >= 2:
                final_block_score = max(final_block_score, 64)
            elif ba_analytics_only:
                final_block_score = min(final_block_score, 42)

        if final_block_score >= 75:
            weight = 1.0
            direct_years += years
            label = "direct"
        elif final_block_score >= 55:
            weight = 0.6
            direct_years += years * weight
            label = "partial"
        elif final_block_score >= 35:
            weight = 0.25
            transferable_years += years * weight
            label = "transferable"
        elif skill_evidence_score >= 70 and responsibility_match_score >= 40:
            weight = 0.25
            transferable_years += years * weight
            label = "strong_transferable"
        else:
            weight = 0.0
            label = "unproven"

        credited_years = years * weight
        if internship and not target_accepts_junior:
            capped = min(credited_years, 0.35)
            if capped < credited_years:
                warnings.append(f"Capped internship/trainee relevance for {company or role} at 0.35 years.")
            credited_years = capped
            if label in {"direct", "partial"}:
                direct_years = max(0.0, direct_years - (years * weight) + credited_years)
            elif label in {"transferable", "strong_transferable"}:
                transferable_years = max(0.0, transferable_years - (years * weight) + credited_years)

        if SENIOR_ROLE_RE.search(role) and final_block_score >= 55:
            senior_years += credited_years

        block_scores.append(final_block_score)
        evidence.append({
            "company_name": company,
            "role": role,
            "years": round(years, 2),
            "credited_years": round(credited_years, 2),
            "label": label,
            "role_title_match_score": role_title_score,
            "skill_evidence_score": skill_evidence_score,
            "responsibility_match_score": responsibility_match_score,
            "domain_match_score": domain_match_score,
            "seniority_signal_score": seniority_signal_score,
            "recency_score": recency_score,
            "final_block_relevance_score": final_block_score,
            "relevance_weight": weight,
            "matched_skills": sorted(set(skill_hits))[:10],
            "matched_responsibilities": sorted(set(responsibility_hits))[:8],
        })

    parsed_total = 0.0
    try:
        parsed_total = float(parsed.get("total_experience_years") or 0)
    except (TypeError, ValueError):
        parsed_total = 0.0
    total_years = round(parsed_total if parsed_total > 0 else summed_total_years, 2)
    relevant_years = round(min(total_years, direct_years + transferable_years), 2)
    role_relevance_score = round(max(block_scores or [0]), 2)

    if not evidence and re.search(r"\b\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b", resume_text or "", re.I):
        warnings.append("Explicit years claim found, but work-history evidence did not prove role relevance.")

    if relevant_years <= 0:
        label = "unproven" if evidence else "needs_validation"
    elif direct_years >= max(1.0, relevant_years * 0.75):
        label = "direct_match"
    elif direct_years > 0:
        label = "partial_match"
    else:
        label = "transferable"

    return {
        "total_experience_years": total_years,
        "relevant_experience_years": relevant_years,
        "direct_relevant_experience_years": round(min(total_years, direct_years), 2),
        "transferable_experience_years": round(min(total_years, transferable_years), 2),
        "senior_role_experience_years": round(min(total_years, senior_years), 2),
        "role_relevance_score": role_relevance_score,
        "experience_relevance_label": label,
        "experience_evidence": evidence,
        "experience_warnings": warnings,
    }
