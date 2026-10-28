"""Deterministic weekly scheduling with Google OR-Tools CP-SAT. No LLM or network access.

The work-hours windows are the planning horizon. Every 15-minute slot inside them is a
candidate unless a fixed commitment or hard boundary overlaps it. CP-SAT chooses which
candidate slots hold the work outcome and which hold the personal outcome; the chosen slots
are then merged into blocks and re-checked in plain Python before anything is returned.
"""

import math
from datetime import time

from ortools.sat.python import cp_model

from app.models.analysis import Outcome
from app.models.calendar import CalendarCommitment
from app.models.planning_profile import DayOfWeek, PlanningProfile
from app.models.schedule import (
    ConstraintsSummary,
    ScheduledBlock,
    ScheduleResponse,
    SolverInfo,
)
from app.services.capacity_engine import Interval, merge_intervals, to_minutes

SLOT = 15
SLOTS_PER_DAY = 24 * 60 // SLOT
DAYS = list(DayOfWeek)  # Monday..Sunday

SOLVER_SEED = 42
SOLVER_MAX_SECONDS = 5.0

# Objective, in priority order. Weights are per 15-minute slot (or per block start). The
# tie-break term (earlier slots first) is scaled far below the smallest real weight.
W_PERSONAL = 1000  # protected personal time is scheduled before work
W_WORK = 800
W_FOCUS_FIT = 20  # work in a preferred focus window / personal outside one
W_SOFT_BOUNDARY = 60  # penalty per slot inside a soft boundary
W_BLOCK_START = 30  # penalty per separate block (fragmentation)
SCALE = 1_000_000

Slot = tuple[int, int]  # (day index, slot index within the day)


class SchedulingError(RuntimeError):
    """The solver failed, or its result did not pass final validation."""


def _slots_needed(minutes: int) -> int:
    return math.ceil(minutes / SLOT)


def _slot_interval(slot: Slot) -> Interval:
    return slot[1] * SLOT, slot[1] * SLOT + SLOT


def _overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _by_day(windows) -> dict[int, list[Interval]]:
    result: dict[int, list[Interval]] = {}
    for w in windows:
        result.setdefault(DAYS.index(w.day), []).append(
            (to_minutes(w.start_time), to_minutes(w.end_time))
        )
    return {d: merge_intervals(v) for d, v in result.items()}


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}{minutes % 60:02d}"


def _time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


class _Grid:
    """The candidate slots and the per-slot facts the model and the validator share."""

    def __init__(self, profile: PlanningProfile, commitments: list[CalendarCommitment]):
        self.work = _by_day(profile.work_hours)
        self.focus = _by_day(profile.preferred_focus_windows)
        self.fixed = _by_day(c for c in commitments if c.is_fixed)
        self.hard = _by_day(
            w for b in profile.boundaries if b.is_hard for w in b.windows
        )
        self.soft = _by_day(
            w for b in profile.boundaries if not b.is_hard for w in b.windows
        )

        self.candidates: list[Slot] = []
        self.in_window = 0
        self.blocked_by_commitments = 0
        self.blocked_by_hard = 0
        for day in sorted(self.work):
            for s in range(SLOTS_PER_DAY):
                iv = _slot_interval((day, s))
                if not any(w[0] <= iv[0] and iv[1] <= w[1] for w in self.work[day]):
                    continue
                self.in_window += 1
                by_commitment = self._hits(self.fixed, day, iv)
                by_hard = self._hits(self.hard, day, iv)
                self.blocked_by_commitments += by_commitment
                self.blocked_by_hard += by_hard
                if not (by_commitment or by_hard):
                    self.candidates.append((day, s))

        self.focus_slots = {
            sl for sl in self.candidates if self._inside(self.focus, sl[0], _slot_interval(sl))
        }
        self.soft_slots = {
            sl for sl in self.candidates if self._hits(self.soft, sl[0], _slot_interval(sl))
        }

    @staticmethod
    def _hits(by_day: dict[int, list[Interval]], day: int, iv: Interval) -> bool:
        return any(_overlaps(iv, w) for w in by_day.get(day, []))

    @staticmethod
    def _inside(by_day: dict[int, list[Interval]], day: int, iv: Interval) -> bool:
        return any(w[0] <= iv[0] and iv[1] <= w[1] for w in by_day.get(day, []))


