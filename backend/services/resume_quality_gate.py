import re


SECTION_NOISE_PATTERN = re.compile(
    r"\b("
    r"about me|contact|email|phone|linkedin|github|portfolio|resume|"
    r"education|experience|work experience|professional experience|employment history|"
    r"technical skills|technical tools|projects?|certifications?|"
    r"other professional experience|microsoft word|powerpoint|outlook|"
    r"grade|feelings|childhood|outcomes|objective|career objective|preferred full name|"
    r"job title|company name|department|hiring manager|application form|position applied"
    r")\b",
    re.I,
)

WORK_CONTEXT_PATTERN = re.compile(
    r"\b("
    r"work experience|employment|professional experience|analyst|engineer|developer|"
    r"consultant|associate|executive|manager|intern|coordinator|company|"
    r"limited|ltd|pvt|private|inc|llc|services|consulting|analytics|technologies"
    r")\b",
    re.I,
)


def _flag(flags, code, severity, message, penalty):
    flags.append({
        "code": code,
        "severity": severity,
        "message": message,
        "penalty": penalty,
    })


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _looks_like_sentence_or_section(value):
    text = _clean_text(value)
    if not text:
        return False
    if len(text) > 90 or len(text.split()) > 10:
        return True
    if SECTION_NOISE_PATTERN.search(text):
        return True
    if re.search(r"(@|https?://|www\.|\+?\d[\d\s().-]{8,}\d)", text, re.I):
        return True
    return False


def _valid_work_record(job):
    if not isinstance(job, dict):
        return False
    company = _clean_text(job.get("company_name"))
    role = _clean_text(job.get("role"))
    description = _clean_text(job.get("description"))
    if _looks_like_sentence_or_section(company):
        return False
    return bool(company or role) and bool(WORK_CONTEXT_PATTERN.search(f"{company} {role} {description}"))


def explicit_experience_years(text):
    values = []
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", text or "", re.I):
        number = float(match.group(1))
        context = (text or "")[max(0, match.start() - 100): match.end() + 140].lower()
        if any(term in context for term in ["experience", "analyst", "engineer", "developer", "reporting", "dashboard", "sql", "power bi"]):
            values.append(number)
    return max(values) if values else 0


def build_parser_quality_report(text, parsed, exp_data=None, jd_data=None):
    parsed = parsed or {}
    exp_data = exp_data or {}
    flags = []
    score = float(parsed.get("resume_quality_score") or 75)

    name = _clean_text(parsed.get("full_name"))
    email = _clean_text(parsed.get("email"))
    if not name:
        _flag(flags, "missing_name", "warning", "Candidate name was not confidently extracted.", 8)
    elif _looks_like_sentence_or_section(name) or len(name.split()) > 5:
        _flag(flags, "suspicious_name", "critical", "Extracted candidate name looks like resume content instead of a person name.", 25)

    if not email:
        _flag(flags, "missing_email", "warning", "Candidate email is missing or invalid.", 6)

    parser_flags = set(parsed.get("parser_flags") or [])
    if "ai_parse_recovered" in parser_flags:
        _flag(flags, "parser_recovered_ai_pollution", "warning", "Initial AI parse had polluted fields and was repaired from resume sections.", 5)

    education = [item for item in parsed.get("education") or [] if isinstance(item, dict)]
    text_has_education_signal = bool(re.search(
        r"\b(education|educational qualification|degree|university|college|school|bootcamp|bachelor|master|b\.?s\.?|bca|mba)\b",
        text or "",
        re.I,
    ))
    if "education_needs_review" in parser_flags or (text_has_education_signal and not education):
        _flag(flags, "missing_education", "warning", "Education was not confidently extracted from available resume evidence.", 8)

    experience = [item for item in parsed.get("experience") or [] if isinstance(item, dict)]
    valid_work = [item for item in experience if _valid_work_record(item)]
    total_years = float(parsed.get("total_experience_years") or exp_data.get("total_experience_years") or 0)
    last_company = _clean_text(exp_data.get("last_company_name") or (valid_work[0].get("company_name") if valid_work else ""))

    if last_company and _looks_like_sentence_or_section(last_company):
        _flag(flags, "suspicious_last_company", "critical", "Last company looks polluted by resume section text.", 25)

    noisy_companies = [
        _clean_text(item.get("company_name"))
        for item in experience
        if item.get("company_name") and _looks_like_sentence_or_section(item.get("company_name"))
    ]
    if noisy_companies:
        _flag(flags, "noisy_experience_company", "critical", "One or more company names look like parsed resume paragraphs.", 25)

    jd_profile_json = parsed.get("jd_profile_json") if isinstance(parsed.get("jd_profile_json"), dict) else {}
    role_family = _clean_text(parsed.get("role_family") or jd_profile_json.get("role_family")).lower()
    if role_family == "full_stack":
        full_stack_skill_hits = len([
            skill for skill in parsed.get("key_skills") or []
            if re.search(
                r"\b(react|next|vue|angular|node|express|django|fastapi|laravel|mongodb|mysql|postgres|sql|"
                r"rest|api|jwt|auth|git|docker|aws|vercel|netlify|nginx|linux)\b",
                str(skill),
                re.I,
            )
        ])
        has_work_or_project = bool(parsed.get("experience") or parsed.get("projects"))
        if full_stack_skill_hits >= 6 and has_work_or_project:
            for item in flags:
                if item.get("code") == "noisy_experience_company":
                    item["severity"] = "warning"
                    item["penalty"] = min(float(item.get("penalty") or 0), 10)
                    item["message"] = "One or more company names need recruiter validation."

    sections = parsed.get("sections") or {}
    has_work_section = bool(sections.get("experience"))
    explicit_years = explicit_experience_years(text)
    if total_years > 40:
        _flag(flags, "impossible_experience", "critical", "Extracted experience is implausibly high.", 35)
    elif total_years > 1.5 and not valid_work and not has_work_section:
        _flag(flags, "experience_without_work_evidence", "critical", "Experience years were extracted without reliable work-history evidence.", 30)
    elif total_years > 0 and not valid_work:
        _flag(flags, "weak_experience_evidence", "warning", "Experience years need recruiter validation because role/company evidence is weak.", 12)

    if explicit_years and total_years and abs(total_years - explicit_years) > 3:
        _flag(flags, "experience_conflict", "warning", "Computed experience conflicts with explicit years mentioned in the resume.", 14)

    max_years = float((jd_data or {}).get("max_experience_years") or 0)
    if max_years and total_years > max_years + 5 and not parsed.get("transition_candidate"):
        _flag(flags, "seniority_outside_jd_range", "warning", "Candidate experience is far above the JD target range.", 8)

    projects = [item for item in parsed.get("projects") or [] if isinstance(item, dict)]

    def _project_item_has_noise(item):
        name = _clean_text(item.get("name"))
        description = _clean_text(item.get("description"))
        body = f"{name} {description}"
        if not name:
            return True
        if len(name) > 120 or len(name.split()) > 14:
            return True
        if re.search(r"(@|https?://|www\.|\+?\d[\d\s().-]{8,}\d)", body, re.I):
            return True
        if re.fullmatch(r"(education|technical skills|technical tools|skills|experience|work experience|professional experience|contact|summary|profile)", name, re.I):
            return True
        if re.search(r"(?:^|\n)\s*(work experience|professional experience|education|technical skills|technical tools|summary|profile)\s*:?\s*(?:\n|$)", str(item.get("description") or ""), re.I):
            return True
        if re.search(
            r"\b(?:cid:\d+|achievements?|designation|location|manpower strength|ncaa|dean'?s list|all-conference team|"
            r"atlantic sun|community involvement|nashville food project|senior revenue accountant|senior staff accountant|"
            r"assistant business manager|bookkeeper|gaap|1099|cash flow|payment discrepancies|fiscal files|"
            r"financial statements|accounts payable|accounts receivable)\b",
            body,
            re.I,
        ):
            return True
        return False

    noisy_projects = [
        _clean_text(item.get("name"))
        for item in projects
        if _project_item_has_noise(item)
    ]
    if noisy_projects:
        _flag(flags, "noisy_project_evidence", "warning", "Project evidence contains resume section noise and should be reviewed.", 10)

    for item in flags:
        score -= item["penalty"]

    score = max(0, min(100, round(score, 2)))
    critical_count = sum(1 for item in flags if item["severity"] == "critical")

    if critical_count >= 2:
        action = "manual_review_required"
    elif critical_count == 1 or score < 55:
        action = "review_before_shortlist"
    else:
        action = "auto_rank_ok"

    return {
        "parser_quality_score": score,
        "parser_quality_flags": flags,
        "parser_quality_action": action,
    }


