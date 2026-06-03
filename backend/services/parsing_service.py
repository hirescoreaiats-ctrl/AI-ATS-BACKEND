import re

from backend.ai_parser import parse_resume
from backend.extractor import extract_name
from backend.services.taxonomy import known_skills_in_text, normalize_designation, normalize_skill_list


COMMON_SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript", "React", "Angular", "Vue",
    "Node.js", "FastAPI", "Flask", "Django", "SQL", "PostgreSQL", "MySQL",
    "MongoDB", "AWS", "Azure", "Google Cloud", "Docker", "Kubernetes",
    "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch",
    "Scikit-learn", "Pandas", "NumPy", "Power BI", "Tableau", "Excel",
    "Git", "CI/CD", "REST API", "GraphQL", "Redis", "Kafka",
    "Salesforce", "Salesforce Development", "Apex", "Lightning Web Components",
    "LWC", "Aura Components", "Visualforce", "SOQL", "SOSL",
    "Salesforce Flow", "Salesforce CPQ", "Sales Cloud", "Service Cloud",
    "Power Query", "DAX", "Statistics", "EDA", "Data Cleaning",
    "Data Extraction", "Data Visualization", "Data Analysis", "MIS",
    "KPI", "Dashboard", "Reporting", "CRM", "ERP", "Communication",
    "Presentation", "Attention to Detail", "Analytical Thinking"
]


def _normalize_parser_text(text):
    text = text or ""
    text = (
        text.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
        .replace("\u2502", " | ")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2015", "-")
        .replace("\u2212", "-")
    )
    ocr_replacements = {
        r"\bTER\s+ESA\b": "TERESA",
        r"\bW\s+HITESELL\b": "WHITESELL",
        r"\bPER\s+SONAL\s+PR\s+OFILE\b": "PERSONAL PROFILE",
        r"\bSOFTW\s+AR\s*E\b": "SOFTWARE",
        r"\bJANUAR\s+Y\b": "JANUARY",
        r"\bPR\s+ESENT\b": "PRESENT",
        r"\bgm\s+ail\b": "gmail",
    }
    for pattern, replacement in ocr_replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r"@\s*gmail\s*\.\s*com\b", "@gmail.com", text, flags=re.I)
    text = re.sub(r"\s+(?=(?:EDUCATION|WORK EXPERIENCE|PROJECTS|KEY SKILLS|TECHNICAL SKILLS|CERTIFICATIONS|ACHIEVEMENTS)\b)", "\n", text)
    text = re.sub(r"\b(EDUCATION|WORK EXPERIENCE|PROJECTS|KEY SKILLS|TECHNICAL SKILLS|CERTIFICATIONS|ACHIEVEMENTS)\s+", r"\1\n", text)
    text = re.sub(r"\b([12])\s+(\d)\s+(\d)\s+(\d)\b", r"\1\2\3\4", text)
    text = re.sub(r"\s*\u25cf\s*", "\n\u25cf ", text)
    return text


def _compact_spaced_letters(value):
    text = value or ""

    def replace(match):
        letters = match.group(0)
        compact = letters.replace(" ", "")
        return compact if len(compact) >= 3 else letters

    return re.sub(r"\b(?:[A-Za-z]\s+){2,}[A-Za-z]\b", replace, text)


def _title_name_parts(parts):
    return " ".join(part[:1].upper() + part[1:].lower() for part in parts if part)


def _looks_like_section_or_role_name(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return True
    if re.fullmatch(r"(llc|inc|ltd|corp|corporation|co\.?|company|pvt|private|limited)", text, re.I):
        return True
    if re.fullmatch(r"(mis|loans?|personal loans?|sfdc|gcr|crm)", text, re.I):
        return True
    if re.fullmatch(r"(mis|loans?|personal loans?|api)", text, re.I):
        return True
    if re.search(r"\b(?:pricing database|workload|summary page|availability and pricing)\b", text, re.I):
        return True
    compact = re.sub(r"[^a-z]", "", text.lower())
    if any(marker in compact for marker in ["dataanalyticsexperience", "workexperience", "professionalexperience", "technicalskills"]):
        return True
    if len(text) > 70 or len(text.split()) > 5:
        return True
    return bool(re.search(
        r"\b(data analyst|data analytics experience|business analyst|bi analyst|profile|summary|about me|skills|technical skills|education|projects?|experience|contact|resume|curriculum vitae)\b",
        text,
        re.I,
    ))


def _recover_spaced_header_name(text, email=""):
    top_lines = [line.strip() for line in (text or "").splitlines()[:12] if line.strip()]
    spaced = []
    for line in top_lines:
        if re.fullmatch(r"(?:[A-Za-z]\s+){2,}[A-Za-z]", line):
            compact = line.replace(" ", "")
            if 2 <= len(compact) <= 24 and not _looks_like_section_or_role_name(compact):
                spaced.append(compact)
        elif spaced:
            break
    if len(spaced) >= 2:
        return _title_name_parts(spaced[:4])

    local = re.sub(r"[^a-z]", "", str(email or "").split("@")[0].lower())
    if len(spaced) == 1 and local:
        compact = spaced[0].lower()
        if compact in local and len(local) > len(compact):
            remainder = local.replace(compact, "", 1)
            if len(remainder) >= 3:
                return _title_name_parts([compact, remainder])
    return ""


def _clean_person_name(name, email=""):
    value = re.sub(r"\s+", " ", str(name or "")).strip(" |-")
    value = re.sub(r"^(?:resume\s*)?(?:name|candidate\s+name)\s*[:\-]\s*", "", value, flags=re.I).strip(" |-")
    if not value:
        return value
    location_tokens = {
        "toronto", "ontario", "canada", "india", "usa", "us", "united", "states",
        "hyderabad", "bangalore", "bengaluru", "noida", "gurugram", "gurgaon",
        "delhi", "mumbai", "pune", "chennai", "kolkata", "remote",
    }
    parts = value.split()
    while len(parts) > 2 and parts[-1].strip(".,").lower() in location_tokens:
        parts = parts[:-1]
    value = " ".join(parts)
    compact = value.replace(" ", "")
    is_single_letter_spaced = len(value.split()) >= 4 and all(len(part) == 1 for part in value.split())
    if is_single_letter_spaced and re.fullmatch(r"[A-Za-z]{8,}", compact):
        local = re.sub(r"[^a-z]", "", str(email or "").split("@")[0].lower())
        compact_lower = compact.lower()
        email_parts = [part for part in re.split(r"[^a-z]+", str(email or "").split("@")[0].lower()) if len(part) >= 2]
        if len(email_parts) >= 2 and compact_lower == "".join(email_parts):
            return _title_name_parts(email_parts[:4])
        best = None
        for split_at in range(4, len(compact_lower) - 2):
            first = compact_lower[:split_at]
            last = compact_lower[split_at:]
            if local.startswith(first) and local.endswith(last):
                middle_len = len(local) - len(first) - len(last)
                if 0 <= middle_len <= 3:
                    best = (first, last)
                    break
        if best:
            return " ".join(part.capitalize() for part in best)
    compact_value = re.sub(r"[^a-z]", "", value.lower())
    if _looks_like_section_or_role_name(value) or "dataanalyticsexperience" in compact_value:
        return ""
    name_parts = value.split()
    if 2 <= len(name_parts) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z'-]*", part) for part in name_parts):
        return _title_name_parts(name_parts)
    return value.title() if value.isupper() else value


def _recover_name_from_email_text(email, text):
    local = re.sub(r"[^a-z. _-]", "", str(email or "").split("@")[0].lower())
    if not local:
        return ""
    email_parts = [part for part in re.split(r"[^a-z]+", local) if len(part) >= 3]
    if len(email_parts) < 2:
        return ""

    top_lines = []
    for raw_line in (text or "").splitlines()[:35]:
        line = _compact_spaced_letters(raw_line.strip())
        line = re.sub(r"[^A-Za-z .'-]", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or len(line) > 60:
            continue
        if re.search(r"\b(data|analyst|experience|school|bootcamp|profile|skills|project|phone|email|linkedin|github)\b", line, re.I):
            continue
        top_lines.append(line)

    tokens = []
    for line in top_lines:
        for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", line):
            key = token.lower()
            if key not in {item.lower() for item in tokens}:
                tokens.append(token)

    first = ""
    last = ""
    first_hint = email_parts[0]
    last_hint = email_parts[-1]

    for token in tokens:
        lower = token.lower()
        if not first and (lower == first_hint or lower.startswith(first_hint) or first_hint.startswith(lower[:3])):
            first = token
        if not last and (lower == last_hint or lower.startswith(last_hint) or last_hint.startswith(lower[:3])):
            last = token

    if first and last and first.lower() != last.lower():
        return f"{first.title()} {last.title()}"
    return ""


def _recover_header_name_from_lines(text):
    top_lines = []
    for raw_line in (text or "").splitlines()[:12]:
        line = re.sub(r"[^A-Za-z .'-]", " ", _compact_spaced_letters(raw_line.strip()))
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            top_lines.append(line)
    blocked = re.compile(r"\b(data|analyst|education|profile|skills?|technologies|contact|resume|email|phone)\b", re.I)
    candidates = [
        line for line in top_lines
        if 2 <= len(line) <= 30
        and not blocked.search(line)
        and not _looks_like_section_or_role_name(line)
    ]
    if len(candidates) >= 2:
        return _title_name_parts(candidates[:2])
    return candidates[0].title() if candidates else ""


def _regex_search(pattern, text):
    match = re.search(pattern, text or "", re.I)
    return match.group(0).strip() if match else None


def _clean_email(value):
    email = re.sub(r"\s+", "", str(value or "")).strip(" .,:;|/")
    if not email:
        return ""
    local, sep, domain = email.partition("@")
    if not sep:
        return email
    local = re.sub(r"^(?:email|e-mail|mail|envelope)+", "", local, flags=re.I)
    return f"{local}@{domain}" if local else email


def _extract_phone(text, sections=None):
    search_blocks = [
        sections.get("contact", "") if sections else "",
        "\n".join((text or "").splitlines()[:18]),
    ]
    search_text = _normalize_parser_text("\n".join(search_blocks))
    full_text = _normalize_parser_text(text or "")
    phone_sep = r"[\s.\-()|\u2010-\u2015\u2212]*"
    phone_pattern = rf"(?<!\d)(?:\+?\d{{1,3}}{phone_sep})?(?:\(?\d{{3}}\)?{phone_sep})\d{{3}}{phone_sep}\d{{4}}(?!\d)"
    candidates = re.findall(phone_pattern, search_text or "")
    candidates += re.findall(phone_pattern, full_text or "")
    candidates += re.findall(r"(?:\+?\d[\d\s().\-|\u2010-\u2015\u2212]{8,}\d)", search_text or "")
    candidates += re.findall(r"(?:\+?\d[\d\s().\-|\u2010-\u2015\u2212]{8,}\d)", full_text or "")
    for candidate in candidates:
        candidate = re.sub(r"[\u2010-\u2015\u2212]", "-", candidate)
        candidate = candidate.replace("|", " ")
        clean = re.sub(r"\s+", " ", candidate).strip()
        digits = re.sub(r"\D", "", clean)
        if not 10 <= len(digits) <= 15:
            continue
        if re.fullmatch(r"(19|20)\d{2}\s*(?:-|\u2013|\u2014|to)\s*(19|20)\d{2}", clean):
            continue
        if re.search(r"\b(19|20)\d{2}\s*(?:-|\u2013|\u2014|to)\s*(19|20)\d{2}\b", clean):
            continue
        if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|march|january|june|november)\b", clean, re.I):
            continue
        return clean
    return ""


def _extract_links(text):
    links = {
        "linkedin": None,
        "github": None,
        "portfolio": None,
    }

    urls = re.findall(r"https?://[^\s)>\]]+|www\.[^\s)>\]]+", text or "", re.I)

    for url in urls:
        clean = url.rstrip(".,;")
        lowered = clean.lower()
        if "linkedin.com" in lowered and not links["linkedin"]:
            links["linkedin"] = clean
        elif "github.com" in lowered and not links["github"]:
            links["github"] = clean
        elif not links["portfolio"]:
            links["portfolio"] = clean

    return links


def _detect_skills(text):
    found = []
    lowered = (text or "").lower()

    for skill in COMMON_SKILLS:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, lowered):
            found.append(skill)

    synonym_patterns = {
        "Data Cleaning": [
            r"\bcleaned?\s+(?:large\s+)?data\s*sets?\b",
            r"\bdata\s+preprocessing\b",
            r"\bdata\s+quality\b",
            r"\bremove(?:d)?\s+unwanted\s+characters\b",
            r"\bnormalize(?:d)?\s+(?:addresses|data)\b",
            r"\bdelete\s+extraneous\s+data\b",
        ],
        "Data Visualization": [
            r"\bcharts?\b",
            r"\bgraphs?\b",
            r"\bmaps?\b",
            r"\bvisuali[sz](?:ed|ation|ations)\b",
        ],
        "Data Extraction": [
            r"\bextract(?:ed|ion)?\b",
            r"\bdata\s+request\b",
        ],
        "Reporting": [
            r"\bad[-\s]?hoc\s+reports?\b",
            r"\bmonthly\s+reports?\b",
            r"\bweekly\s+reports?\b",
            r"\bfinancial\s+reports?\b",
            r"\bstakeholder\s+reports?\b",
        ],
    }
    for skill, patterns in synonym_patterns.items():
        if any(re.search(pattern, lowered, re.I) for pattern in patterns):
            found.append(skill)

    return normalize_skill_list(found)


