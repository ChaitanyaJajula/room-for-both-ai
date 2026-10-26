from datetime import time
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.planning_profile import DayOfWeek


class CommitmentCategory(str, Enum):
    work = "work"
    personal = "personal"


class CalendarCommitment(BaseModel):
    """A weekly recurring calendar entry within a single day (no overnight entries)."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    day: DayOfWeek
    start_time: time
    end_time: time
    category: CommitmentCategory
    is_fixed: bool = True
    description: str | None = None

    @field_validator("id", "title")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def end_must_be_after_start(self) -> "CalendarCommitment":
        if self.end_time <= self.start_time:
            raise ValueError(
                "end_time must be later than start_time; overnight commitments are not supported"
            )
        return self


class DemoCalendarResponse(BaseModel):
    name: str
    description: str
    commitments: list[CalendarCommitment]
