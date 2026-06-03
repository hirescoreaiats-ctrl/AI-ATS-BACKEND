import re

from backend.services.role_taxonomy import detect_role_family, dynamic_core_groups
from backend.services.taxonomy import expand_skill_requirements, known_skills_in_text, normalize_skill_list


SENIORITY_PATTERNS = [
    ("architect", r"\b(architect|principal)\b"),
    ("manager", r"\b(manager|head|leadership|people\s+management)\b"),
    ("lead", r"\b(lead|team\s+lead|tech\s+lead)\b"),
    ("senior", r"\b(senior|sr\.?)\b"),
    ("intern", r"\b(intern|internship|trainee)\b"),
    ("junior", r"\b(junior|jr\.?|fresher|entry[-\s]?level)\b"),
    ("mid-level", r"\b(mid[-\s]?level|associate)\b"),
]


def _as_list(value):
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n|]+", value) if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _first_text(*values):
    for value in values:
        if value:
            return str(value).strip()
    return ""


def _experience_range(jd_text="", jd_data=None):
    jd_data = jd_data or {}
    min_years = jd_data.get("min_experience_years")
    max_years = jd_data.get("max_experience_years")
    text = " ".join([
        str(jd_text or ""),
        str(jd_data.get("experience_required") or ""),
        str(jd_data.get("experience") or ""),
    ])

    range_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:-|\u2013|\u2014|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
        text,
        re.I,
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        min_years = min_years if min_years is not None else min(low, high)
        max_years = max_years if max_years is not None else max(low, high)

    min_match = re.search(
        r"\b(?:minimum|min|at\s+least)\s+(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
        text,
        re.I,
    )
    if min_match and min_years is None:
        min_years = float(min_match.group(1))

    plus_match = re.search(r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b", text, re.I)
    if plus_match and min_years is None:
        min_years = float(plus_match.group(1))

    return float(min_years or 0), float(max_years or 0)


def _seniority(role_title="", jd_text="", min_years=0):
    text = f"{role_title or ''} {jd_text or ''}".lower()
    for level, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, text, re.I):
            return level
    if min_years >= 8:
        return "lead"
    if min_years >= 5:
        return "senior"
    if min_years >= 2:
        return "mid-level"
    if min_years > 0:
        return "junior"
    return "unknown"


def _requirement_lines(jd_text=""):
    hard = []
    soft = []
    for raw in re.split(r"[\n\r]+", jd_text or ""):
        line = re.sub(r"\s+", " ", raw).strip(" -:;")
        if not line:
            continue
        lowered = line.lower()
        if re.search(r"\b(must|required|mandatory|min(?:imum)?|should have|need(?:ed)?)\b", lowered):
            hard.append(line[:220])
        elif re.search(r"\b(preferred|nice to have|good to have|plus|communication|team|stakeholder)\b", lowered):
            soft.append(line[:220])
    return hard[:10], soft[:10]


def _responsibility_signals(jd_text=""):
    patterns = [
        "develop", "design", "implement", "maintain", "analyze", "report", "dashboard",
        "deploy", "monitor", "support", "sell", "source", "screen", "onboard",
        "reconcile", "audit", "manage", "coordinate", "troubleshoot",
    ]
    found = []
    text = (jd_text or "").lower()
    for word in patterns:
        if re.search(r"\b" + re.escape(word) + r"\w*\b", text):
            found.append(word)
    return found[:12]


def build_jd_profile(jd_text, jd_data=None, jd_skills=None):
    jd_data = jd_data or {}
    role_title = _first_text(jd_data.get("role"), jd_data.get("job_title"), jd_data.get("title"))
    required_skills = expand_skill_requirements(jd_skills or _as_list(jd_data.get("required_skills")))
    nice_skills = expand_skill_requirements(
        _as_list(jd_data.get("preferred_skills") or jd_data.get("nice_to_have_skills"))
    )

    inferred_from_text = known_skills_in_text(jd_text or "")
    must_have = normalize_skill_list(required_skills or inferred_from_text)
    nice_to_have = normalize_skill_list([skill for skill in nice_skills if skill.lower() not in {item.lower() for item in must_have}])

    family_text = " ".join([role_title, jd_text or "", " ".join(must_have), " ".join(nice_to_have)])
    role_family, role_family_confidence = detect_role_family(family_text, must_have + nice_to_have)
    min_years, max_years = _experience_range(jd_text, jd_data)
    seniority = _seniority(role_title, jd_text, min_years)
    hard, soft = _requirement_lines(jd_text)

    return {
        "role_title": role_title,
        "role_family": role_family,
        "role_family_confidence": role_family_confidence,
        "seniority_level": seniority,
        "min_experience_years": min_years,
        "max_experience_years": max_years,
        "must_have_skills": must_have,
        "nice_to_have_skills": nice_to_have,
        "core_skill_groups": dynamic_core_groups(role_family, must_have, jd_text or ""),
        "responsibility_signals": _responsibility_signals(jd_text or ""),
        "domain_context": role_family if role_family != "other" else "",
        "hard_requirements": hard,
        "soft_requirements": soft,
    }