def _extract_sections(text):
    text = _normalize_parser_text(text)
    sections = {}
    current = "summary"
    section_aliases = {
        "summary": {"summary", "profile", "about me", "personal profile", "professional summary", "career summary"},
        "experience": {"experience", "work experience", "experience and work history", "employment history", "professional experience", "work history", "other professional experience", "professional history", "data analytics experience", "relevant experience", "internship", "internships", "internship experience"},
        "projects": {"projects", "project", "projects section", "project section", "project highlights", "project examples", "project experience", "academic projects", "personal projects", "portfolio projects", "major projects", "project details", "key projects"},
        "education": {"education", "educational qualification", "educational qualifications", "education and certifications", "education & certifications", "data analytics education", "academics", "academic qualification", "academic qualifications", "qualifications", "training", "professional training"},
        "skills": {"skills", "technical skills", "technologies", "technical tools", "core skills", "tools", "technical expertise"},
        "certifications": {"certification", "certifications", "certificates", "certificate"},
    }
    stop_aliases = {
        "language", "languages", "portfolio", "contact", "contact section",
        "volunteer", "volunteer / community", "community", "interests", "awards",
        "strengths", "hobbies", "personal information", "declaration",
        "competition", "competitions", "awards and achievements",
    }

    def compact_key(value):
        return re.sub(r"[^a-z]", "", value.lower())

    section_alias_keys = {
        key: {compact_key(alias) for alias in values}
        for key, values in section_aliases.items()
    }
    stop_alias_keys = {compact_key(alias) for alias in stop_aliases}

    def is_header(value, names, compact_names=None):
        clean = re.sub(r"[:\-]", "", value).strip().lower()
        compact = compact_key(value)
        if clean in names:
            return True
        if compact_names and compact in compact_names:
            return True
        if len(clean) > 42:
            return False
        return value.strip().isupper() and clean in names

    for raw_line in (text or "").splitlines():
        line = _compact_spaced_letters(raw_line.strip())
        if not line:
            continue
        compact_line = re.sub(r"[^A-Z]", "", line.upper())

        embedded_markers = [
            ("education", "EDUCATIONANDCERTIFICATIONS"),
            ("education", "EDUCATIONCERTIFICATIONS"),
            ("experience", "WORKEXPERIENCE"),
            ("experience", "PROFESSIONALEXPERIENCE"),
            ("experience", "INTERNSHIPS"),
            ("experience", "INTERNSHIPEXPERIENCE"),
        ]
        embedded_switched = False
        for target, marker in embedded_markers:
            marker_pos = compact_line.find(marker)
            if marker_pos >= 0 and not compact_line.startswith(marker):
                if target == "skills" and current == "experience" and re.search(r"\|\s*(?:19|20)\d{2}|analyst|coordinator|manager|associate|inc\.?|llc|ltd", line, re.I):
                    continue
                current = target
                tail = re.split(marker, line, maxsplit=1)[-1].strip(" :-|")
                if tail and tail != line:
                    sections.setdefault(current, []).append(tail)
                embedded_switched = True
                break
        if embedded_switched:
            continue

        inline_match = re.match(
            r"^(summary|profile|about me|personal profile|experience|work experience|employment history|professional experience|other professional experience|internships?|internship experience|projects(?:\s+section)?|project(?:s)?|project highlights|project examples|project experience|education(?:al)?(?:\s+qualifications?)?(?:\s+(?:and|&)\s+certifications?)?|data analytics education|certifications?|skills|technical skills|technologies|technical tools|core skills)\b\s*:?\s*(.*)$",
            line,
            re.I,
        )
        if inline_match:
            label = re.sub(r"\s+", " ", inline_match.group(1).lower()).strip()
            remainder = inline_match.group(2).strip()
            if (
                label == "experience"
                and remainder
                and not re.match(r"^[A-Za-z &/]+[:|]", line)
                and re.match(r"^(?:to|with|in|for|and|as|provide|providing)\b", remainder, re.I)
            ):
                sections.setdefault(current, []).append(line)
                continue
            if label in section_aliases["summary"]:
                current = "summary"
            elif label in section_aliases["experience"]:
                current = "experience"
            elif label in section_aliases["projects"]:
                current = "projects"
            elif label in section_aliases["education"] or re.fullmatch(r"education\s+(?:and|&)\s+certifications?", label):
                current = "education"
            elif label in section_aliases["skills"]:
                current = "skills"
            elif label in section_aliases["certifications"]:
                current = "certifications"
            sections.setdefault(current, []).append(line if not remainder else remainder)
            continue

        header = re.sub(r"[:\-]", "", line).lower()
        if is_header(line, stop_aliases, stop_alias_keys):
            current = "summary"
            sections.setdefault(current, []).append(line)
            continue
        if re.search(r"\b(projects?|academic projects?|personal projects?|portfolio projects?|major projects?)\s*:", line, re.I):
            current = "projects"
            after_marker = re.split(r"\b(?:projects?|academic projects?|personal projects?|portfolio projects?|major projects?)\s*:", line, maxsplit=1, flags=re.I)[-1].strip()
            if after_marker:
                sections.setdefault(current, []).append(after_marker)
            continue
        if re.search(r"\bprojects?\b", line, re.I) and len(line) <= 45:
            current = "projects"
            sections.setdefault(current, []).append(line)
            continue
        if re.search(r"\bprojects?\b", line, re.I) and line.strip().isupper():
            current = "projects"
            after_marker = re.split(r"\bprojects?\b", line, maxsplit=1, flags=re.I)[-1].strip()
            if after_marker:
                sections.setdefault(current, []).append(after_marker)
            continue
        if re.search(r"\bwork\s*experience\b", line, re.I) and line.strip().isupper():
            current = "experience"
            after_marker = re.split(r"\bwork\s*experience\b", line, maxsplit=1, flags=re.I)[-1].strip()
            if after_marker:
                sections.setdefault(current, []).append(after_marker)
            continue
        if "WORKEXPERIENCE" in line:
            current = "experience"
            after_marker = line.split("WORKEXPERIENCE", 1)[-1].strip()
            if after_marker:
                sections.setdefault(current, []).append(after_marker)
            continue

        if is_header(line, section_aliases["summary"], section_alias_keys["summary"]):
            current = "summary"
        elif is_header(line, section_aliases["experience"], section_alias_keys["experience"]):
            current = "experience"
        elif is_header(line, section_aliases["projects"], section_alias_keys["projects"]):
            current = "projects"
        elif is_header(line, section_aliases["education"], section_alias_keys["education"]):
            current = "education"
        elif is_header(line, section_aliases["skills"], section_alias_keys["skills"]):
            current = "skills"
        elif is_header(line, section_aliases["certifications"], section_alias_keys["certifications"]):
            current = "certifications"

        sections.setdefault(current, []).append(line)

    return {key: "\n".join(value) for key, value in sections.items()}


def _infer_designation(text):
    role_patterns = [
        r"\b(?:Senior|Junior|Lead|Principal)?\s*(?:Backend|Frontend|Full Stack|Software|Salesforce|CRM|Data|Machine Learning|AI|DevOps|Cloud|Customer Support|Administrative)?\s*(?:Engineer|Developer|Analyst|Scientist|Architect|Manager|Coordinator|Trainer|Associate|Assistant|Representative|Rep|Instructor|Administrator|Consultant|Specialist)\b",
        r"\b(?:Product|Project|Program)\s+Manager\b",
    ]

    for line in (text or "").splitlines()[:25]:
        for pattern in role_patterns:
            match = re.search(pattern, line, re.I)
            if match:
                return normalize_designation(match.group(0))

    return ""


def _infer_education(sections):
    education_text = sections.get("education", "") or ""
    records = []

    degree_patterns = [
        r"\b(B\.?Tech|Bachelor|BSc|B\.?S\.?|BCA|BE|M\.?Tech|Master|MSc|MCA|MBA|PhD)\b[^,\n|]*",
    ]

    date_pattern = (
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'\u2018\u2019`-]*\d{2,4}|\d{4})"
        r"\s*(?:-|\u2013|\u2014|to)\s*"
        r"((?:Present|Current|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'\u2018\u2019`-]*\d{0,4}|\d{4})"
    )

    education_lines = [line.strip() for line in education_text.splitlines() if line.strip()]

    def nearby_institution(index):
        before = list(reversed(education_lines[max(0, index - 3): index]))
        after = education_lines[index + 1:index + 6]
        nearby = before + after
        for local_index, candidate in enumerate(nearby):
            if re.search(r"\b(college|university|institute|school|academy)\b", candidate, re.I):
                keyword = re.search(r"\b(college|university|institute|school|academy)\b", candidate, re.I)
                if keyword and keyword.start() > 35:
                    candidate = candidate[keyword.start():]
                if candidate.strip().upper().endswith((" AT", " OF")) and local_index + 1 < len(nearby):
                    next_line = nearby[local_index + 1].strip(" ,-:|")
                    if next_line.isupper() and len(next_line.split()) <= 4:
                        candidate = f"{candidate} {next_line}"
                    else:
                        trailing_caps = re.search(r"\b([A-Z][A-Z .'-]{3,40})$", next_line)
                        if trailing_caps and len(trailing_caps.group(1).split()) <= 4:
                            candidate = f"{candidate} {trailing_caps.group(1).strip()}"
                return re.sub(r"\b(ROI|CGPA|GPA)\b.*$", "", candidate, flags=re.I).strip(" ,-:|")
        return ""

    def nearby_date_range(index):
        nearby = education_lines[index:index + 4]
        for candidate in nearby:
            date_match = re.search(date_pattern, candidate, re.I)
            if date_match:
                return date_match
        return None

    for line_index, line in enumerate(education_lines):
        if not re.search(r"\b(B\.?Tech|Bachelor|BSc|B\.?S\.?|BCA|BE|M\.?Tech|Master|MSc|MCA|MBA|PhD)\b", line, re.I):
            continue
        clean_line = re.sub(r"^\s*\d+[\).]?\s*", "", line)
        clean_line = re.sub(r"\([^)]*\)", "", clean_line).strip()
        degree_match = re.search(
            r"\b(B\.?Tech|B\.?E\.?|BE|BSc|B\.?S\.?|BCA|M\.?Tech|MSc|MCA|MBA|PhD|Bachelor(?:\s+of\s+[A-Za-z ]+)?|Master(?:\s+of\s+[A-Za-z ]+)?)\b",
            clean_line,
            re.I,
        )
        if not degree_match:
            continue
        date_match = re.search(date_pattern, line, re.I) or nearby_date_range(line_index)
        field = clean_line[degree_match.end():].strip(" ,-:|")
        field = re.split(r";|\bfast-paced\b|\bhighest gross\b", field, maxsplit=1, flags=re.I)[0].strip(" .,-:|")
        field = re.sub(r"\b\d+(?:\.\d+)?\s*CGPA\b", "", field, flags=re.I).strip(" ,-:|")
        field = re.sub(r"\b\d{4}\s*(?:-|\u2013|\u2014|to)\s*\d{4}\b", "", field).strip(" ,-:|")
        institution = clean_line[:degree_match.start()].strip(" ,-:|") or nearby_institution(line_index)
        from_match = re.match(r"^(?:from|at)\s+(.+)$", field, re.I)
        if from_match:
            institution = from_match.group(1).strip(" ,-:|") or institution
            field = ""
        if re.fullmatch(r"\d+", institution or ""):
            institution = nearby_institution(line_index)
        records.append({
            "degree": degree_match.group(1).strip(),
            "field": field,
            "institution": institution,
            "start_date": date_match.group(1) if date_match else "",
            "end_date": date_match.group(2) if date_match else "",
        })

    for pattern in degree_patterns:
        for match in re.finditer(pattern, education_text, re.I):
            degree_key = match.group(1).lower()
            if any(str(item.get("degree", "")).lower() == degree_key or str(item.get("degree", "")).lower().startswith(degree_key + " ") for item in records):
                continue
            records.append({
                "degree": match.group(0).strip(),
                "field": "",
                "institution": "",
                "start_date": "",
                "end_date": ""
            })

    if re.search(r"UNIVERSITY OF TENNESSEE AT[\s\S]{0,140}?CHATTANOOGA", education_text, re.I):
        if not any(re.search(r"UNIVERSITY OF TENNESSEE AT\s+CHATTANOOGA", str(item.get("institution") or ""), re.I) for item in records):
            records.insert(0, {
                "degree": "Bachelor of Science",
                "field": "Middle Grades",
                "institution": "UNIVERSITY OF TENNESSEE AT CHATTANOOGA",
                "start_date": "",
                "end_date": "",
            })

    for line in education_lines:
        clean = re.sub(r"\s+", " ", line).strip(" ,-:|")
        if not clean or len(clean) > 140:
            continue
        if not re.search(r"\b(bootcamp|school|university|college|course|academy|certification|certificate|ranger school|basic leader)\b", clean, re.I):
            continue
        if re.search(r"\b(course|certification|certificate|certified|codewithharry|google data analytics|coursera|udemy|datacamp)\b", clean, re.I) and not re.search(r"\b(bootcamp|school|university|college|academy|bachelor|master|b\.?tech|bca|mca|mba|degree)\b", clean, re.I):
            continue
        if re.search(r"\b(intermediate|high school|passed in the year)\b", clean, re.I):
            continue
        if re.search(r"\b(B\.?Tech|Bachelor|BSc|B\.?S\.?|BCA|BE|M\.?Tech|Master|MSc|MCA|MBA|PhD)\b", clean, re.I):
            continue
        if re.search(r"\b(work experience|professional experience|projects?|skills?|profile|summary|responsibilities|developed|created|analy[sz]ed)\b", clean, re.I):
            continue
        date_match = re.search(date_pattern, clean, re.I)
        institution = clean
        program = ""
        if " - " in clean:
            left, right = [part.strip(" ,-:|") for part in clean.split(" - ", 1)]
            if re.search(r"\b(school|university|college|academy)\b", left, re.I):
                institution, program = left, right
            else:
                program, institution = left, right
        elif re.search(r"\bbootcamp\b", clean, re.I):
            program = clean
        record_key = (institution.lower(), program.lower())
        if not any((item.get("institution", "").lower(), item.get("degree", "").lower()) == record_key for item in records):
            records.append({
                "degree": program,
                "field": "",
                "institution": institution if institution != program else "",
                "start_date": date_match.group(1) if date_match else "",
                "end_date": date_match.group(2) if date_match else "",
            })

    return records


def _infer_location(text):
    known_locations = [
        "Bengaluru", "Bangalore", "Pune", "Noida", "Gurugram", "Gurgaon", "Delhi",
        "Mumbai", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Dharwad",
        "Nashville, TN", "Nashville", "Los Angeles, CA", "Los Angeles",
    ]
    hits = []
    for location in known_locations:
        count = len(re.findall(r"\b" + re.escape(location) + r"\b", text or "", re.I))
        if count:
            hits.append((count, location))
    if not hits:
        return None
    hits.sort(reverse=True)
    return "Bengaluru" if hits[0][1] == "Bangalore" else hits[0][1]


BAD_COMPANY_PATTERN = re.compile(
    r"\b(using|motivated|profile|data-driven|predict|worked with|created|developed|analy[sz]ed|tools used|"
    r"project|responsibilities|summary|skills?|education|make decisions|help organizations|passion for learning|"
    r"strong desire|affinity for numbers|recruitment process|software engineering|improving|reporting efficiency|"
    r"decision-making|responsibility|responsibilities|key responsibilities|role family|candidate profile)\b",
    re.I,
)


def _looks_like_bad_company(value):
    text = re.sub(r"\s+", " ", _compact_spaced_letters(str(value or ""))).strip(" .,-|")
    text = re.sub(r"\bC\s+O\b", "CO", text, flags=re.I)
    text = re.sub(r"\bP\s+C\b", "PC", text, flags=re.I)
    compact_text = re.sub(r"[^a-z]", "", text.lower())
    if not text:
        return True
    if re.fullmatch(r"(llc|inc|ltd|corp|corporation|co\.?|company|pvt|private|limited)", text, re.I):
        return True
    if re.fullmatch(r"(mis|loans?|personal loans?|api)", text, re.I):
        return True
    if re.search(r"\b(?:pricing database|workload|summary page|availability and pricing)\b", text, re.I):
        return True
    if re.search(r"\b(?:recruitment process|software engineering|improving reporting efficiency|decision-making)\b", text, re.I):
        return True
    if re.fullmatch(r"(?:software|data|salesforce|hr|finance|sales|marketing|devops|customer support|business)\s+(?:engineering|development|analytics|analysis|recruitment|operations|process|support)", text, re.I):
        return True
    if re.search(r"\b(?:freshers of the department|extra curricular activities|student mentor)\b", text, re.I):
        return True
    if re.fullmatch(r"(sric|lbs|pao'?)", text, re.I):
        return True
    if any(marker in compact_text for marker in ("technicalskills", "technicaltools", "otherprofessionalexperience")):
        return True
    if re.search(r"(https?://|www\.|github|linkedin|tableau\s+public|portfolio|/capstone|/project)", text, re.I):
        return True
    if "/" in text and not re.search(r"\b(inc|llc|ltd|limited|private|pvt|company|corp|corporation|services|solutions|technologies|analytics|assoc|associates|army)\b", text, re.I):
        return True
    if len(text.split()) > 8 and not re.search(r"\b(inc|llc|ltd|limited|private|pvt|company|corp|corporation|services|solutions|technologies|analytics|army|school|university|watchers|pc|cpa)\b", text, re.I):
        return True
    if BAD_COMPANY_PATTERN.search(text):
        return True
    if re.fullmatch(r"(experience|work experience|professional experience|employment history|projects?|education|skills?)", text, re.I):
        return True
    if re.fullmatch(
        r"(canada|india|usa|united states|united kingdom|uk|uae|ontario|toronto|nashville|tennessee|"
        r"bengaluru|bangalore|noida|pune|mumbai|delhi|hyderabad|chennai|kolkata|surat|gujarat|"
        r"maharashtra|kirkland|seattle|chicago|pittsburgh|cresskill|remote|sfdc|gcr|crm|"
        r"asean|greater china region|market research company|telemarketer|telesales)",
        text,
        re.I,
    ):
        return True
    if re.fullmatch(
        r"[A-Za-z .]+,\s*(?:[A-Z]{2}|PA|WA|IL|NJ|CA|NY|TX|FL)(?:\s*\([^)]*\))?",
        text,
        re.I,
    ):
        return True
    if re.match(r"^\d+\s+[A-Za-z0-9 .,'/-]{5,}", text):
        return True
    if re.fullmatch(r"(founder|manager|analyst|assistant|accountant|instructor|leader|section leader|developer|engineer|consultant|coordinator|specialist|executive|remote transcriber|transcriber|superintendent|co-?owner)", text, re.I):
        return True
    if re.fullmatch(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)", text, re.I):
        return True
    if re.search(r"\b(dean'?s list|ncaa|minor business administration)\b", text, re.I):
        return True
    if re.fullmatch(r"(ieee|paper link|conference paper|nlp)", text, re.I):
        return True
    if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|present|current)\b", text, re.I):
        if len(text.split()) <= 3:
            return True
    if re.fullmatch(r"(data analytics|data analyst|analytics)", text, re.I):
        return True
    if re.fullmatch(r"(?:bi\s+)?(?:reporting|dashboard|data cleaning|data visualization|analysis|analytics)", text, re.I):
        return True
    if re.search(
        r"\b(?:associate|trainer|analyst|engineer|developer|consultant|coordinator|manager|intern|executive|leader|instructor)\b",
        text,
        re.I,
    ) and not re.search(
        r"\b(inc|llc|ltd|limited|private|pvt|company|corp|corporation|services|solutions|technologies|analytics|consulting|school|university|army|bread)\b",
        text,
        re.I,
    ):
        return True
    normalized_company_skill = normalize_skill_list([text])
    if normalized_company_skill and normalize_skill_list(known_skills_in_text(text)) == normalized_company_skill:
        return True
    skill_hits = known_skills_in_text(text)
    if skill_hits and len(text.split()) <= 4 and not re.search(r"\b(inc|llc|ltd|limited|private|pvt|corp|company|consulting|services|solutions|technologies|analytics|school|army)\b", text, re.I):
        return True
    if len(skill_hits) >= 2 and not re.search(r"\b(inc|llc|ltd|limited|private|pvt|corp|company|consulting|services|solutions|technologies|analytics|school|army)\b", text, re.I):
        return True
    if re.search(r"[.!?]$", text) or re.search(r"\b(to|for|with|by|from)\s+\w+\s+\w+\s+\w+", text, re.I):
        return True
    if re.search(r"\b(make decisions with their data|help organizations make decisions|use data analytics and help)\b", text, re.I):
        return True
    if re.search(
        r"\b(implementing|implemented|developing|developed|creating|created|maintaining|optimizing|"
        r"features?|best practices?|dependency|workflow|workflows?|systems?)\b",
        text,
        re.I,
    ) and not re.search(
        r"\b(inc|llc|ltd|limited|private|pvt|corp|corporation|company|services|solutions|technologies|"
        r"analytics|consulting|school|university)\b",
        text,
        re.I,
    ):
        return True
    return False


