from pydantic import BaseModel, Field, model_validator

from app.models.calendar import CalendarCommitment
from app.models.planning_profile import DayOfWeek, PlanningProfile


class CapacityRequest(BaseModel):
    profile: PlanningProfile
    commitments: list[CalendarCommitment] = Field(default_factory=list)

    @model_validator(mode="after")
    def commitment_ids_unique(self) -> "CapacityRequest":
        seen: set[str] = set()
        for commitment in self.commitments:
            if commitment.id in seen:
                raise ValueError(f"duplicate commitment id '{commitment.id}'")
            seen.add(commitment.id)
        return self


class DailyCapacity(BaseModel):
    day: DayOfWeek
    work_window_minutes: int
    occupied_minutes: int
    free_minutes: int
    reserved_break_minutes: int
    schedulable_focus_minutes: int
    # Fixed commitments that overlap this day's work hours, ordered by start time.
    commitment_ids: list[str]


class WeeklyCapacitySummary(BaseModel):
    work_window_minutes: int
    occupied_minutes: int
    free_minutes: int
    reserved_break_minutes: int
    schedulable_focus_minutes: int
    protected_personal_target_minutes: int


class OverlappingPair(BaseModel):
    day: DayOfWeek
    first_id: str
    second_id: str


class CapacitySignals(BaseModel):
    """Deterministic facts only; interpretation is left to a later phase."""

    zero_capacity_days: list[DayOfWeek]
    days_at_focus_cap: list[DayOfWeek]
    # Fixed commitments with no overlap with any work window (includes non-workdays).
    commitments_outside_work_hours: list[str]
    # Fixed commitments that overlap a work window but also extend beyond it.
    commitments_partially_outside_work_hours: list[str]
    overlapping_commitments: list[OverlappingPair]


class CapacityResponse(BaseModel):
    daily: list[DailyCapacity]
    weekly: WeeklyCapacitySummary
    signals: CapacitySignals
