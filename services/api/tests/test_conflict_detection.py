from datetime import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.calendar import CalendarCommitment, CommitmentCategory
from app.models.conflict import ConflictRequest
from app.models.planning_profile import (
    Boundary,
    DayOfWeek,
    PlanningProfile,
    RecurringTimeWindow,
)
from app.models.schedule import (
    ConstraintsSummary,
    ScheduledBlock,
    ScheduleResponse,
    SolverInfo,
)
from app.services.conflict_detection import detect_conflicts

client = TestClient(app)
URL = "/api/v1/conflicts/detect"
MON, TUE = DayOfWeek.monday, DayOfWeek.tuesday
WEEKDAYS = [MON, TUE, DayOfWeek.wednesday, DayOfWeek.thursday, DayOfWeek.friday]


def t(hhmm: str) -> time:
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def window(day, start, end):
    return RecurringTimeWindow(day=day, start_time=t(start), end_time=t(end))


def profile(boundaries=()):
    return PlanningProfile(
        timezone="UTC",
        work_hours=[window(d, "09:00", "17:00") for d in WEEKDAYS],
        boundaries=list(boundaries),
    )


def block(id, start, end, day=MON, kind="work"):
    return ScheduledBlock(
        id=id,
        outcome_type=kind,
        outcome_title=f"{kind} outcome",
        day=day,
        start_time=t(start),
        end_time=t(end),
        duration_minutes=(t(end).hour * 60 + t(end).minute) - (t(start).hour * 60 + t(start).minute),
        inside_preferred_focus_window=False,
        uses_soft_boundary=False,
    )


