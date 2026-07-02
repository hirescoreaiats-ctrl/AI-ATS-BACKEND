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


def test_top_candidates_to_communication_builds_action_agent_plan():
    result = fallback_parse_intent(
        "mujhe 10 candiate nikal do data analyst kai lia aur unha commincation mai bhej do"
    )

    assert result["intent"] == "candidate_workflow"
    assert result["entities"]["job_title"] == "Data Analyst"
    assert result["entities"]["limit"] == 10
    assert result["entities"]["candidate_group"] == "top_candidates"
    assert result["entities"]["target_stage"] == "communication"
    assert [task["intent"] for task in result["tasks"]] == [
        "select_top_candidates",
        "shortlist_candidate",
        "move_candidates_to_communication",
    ]
    assert [action["action_id"] for action in result["actions"]] == [
        "find_top_candidates",
        "shortlist_candidates",
        "move_to_communication",
    ]
    assert result["actions"][2]["endpoint"] == "/move-to-communication"
    assert result["visual_tour"]["mode"] == "visual_tour"
    assert [step["target"] for step in result["visual_tour"]["steps"]]
    assert result["action_agent_plan"]["enabled"] is True
    assert result["requires_confirmation"] is True
    assert result["missing_fields"] == []


def test_top_candidates_to_interview_requests_missing_schedule_details():
    result = fallback_parse_intent("data analyst ke liye top 10 candidates ka interview schedule kar do")

    assert result["intent"] == "candidate_workflow"
    assert result["entities"]["job_title"] == "Data Analyst"
    assert result["entities"]["target_stage"] == "interview_scheduling"
    assert [action["action_id"] for action in result["actions"]] == [
        "find_top_candidates",
        "shortlist_candidates",
        "move_to_communication",
        "move_to_interview_scheduling",
        "schedule_interview_slot",
    ]
    assert "scheduled_at" in result["missing_fields"]
    assert "meeting_url" in result["missing_fields"]
    assert result["ready_for_action_agent"] is False


def test_top_candidate_of_backend_developer_extracts_role_and_limit():
    result = fallback_parse_intent("i want you to give 5 top candidate of backend developer")

    assert result["intent"] == "select_top_candidates"
    assert result["entities"]["job_title"] == "Backend Developer"
    assert result["entities"]["limit"] == 5
    assert result["entities"]["candidate_name"] is None
    assert result["visual_tour"]["steps"][0]["target"] == "jobs-menu"
    assert result["action_agent_plan"]["missing_fields"] == []
