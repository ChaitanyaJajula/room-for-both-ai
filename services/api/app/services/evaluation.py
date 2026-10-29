"""A fixed, deterministic reliability suite for the safety-critical (non-LLM) parts of the app.

Every run executes the same cases on in-code fixtures and calls the real capacity, scheduling,
conflict-detection and repair-validation services. It never imports or calls the model client,
accepts no input, and reports only what it computed. A case that raises is reported as a safe
failed case; the exception stays in the server log.
"""

import logging
import math
import time as clock
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from app.models.analysis import Outcome
from app.models.calendar import CalendarCommitment, CommitmentCategory
from app.models.conflict import ConflictResponse
from app.models.evaluation import (
    EvaluationCaseResult,
    EvaluationCategory,
    EvaluationReport,
    EvaluationSummary,
)
from app.models.planning_profile import Boundary, DayOfWeek, PlanningProfile, RecurringTimeWindow
from app.models.schedule import (
    ConstraintsSummary,
    ScheduledBlock,
    ScheduleResponse,
    SolverInfo,
)
from app.services.capacity_engine import calculate_capacity, merge_intervals, to_minutes
from app.services.conflict_detection import detect_conflicts
from app.services.demo_calendar import get_demo_calendar
from app.services.repair_candidates import build_candidates
from app.services.scheduler import generate_schedule

logger = logging.getLogger(__name__)

ARCHITECTURE_GUARANTEES = [
    "This suite makes no Nebius or Nemotron call.",
    "Weekly capacity is calculated deterministically in Python.",
    "Schedules are solved by Google OR-Tools CP-SAT and independently re-checked.",
    "Conflicts and repair options are detected and validated by Python.",
    "Model output can only rank or explain options that Python has already verified.",
]

WEEKDAYS = [
    DayOfWeek.monday,
    DayOfWeek.tuesday,
    DayOfWeek.wednesday,
    DayOfWeek.thursday,
    DayOfWeek.friday,
]
EXPECTED_STRATEGIES = {"move", "simplify", "delegate", "drop"}


# --- fixtures --------------------------------------------------------------------------------


def _window(day: DayOfWeek, start: tuple[int, int], end: tuple[int, int]) -> RecurringTimeWindow:
    return RecurringTimeWindow(day=day, start_time=time(*start), end_time=time(*end))


def _event(id: str, day: DayOfWeek, start: tuple[int, int], end: tuple[int, int]) -> CalendarCommitment:
    return CalendarCommitment(
        id=id,
        title=id,
        day=day,
        start_time=time(*start),
        end_time=time(*end),
        category=CommitmentCategory.work,
        is_fixed=True,
    )


def _balanced_profile() -> PlanningProfile:
    return PlanningProfile(
        timezone="UTC",
        work_hours=[_window(d, (9, 0), (17, 0)) for d in WEEKDAYS],
        preferred_focus_windows=[_window(d, (9, 0), (11, 30)) for d in WEEKDAYS],
        boundaries=[
            Boundary(
                name="Family dinner",
                windows=[_window(DayOfWeek.monday, (18, 0), (19, 30))],
                is_hard=True,
            )
        ],
        max_daily_focus_minutes=240,
        minimum_break_minutes=15,
        protected_personal_minutes_per_week=180,
    )


def _constrained_profile() -> PlanningProfile:
    return PlanningProfile(
        timezone="UTC",
        work_hours=[_window(d, (9, 0), (12, 0)) for d in WEEKDAYS[:3]],
        max_daily_focus_minutes=120,
        minimum_break_minutes=15,
        protected_personal_minutes_per_week=600,
    )


def _constrained_commitments() -> list[CalendarCommitment]:
    mon, tue, wed, sat = (DayOfWeek.monday, DayOfWeek.tuesday, DayOfWeek.wednesday, DayOfWeek.saturday)
    return [
        _event("mon-long-block", mon, (9, 0), (11, 15)),  # leaves 45 minutes: tight
        _event("tue-all-morning", tue, (9, 0), (12, 0)),  # leaves nothing: zero capacity
        _event("wed-first", wed, (9, 30), (10, 30)),
        _event("wed-second", wed, (10, 0), (11, 0)),  # overlaps the first
        _event("sat-outside", sat, (10, 0), (11, 0)),  # outside every work window
    ]