def plan(*blocks) -> ScheduleResponse:
    return ScheduleResponse(
        status="optimal",
        blocks=list(blocks),
        requested_work_minutes=0,
        target_work_minutes=0,
        scheduled_work_minutes=0,
        unscheduled_work_minutes=0,
        requested_personal_minutes=0,
        target_personal_minutes=0,
        scheduled_personal_minutes=0,
        unscheduled_personal_minutes=0,
        solver=SolverInfo(status="OPTIMAL", wall_time_seconds=0.1),
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


def event(id, start, end, day=MON, is_fixed=True, title=None):
    return CalendarCommitment(
        id=id,
        title=title or id,
        day=day,
        start_time=t(start),
        end_time=t(end),
        category=CommitmentCategory.work,
        is_fixed=is_fixed,
    )


def detect(unexpected, blocks=(), commitments=(), boundaries=()):
    return detect_conflicts(profile(boundaries), list(commitments), plan(*blocks), unexpected)


# --- service ------------------------------------------------------------------------------


def test_overlapping_one_work_block():
    result = detect(event("urgent", "10:30", "11:30"), [block("w1", "10:00", "12:00")])
    assert result.status == "conflict"
    assert result.conflict_detected and result.repair_required
    [c] = result.conflicts
    assert c.conflict_type == "scheduled_block"
    assert c.conflicting_item_id == "w1"
    assert c.outcome_type == "work"
    assert result.affected_block_ids == ["w1"]


def test_overlapping_one_personal_block():
    result = detect(event("urgent", "14:00", "15:00"), [block("p1", "14:30", "16:00", kind="personal")])
    [c] = result.conflicts
    assert c.outcome_type == "personal"
    assert result.affected_block_ids == ["p1"]


def test_overlapping_multiple_scheduled_blocks():
    blocks = [block("w2", "11:00", "12:00"), block("w1", "09:00", "10:30"), block("p1", "10:30", "11:00", kind="personal")]
    result = detect(event("urgent", "10:00", "11:30"), blocks)
    assert [c.conflicting_item_id for c in result.conflicts] == ["w1", "p1", "w2"]
    assert result.affected_block_ids == ["w1", "p1", "w2"]


def test_overlapping_an_existing_fixed_commitment():
    existing = event("standup", "09:30", "10:00")
    result = detect(event("urgent", "09:45", "10:15"), commitments=[existing])
    [c] = result.conflicts
    assert c.conflict_type == "existing_commitment"
    assert c.conflicting_item_id == "standup"
    assert c.outcome_type is None
    assert result.conflict_detected
    assert result.affected_block_ids == []
    assert result.repair_required is True  # still needs resolving, though no block is affected


def test_non_fixed_existing_commitments_are_ignored():
    optional = event("optional", "10:00", "11:00", is_fixed=False)
    result = detect(event("urgent", "10:00", "11:00"), commitments=[optional])
    assert result.status == "clear"


def test_overlapping_a_hard_boundary():
    hard = Boundary(name="Family dinner", windows=[window(MON, "18:00", "19:30")], is_hard=True)
    result = detect(event("urgent", "17:30", "18:30"), boundaries=[hard])
    [c] = result.conflicts
    assert c.conflict_type == "hard_boundary"
    assert c.conflicting_item_title == "Family dinner"
    assert c.overlap_minutes == 30
    assert result.conflict_detected is True
    assert result.repair_required is True
    assert result.affected_block_ids == []


def test_soft_boundary_is_not_a_hard_conflict():
    soft = Boundary(name="Quiet time", windows=[window(MON, "10:00", "12:00")], is_hard=False)
    result = detect(event("urgent", "10:30", "11:30"), boundaries=[soft])
    assert result.status == "clear"
    assert result.conflicts == []


def test_exact_overlap_minutes_and_times():
    result = detect(event("urgent", "10:20", "11:05"), [block("w1", "10:00", "10:45")])
    [c] = result.conflicts
    assert (c.overlap_start_time, c.overlap_end_time) == (t("10:20"), t("10:45"))
    assert c.overlap_minutes == 25
    assert (c.conflicting_start_time, c.conflicting_end_time) == (t("10:00"), t("10:45"))


def test_same_times_on_different_days_do_not_conflict():
    result = detect(
        event("urgent", "10:00", "11:00", day=TUE),
        [block("w1", "10:00", "11:00", day=MON)],
        commitments=[event("c1", "10:00", "11:00", day=MON)],
    )
    assert result.status == "clear"


def test_back_to_back_times_do_not_conflict():
    before = detect(event("urgent", "11:00", "12:00"), [block("w1", "10:00", "11:00")])
    after = detect(event("urgent", "10:00", "11:00"), [block("w1", "11:00", "12:00")])
    assert before.status == "clear" and after.status == "clear"


def test_unexpected_commitment_containing_a_block():
    result = detect(event("urgent", "09:00", "12:00"), [block("w1", "10:00", "11:00")])
    [c] = result.conflicts
    assert c.overlap_minutes == 60
    assert (c.overlap_start_time, c.overlap_end_time) == (t("10:00"), t("11:00"))


def test_block_containing_the_unexpected_commitment():
    result = detect(event("urgent", "10:15", "10:45"), [block("w1", "09:00", "12:00")])
    [c] = result.conflicts
    assert c.overlap_minutes == 30
    assert (c.overlap_start_time, c.overlap_end_time) == (t("10:15"), t("10:45"))


def test_no_conflict_response():
    result = detect(event("urgent", "13:00", "14:00"), [block("w1", "09:00", "10:00")])
    assert result.status == "clear"
    assert result.conflict_detected is False
    assert result.repair_required is False
    assert result.conflicts == [] and result.affected_block_ids == []
    assert result.summary.startswith("No conflicts")
    assert result.unexpected_commitment.id == "urgent"


def test_conflicts_are_ordered_deterministically():
    hard = Boundary(name="Boundary", windows=[window(MON, "09:00", "12:00")], is_hard=True)
    commitments = [event("c-late", "11:00", "11:30"), event("c-early", "09:30", "10:00")]
    blocks = [block("w-b", "10:30", "11:00"), block("w-a", "10:00", "10:30", kind="personal")]
    result = detect(event("urgent", "09:00", "12:00"), blocks, commitments, [hard])
    assert [(c.conflict_type, c.conflicting_item_id) for c in result.conflicts] == [
        ("scheduled_block", "w-a"),
        ("scheduled_block", "w-b"),
        ("existing_commitment", "c-early"),
        ("existing_commitment", "c-late"),
        ("hard_boundary", "boundary:Boundary"),
    ]
    reversed_run = detect(
        event("urgent", "09:00", "12:00"), blocks[::-1], commitments[::-1], [hard]
    )
    assert reversed_run.conflicts == result.conflicts


def test_ties_break_on_stable_id():
    blocks = [block("b", "10:00", "11:00"), block("a", "10:00", "11:00", kind="personal")]
    result = detect(event("urgent", "10:00", "11:00"), blocks)
    assert [c.conflicting_item_id for c in result.conflicts] == ["a", "b"]


def test_affected_block_ids_are_unique():
    # Two overlapping windows for one block would otherwise repeat it; ids must stay unique.
    duplicate = [block("w1", "10:00", "11:00"), block("w1", "10:00", "11:00")]
    result = detect(event("urgent", "10:00", "11:00"), duplicate)
    assert result.affected_block_ids == ["w1"]


def test_inputs_are_not_mutated():
    prof = profile()
    existing = [event("c1", "10:00", "11:00")]
    approved = plan(block("w1", "10:00", "11:00"))
    unexpected = event("urgent", "10:00", "11:00")
    snapshots = (
        prof.model_dump(),
        [c.model_dump() for c in existing],
        approved.model_dump(),
        unexpected.model_dump(),
    )
    detect_conflicts(prof, existing, approved, unexpected)
    assert snapshots == (
        prof.model_dump(),
        [c.model_dump() for c in existing],
        approved.model_dump(),
        unexpected.model_dump(),
    )


def test_summary_is_deterministic_text_with_only_known_facts():
    result = detect(event("urgent", "10:30", "11:30", title="Urgent customer meeting"), [block("w1", "10:00", "12:00")])
    assert result.summary == (
        "'Urgent customer meeting' on Monday 10:30-11:30 conflicts with 1 scheduled plan block(s)."
    )


# --- request validation ---------------------------------------------------------------------


def body(unexpected=None, blocks=(), commitments=()):
    return {
        "profile": profile().model_dump(mode="json"),
        "commitments": [c.model_dump(mode="json") for c in commitments],
        "approved_plan": plan(*blocks).model_dump(mode="json"),
        "unexpected_commitment": (unexpected or event("urgent", "10:00", "11:00")).model_dump(mode="json"),
    }


def test_endpoint_reports_a_conflict():
    response = client.post(URL, json=body(blocks=[block("w1", "10:30", "12:00")]))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "conflict"
    assert data["conflict_detected"] is True and data["repair_required"] is True
    assert data["affected_block_ids"] == ["w1"]
    assert data["conflicts"][0]["overlap_minutes"] == 30
    assert data["conflicts"][0]["overlap_start_time"] == "10:30:00"
    assert data["unexpected_commitment"]["id"] == "urgent"


def test_endpoint_reports_clear():
    data = client.post(URL, json=body(blocks=[block("w1", "13:00", "14:00")])).json()
    assert data["status"] == "clear" and data["conflicts"] == []


def test_non_fixed_unexpected_commitment_returns_422():
    payload = body(event("urgent", "10:00", "11:00", is_fixed=False))
    assert client.post(URL, json=payload).status_code == 422


def test_duplicate_commitment_id_returns_422():
    payload = body(event("dup", "10:00", "11:00"), commitments=[event("dup", "13:00", "14:00")])
    assert client.post(URL, json=payload).status_code == 422


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b["unexpected_commitment"].update(end_time="10:00:00", start_time="11:00:00"),
        lambda b: b["unexpected_commitment"].update(end_time="10:00:00", start_time="10:00:00"),
        lambda b: b["unexpected_commitment"].update(day="funday"),
        lambda b: b.pop("approved_plan"),
        lambda b: b.pop("unexpected_commitment"),
        lambda b: b["approved_plan"].update(status="great"),
        lambda b: b["profile"].update(timezone="Nope/Nope"),
    ],
)
def test_other_invalid_input_returns_422(mutate):
    payload = body()
    mutate(payload)
    assert client.post(URL, json=payload).status_code == 422


