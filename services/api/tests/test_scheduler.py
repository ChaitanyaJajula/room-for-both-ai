from datetime import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.analysis import Outcome
from app.models.calendar import CalendarCommitment, CommitmentCategory
from app.models.planning_profile import (
    Boundary,
    DayOfWeek,
    PlanningProfile,
    RecurringTimeWindow,
)
from app.services import scheduler
from app.services.capacity_engine import to_minutes
from app.services.demo_calendar import get_demo_calendar
from app.services.scheduler import SchedulingError, generate_schedule

client = TestClient(app)
URL = "/api/v1/plan/generate"

WEEKDAYS = [
    DayOfWeek.monday,
    DayOfWeek.tuesday,
    DayOfWeek.wednesday,
    DayOfWeek.thursday,
    DayOfWeek.friday,
]
MON = DayOfWeek.monday


def t(hhmm: str) -> time:
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def window(day, start, end):
    return RecurringTimeWindow(day=day, start_time=t(start), end_time=t(end))


def week(start="09:00", end="17:00", days=WEEKDAYS):
    return [window(d, start, end) for d in days]


def profile(work_hours=None, **overrides) -> PlanningProfile:
    return PlanningProfile(
        timezone="UTC", work_hours=work_hours or week(), **overrides
    )


def commitment(id, start, end, day=MON, is_fixed=True):
    return CalendarCommitment(
        id=id,
        title=id,
        day=day,
        start_time=t(start),
        end_time=t(end),
        category=CommitmentCategory.work,
        is_fixed=is_fixed,
    )


def outcome(title, minutes):
    return Outcome(title=title, reason="because", estimated_minutes=minutes)


def plan(prof=None, commitments=(), work=240, personal=120):
    return generate_schedule(
        prof or profile(), list(commitments), outcome("Deep work", work), outcome("Family", personal)
    )


def span(block):
    return to_minutes(block.start_time), to_minutes(block.end_time)


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def of_type(result, kind):
    return [b for b in result.blocks if b.outcome_type == kind]


def assert_no_block_overlap(result):
    for i, a in enumerate(result.blocks):
        for b in result.blocks[i + 1 :]:
            if a.day == b.day:
                assert not overlap(span(a), span(b)), (a.id, b.id)


# --- behaviour --------------------------------------------------------------------------


def test_demo_calendar_schedule_is_complete_and_optimal():
    demo = get_demo_calendar().commitments
    result = plan(commitments=demo, work=600, personal=180)

    assert result.status == "optimal"
    assert result.slot_minutes == 15
    assert result.scheduled_work_minutes == 600
    assert result.scheduled_personal_minutes == 180
    assert result.unscheduled_work_minutes == 0
    assert result.unscheduled_personal_minutes == 0
    assert result.solver.name == "Google OR-Tools CP-SAT"
    assert result.solver.status == "OPTIMAL"
    assert result.solver.objective_value is not None
    assert sum(b.duration_minutes for b in of_type(result, "work")) == 600
    assert {b.outcome_title for b in result.blocks} == {"Deep work", "Family"}
    assert_no_block_overlap(result)
    for b in result.blocks:
        assert to_minutes(b.start_time) % 15 == 0 and to_minutes(b.end_time) % 15 == 0
        assert 9 * 60 <= to_minutes(b.start_time) and to_minutes(b.end_time) <= 17 * 60


def test_blocks_never_overlap_fixed_commitments():
    demo = get_demo_calendar().commitments
    result = plan(commitments=demo, work=1200, personal=300)
    assert result.blocks
    for b in result.blocks:
        for c in demo:
            if c.day == b.day:
                assert not overlap(span(b), (to_minutes(c.start_time), to_minutes(c.end_time)))


def test_non_fixed_commitments_do_not_block_time():
    free = commitment("optional", "09:00", "17:00", is_fixed=False)
    result = plan(profile(week(days=[MON])), [free], work=120, personal=0)
    assert result.scheduled_work_minutes == 120


def test_blocks_never_overlap_hard_boundaries():
    lunch = Boundary(name="Lunch", windows=week("12:00", "13:00"), is_hard=True)
    result = plan(profile(boundaries=[lunch]), work=1200, personal=300)
    assert result.blocks
    for b in result.blocks:
        assert not overlap(span(b), (12 * 60, 13 * 60))


def test_work_prefers_focus_windows_and_personal_avoids_them():
    focus = week("09:00", "11:00")
    result = plan(profile(preferred_focus_windows=focus), work=240, personal=120)
    assert result.status == "optimal"
    for b in of_type(result, "work"):
        assert b.inside_preferred_focus_window
        assert 9 * 60 <= to_minutes(b.start_time) and to_minutes(b.end_time) <= 11 * 60
    for b in of_type(result, "personal"):
        assert not b.inside_preferred_focus_window
        assert to_minutes(b.start_time) >= 11 * 60


def test_soft_boundaries_are_avoided_when_possible():
    soft = Boundary(name="Quiet mornings", windows=week("09:00", "12:00"), is_hard=False)
    result = plan(profile(boundaries=[soft]), work=600, personal=180)
    assert result.status == "optimal"
    assert not any(b.uses_soft_boundary for b in result.blocks)
    for b in result.blocks:
        assert to_minutes(b.start_time) >= 12 * 60


