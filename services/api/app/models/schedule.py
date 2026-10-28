from datetime import time
from typing import Literal

from pydantic import BaseModel, field_validator

from app.models.analysis import Outcome
from app.models.capacity import CapacityRequest
from app.models.planning_profile import DayOfWeek

OutcomeType = Literal["work", "personal"]
PlanStatus = Literal["optimal", "feasible", "partial", "infeasible"]


class ScheduleRequest(CapacityRequest):
    """Profile and fixed commitments (validated by CapacityRequest) plus the two outcomes."""

    work_outcome: Outcome
    personal_outcome: Outcome

    @field_validator("work_outcome", "personal_outcome")
    @classmethod
    def title_not_blank(cls, outcome: Outcome) -> Outcome:
        if not outcome.title.strip():
            raise ValueError("outcome title must not be blank")
        return outcome


class ScheduledBlock(BaseModel):
    id: str
    outcome_type: OutcomeType
    outcome_title: str
    day: DayOfWeek
    start_time: time
    end_time: time
    duration_minutes: int
    inside_preferred_focus_window: bool
    uses_soft_boundary: bool


class SolverInfo(BaseModel):
    name: Literal["Google OR-Tools CP-SAT"] = "Google OR-Tools CP-SAT"
    status: str
    objective_value: float | None = None
    wall_time_seconds: float


class ConstraintsSummary(BaseModel):
    candidate_slots: int
    slots_blocked_by_commitments: int
    slots_blocked_by_hard_boundaries: int
    soft_boundary_slots: int
    preferred_focus_slots: int
    max_daily_work_minutes: int
    minimum_break_minutes: int
    rules: list[str]


class ScheduleResponse(BaseModel):
    status: PlanStatus
    slot_minutes: Literal[15] = 15
    blocks: list[ScheduledBlock]
    # "requested" is the outcome's own estimate; "target" is that rounded up to the 15-minute
    # grid, which is what the solver tries to place. Nothing is ever scheduled below the target
    # silently: any shortfall is reported as unscheduled.
    requested_work_minutes: int
    target_work_minutes: int
    scheduled_work_minutes: int
    unscheduled_work_minutes: int
    requested_personal_minutes: int
    target_personal_minutes: int
    scheduled_personal_minutes: int
    unscheduled_personal_minutes: int
    solver: SolverInfo
    constraints_summary: ConstraintsSummary
    warnings: list[str]