def test_request_model_rejects_non_fixed_directly():
    with pytest.raises(ValueError):
        ConflictRequest(
            profile=profile(),
            commitments=[],
            approved_plan=plan(),
            unexpected_commitment=event("urgent", "10:00", "11:00", is_fixed=False),
        )


def test_endpoint_is_in_openapi():
    assert "post" in client.get("/openapi.json").json()["paths"][URL]


def test_conflict_detection_makes_no_model_call(monkeypatch):
    def no_model(*args, **kwargs):
        raise AssertionError("conflict detection must not call Nemotron")

    monkeypatch.setattr("app.services.nebius_client.create_chat_completion", no_model)
    monkeypatch.setattr("app.services.weekly_analysis.create_chat_completion", no_model)
    response = client.post(URL, json=body(blocks=[block("w1", "10:00", "11:00")]))
    assert response.status_code == 200
    assert response.json()["status"] == "conflict"


def test_existing_routes_still_work(monkeypatch):
    assert client.get("/health").json()["status"] == "healthy"

    def failing(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("app.services.weekly_analysis.create_chat_completion", failing)
    commitments = client.get("/api/v1/calendar/demo").json()["commitments"]
    base = {"profile": profile().model_dump(mode="json"), "commitments": commitments}
    analysis = client.post("/api/v1/analysis/weekly", json=base)
    assert analysis.status_code == 200
    assert analysis.json()["analysis"]["source"] == "fallback"

    outcome = {"title": "Deep work", "reason": "Focus.", "estimated_minutes": 120}
    planned = client.post(
        "/api/v1/plan/generate",
        json={**base, "work_outcome": outcome, "personal_outcome": {**outcome, "title": "Family"}},
    )
    assert planned.status_code == 200
    assert planned.json()["scheduled_work_minutes"] == 120