def _longest_runs(grid: _Grid) -> dict[int, int]:
    """Longest stretch of consecutive candidate slots on each day."""
    longest: dict[int, int] = {}
    slots = set(grid.candidates)
    for day, index in grid.candidates:
        if (day, index - 1) in slots:
            continue
        length = 0
        while (day, index + length) in slots:
            length += 1
        longest[day] = max(longest.get(day, 0), length)
    return longest


def _solve(
    grid: _Grid,
    profile: PlanningProfile,
    work_slots: int,
    personal_slots: int,
) -> tuple[dict[Slot, str], int, float | None, float]:
    """Run CP-SAT. Returns (slot -> "work"|"personal", solver status, objective, seconds)."""
    model = cp_model.CpModel()
    w = {sl: model.new_bool_var(f"w_{sl[0]}_{sl[1]}") for sl in grid.candidates}
    p = {sl: model.new_bool_var(f"p_{sl[0]}_{sl[1]}") for sl in grid.candidates}

    for sl in grid.candidates:  # one thing per slot
        model.add(w[sl] + p[sl] <= 1)

    model.add(sum(w.values()) <= work_slots)
    model.add(sum(p.values()) <= personal_slots)

    max_daily_slots = profile.max_daily_focus_minutes // SLOT
    break_slots = _slots_needed(profile.minimum_break_minutes)
    for day in {sl[0] for sl in grid.candidates}:
        model.add(sum(v for sl, v in w.items() if sl[0] == day) <= max_daily_slots)
        # After a work block ends at slot s, the next B-1 slots after the first empty slot
        # stay empty too, so separate work blocks are at least `break_slots` apart.
        for s in range(SLOTS_PER_DAY):
            here = w.get((day, s))
            if here is None:
                continue
            after = w.get((day, s + 1))
            for k in range(1, break_slots):
                later = w.get((day, s + 1 + k))
                if later is None:
                    continue
                if after is None:
                    model.add(here + later <= 1)
                else:
                    model.add(here - after + later <= 1)

    objective = []
    for sl in grid.candidates:
        focus = sl in grid.focus_slots
        soft = sl in grid.soft_slots
        work_value = W_WORK + (W_FOCUS_FIT if focus else 0) - (W_SOFT_BOUNDARY if soft else 0)
        personal_value = (
            W_PERSONAL + (0 if focus else W_FOCUS_FIT) - (W_SOFT_BOUNDARY if soft else 0)
        )
        objective.append(w[sl] * work_value * SCALE)
        objective.append(p[sl] * (personal_value * SCALE - 0))

    # Fragmentation: each run of a type pays once, at the slot where the run starts. The
    # per-day cut (a run holds at most `longest` slots) keeps the LP bound tight enough for
    # CP-SAT to prove optimality quickly.
    longest = _longest_runs(grid)
    for kind, variables in (("w", w), ("p", p)):
        starts: dict[int, list] = {}
        for sl, var in variables.items():
            previous = variables.get((sl[0], sl[1] - 1))
            start = model.new_bool_var(f"start_{kind}_{sl[0]}_{sl[1]}")
            model.add(start >= var - (previous if previous is not None else 0))
            objective.append(start * -(W_BLOCK_START * SCALE))
            starts.setdefault(sl[0], []).append(start)
        for day, day_starts in starts.items():
            limit = longest[day] if kind == "p" else min(longest[day], max_daily_slots)
            day_vars = [v for sl, v in variables.items() if sl[0] == day]
            model.add(sum(day_vars) <= limit * sum(day_starts))

    model.maximize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.random_seed = SOLVER_SEED
    solver.parameters.num_workers = 1
    solver.parameters.linearization_level = 2
    # Every weight is a multiple of 10, so a gap below 10 units is a proof of optimality.
    solver.parameters.absolute_gap_limit = 9 * SCALE
    solver.parameters.max_time_in_seconds = SOLVER_MAX_SECONDS
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SchedulingError(f"solver ended with status {solver.status_name(status)}")

    assignment: dict[Slot, str] = {}
    for sl in grid.candidates:
        if solver.value(w[sl]):
            assignment[sl] = "work"
        elif solver.value(p[sl]):
            assignment[sl] = "personal"
    return assignment, status, solver.objective_value / SCALE, solver.wall_time


