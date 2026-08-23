from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from backend.core.config import get_settings
from backend.core.security import get_current_user
from backend.database import get_db
from backend.services.conversation_context import build_conversation_context
from backend.services.help_action_agent import execute_confirmed_action, prepare_action_agent
from backend.services.help_intent import parse_intent


router = APIRouter(prefix="/help", tags=["help-agent"])


class HelpIntentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    current_route: str | None = None
    current_context: dict | None = None
    conversation_history: list[dict] = Field(default_factory=list, max_length=12)


class HelpActionExecuteRequest(BaseModel):
    confirmation_token: str = Field(..., min_length=20, max_length=10000)


class AgentUIContract(BaseModel):
    kind: str
    candidate_cards: list[dict] = Field(default_factory=list)
    job_cards: list[dict] = Field(default_factory=list)
    navigation: dict | None = None
    confirmation: dict | None = None
    metrics: dict = Field(default_factory=dict)


class AgentResponse(BaseModel):
    result_schema_version: str
    response_type: str | None = None
    assistant_reply: str | None = None
    status: str | None = None
    intent: str | None = None
    entities: dict = Field(default_factory=dict)
    candidate_preview: list[dict] = Field(default_factory=list)
    job_preview: list[dict] = Field(default_factory=list)
    confirmation: dict | None = None
    ui: AgentUIContract

    class Config:
        extra = "allow"


def _request_context(payload: HelpIntentRequest) -> dict:
    return build_conversation_context(payload.current_context, payload.conversation_history)


def _require_action_agent_enabled() -> None:
    if not get_settings().conversational_action_agent_enabled:
        raise HTTPException(status_code=503, detail="Conversational Action Agent is disabled")


@router.post("/parse-intent")
def parse_help_intent(payload: HelpIntentRequest, user=Depends(get_current_user)):
    return parse_intent(
        message=payload.message,
        current_route=payload.current_route,
        current_context=_request_context(payload),
    )


@router.post("/action-plan")
def plan_help_action(payload: HelpIntentRequest, user=Depends(get_current_user)):
    return parse_intent(
        message=payload.message,
        current_route=payload.current_route,
        current_context=_request_context(payload),
    )


@router.post("/chat", response_model=AgentResponse)
def chat_with_help_agent(
    payload: HelpIntentRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _require_action_agent_enabled()
    return prepare_action_agent(
        message=payload.message,
        current_route=payload.current_route,
        current_context=_request_context(payload),
        db=db,
        user=user,
    )


@router.post("/execute", response_model=AgentResponse)
def execute_help_action(
    payload: HelpActionExecuteRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _require_action_agent_enabled()
    return execute_confirmed_action(
        confirmation_token=payload.confirmation_token,
        db=db,
        user=user,
    )
