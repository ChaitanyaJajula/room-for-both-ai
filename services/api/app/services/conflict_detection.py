"""Deterministic detection of conflicts caused by an unexpected fixed commitment.

Pure Python: no LLM, no network. Intervals are half-open minute ranges [start, end), so
back-to-back items never conflict. Inputs are only read, never modified.
"""

from datetime import time

from app.models.calendar import CalendarCommitment
from app.models.conflict import ConflictRecord, ConflictResponse, ConflictType
from app.models.planning_profile import PlanningProfile
from app.models.schedule import OutcomeType, ScheduleResponse
from app.services.capacity_engine import to_minutes

# Report order: scheduled blocks, then existing commitments, then hard boundaries.
_TYPE_ORDER: dict[ConflictType, int] = {
    "scheduled_block": 0,
    "existing_commitment": 1,
    "hard_boundary": 2,
}


def _time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _hhmm(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _record(
    kind: ConflictType,
    item_id: str,
    title: str,
    unexpected: CalendarCommitment,
    start: time,
    end: time,
    outcome_type: OutcomeType | None = None,
) -> ConflictRecord | None:
    overlap_start = max(to_minutes(unexpected.start_time), to_minutes(start))
    overlap_end = min(to_minutes(unexpected.end_time), to_minutes(end))
    if overlap_end <= overlap_start:
        return None
    return ConflictRecord(
        conflict_type=kind,
        conflicting_item_id=item_id,
        conflicting_item_title=title,
        day=unexpected.day,
        conflicting_start_time=start,
        conflicting_end_time=end,
        overlap_start_time=_time(overlap_start),
        overlap_end_time=_time(overlap_end),
        overlap_minutes=overlap_end - overlap_start,
        outcome_type=outcome_type,
    )


def _summary(item: CalendarCommitment, conflicts: list[ConflictRecord], affected: int) -> str:
    when = f"{item.day.value.capitalize()} {_hhmm(item.start_time)}-{_hhmm(item.end_time)}"
    if not conflicts:
        return (
            f"No conflicts: '{item.title}' on {when} does not overlap any approved plan "
            "block, existing fixed commitment or hard boundary."
        )
    counts = {kind: sum(c.conflict_type == kind for c in conflicts) for kind in _TYPE_ORDER}
    parts = []
    if counts["scheduled_block"]:
        parts.append(f"{affected} scheduled plan block(s)")
    if counts["existing_commitment"]:
        parts.append(f"{counts['existing_commitment']} existing commitment(s)")
    if counts["hard_boundary"]:
        parts.append(f"{counts['hard_boundary']} hard boundary window(s)")
    return f"'{item.title}' on {when} conflicts with " + ", ".join(parts) + "."


def detect_conflicts(
    profile: PlanningProfile,
    commitments: list[CalendarCommitment],
    approved_plan: ScheduleResponse,
    unexpected: CalendarCommitment,
) -> ConflictResponse:
    found: list[ConflictRecord] = []

    for block in approved_plan.blocks:
        if block.day == unexpected.day:
            record = _record(
                "scheduled_block",
                block.id,
                block.outcome_title,
                unexpected,
                block.start_time,
                block.end_time,
                block.outcome_type,
            )
            if record:
                found.append(record)

    for existing in commitments:
        if existing.is_fixed and existing.day == unexpected.day:
            record = _record(
                "existing_commitment",
                existing.id,
                existing.title,
                unexpected,
                existing.start_time,
                existing.end_time,
            )
            if record:
                found.append(record)

    for boundary in profile.boundaries:
        if not boundary.is_hard:
            continue  # soft boundaries are preferences, not hard conflicts
        for window in boundary.windows:
            if window.day == unexpected.day:
                record = _record(
                    "hard_boundary",
                    f"boundary:{boundary.name}",
                    boundary.name,
                    unexpected,
                    window.start_time,
                    window.end_time,
                )
                if record:
                    found.append(record)

    found.sort(
        key=lambda c: (
            _TYPE_ORDER[c.conflict_type],
            to_minutes(c.conflicting_start_time),
            to_minutes(c.conflicting_end_time),
            c.conflicting_item_id,
        )
    )

    affected: list[str] = []
    for c in found:
        if c.conflict_type == "scheduled_block" and c.conflicting_item_id not in affected:
            affected.append(c.conflicting_item_id)

    return ConflictResponse(
        status="conflict" if found else "clear",
        conflict_detected=bool(found),
        repair_required=bool(found),
        unexpected_commitment=unexpected,
        conflicts=found,
        affected_block_ids=affected,
        summary=_summary(unexpected, found, len(affected)),
    )