def test_soft_boundaries_are_used_when_necessary():
    soft = Boundary(name="Quiet", windows=[window(MON, "09:00", "10:00")], is_hard=False)
    result = plan(profile(week("09:00", "10:00", [MON]), boundaries=[soft]), work=60, personal=0)
    assert result.status == "optimal"
    assert [b.uses_soft_boundary for b in result.blocks] == [True]
    assert any("soft boundary" in w for w in result.warnings)


def test_daily_work_limit_is_respected():
    result = plan(profile(max_daily_focus_minutes=60), work=600, personal=0)
    assert result.status == "partial"
    for day in WEEKDAYS:
        day_total = sum(b.duration_minutes for b in of_type(result, "work") if b.day == day)
        assert day_total <= 60
    assert result.scheduled_work_minutes == 300
    assert result.unscheduled_work_minutes == 300


def test_minimum_break_between_separate_work_blocks():
    prof = profile(week("09:00", "12:00", [MON]), minimum_break_minutes=60)
    blocker = commitment("mid", "10:00", "10:30")
    result = plan(prof, [blocker], work=150, personal=0)
    work = sorted(of_type(result, "work"), key=span)
    assert work
    for first, second in zip(work, work[1:]):
        assert to_minutes(second.start_time) - to_minutes(first.end_time) >= 60
    assert result.scheduled_work_minutes > 0


def test_personal_blocks_are_not_subject_to_the_work_break_rule():
    prof = profile(week("09:00", "10:00", [MON]), minimum_break_minutes=60)
    result = plan(prof, work=0, personal=60)
    assert result.scheduled_personal_minutes == 60


def test_work_and_personal_never_overlap():
    result = plan(profile(week(days=[MON])), work=240, personal=240)
    assert_no_block_overlap(result)
    assert result.scheduled_work_minutes + result.scheduled_personal_minutes == 480


def test_rounding_up_to_the_grid_is_reported_not_hidden():
    result = plan(profile(week(days=[MON, DayOfWeek.tuesday])), work=100, personal=20)
    assert result.requested_work_minutes == 100
    assert result.target_work_minutes == 105
    assert result.scheduled_work_minutes == 105
    assert result.requested_personal_minutes == 20
    assert result.target_personal_minutes == 30
    assert result.scheduled_personal_minutes == 30
    assert result.unscheduled_work_minutes == 0
    assert any("rounded up" in w for w in result.warnings)


def test_partial_schedule_prioritises_personal_time_and_stays_valid():
    prof = profile(week("09:00", "10:00", [MON]))
    result = plan(prof, work=120, personal=120)
    assert result.status == "partial"
    assert result.scheduled_personal_minutes == 60
    assert result.scheduled_work_minutes == 0
    assert result.unscheduled_personal_minutes == 60
    assert result.unscheduled_work_minutes == 120
    assert_no_block_overlap(result)
    assert any("Only" in w for w in result.warnings)


def test_infeasible_when_no_time_is_available():
    prof = profile(week("09:00", "17:00", [MON]))
    result = plan(prof, [commitment("all-day", "09:00", "17:00")], work=60, personal=60)
    assert result.status == "infeasible"
    assert result.blocks == []
    assert result.scheduled_work_minutes == 0
    assert result.unscheduled_work_minutes == 60
    assert result.unscheduled_personal_minutes == 60


def test_zero_minute_outcomes_schedule_nothing():
    result = plan(work=0, personal=0)
    assert result.status == "optimal"
    assert result.blocks == []
    assert result.unscheduled_work_minutes == 0

    only_personal = plan(work=0, personal=60)
    assert only_personal.scheduled_work_minutes == 0
    assert only_personal.scheduled_personal_minutes == 60
    assert all(b.outcome_type == "personal" for b in only_personal.blocks)


def test_fragmentation_is_minimised():
    result = plan(profile(week(days=[MON])), work=240, personal=0)
    assert len(result.blocks) == 1


def test_results_are_deterministic():
    demo = get_demo_calendar().commitments
    prof = profile(preferred_focus_windows=week("09:00", "12:00"))
    runs = [
        plan(prof, demo, work=900, personal=180).model_dump(mode="json") for _ in range(3)
    ]
    for r in runs:
        r["solver"].pop("wall_time_seconds")
    assert runs[0] == runs[1] == runs[2]


def test_block_ids_are_stable_and_unique():
    result = plan(commitments=get_demo_calendar().commitments, work=600, personal=180)
    ids = [b.id for b in result.blocks]
    assert len(ids) == len(set(ids))
    assert all(b.id.startswith(b.outcome_type) for b in result.blocks)


def test_failed_final_validation_raises(monkeypatch):
    def broken(*args, **kwargs):
        raise SchedulingError("schedule failed validation: test")

    monkeypatch.setattr(scheduler, "_validate", broken)
    with pytest.raises(SchedulingError):
        plan()