WORK_OUTCOME = Outcome(title="Focused project work", reason="Evaluation fixture", estimated_minutes=1200)
PERSONAL_OUTCOME = Outcome(
    title="Protected personal time", reason="Evaluation fixture", estimated_minutes=180
)


def _fixed_plan() -> ScheduleResponse:
    """A hand-written approved plan, so conflict cases do not depend on the solver."""

    def block(id, kind, day, start, end):
        minutes = (end[0] * 60 + end[1]) - (start[0] * 60 + start[1])
        return ScheduledBlock(
            id=id,
            outcome_type=kind,
            outcome_title=f"{kind} fixture",
            day=day,
            start_time=time(*start),
            end_time=time(*end),
            duration_minutes=minutes,
            inside_preferred_focus_window=False,
            uses_soft_boundary=False,
        )

    return ScheduleResponse(
        status="optimal",
        blocks=[
            block("work-monday-1000", "work", DayOfWeek.monday, (10, 0), (11, 30)),
            block("personal-friday-1300", "personal", DayOfWeek.friday, (13, 0), (16, 0)),
        ],
        requested_work_minutes=90,
        target_work_minutes=90,
        scheduled_work_minutes=90,
        unscheduled_work_minutes=0,
        requested_personal_minutes=180,
        target_personal_minutes=180,
        scheduled_personal_minutes=180,
        unscheduled_personal_minutes=0,
        solver=SolverInfo(status="OPTIMAL", wall_time_seconds=0.0),
        constraints_summary=ConstraintsSummary(
            candidate_slots=0,
            slots_blocked_by_commitments=0,
            slots_blocked_by_hard_boundaries=0,
            soft_boundary_slots=0,
            preferred_focus_slots=0,
            max_daily_work_minutes=240,
            minimum_break_minutes=15,
            rules=[],
        ),
        warnings=[],
    )


# --- helpers ---------------------------------------------------------------------------------


@dataclass
class Checks:
    results: list[bool] = field(default_factory=list)

    def check(self, condition: object) -> None:
        self.results.append(bool(condition))

    @property
    def passed(self) -> int:
        return sum(self.results)

    @property
    def total(self) -> int:
        return len(self.results)


def _span(item) -> tuple[int, int]:
    return to_minutes(item.start_time), to_minutes(item.end_time)


