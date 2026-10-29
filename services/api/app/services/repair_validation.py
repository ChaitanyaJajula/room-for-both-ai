"""Independent Python check of a revised plan produced by OR-Tools for a repair candidate."""

from app.models.calendar import CalendarCommitment
from app.models.planning_profile import PlanningProfile
from app.models.repair import RepairValidation
from app.models.schedule import ScheduledBlock, ScheduleResponse
from app.services.capacity_engine import to_minutes
from app.services.scheduler import SLOT

Interval = tuple[int, int]


def _span(item: ScheduledBlock | CalendarCommitment) -> Interval:
    return to_minutes(item.start_time), to_minutes(item.end_time)


def _overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _grid_ceil(minutes: int) -> int:
    return -(-minutes // SLOT) * SLOT


def _hits_blocks(blocks: list[ScheduledBlock], day, interval: Interval) -> bool:
    return any(b.day == day and _overlaps(_span(b), interval) for b in blocks)


def _internal_overlap(blocks: list[ScheduledBlock]) -> bool:
    for i, first in enumerate(blocks):
        for second in blocks[i + 1 :]:
            if first.day == second.day and _overlaps(_span(first), _span(second)):
                return True
    return False


def _targets_consistent(
    plan: ScheduleResponse, target_work: int, target_personal: int
) -> bool:
    for kind, target, requested, grid_target, scheduled, unscheduled in (
        (
            "work",
            target_work,
            plan.requested_work_minutes,
            plan.target_work_minutes,
            plan.scheduled_work_minutes,
            plan.unscheduled_work_minutes,
        ),
        (
            "personal",
            target_personal,
            plan.requested_personal_minutes,
            plan.target_personal_minutes,
            plan.scheduled_personal_minutes,
            plan.unscheduled_personal_minutes,
        ),
    ):
        block_total = sum(b.duration_minutes for b in plan.blocks if b.outcome_type == kind)
        if not (
            requested == target
            and grid_target == _grid_ceil(target)
            and scheduled == block_total
            and scheduled + unscheduled == grid_target
            and 0 <= scheduled <= grid_target
        ):
            return False
    return True


def validate_revised_plan(
    plan: ScheduleResponse,
    profile: PlanningProfile,
    existing: list[CalendarCommitment],
    unexpected: CalendarCommitment,
    target_work: int,
    target_personal: int,
) -> RepairValidation:
    no_unexpected = not _hits_blocks(plan.blocks, unexpected.day, _span(unexpected))
    no_existing = not any(
        c.is_fixed and _hits_blocks(plan.blocks, c.day, _span(c)) for c in existing
    )
    no_hard = not any(
        _hits_blocks(plan.blocks, w.day, (to_minutes(w.start_time), to_minutes(w.end_time)))
        for boundary in profile.boundaries
        if boundary.is_hard
        for w in boundary.windows
    )
    no_internal = not _internal_overlap(plan.blocks)
    consistent = _targets_consistent(plan, target_work, target_personal)

    notes = []
    if plan.unscheduled_work_minutes:
        notes.append("Some work time did not fit and is left unscheduled.")
    if plan.unscheduled_personal_minutes:
        notes.append("Some personal time did not fit and is left unscheduled.")

    return RepairValidation(
        valid=all([no_unexpected, no_existing, no_hard, no_internal, consistent]),
        no_unexpected_commitment_overlap=no_unexpected,
        no_existing_commitment_overlap=no_existing,
        no_hard_boundary_overlap=no_hard,
        no_internal_block_overlap=no_internal,
        targets_consistent=consistent,
        notes=notes,
    )
