from backend.services.help_intent import fallback_parse_intent, parse_intent, _merge_with_fallback, normalize_intent_response


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


def test_shortlist_action_with_typo_extracts_job_and_action_plan():
    result = fallback_parse_intent("i want short;ist candidate of data analyst job")

    assert result["intent"] == "candidate_workflow"
    assert result["entities"]["job_title"] == "Data Analyst"
    assert result["entities"]["candidate_group"] == "top_candidates"
    assert [action["action_id"] for action in result["actions"]] == [
        "find_top_candidates",
        "shortlist_candidates",
    ]
    assert result["missing_fields"] == []


def test_ai_response_keeps_fallback_job_title_when_ai_misses_entity():
    fallback = fallback_parse_intent("i want short;ist candidate of data analyst job")
    ai_result = normalize_intent_response({
        "intent": "candidate_workflow",
        "entities": {"job_title": None, "candidate_group": "top_candidates"},
        "confidence": 0.9,
    })

    merged = _merge_with_fallback(ai_result, fallback)

    assert merged["intent"] == "candidate_workflow"
    assert merged["entities"]["job_title"] == "Data Analyst"


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


def test_greeting_is_conversation_with_no_backend_tasks():
    result = fallback_parse_intent("hello")

    assert result["response_type"] == "conversation"
    assert result["assistant_reply"]
    assert result["intent"] == "unknown"
    assert result["tasks"] == []
    assert result["actions"] == []
    assert result["clarification_needed"] is False


def test_greeting_guard_overrides_hallucinated_ai_workflow():
    fallback = fallback_parse_intent("hello bhai")
    hallucinated = normalize_intent_response({
        "response_type": "workflow",
        "intent": "select_top_candidates",
        "confidence": 0.95,
        "actions": [{"action_id": "find_top_candidates"}],
    })

    merged = _merge_with_fallback(hallucinated, fallback)

    assert merged["response_type"] == "conversation"
    assert merged["actions"] == []


def test_all_candidates_uses_job_title_without_requesting_internal_id():
    result = fallback_parse_intent("i want all candidate of data analyst")

    assert result["response_type"] == "workflow"
    assert result["intent"] == "view_candidates_by_stage"
    assert result["entities"]["job_title"] == "Data Analyst"
    assert result["entities"]["candidate_group"] == "all"
    assert result["actions"] == []
    assert result["clarification_needed"] is False


def test_ai_job_id_question_is_rewritten_for_normal_users():
    result = normalize_intent_response({
        "response_type": "clarification",
        "intent": "unknown",
        "assistant_reply": "Please specify the job ID or confirm the job.",
        "clarification_question": "Enter job_id.",
        "confidence": 0.7,
    })

    assert "job id" not in result["assistant_reply"].lower()
    assert "job_id" not in result["clarification_question"].lower()


def test_top_ten_score_explanation_remains_a_candidate_group():
    message = "i want ai explanation of data analyst top 10 candidate"
    fallback = fallback_parse_intent(message)
    ai_result = normalize_intent_response({
        "response_type": "workflow",
        "intent": "explain_candidate_score",
        "entities": {"job_title": "Data Analyst", "limit": 10, "candidate_group": "top_candidates"},
        "confidence": 0.92,
    })

    merged = _merge_with_fallback(ai_result, fallback)

    assert merged["intent"] == "review_ai_ranked_candidates"
    assert merged["entities"]["candidate_group"] == "top_candidates"
    assert merged["entities"]["limit"] == 10
    assert merged["entities"]["candidate_name"] is None
    assert [action["action_id"] for action in merged["actions"]] == ["find_top_candidates"]


def test_model_cannot_invent_executable_backend_endpoint():
    result = normalize_intent_response({
        "response_type": "workflow",
        "intent": "create_job",
        "entities": {},
        "tasks": [{"intent": "create_job", "description": "Create a role", "entities": {}}],
        "actions": [{"action_id": "delete_everything", "method": "DELETE", "endpoint": "/admin/all"}],
        "confidence": 0.95,
    })

    assert result["tasks"][0]["intent"] == "create_job"
    assert result["actions"] == []
    assert result["agent_contract_version"] == "2026-07-general-v1"


def test_generic_candidate_request_does_not_loop_on_scope_question():
    primary = normalize_intent_response({
        "response_type": "clarification",
        "intent": "unknown",
        "entities": {"job_title": "Data Scientist"},
        "assistant_reply": "Do you want all candidates, top candidates, or shortlisted profiles?",
        "confidence": 0.72,
    })
    fallback = fallback_parse_intent("show candidates")

    merged = _merge_with_fallback(primary, fallback)

    assert merged["response_type"] == "workflow"
    assert merged["intent"] == "view_candidates_by_stage"
    assert merged["entities"]["job_title"] == "Data Scientist"
    assert merged["entities"]["candidate_group"] == "all"
    assert merged["clarification_needed"] is False


def test_role_candidate_request_uses_cross_job_talent_search():
    result = fallback_parse_intent(
        "i want data science candidates",
        current_context={"job_id": "stale-job", "job_title": "Old Role"},
    )

    assert result["response_type"] == "workflow"
    assert result["intent"] == "search_talent"
    assert result["entities"]["search_query"] == "Data Science"
    assert result["entities"]["job_title"] is None
    assert result["entities"]["job_id"] is None
    assert [action["action_id"] for action in result["actions"]] == ["search_talent"]