def apply_parser_quality_gate(parsed, exp_data=None, jd_data=None, resume_text=""):
    report = build_parser_quality_report(resume_text, parsed, exp_data, jd_data)
    flags = report["parser_quality_flags"]
    critical_count = sum(1 for item in flags if item["severity"] == "critical")
    flag_codes = {item.get("code") for item in flags}

    parsed["parser_quality_score"] = report["parser_quality_score"]
    parsed["parser_quality_flags"] = flags
    parsed["parser_quality_action"] = report["parser_quality_action"]
    parsed["resume_quality_score"] = min(
        float(parsed.get("resume_quality_score") or 100),
        report["parser_quality_score"],
    )

    cap = 100
    confidence_cap = 100
    if critical_count >= 2:
        cap = 58
        confidence_cap = 45
    elif critical_count == 1:
        cap = 68
        confidence_cap = 58
    elif report["parser_quality_score"] < 55:
        cap = 72
        confidence_cap = 62

    if cap < 100:
        for key in ("final_score", "rank_score"):
            if parsed.get(key) is not None:
                parsed[key] = min(float(parsed.get(key) or 0), cap)
        if parsed.get("confidence_score") is not None:
            parsed["confidence_score"] = min(float(parsed.get("confidence_score") or 0), confidence_cap)
        parsed["recommendation"] = "in_review"
        parsed["fit_band"] = "review"

    if "noisy_project_evidence" in flag_codes:
        parsed["projects"] = []
        parsed["project_evidence_needs_manual_review"] = True
        parser_flags = set(parsed.get("parser_flags") or [])
        parser_flags.add("project_noise_detected")
        parsed["parser_flags"] = sorted(parser_flags)
        safe_display = dict(parsed.get("safe_display") or {})
        safe_display["project_evidence"] = "Needs manual review"
        parsed["safe_display"] = safe_display
        field_confidence = dict(parsed.get("field_confidence") or {})
        field_confidence["project_evidence"] = min(float(field_confidence.get("project_evidence") or 0.35), 0.35)
        parsed["field_confidence"] = field_confidence

    messages = [item["message"] for item in flags[:3]]
    if messages:
        suffix = " Parser quality gate: " + " ".join(messages)
        parsed["ranking_reason"] = _clean_text(f"{parsed.get('ranking_reason') or ''}{suffix}")
        concerns = list(parsed.get("resume_quality_concerns") or [])
        for message in messages:
            if message not in concerns:
                concerns.append(message)
        parsed["resume_quality_concerns"] = concerns

    return report