def _overlap_minutes(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def _count_hits(plan: ScheduleResponse, others: list[tuple[DayOfWeek, tuple[int, int]]]) -> int:
    return sum(
        1
        for block in plan.blocks
        for day, interval in others
        if block.day == day and _overlap_minutes(_span(block), interval) > 0
    )


def _internal_overlaps(plan: ScheduleResponse) -> int:
    return sum(
        1
        for i, first in enumerate(plan.blocks)
        for second in plan.blocks[i + 1 :]
        if first.day == second.day and _overlap_minutes(_span(first), _span(second)) > 0
    )


def _fixed_intervals(commitments: list[CalendarCommitment]) -> list[tuple[DayOfWeek, tuple[int, int]]]:
    return [(DayOfWeek(c.day), _span(c)) for c in commitments if c.is_fixed]


def _hard_intervals(profile: PlanningProfile) -> list[tuple[DayOfWeek, tuple[int, int]]]:
    return [
        (DayOfWeek(w.day), _span(w))
        for boundary in profile.boundaries
        if boundary.is_hard
        for w in boundary.windows
    ]


def _reconciles(plan: ScheduleResponse) -> bool:
    return (
        plan.scheduled_work_minutes + plan.unscheduled_work_minutes == plan.target_work_minutes
        and plan.scheduled_personal_minutes + plan.unscheduled_personal_minutes
        == plan.target_personal_minutes
        and plan.scheduled_work_minutes
        == sum(b.duration_minutes for b in plan.blocks if b.outcome_type == "work")
        and plan.scheduled_personal_minutes
        == sum(b.duration_minutes for b in plan.blocks if b.outcome_type == "personal")
    )


def _approved_plan(ctx: dict) -> ScheduleResponse:
    """The real OR-Tools plan for the balanced fixture, solved once per run."""
    if "plan" not in ctx:
        ctx["plan"] = generate_schedule(
            _balanced_profile(), get_demo_calendar().commitments, WORK_OUTCOME, PERSONAL_OUTCOME
        )
    return ctx["plan"]


# --- cases -----------------------------------------------------------------------------------


def _capacity_balanced(ctx: dict) -> Checks:
    profile = _balanced_profile()
    commitments = get_demo_calendar().commitments
    capacity = calculate_capacity(profile, commitments)
    ids = {c.id for c in commitments}
    daily, weekly = capacity.daily, capacity.weekly
    c = Checks()
    c.check({d.day for d in daily} == set(WEEKDAYS))
    c.check(
        all(
            min(
                d.work_window_minutes,
                d.occupied_minutes,
                d.free_minutes,
                d.reserved_break_minutes,
                d.schedulable_focus_minutes,
            )
            >= 0
            for d in daily
        )
    )
    c.check(all(d.schedulable_focus_minutes <= profile.max_daily_focus_minutes for d in daily))
    c.check(all(d.occupied_minutes + d.free_minutes == d.work_window_minutes for d in daily))
    c.check(weekly.work_window_minutes == sum(d.work_window_minutes for d in daily))
    c.check(weekly.occupied_minutes == sum(d.occupied_minutes for d in daily))
    c.check(weekly.free_minutes == sum(d.free_minutes for d in daily))
    c.check(weekly.reserved_break_minutes == sum(d.reserved_break_minutes for d in daily))
    c.check(weekly.schedulable_focus_minutes == sum(d.schedulable_focus_minutes for d in daily))
    c.check(all(set(d.commitment_ids) <= ids for d in daily))
    signals = capacity.signals
    c.check(
        set(signals.commitments_outside_work_hours) <= ids
        and set(signals.commitments_partially_outside_work_hours) <= ids
        and all({p.first_id, p.second_id} <= ids for p in signals.overlapping_commitments)
    )
    c.check(weekly.protected_personal_target_minutes == profile.protected_personal_minutes_per_week)
    return c


def _capacity_constrained(ctx: dict) -> Checks:
    profile = _constrained_profile()
    commitments = _constrained_commitments()
    capacity = calculate_capacity(profile, commitments)
    by_day = {d.day: d for d in capacity.daily}
    signals = capacity.signals
    c = Checks()
    c.check(DayOfWeek.tuesday in signals.zero_capacity_days)
    c.check(DayOfWeek.monday not in signals.zero_capacity_days)
    tuesday, monday = by_day.get(DayOfWeek.tuesday), by_day.get(DayOfWeek.monday)
    c.check(tuesday is not None and tuesday.free_minutes == 0 and tuesday.schedulable_focus_minutes == 0)
    c.check(monday is not None and monday.free_minutes == 45 and monday.schedulable_focus_minutes == 30)
    c.check(
        all(
            min(d.free_minutes, d.occupied_minutes, d.reserved_break_minutes, d.schedulable_focus_minutes)
            >= 0
            for d in capacity.daily
        )
    )
    c.check(any({p.first_id, p.second_id} == {"wed-first", "wed-second"} for p in signals.overlapping_commitments))
    c.check("sat-outside" in signals.commitments_outside_work_hours)
    c.check(capacity.weekly.protected_personal_target_minutes == 600)
    c.check(capacity.weekly.free_minutes == sum(d.free_minutes for d in capacity.daily))
    return c


def _schedule_validity(ctx: dict) -> Checks:
    profile = _balanced_profile()
    commitments = get_demo_calendar().commitments
    plan = _approved_plan(ctx)
    work_by_day: dict[tuple[DayOfWeek, str], list[tuple[int, int]]] = {}
    for b in plan.blocks:
        work_by_day.setdefault((b.day, b.outcome_type), []).append(_span(b))
    c = Checks()
    c.check(plan.status in ("optimal", "feasible"))
    c.check(plan.solver.name == "Google OR-Tools CP-SAT")
    c.check(len(plan.blocks) > 0)
    c.check(_internal_overlaps(plan) == 0)
    c.check(_count_hits(plan, _fixed_intervals(commitments)) == 0)
    c.check(_count_hits(plan, _hard_intervals(profile)) == 0)
    work_windows = [(DayOfWeek(w.day), _span(w)) for w in profile.work_hours]
    c.check(
        all(
            any(b.day == day and iv[0] <= _span(b)[0] and _span(b)[1] <= iv[1] for day, iv in work_windows)
            for b in plan.blocks
        )
    )
    merged_work = {
        day: merge_intervals(spans) for (day, kind), spans in work_by_day.items() if kind == "work"
    }
    c.check(
        all(sum(e - s for s, e in spans) <= profile.max_daily_focus_minutes for spans in merged_work.values())
    )
    c.check(
        all(
            nxt[0] - prev[1] >= profile.minimum_break_minutes
            for spans in merged_work.values()
            for prev, nxt in zip(spans, spans[1:])
        )
    )
    c.check(_reconciles(plan))
    c.check(
        plan.requested_work_minutes == WORK_OUTCOME.estimated_minutes
        and plan.requested_personal_minutes == PERSONAL_OUTCOME.estimated_minutes
    )
    c.check(plan.unscheduled_work_minutes == 0 and plan.unscheduled_personal_minutes == 0)
    return c


def _conflict_known(ctx: dict) -> Checks:
    profile = _balanced_profile()
    commitments = get_demo_calendar().commitments
    meeting = _event("eval-urgent-meeting", DayOfWeek.monday, (10, 15), (11, 0))
    result = detect_conflicts(profile, commitments, _fixed_plan(), meeting)
    record = result.conflicts[0] if result.conflicts else None
    c = Checks()
    c.check(result.conflict_detected is True)
    c.check(result.repair_required is True)
    c.check(result.status == "conflict")
    c.check(result.affected_block_ids == ["work-monday-1000"])
    c.check(len(result.conflicts) == 1)
    c.check(record is not None and record.conflict_type == "scheduled_block")
    c.check(record is not None and record.overlap_minutes == 45)
    c.check(record is not None and record.outcome_type == "work")
    return c


def _conflict_clear(ctx: dict) -> Checks:
    profile = _balanced_profile()
    commitments = get_demo_calendar().commitments
    event = _event("eval-early-call", DayOfWeek.tuesday, (6, 0), (6, 30))
    result = detect_conflicts(profile, commitments, _fixed_plan(), event)
    c = Checks()
    c.check(result.conflict_detected is False)
    c.check(result.repair_required is False)
    c.check(result.status == "clear")
    c.check(result.conflicts == [])
    c.check(result.affected_block_ids == [])
    return c


def _pick_meeting(plan: ScheduleResponse, profile: PlanningProfile, commitments) -> CalendarCommitment:
    """A 45-minute fixed meeting inside a planned work block and clear of other fixed time."""
    others = _fixed_intervals(commitments) + _hard_intervals(profile)
    for block in sorted(plan.blocks, key=lambda b: (list(DayOfWeek).index(DayOfWeek(b.day)), b.start_time)):
        if block.outcome_type != "work":
            continue
        start, end = _span(block)
        window = (start, start + 45)
        if window[1] <= end and not any(
            block.day == day and _overlap_minutes(window, iv) > 0 for day, iv in others
        ):
            return _event(
                "eval-urgent-meeting",
                DayOfWeek(block.day),
                (window[0] // 60, window[0] % 60),
                (window[1] // 60, window[1] % 60),
            )
    raise ValueError("no safe meeting window in the fixed plan")


def _repair_validation(ctx: dict) -> Checks:
    profile = _balanced_profile()
    commitments = get_demo_calendar().commitments
    plan = _approved_plan(ctx)
    meeting = _pick_meeting(plan, profile, commitments)
    conflict: ConflictResponse = detect_conflicts(profile, commitments, plan, meeting)
    options = build_candidates(
        profile, commitments, plan, meeting, WORK_OUTCOME, PERSONAL_OUTCOME, conflict
    )

    meeting_interval = [(DayOfWeek(meeting.day), _span(meeting))]
    strategies = [o.strategy for o in options]
    c = Checks()
    c.check(conflict.conflict_detected and all(r.conflict_type == "scheduled_block" for r in conflict.conflicts))
    for strategy in ("move", "simplify", "delegate", "drop"):
        c.check(strategy in strategies)
    c.check(len(set(strategies)) == len(strategies) == len(EXPECTED_STRATEGIES))
    c.check(bool(options) and all(o.revised_plan.status != "infeasible" for o in options))
    c.check(
        bool(options)
        and all(
            o.validation.valid
            and o.validation.no_unexpected_commitment_overlap
            and o.validation.no_existing_commitment_overlap
            and o.validation.no_hard_boundary_overlap
            and o.validation.no_internal_block_overlap
            and o.validation.targets_consistent
            for o in options
        )
    )
    c.check(bool(options) and all(_count_hits(o.revised_plan, meeting_interval) == 0 for o in options))
    c.check(
        bool(options)
        and all(_count_hits(o.revised_plan, _hard_intervals(profile)) == 0 for o in options)
    )
    c.check(
        bool(options)
        and all(_count_hits(o.revised_plan, _fixed_intervals(commitments)) == 0 for o in options)
    )
    c.check(bool(options) and all(_internal_overlaps(o.revised_plan) == 0 for o in options))
    c.check(bool(options) and all(_reconciles(o.revised_plan) for o in options))
    return c


@dataclass(frozen=True)
class _Case:
    id: str
    category: EvaluationCategory
    name: str
    run: Callable[[dict], Checks]
    passed_summary: str
    failed_summary: str


CASES: list[_Case] = [
    _Case(
        "capacity-balanced-week",
        "capacity",
        "Capacity invariants: balanced week",
        _capacity_balanced,
        "Daily and weekly capacity is non-negative, within the focus limit, and adds up.",
        "The capacity invariants did not pass.",
    ),
    _Case(
        "capacity-constrained-week",
        "capacity",
        "Capacity invariants: constrained week",
        _capacity_constrained,
        "A fully booked day shows zero capacity and nothing goes negative.",
        "The constrained-week capacity checks did not pass.",
    ),
    _Case(
        "schedule-validity",
        "scheduling",
        "OR-Tools schedule validity",
        _schedule_validity,
        "The OR-Tools schedule respects commitments, boundaries, limits and breaks, and reconciles.",
        "The scheduling invariants did not pass.",
    ),
    _Case(
        "conflict-known-overlap",
        "conflict_detection",
        "Conflict detection: known overlap",
        _conflict_known,
        "A meeting inside a planned block is detected with the correct block and overlap.",
        "The known-conflict checks did not pass.",
    ),
    _Case(
        "conflict-clear-event",
        "conflict_detection",
        "Conflict detection: clear event",
        _conflict_clear,
        "An event that touches nothing is reported as clear, with no repair required.",
        "The clear-event checks did not pass.",
    ),
    _Case(
        "repair-option-validation",
        "repair_validation",
        "Repair option validation",
        _repair_validation,
        "Every repair option was rescheduled by OR-Tools and passed Python validation.",
        "The repair validation checks did not pass.",
    ),
]


def _run_case(case: _Case, ctx: dict) -> EvaluationCaseResult:
    started = clock.monotonic()
    try:
        checks = case.run(ctx)
        passed, total = checks.passed, checks.total
    except Exception:
        # Details stay in the server log; the report only says the case did not pass.
        logger.exception("Evaluation case %s raised", case.id)
        passed, total = 0, 1
    elapsed_ms = round((clock.monotonic() - started) * 1000, 3)

    ok = passed == total
    summary = (
        case.passed_summary
        if ok
        else f"{case.failed_summary} ({passed} of {total} checks passed)"
    )
    return EvaluationCaseResult(
        id=case.id,
        category=case.category,
        name=case.name,
        passed=ok,
        duration_ms=elapsed_ms,
        checks_passed=passed,
        checks_total=total,
        summary=summary,
    )


def run_evaluation() -> EvaluationReport:
    ctx: dict = {}
    results = [_run_case(case, ctx) for case in CASES]

    passed_cases = sum(r.passed for r in results)
    total_duration = round(sum(r.duration_ms for r in results), 3)
    if not math.isfinite(total_duration):
        total_duration = 0.0
    return EvaluationReport(
        status="passed" if passed_cases == len(results) else "failed",
        generated_at=datetime.now(timezone.utc),
        summary=EvaluationSummary(
            total_cases=len(results),
            passed_cases=passed_cases,
            failed_cases=len(results) - passed_cases,
            pass_rate_percent=round(100 * passed_cases / len(results), 2),
            total_checks=sum(r.checks_total for r in results),
            passed_checks=sum(r.checks_passed for r in results),
            total_duration_ms=total_duration,
        ),
        cases=results,
        architecture_guarantees=ARCHITECTURE_GUARANTEES,
    )
