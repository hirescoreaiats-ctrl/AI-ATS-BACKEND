from backend.ai_parser import repair_parse_fields, repair_parse_resume
from backend.domain_engine import detect_domain
from backend.experience_engine import process_experience
from backend.validation_scoring import validate_email, validate_phone
from backend.services.explanation_service import generate_recruiter_explanation
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.canonical_parser import apply_safe_primary_fields, parse_resume_document
from backend.services.resume_quality_gate import apply_parser_quality_gate, build_parser_quality_report
from backend.services.scoring_service import score_candidate
from backend.services.semantic_service import candidate_embedding_payload, cosine_similarity_cached


def _explicit_experience_years(text, jd_profile=None):
    import re

    values = []
    jd_profile = jd_profile or {}
    role_terms = set()
    for value in [
        jd_profile.get("role_title"),
        jd_profile.get("role_family"),
        *(jd_profile.get("must_have_skills") or []),
        *(jd_profile.get("responsibility_signals") or []),
    ]:
        for token in re.findall(r"[a-z][a-z0-9+#.]{2,}", str(value or "").lower()):
            if token not in {"years", "experience", "role", "job", "and", "with", "using"}:
                role_terms.add(token)
    professional_terms = {
        "experience", "work", "worked", "professional", "employment", "career",
        "role", "responsibilities", "handled", "managed", "developed", "implemented",
        "supported", "delivered", "created", "built",
    }
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", text or "", re.I):
        number = float(match.group(1))
        context = (text or "")[max(0, match.start() - 80): match.end() + 120].lower()
        if any(term in context for term in [
            "competitive programming",
            "leaderboard",
            "codechef",
            "codeforces",
            "google kickstart",
            "hacker cup",
            "virtual experience",
        ]):
            continue
        context_tokens = set(re.findall(r"[a-z][a-z0-9+#.]{2,}", context))
        has_professional_context = bool(context_tokens & professional_terms)
        has_role_context = bool(role_terms and context_tokens & role_terms)
        if has_professional_context and (has_role_context or "experience" in context_tokens):
            values.append(number)
    return max(values) if values else 0


def _jd_experience_range(text):
    import re

    text = text or ""
    range_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:-|\u2013|\u2014|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
        text,
        re.I,
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        return min(low, high), max(low, high)

    min_match = re.search(
        r"\b(?:minimum|min|at least)\s+(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
        text,
        re.I,
    )
    if min_match:
        return float(min_match.group(1)), None

    return None, None