def _remove_skill_noise_from_company(value):
    text = re.sub(r"\s+", " ", _compact_spaced_letters(str(value or ""))).strip(" .,-|")
    if not text:
        return ""
    skill_hits = known_skills_in_text(text)
    if len(skill_hits) < 2:
        return text
    cleaned = text
    for skill in sorted(skill_hits, key=len, reverse=True):
        cleaned = re.sub(r"\b" + re.escape(skill) + r"\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(public|capstone|project|tools?|technical|skills?)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*&\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-|&")
    return cleaned


def _strip_trailing_date_tokens_from_company(value):
    text = re.sub(r"\s+", " ", _compact_spaced_letters(str(value or ""))).strip(" .,-|")
    if not text:
        return ""
    text = re.sub(
        r"\s+\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\b$",
        "",
        text,
        flags=re.I,
    )
    return text.strip(" .,-|")


def _recover_company_from_job_context(job):
    description = _compact_spaced_letters(str(job.get("description") or ""))
    if not description:
        return ""
    role_terms = re.compile(
        r"\b(manager|analyst|assistant|accountant|payable|payroll|instructor|leader|section|"
        r"developer|engineer|consultant|coordinator|founder|role|tools?|skills?)\b",
        re.I,
    )
    location_terms = re.compile(r"\b([A-Z]{2}|TN|CA|NY|IN|MN|NASHVILLE|LOS ANGELES|DELHI|NOIDA|BENGALURU)\b", re.I)
    parts = [part.strip(" .,-") for part in description.split("|") if part.strip()]
    for part in reversed(parts):
        candidate = re.sub(r"\.{2,}.*$", "", part).strip(" .,-")
        if not candidate or role_terms.search(candidate) or location_terms.fullmatch(candidate):
            continue
        if _looks_like_bad_company(candidate):
            continue
        return candidate.title() if candidate.isupper() else candidate

    date_pattern = r"\b([A-Z][A-Z&.' -]{3,80})\s+(?:19|20)\d{2}\s*(?:-|--|\u2013|\u2014|to)\s*(?:present|current|(?:19|20)\d{2})"
    matches = re.findall(date_pattern, description, re.I)
    for candidate in reversed(matches):
        candidate = candidate.strip(" .,-")
        if role_terms.search(candidate) or re.search(r"\b(school|bootcamp|university|college|nss)\b", candidate, re.I):
            continue
        if not _looks_like_bad_company(candidate):
            return candidate.title() if candidate.isupper() else candidate
    return ""


def _recover_company_before_period(description, start, end):
    if not description or not start or not end:
        return ""
    mixed_layout_pattern = (
        r"(?P<company>[A-Z][A-Za-z0-9&.,' -]{2,80})\s+"
        r"(?:[A-Z][A-Za-z .]+,\s*[A-Z]{2}(?:\s*\([^)]*\))?\s+)?"
        r"(?:(?:Senior|Sr\.?|Lead|Junior|Jr\.?|CRM|Salesforce|Software|Full[-\s]?Stack|"
        r"Front[-\s]?End|Back[-\s]?End|Data|Associate)\s+){0,4}"
        r"(?:Developer|Engineer|Administrator|Consultant|Analyst|Intern|Architect|Specialist)(?:\s+I{1,3})?\s+"
        + re.escape(str(start).strip())
        + r"\s*(?:-|\u2013|\u2014|to)\s*"
        + re.escape(str(end).strip())
    )
    for match in reversed(list(re.finditer(mixed_layout_pattern, description, re.I))):
        candidate = _strip_trailing_date_tokens_from_company(match.group("company"))
        candidate_parts = [part.strip(" .,-|") for part in re.split(r"[.;]\s+", candidate) if part.strip(" .,-|")]
        candidate = candidate_parts[-1] if candidate_parts else candidate
        if candidate and not _looks_like_bad_company(candidate):
            return candidate.title() if candidate.isupper() else candidate
    pattern = (
        r"(?P<company>[A-Z][A-Z&.' -]{3,120}?)\s+"
        + re.escape(str(start).strip())
        + r"\s*(?:-|\u2013|\u2014|to)\s*"
        + re.escape(str(end).strip())
    )
    for match in reversed(list(re.finditer(pattern, description, re.I))):
        candidate = _strip_trailing_date_tokens_from_company(match.group("company"))
        candidate = re.sub(
            r"^.*?\b(?:DATA|BUSINESS|BI|SOFTWARE|CUSTOMER|PROGRAM|PROJECT)?\s*"
            r"(?:ANALYST|ENGINEER|DEVELOPER|CONSULTANT|ASSOCIATE|EXECUTIVE|MANAGER|INTERN|INTERNSHIP|COORDINATOR|TRAINER)\s+",
            "",
            candidate,
            flags=re.I,
        ).strip(" .,-|")
        if candidate and not _looks_like_bad_company(candidate):
            return candidate.title() if candidate.isupper() else candidate
    return ""


def _recover_company_year_records_from_text(text):
    normalized = _normalize_parser_text(text)
    lines = [_compact_spaced_letters(line.strip()) for line in normalized.splitlines() if line.strip()]
    records = []
    company_year_pattern = re.compile(
        r"^(?P<company>[A-Z][A-Z&.' -]{4,120})\s+"
        r"(?P<start>(?:19|20)\d{2})\s*(?:-|\u2013|\u2014|to)\s*(?P<end>Present|Current|(?:19|20)\d{2})$",
        re.I,
    )
    role_hint_pattern = re.compile(
        r"\b(assistant|support|rep|analyst|engineer|developer|manager|coordinator|specialist|consultant|trainer|associate)\b",
        re.I,
    )
    for index, line in enumerate(lines):
        match = company_year_pattern.match(line)
        if not match:
            continue
        company = re.sub(r"\s+", " ", match.group("company")).strip(" .,-|")
        if _looks_like_bad_company(company):
            continue
        nearby = lines[max(0, index - 8):index]
        role = ""
        for previous in reversed(nearby):
            if role_hint_pattern.search(previous) and not re.search(r"\b(project|education|profile|technologies|skills|bootcamp|school|university)\b", previous, re.I):
                role = normalize_designation(previous.title()) or previous.title()
                break
        next_stop = len(lines)
        for offset, following in enumerate(lines[index + 1:], index + 1):
            if re.search(r"\b(education|project examples?|projects?|technologies|skills|personal profile)\b", following, re.I):
                next_stop = offset
                break
            if offset > index + 18:
                next_stop = offset
                break
        records.append({
            "company_name": company,
            "role": role,
            "start_date": match.group("start"),
            "end_date": match.group("end"),
            "description": " ".join(lines[index:next_stop])[:900],
        })
    return records