def _build_blocks(
    grid: _Grid,
    assignment: dict[Slot, str],
    titles: dict[str, str],
) -> list[ScheduledBlock]:
    """Merge consecutive slots of one outcome into blocks, split where the flags change."""
    blocks: list[ScheduledBlock] = []
    run: list[Slot] = []
    run_key: tuple | None = None

    def flush() -> None:
        if not run:
            return
        kind = assignment[run[0]]
        start = run[0][1] * SLOT
        end = (run[-1][1] + 1) * SLOT
        day = DAYS[run[0][0]]
        blocks.append(
            ScheduledBlock(
                id=f"{kind}-{day.value}-{_hhmm(start)}",
                outcome_type=kind,
                outcome_title=titles[kind],
                day=day,
                start_time=_time(start),
                end_time=_time(end),
                duration_minutes=end - start,
                inside_preferred_focus_window=run[0] in grid.focus_slots,
                uses_soft_boundary=run[0] in grid.soft_slots,
            )
        )

    for sl in sorted(assignment):
        key = (assignment[sl], sl[0], sl in grid.focus_slots, sl in grid.soft_slots)
        if run and (key != run_key or sl[1] != run[-1][1] + 1):
            flush()
            run = []
        run.append(sl)
        run_key = key
    flush()
    return blocks


def _validate(
    grid: _Grid,
    profile: PlanningProfile,
    blocks: list[ScheduledBlock],
    work_slots: int,
    personal_slots: int,
) -> None:
    """Independent check of the final blocks; raises SchedulingError if anything is unsafe."""

    def fail(reason: str) -> None:
        raise SchedulingError(f"schedule failed validation: {reason}")

    intervals: dict[int, list[tuple[Interval, ScheduledBlock]]] = {}
    for b in blocks:
        day = DAYS.index(b.day)
        iv = (to_minutes(b.start_time), to_minutes(b.end_time))
        if iv[0] % SLOT or iv[1] % SLOT or iv[1] - iv[0] != b.duration_minutes or iv[1] <= iv[0]:
            fail(f"{b.id} is not on the {SLOT}-minute grid")
        if not any(w[0] <= iv[0] and iv[1] <= w[1] for w in grid.work.get(day, [])):
            fail(f"{b.id} is outside work hours")
        for name, source in (("a fixed commitment", grid.fixed), ("a hard boundary", grid.hard)):
            if any(_overlaps(iv, other) for other in source.get(day, [])):
                fail(f"{b.id} overlaps {name}")
        if b.inside_preferred_focus_window != _Grid._inside(grid.focus, day, iv):
            fail(f"{b.id} has a wrong focus flag")
        if b.uses_soft_boundary != _Grid._hits(grid.soft, day, iv):
            fail(f"{b.id} has a wrong soft-boundary flag")
        intervals.setdefault(day, []).append((iv, b))

    for day, items in intervals.items():
        ordered = sorted(items, key=lambda item: item[0])
        for (a, _), (b, other) in zip(ordered, ordered[1:]):
            if a[1] > b[0]:
                fail(f"{other.id} overlaps another block")
        work = merge_intervals([iv for iv, blk in ordered if blk.outcome_type == "work"])
        if sum(e - s for s, e in work) > profile.max_daily_focus_minutes:
            fail(f"{DAYS[day].value} exceeds the daily focus limit")
        for (_, prev_end), (next_start, _) in zip(work, work[1:]):
            if next_start - prev_end < profile.minimum_break_minutes:
                fail(f"{DAYS[day].value} has a work gap shorter than the minimum break")

    for kind, limit in (("work", work_slots), ("personal", personal_slots)):
        if sum(b.duration_minutes for b in blocks if b.outcome_type == kind) > limit * SLOT:
            fail(f"{kind} time exceeds its target")