def analyze_resume_for_job(text, jd_text, jd_skills, jd_data):
    jd_profile = build_jd_profile(jd_text, jd_data, jd_skills)
    parsed = parse_resume_document(text, job_context={**(jd_data or {}), "jd_profile": jd_profile}, mode="application")

    parsed["domain"] = parsed.get("domain") or detect_domain(
        parsed.get("key_skills", []),
        parsed.get("designation")
    )

    exp_data = process_experience(parsed.get("experience", []))
    explicit_years = _explicit_experience_years(text, jd_profile)
    resume_lower = (text or "").lower()
    role_terms = [
        str(item).lower()
        for item in [jd_profile.get("role_title"), *(jd_profile.get("must_have_skills") or [])]
        if str(item or "").strip()
    ]
    explicit_is_role_relevant = bool(explicit_years and any(term and term in resume_lower for term in role_terms))
    if explicit_is_role_relevant and explicit_years < exp_data["total_experience_years"]:
        exp_data["total_experience_years"] = explicit_years
    elif explicit_years > exp_data["total_experience_years"]:
        exp_data["total_experience_years"] = explicit_years
    parsed["total_experience_years"] = exp_data["total_experience_years"]
    parsed["email"] = validate_email(parsed.get("email"))
    parsed["phone"] = validate_phone(parsed.get("phone"))
    parsed["jd_profile_json"] = jd_profile
    parsed["role_family"] = jd_profile.get("role_family")
    parsed["role_family_confidence"] = jd_profile.get("role_family_confidence")

    pre_score_quality_report = build_parser_quality_report(text, parsed, exp_data, jd_data)
    parsed.update({
        "parser_quality_score": pre_score_quality_report.get("parser_quality_score"),
        "parser_quality_flags": pre_score_quality_report.get("parser_quality_flags"),
        "parser_quality_action": pre_score_quality_report.get("parser_quality_action"),
    })
    parsed["parser_recall_attempted"] = False
    parsed["parser_recall_applied"] = False
    pre_score_flags = pre_score_quality_report.get("parser_quality_flags", [])
    recall_worthy_flags = [
        item for item in pre_score_flags
        if item.get("code") not in {"seniority_outside_jd_range"}
    ]
    if recall_worthy_flags or pre_score_quality_report.get("parser_quality_action") != "auto_rank_ok":
        issue_messages = [
            item.get("message")
            for item in recall_worthy_flags or pre_score_flags
            if item.get("message")
        ]
        repaired_ai_parse = repair_parse_fields(text, parsed, recall_worthy_flags or pre_score_flags)
        if not repaired_ai_parse:
            repaired_ai_parse = repair_parse_resume(text, parsed, issue_messages)
        parsed["parser_recall_attempted"] = True
        if repaired_ai_parse:
            repaired = parse_resume_document(
                text,
                job_context={**(jd_data or {}), "jd_profile": jd_profile},
                mode="application_repair",
                ai_parse_override=repaired_ai_parse,
            )
            repaired_exp_data = process_experience(repaired.get("experience", []))
            repaired["total_experience_years"] = repaired_exp_data["total_experience_years"]
            repaired["email"] = validate_email(repaired.get("email"))
            repaired["phone"] = validate_phone(repaired.get("phone"))
            repaired["jd_profile_json"] = jd_profile
            repaired["role_family"] = jd_profile.get("role_family")
            repaired["role_family_confidence"] = jd_profile.get("role_family_confidence")
            repaired_quality_report = build_parser_quality_report(text, repaired, repaired_exp_data, jd_data)
            current_critical = sum(
                1 for item in pre_score_quality_report.get("parser_quality_flags", [])
                if item.get("severity") == "critical"
            )
            repaired_critical = sum(
                1 for item in repaired_quality_report.get("parser_quality_flags", [])
                if item.get("severity") == "critical"
            )
            repaired_is_better = (
                repaired_critical < current_critical
                or (
                    repaired_critical == current_critical
                    and repaired_quality_report.get("parser_quality_score", 0) > pre_score_quality_report.get("parser_quality_score", 0)
                )
            )
            if repaired_is_better:
                parsed = repaired
                exp_data = repaired_exp_data
                pre_score_quality_report = repaired_quality_report
                parsed.update({
                    "parser_quality_score": pre_score_quality_report.get("parser_quality_score"),
                    "parser_quality_flags": pre_score_quality_report.get("parser_quality_flags"),
                    "parser_quality_action": pre_score_quality_report.get("parser_quality_action"),
                })
                parsed["parser_recall_attempted"] = True
                parsed["parser_recall_applied"] = True
            else:
                parsed["parser_recall_applied"] = False

    parsed["semantic_score"] = cosine_similarity_cached(jd_text, text)

    jd_role = jd_data.get("role", "")
    resume_role = parsed.get("designation", "")
    parsed["role_similarity"] = cosine_similarity_cached(jd_role, resume_role) if jd_role and resume_role else 0

    relevance = estimate_relevant_experience_v2(parsed, text, jd_profile)
    if not relevance:
        relevance = {
            "relevant_experience_years": 0,
            "experience_relevance_label": "needs_validation",
            "experience_evidence": [],
            "experience_warnings": ["Relevant experience could not be calculated from work-history evidence."],
        }
    parsed.update(relevance)
    parsed["total_experience_years"] = max(
        float(parsed.get("total_experience_years") or 0),
        float(exp_data.get("total_experience_years") or 0),
    )
    if explicit_is_role_relevant and explicit_years:
        parsed["total_experience_years"] = min(parsed["total_experience_years"], explicit_years)
        parsed["relevant_experience_years"] = min(
            max(float(parsed.get("relevant_experience_years") or 0), explicit_years),
            parsed["total_experience_years"],
        )
        parsed["direct_relevant_experience_years"] = min(
            max(float(parsed.get("direct_relevant_experience_years") or 0), parsed["relevant_experience_years"]),
            parsed["total_experience_years"],
        )

    jd_min_years, jd_max_years = _jd_experience_range(jd_text)
    if jd_min_years is not None and not jd_data.get("min_experience_years"):
        jd_data["min_experience_years"] = jd_min_years
    if jd_max_years is not None:
        jd_data["max_experience_years"] = jd_max_years
    jd_data["min_experience_years"] = jd_profile.get("min_experience_years") or jd_data.get("min_experience_years")
    jd_data["max_experience_years"] = jd_profile.get("max_experience_years") or jd_data.get("max_experience_years")

    score_data = score_candidate(parsed, jd_text, jd_profile.get("must_have_skills") or jd_skills, jd_data, text, jd_profile=jd_profile)
    parsed.update(score_data)
    quality_report = apply_parser_quality_gate(parsed, exp_data, jd_data, text)
    apply_safe_primary_fields(parsed)
    if quality_report.get("parser_quality_action") == "manual_review_required" and parsed.get("final_score", 0) > 58:
        parsed["final_score"] = 58
        parsed["rank_score"] = min(parsed.get("rank_score") or 58, 58)
        parsed["fit_band"] = "review"
        score_data["final_score"] = parsed["final_score"]
        score_data["rank_score"] = parsed["rank_score"]
        score_data["fit_band"] = parsed["fit_band"]
        caps = score_data.setdefault("score_caps_applied", [])
        caps.append({"cap": 58, "reason": "Parser quality requires manual review."})
        flags = score_data.setdefault("recruiter_flags", [])
        if "parser_manual_review" not in flags:
            flags.append("parser_manual_review")
    score_data.update({
        "final_score": parsed.get("final_score"),
        "rank_score": parsed.get("rank_score"),
        "fit_band": parsed.get("fit_band"),
        "confidence_score": parsed.get("confidence_score"),
        "resume_quality_score": parsed.get("resume_quality_score"),
        "recommendation": parsed.get("recommendation"),
        "ranking_reason": parsed.get("ranking_reason"),
        "parser_quality_score": quality_report.get("parser_quality_score"),
        "parser_quality_flags": quality_report.get("parser_quality_flags"),
        "parser_quality_action": quality_report.get("parser_quality_action"),
        "parser_recall_attempted": parsed.get("parser_recall_attempted", False),
        "parser_recall_applied": parsed.get("parser_recall_applied", False),
        "jd_profile_json": jd_profile,
    })

    parsed["ai_recruiter_explanation"] = generate_recruiter_explanation(parsed, jd_data, score_data)
    parsed["embedding_metadata"] = candidate_embedding_payload(text, jd_text)

    return parsed, exp_data, score_data
