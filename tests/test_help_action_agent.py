from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import CandidateActivity, Job, Resume, User
from backend.services.help_action_agent import execute_confirmed_action, prepare_action_agent
from backend.services.help_intent import fallback_parse_intent


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_workspace(db):
    user = User(id="user-a", name="Recruiter", email="recruiter@example.com", password="hash", role="recruiter", organization_id="org-a")
    second_user = User(id="user-b", name="Second Recruiter", email="second@example.com", password="hash", role="recruiter", organization_id="org-a")
    outsider = User(id="user-c", name="Other Recruiter", email="other@example.com", password="hash", role="recruiter", organization_id="org-b")
    job = Job(id="job-data", job_title="Data Analyst", role="Data Analyst", organization_id="org-a", is_active=True)
    candidates = [
        Resume(id="candidate-1", job_id=job.id, organization_id="org-a", full_name="Asha Singh", final_score=91, rank_score=94, status="Review", stage="review", is_active=True, recruiter_explanation="Strong SQL and analytics evidence.", strengths='["SQL", "Dashboarding"]', concerns='["Validate stakeholder depth"]', matched_skills='["SQL", "Power BI"]'),
        Resume(id="candidate-2", job_id=job.id, organization_id="org-a", full_name="Ravi Kumar", final_score=84, rank_score=87, status="Review", stage="review", is_active=True),
        Resume(id="candidate-3", job_id=job.id, organization_id="org-a", full_name="Neha Shah", designation="Data Scientist", key_skills="Python, machine learning, statistics", final_score=70, rank_score=72, status="Review", stage="review", is_active=True),
    ]
    db.add_all([user, second_user, outsider, job, *candidates])
    db.commit()
    return user, second_user, outsider, job, candidates


def test_preview_resolves_exact_job_and_top_candidates(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="data analyst job ke top 2 candidates shortlist kar do",
        current_route="/dashboard",
        current_context={},
        db=db,
        user=user,
    )

    assert result["entities"]["job_id"] == job.id
    assert [candidate["id"] for candidate in result["candidate_preview"]] == ["candidate-1", "candidate-2"]
    assert result["candidate_preview"][0]["recruiter_explanation"] == "Strong SQL and analytics evidence."
    assert result["candidate_preview"][0]["strengths"] == ["SQL", "Dashboarding"]
    assert result["candidate_preview"][0]["matched_skills"] == ["SQL", "Power BI"]
    assert result["missing_fields"] == []
    assert result["confirmation"]["token"]
    assert result["requires_confirmation"] is True


def test_confirmed_workflow_shortlists_and_moves_only_previewed_candidates(monkeypatch, db):
    user, _, _, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )
    plan = prepare_action_agent(
        message="data analyst ke top 2 candidates communication me bhej do",
        current_route="/dashboard",
        current_context={},
        db=db,
        user=user,
    )

    result = execute_confirmed_action(
        confirmation_token=plan["confirmation"]["token"],
        db=db,
        user=user,
    )

    assert result["status"] == "completed"
    assert result["candidate_count"] == 2
    assert db.get(Resume, "candidate-1").stage == "communication"
    assert db.get(Resume, "candidate-2").stage == "communication"
    assert db.get(Resume, "candidate-3").stage == "review"


def test_duplicate_confirmation_is_idempotent(monkeypatch, db):
    user, _, _, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )
    plan = prepare_action_agent(
        message="data analyst ka top candidate shortlist kar do",
        current_route="/dashboard",
        current_context={"limit": 1},
        db=db,
        user=user,
    )

    first = execute_confirmed_action(confirmation_token=plan["confirmation"]["token"], db=db, user=user)
    activity_count = db.query(CandidateActivity).count()
    replay = execute_confirmed_action(confirmation_token=plan["confirmation"]["token"], db=db, user=user)

    assert first["status"] == "completed"
    assert replay["status"] == "already_completed"
    assert replay["idempotent_replay"] is True
    assert db.query(CandidateActivity).count() == activity_count


def test_database_failure_never_returns_a_false_action_success(monkeypatch, db):
    user, _, _, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )
    plan = prepare_action_agent(
        message="data analyst ka top candidate shortlist kar do",
        current_route="/dashboard",
        current_context={"limit": 1},
        db=db,
        user=user,
    )

    def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="database unavailable"):
        execute_confirmed_action(confirmation_token=plan["confirmation"]["token"], db=db, user=user)

    assert db.get(Resume, "candidate-1").stage == "review"


def test_confirmation_token_cannot_be_used_by_another_user(monkeypatch, db):
    user, second_user, _, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )
    plan = prepare_action_agent(
        message="data analyst ka top candidate shortlist kar do",
        current_route="/dashboard",
        current_context={"limit": 1},
        db=db,
        user=user,
    )

    with pytest.raises(HTTPException) as exc:
        execute_confirmed_action(
            confirmation_token=plan["confirmation"]["token"],
            db=db,
            user=second_user,
        )

    assert exc.value.status_code == 403


def test_outside_tenant_cannot_resolve_job_or_candidates(monkeypatch, db):
    _, _, outsider, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="data analyst job ke top 2 candidates shortlist kar do",
        current_route="/dashboard",
        current_context={},
        db=db,
        user=outsider,
    )

    assert "job" in result["missing_fields"]
    assert result["candidate_preview"] == []
    assert result["confirmation"] is None


def test_hallucinated_candidate_id_never_reaches_confirmation(monkeypatch, db):
    user, _, _, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="data analyst candidate shortlist kar do",
        current_route="/results",
        current_context={"candidate_ids": ["candidate-does-not-exist"]},
        db=db,
        user=user,
    )

    assert result["candidate_preview"] == []
    assert "candidate_ids" in result["missing_fields"]
    assert result["confirmation"] is None


