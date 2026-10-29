"""Repair orchestration: detect, build verified candidates, then rank them.

Order matters: Nemotron is consulted only after Python has detected a plan conflict and
produced at least one validated candidate.
"""

from app.core.config import get_settings
from app.models.repair import RepairRequest, RepairResponse
from app.services.conflict_detection import detect_conflicts
from app.services.repair_candidates import build_candidates
from app.services.repair_ranking import FALLBACK_MESSAGE, rank_options


def _response(status, conflict, options=(), recommended=None, source="not_used", message=None):
    return RepairResponse(
        status=status,
        conflict=conflict,
        options=list(options),
        recommended_option_id=recommended,
        reasoning_source=source,
        model_name=get_settings().NEMOTRON_FAST_MODEL,
        fallback_message=message,
    )


def build_repair_options(request: RepairRequest) -> RepairResponse:
    conflict = detect_conflicts(
        request.profile,
        request.commitments,
        request.approved_plan,
        request.unexpected_commitment,
    )
    if not conflict.conflict_detected:
        return _response("not_needed", conflict)

    # Two fixed obligations collide: OR-Tools can move plan blocks but not these.
    if any(c.conflict_type != "scheduled_block" for c in conflict.conflicts):
        return _response("manual_resolution_required", conflict)

    candidates = build_candidates(
        request.profile,
        request.commitments,
        request.approved_plan,
        request.unexpected_commitment,
        request.work_outcome,
        request.personal_outcome,
        conflict,
    )
    if not candidates:
        return _response("no_valid_options", conflict)

    ranking, source = rank_options(conflict, candidates)
    by_id = {c.id: c for c in candidates}
    options = [
        by_id[item.candidate_id].model_copy(
            update={"rank": rank, "explanation": item.explanation, "recommended": rank == 1}
        )
        for rank, item in enumerate(ranking, start=1)
    ]
    return _response(
        "options_ready",
        conflict,
        options,
        recommended=options[0].id,
        source=source,
        message=FALLBACK_MESSAGE if source == "fallback" else None,
    )