def generate_schedule(
    profile: PlanningProfile,
    commitments: list[CalendarCommitment],
    work_outcome: Outcome,
    personal_outcome: Outcome,
) -> ScheduleResponse:
    grid = _Grid(profile, commitments)
    work_slots = _slots_needed(work_outcome.estimated_minutes)
    personal_slots = _slots_needed(personal_outcome.estimated_minutes)

    assignment, status, objective, seconds = _solve(grid, profile, work_slots, personal_slots)
    blocks = _build_blocks(
        grid, assignment, {"work": work_outcome.title, "personal": personal_outcome.title}
    )
    _validate(grid, profile, blocks, work_slots, personal_slots)

    scheduled = {
        kind: sum(b.duration_minutes for b in blocks if b.outcome_type == kind)
        for kind in ("work", "personal")
    }
    targets = {"work": work_slots * SLOT, "personal": personal_slots * SLOT}
    complete = all(scheduled[k] == targets[k] for k in scheduled)

    if complete:
        plan_status = "optimal" if status == cp_model.OPTIMAL else "feasible"
    elif blocks:
        plan_status = "partial"
    else:
        plan_status = "infeasible"

    warnings: list[str] = []
    for label, outcome in (("Work", work_outcome), ("Personal", personal_outcome)):
        if outcome.estimated_minutes % SLOT:
            warnings.append(
                f"{label} outcome of {outcome.estimated_minutes} minutes was rounded up to "
                f"{_slots_needed(outcome.estimated_minutes) * SLOT} minutes "
                f"for the {SLOT}-minute grid."
            )
    for kind in ("work", "personal"):
        if scheduled[kind] < targets[kind]:
            warnings.append(
                f"Only {scheduled[kind]} of {targets[kind]} {kind} minutes could be scheduled."
            )
    if any(b.uses_soft_boundary for b in blocks):
        warnings.append("Some blocks fall inside a soft boundary because no free time avoided it.")

    return ScheduleResponse(
        status=plan_status,
        blocks=blocks,
        requested_work_minutes=work_outcome.estimated_minutes,
        target_work_minutes=targets["work"],
        scheduled_work_minutes=scheduled["work"],
        unscheduled_work_minutes=targets["work"] - scheduled["work"],
        requested_personal_minutes=personal_outcome.estimated_minutes,
        target_personal_minutes=targets["personal"],
        scheduled_personal_minutes=scheduled["personal"],
        unscheduled_personal_minutes=targets["personal"] - scheduled["personal"],
        solver=SolverInfo(
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            objective_value=round(objective, 3) if objective is not None else None,
            wall_time_seconds=round(seconds, 3),
        ),
        constraints_summary=ConstraintsSummary(
            candidate_slots=len(grid.candidates),
            slots_blocked_by_commitments=grid.blocked_by_commitments,
            slots_blocked_by_hard_boundaries=grid.blocked_by_hard,
            soft_boundary_slots=len(grid.soft_slots),
            preferred_focus_slots=len(grid.focus_slots),
            max_daily_work_minutes=profile.max_daily_focus_minutes,
            minimum_break_minutes=profile.minimum_break_minutes,
            rules=[
                "Work hours are the planning horizon for both outcomes.",
                "Fixed commitments and hard boundaries are never overlapped.",
                "Blocks never overlap each other.",
                "Work per day stays within the daily focus limit.",
                "Separate work blocks are at least the minimum break apart.",
                "Soft boundaries are avoided when possible.",
            ],
        ),
        warnings=warnings,
    )
