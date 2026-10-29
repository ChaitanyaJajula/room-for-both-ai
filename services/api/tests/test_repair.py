import json
from datetime import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.analysis import Outcome
from app.models.calendar import CalendarCommitment, CommitmentCategory
from app.models.conflict import ConflictResponse
from app.models.planning_profile import (
    Boundary,
    DayOfWeek,
    PlanningProfile,
    RecurringTimeWindow,
)
from app.models.repair import RepairRequest
from app.models.schedule import (
    ConstraintsSummary,
    ScheduledBlock,
    ScheduleResponse,
    SolverInfo,
)
from app.services import repair_candidates, repair_ranking
from app.services.conflict_detection import detect_conflicts
from app.services.capacity_engine import to_minutes
from app.services.repair import build_repair_options
from app.services.repair_ranking import (
    InvalidModelOutput,
    fallback_ranking,
    parse_ranking,
)

client = TestClient(app)
URL = "/api/v1/repair/options"
MON, TUE = DayOfWeek.monday, DayOfWeek.tuesday
IDS = ["move", "simplify", "delegate", "drop"]


def t(hhmm: str) -> time:
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def window(day, start, end):
    return RecurringTimeWindow(day=day, start_time=t(start), end_time=t(end))


def profile(boundaries=()):
    return PlanningProfile(
        timezone="UTC",
        work_hours=[window(MON, "09:00", "17:00"), window(TUE, "09:00", "17:00")],
        boundaries=list(boundaries),
        max_daily_focus_minutes=240,
        minimum_break_minutes=15,
    )


def minutes(hhmm):
    return to_minutes(t(hhmm))


def block(id, start, end, kind="work", day=MON):
    return ScheduledBlock(
        id=id,
        outcome_type=kind,
        outcome_title=f"{kind} outcome",
        day=day,
        start_time=t(start),
        end_time=t(end),
        duration_minutes=minutes(end) - minutes(start),
        inside_preferred_focus_window=False,
        uses_soft_boundary=False,
    )