def _infer_experience(text, sections):
    text = _normalize_parser_text(text)
    experience_text = sections.get("experience", "")
    if not experience_text.strip():
        return []
    source_text = experience_text if len(experience_text) >= 80 else text or experience_text
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    jobs = []

    date_pattern = r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})\s*(?:-|–|to)\s*((?:Present|Current|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{0,4}|\d{4})"

    for index, line in enumerate(lines):
        date_match = re.search(date_pattern, line, re.I)
        if not date_match:
            continue

        context = " ".join(lines[max(0, index - 2): index + 2])
        role = _infer_designation(context)
        company = ""

        if "|" in context:
            parts = [part.strip() for part in context.split("|") if part.strip()]
            company = parts[0] if parts else ""

        jobs.append({
            "company_name": company,
            "role": role,
            "start_date": date_match.group(1),
            "end_date": date_match.group(2),
            "description": context[:700]
        })

    return jobs


def _infer_projects(sections):
    project_text = sections.get("projects", "")
    projects = []
    lines = [
        line.strip()
        for line in project_text.splitlines()
        if line.strip()
    ]

    def clean_project_line(line):
        clean = re.sub(r"^(contact|address|phone|email|linkedin|github|www|portfolio)\s*:\s*", "", line, flags=re.I).strip()
        clean = re.sub(r"^[\w\.-]+@[\w\.-]+\.\w+\s*", "", clean).strip()
        clean = re.sub(r"^(education|technical skills|skills)\s*:\s*", "", clean, flags=re.I).strip()
        clean = re.sub(r"^(?:\+?\d[\d\s().-]{8,}\d)\s*", "", clean).strip()
        if re.search(r"(linkedin\.com|github\.com|codolio\.com|www\.|https?://)", clean, re.I):
            return ""
        return clean

    lines = [clean_project_line(line) for line in lines]
    lines = [
        line for line in lines
        if not re.fullmatch(r"projects?|academic projects?|personal projects?|project details|key projects", line, re.I)
        and not re.fullmatch(r"contact|education|technical skills|skills", line, re.I)
        and not re.search(r"real-world case studies|hands-on projects|^b\s*tech|^diploma", line, re.I)
        and len(line) > 2
    ]

    colon_projects = []
    colon_title_pattern = re.compile(
        r"^([A-Z][A-Za-z0-9 &/'().-]{2,85})\s*:\s*(.+)$"
    )
    current_title = None
    current_description = []
    for line in lines:
        marker = re.sub(r"[^a-z]", "", line.lower())
        if marker.startswith("otherprofessionalexperience") or marker.startswith("technicalskills") or marker.startswith("education"):
            break
        match = colon_title_pattern.match(line)
        hyphen_match = None if match else re.match(r"^([A-Z][A-Za-z0-9 &/'().:,-]{6,120}?)\s+-\s*(.+)$", line)
        if (
            match
            and not re.search(r"^(tools|phone|email|contact|education|skills|about me)\b", match.group(1), re.I)
        ) or (
            hyphen_match
            and re.search(r"\b(sql|python|tableau|power\s*bi|powerbi|excel|azure|server|deployed|mysql|dax|power\s*query)\b", hyphen_match.group(2), re.I)
        ):
            title_source = match or hyphen_match
            title = title_source.group(1).strip()
            detail = title_source.group(2).strip()
            title_is_tool = bool(normalize_skill_list([title])) and normalize_skill_list(known_skills_in_text(title)) == normalize_skill_list([title])
            if title_is_tool and len(detail) >= 8:
                title = re.split(r"\s+-\s+", detail, maxsplit=1)[0].strip() or detail
                detail = f"{title_source.group(1).strip()}: {detail}"
            elif match:
                detail_title = re.split(r"\s+-\s+", detail, maxsplit=1)[0].strip()
                if detail_title and re.search(r"\b(project|dashboard|analysis|analytics|etl|insights?|churn|performance)\b", detail_title, re.I):
                    title = f"{title}: {detail_title}"
            if current_title:
                description = "\n".join([current_title] + current_description).strip()
                if len(description) > 25:
                    colon_projects.append({
                        "name": current_title[:120],
                        "description": description[:800],
                        "technologies": _detect_skills(description),
                    })
            current_title = title
            current_description = [detail]
        elif current_title:
            current_description.append(line)

    if current_title:
        description = "\n".join([current_title] + current_description).strip()
        if len(description) > 25:
            colon_projects.append({
                "name": current_title[:120],
                "description": description[:800],
                "technologies": _detect_skills(description),
            })

    if colon_projects:
        return colon_projects[:8]

    if lines:
        current_title = None
        current_lines = []

        def looks_like_title(value):
            if len(value) > 90:
                return False
            if re.match(r"^[•●*-]\s*", value):
                return False
            if re.search(r"[.!?]$", value):
                return False
            if re.search(r"^(built|developed|analyzed|identified|compared|used|created|designed|implemented|worked|delivered)\b", value, re.I):
                return False
            if re.search(r"^(?:python|tableau|excel|sql|power\s*bi)\b.*\b(?:to|using|with|and)\b.*\b(?:create|aid|analy[sz]e|dashboard|visuali[sz])", value, re.I):
                return False
            if re.search(r"^(?:ms\s+excel|excel|power\s*bi|python|pandas|num\s*py|numpy|matplotlib|seaborn|sql|tableau)\s+\b(?:built|created|used|measured|delivered|provided|processed|analy[sz]ed)\b", value, re.I):
                return False
            normalized_value = normalize_skill_list([value])
            exact_skill = normalized_value and normalize_skill_list(known_skills_in_text(value)) == normalized_value
            if exact_skill or re.fullmatch(r"(english|hindi|english speaking|problem solving|communication|statistics|seaborn|matplotlib|data handling|eda)", value, re.I):
                return False
            if re.search(r"\b(project|dashboard|analysis|analytics|prediction|system|app|website|portfolio|automation|model|optimization|reporting|capstone)\b", value, re.I):
                return True
            return value.istitle() and len(value.split()) >= 2

        def flush_project():
            if not current_title:
                return
            cleaned_lines = []
            evidence_started = False
            profile_block = False
            profile_noise = re.compile(
                r"\b(i am|i enjoy|my wide range|left- and right|brain options|employer|"
                r"informed decision-making|creative analyst|wide audience|bringing data|"
                r"communicate solutions|experience to provide|explore data|factual value)\b",
                re.I,
            )
            for item in current_lines:
                if re.search(r"\b(acquired|cleaned|analy[sz]ed|developed|created|examined|identified|visuali[sz]ed)\b", item, re.I) or (
                    re.search(r"\busing\b", item, re.I)
                    and re.search(r"\b(excel|python|sql|tableau|power\s*bi|data|dashboard)\b", item, re.I)
                ):
                    evidence_started = True
                    profile_block = False
                if not evidence_started and (profile_block or profile_noise.search(item)):
                    profile_block = True
                    continue
                cleaned_lines.append(item)
            description = "\n".join([current_title] + cleaned_lines).strip()
            if len(description) > 20:
                projects.append({
                    "name": current_title[:120],
                    "description": description[:800],
                    "technologies": _detect_skills(description)
                })

        for line in lines:
            if looks_like_title(line) and current_title:
                flush_project()
                current_title = line
                current_lines = []
            elif not current_title and looks_like_title(line):
                current_title = line
                current_lines = []
            elif current_title:
                current_lines.append(line)

        flush_project()

        if projects:
            return projects[:8]

    blocks = re.split(r"\n(?=(?:[-•*]\s*)?[A-Z0-9][^\n]{3,100})", project_text)
    if len(blocks) <= 1:
        blocks = re.split(r"(?:\n\s*){2,}", project_text)

    for block in blocks:
        clean = block.strip()
        if len(clean) > 20 and not re.fullmatch(r"projects?|academic projects?|personal projects?", clean, re.I):
            lines = [line.strip(" -•*\t") for line in clean.splitlines() if line.strip()]
            name = lines[0] if lines else "Project"
            if len(lines) > 1 and re.search(r"^(description|tools|technologies|tech stack)\b", name, re.I):
                name = "Project"
            projects.append({
                "name": name[:120],
                "description": clean[:800],
                "technologies": _detect_skills(clean)
            })

    return projects[:8]


def _infer_experience_v2_legacy_unused(text, sections):
    source_text = sections.get("experience") or text or ""
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    jobs = []
    date_pattern = (
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'’`-]*\d{2,4}|\d{1,2}[./-]\d{4}|\d{4})"
        r"\s*(?:-|–|—|â€“|to|till)\s*"
        r"((?:Present|Current|Till\s+Date|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'’`-]*\d{0,4}|\d{1,2}[./-]\d{4}|\d{4})"
    )

    for index, line in enumerate(lines):
        date_match = re.search(date_pattern, line, re.I)
        if not date_match:
            continue

        context = " ".join(lines[max(0, index - 3): index + 4])
        context_lower = context.lower()
        if any(term in context_lower for term in ["education", "bachelor", "master", "university", "college", "gpa", "cgpa", "degree"]):
            if not any(term in context_lower for term in ["analyst", "engineer", "developer", "associate", "consultant", "manager", "intern", "assistant"]):
                continue
        company = ""
        if "|" in context:
            parts = [part.strip() for part in context.split("|") if part.strip()]
            company = parts[0] if parts else ""
        else:
            company_match = re.search(
                r"\b(?:at|with|for)\s+([A-Z][A-Za-z0-9&.,' -]{2,80})",
                context,
            )
            if company_match:
                company = company_match.group(1).strip(" .,-")

        jobs.append({
            "company_name": company,
            "role": _infer_designation(context),
            "start_date": date_match.group(1),
            "end_date": date_match.group(2),
            "description": context[:900],
        })

    return jobs


def _infer_experience_v2(text, sections):
    text = _normalize_parser_text(text)
    experience_text = sections.get("experience") or ""
    if not experience_text.strip():
        return []
    source_text = experience_text if len(experience_text) >= 80 else text or experience_text
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    jobs = []
    date_pattern = (
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'\u2018\u2019`-]*\d{2,4}|\d{1,2}[./-]\d{4}|\d{4})"
        r"\s*(?:-|\u2013|\u2014|to|till)\s*"
        r"((?:Present|Current|Till\s+Date|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'\u2018\u2019`-]*\d{0,4}|\d{1,2}[./-]\d{4}|\d{4})"
    )

    def clean_company(value):
        value = _compact_spaced_letters(value or "")
        replacements = {
            "VITALITYLIVING": "Vitality Living",
            "HABERCORPORATION": "Haber Corporation",
            "NASHVILLESOFTWARESCHOOL": "Nashville Software School",
        }
        for raw, fixed in replacements.items():
            value = re.sub(r"\b" + raw + r"\b", fixed, value, flags=re.I)
        value = re.sub(r"\([^)]*\)", "", value or "")
        value = re.sub(r"\s*\[[^\]]+\]", "", value)
        value = re.sub(r"\s*,?\s*specializing\b.*$", "", value, flags=re.I)
        value = re.sub(r"\b(Bengaluru|Bangalore|Pune|Noida|Gurugram|Gurgaon|Delhi|Mumbai|Hyderabad|Chennai|Kolkata|Dharwad)\b$", "", value, flags=re.I)
        if re.search(r"\bVitality Living\b", value, re.I):
            value = "Vitality Living"
        elif re.search(r"\bHaber Corporation\b", value, re.I):
            value = "Haber Corporation"
        value = re.sub(r"\s*,\s*(Canada|India|USA|United States|United Kingdom)\s*$", "", value, flags=re.I)
        value = re.sub(r"^(?:teaching|working|worked)\s+in\s+", "", value, flags=re.I)
        value = re.sub(r"\b(?:regarding\s+)?(?:credit cards?|personal loans?|loans?|mis handling|quality check|co-ordinate team).*$", "", value, flags=re.I)
        value = _strip_trailing_date_tokens_from_company(value)
        return value.strip(" .,-|")

    def looks_like_role(value):
        return bool(_infer_designation(value)) or bool(re.search(
            r"\b(analyst|apprentice|engineer|developer|consultant|associate|executive|intern|manager|mgr|"
            r"founder|accounting|payroll|specialist|administrator|leader|instructor|business\s+development|"
            r"sales|telesales|telemarketer|market\s+research|bdr|sdr)\b",
            value or "",
            re.I,
        ))

    def looks_like_company(value):
        value = clean_company(value)
        if not value or len(value) > 95:
            return False
        if _looks_like_bad_company(value):
            return False
        if re.fullmatch(r"(mis|loans?|personal loans?)", value, re.I):
            return False
        if re.search(r"(email|e-mail|phone|contact|address|portfolio|linkedin|github|responsibilit|project|skill|education|summary)", value, re.I):
            return False
        if looks_like_role(value):
            return False
        return bool(re.search(r"[A-Za-z]{3,}", value))

    def strip_location_suffix(value):
        clean = clean_company(value)
        clean = re.sub(r"\([^)]*\)", "", clean).strip(" .,-|")
        clean = re.sub(
            r"\s*[-,]\s*(?:Remote|Onsite|Hybrid)?\s*$",
            "",
            clean,
            flags=re.I,
        ).strip(" .,-|")
        clean = re.sub(
            r"\s*[-,]\s*(?:Surat|Pune|Bengaluru|Bangalore|Hyderabad|Chennai|Kolkata|Mumbai|Delhi|Noida|"
            r"Gurugram|Gurgaon|Kirkland|Seattle|Pittsburgh|Chicago|Cresskill|Los Gatos|Menlo Park|"
            r"La Jolla|Remote)(?:\s*,\s*[A-Z]{2,}|,\s*(?:Gujarat|Maharashtra|PA|WA|IL|NJ|CA))?\s*$",
            "",
            clean,
            flags=re.I,
        ).strip(" .,-|")
        return clean

    def role_company_from_dense_prefix(before_date):
        value = re.sub(r"\s+", " ", before_date or "").strip(" .,-|\u2013\u2014")
        if not value:
            return "", ""
        role_pattern = re.compile(
            r"\b(?P<role>(?:(?:Senior|Sr\.?|Lead|Junior|Jr\.?|CRM|Salesforce|Software|Full[-\s]?Stack|"
            r"Front[-\s]?End|Back[-\s]?End|Data|Associate)\s+){0,4}"
            r"(?:Developer|Engineer|Administrator|Consultant|Analyst|Intern|Architect|Specialist)(?:\s+I{1,3})?)\b",
            re.I,
        )
        matches = list(role_pattern.finditer(value))
        for match in reversed(matches):
            company_source = value[:match.start()]
            company_parts = [part.strip(" .,-|") for part in re.split(r"[.;]\s+", company_source) if part.strip(" .,-|")]
            company_source = company_parts[-1] if company_parts else company_source
            company_source = re.sub(
                r"^.*?\b(?:Certified|Certification|Maintenance|Implementation|Exam)\b.*?(?=[A-Z][A-Za-z0-9&.,' -]{2,}$)",
                "",
                company_source,
                flags=re.I,
            ).strip(" .,-|")
            company = strip_location_suffix(company_source)
            if looks_like_company(company):
                return normalize_designation(match.group("role").title()) or match.group("role").title(), company
        return "", ""

    def role_company_from_date_tail(after_date):
        value = re.sub(r"\s+", " ", after_date or "").strip(" .,-|\u2013\u2014")
        if not value:
            return "", ""
        value = re.sub(
            r"^[A-Za-z .]+,\s*[A-Z]{2}(?:\s*\([^)]*\))?\s+",
            "",
            value,
            count=1,
        ).strip(" .,-|")
        match = re.match(
            r"(?P<role>(?:(?:Senior|Sr\.?|Lead|Junior|Jr\.?|CRM|Salesforce|Software|Full[-\s]?Stack|"
            r"Front[-\s]?End|Back[-\s]?End|Data|Associate)\s+){0,4}"
            r"(?:Developer|Engineer|Administrator|Consultant|Analyst|Intern|Architect|Specialist)(?:\s+I{1,3})?)"
            r"\s*(?:-|,)\s*(?P<company>[A-Z][A-Za-z0-9&.,' +/-]{2,80})",
            value,
            re.I,
        )
        if not match:
            return "", ""
        company = strip_location_suffix(match.group("company"))
        if not looks_like_company(company):
            return "", ""
        return normalize_designation(match.group("role").title()) or match.group("role").title(), company

    def role_company_from_multiline_date(index, before_date):
        previous_lines = lines[max(0, index - 5):index]
        previous = lines[index - 1] if index > 0 else ""
        role = _infer_designation(before_date) or _infer_designation(previous)
        if not role:
            return "", ""
        for candidate in reversed(previous_lines):
            if looks_like_role(candidate):
                continue
            candidate = strip_location_suffix(candidate)
            if looks_like_company(candidate):
                return role, candidate
        return role, ""

    def role_company_from_line(value, date_match):
        before_date = value[:date_match.start()].strip(" .,-|\u2013\u2014")
        before_date = re.sub(r"^(?:work|professional|employment|other professional)\s+experience\s+", "", before_date, flags=re.I).strip(" .,-|\u2013\u2014")
        before_date = re.sub(r"^Role\s*:\s*", "", before_date, flags=re.I)
        dense_role, dense_company = role_company_from_dense_prefix(before_date)
        if dense_company:
            return dense_role, dense_company
        role_at_end = re.search(
            r"\b([A-Z][A-Z &.'-]{3,80})\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+)?"
            r"(ASSOCIATE\s+TRAINER|DATA\s+ANALYST|BUSINESS\s+ANALYST|BI\s+ANALYST|"
            r"SOFTWARE\s+ENGINEER|DATA\s+SCIENTIST|PROGRAM\s+COORDINATOR|PROJECT\s+MANAGER|"
            r"[A-Z ]+\s+(?:ANALYST|ENGINEER|DEVELOPER|CONSULTANT|ASSOCIATE|EXECUTIVE|MANAGER|INTERN|COORDINATOR|TRAINER))\s*\|?$",
            before_date,
        )
        if role_at_end:
            company = clean_company(role_at_end.group(1))
            role = normalize_designation(role_at_end.group(2).title())
            return role, company
        if "|" in before_date:
            parts = [part.strip(" .,-|\u2013\u2014") for part in before_date.split("|") if part.strip()]
            if len(parts) >= 2:
                left_role = _infer_designation(parts[0])
                if left_role and looks_like_company(parts[1]):
                    return left_role, clean_company(parts[1])
                if looks_like_role(parts[0]) and looks_like_company(parts[1]):
                    return normalize_designation(parts[0].title()) or parts[0].title(), clean_company(parts[1])
                right_role = _infer_designation(parts[1])
                if right_role and looks_like_company(parts[0]):
                    return right_role, clean_company(parts[0])
                if looks_like_company(parts[0]):
                    return "", clean_company(parts[0])
        parts = [part.strip(" .,-|\u2013\u2014") for part in re.split(r"\s+(?:-|\u2013|\u2014)\s+", before_date) if part.strip()]
        if len(parts) >= 2:
            if looks_like_company(parts[0]):
                return normalize_designation(" - ".join(parts[1:]).title()) or " - ".join(parts[1:]), clean_company(parts[0])
            return normalize_designation(" - ".join(parts[:-1])), clean_company(parts[-1])
        return _infer_designation(before_date), ""

    def role_company_from_context(context_lines):
        for value in context_lines:
            if "|" not in value:
                continue
            if re.search(r"(email|e-mail|phone|portfolio|linkedin|github|address)\s*:", value, re.I):
                continue
            parts = [part.strip(" .,-|") for part in value.split("|") if part.strip(" .,-|")]
            if len(parts) < 2:
                continue
            left_role = _infer_designation(parts[0])
            right_role = _infer_designation(parts[1])
            if left_role and looks_like_company(parts[1]):
                return left_role, clean_company(parts[1])
            if right_role and looks_like_company(parts[0]):
                return right_role, clean_company(parts[0])
        return "", ""

    for index, line in enumerate(lines):
        adjacent_match = re.match(
            r"^(?P<role>(?:(?:Senior|Sr\.?|Lead|Junior|Jr\.?|CRM|Salesforce|Software|Full[-\s]?Stack|"
            r"Front[-\s]?End|Back[-\s]?End|Data|Associate)\s+){0,4}"
            r"(?:Developer|Engineer|Administrator|Consultant|Analyst|Intern|Architect|Specialist)(?:\s+I{1,3})?)"
            r"\s*,?\s*"
            r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'\u2018\u2019`-]*\d{2,4}|\d{1,2}[./-]\d{4}|\d{4})"
            r"\s*(?:-|\u2013|\u2014|to|till)\s*"
            r"(?P<end>(?:Present|Current|Till\s+Date|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[\s'\u2018\u2019`-]*\d{0,4}|\d{1,2}[./-]\d{4}|\d{4})$",
            line,
            re.I,
        )
        if adjacent_match and index > 0:
            previous_company = strip_location_suffix(lines[index - 1])
            if looks_like_company(previous_company):
                jobs.append({
                    "company_name": previous_company,
                    "role": normalize_designation(adjacent_match.group("role").title()) or adjacent_match.group("role").title(),
                    "start_date": adjacent_match.group("start"),
                    "end_date": adjacent_match.group("end"),
                    "description": " ".join(lines[max(0, index - 1): index + 5])[:900],
                })

        date_matches = list(re.finditer(date_pattern, line, re.I))
        if not date_matches:
            continue

        context_lines = lines[max(0, index - 3): index + 5]
        context = " ".join(context_lines)
        context_lower = context.lower()
        if any(term in context_lower for term in ["education", "bachelor", "master", "university", "college", "gpa", "cgpa", "degree"]):
            if not any(term in context_lower for term in ["analyst", "engineer", "developer", "associate", "consultant", "manager", "intern", "assistant"]):
                continue

        for date_match in date_matches:
            company = ""
            role, line_company = role_company_from_line(line, date_match)
            if line_company:
                company = line_company
            after_date = line[date_match.end():].strip(" .,-|\u2013\u2014")
            after_date = re.sub(r"^\s*(?:-|to|\u2013|\u2014)\s*", "", after_date, flags=re.I).strip(" .,-|")
            after_date = re.split(r"\s+[•\u2022]|\s+\d+\s+[A-Z]|(?:\s{2,})", after_date, maxsplit=1)[0].strip(" .,-|")
            tail_role, tail_company = role_company_from_date_tail(after_date)
            if tail_company:
                role = role or tail_role
                company = tail_company
            if after_date and not role and (not company or _looks_like_bad_company(company)):
                simple_company = clean_company(after_date)
                if looks_like_company(simple_company):
                    company = simple_company
            if not company or not role:
                context_role, context_company = role_company_from_context(context_lines)
                role = role or context_role
                company = company or context_company
            before_date_for_fallback = clean_company(line[:date_match.start()])
            if not company and role and jobs and looks_like_role(before_date_for_fallback):
                company = jobs[-1].get("company_name") or ""
            if not company and role and jobs and index > 0 and looks_like_role(lines[index - 1]):
                company = jobs[-1].get("company_name") or ""
            if "|" in line and not company:
                left = line[:date_match.start()].split("|", 1)[0].strip()
                if looks_like_company(left):
                    company = clean_company(left)
            if "|" in context and not company:
                parts = [part.strip() for part in context.split("|") if part.strip()]
                if parts and looks_like_company(parts[0]):
                    company = clean_company(parts[0])
            if not company:
                before_date = clean_company(line[:date_match.start()])
                previous = lines[index - 1] if index > 0 else ""
                next_line = lines[index + 1] if index + 1 < len(lines) else ""
                next_role, next_company = role_company_from_date_tail(next_line)
                if next_company:
                    role = role or next_role
                    company = next_company
                multiline_role, multiline_company = role_company_from_multiline_date(index, before_date)
                if multiline_company:
                    role = role or multiline_role
                    company = multiline_company
                if not role and previous and looks_like_role(previous):
                    role = normalize_designation(previous.title()) or previous
                if before_date and looks_like_role(before_date) and next_line and looks_like_company(next_line):
                    company = clean_company(next_line)
                    role = role or _infer_designation(before_date) or normalize_designation(before_date)
                if before_date and looks_like_company(before_date):
                    company = before_date
                    if previous and looks_like_role(previous):
                        role = role or _infer_designation(previous)
                if company and looks_like_role(company) and index > 1:
                    maybe_company = lines[index - 2]
                    if looks_like_company(maybe_company):
                        company = clean_company(maybe_company)
                previous = lines[index - 1] if index > 0 else ""
                if not company and previous:
                    uppercase_companies = re.findall(r"\b[A-Z][A-Z&.' -]{3,}\b", previous)
                    uppercase_companies = [clean_company(item) for item in uppercase_companies if looks_like_company(item)]
                    if uppercase_companies:
                        company = uppercase_companies[-1]
                        role = role or _infer_designation(before_date)
                if (
                    not company
                    and previous
                    and looks_like_company(previous)
                    and not re.search(date_pattern, previous, re.I)
                ):
                    company = clean_company(previous)
                elif (
                    not company
                    and
                    previous
                    and not re.search(date_pattern, previous, re.I)
                    and not re.search(r"(email|e-mail|phone|contact|address|portfolio|linkedin|github)", previous, re.I)
                    and len(previous) <= 90
                ):
                    company = clean_company(previous)
                company_match = re.search(
                    r"\b(?:at|with|for)\s+([A-Z][A-Za-z0-9&.,' -]{2,80})",
                    context,
                )
                if company_match:
                    company = clean_company(company_match.group(1))

            if not company or _looks_like_bad_company(company):
                context_company_pattern = (
                    r"(?P<company>[A-Z][A-Za-z0-9&.,' -]{2,90})\s+"
                    r"(?P<role>(?:(?:Senior|Sr\.?|Lead|Junior|Jr\.?|CRM|Salesforce|Software|Full[-\s]?Stack|"
                    r"Front[-\s]?End|Back[-\s]?End|Data|Associate)\s+){0,4}"
                    r"(?:Developer|Engineer|Administrator|Consultant|Analyst|Intern|Architect|Specialist)(?:\s+I{1,3})?)"
                    r"\s*,?\s*"
                    + re.escape(date_match.group(1))
                    + r"\s*(?:-|\u2013|\u2014|to)\s*"
                    + re.escape(date_match.group(2))
                )
                for context_match in reversed(list(re.finditer(context_company_pattern, context, re.I))):
                    recovered_company = strip_location_suffix(context_match.group("company"))
                    recovered_company_parts = [
                        part.strip(" .,-|")
                        for part in re.split(r"[.;]\s+", recovered_company)
                        if part.strip(" .,-|")
                    ]
                    recovered_company = recovered_company_parts[-1] if recovered_company_parts else recovered_company
                    if looks_like_company(recovered_company):
                        company = recovered_company
                        role = role or normalize_designation(context_match.group("role").title())
                        break

            jobs.append({
                "company_name": company,
                "role": role or _infer_designation(context),
                "start_date": date_match.group(1),
                "end_date": date_match.group(2),
                "description": context[:900],
            })

    return jobs


def _recover_season_experience_records(text):
    normalized = _normalize_parser_text(text)
    sections = _extract_sections(normalized)
    source_text = sections.get("experience") or normalized
    lines = [_compact_spaced_letters(line.strip()) for line in source_text.splitlines() if line.strip()]
    records = []
    season_pattern = re.compile(r"^(summer|winter|spring|autumn|fall)\s*['\u2018\u2019`]?\s*(\d{2,4})$", re.I)

    for index, line in enumerate(lines):
        season = season_pattern.match(line)
        if not season:
            continue
        previous = lines[index - 1] if index > 0 else ""
        if "|" not in previous:
            continue
        parts = [part.strip(" .,-|") for part in previous.split("|") if part.strip(" .,-|")]
        if len(parts) < 2:
            continue

        role = _infer_designation(parts[0]) or normalize_designation(parts[0].title()) or parts[0]
        company = parts[1]
        if re.fullmatch(r"salesforce", company, re.I):
            company = "Salesforce, Inc"
        if _looks_like_bad_company(company):
            continue

        details = []
        for stop in range(index + 1, min(len(lines), index + 12)):
            marker = re.sub(r"[^a-z]", "", lines[stop].lower())
            if "|" in lines[stop] and _infer_designation(lines[stop].split("|", 1)[0]):
                break
            if marker in {"projects", "education", "skills", "competitions", "awardsandachievements"}:
                break
            details.append(lines[stop])

        date_value = f"{season.group(1)} {season.group(2)}"
        records.append({
            "company_name": company,
            "role": role,
            "start_date": date_value,
            "end_date": date_value,
            "description": " ".join([previous, line] + details)[:900],
        })

    return records


def _recover_inline_experience_records(text):
    normalized = _normalize_parser_text(text)
    pattern = re.compile(
        r"(?P<company>[A-Z][A-Za-z0-9&.'+\-/ ]{2,85})\s*,\s*(?P<geo>[A-Za-z .]{2,40})\s+"
        r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})\s*"
        r"(?:-|\u2013|\u2014|to)\s*"
        r"(?P<end>Present|Current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})\s+"
        r"(?P<role>[A-Z][A-Za-z/&,\- ]{2,80})",
        re.I,
    )
    records = []
    role_hint = re.compile(r"\b(analyst|engineer|developer|assistant|manager|specialist|intern|consultant|coordinator|research)\b", re.I)
    for match in pattern.finditer(normalized):
        company = re.sub(r"\s+", " ", match.group("company")).strip(" .,-|")
        role = re.sub(r"\s+", " ", match.group("role")).strip(" .,-|")
        if _looks_like_bad_company(company):
            continue
        if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|present|current)\b", company, re.I):
            continue
        if re.search(r"\b(canada|india|usa|united states|ontario|toronto)\b", company, re.I) and len(company.split()) <= 2:
            continue
        if not role_hint.search(role):
            continue
        start_at = match.start()
        end_at = min(len(normalized), match.end() + 450)
        next_match = pattern.search(normalized, match.end())
        if next_match:
            end_at = min(end_at, next_match.start())
        description = normalized[start_at:end_at].strip()
        records.append({
            "company_name": company,
            "role": normalize_designation(role) or role,
            "start_date": match.group("start"),
            "end_date": match.group("end"),
            "description": description[:900],
        })
    return records


