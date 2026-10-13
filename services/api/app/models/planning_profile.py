from enum import Enum
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class DayOfWeek(str, Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"
    saturday = "saturday"
    sunday = "sunday"


class RecurringTimeWindow(BaseModel):
    """A weekly recurring window within a single day (no overnight windows)."""

    day: DayOfWeek
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def end_must_be_after_start(self) -> "RecurringTimeWindow":
        if self.end_time <= self.start_time:
            raise ValueError(
                "end_time must be later than start_time; overnight windows are not supported"
            )
        return self


class Boundary(BaseModel):
    name: str = Field(min_length=1)
    windows: list[RecurringTimeWindow] = Field(min_length=1)
    is_hard: bool = True

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class PlanningProfile(BaseModel):
    timezone: str
    work_hours: list[RecurringTimeWindow] = Field(min_length=1)
    preferred_focus_windows: list[RecurringTimeWindow] = Field(default_factory=list)
    boundaries: list[Boundary] = Field(default_factory=list)
    max_daily_focus_minutes: int = Field(default=240, ge=30, le=480)
    minimum_break_minutes: int = Field(default=15, ge=5, le=120)
    protected_personal_minutes_per_week: int = Field(default=180, ge=0, le=10080)

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_valid_iana(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError(f"'{value}' is not a valid IANA timezone name") from exc
        return value
