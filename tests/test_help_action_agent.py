from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Job, Resume, User
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
        Resume(id="candidate-1", job_id=job.id, organization_id="org-a", full_name="Asha Singh", final_score=91, rank_score=94, status="Review", stage="review", is_active=True),
        Resume(id="candidate-2", job_id=job.id, organization_id="org-a", full_name="Ravi Kumar", final_score=84, rank_score=87, status="Review", stage="review", is_active=True),
        Resume(id="candidate-3", job_id=job.id, organization_id="org-a", full_name="Neha Shah", final_score=70, rank_score=72, status="Review", stage="review", is_active=True),
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