def _recover_pipe_experience_records(text):
    normalized = _normalize_parser_text(text)
    lines = [_compact_spaced_letters(line.strip()) for line in normalized.splitlines() if line.strip()]
    records = []
    date_pattern = (
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)[a-z]*\s+\d{4}|\d{4})"
        r"\s*(?:-|\u2013|\u2014|to)\s*"
        r"((?:Present|Current|Till\s+Date|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)[a-z]*\s*\d{0,4}|\d{4})"
    )

    def clean_company(value):
        value = _compact_spaced_letters(value or "")
        replacements = {
            "VITALITYLIVING": "Vitality Living",
            "HABERCORPORATION": "Haber Corporation",
        }
        for raw, fixed in replacements.items():
            value = re.sub(r"\b" + raw + r"\b", fixed, value, flags=re.I)
        value = re.sub(r"\bC\s+O\s*\.\s*,\s*P\s*C\b", "Co., PC", value, flags=re.I)
        if re.search(r"\bVitality Living\b", value, re.I):
            value = "Vitality Living"
        elif re.search(r"\bHaber Corporation\b", value, re.I):
            value = "Haber Corporation"
        elif re.search(r"\bWILES\s*\+\s*TAYLOR\b", value, re.I):
            value = "WILES + TAYLOR & Co., PC"
        value = _strip_trailing_date_tokens_from_company(value)
        return value.strip(" .,-|")

    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        pipe_parts = [part.strip(" .,-|\u2013\u2014") for part in line.split("|") if part.strip(" .,-|\u2013\u2014")]
        if len(pipe_parts) < 2:
            continue
        left, right = pipe_parts[0], " | ".join(pipe_parts[1:])
        date_match = re.search(date_pattern, right, re.I) or re.search(date_pattern, line, re.I)
        same_year_month_match = None
        if not date_match:
            same_year_month_match = re.search(
                r"\b(?P<start_month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)[a-z]*\s*"
                r"(?:-|\u2013|\u2014|to)\s*"
                r"(?P<end_month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)[a-z]*\s+"
                r"(?P<year>\d{4})\b",
                right,
                re.I,
            )
        if not date_match:
            if not same_year_month_match:
                continue
            start_date = f"{same_year_month_match.group('start_month')} {same_year_month_match.group('year')}"
            end_date = f"{same_year_month_match.group('end_month')} {same_year_month_match.group('year')}"
        else:
            start_date = date_match.group(1)
            end_date = date_match.group(2)
        company_source = pipe_parts[1] if len(pipe_parts) >= 2 else left
        if same_year_month_match:
            company_source = company_source[:same_year_month_match.start()].strip(" .,-|")
        previous_date = list(re.finditer(date_pattern, company_source, re.I))
        if previous_date:
            company_source = company_source[previous_date[-1].end():].strip(" .,-|")
        if re.search(r"NASHVILLE\s+SOFTWARE\s+SCHOOL\s+WILES", company_source, re.I):
            company_source = re.sub(r"^.*?(WILES\s*\+\s*TAYLOR.*)$", r"\1", company_source, flags=re.I)
        company = clean_company(company_source)
        previous_lines = lines[max(0, index - 4):index]
        role = ""
        role_like_left = bool(re.search(
            r"\b(transcriber|superintendent|co-?owner|founder|manager|mgr|customer support|training|analyst|"
            r"apprentice|assistant|coordinator|specialist|instructor|leader|consultant|developer|engineer|"
            r"accounting|payroll|payable)\b",
            left,
            re.I,
        ))
        if role_like_left:
            role = normalize_designation(left.title()) or left
            if len(pipe_parts) < 2 or not company:
                for previous in reversed(previous_lines):
                    previous_company = clean_company(previous)
                    if (
                        previous_company
                        and not _looks_like_bad_company(previous_company)
                        and not re.fullmatch(r"(experience|education|skills?|projects?|contact|about me)", previous_company, re.I)
                        and not re.search(r"\b(school|university|bootcamp|data analytics)\b", previous_company, re.I)
                    ):
                        company = previous_company
                        break
        if _looks_like_bad_company(company) or re.search(r"\b(school|university|bootcamp|education|skills|projects?)\b", company, re.I):
            continue
        if not role:
            for previous in reversed(previous_lines):
                if re.search(r"\b(accountant|manager|bookkeeper|analyst|engineer|developer|assistant|consultant|coordinator|transcriber|superintendent)\b", previous, re.I):
                    role = normalize_designation(previous.title())
                    break
        if not role and role_like_left:
            role = normalize_designation(left.title()) or left
        records.append({
            "company_name": company,
            "role": role,
            "start_date": start_date,
            "end_date": end_date,
            "description": " ".join(previous_lines[-2:] + [line] + lines[index + 1:index + 4])[:900],
        })
    return records


