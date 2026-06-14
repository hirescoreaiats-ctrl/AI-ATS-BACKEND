from backend.services.candidate_report_normalizer import normalize_candidate_report, serialize_candidate_report


def test_normalizes_stringified_json_report_without_parser_flags_as_concerns():
    raw = (
        '{"summary":"Candidate appears strong","strengths":["ML evidence"],'
        '"concerns":["Parser flag: ai_parse_recovered","Verify LLM depth"],'
        '"recommendation":"Shortlist","ranking_reason":"Rank score 96.5/100.",'
        '"experience_summary":{"total_years":6.93,"relevant_years":6.35,"label":"direct_match"}}'
    )

    report = normalize_candidate_report(raw)

    assert report["summary"] == "Candidate appears strong"
    assert report["strengths"] == ["ML evidence"]
    assert report["concerns"] == ["Verify LLM depth"]
    assert report["recommendation"] == "Shortlist"
    assert report["experience_summary"]["relevant_years"] == 6.35
    assert "Resume parse was repaired after an initial extraction issue." in report["data_quality_notes"]


def test_serializes_report_as_single_json_object_string():
    saved = serialize_candidate_report(
        {"summary": "Clean", "strengths": ["A"], "concerns": [], "recommendation": "Review"},
        {"parser_quality_flags": ["phone_needs_review"]},
    )

    assert '\\"summary\\"' not in saved
    assert '"summary": "Clean"' in saved
    assert "Phone number may need manual verification." in saved


def test_plain_text_report_gets_safe_sections():
    report = normalize_candidate_report(
        "Summary: Good fit.\nStrengths:\n- Python\n- ML\nGaps:\n- Parser flag: phone_needs_review\n- Verify Docker\nVerdict: Shortlist"
    )

    assert report["summary"] == "Good fit."
    assert report["strengths"] == ["Python", "ML"]
    assert report["concerns"] == ["Verify Docker"]
    assert report["recommendation"] == "Shortlist"
    assert "Phone number may need manual verification." in report["data_quality_notes"]
