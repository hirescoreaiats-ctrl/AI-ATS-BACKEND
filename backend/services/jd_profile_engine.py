import hashlib
import json
import re

from backend.services.role_taxonomy import detect_role_family, dynamic_core_groups, role_family_default_must_have, role_family_default_nice_to_have
from backend.services.taxonomy import SKILL_CATEGORIES, expand_skill_requirements, known_skills_in_text, normalize_skill_list


JD_PROFILE_VERSION = "jd_profile_v3_dual_mode"

BUSINESS_ANALYST_RESPONSIBILITY_SIGNALS = [
    "requirement gathering",
    "requirement analysis",
    "requirement documentation",
    "business requirements",
    "brd",
    "frd",
    "srs",
    "user stories",
    "use cases",
    "acceptance criteria",
    "functional specification",
    "stakeholder",
    "uat",
    "change request",
    "gap analysis",
    "process flow",
    "workflow",
    "business case",
    "status reports",
    "defect clarification",
]

SENIORITY_PATTERNS = [
    ("architect", r"\b(architect|principal)\b"),
    ("manager", r"\b(manager|head|leadership|people\s+management)\b"),
    ("lead", r"\b(lead|team\s+lead|tech\s+lead)\b"),
    ("senior", r"\b(senior|sr\.?)\b"),
    ("intern", r"\b(intern|internship|trainee)\b"),
    ("junior", r"\b(junior|jr\.?|fresher|entry[-\s]?level)\b"),
    ("mid-level", r"\b(mid[-\s]?level|associate)\b"),
]

