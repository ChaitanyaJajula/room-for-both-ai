from datetime import time
from typing import Literal

from pydantic import BaseModel, model_validator

from app.models.calendar import CalendarCommitment
from app.models.capacity import CapacityRequest
from app.models.planning_profile import DayOfWeek
from app.models.schedule import OutcomeType, ScheduleResponse

ConflictType = Literal["scheduled_block", "existing_commitment", "hard_boundary"]


class ConflictRequest(CapacityRequest):
    """Profile and existing commitments (ids already unique) plus the plan and the new item."""

    approved_plan: ScheduleResponse
    unexpected_commitment: CalendarCommitment

    @model_validator(mode="after")
    def unexpected_commitment_is_valid(self) -> "ConflictRequest":
        if not self.unexpected_commitment.is_fixed:
            raise ValueError("unexpected_commitment must be fixed")
        if any(c.id == self.unexpected_commitment.id for c in self.commitments):
            raise ValueError(
                f"unexpected_commitment id '{self.unexpected_commitment.id}' "
                "duplicates an existing commitment id"
            )
        return self


class ConflictRecord(BaseModel):
    conflict_type: ConflictType
    conflicting_item_id: str
    conflicting_item_title: str
    day: DayOfWeek
    conflicting_start_time: time
    conflicting_end_time: time
    overlap_start_time: time
    overlap_end_time: time
    overlap_minutes: int
    outcome_type: OutcomeType | None = None


class ConflictResponse(BaseModel):
    status: Literal["clear", "conflict"]
    conflict_detected: bool
    # Always equals conflict_detected: any conflict needs the user to resolve it, even when no
    # approved-plan block is affected (see affected_block_ids).
    repair_required: bool
    unexpected_commitment: CalendarCommitment
    conflicts: list[ConflictRecord]
    affected_block_ids: list[str]
    summary: str
