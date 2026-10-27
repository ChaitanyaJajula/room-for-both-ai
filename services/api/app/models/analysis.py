from typing import Literal

from pydantic import BaseModel, Field

from app.models.capacity import CapacityRequest, CapacityResponse

Classification = Literal["balanced", "tight", "overloaded"]


class Outcome(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=600)
    estimated_minutes: int = Field(ge=0, le=10080)


class NemotronAnalysis(BaseModel):
    """The structure Nemotron must return. Metadata is added by the service, not the model."""

    classification: Classification
    summary: str = Field(min_length=1, max_length=800)
    capacity_explanation: str = Field(min_length=1, max_length=1200)
    work_outcome: Outcome
    personal_outcome: Outcome
    risks: list[str] = Field(default_factory=list, max_length=6)


class WeeklyAnalysis(NemotronAnalysis):
    model_provider: Literal["Nebius Token Factory"] = "Nebius Token Factory"
    model_name: str
    source: Literal["nemotron", "fallback"]
    # Set only when source is "fallback": why the model result was not used.
    fallback_reason: str | None = None


class WeeklyAnalysisRequest(CapacityRequest):
    """Same input as the capacity calculation: a profile and calendar commitments."""


class WeeklyAnalysisResponse(BaseModel):
    capacity: CapacityResponse
    analysis: WeeklyAnalysis