def test_conversation_never_resolves_jobs_or_dispatches_actions(monkeypatch, db):
    user, _, _, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(message="hello", current_route="/dashboard", current_context={}, db=db, user=user)

    assert result["response_type"] == "conversation"
    assert result["assistant_reply"]
    assert result["job_options"] == []
    assert result["candidate_preview"] == []
    assert result["actions"] == []
    assert result["ready_for_action_agent"] is False


def test_all_candidates_resolves_exact_job_title_without_asking_for_id(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="i want all candidate of data analyst",
        current_route="/dashboard",
        current_context={},
        db=db,
        user=user,
    )

    assert result["entities"]["job_id"] == job.id
    assert result["entities"]["job_title"] == "Data Analyst"
    assert result["job_options"] == []
    assert result["missing_fields"] == []
    assert result["clarification_needed"] is False


def test_role_query_searches_candidates_across_jobs_without_job_picker(monkeypatch, db):
    user, _, _, _, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="i want data science candidates",
        current_route="/dashboard",
        current_context={},
        db=db,
        user=user,
    )

    assert result["intent"] == "search_talent"
    assert result["entities"]["search_query"] == "Data Science"
    assert result["job_options"] == []
    assert [candidate["id"] for candidate in result["candidate_preview"]] == ["candidate-3"]
    assert result["clarification_needed"] is False
    assert result["actions"] == []


def test_candidate_filters_query_stored_fields_without_mutation(monkeypatch, db):
    user, _, _, _, _ = _seed_workspace(db)
    matching = db.get(Resume, "candidate-3")
    matching.location = "San Jose, California"
    matching.direct_relevant_experience_years = 6
    matching.key_skills = "Firmware, C, RTOS"
    db.commit()
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="Show me California candidates with 5-7 years firmware experience.",
        current_route="/results",
        current_context={},
        db=db,
        user=user,
    )

    assert result["intent"] == "filter_candidates"
    assert [candidate["id"] for candidate in result["candidate_preview"]] == ["candidate-3"]
    assert result["requires_confirmation"] is False
    assert db.get(Resume, "candidate-3").stage == "review"


def test_job_scoped_skill_filter_returns_real_candidates_and_stable_cards(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    db.get(Resume, "candidate-1").key_skills = "AWS, Python, SQL"
    db.get(Resume, "candidate-2").key_skills = "Azure, Excel"
    db.commit()
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="Show me the top 10 candidates with AWS",
        current_route="jobResult",
        current_context={"job_id": job.id, "job_title": job.job_title},
        db=db,
        user=user,
    )

    assert result["intent"] == "filter_candidates"
    assert result["entities"]["job_id"] == job.id
    assert [item["id"] for item in result["ui"]["candidate_cards"]] == ["candidate-1"]
    assert result["ui"]["kind"] == "candidate_results"


def test_active_jobs_returns_tenant_scoped_job_cards(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="Show my active jobs", current_route="dashboard", current_context={}, db=db, user=user
    )

    assert result["intent"] == "view_active_jobs"
    assert result["ui"]["kind"] == "job_results"
    assert result["ui"]["job_cards"][0]["id"] == job.id
    assert result["ui"]["job_cards"][0]["applicant_count"] == 3


def test_no_result_filter_never_claims_candidates_exist(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="Show candidates with COBOL", current_route="jobResult",
        current_context={"job_id": job.id, "job_title": job.job_title}, db=db, user=user,
    )

    assert result["candidate_preview"] == []
    assert "0 candidate(s)" in result["assistant_reply"]
    assert result["confirmation"] is None


def test_reject_below_score_requires_signed_confirmation(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="Reject candidates with score below 90", current_route="jobResult",
        current_context={"job_id": job.id, "job_title": job.job_title}, db=db, user=user,
    )

    assert [item["id"] for item in result["candidate_preview"]] == ["candidate-2", "candidate-3"]
    assert result["requires_confirmation"] is True


def test_candidate_fit_follow_up_returns_stored_evidence_without_reasking_context(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="how is that candidate fit for this role?",
        current_route="topCandidate",
        current_context={
            "job_id": job.id,
            "job_title": job.job_title,
            "candidate_id": "candidate-1",
            "candidate_ids": ["candidate-1"],
        },
        db=db,
        user=user,
    )

    assert result["intent"] == "explain_candidate_score"
    assert [candidate["id"] for candidate in result["candidate_preview"]] == ["candidate-1"]
    assert "Asha Singh" in result["assistant_reply"]
    assert "Strong SQL and analytics evidence" in result["assistant_reply"]
    assert "Matched skills: SQL, Power BI" in result["assistant_reply"]
    assert "mail_status" in result["candidate_preview"][0]
    assert "response_status" in result["candidate_preview"][0]
    assert result["missing_fields"] == []
    assert result["clarification_needed"] is False


def test_follow_up_shortlist_best_three_limits_context_candidates(monkeypatch, db):
    user, _, _, job, _ = _seed_workspace(db)
    monkeypatch.setattr(
        "backend.services.help_action_agent.parse_intent",
        lambda message, current_route, current_context: fallback_parse_intent(message, current_route, current_context),
    )

    result = prepare_action_agent(
        message="Shortlist the best 2",
        current_route="jobResult",
        current_context={
            "job_id": job.id,
            "job_title": job.job_title,
            "candidate_ids": ["candidate-3", "candidate-1", "candidate-2"],
        },
        db=db,
        user=user,
    )

    assert result["entities"]["limit"] == 2
    assert [candidate["id"] for candidate in result["candidate_preview"]] == ["candidate-1", "candidate-2"]
    assert result["requires_confirmation"] is True
    assert result["confirmation"]["token"]
    assert db.get(Resume, "candidate-2").stage == "review"
