"""Deterministic weekly-capacity calculation. No LLM or network access."""

from datetime import time

from app.models.calendar import CalendarCommitment
from app.models.capacity import (
    CapacityResponse,
    CapacitySignals,
    DailyCapacity,
    OverlappingPair,
    WeeklyCapacitySummary,
)
from app.models.planning_profile import DayOfWeek, PlanningProfile

# Half-open interval in whole minutes since midnight: [start, end).
Interval = tuple[int, int]


def to_minutes(value: time) -> int:
    """Whole minutes since midnight; seconds are truncated."""
    return value.hour * 60 + value.minute


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping or touching intervals so no minute is counted twice."""
    merged: list[Interval] = []
    for start, end in sorted(i for i in intervals if i[1] > i[0]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def total_minutes(intervals: list[Interval]) -> int:
    return sum(end - start for start, end in intervals)


def clip(interval: Interval, windows: list[Interval]) -> list[Interval]:
    """Parts of `interval` that fall inside any of the (merged) `windows`."""
    pieces = []
    for w_start, w_end in windows:
        start, end = max(interval[0], w_start), min(interval[1], w_end)
        if end > start:
            pieces.append((start, end))
    return pieces


def _commitment_interval(c: CalendarCommitment) -> Interval:
    return to_minutes(c.start_time), to_minutes(c.end_time)


def calculate_capacity(
    profile: PlanningProfile, commitments: list[CalendarCommitment]
) -> CapacityResponse:
    # Only fixed commitments are treated as unavailable time.
    fixed = [c for c in commitments if c.is_fixed]

    work_by_day: dict[DayOfWeek, list[Interval]] = {}
    for window in profile.work_hours:
        work_by_day.setdefault(window.day, []).append(
            (to_minutes(window.start_time), to_minutes(window.end_time))
        )
    work_by_day = {day: merge_intervals(w) for day, w in work_by_day.items()}

    daily: list[DailyCapacity] = []
    for day in DayOfWeek:  # Monday..Sunday order
        windows = work_by_day.get(day)
        if not windows:
            continue

        work_minutes = total_minutes(windows)
        day_commitments = sorted(
            (c for c in fixed if c.day == day), key=lambda c: (_commitment_interval(c), c.id)
        )

        clipped: list[Interval] = []
        relevant_ids: list[str] = []
        for c in day_commitments:
            pieces = clip(_commitment_interval(c), windows)
            if pieces:
                clipped.extend(pieces)
                relevant_ids.append(c.id)

        occupied = total_minutes(merge_intervals(clipped))
        free = work_minutes - occupied
        # The break is reserved once per day, and never more than the time available.
        reserved_break = min(profile.minimum_break_minutes, free) if free > 0 else 0
        focus = max(0, min(profile.max_daily_focus_minutes, free - reserved_break))

        daily.append(
            DailyCapacity(
                day=day,
                work_window_minutes=work_minutes,
                occupied_minutes=occupied,
                free_minutes=free,
                reserved_break_minutes=reserved_break,
                schedulable_focus_minutes=focus,
                commitment_ids=relevant_ids,
            )
        )

    weekly = WeeklyCapacitySummary(
        work_window_minutes=sum(d.work_window_minutes for d in daily),
        occupied_minutes=sum(d.occupied_minutes for d in daily),
        free_minutes=sum(d.free_minutes for d in daily),
        reserved_break_minutes=sum(d.reserved_break_minutes for d in daily),
        schedulable_focus_minutes=sum(d.schedulable_focus_minutes for d in daily),
        protected_personal_target_minutes=profile.protected_personal_minutes_per_week,
    )

    return CapacityResponse(
        daily=daily,
        weekly=weekly,
        signals=_signals(profile, daily, fixed, work_by_day),
    )


def _signals(
    profile: PlanningProfile,
    daily: list[DailyCapacity],
    fixed: list[CalendarCommitment],
    work_by_day: dict[DayOfWeek, list[Interval]],
) -> CapacitySignals:
    outside: list[str] = []
    partial: list[str] = []
    for c in fixed:
        interval = _commitment_interval(c)
        overlap = total_minutes(merge_intervals(clip(interval, work_by_day.get(c.day, []))))
        if overlap == 0:
            outside.append(c.id)
        elif overlap < interval[1] - interval[0]:
            partial.append(c.id)

    overlaps: list[OverlappingPair] = []
    for day in DayOfWeek:
        day_items = sorted(
            (c for c in fixed if c.day == day), key=lambda c: (_commitment_interval(c), c.id)
        )
        for i, first in enumerate(day_items):
            first_end = _commitment_interval(first)[1]
            for second in day_items[i + 1 :]:
                # Sorted by start, so once a later item starts at/after first ends, stop.
                if _commitment_interval(second)[0] >= first_end:
                    break
                overlaps.append(OverlappingPair(day=day, first_id=first.id, second_id=second.id))

    return CapacitySignals(
        zero_capacity_days=[d.day for d in daily if d.schedulable_focus_minutes == 0],
        days_at_focus_cap=[
            d.day
            for d in daily
            if d.schedulable_focus_minutes > 0
            and d.schedulable_focus_minutes == profile.max_daily_focus_minutes
        ],
        commitments_outside_work_hours=outside,
        commitments_partially_outside_work_hours=partial,
        overlapping_commitments=overlaps,
    )
