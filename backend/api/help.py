from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from backend.core.security import get_current_user
from backend.database import get_db
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


def _request_context(payload: HelpIntentRequest) -> dict:
    context = dict(payload.current_context or {})
    context["conversation_history"] = [
        {
            "role": str(item.get("role") or "user")[:20],
            "content": str(item.get("content") or "")[:1000],
        }
        for item in payload.conversation_history[-12:]
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    return context


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


@router.post("/chat")
def chat_with_help_agent(
    payload: HelpIntentRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return prepare_action_agent(
        message=payload.message,
        current_route=payload.current_route,
        current_context=_request_context(payload),
        db=db,
        user=user,
    )


@router.post("/execute")
def execute_help_action(
    payload: HelpActionExecuteRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return execute_confirmed_action(
        confirmation_token=payload.confirmation_token,
        db=db,
        user=user,
    )