DYNAMIC_ROLE_GROUP_RULES = [
    (
        "procurement",
        r"\b(procurement|purchase|purchasing|vendor|supply\s+chain)\b",
        {
            "procurement_process": ["Procurement", "Purchase Orders", "Purchasing"],
            "vendor_management": ["Vendor Management", "Supplier Management", "Negotiation"],
            "erp_tools": ["ERP", "SAP", "Excel"],
            "supply_chain": ["Supply Chain", "Inventory", "Coordination"],
        },
    ),
    (
        "seo",
        r"\b(seo|search\s+engine\s+optimization|keyword\s+research|on[-\s]?page|off[-\s]?page)\b",
        {
            "seo_research": ["Keyword Research", "SEO"],
            "seo_execution": ["On-page SEO", "Off-page SEO", "Content Optimization"],
            "seo_tools": ["Google Search Console", "Google Analytics", "SEMrush", "Ahrefs"],
            "reporting": ["Reporting", "Analytics"],
        },
    ),
    (
        "ui_ux",
        r"\b(ui/ux|ux|user\s+experience|figma|wireframes?|prototypes?|usability)\b",
        {
            "design_tools": ["Figma", "Adobe XD", "Sketch"],
            "interaction_design": ["Wireframes", "Prototypes", "Design Systems"],
            "research_testing": ["User Research", "Usability Testing"],
        },
    ),
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


def _stable_hash(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalized_role_label(role_title, role_family):
    label = re.sub(r"[^a-z0-9]+", "_", str(role_title or role_family or "generic").lower()).strip("_")
    return label or "generic"


def _scoring_mode(role_family, confidence):
    if role_family == "other" or confidence < 55:
        return "dynamic"
    if confidence < 80:
        return "hybrid"
    return "known_template"


def _profile_confidence(mode, role_confidence, must_have, core_groups):
    base = float(role_confidence or 0)
    if mode == "known_template":
        base = max(base, 82)
    elif mode == "hybrid":
        base = min(max(base, 62), 79)
    else:
        base = min(max(base, 45), 74)
    if len(must_have or []) >= 4:
        base += 6
    if len(core_groups or {}) >= 3:
        base += 5
    return round(max(20, min(100, base)), 2)


def _dynamic_core_groups_from_jd(role_title, jd_text, must_have):
    text = f"{role_title or ''}\n{jd_text or ''}\n{' '.join(must_have or [])}".lower()
    for normalized_role, pattern, groups in DYNAMIC_ROLE_GROUP_RULES:
        if re.search(pattern, text, re.I):
            selected = {}
            for group, options in groups.items():
                hits = []
                for option in options:
                    option_pattern = re.escape(option.lower()).replace(r"\ ", r"\s+")
                    if re.search(r"\b" + option_pattern + r"\b", text, re.I):
                        hits.append(option)
                selected[group] = normalize_skill_list(hits or options[:2])
            return normalized_role, selected

    dynamic_skills = normalize_skill_list(must_have or known_skills_in_text(jd_text or ""))
    if dynamic_skills:
        groups = {}
        for index, skill in enumerate(dynamic_skills[:12], start=1):
            key = re.sub(r"[^a-z0-9]+", "_", skill.lower()).strip("_") or f"requirement_{index}"
            groups[key] = [skill]
        return "", groups
    return "", {}


def _dynamic_role_hint(role_title, jd_text):
    text = f"{role_title or ''}\n{jd_text or ''}".lower()
    for normalized_role, pattern, _groups in DYNAMIC_ROLE_GROUP_RULES:
        if re.search(pattern, text, re.I):
            return normalized_role
    return ""


def _title_signals(role_title, role_family):
    tokens = [
        token for token in re.findall(r"[a-z][a-z0-9+#.]{2,}", f"{role_title or ''} {role_family or ''}".lower())
        if token not in {"engineer", "developer", "executive", "associate", "manager", "role"}
    ]
    return sorted(set(tokens))[:8]


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


def _explicit_seniority(role_title="", jd_text=""):
    text = f"{role_title or ''} {jd_text or ''}".lower()
    return next((level for level, pattern in SENIORITY_PATTERNS if re.search(pattern, text, re.I)), "")


def _explicit_crm_analytics_requirement(role_title="", jd_text=""):
    text = f"{role_title or ''}\n{jd_text or ''}".lower()
    return bool(re.search(
        r"\b(?:salesforce|crm)\s+(?:data|report(?:ing|s)?|dashboard(?:s)?|analytics?|analyst|administrator|admin)\b|"
        r"\b(?:data|report(?:ing|s)?|dashboard(?:s)?|analytics?)\s+(?:in|on|for|from)\s+(?:salesforce|crm)\b",
        text,
        re.I,
    ))


def _split_analytics_must_have(role_family, role_title, jd_text, must_have):
    if role_family != "data_analytics" or _explicit_crm_analytics_requirement(role_title, jd_text):
        return normalize_skill_list(must_have), []

    filtered = []
    demoted = []
    for skill in normalize_skill_list(must_have):
        if SKILL_CATEGORIES.get(skill) == "CRM":
            demoted.append(skill)
        else:
            filtered.append(skill)
    return filtered, demoted


def _split_full_stack_requirements(role_family, role_title, jd_text, must_have, nice_to_have):
    if role_family != "full_stack":
        return normalize_skill_list(must_have), normalize_skill_list(nice_to_have)

    text = f"{role_title or ''}\n{jd_text or ''}".lower()
    must = normalize_skill_list(must_have)
    nice = normalize_skill_list(nice_to_have)
    analytics_requested = bool(re.search(r"\b(data\s+visuali[sz]ation|analytics\s+dashboard|bi\s+dashboard|reporting\s+dashboard)\b", text, re.I))
    demote = {
        "Data Visualization",
        "Data Analysis",
        "Data Cleaning",
        "Reporting",
        "Dashboard",
        "KPI",
        "KPI Reporting",
        "MIS Reporting",
        "Business Reporting",
    }
    if analytics_requested:
        demote.discard("Dashboard")
        demote.discard("Data Visualization")

    filtered = [skill for skill in must if skill not in demote]
    demoted = [skill for skill in must if skill in demote]
    default_required = role_family_default_must_have("full_stack")
    default_nice = role_family_default_nice_to_have("full_stack")
    filtered = normalize_skill_list(filtered + default_required)
    nice = normalize_skill_list(nice + demoted + [skill for skill in default_nice if skill.lower() not in {item.lower() for item in filtered}])
    return filtered, nice


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
        "test", "automate", "validate", "verify", "debug", "document", "track",
        "regression", "smoke", "sanity", "functional", "integration",
    ]
    found = []
    text = (jd_text or "").lower()
    for word in patterns:
        if re.search(r"\b" + re.escape(word) + r"\w*\b", text):
            found.append(word)
    return found[:12]


def _profile_responsibility_signals(role_family, jd_text=""):
    found = _responsibility_signals(jd_text or "")
    if role_family == "business_analyst":
        text = (jd_text or "").lower()
        ba_found = [
            signal for signal in BUSINESS_ANALYST_RESPONSIBILITY_SIGNALS
            if re.search(r"\b" + re.escape(signal).replace(r"\ ", r"\s+") + r"\b", text, re.I)
        ]
        found = ba_found + [item for item in found if item not in ba_found]
    return found[:20]


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
    if role_family == "business_analysis":
        role_family = "business_analyst"
    dynamic_hint = _dynamic_role_hint(role_title, jd_text)
    if dynamic_hint and role_family in {"crm_erp", "other"}:
        role_family = "other"
        role_family_confidence = min(role_family_confidence, 54)
    scoring_mode = _scoring_mode(role_family, role_family_confidence)
    default_must_have = role_family_default_must_have(role_family)
    defaults_applied = False
    if default_must_have and len(must_have) < 3 and role_family_confidence >= 70:
        must_have = normalize_skill_list(must_have + default_must_have)
        nice_to_have = normalize_skill_list([
            skill for skill in nice_to_have
            if skill.lower() not in {item.lower() for item in must_have}
        ])
        defaults_applied = True
    must_have, demoted_must_have = _split_analytics_must_have(role_family, role_title, jd_text, must_have)
    if demoted_must_have:
        nice_to_have = normalize_skill_list(nice_to_have + [
            skill for skill in demoted_must_have
            if skill.lower() not in {item.lower() for item in must_have}
        ])
    must_have, nice_to_have = _split_full_stack_requirements(role_family, role_title, jd_text, must_have, nice_to_have)
    min_years, max_years = _experience_range(jd_text, jd_data)
    seniority = _seniority(role_title, jd_text, min_years)
    if role_family == "data_analytics" and seniority in {"senior", "lead"} and not _explicit_seniority(role_title, jd_text):
        seniority = "mid-level" if min_years >= 2 else "unknown"
    hard, soft = _requirement_lines(jd_text)
    core_groups = dynamic_core_groups(role_family, must_have, jd_text or "")
    dynamic_role_label = ""
    if scoring_mode == "dynamic":
        dynamic_role_label, dynamic_groups = _dynamic_core_groups_from_jd(role_title, jd_text, must_have)
        if dynamic_groups:
            core_groups = dynamic_groups
        if not must_have and core_groups:
            must_have = normalize_skill_list([
                skill
                for options in core_groups.values()
                for skill in (options or [])
            ])
    normalized_role_label = dynamic_role_label or _normalized_role_label(role_title, role_family)
    responsibility_signals = _profile_responsibility_signals(role_family, jd_text or "")
    profile_warnings = []
    if scoring_mode == "dynamic":
        profile_warnings.append("Low role-family confidence; using JD-specific dynamic scoring profile.")
    elif scoring_mode == "hybrid":
        profile_warnings.append("Medium role-family confidence; using calibrated template hints with JD-specific requirements.")
    if defaults_applied:
        profile_warnings.append("Role template defaults applied because JD had too few explicit required skills.")
    profile_confidence = _profile_confidence(scoring_mode, role_family_confidence, must_have, core_groups)
    profile_hash = _stable_hash({
        "role_title": role_title,
        "jd_text": jd_text or "",
        "must_have_skills": must_have,
        "nice_to_have_skills": nice_to_have,
        "min_experience_years": min_years,
        "max_experience_years": max_years,
        "profile_version": JD_PROFILE_VERSION,
    })

    return {
        "jd_profile_version": JD_PROFILE_VERSION,
        "profile_jd_hash": profile_hash,
        "role_title": role_title,
        "normalized_role_label": normalized_role_label,
        "role_family": role_family,
        "detected_role_family": role_family,
        "role_family_confidence": role_family_confidence,
        "scoring_mode": scoring_mode,
        "dynamic_profile_used": scoring_mode == "dynamic",
        "known_template_used": scoring_mode == "known_template",
        "hybrid_profile_used": scoring_mode == "hybrid",
        "profile_confidence": profile_confidence,
        "seniority_level": seniority,
        "min_experience_years": min_years,
        "max_experience_years": max_years,
        "must_have_skills": must_have,
        "nice_to_have_skills": nice_to_have,
        "mandatory_skill_groups": core_groups,
        "preferred_skill_groups": {"preferred": nice_to_have} if nice_to_have else {},
        "core_skill_groups": core_groups,
        "responsibility_signals": responsibility_signals,
        "responsibility_groups": {"responsibilities": responsibility_signals},
        "title_signals": _title_signals(role_title, role_family),
        "adjacent_title_signals": [],
        "negative_title_signals": [],
        "domain_context": role_family if role_family != "other" else "",
        "hard_requirements": hard,
        "soft_requirements": soft,
        "scoring_weights": {},
        "score_caps": {},
        "score_boosts": {},
        "profile_warnings": profile_warnings,
        "defaults_applied": defaults_applied,
    }
