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


class HelpActionExecuteRequest(BaseModel):
    confirmation_token: str = Field(..., min_length=20, max_length=10000)


@router.post("/parse-intent")
def parse_help_intent(payload: HelpIntentRequest, user=Depends(get_current_user)):
    return parse_intent(
        message=payload.message,
        current_route=payload.current_route,
        current_context=payload.current_context or {},
    )


@router.post("/action-plan")
def plan_help_action(payload: HelpIntentRequest, user=Depends(get_current_user)):
    return parse_intent(
        message=payload.message,
        current_route=payload.current_route,
        current_context=payload.current_context or {},
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
        current_context=payload.current_context or {},
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
