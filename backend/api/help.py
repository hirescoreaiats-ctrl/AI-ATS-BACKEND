from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from backend.core.security import get_current_user
from backend.services.help_intent import parse_intent


router = APIRouter(prefix="/help", tags=["help-agent"])


class HelpIntentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    current_route: str | None = None
    current_context: dict | None = None


@router.post("/parse-intent")
def parse_help_intent(payload: HelpIntentRequest, user=Depends(get_current_user)):
    return parse_intent(
        message=payload.message,
        current_route=payload.current_route,
        current_context=payload.current_context or {},
    )
