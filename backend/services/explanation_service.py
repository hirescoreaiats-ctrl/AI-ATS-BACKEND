def generate_recruiter_explanation(parsed, jd_data, score_data):
    matched = score_data.get("direct_matched_skills") or []
    transferable = score_data.get("transferable_skills") or []
    missing = score_data.get("missing_skills") or []
    concerns = parsed.get("resume_quality_concerns") or []
    flags = score_data.get("recruiter_flags") or []
    missing_core_groups = score_data.get("missing_core_skill_groups") or []

    verdict = {
        "shortlisted": "Shortlist",
        "in_review": "Review",
        "rejected": "Reject",
    }.get(score_data.get("recommendation"), "Review")

    if score_data.get("jd_role_family") == "aml_transaction_monitoring":
        group_scores = score_data.get("evidence_group_scores") or {}
        flags = score_data.get("risk_flags") or []
        total_years = parsed.get("total_experience_years")
        relevant_years = (
            ((score_data.get("scoring_breakdown") or {}).get("experience_fit") or {}).get("relevant_years")
            if isinstance(score_data.get("scoring_breakdown"), dict)
            else parsed.get("relevant_experience_years")
        )
        recommendation = score_data.get("recruiter_recommendation") or {
            "shortlisted": "Shortlist",
            "in_review": "Review manually",
            "rejected": "Reject for this role",
        }.get(score_data.get("recommendation"), "Review manually")

        def has_group(name):
            return (group_scores.get(name) or {}).get("score", 0) >= 25

        strengths = []
        if has_group("transaction_monitoring"):
            strengths.append("AML Transaction Monitoring evidence is present.")
        if has_group("aml_investigations"):
            strengths.append("AML investigation or suspicious transaction review evidence is present.")
        if has_group("case_management"):
            strengths.append("Case management, case closure, or case narrative evidence is present.")
        if has_group("sar_str"):
            strengths.append("SAR/STR or suspicious reporting process evidence is present.")
        if has_group("banking_exposure"):
            strengths.append("Banking or financial institution domain exposure is present.")
        if relevant_years is not None:
            strengths.append(f"JD-related AML Transaction Monitoring experience is approximately {relevant_years:g} years.")

        concerns = []
        if "missing_sar_str" in flags:
            concerns.append("Verify SAR/STR process knowledge and documentation exposure.")
        if "kyc_only_profile" in flags:
            concerns.append("KYC/CDD/EDD evidence appears stronger than AML Transaction Monitoring investigation evidence.")
        if "generic_banking_only" in flags:
            concerns.append("Generic banking operations evidence is not enough for this AML L2 investigator role.")
        if "under_experienced_for_l2" in flags:
            concerns.append("Candidate appears below the target 5-7 years of JD-related AML Transaction Monitoring experience.")
        if "over_experienced_for_l2" in flags:
            concerns.append("Candidate appears above the target 5-7 years and should be reviewed for level fit.")
        if "no_case_management_evidence" in flags:
            concerns.append("No clear case management or case narrative documentation evidence was found.")
        if "synthetic_or_non_human_profile" in flags:
            concerns.append("Document appears to describe an AI/digital worker rather than a human candidate resume.")
        if "invalid_document_or_jd_uploaded" in flags:
            concerns.append("Document appears to be a job description uploaded as a resume.")

        return {
            "summary": (
                f"Candidate is evaluated specifically for AML Transaction Monitoring Investigator L2 with "
                f"a score of {score_data.get('final_score')}/100 and {score_data.get('confidence_score')}% confidence."
            ),
            "strengths": strengths or ["Limited AML Transaction Monitoring investigator evidence found."],
            "concerns": concerns or ["No major AML L2 concerns detected from available resume evidence."],
            "recommendation": recommendation,
            "ranking_reason": score_data.get("ranking_reason"),
            "experience_summary": {
                "total_years": total_years,
                "relevant_years": relevant_years,
                "direct_relevant_years": parsed.get("direct_relevant_experience_years"),
                "transferable_reporting_years": parsed.get("transferable_reporting_experience_years"),
                "label": parsed.get("experience_relevance_label"),
                "transition_candidate": bool(parsed.get("transition_candidate")),
            },
        }

    summary = (
        f"Candidate appears to be a {score_data.get('seniority_level', 'candidate')} profile "
        f"for {jd_data.get('role') or 'this role'} with a score of {score_data.get('final_score')}/100 "
        f"and {score_data.get('confidence_score')}% confidence."
    )

    strengths = []
    if matched:
        strengths.append(f"Direct skill alignment: {', '.join(matched[:6])}.")
    if transferable:
        strengths.append(f"Transferable skill coverage identified for: {', '.join(transferable[:5])}.")
    total_years = parsed.get("total_experience_years")
    relevant_years = parsed.get("relevant_experience_years")
    if relevant_years is not None:
        strengths.append(f"Shows approximately {relevant_years:g} years of JD-related experience.")
    if total_years and total_years != relevant_years:
        strengths.append(f"Total professional experience is approximately {total_years:g} years.")
    if "good_project_match" in flags:
        strengths.append("Strong JD-aligned project evidence is present.")
    if "strong_match" in flags:
        strengths.append("Recruiter calibration marks this as a strong role match.")

    gaps = []
    if missing:
        gaps.append(f"Missing or weak evidence for: {', '.join(missing[:6])}.")
    if missing_core_groups:
        gaps.append(f"Core evidence needing review: {', '.join(missing_core_groups[:5])}.")
    if "under_experienced" in flags:
        gaps.append("Candidate has limited professional experience for the JD range; review project evidence before shortlisting.")
    if "overqualified" in flags:
        gaps.append("Candidate appears above the target experience range; recruiter review is recommended instead of blind auto-shortlist.")
    if "score_capped" in flags:
        gaps.append("Score was calibrated/capped to avoid overstating fit without complete JD evidence.")
    gaps.extend(concerns[:2])

    return {
        "summary": summary,
        "strengths": strengths or ["Resume contains limited but usable evidence for evaluation."],
        "concerns": gaps or ["No major concerns detected from available resume text."],
        "recommendation": verdict,
        "ranking_reason": score_data.get("ranking_reason"),
        "experience_summary": {
            "total_years": total_years,
            "relevant_years": relevant_years,
            "direct_relevant_years": parsed.get("direct_relevant_experience_years"),
            "transferable_reporting_years": parsed.get("transferable_reporting_experience_years"),
            "label": parsed.get("experience_relevance_label"),
            "transition_candidate": bool(parsed.get("transition_candidate")),
        },
    }