def test_validator_rejects_an_unsafe_schedule():
    demo = get_demo_calendar().commitments
    prof = profile()
    grid = scheduler._Grid(prof, demo)
    # Monday 09:30 is the team standup.
    from app.models.schedule import ScheduledBlock

    bad = ScheduledBlock(
        id="work-monday-0930",
        outcome_type="work",
        outcome_title="x",
        day=MON,
        start_time=t("09:30"),
        end_time=t("10:00"),
        duration_minutes=30,
        inside_preferred_focus_window=False,
        uses_soft_boundary=False,
    )
    with pytest.raises(SchedulingError):
        scheduler._validate(grid, prof, [bad], 4, 0)


# --- endpoint ---------------------------------------------------------------------------


def request_body(**overrides):
    body = {
        "profile": profile(preferred_focus_windows=week("09:00", "12:00")).model_dump(mode="json"),
        "commitments": client.get("/api/v1/calendar/demo").json()["commitments"],
        "work_outcome": {"title": "Deep work", "reason": "Focus.", "estimated_minutes": 600},
        "personal_outcome": {"title": "Family time", "reason": "Rest.", "estimated_minutes": 180},
    }
    body.update(overrides)
    return body


def test_endpoint_returns_a_valid_schedule(monkeypatch):
    # The scheduler must never reach the model: any Nemotron call fails the test.
    def no_model(*args, **kwargs):
        raise AssertionError("scheduling must not call Nemotron")

    monkeypatch.setattr("app.services.nebius_client.create_chat_completion", no_model)
    monkeypatch.setattr("app.services.weekly_analysis.create_chat_completion", no_model)

    response = client.post(URL, json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "optimal"
    assert body["slot_minutes"] == 15
    assert body["solver"]["name"] == "Google OR-Tools CP-SAT"
    assert body["scheduled_work_minutes"] == 600
    assert body["scheduled_personal_minutes"] == 180
    first = body["blocks"][0]
    assert set(first) == {
        "id",
        "outcome_type",
        "outcome_title",
        "day",
        "start_time",
        "end_time",
        "duration_minutes",
        "inside_preferred_focus_window",
        "uses_soft_boundary",
    }
    assert len(first["start_time"]) == 8  # HH:MM:SS
    assert "candidate_slots" in body["constraints_summary"]


def test_endpoint_route_is_in_openapi():
    assert "post" in client.get("/openapi.json").json()["paths"][URL]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b["work_outcome"].update(estimated_minutes=-5),
        lambda b: b["personal_outcome"].update(estimated_minutes=20000),
        lambda b: b["work_outcome"].update(title="   "),
        lambda b: b.pop("personal_outcome"),
        lambda b: b["profile"].update(timezone="Nope/Nope"),
        lambda b: b["commitments"].append(dict(b["commitments"][0])),
        lambda b: b["commitments"][0].update(end_time="00:00:00"),
    ],
)
def test_endpoint_rejects_invalid_input(mutate):
    body = request_body()
    mutate(body)
    assert client.post(URL, json=body).status_code == 422


def test_endpoint_hides_internal_scheduling_errors(monkeypatch):
    def broken(*args, **kwargs):
        raise SchedulingError("INTERNAL solver detail")

    monkeypatch.setattr(scheduler, "_validate", broken)
    response = client.post(URL, json=request_body())
    assert response.status_code == 500
    assert response.json() == {"detail": "The schedule could not be generated safely."}
    assert "INTERNAL" not in response.text


def test_integration_sized_schedule_matches_real_nemotron_outcomes():
    """1200 work + 180 personal minutes, the outcomes Nemotron returned in the browser test."""
    import time as clock

    lunch = Boundary(name="Lunch", windows=week("12:00", "13:00"), is_hard=True)
    prof = profile(
        preferred_focus_windows=week("09:00", "12:00"),
        boundaries=[lunch],
        max_daily_focus_minutes=240,
        minimum_break_minutes=15,
    )
    demo = get_demo_calendar().commitments

    started = clock.monotonic()
    result = plan(prof, demo, work=1200, personal=180)
    elapsed = clock.monotonic() - started

    assert result.status in ("optimal", "feasible")
    assert result.scheduled_work_minutes == 1200
    assert result.unscheduled_work_minutes == 0
    assert result.scheduled_personal_minutes == 180
    assert result.unscheduled_personal_minutes == 0
    assert result.solver.name == "Google OR-Tools CP-SAT"
    assert elapsed < scheduler.SOLVER_MAX_SECONDS + 5

    for b in result.blocks:
        for c in demo:
            if c.day == b.day:
                assert not overlap(span(b), (to_minutes(c.start_time), to_minutes(c.end_time)))
        assert not overlap(span(b), (12 * 60, 13 * 60))
    assert_no_block_overlap(result)

    for day in WEEKDAYS:
        work = sorted((b for b in of_type(result, "work") if b.day == day), key=span)
        assert sum(b.duration_minutes for b in work) <= 240
        for first, second in zip(work, work[1:]):
            assert to_minutes(second.start_time) - to_minutes(first.end_time) >= 15
