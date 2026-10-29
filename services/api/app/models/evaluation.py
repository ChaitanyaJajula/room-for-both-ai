import math
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EvaluationCategory = Literal["capacity", "scheduling", "conflict_detection", "repair_validation"]

SUITE_NAME = "Room for Both deterministic reliability suite"


class EvaluationCaseResult(BaseModel):
    id: str = Field(min_length=1)
    category: EvaluationCategory
    name: str = Field(min_length=1)
    passed: bool
    duration_ms: float
    checks_passed: int = Field(ge=0)
    checks_total: int = Field(gt=0)
    summary: str = Field(min_length=1)

    @field_validator("duration_ms")
    @classmethod
    def duration_is_finite_and_non_negative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("duration_ms must be finite and non-negative")
        return value

    @model_validator(mode="after")
    def passed_agrees_with_checks(self) -> "EvaluationCaseResult":
        if self.checks_passed > self.checks_total:
            raise ValueError("checks_passed cannot exceed checks_total")
        if self.passed != (self.checks_passed == self.checks_total):
            raise ValueError("passed must agree with checks_passed and checks_total")
        return self


class EvaluationSummary(BaseModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    pass_rate_percent: float
    total_checks: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    total_duration_ms: float

    @model_validator(mode="after")
    def totals_are_consistent(self) -> "EvaluationSummary":
        if self.passed_cases + self.failed_cases != self.total_cases:
            raise ValueError("passed_cases + failed_cases must equal total_cases")
        if self.passed_checks > self.total_checks:
            raise ValueError("passed_checks cannot exceed total_checks")
        if not math.isfinite(self.total_duration_ms) or self.total_duration_ms < 0:
            raise ValueError("total_duration_ms must be finite and non-negative")
        expected = 100 * self.passed_cases / self.total_cases if self.total_cases else 0.0
        if not math.isfinite(self.pass_rate_percent) or abs(self.pass_rate_percent - expected) > 0.01:
            raise ValueError("pass_rate_percent does not match the case totals")
        return self


class EvaluationReport(BaseModel):
    status: Literal["passed", "failed"]
    suite_name: Literal["Room for Both deterministic reliability suite"] = SUITE_NAME
    generated_at: datetime
    model_calls_made: Literal[0] = 0
    summary: EvaluationSummary
    cases: list[EvaluationCaseResult]
    architecture_guarantees: list[str]

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("generated_at must be a UTC timestamp")
        return value

    @model_validator(mode="after")
    def report_matches_cases(self) -> "EvaluationReport":
        ids = [case.id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("case ids must be unique")
        passed = sum(case.passed for case in self.cases)
        if (
            self.summary.total_cases != len(self.cases)
            or self.summary.passed_cases != passed
            or self.summary.total_checks != sum(case.checks_total for case in self.cases)
            or self.summary.passed_checks != sum(case.checks_passed for case in self.cases)
        ):
            raise ValueError("summary does not match the case results")
        if self.status != ("passed" if self.cases and passed == len(self.cases) else "failed"):
            raise ValueError("status must be passed only when every case passed")
        return self