def approved(blocks, work=240, personal=60):
    return ScheduleResponse(
        status="optimal",
        blocks=blocks,
        requested_work_minutes=work,
        target_work_minutes=work,
        scheduled_work_minutes=work,
        unscheduled_work_minutes=0,
        requested_personal_minutes=personal,
        target_personal_minutes=personal,
        scheduled_personal_minutes=personal,
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


# Monday: work 09:00-11:00 and 13:00-15:00, personal 15:15-16:15.
def base_blocks():
    return [
        block("work-monday-0900", "09:00", "11:00"),
        block("work-monday-1300", "13:00", "15:00"),
        block("personal-monday-1515", "15:15", "16:15", kind="personal"),
    ]


def event(id, start, end, day=MON, is_fixed=True):
    return CalendarCommitment(
        id=id,
        title=id,
        day=day,
        start_time=t(start),
        end_time=t(end),
        category=CommitmentCategory.work,
        is_fixed=is_fixed,
    )


def request(unexpected, commitments=(), blocks=None, prof=None, work=240, personal=60):
    return RepairRequest(
        profile=prof or profile(),
        commitments=list(commitments),
        approved_plan=approved(blocks if blocks is not None else base_blocks(), work, personal),
        unexpected_commitment=unexpected,
        work_outcome=Outcome(title="Deep work", reason="r", estimated_minutes=work),
        personal_outcome=Outcome(title="Family", reason="r", estimated_minutes=personal),
    )


class FakeModel:
    """Stands in for Nemotron; records every conversation it receives."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def __call__(self, messages, **kwargs):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def ranking_reply(order, explanation="Keeps things simple."):
    return {
        "ranked_options": [
            {"candidate_id": cid, "rank": i, "explanation": explanation}
            for i, cid in enumerate(order, start=1)
        ]
    }


@pytest.fixture
def model(monkeypatch):
    def install(*replies):
        fake = FakeModel(*replies)
        monkeypatch.setattr(repair_ranking, "create_chat_completion", fake)
        return fake

    return install


@pytest.fixture
def no_model(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Nemotron must not be called here")

    monkeypatch.setattr(repair_ranking, "create_chat_completion", forbidden)
    monkeypatch.setattr("app.services.nebius_client.create_chat_completion", forbidden)


def by_id(result):
    return {o.id: o for o in result.options}


# --- statuses that never reach Nemotron ---------------------------------------------------


def test_no_conflict_is_not_needed(no_model):
    result = build_repair_options(request(event("urgent", "12:00", "12:30")))
    assert result.status == "not_needed"
    assert result.options == [] and result.recommended_option_id is None
    assert result.reasoning_source == "not_used"
    assert result.conflict.conflict_detected is False


def test_existing_commitment_conflict_needs_manual_resolution(no_model):
    existing = event("standup", "09:30", "10:00", day=TUE)
    result = build_repair_options(request(event("urgent", "09:45", "10:15", day=TUE), [existing]))
    assert result.status == "manual_resolution_required"
    assert result.options == [] and result.reasoning_source == "not_used"
    assert result.conflict.conflict_detected and result.conflict.repair_required


def test_hard_boundary_conflict_needs_manual_resolution(no_model):
    hard = Boundary(name="Dinner", windows=[window(TUE, "12:00", "13:00")], is_hard=True)
    result = build_repair_options(
        request(event("urgent", "12:30", "13:30", day=TUE), prof=profile([hard]))
    )
    assert result.status == "manual_resolution_required"
    assert result.options == []


def test_plan_plus_fixed_conflict_is_still_manual(no_model):
    existing = event("standup", "10:30", "11:00")
    result = build_repair_options(request(event("urgent", "10:30", "11:30"), [existing]))
    assert result.status == "manual_resolution_required"


# --- candidates -----------------------------------------------------------------------------


def test_work_conflict_builds_all_four_valid_candidates(model):
    fake = model(ranking_reply(IDS))
    result = build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert result.status == "options_ready"
    assert sorted(o.id for o in result.options) == sorted(IDS)
    for option in result.options:
        v = option.validation
        assert v.valid and v.no_unexpected_commitment_overlap and v.no_existing_commitment_overlap
        assert v.no_hard_boundary_overlap and v.no_internal_block_overlap and v.targets_consistent
        assert option.revised_plan.status in ("optimal", "feasible")
        for b in option.revised_plan.blocks:
            if b.day == MON:
                assert not (minutes("10:30") < to_minutes(b.end_time) and to_minutes(b.start_time) < minutes("11:30"))
    assert len(fake.calls) == 1


def test_personal_only_conflict_has_no_delegate_candidate(model):
    model(ranking_reply(["move", "simplify", "drop"]))
    result = build_repair_options(request(event("urgent", "15:30", "16:00")))
    assert sorted(o.id for o in result.options) == ["drop", "move", "simplify"]
    options = by_id(result)
    assert options["simplify"].reduced_personal_minutes == 30
    assert options["simplify"].reduced_work_minutes == 0
    assert options["drop"].dropped_personal_minutes == 60
    assert options["drop"].dropped_work_minutes == 0


def test_mixed_work_and_personal_conflict(model):
    model(ranking_reply(IDS))
    result = build_repair_options(request(event("urgent", "14:30", "15:45")))
    options = by_id(result)
    assert result.conflict.affected_block_ids == ["work-monday-1300", "personal-monday-1515"]
    assert options["simplify"].reduced_work_minutes == 30
    assert options["simplify"].reduced_personal_minutes == 30
    assert options["delegate"].delegated_work_minutes == 120
    assert options["delegate"].target_personal_minutes == 60
    assert options["drop"].dropped_work_minutes == 120
    assert options["drop"].dropped_personal_minutes == 60


def test_overlap_rounds_up_to_the_slot(model):
    model(ranking_reply(IDS))
    result = build_repair_options(request(event("urgent", "10:40", "11:20")))
    assert by_id(result)["simplify"].reduced_work_minutes == 30  # 20 overlap minutes -> 2 slots


def test_unique_blocks_are_not_double_counted(model):
    model(ranking_reply(IDS))
    two_blocks = event("urgent", "10:00", "14:00")  # touches both work blocks
    result = build_repair_options(request(two_blocks))
    options = by_id(result)
    # Each affected block counts once, by its full duration: 120 + 120.
    assert result.conflict.affected_block_ids == ["work-monday-0900", "work-monday-1300"]
    assert options["delegate"].delegated_work_minutes == 240
    assert options["drop"].dropped_work_minutes == 240
    assert options["simplify"].reduced_work_minutes == 60 + 60  # overlaps 10:00-11:00, 13:00-14:00


def test_impacts_are_capped_at_the_requested_minutes():
    plan = approved(base_blocks())
    conflict = detect_conflicts(profile(), [], plan, event("urgent", "09:00", "16:30"))
    impacts = repair_candidates.plan_impacts(conflict, plan, work_minutes=100, personal_minutes=30)
    assert impacts["delegate"].delegated_work == 100
    assert impacts["drop"].dropped_work == 100
    assert impacts["drop"].dropped_personal == 30
    assert impacts["simplify"].reduced_work == 100
    assert impacts["simplify"].reduced_personal == 30


def test_candidate_arithmetic_and_revised_plan_totals(model):
    model(ranking_reply(IDS))
    result = build_repair_options(request(event("urgent", "14:30", "15:45")))
    for o in result.options:
        cut_work = o.reduced_work_minutes + o.delegated_work_minutes + o.dropped_work_minutes
        cut_personal = o.reduced_personal_minutes + o.dropped_personal_minutes
        assert o.target_work_minutes == o.original_work_minutes - cut_work
        assert o.target_personal_minutes == o.original_personal_minutes - cut_personal
        plan = o.revised_plan
        assert plan.requested_work_minutes == o.target_work_minutes
        assert plan.requested_personal_minutes == o.target_personal_minutes
        for kind in ("work", "personal"):
            total = sum(b.duration_minutes for b in plan.blocks if b.outcome_type == kind)
            assert total == getattr(plan, f"scheduled_{kind}_minutes")
            assert total + getattr(plan, f"unscheduled_{kind}_minutes") == getattr(
                plan, f"target_{kind}_minutes"
            )
    moved = by_id(result)["move"]
    assert moved.target_work_minutes == 240 and moved.target_personal_minutes == 60


def test_request_and_approved_plan_are_not_mutated(model):
    model(ranking_reply(IDS))
    req = request(event("urgent", "10:30", "11:30"))
    before = req.model_dump()
    build_repair_options(req)
    assert req.model_dump() == before


def test_invalid_candidates_are_rejected(monkeypatch, model):
    real = repair_candidates.validate_revised_plan

    def reject_drop(plan, prof, existing, unexpected, tw, tp):
        result = real(plan, prof, existing, unexpected, tw, tp)
        if tw == 0:  # only the drop-style candidate reaches zero work here
            return result.model_copy(update={"valid": False, "targets_consistent": False})
        return result

    monkeypatch.setattr(repair_candidates, "validate_revised_plan", reject_drop)
    model(ranking_reply(["move", "simplify"]))
    result = build_repair_options(request(event("urgent", "10:30", "11:30"), work=240))
    assert all(o.validation.valid for o in result.options)


def test_no_valid_options_when_every_candidate_is_infeasible(monkeypatch, no_model):
    def infeasible(profile_, commitments, work, personal):
        base = approved([], work.estimated_minutes, personal.estimated_minutes)
        return base.model_copy(update={"status": "infeasible", "blocks": []})

    monkeypatch.setattr(repair_candidates, "generate_schedule", infeasible)
    result = build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert result.status == "no_valid_options"
    assert result.options == [] and result.reasoning_source == "not_used"


# --- Nemotron ranking -----------------------------------------------------------------------


def test_valid_nemotron_ranking_is_applied(model):
    fake = model(ranking_reply(["drop", "move", "delegate", "simplify"], "Fits the new meeting."))
    result = build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert result.reasoning_source == "nemotron"
    assert result.fallback_message is None
    assert [o.id for o in result.options] == ["drop", "move", "delegate", "simplify"]
    assert [o.rank for o in result.options] == [1, 2, 3, 4]
    assert result.recommended_option_id == "drop"
    assert [o.recommended for o in result.options] == [True, False, False, False]
    assert all(o.explanation == "Fits the new meeting." for o in result.options)
    assert len(fake.calls) == 1


def test_model_only_sees_validated_candidates_and_no_times(monkeypatch, model):
    validated = []
    real = repair_candidates.validate_revised_plan

    def spy(*args, **kwargs):
        result = real(*args, **kwargs)
        validated.append(result.valid)
        return result

    monkeypatch.setattr(repair_candidates, "validate_revised_plan", spy)
    seen = {}

    def fake(messages, **kwargs):
        seen["validated_before_call"] = len(validated)
        seen["payload"] = json.loads(messages[1]["content"])
        return json.dumps(ranking_reply(IDS))

    monkeypatch.setattr(repair_ranking, "create_chat_completion", fake)
    build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert seen["validated_before_call"] == 4 and all(validated)
    payload_text = json.dumps(seen["payload"])
    assert {c["candidate_id"] for c in seen["payload"]["candidates"]} == set(IDS)
    assert "10:30" not in payload_text and "work-monday" not in payload_text


@pytest.mark.parametrize(
    "reply",
    [
        {"ranked_options": [{"candidate_id": "teleport", "rank": 1, "explanation": "x"}]},
        {"ranked_options": [{"candidate_id": c, "rank": i, "explanation": "ok"} for i, c in enumerate(["move", "simplify", "delegate"], 1)]},
        {"ranked_options": [{"candidate_id": c, "rank": i, "explanation": "ok"} for i, c in enumerate(["move", "move", "delegate", "drop"], 1)]},
        {"ranked_options": [{"candidate_id": c, "rank": r, "explanation": "ok"} for c, r in zip(IDS, [1, 1, 2, 3])]},
        {"ranked_options": [{"candidate_id": c, "rank": r, "explanation": "ok"} for c, r in zip(IDS, [1, 2, 3, 5])]},
        {"ranked_options": [{"candidate_id": c, "rank": r, "explanation": "ok"} for c, r in zip(IDS, [0, 1, 2, 3])]},
        {"ranked_options": [{"candidate_id": c, "rank": i, "explanation": " "} for i, c in enumerate(IDS, 1)]},
        {"ranked_options": [{"candidate_id": c, "rank": i, "explanation": "Saves 30 minutes"} for i, c in enumerate(IDS, 1)]},
        {"ranked_options": []},
        {"other": 1},
    ],
)
def test_invalid_rankings_are_rejected(reply):
    with pytest.raises(InvalidModelOutput):
        parse_ranking(json.dumps(reply), IDS)


def test_parse_ranking_accepts_valid_reply_with_code_fence():
    text = "```json\n" + json.dumps(ranking_reply(["simplify", "move", "drop", "delegate"])) + "\n```"
    assert [r.candidate_id for r in parse_ranking(text, IDS)] == ["simplify", "move", "drop", "delegate"]


def test_malformed_json_triggers_exactly_one_repair_attempt(model):
    fake = model("this is not json", ranking_reply(["move", "simplify", "delegate", "drop"]))
    result = build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert result.reasoning_source == "nemotron"
    assert len(fake.calls) == 2
    assert fake.calls[1][-2]["role"] == "assistant"
    assert "failed validation" in fake.calls[1][-1]["content"]


def test_digits_in_explanations_trigger_repair(model):
    fake = model(ranking_reply(IDS, "Saves 30 minutes."), ranking_reply(IDS, "Keeps things simple."))
    result = build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert result.reasoning_source == "nemotron"
    assert len(fake.calls) == 2


def test_second_invalid_reply_uses_fallback(model):
    fake = model("nope", {"ranked_options": []})
    result = build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert len(fake.calls) == 2  # never a third attempt
    assert result.reasoning_source == "fallback"
    assert result.fallback_message == "Nemotron was temporarily unavailable. Showing a verified rule-based ranking."
    assert result.status == "options_ready"
    assert result.recommended_option_id == "move"


def test_provider_exception_uses_fallback_without_leaking(model):
    model(RuntimeError("secret-provider-detail sk-abc 500 Internal"))
    response = client.post(URL, json=body(event("urgent", "10:30", "11:30")))
    assert response.status_code == 200
    data = response.json()
    assert data["reasoning_source"] == "fallback"
    assert "secret-provider-detail" not in response.text and "sk-abc" not in response.text
    assert sum(o["recommended"] for o in data["options"]) == 1


def test_fallback_ranking_is_deterministic_and_ordered(model):
    model(RuntimeError("down"), RuntimeError("down"))
    first = build_repair_options(request(event("urgent", "10:30", "11:30")))
    second = build_repair_options(request(event("urgent", "10:30", "11:30")))
    assert [o.id for o in first.options] == [o.id for o in second.options] == IDS
    assert [o.explanation for o in first.options] == [o.explanation for o in second.options]
    assert [o.recommended for o in first.options] == [True, False, False, False]


def test_fallback_order_rules(model):
    model(ranking_reply(IDS))
    options = build_repair_options(request(event("urgent", "10:30", "11:30"))).options
    opts = {o.id: o for o in options}

    def partial(option):
        plan = option.revised_plan.model_copy(update={"status": "partial"})
        return option.model_copy(update={"revised_plan": plan})

    # complete move first, then other complete candidates in strategy order
    assert [r.candidate_id for r in fallback_ranking([opts["drop"], opts["delegate"], opts["simplify"], opts["move"]])] == IDS
    # partial move drops below complete alternatives, above partial simplify/delegate/drop
    mixed = [partial(opts["drop"]), partial(opts["move"]), opts["delegate"], partial(opts["simplify"])]
    assert [r.candidate_id for r in fallback_ranking(mixed)] == ["delegate", "move", "simplify", "drop"]


# --- endpoint -------------------------------------------------------------------------------


def body(unexpected, commitments=(), blocks=None, prof=None, work=240, personal=60):
    req = request(unexpected, commitments, blocks, prof, work, personal)
    return req.model_dump(mode="json")


def test_endpoint_returns_repair_options(model):
    model(ranking_reply(IDS))
    response = client.post(URL, json=body(event("urgent", "10:30", "11:30")))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "options_ready"
    assert data["model_provider"] == "Nebius Token Factory"
    assert data["model_name"]
    assert data["conflict"]["affected_block_ids"] == ["work-monday-0900"]
    assert data["options"][0]["revised_plan"]["solver"]["name"] == "Google OR-Tools CP-SAT"


def test_work_minutes_mismatch_returns_422():
    payload = body(event("urgent", "10:30", "11:30"))
    payload["work_outcome"]["estimated_minutes"] = 120
    assert client.post(URL, json=payload).status_code == 422


def test_personal_minutes_mismatch_returns_422():
    payload = body(event("urgent", "10:30", "11:30"))
    payload["personal_outcome"]["estimated_minutes"] = 30
    assert client.post(URL, json=payload).status_code == 422


def test_non_fixed_and_duplicate_unexpected_return_422():
    not_fixed = body(event("urgent", "10:30", "11:30"))
    not_fixed["unexpected_commitment"]["is_fixed"] = False
    assert client.post(URL, json=not_fixed).status_code == 422

    duplicate = body(event("dup", "10:30", "11:30"))
    duplicate["commitments"] = [event("dup", "13:00", "14:00", day=TUE).model_dump(mode="json")]
    assert client.post(URL, json=duplicate).status_code == 422


def test_blank_outcome_title_returns_422():
    payload = body(event("urgent", "10:30", "11:30"))
    payload["work_outcome"]["title"] = "  "
    assert client.post(URL, json=payload).status_code == 422


def test_endpoint_is_in_openapi():
    assert "post" in client.get("/openapi.json").json()["paths"][URL]


def test_not_needed_and_manual_via_endpoint_make_no_model_call(no_model):
    clear = client.post(URL, json=body(event("urgent", "12:00", "12:30"))).json()
    assert clear["status"] == "not_needed"
    manual = client.post(
        URL, json=body(event("urgent", "09:45", "10:15", day=TUE), [event("standup", "09:30", "10:00", day=TUE)])
    ).json()
    assert manual["status"] == "manual_resolution_required"


def test_existing_routes_still_work(monkeypatch):
    def failing(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("app.services.weekly_analysis.create_chat_completion", failing)
    assert client.get("/health").json()["status"] == "healthy"
    assert client.get("/api/v1/calendar/demo").status_code == 200
    commitments = client.get("/api/v1/calendar/demo").json()["commitments"]
    base = {"profile": profile().model_dump(mode="json"), "commitments": commitments}
    assert client.post("/api/v1/analysis/weekly", json=base).status_code == 200
    outcome = {"title": "Deep work", "reason": "Focus.", "estimated_minutes": 60}
    planned = client.post(
        "/api/v1/plan/generate",
        json={**base, "work_outcome": outcome, "personal_outcome": {**outcome, "title": "Family"}},
    )
    assert planned.status_code == 200
    plan = planned.json()
    conflict = client.post(
        "/api/v1/conflicts/detect",
        json={**base, "approved_plan": plan, "unexpected_commitment": event("x", "12:00", "12:15", day=TUE).model_dump(mode="json")},
    )
    assert conflict.status_code == 200
