from datetime import datetime

from pydantic import BaseModel, Field


class CandidateNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    visibility: str = "team"


class PipelineMove(BaseModel):
    candidate_id: str
    stage: str
    status: str | None = None


class InterviewCreate(BaseModel):
    candidate_id: str
    job_id: str
    interviewer_user_id: str | None = None
    interview_type: str = "technical"
    scheduled_at: datetime | None = None
    duration_minutes: int = 45
    meeting_url: str | None = None


class ScorecardCreate(BaseModel):
    interview_id: str
    candidate_id: str
    recommendation: str
    technical_score: float | None = None
    communication_score: float | None = None
    culture_score: float | None = None
    notes: str | None = None
