from backend.services.help_intent import fallback_parse_intent, parse_intent


def should_require_candidate(result):
    return result["intent"] in {"schedule_interview", "view_candidate_profile", "reject_candidate"} and bool(
        result["entities"].get("candidate_name")
    )


def test_shortlisted_candidates_for_job_does_not_require_candidate(monkeypatch):
    monkeypatch.setattr("backend.services.help_intent._client", lambda: None)
    result = parse_intent("i want shortlisted candiate of data analyst job", "/dashboard", {})

    assert result["intent"] == "view_shortlisted_candidates"
    assert result["entities"]["job_title"] == "Data Analyst"
    assert result["entities"]["candidate_group"] == "shortlisted"
    assert result["entities"]["stage"] == "shortlisted"
    assert result["entities"]["candidate_name"] is None
    assert should_require_candidate(result) is False


def test_named_interview_request_requires_candidate():
    result = fallback_parse_intent("Rahul ka interview schedule karna hai")

    assert result["intent"] == "schedule_interview"
    assert result["entities"]["candidate_name"] == "Rahul"
    assert should_require_candidate(result) is True


def test_shortlisted_email_targets_group_not_candidate():
    result = fallback_parse_intent("shortlisted ko mail bhejna hai")

    assert result["intent"] == "send_candidate_email"
    assert result["entities"]["candidate_group"] == "shortlisted"
    assert result["entities"]["candidate_name"] is None
    assert should_require_candidate(result) is False


def test_hinglish_cv_upload_extracts_job_title():
    result = fallback_parse_intent("data analyst wali job me cv dalna hai")

    assert result["intent"] == "upload_resumes"
    assert result["entities"]["job_title"] == "Data Analyst"