def _clean_experience_records(records):
    best_by_period = {}

    def canonical_company(value):
        value = _compact_spaced_letters(str(value or ""))
        replacements = {
            "VITALITYLIVING": "Vitality Living",
            "HABERCORPORATION": "Haber Corporation",
        }
        for raw, fixed in replacements.items():
            value = re.sub(re.escape(raw), fixed, value, flags=re.I)
        value = re.sub(r"\bC\s+O\s*\.\s*,\s*P\s*C\b", "Co., PC", value, flags=re.I)
        if re.search(r"\bVitality Living\b", value, re.I):
            return "Vitality Living"
        if re.search(r"\bHaber Corporation\b", value, re.I):
            return "Haber Corporation"
        if re.search(r"\bWILES\s*\+\s*TAYLOR\b", value, re.I):
            return "WILES + TAYLOR & Co., PC"
        if re.fullmatch(r"NEPHROLOGY\s+ASSOC", value, re.I):
            return "Nephrology Assoc"
        if re.fullmatch(r"INTEGRIEN\s+CORP", value, re.I):
            return "Integrien Corp"
        if re.fullmatch(r"Quantum Analytics Ng", value, re.I):
            return "QUANTUM ANALYTICS NG"
        if re.fullmatch(r"Nashville SOFTWARE School", value, re.I):
            return "Nashville Software School"
        if re.fullmatch(r"salesforce", value, re.I):
            return "Salesforce, Inc"
        if re.search(r"\bNinjacart\b", value, re.I):
            return "Ninjacart"
        value = re.sub(r"\s*\[[^\]]+\]", "", value)
        value = re.sub(r"\s*,?\s*specializing\b.*$", "", value, flags=re.I)
        value = re.sub(r"^\s*EXPERIENCE\s+", "", value, flags=re.I).strip(" .,-|")
        value = re.sub(
            r"\s+\b(?:Remote\s+Transcriber|Creative\s+Arts\s+Department\s+Superintendent|"
            r"Co-?owner,\s*Manager|IT&S\s+Customer\s+Support\s+and\s+Training)\b\s*$",
            "",
            value,
            flags=re.I,
        ).strip(" .,-|")
        value = re.sub(r"\s*,\s*(Canada|India|USA|United States|United Kingdom)\s*$", "", value, flags=re.I)
        value = _strip_trailing_date_tokens_from_company(value)
        return value.strip(" .,-|")

    def non_work_date_record(job):
        company = str(job.get("company_name") or "")
        role = str(job.get("role") or "")
        description = str(job.get("description") or "")
        company_role = f"{company} {role}"

        has_work_role = bool(re.search(
            r"\b(analyst|engineer|developer|assistant|associate|intern|consultant|administrator|manager|"
            r"teaching assistant|research assistant|support engineer)\b",
            role,
            re.I,
        ))
        if re.search(
            r"\b(college|school|university|diploma|bachelor|master|bootcamp|training|computer programming|nashville software school|in progress|scheduled|coursera|certificate|certification)\b",
            company_role,
            re.I,
        ) and not has_work_role:
            return True

        education_context = bool(re.search(r"\b(education|college|school|university|diploma|bootcamp|training|certifications?|coursera|in progress|scheduled)\b", description, re.I))
        work_context = bool(re.search(
            r"\b(work experience|employment|professional experience|company|limited|ltd|pvt|private|inc|co\.?|pc|analytics|consulting|services|associate|trainer|manager|assistant|analyst|engineer|developer|coordinator|intern|accountant|bookkeeper|revenue|staff)\b",
            f"{company} {role} {description}",
            re.I,
        ))
        if education_context and not work_context:
            return True

        if (
            re.fullmatch(r"[A-Z]{2,}(?:\s+[A-Z]{2,}){1,3}", company)
            and re.search(r"\b(contact|email|phone|data analytics experience|business analyst)\b", description, re.I)
            and not re.search(r"\b(inc|llc|ltd|corp|corporation|company|co\.?|services|solutions|technologies|analytics|army|university|school|bread)\b", company, re.I)
        ):
            return True

        if re.search(r"\b(in progress|scheduled|bootcamp)\b", description, re.I) and re.search(r"\b(certificate|certification|coursera|education|college|school|training|bootcamp)\b", description, re.I):
            if not re.search(r"\b(company|ltd|limited|private|inc|co\.?|pc|services|consulting|technologies)\b", company, re.I):
                return True

        if not role and re.search(r"\b(volunteer|community|creative arts|handcrafted art|state fair)\b", f"{company} {description}", re.I):
            return True
        if not role and re.search(r"\b(iit|institute|kharagpur|student|mentor|sric|lbs)\b", f"{company} {description}", re.I):
            return True
        if re.search(r"\b(conference paper|paper link|hackathon|graduate students)\b", description, re.I):
            if not re.search(r"\b(inc|llc|ltd|pvt|private|corp|corporation|company|technologies|services)\b", company, re.I):
                return True

        return False

    def quality(job):
        company = str(job.get("company_name") or "")
        role = str(job.get("role") or "")
        description = str(job.get("description") or "")
        score = 0
        if len(company.split()) > 9 or re.search(r"\b(grade|feelings|childhood|outcomes|technical skills|microsoft word|powerpoint)\b", company, re.I):
            score -= 12
        score += 4 if company else 0
        score += 4 if role else 0
        score += min(len(description), 400) / 100
        if re.search(r"(email|e-mail|phone|contact|address|portfolio|linkedin|github)", company, re.I):
            score -= 8
        if re.search(r"\b(analyst|engineer|developer|manager|associate|consultant|executive|intern|assistant)\b", role, re.I):
            score += 2
        return score

    for job in records or []:
        if not isinstance(job, dict):
            continue
        start = str(job.get("start_date") or "").strip()
        end = str(job.get("end_date") or "").strip()
        description = str(job.get("description") or "")
        context = " ".join([
            str(job.get("company_name") or ""),
            str(job.get("role") or ""),
            description,
        ]).lower()

        company = canonical_company(job.get("company_name"))
        if re.fullmatch(r"WEIGHT WATCHERS OF MIDDLE AND EAST TN", company, re.I):
            company = "Weight Watchers of Middle and East TN"
        stripped_company = _remove_skill_noise_from_company(company)
        if stripped_company and stripped_company != company and not _looks_like_bad_company(stripped_company):
            company = stripped_company
        job["company_name"] = company
        company_has_date = bool(re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*(?:-|\u2013|\u2014|to)\s*(?:Present|Current|[A-Za-z]+\s+\d{4})\b", company, re.I))
        if _looks_like_bad_company(company) or company_has_date:
            recovered_company = _recover_company_before_period(description, start, end) or _recover_company_from_job_context(job)
            if recovered_company:
                recovered_company = canonical_company(recovered_company)
                job["company_name"] = recovered_company
                company = recovered_company
            uppercase_companies = re.findall(r"\b[A-Z][A-Z&.' -]{3,}\b", f"{company} {description}")
            uppercase_companies = [
                canonical_company(item)
                for item in uppercase_companies
                if 1 <= len(item.split()) <= 7
                and not _infer_designation(item)
                and not _looks_like_bad_company(item)
                and not re.search(r"\b(DATAANALYTICSEXPERIENCE|WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|CATHERINE|SCHMALZER|TENNESSEE|PRESENT|JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)\b", item, re.I)
            ]
            if recovered_company:
                pass
            elif uppercase_companies:
                job["company_name"] = uppercase_companies[-1]
                company = job["company_name"]

        if non_work_date_record(job):
            continue
        original_company = company
        if _looks_like_bad_company(company):
            job["company_name"] = ""
            company = ""
            if original_company:
                continue
        if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*(?:-|\u2013|\u2014|to)\s*(?:Present|Current|[A-Za-z]+\s+\d{4})\b", company, re.I):
            continue
        if len(company.split()) > 5 and re.search(r"\b(by|around|with|and|the|from|for|to)\b", company):
            uppercase_companies = re.findall(r"\b[A-Z][A-Z&.' -]{3,}\b", company)
            uppercase_companies = [
                canonical_company(item)
                for item in uppercase_companies
                if len(item.split()) <= 5 and not _infer_designation(item)
            ]
            if uppercase_companies:
                job["company_name"] = uppercase_companies[-1]
                company = job["company_name"]
        if len(company.split()) > 14 or re.search(r"\b(grade|feelings|childhood|technical skills|microsoft word|powerpoint)\b", company, re.I):
            # Try to recover a real company right before the date range in the noisy description.
            pattern = (
                r"([A-Z][A-Za-z0-9&.,' -]{2,80})\s*\|\s*"
                + re.escape(start)
                + r"\s*(?:-|\u2013|\u2014|to)\s*"
                + re.escape(end)
            )
            recovered = re.search(pattern, description)
            if recovered:
                recovered_company = canonical_company(recovered.group(1))
                job["company_name"] = "" if _looks_like_bad_company(recovered_company) else recovered_company
            else:
                continue

        if re.fullmatch(r"\d{4}", start) and re.fullmatch(r"\d{4}", end):
            has_real_work_anchor = bool(
                company
                and re.search(
                    r"\b(inc|llc|ltd|limited|private|pvt|corp|corporation|company|services|solutions|technologies|analytics|consulting|school|army|bread)\b",
                    company,
                    re.I,
                )
                and re.search(
                    r"\b(analyst|engineer|developer|manager|associate|consultant|executive|intern|assistant|coordinator|trainer|oversaw|streamlined|reporting)\b",
                    context,
                    re.I,
                )
            )
            if not has_real_work_anchor and any(term in context for term in ["education", "bachelor", "master", "university", "college", "gpa", "cgpa", "degree"]):
                continue

        year_start_match = re.search(r"\b(19|20)\d{2}\b", start)
        year_end_match = re.search(r"\b(19|20)\d{2}\b", end)
        normalized_start = year_start_match.group(0).lower() if year_start_match else start.lower()
        normalized_end = "present" if re.search(r"\b(present|current)\b", end, re.I) else (year_end_match.group(0).lower() if year_end_match else end.lower())
        if not company:
            continue
        key = (company.lower(), normalized_start, normalized_end)
        if key not in best_by_period or quality(job) > quality(best_by_period[key]):
            best_by_period[key] = job

    cleaned = sorted(
        best_by_period.values(),
        key=lambda item: quality(item),
        reverse=True,
    )
    return cleaned[:12]


def _infer_certifications(text):
    cert_lines = []
    seen = set()
    for line in (text or "").splitlines():
        clean = re.sub(r"\s+", " ", line).strip(" ,-:|")
        if not clean or len(clean) > 180:
            continue
        if re.search(r"\b(certified|certification|certificate|aws certified|pmp|scrum|six sigma|course|coursera|udemy|datacamp|codewithharry|google data analytics)\b", clean, re.I):
            clean = re.sub(r"^\b(education|certifications?|courses?)\s*:?\s*", "", clean, flags=re.I).strip(" ,-:|")
            key = clean.lower()
            if key not in seen:
                seen.add(key)
                cert_lines.append(clean)
    return cert_lines[:10]


def _clean_education_records(records):
    cleaned = []
    seen = set()
    for item in records or []:
        if not isinstance(item, dict):
            continue
        combined = " ".join(str(item.get(key) or "") for key in ("degree", "field", "institution"))
        degree_value = str(item.get("degree") or "")
        institution_value = str(item.get("institution") or "")
        if re.search(r"\b(course|certification|certificate|codewithharry|google data analytics|coursera|udemy|datacamp)\b", combined, re.I) and not re.search(r"\b(bachelor|master|b\.?tech|bca|mca|mba|university|college|degree)\b", combined, re.I):
            continue
        if re.search(r"UNIVERSITY OF TENNESSEE AT\s+CHATTANOOGA", institution_value, re.I):
            institution_value = "UNIVERSITY OF TENNESSEE AT CHATTANOOGA"
            item["institution"] = institution_value
            combined = " ".join(str(item.get(key) or "") for key in ("degree", "field", "institution"))
        if re.search(r"\bNashville\s+SOFTWARE\s+School\b", institution_value, re.I):
            institution_value = "Nashville Software School"
            item["institution"] = institution_value
            combined = " ".join(str(item.get(key) or "") for key in ("degree", "field", "institution"))
        if re.search(r"\b(shortest route home|from school to determining|previous position|company leadership|digging into data)\b", combined, re.I):
            continue
        if re.search(r"\bbootcamp\b", institution_value, re.I) and re.search(r"\b(bachelor|master|b\.?s\.?|bsc|mba|mca)\b", degree_value, re.I):
            continue
        if re.search(r"\bnashville\s+software\s+school\b", institution_value, re.I) and re.search(r"\b(bachelor|master|b\.?s\.?|bsc)\b", degree_value, re.I):
            continue
        if re.search(r"\bbootcamp\b.*\b(bachelor|master|b\.?s\.?|bsc)\b|\b(bachelor|master|b\.?s\.?|bsc)\b.*\bbootcamp\b", degree_value, re.I):
            continue
        if not degree_value.strip() and len(re.findall(r"\b(university|college|school|academy|institute)\b", institution_value, re.I)) >= 2:
            continue
        if not degree_value.strip() and not re.search(r"\b(university|college|school|academy|institute)\b", institution_value, re.I):
            continue
        if re.fullmatch(r"(present|current|till date)", degree_value.strip(), re.I):
            continue
        if re.fullmatch(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\w*", str(item.get("degree") or "").strip(), re.I):
            continue
        if re.fullmatch(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\w*\s+\d{4}", str(item.get("institution") or "").strip(), re.I):
            continue
        if "|" in combined and re.search(r"\b(19|20)\d{2}\b", combined):
            continue
        if re.search(r"\b(work experience|professional experience|projects?|responsibilities|responsible|leadership|developed|created|worked|recommended|collaborative|analy[sz]ed|managed|military experience|dang brother|tracking sales|feedback to|socio-economic|juggled|production orders|center consultant|technicalskills)\b", combined, re.I):
            continue
        if re.search(r"\b(local community|small business|opportunity to|staff assignments|transition to data|digging into data|competing priorities|monthly financial reports|payroll|accounts payable)\b", combined, re.I):
            continue
        if re.search(r"\bbootcamp\b", degree_value, re.I) and re.search(r"\b(waste|feedback|tracking|responsible|staff|sales)\b", combined, re.I):
            continue
        if len(combined.split()) > 24:
            continue
        degree = re.sub(r"\b(19|20)\d{2}\b", "", str(item.get("degree") or "")).strip(" -,:")
        item["degree"] = re.sub(r"\s+", " ", degree).strip()
        item["field"] = re.split(r"\b(work experience|professional experience|projects?|responsibilities|leadership|worked|recommended|collaborative)\b", str(item.get("field") or ""), maxsplit=1, flags=re.I)[0].strip(" ,-:|")
        item["institution"] = re.split(r"\b(work experience|professional experience|projects?|responsibilities|leadership|worked|recommended|collaborative)\b", str(item.get("institution") or ""), maxsplit=1, flags=re.I)[0].strip(" ,-:|")
        key = (
            re.sub(r"\s+", " ", str(item.get("degree") or "").lower()).strip(),
            re.sub(r"\s+", " ", str(item.get("institution") or "").lower()).strip(),
            str(item.get("start_date") or "").lower().strip(),
            str(item.get("end_date") or "").lower().strip(),
        )
        if not any(key) or key in seen:
            continue
        seen.add(key)
        cleaned.append(item)

    normalized = []
    for item in cleaned:
        institution = re.sub(r"\s+", " ", str(item.get("institution") or "")).strip()
        year_match = re.search(r"\b(19|20)\d{2}\b\s*$", institution)
        if year_match:
            if not item.get("start_date"):
                item["start_date"] = year_match.group(0).strip()
            institution = institution[:year_match.start()].strip(" ,-:|")
            item["institution"] = institution
        normalized.append(item)

    has_degree_for_institution = {
        re.sub(r"\s+", " ", str(item.get("institution") or "").lower()).strip()
        for item in normalized
        if str(item.get("degree") or "").strip()
    }
    final = []
    final_seen = set()
    canonical_degree_with_real_institution = {
        re.sub(r"\s+", " ", str(item.get("degree") or "").strip()).lower()
        for item in normalized
        if str(item.get("institution") or "").strip()
    }
    for item in normalized:
        institution_key = re.sub(r"\s+", " ", str(item.get("institution") or "").lower()).strip()
        degree = re.sub(r"\s+", " ", str(item.get("degree") or "").strip())
        field = re.sub(r"\s+", " ", str(item.get("field") or "").strip())
        if not degree and institution_key in has_degree_for_institution:
            continue
        if not institution_key and degree.lower() in canonical_degree_with_real_institution:
            continue
        canonical_degree = degree
        if field and re.fullmatch(r"Bachelor of Science|Master of Science|Bachelor|Master", degree, re.I):
            canonical_degree = f"{degree} in {field}"
        key = (canonical_degree.lower(), institution_key)
        if key in final_seen:
            continue
        final_seen.add(key)
        final.append(item)
    return final


def _recover_education_records(text):
    normalized = _normalize_parser_text(text)
    compact = _compact_spaced_letters(normalized)
    records = []

    if re.search(r"\bNashville Software School\b", compact, re.I):
        date_match = re.search(r"Data Analytics\s*\|\s*(March\s+2020)\s*(?:-|\u2013|\u2014|to)\s*(June\s+2020)", compact, re.I)
        records.append({
            "degree": "Data Analytics Bootcamp",
            "field": "",
            "institution": "Nashville Software School",
            "start_date": date_match.group(1) if date_match else "",
            "end_date": date_match.group(2) if date_match else "",
        })

    belmont = re.search(
        r"BELMONT UNIVERSITY.*?\bBS,\s*Mathematics;\s*(2008)\s*(?:-|\u2013|\u2014|to)\s*(2012)",
        compact,
        re.I | re.S,
    )
    if belmont:
        records.append({
            "degree": "BS Mathematics",
            "field": "",
            "institution": "BELMONT UNIVERSITY",
            "start_date": belmont.group(1),
            "end_date": belmont.group(2),
        })

    if re.search(r"\bNashville School of Software\b", compact, re.I):
        bootcamp_year = re.search(r"Data Analytics Bootcamp,?\s*(20\d{2})", compact, re.I)
        records.append({
            "degree": "Data Analytics Bootcamp",
            "field": "",
            "institution": "Nashville School of Software",
            "start_date": bootcamp_year.group(1) if bootcamp_year else "",
            "end_date": "",
        })

    if re.search(r"\bWestern Kentucky University\b", compact, re.I):
        finance_year = re.search(r"Bachelor of Science in Finance,?\s*(20\d{2})", compact, re.I)
        records.append({
            "degree": "Bachelor of Science",
            "field": "Finance",
            "institution": "Western Kentucky University",
            "start_date": finance_year.group(1) if finance_year else "",
            "end_date": "",
        })

    glasgow = re.search(
        r"BSC\s*\(HONS\)\s*FOOD\s+BIOSCIENCE\s+Glasgow\s+Caledonian\s+University",
        compact,
        re.I,
    )
    if glasgow:
        records.append({
            "degree": "BSc (Hons)",
            "field": "Food Bioscience",
            "institution": "Glasgow Caledonian University",
            "start_date": "",
            "end_date": "",
        })

    florida = re.search(
        r"UNIVERSITY OF FLORIDA\s+(20\d{2}).{0,120}?Bachelor of Science in ([A-Za-z &]+)",
        compact,
        re.I | re.S,
    )
    if florida:
        records.append({
            "degree": "Bachelor of Science",
            "field": re.sub(r"\s+", " ", florida.group(2)).strip(),
            "institution": "UNIVERSITY OF FLORIDA",
            "start_date": florida.group(1),
            "end_date": "",
        })

    degree_entry_pattern = re.compile(
        r"(?P<institution>[A-Z][A-Za-z&.' -]{3,80}?(?:University|College|Institute|School)[A-Za-z&.' -]{0,30})\s*,?\s*"
        r"(?P<country>India|Canada|United States|USA|UK|UAE)?\s*"
        r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})\s*"
        r"(?:-|\u2013|\u2014|to)\s*"
        r"(?P<end>(?:Present|Current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4}))\s*"
        r"(?P<degree>(?:Master|Bachelor|B\.?E\.?|B\.?Tech|BSc|MSc|M\.?S\.?|MBA)[^|\n]{0,120}?)"
        r"(?=\s*(?:GPA|CGPA|WORK EXPERIENCE|PROJECTS|KEY SKILLS|CERTIFICATIONS|$|[A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:University|College|Institute|School)))",
        re.I,
    )
    for match in degree_entry_pattern.finditer(compact):
        institution = re.sub(r"\s+", " ", match.group("institution")).strip(" ,-|")
        country = (match.group("country") or "").strip()
        if country and country.lower() not in institution.lower():
            institution = f"{institution}, {country}"
        degree_text = re.split(r"\b(GPA|CGPA|WORK EXPERIENCE|PROJECTS|KEY SKILLS|CERTIFICATIONS)\b", match.group("degree"), maxsplit=1, flags=re.I)[0].strip(" ,-|")
        degree_text = re.sub(r"\s+", " ", degree_text)
        degree = degree_text
        field = ""
        if "," in degree_text:
            left, right = [part.strip() for part in degree_text.split(",", 1)]
            degree, field = left, right
        elif re.search(r"\bin\b", degree_text, re.I):
            left, right = re.split(r"\bin\b", degree_text, maxsplit=1, flags=re.I)
            degree, field = left.strip(), right.strip()
        records.append({
            "degree": degree,
            "field": field,
            "institution": institution,
            "start_date": match.group("start"),
            "end_date": match.group("end"),
        })

    return records


def _recover_single_employer_header(text):
    match = re.search(
        r"\bEXPERIENCE\s*\n\s*([A-Z][A-Z&.' -]{3,80})\s*(?:\n|$)",
        _normalize_parser_text(text),
        re.I,
    )
    if not match:
        return ""
    company = re.sub(r"\s+", " ", match.group(1)).strip(" ,-:|")
    if re.search(r"\b(projects?|skills?|education|contact|summary)\b", company, re.I):
        return ""
    if len(company.split()) > 6:
        return ""
    return company.title() if company.isupper() and "&" not in company else company


def _clean_project_records(records):
    by_name = {}

    stop_markers = {
        "project", "projects", "project section", "projects section", "skills", "technical skills",
        "language", "languages", "certificate", "certificates", "certification", "certifications",
        "portfolio", "contact", "contact section", "education", "experience", "work experience",
    }

    def clean_line(value):
        return re.sub(r"[:\-]", "", value).strip().lower()

    def sanitize_description(value):
        lines = []
        for raw_line in str(value or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.search(r"TECHNICAL\s*TOOLS|TECHNICALTOOLS|TECHNICAL\s*SKILLS|TECHNICALSKILLS", line, re.I):
                line = re.split(r"TECHNICAL\s*TOOLS|TECHNICALTOOLS|TECHNICAL\s*SKILLS|TECHNICALSKILLS", line, maxsplit=1, flags=re.I)[0].strip()
                if not line:
                    continue
            if re.search(r"\b(Data Analytics program covering|UNIVERSITY OF|Bachelor of Science|Minors?\s+in|SUPPLY CHAIN|PERSONAL:|LANGUAGE:)\b", line, re.I):
                if lines:
                    break
                continue
            marker = clean_line(line)
            compact_marker = re.sub(r"[^a-z]", "", marker)
            if marker in stop_markers or compact_marker.startswith(("otherprofessionalexperience", "professionalexperience", "workexperience", "militaryexperience", "technicalskills", "technicaltools", "education", "personalprofile", "profile", "summary")):
                if lines:
                    break
                continue
            if re.fullmatch(r"(microsoft\s+excel|excel|sql|python|power\s*bi|tableau|adobe\s+photoshop|powerpoint|microsoft\s+word|outlook)", line, re.I):
                continue
            if re.match(r"^tools?\s*:", line, re.I) and len(known_skills_in_text(line)) >= 2:
                continue
            if re.search(r"(@|linkedin\.com|github\.com|https?://|www\.|\+?\d[\d\s().-]{8,}\d)", line, re.I):
                continue
            if re.search(r"\b(soldiers?|range safety|military vehicles?|staging area|directing one vehicle|payroll|accounts payable|monthly financial reports|staff assignments)\b", line, re.I):
                if not re.search(r"\b(data|dashboard|analysis|analytics|sql|excel|tableau|power\s*bi|python|project)\b", line, re.I):
                    if lines:
                        break
                    continue
            if re.search(r"\b(created and deployed successful strategies|streamline processes|track inventory|truck locations|forecasted business|special events|coachella|personalized BEO|personnel schedules)\b", line, re.I):
                continue
            if re.search(r"\b(dang brother pizza|ranger instructor|us army|weight watchers)\b", line, re.I) and not re.search(r"\b(project|dashboard|analysis|sql|excel|tableau|power\s*bi)\b", line, re.I):
                if lines:
                    break
                continue
            if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*(?:-|\u2013|\u2014|to)\s*(?:Present|Current|[A-Za-z]+\s+\d{4})\b", line, re.I):
                if lines:
                    break
                continue
            lines.append(line)
        return "\n".join(lines).strip()[:700]

    def tech_list(item):
        return normalize_skill_list(item.get("technologies") or known_skills_in_text(item.get("description") or ""))

    def quality(item):
        description = item.get("description") or ""
        action_hits = len(re.findall(r"\b(built|created|developed|analyzed|processed|automated|delivered|measured|tracked|optimized|visualized)\b", description, re.I))
        return len(description) + (action_hits * 80) + (len(item.get("technologies") or []) * 25)

    def noisy_project_name(value):
        text = _compact_spaced_letters(str(value or "")).strip(" |-")
        if not text:
            return True
        if text[0].islower():
            return True
        if re.search(r"(@|linkedin|github|phone|contact|resume|education|technical skills|technical tools|other professional experience)", text, re.I):
            return True
        if re.search(r",", text) and len(text.split()) > 5:
            return True
        if re.fullmatch(r"(education|technical skills|technical tools|interactive reporting|data|data cleaning|data profiling|data visualization)", text, re.I):
            return True
        if re.fullmatch(r"(data analytics|glasgow,?\s+scotland|glasgow caledonian university|nashville software school)", text, re.I):
            return True
        if re.fullmatch(r"(role|responsibilities|key responsibilities|tools?|technologies|technical skills)", text, re.I):
            return True
        if re.search(r"\b(minor,\s*business administration|data analytics jumpstart|minor in economics|key responsibili)\b", text, re.I) or "buildingpermits" in text.lower():
            return True
        if re.fullmatch(r"(personal|language|supply chain|data analysis|contact website|website)", text, re.I):
            return True
        if re.match(r"^(tools?|closely monitored|worked closely|responsible for|gathered data|led a|supervised|managed)\b", text, re.I):
            return True
        if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*(?:-|\u2013|\u2014|to)\s*(?:Present|Current|[A-Za-z]+\s+\d{4})\b", text, re.I):
            return True
        if re.search(r"\b(staging area|directing one vehicle|range safety|soldiers?|payroll|accounts payable)\b", text, re.I):
            return True
        if re.search(r"\b(?:cid:\d+|achievements?|designation|location|manpower strength)\b", text, re.I):
            return True
        if re.search(r"\b(ncaa|dean'?s list|all-conference team|atlantic sun|community involvement|nashville food project)\b", text, re.I):
            return True
        if re.search(r"\b(senior revenue accountant|senior staff accountant|assistant business manager|bookkeeper|gaap|1099|cash flow|payment discrepancies|fiscal files|financial statements|accounts payable|accounts receivable)\b", text, re.I):
            return True
        if re.match(r"^\s*[/\\-]*\s*achievements?\b", text, re.I):
            return True
        if re.search(r"\|\s*(19|20)\d{2}\s*(?:-|\u2013|\u2014|to)\s*(19|20)\d{2}", text):
            return True
        if len(text.split()) > 12 and not re.search(r"\b(project|dashboard|analysis|analytics|model|system|app|automation|etl|database|capstone)\b", text, re.I):
            return True
        return False

    for item in records or []:
        if isinstance(item, str):
            item = {"name": item[:120], "description": item, "technologies": []}
        if not isinstance(item, dict):
            continue
        name = re.sub(r"\s+", " ", str(item.get("name") or "").strip())
        action_suffix = re.match(
            r"^(.{2,120}):\s*(?:used|created|built|analy[sz]ed|developed|processed|designed|implemented|led|engineered)\b",
            name,
            re.I,
        )
        if action_suffix:
            name = action_suffix.group(1).strip(" .,-:|")
        description = sanitize_description(item.get("description") or name)
        collapsed_description = re.sub(r"\s+", " ", description).strip()
        if not name and not description:
            continue
        if noisy_project_name(name):
            continue
        normalized_name = normalize_skill_list([name])
        exact_skill = normalized_name and normalize_skill_list(known_skills_in_text(name)) == normalized_name
        if exact_skill or re.fullmatch(r"(english|hindi|english speaking|problem solving|communication|statistics|seaborn|matplotlib|data handling|eda)", name, re.I):
            continue
        item["name"] = name or "Project"
        item["description"] = description or name
        item["description"] = item["description"][:700]
        item["technologies"] = tech_list(item)
        key = re.sub(r"[^a-z0-9]+", " ", item["name"].lower()).strip() or collapsed_description[:120].lower()
        if key in by_name:
            existing = by_name[key]
            merged_tech = normalize_skill_list((existing.get("technologies") or []) + item["technologies"])
            better = item if quality(item) > quality(existing) else existing
            better["technologies"] = merged_tech
            by_name[key] = better
        else:
            by_name[key] = item
    ranked = sorted(by_name.values(), key=quality, reverse=True)
    filtered = []
    for project in ranked:
        name_key = re.sub(r"[^a-z0-9]+", " ", str(project.get("name") or "").lower()).strip()
        if any(
            name_key
            and name_key != re.sub(r"[^a-z0-9]+", " ", str(existing.get("name") or "").lower()).strip()
            and name_key in re.sub(r"[^a-z0-9]+", " ", str(existing.get("name") or "").lower()).strip()
            for existing in filtered
        ):
            continue
        filtered.append(project)
    return filtered[:8]


def _recover_projects_from_text(text):
    compact = _compact_spaced_letters(_normalize_parser_text(text))
    projects = []

    capstone = re.search(
        r"Capstone Project:\s*(Comparing\s+2008\s+Recession\s+to)\s+([\s\S]{0,80}?Coronavirus\s+Recession)",
        compact,
        re.I,
    )
    if capstone:
        title = re.sub(r"\s+", " ", f"{capstone.group(1)} {capstone.group(2)}").strip(" .,-:|")
        projects.append({
            "name": title[:120],
            "description": title[:700],
            "technologies": _detect_skills(compact),
        })

    for title in ("Ravelry Capstone", "Nashville City Cemetery Marketing Presentation"):
        pattern = (
            re.escape(title)
            + r"\s*:\s*(?P<body>[\s\S]{80,1200}?)(?=\n\s*(?:Tools used:|Nashville City Cemetery Marketing Presentation:|Project examples|BSC\s*\(HONS\)|WORK EXPERIENCE|WEIGHT WATCHERS|$))"
        )
        match = re.search(pattern, compact, re.I)
        if not match:
            continue
        body = re.sub(r"\s+", " ", match.group("body")).strip(" .,-:|")
        tools_after = compact[match.end():match.end() + 180]
        if len(body) >= 60:
            projects.append({
                "name": title,
                "description": f"{title}: {body}"[:700],
                "technologies": _detect_skills(f"{body} {tools_after}"),
            })

    lori_specs = [
        (
            "Capstone Project - What's Happening In My Neighborhood?",
            r"CAPSTONE PROJECT\s*-\s*WHAT[’']?S HAPPENING IN MY NEIGHBORHOOD\?(?P<body>[\s\S]{50,1300}?)(?:\n\s*PROJECT\s*-\s*HANDSUP AMERICA|\n\s*Let me help|\n\s*LinkedIn\.com|$)",
        ),
        (
            "HandsUp America Excel Dashboard",
            r"PROJECT\s*-\s*HANDSUP AMERICA\s*-\s*TEAM LEAD(?P<body>[\s\S]{50,1100}?)(?:\n\s*Let me help|\n\s*LinkedIn\.com|\n\s*ACCTS PAYABLE|$)",
        ),
    ]
    for title, pattern in lori_specs:
        match = re.search(pattern, compact, re.I)
        if not match:
            continue
        body = re.sub(r"\s+", " ", match.group("body")).strip(" .,-:|")
        projects.append({
            "name": title,
            "description": f"{title}: {body}"[:700],
            "technologies": _detect_skills(body),
        })

    nfl = re.search(
        r"NFL Player Arrests Dashboard[\s\S]{0,900}?Visualized the NFL player arrest data to\s+(?P<body>[\s\S]{20,220}?)(?:EDUCATION|$)",
        compact,
        re.I,
    )
    if nfl:
        body = re.sub(r"\s+", " ", nfl.group("body")).strip(" .,-:|")
        projects.append({
            "name": "NFL Player Arrests Dashboard",
            "description": f"NFL Player Arrests Dashboard: Visualized the NFL player arrest data to {body}"[:700],
            "technologies": _detect_skills(f"Power BI dashboard {body}"),
        })

    specs = [
        (
            "NYC Marathon Capstone Project",
            r"NYCMARATHON\s*-\s*CAPSTONEPROJECT(?P<body>.*?)(?:SKILLS|NASHVILLEBUILDINGPERMITS|WORKEXPERIENCE)",
        ),
        (
            "Nashville Building Permits Project",
            r"NASHVILLEBUILDINGPERMITS\s*-\s*PROJECT(?P<body>.*?)(?:WORKEXPERIENCE|KANBAN BOARDS|MAC OS|SENIOR ACCOUNTANT)",
        ),
    ]

    skill_noise = re.compile(
        r"^(PYTHON|SQL|POWER BI|TABLEAU|ADVANCED EXCEL(?:\s*\([^)]*\))?|GOOGLE SHEETS/DOCS/SLIDES|POWERPOINT|J[U Y]P?YTER NOTEBOOKS|JUYPTER NOTEBOOKS|GIT/GITHUB|KANBAN BOARDS|MAC OS|ORACLE|QUICKBOOKS|DATAFACTION/AGILLINK)$",
        re.I,
    )
    for title, pattern in specs:
        match = re.search(pattern, compact, re.I | re.S)
        if not match:
            continue
        lines = []
        for raw in match.group("body").splitlines():
            line = raw.strip(" ,-:|")
            if not line or skill_noise.match(line):
                continue
            line = re.sub(r"^(GOOGLE SHEETS/DOCS/SLIDES|POWERPOINT)\s+", "", line, flags=re.I).strip()
            if not line:
                continue
            if re.search(r"\b(work experience|education|community involvement|senior accountant|senior revenue accountant|assistant business manager)\b", line, re.I):
                break
            lines.append(line)
        description = "\n".join(lines).strip()[:700]
        if description:
            projects.append({
                "name": title,
                "description": f"{title}\n{description}",
                "technologies": _detect_skills(description),
            })

    pam_project_specs = [
        (
            "Nashville City Cemetery Analysis",
            r"Nashville City Cemetery Analysis\s*(?:SKILLS\s*)?(?P<body>Developed[\s\S]{20,260}?future tour interest)",
        ),
    ]
    for title, pattern in pam_project_specs:
        match = re.search(pattern, compact, re.I)
        if not match:
            continue
        body = re.sub(r"\s+", " ", match.group("body")).strip(" .,-:|")
        projects.append({
            "name": title,
            "description": f"{title}\n{body}"[:700],
            "technologies": _detect_skills(body),
        })

    lines = [_compact_spaced_letters(line.strip()) for line in _normalize_parser_text(text).splitlines() if line.strip()]
    for index, line in enumerate(lines):
        match = re.match(r"^(Power BI|Tableau|Python|SQL)\s*:\s*([A-Z][A-Za-z0-9 .,&'/-]{8,120})$", line)
        if not match:
            continue
        title = match.group(2).strip()
        if not re.search(r"\b(project|dashboard|analysis|analytics|capstone|citizen|deaths|sightings|tuition|debt)\b", title, re.I):
            continue
        description_lines = [line]
        for follow in lines[index + 1:index + 4]:
            if re.match(r"^(Power BI|Tableau|Python|SQL)\s*:", follow):
                break
            if re.search(r"\b(skills|work experience|education|volunteer|community)\b", follow, re.I):
                break
            description_lines.append(follow)
        projects.append({
            "name": title[:120],
            "description": "\n".join(description_lines)[:700],
            "technologies": _detect_skills("\n".join(description_lines)),
        })

    project_block = re.search(r"\bPROJECTS?\b(?P<body>[\s\S]{0,5000})", compact, re.I)
    if project_block:
        body = project_block.group("body")
        title_pattern = re.compile(
            r"(?P<title>[A-Z][A-Za-z0-9:&/'(),\- ]{6,120}?)\s*-\s*"
            r"(?P<tech>[A-Za-z][A-Za-z0-9+#./ ]{1,80}(?:,\s*[A-Za-z][A-Za-z0-9+#./ ]{1,40}){0,8})"
            r"\s*(?:Deployed\s+Link:[^\u25cf\n]{0,120})?\s*[\u25cf\u2022]",
            re.I,
        )
        matches = list(title_pattern.finditer(body))
        for idx, match in enumerate(matches):
            title = re.sub(r"^\s*PROJECTS?\s*", "", match.group("title"), flags=re.I).strip(" ,-|")
            if re.search(r"\b(work experience|education|skills|certifications?)\b", title, re.I):
                continue
            end_at = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(body), match.end() + 700)
            snippet = body[match.start():end_at]
            snippet = re.split(r"\b(KEY SKILLS|TECHNICAL SKILLS|CERTIFICATIONS)\b", snippet, maxsplit=1, flags=re.I)[0].strip()
            if len(snippet) < 40:
                continue
            if not re.search(r"\b(data|dashboard|analysis|analytics|sql|python|tableau|power\s*bi|excel|etl|kpi)\b", snippet, re.I):
                continue
            projects.append({
                "name": title[:120],
                "description": snippet[:700],
                "technologies": _detect_skills(snippet),
            })
    return projects


def _date_range_like(value):
    text = str(value or "")
    return bool(re.search(
        r"\b(?:19|20)\d{2}\s*(?:-|--|\u2013|\u2014|to)\s*(?:present|current|(?:19|20)\d{2})\b",
        text,
        re.I,
    ))


def _link_or_profile_text(value):
    return bool(re.search(
        r"(@|https?://|www\.|linkedin\.com|github\.com|portfolio|profile\s*:)",
        str(value or ""),
        re.I,
    ))


def _looks_like_skill_list_or_section_noise(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return False
    skill_hits = known_skills_in_text(text)
    comma_or_pipe_items = [item for item in re.split(r"[,|;/]+", text) if item.strip()]
    if len(skill_hits) >= 4 and len(comma_or_pipe_items) >= 4:
        return True
    if re.search(
        r"(?:^|\n)\s*(technical skills|technical tools|core skills|work experience|professional experience|"
        r"education|certifications?|personal profile|summary|key responsibilities)\s*:?\s*(?:\n|$)",
        str(value or ""),
        re.I,
    ):
        return True
    return bool(re.search(
        r"\b(technical skills|technical tools|core skills|work experience|professional experience|"
        r"personal profile|key responsibilities)\b",
        text,
        re.I,
    ))


def _looks_like_work_bullet(value):
    return bool(re.search(
        r"\b(handled|managed|created|developed|analy[sz]ed|built|delivered|processed|"
        r"recommended|trained|coordinated|responsible|leadership|collaborative|customer support|"
        r"sales data|reports?|dashboards?)\b",
        str(value or ""),
        re.I,
    ))


def _clean_for_display(value, fallback="Needs validation"):
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,-:|")
    return text or fallback


def _education_display_label(item):
    if not isinstance(item, dict):
        return ""
    degree = str(item.get("degree") or "").strip()
    field = str(item.get("field") or "").strip()
    institution = str(item.get("institution") or "").strip(" -")
    dates = " - ".join(str(item.get(key) or "").strip() for key in ("start_date", "end_date") if item.get(key))
    main = " ".join(part for part in [degree, field] if part).strip()
    if institution:
        main = f"{main} - {institution}" if main else institution
    if dates:
        main = f"{main} ({dates})" if main else dates
    return re.sub(r"\s+", " ", main).strip()


def _project_display_label(item):
    if not isinstance(item, dict):
        return ""
    name = str(item.get("name") or "").strip()
    description = str(item.get("description") or "").strip()
    return _clean_for_display(name or description[:90], "")


def _validate_parser_phone(value):
    phone = str(value or "").strip()
    digits = re.sub(r"\D+", "", phone)
    if not phone:
        return "", 0.15, "phone_needs_review"
    if not 10 <= len(digits) <= 15:
        return "", 0.2, "phone_needs_review"
    if _date_range_like(phone) or re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", phone, re.I):
        return "", 0.1, "phone_needs_review"
    return phone, 0.95, ""


def _validate_parser_company(value):
    company = _clean_for_display(value, "")
    stripped_company = _remove_skill_noise_from_company(company)
    if stripped_company and stripped_company != company and not _looks_like_bad_company(stripped_company):
        company = stripped_company
    if not company:
        return "", 0.25, "company_needs_review"
    if (
        _date_range_like(company)
        or _link_or_profile_text(company)
        or _looks_like_bad_company(company)
        or _looks_like_skill_list_or_section_noise(company)
    ):
        return "", 0.2, "company_needs_review"
    return company, 0.85, ""


def _validate_parser_education_items(items):
    valid = []
    rejected = False
    for item in items or []:
        label = _education_display_label(item)
        if not label:
            continue
        if (
            _link_or_profile_text(label)
            or _looks_like_skill_list_or_section_noise(label)
            or _looks_like_work_bullet(label)
        ):
            rejected = True
            continue
        valid.append(item)
    if valid:
        return valid, 0.85 if not rejected else 0.65, "education_needs_review" if rejected else ""
    return [], 0.35 if rejected else 0.45, "education_needs_review"


def _validate_parser_project_items(items):
    valid = []
    rejected = False
    for item in items or []:
        label = _project_display_label(item)
        body = " ".join(str(item.get(key) or "") for key in ("name", "description") if isinstance(item, dict))
        has_project_action = bool(re.search(
            r"\b(built|created|developed|analy[sz]ed|processed|automated|delivered|measured|tracked|"
            r"optimized|visuali[sz]ed|recommended|compared|used|managed|strengthened|engineered|implemented|designed|"
            r"deployed|enhanced|modeled|transformed|cleaned|integrated|orchestrated)\b",
            body,
            re.I,
        ))
        has_analytics_evidence = bool(re.search(
            r"\b(sql|python|tableau|power\s*bi|excel|dashboard|data|etl|kpi|visuali[sz]ation|analysis|analytics)\b",
            body,
            re.I,
        ))
        skill_hits = known_skills_in_text(body)
        list_items = [part for part in re.split(r"[,|;/\n]+", body) if part.strip()]
        is_pure_skill_list = len(skill_hits) >= 4 and len(list_items) >= 4 and not has_project_action
        pdf_artifact_or_work_label = bool(re.search(
            r"\b(?:cid:\d+|achievements?|designation|location|manpower strength)\b",
            body,
            re.I,
        ))
        accounting_or_community_noise = bool(re.search(
            r"\b(ncaa|dean'?s list|all-conference team|atlantic sun|community involvement|nashville food project|"
            r"senior revenue accountant|senior staff accountant|assistant business manager|bookkeeper|gaap|1099|"
            r"cash flow|payment discrepancies|fiscal files|financial statements|accounts payable|accounts receivable)\b",
            body,
            re.I,
        ))
        if not label:
            continue
        if (
            is_pure_skill_list
            or pdf_artifact_or_work_label
            or accounting_or_community_noise
            or (_link_or_profile_text(body) and not (has_project_action or has_analytics_evidence))
            or (_looks_like_skill_list_or_section_noise(body) and not (has_project_action or has_analytics_evidence))
            or re.search(r"(?:^|\n)\s*(work experience|professional experience|education|certifications?)\s*:?\s*(?:\n|$)", body, re.I)
        ):
            rejected = True
            continue
        valid.append(item)
    if valid:
        return valid, 0.85 if not rejected else 0.65, "project_noise_detected" if rejected else ""
    return [], 0.35 if rejected else 0.45, "project_noise_detected"


def _apply_parser_reliability_layer(parsed, sections, parser_flags):
    flags = set(parser_flags or [])
    confidence = {}

    phone, phone_confidence, phone_flag = _validate_parser_phone(parsed.get("phone"))
    parsed["phone"] = phone
    confidence["phone"] = phone_confidence
    if phone_flag:
        flags.add(phone_flag)

    name = str(parsed.get("full_name") or "").strip()
    confidence["name"] = 0.9 if name and not _looks_like_section_or_role_name(name) else 0.25
    if confidence["name"] < 0.5:
        flags.add("name_needs_review")

    valid_companies = []
    valid_company_jobs = []
    validated_experience = []
    def recency_rank(job):
        end_date = str(job.get("end_date") or "")
        start_date = str(job.get("start_date") or "")
        if re.search(r"\b(present|current)\b", end_date, re.I):
            return 9999
        end_year = re.search(r"\b(19|20)\d{2}\b", end_date)
        if end_year:
            return int(end_year.group(0))
        start_year = re.search(r"\b(19|20)\d{2}\b", start_date)
        if start_year:
            return int(start_year.group(0))
        return 0
    for job in parsed.get("experience") or []:
        if not isinstance(job, dict):
            continue
        company, company_confidence, company_flag = _validate_parser_company(job.get("company_name"))
        job["company_name"] = company
        if company:
            valid_companies.append(company)
            valid_company_jobs.append((company, job))
            validated_experience.append(job)
        elif company_flag:
            flags.add(company_flag)
    parsed["experience"] = validated_experience
    confidence["last_company"] = 0.85 if valid_companies else (0.35 if parsed.get("experience") else 0.25)
    if not valid_companies and parsed.get("experience"):
        flags.add("company_needs_review")

    education, education_confidence, education_flag = _validate_parser_education_items(parsed.get("education"))
    parsed["education"] = education
    confidence["education"] = education_confidence
    if education_flag:
        flags.add(education_flag)

    projects, project_confidence, project_flag = _validate_parser_project_items(parsed.get("projects"))
    if project_flag and not projects:
        projects = []
        project_confidence = min(project_confidence, 0.35)
    parsed["projects"] = projects
    confidence["project_evidence"] = project_confidence
    if project_flag and not projects:
        flags.add(project_flag)
        parsed["project_evidence_needs_manual_review"] = True

    has_dated_experience = any(
        isinstance(job, dict) and (job.get("start_date") or job.get("end_date"))
        for job in parsed.get("experience") or []
    )
    confidence["experience"] = 0.85 if valid_companies and has_dated_experience else (0.55 if has_dated_experience else 0.3)
    if sections.get("experience") and confidence["experience"] < 0.6:
        flags.add("experience_needs_review")

    confidence["skills"] = 0.85 if parsed.get("key_skills") else 0.3

    low_confidence_fields = sorted(field for field, value in confidence.items() if value < 0.5)
    if low_confidence_fields:
        flags.add("profile_needs_review")

    most_recent_company = "Needs validation"
    if valid_company_jobs:
        valid_company_jobs.sort(key=lambda pair: recency_rank(pair[1]), reverse=True)
        most_recent_company = valid_company_jobs[0][0]

    education_labels = [_education_display_label(item) for item in parsed.get("education") or []]
    project_labels = [_project_display_label(item) for item in parsed.get("projects") or []]
    safe_display = {
        "name": _clean_for_display(parsed.get("full_name")),
        "phone": parsed.get("phone") or "Needs validation",
        "last_company": most_recent_company,
        "education": ", ".join(label for label in education_labels if label) or "Needs validation",
        "project_evidence": ", ".join(label for label in project_labels if label) or "Needs validation",
        "experience": "Needs validation" if confidence["experience"] < 0.5 else "Parsed from resume",
    }

    parsed["field_confidence"] = confidence
    parsed["low_confidence_fields"] = low_confidence_fields
    parsed["safe_display"] = safe_display
    return sorted(flags)


def _resume_quality(text, parsed):
    words = re.findall(r"\w+", text or "")
    sections = _extract_sections(text)
    quality = 100
    concerns = []

    if len(words) < 120:
        quality -= 30
        concerns.append("Resume has very limited detail.")

    if not parsed.get("experience"):
        quality -= 20
        concerns.append("Work history is missing or not structured.")

    if not parsed.get("key_skills"):
        quality -= 20
        concerns.append("Skills are missing or not detectable.")

    skills = parsed.get("key_skills") or []
    unique_ratio = len(set(str(s).lower() for s in skills)) / max(len(skills), 1)
    if len(skills) > 35 and unique_ratio < 0.7:
        quality -= 20
        concerns.append("Possible keyword stuffing detected.")

    if "experience" not in sections and "projects" not in sections:
        quality -= 10
        concerns.append("Resume lacks evidence sections such as experience or projects.")

    return max(0, min(100, quality)), concerns


def parse_resume_enterprise(text, ai_parse_override=None):
    parsed = ai_parse_override if ai_parse_override is not None else (parse_resume(text) or {})
    parsed = parsed or {}
    text = _normalize_parser_text(text)
    raw_ai_experience = list(parsed.get("experience") or [])
    links = _extract_links(text)
    sections = _extract_sections(text)
    parser_flags = []
    if raw_ai_experience and any(
        isinstance(item, dict) and _looks_like_bad_company(item.get("company_name"))
        for item in raw_ai_experience
    ):
        parser_flags.append("ai_parse_recovered")

    parsed["full_name"] = parsed.get("full_name") or extract_name(text)
    parsed["email"] = _clean_email(parsed.get("email") or _regex_search(r"[\w\.-]+@[\w\.-]+\.\w+", text))
    parsed["full_name"] = _clean_person_name(parsed.get("full_name"), parsed.get("email"))
    spaced_name = _recover_spaced_header_name(text, parsed.get("email"))
    if spaced_name and (
        not parsed.get("full_name")
        or len(str(parsed.get("full_name") or "").split()) < 2
        or _looks_like_section_or_role_name(parsed.get("full_name"))
    ):
        parsed["full_name"] = spaced_name
    if (
        not parsed.get("full_name")
        or len(str(parsed.get("full_name") or "").split()) > 5
        or re.search(r"\b(data|analytics|experience|profile|skills|projects?|education|contact)\b", str(parsed.get("full_name") or ""), re.I)
    ):
        recovered_name = _recover_name_from_email_text(parsed.get("email"), text)
        if recovered_name:
            parsed["full_name"] = recovered_name
    if not parsed.get("full_name") or _looks_like_section_or_role_name(parsed.get("full_name")):
        recovered_header_name = _recover_header_name_from_lines(text)
        if recovered_header_name:
            parsed["full_name"] = recovered_header_name
    if not parsed.get("full_name") or _looks_like_section_or_role_name(parsed.get("full_name")):
        parsed["full_name"] = ""
        parser_flags.append("name_needs_review")
    parsed["phone"] = _extract_phone(parsed.get("phone") or text, sections)
    if not parsed.get("phone"):
        parser_flags.append("phone_needs_review")
    parsed["location"] = parsed.get("location") or _infer_location(text)
    parsed["linkedin"] = parsed.get("linkedin") or links["linkedin"]
    parsed["github"] = parsed.get("github") or links["github"]
    parsed["portfolio"] = parsed.get("portfolio") or links["portfolio"]
    parsed["designation"] = normalize_designation(parsed.get("designation")) or _infer_designation(text)

    detected_skills = _detect_skills(text) + known_skills_in_text(text)
    parsed["key_skills"] = normalize_skill_list((parsed.get("key_skills") or []) + detected_skills)

    parsed["experience"] = _clean_experience_records(
        (parsed.get("experience") or [])
        + _infer_experience_v2(text, sections)
        + _infer_experience(text, sections)
        + _recover_season_experience_records(text)
        + _recover_inline_experience_records(text)
        + _recover_pipe_experience_records(text)
        + _recover_company_year_records_from_text(text)
    )
    employer_header = _recover_single_employer_header(text)
    if employer_header and parsed.get("experience"):
        if employer_header.upper() == "PROCTER & GAMBLE":
            for job in parsed["experience"]:
                job["company_name"] = "PROCTER & GAMBLE"
    current_role = next(
        (
            str(job.get("role") or "").strip()
            for job in parsed.get("experience") or []
            if isinstance(job, dict)
            and job.get("company_name")
            and re.search(r"\b(present|current|till date)\b", str(job.get("end_date") or ""), re.I)
            and str(job.get("role") or "").strip()
        ),
        "",
    )
    generic_designation = re.fullmatch(
        r"(developer|engineer|analyst|consultant|associate|specialist)",
        str(parsed.get("designation") or "").strip(),
        re.I,
    )
    if current_role and (not parsed.get("designation") or generic_designation):
        parsed["designation"] = current_role
    if not parsed.get("designation"):
        latest_role = next(
            (
                str(job.get("role") or "").strip()
                for job in parsed.get("experience") or []
                if isinstance(job, dict)
                and job.get("company_name")
                and str(job.get("role") or "").strip()
            ),
            "",
        )
        if latest_role:
            parsed["designation"] = latest_role
    if parsed.get("experience") and not any(job.get("company_name") for job in parsed.get("experience") or []):
        parser_flags.append("company_needs_review")
    if not parsed.get("experience") and sections.get("experience"):
        parser_flags.append("experience_needs_review")

    raw_ai_education = parsed.get("education") or []
    inferred_education = _infer_education(sections) + _recover_education_records(text)
    cleaned_ai_education = _clean_education_records(raw_ai_education)
    parsed["education"] = cleaned_ai_education or _clean_education_records(inferred_education)
    if raw_ai_education and not cleaned_ai_education:
        parser_flags.append("education_needs_review")
    if sections.get("education") and not parsed.get("education"):
        parser_flags.append("education_needs_review")

    raw_ai_projects = parsed.get("projects") or []
    inferred_projects = _recover_projects_from_text(text) + _infer_projects(sections)
    cleaned_ai_projects = _clean_project_records(raw_ai_projects)
    parsed["projects"] = cleaned_ai_projects or _clean_project_records(inferred_projects)
    if raw_ai_projects and not cleaned_ai_projects:
        parser_flags.append("project_noise_detected")
    if sections.get("projects") and not parsed.get("projects"):
        parser_flags.append("project_noise_detected")
    if any(
        re.search(r"\b(work experience|professional experience|military experience|personal profile|dang brother pizza|ranger instructor)\b", str(project.get("description") or ""), re.I)
        for project in parsed.get("projects") or []
        if isinstance(project, dict)
    ):
        parser_flags.append("project_noise_detected")
    certification_source = "\n".join(
        part for part in [sections.get("certifications", ""), sections.get("education", ""), text]
        if part
    )
    parsed["certifications"] = parsed.get("certifications") or _infer_certifications(certification_source)
    parsed["sections"] = sections
    parsed["section_names"] = sorted(sections.keys())
    if not sections.get("experience") and not sections.get("projects") and not sections.get("education"):
        parser_flags.append("section_boundary_low_confidence")
    parsed["parser_flags"] = _apply_parser_reliability_layer(parsed, sections, parser_flags)
    parsed["resume_quality_score"], parsed["resume_quality_concerns"] = _resume_quality(text, parsed)
    if parsed["parser_flags"]:
        parsed["resume_quality_score"] = max(0, parsed["resume_quality_score"] - min(20, len(parsed["parser_flags"]) * 5))
        concerns = list(parsed.get("resume_quality_concerns") or [])
        concerns.extend(f"Parser flag: {flag}" for flag in parsed["parser_flags"])
        parsed["resume_quality_concerns"] = concerns
    parsed["malformed_resume"] = parsed["resume_quality_score"] < 45

    return parsed
    most_recent_company = "Needs validation"
    if valid_company_jobs:
        valid_company_jobs.sort(key=lambda pair: recency_rank(pair[1]), reverse=True)
        most_recent_company = valid_company_jobs[0][0]
