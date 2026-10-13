from datetime import time

import pytest
from pydantic import ValidationError

from app.models.planning_profile import (
    Boundary,
    DayOfWeek,
    PlanningProfile,
    RecurringTimeWindow,
)


def window(day=DayOfWeek.monday, start=time(9), end=time(17)):
    return RecurringTimeWindow(day=day, start_time=start, end_time=end)


def valid_profile_data(**overrides):
    data = {
        "timezone": "America/New_York",
        "work_hours": [window()],
        "preferred_focus_windows": [window(start=time(9), end=time(11))],
        "boundaries": [
            Boundary(
                name="Family dinner",
                windows=[window(start=time(18), end=time(19))],
            )
        ],
        "max_daily_focus_minutes": 300,
        "minimum_break_minutes": 10,
        "protected_personal_minutes_per_week": 240,
    }
    data.update(overrides)
    return data


def test_valid_planning_profile():
    profile = PlanningProfile(**valid_profile_data())
    assert profile.timezone == "America/New_York"
    assert profile.work_hours[0].day == DayOfWeek.monday
    assert profile.boundaries[0].is_hard is True
    assert profile.max_daily_focus_minutes == 300


def test_valid_profile_from_json_style_dict():
    profile = PlanningProfile.model_validate(
        {
            "timezone": "UTC",
            "work_hours": [
                {"day": "tuesday", "start_time": "09:00:00", "end_time": "17:30:00"}
            ],
        }
    )
    assert profile.work_hours[0].end_time == time(17, 30)


def test_invalid_timezone():
    with pytest.raises(ValidationError, match="not a valid IANA timezone"):
        PlanningProfile(**valid_profile_data(timezone="Mars/Olympus_Mons"))


@pytest.mark.parametrize("end", [time(9), time(8)])
def test_end_time_must_be_after_start_time(end):
    with pytest.raises(ValidationError, match="end_time must be later than start_time"):
        window(start=time(9), end=end)


def test_empty_work_hours():
    with pytest.raises(ValidationError):
        PlanningProfile(**valid_profile_data(work_hours=[]))


def test_boundary_requires_name_and_windows():
    with pytest.raises(ValidationError):
        Boundary(name="", windows=[window()])
    with pytest.raises(ValidationError):
        Boundary(name="   ", windows=[window()])
    with pytest.raises(ValidationError):
        Boundary(name="Dinner", windows=[])


@pytest.mark.parametrize(
    "field, value",
    [
        ("max_daily_focus_minutes", 29),
        ("max_daily_focus_minutes", 481),
        ("minimum_break_minutes", 4),
        ("minimum_break_minutes", 121),
        ("protected_personal_minutes_per_week", -1),
        ("protected_personal_minutes_per_week", 10081),
    ],
)
def test_numeric_limits_out_of_range(field, value):
    with pytest.raises(ValidationError):
        PlanningProfile(**valid_profile_data(**{field: value}))


@pytest.mark.parametrize(
    "field, value",
    [
        ("max_daily_focus_minutes", 30),
        ("max_daily_focus_minutes", 480),
        ("minimum_break_minutes", 5),
        ("minimum_break_minutes", 120),
        ("protected_personal_minutes_per_week", 0),
        ("protected_personal_minutes_per_week", 10080),
    ],
)
def test_numeric_limits_at_boundaries(field, value):
    profile = PlanningProfile(**valid_profile_data(**{field: value}))
    assert getattr(profile, field) == value


def test_defaults():
    profile = PlanningProfile(timezone="UTC", work_hours=[window()])
    assert profile.preferred_focus_windows == []
    assert profile.boundaries == []
    assert profile.max_daily_focus_minutes == 240
    assert profile.minimum_break_minutes == 15
    assert profile.protected_personal_minutes_per_week == 180


def test_boundary_is_hard_by_default():
    assert Boundary(name="Dinner", windows=[window()]).is_hard is True
