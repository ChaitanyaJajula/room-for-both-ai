from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from app.models.analysis import Outcome
from app.models.conflict import ConflictRequest, ConflictResponse
from app.models.schedule import ScheduleResponse

RepairStrategy = Literal["move", "simplify", "delegate", "drop"]
RepairStatus = Literal[
    "not_needed", "manual_resolution_required", "options_ready", "no_valid_options"
]
ReasoningSource = Literal["nemotron", "fallback", "not_used"]


class RepairRequest(ConflictRequest):
    """ConflictRequest rules (fixed, unique unexpected commitment) plus the two outcomes."""

    work_outcome: Outcome
    personal_outcome: Outcome

    @field_validator("work_outcome", "personal_outcome")
    @classmethod
    def title_not_blank(cls, outcome: Outcome) -> Outcome:
        if not outcome.title.strip():
            raise ValueError("outcome title must not be blank")
        return outcome

    @model_validator(mode="after")
    def outcomes_match_approved_plan(self) -> "RepairRequest":
        if self.work_outcome.estimated_minutes != self.approved_plan.requested_work_minutes:
            raise ValueError("work_outcome.estimated_minutes must equal the approved plan's request")
        if (
            self.personal_outcome.estimated_minutes
            != self.approved_plan.requested_personal_minutes
        ):
            raise ValueError(
                "personal_outcome.estimated_minutes must equal the approved plan's request"
            )
        return self


class RepairValidation(BaseModel):
    valid: bool
    no_unexpected_commitment_overlap: bool
    no_existing_commitment_overlap: bool
    no_hard_boundary_overlap: bool
    no_internal_block_overlap: bool
    targets_consistent: bool
    notes: list[str]


class RepairOption(BaseModel):
    id: RepairStrategy
    strategy: RepairStrategy
    rank: int
    title: str
    explanation: str
    recommended: bool
    revised_plan: ScheduleResponse
    original_work_minutes: int
    original_personal_minutes: int
    target_work_minutes: int
    target_personal_minutes: int
    reduced_work_minutes: int
    reduced_personal_minutes: int
    delegated_work_minutes: int
    dropped_work_minutes: int
    dropped_personal_minutes: int
    validation: RepairValidation


class RepairResponse(BaseModel):
    status: RepairStatus
    conflict: ConflictResponse
    options: list[RepairOption]
    recommended_option_id: RepairStrategy | None
    reasoning_source: ReasoningSource
    model_provider: Literal["Nebius Token Factory"] = "Nebius Token Factory"
    model_name: str
    fallback_message: str | None = None
