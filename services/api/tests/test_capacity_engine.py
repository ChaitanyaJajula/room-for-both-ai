from datetime import time

import pytest
from pydantic import ValidationError

from app.models.calendar import CalendarCommitment, CommitmentCategory
from app.models.planning_profile import DayOfWeek, PlanningProfile, RecurringTimeWindow
from app.services.capacity_engine import calculate_capacity

WEEKDAYS = [
    DayOfWeek.monday,
    DayOfWeek.tuesday,
    DayOfWeek.wednesday,
    DayOfWeek.thursday,
    DayOfWeek.friday,
]


def t(hhmm: str) -> time:
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def window(day, start="09:00", end="17:00"):
    return RecurringTimeWindow(day=day, start_time=t(start), end_time=t(end))


def make_profile(work_hours=None, **overrides) -> PlanningProfile:
    if work_hours is None:
        work_hours = [window(d) for d in WEEKDAYS]
    return PlanningProfile(timezone="UTC", work_hours=work_hours, **overrides)


def event(id, start, end, day=DayOfWeek.monday, is_fixed=True):
    return CalendarCommitment(
        id=id,
        title=id,
        day=day,
        start_time=t(start),
        end_time=t(end),
        category=CommitmentCategory.work,
        is_fixed=is_fixed,
    )


def monday(result):
    return next(d for d in result.daily if d.day == DayOfWeek.monday)


def test_normal_five_day_workweek():
    result = calculate_capacity(make_profile(), [])
    assert [d.day for d in result.daily] == WEEKDAYS
    for d in result.daily:
        assert d.work_window_minutes == 480
        assert d.occupied_minutes == 0
        assert d.free_minutes == 480
        assert d.reserved_break_minutes == 15
        assert d.schedulable_focus_minutes == 240
    assert result.weekly.work_window_minutes == 2400
    assert result.weekly.free_minutes == 2400
    assert result.weekly.reserved_break_minutes == 75
    assert result.weekly.schedulable_focus_minutes == 1200
    assert result.weekly.protected_personal_target_minutes == 180


def test_max_daily_focus_limit_applies():
    result = calculate_capacity(make_profile(max_daily_focus_minutes=120), [])
    assert all(d.schedulable_focus_minutes == 120 for d in result.daily)
    assert result.signals.days_at_focus_cap == WEEKDAYS


def test_day_below_cap_is_not_flagged_as_at_cap():
    result = calculate_capacity(make_profile(max_daily_focus_minutes=480), [])
    assert monday(result).schedulable_focus_minutes == 465  # 480 free - 15 break
    assert result.signals.days_at_focus_cap == []


def test_event_outside_work_hours_does_not_reduce_capacity():
    result = calculate_capacity(make_profile(), [event("dinner", "18:00", "19:30")])
    assert monday(result).occupied_minutes == 0
    assert monday(result).commitment_ids == []
    assert result.signals.commitments_outside_work_hours == ["dinner"]


def test_event_on_non_workday_is_outside_work_hours():
    saturday = event("market", "10:00", "11:00", day=DayOfWeek.saturday)
    result = calculate_capacity(make_profile(), [saturday])
    assert result.weekly.occupied_minutes == 0
    assert result.signals.commitments_outside_work_hours == ["market"]


def test_event_crossing_window_boundary_is_clipped():
    result = calculate_capacity(make_profile(), [event("late", "16:30", "17:30")])
    assert monday(result).occupied_minutes == 30
    assert monday(result).free_minutes == 450
    assert monday(result).commitment_ids == ["late"]
    assert result.signals.commitments_partially_outside_work_hours == ["late"]
    assert result.signals.commitments_outside_work_hours == []


def test_overlapping_events_counted_once():
    events = [event("a", "10:00", "11:00"), event("b", "10:30", "11:30")]
    result = calculate_capacity(make_profile(), events)
    assert monday(result).occupied_minutes == 90
    assert monday(result).free_minutes == 390
    assert [(p.first_id, p.second_id) for p in result.signals.overlapping_commitments] == [
        ("a", "b")
    ]


def test_events_that_only_touch_do_not_overlap():
    events = [event("a", "10:00", "11:00"), event("b", "11:00", "12:00")]
    result = calculate_capacity(make_profile(), events)
    assert monday(result).occupied_minutes == 120
    assert result.signals.overlapping_commitments == []


def test_multiple_work_windows_on_one_day():
    profile = make_profile(
        [
            window(DayOfWeek.monday, "09:00", "12:00"),
            window(DayOfWeek.monday, "13:00", "17:00"),
        ]
    )
    result = calculate_capacity(profile, [event("lunch", "11:30", "13:30")])
    day = monday(result)
    assert day.work_window_minutes == 420
    assert day.occupied_minutes == 60  # 30 min from each window; the gap is not work time
    assert day.free_minutes == 360
    assert day.reserved_break_minutes == 15  # reserved once, not per window
    assert day.schedulable_focus_minutes == 240


def test_overlapping_work_windows_are_merged():
    profile = make_profile(
        [
            window(DayOfWeek.monday, "09:00", "13:00"),
            window(DayOfWeek.monday, "12:00", "17:00"),
        ]
    )
    assert monday(calculate_capacity(profile, [])).work_window_minutes == 480


def test_completely_booked_day_has_zero_capacity():
    result = calculate_capacity(make_profile(), [event("all-day", "09:00", "17:00")])
    day = monday(result)
    assert day.free_minutes == 0
    assert day.reserved_break_minutes == 0
    assert day.schedulable_focus_minutes == 0
    assert DayOfWeek.monday in result.signals.zero_capacity_days


def test_minimum_break_is_reserved_once_from_free_time():
    result = calculate_capacity(
        make_profile(minimum_break_minutes=30), [event("busy", "09:00", "14:50")]
    )
    day = monday(result)
    assert day.free_minutes == 130
    assert day.reserved_break_minutes == 30
    assert day.schedulable_focus_minutes == 100


def test_break_larger_than_free_time_never_goes_negative():
    day = monday(calculate_capacity(make_profile(), [event("busy", "09:00", "16:50")]))
    assert day.free_minutes == 10
    assert day.reserved_break_minutes == 10
    assert day.schedulable_focus_minutes == 0


@pytest.mark.parametrize(
    "start,end", [("08:00", "18:00"), ("09:00", "17:00"), ("00:00", "23:59")]
)
def test_capacity_is_never_negative(start, end):
    events = [event("x", start, end), event("y", "09:00", "10:00")]
    result = calculate_capacity(make_profile(), events)
    for d in result.daily:
        assert min(d.free_minutes, d.reserved_break_minutes, d.schedulable_focus_minutes) >= 0
    assert result.weekly.schedulable_focus_minutes >= 0


def test_non_fixed_commitments_do_not_reduce_capacity():
    result = calculate_capacity(
        make_profile(), [event("maybe", "10:00", "12:00", is_fixed=False)]
    )
    assert monday(result).occupied_minutes == 0
    assert result.signals.commitments_outside_work_hours == []


def test_invalid_commitment_interval_is_rejected():
    with pytest.raises(ValidationError, match="end_time must be later than start_time"):
        event("bad", "10:00", "10:00")
    with pytest.raises(ValidationError):
        event("bad", "11:00", "10:00")


@pytest.mark.parametrize("field", ["id", "title"])
def test_blank_id_and_title_are_rejected(field):
    data = {
        "id": "a",
        "title": "A",
        "day": "monday",
        "start_time": "09:00",
        "end_time": "10:00",
        "category": "work",
    }
    for blank in ("", "   "):
        with pytest.raises(ValidationError):
            CalendarCommitment(**{**data, field: blank})
