"""Deterministic repair candidates: Python sizes each one, OR-Tools reschedules, Python validates.

No LLM is involved here. A candidate is returned only if its revised plan is not infeasible
and passes every validation check.
"""

import logging
from dataclasses import dataclass

from app.models.analysis import Outcome
from app.models.calendar import CalendarCommitment
from app.models.conflict import ConflictResponse
from app.models.planning_profile import PlanningProfile
from app.models.repair import RepairOption, RepairStrategy
from app.models.schedule import ScheduledBlock, ScheduleResponse
from app.services.repair_validation import validate_revised_plan
from app.services.scheduler import SLOT, SchedulingError, generate_schedule

logger = logging.getLogger(__name__)

TITLES: dict[RepairStrategy, str] = {
    "move": "Move my plan around the new commitment",
    "simplify": "Shorten the outcomes that overlap",
    "delegate": "Delegate the affected work",
    "drop": "Drop the affected blocks",
}


@dataclass(frozen=True)
class Impact:
    """How much of each outcome a strategy gives up. All values are minutes."""

    reduced_work: int = 0
    reduced_personal: int = 0
    delegated_work: int = 0
    dropped_work: int = 0
    dropped_personal: int = 0

    @property
    def work_cut(self) -> int:
        return self.reduced_work + self.delegated_work + self.dropped_work

    @property
    def personal_cut(self) -> int:
        return self.reduced_personal + self.dropped_personal


def _round_up_to_slot(minutes: int) -> int:
    return -(-minutes // SLOT) * SLOT


def affected_blocks(conflict: ConflictResponse, plan: ScheduleResponse) -> list[ScheduledBlock]:
    """Unique approved-plan blocks hit by the conflict, in conflict (deterministic) order."""
    by_id = {b.id: b for b in plan.blocks}
    return [by_id[block_id] for block_id in conflict.affected_block_ids if block_id in by_id]


def _overlap_by_type(conflict: ConflictResponse, blocks: list[ScheduledBlock]) -> dict[str, int]:
    """Overlap minutes per outcome type, counting each affected block once."""
    overlap_by_block = {
        c.conflicting_item_id: c.overlap_minutes
        for c in conflict.conflicts
        if c.conflict_type == "scheduled_block"
    }
    totals = {"work": 0, "personal": 0}
    for block in blocks:
        totals[block.outcome_type] += overlap_by_block.get(block.id, 0)
    return totals


def _full_duration_by_type(blocks: list[ScheduledBlock]) -> dict[str, int]:
    totals = {"work": 0, "personal": 0}
    for block in blocks:
        totals[block.outcome_type] += block.duration_minutes
    return totals


def plan_impacts(
    conflict: ConflictResponse,
    plan: ScheduleResponse,
    work_minutes: int,
    personal_minutes: int,
) -> dict[RepairStrategy, Impact]:
    """The impact of each strategy that applies to this conflict, before any rescheduling."""
    blocks = affected_blocks(conflict, plan)
    overlap = _overlap_by_type(conflict, blocks)
    full = _full_duration_by_type(blocks)

    impacts: dict[RepairStrategy, Impact] = {"move": Impact()}
    impacts["simplify"] = Impact(
        reduced_work=min(_round_up_to_slot(overlap["work"]), work_minutes),
        reduced_personal=min(_round_up_to_slot(overlap["personal"]), personal_minutes),
    )
    if full["work"] > 0:  # delegating only makes sense for work
        impacts["delegate"] = Impact(delegated_work=min(full["work"], work_minutes))
    impacts["drop"] = Impact(
        dropped_work=min(full["work"], work_minutes),
        dropped_personal=min(full["personal"], personal_minutes),
    )
    return impacts


def build_candidate(
    strategy: RepairStrategy,
    impact: Impact,
    profile: PlanningProfile,
    commitments: list[CalendarCommitment],
    unexpected: CalendarCommitment,
    work_outcome: Outcome,
    personal_outcome: Outcome,
) -> RepairOption | None:
    """Reschedule with OR-Tools under the strategy's targets; None if unusable."""
    target_work = work_outcome.estimated_minutes - impact.work_cut
    target_personal = personal_outcome.estimated_minutes - impact.personal_cut
    fixed = [*commitments, unexpected]

    try:
        revised = generate_schedule(
            profile,
            fixed,
            work_outcome.model_copy(update={"estimated_minutes": target_work}),
            personal_outcome.model_copy(update={"estimated_minutes": target_personal}),
        )
    except SchedulingError:
        logger.warning("Repair candidate %s could not be scheduled safely", strategy)
        return None
    if revised.status == "infeasible":
        return None

    validation = validate_revised_plan(
        revised, profile, commitments, unexpected, target_work, target_personal
    )
    if not validation.valid:
        logger.warning("Repair candidate %s failed validation", strategy)
        return None

    return RepairOption(
        id=strategy,
        strategy=strategy,
        rank=0,
        title=TITLES[strategy],
        explanation="",
        recommended=False,
        revised_plan=revised,
        original_work_minutes=work_outcome.estimated_minutes,
        original_personal_minutes=personal_outcome.estimated_minutes,
        target_work_minutes=target_work,
        target_personal_minutes=target_personal,
        reduced_work_minutes=impact.reduced_work,
        reduced_personal_minutes=impact.reduced_personal,
        delegated_work_minutes=impact.delegated_work,
        dropped_work_minutes=impact.dropped_work,
        dropped_personal_minutes=impact.dropped_personal,
        validation=validation,
    )


def build_candidates(
    profile: PlanningProfile,
    commitments: list[CalendarCommitment],
    approved_plan: ScheduleResponse,
    unexpected: CalendarCommitment,
    work_outcome: Outcome,
    personal_outcome: Outcome,
    conflict: ConflictResponse,
) -> list[RepairOption]:
    impacts = plan_impacts(
        conflict,
        approved_plan,
        work_outcome.estimated_minutes,
        personal_outcome.estimated_minutes,
    )
    candidates = (
        build_candidate(
            strategy, impact, profile, commitments, unexpected, work_outcome, personal_outcome
        )
        for strategy, impact in impacts.items()
    )
    return [c for c in candidates if c is not None]
