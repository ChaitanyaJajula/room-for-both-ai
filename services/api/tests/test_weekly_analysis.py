import json
from datetime import time
from decimal import Decimal

import httpx
import openai
import pytest

from app.core.config import get_settings
from app.models.calendar import CalendarCommitment, CommitmentCategory
from app.models.planning_profile import DayOfWeek, PlanningProfile, RecurringTimeWindow
from app.services import nebius_client, weekly_analysis
from app.services.capacity_engine import calculate_capacity
from app.services.demo_calendar import get_demo_calendar
from app.services.weekly_analysis import (
    SYSTEM_PROMPT,
    analyze_week,
    build_messages,
    extract_numbers,
)

WEEKDAYS = [
    DayOfWeek.monday,
    DayOfWeek.tuesday,
    DayOfWeek.wednesday,
    DayOfWeek.thursday,
    DayOfWeek.friday,
]


def make_profile(**overrides) -> PlanningProfile:
    windows = [
        RecurringTimeWindow(day=d, start_time=time(9), end_time=time(17)) for d in WEEKDAYS
    ]
    return PlanningProfile(timezone="UTC", work_hours=windows, **overrides)


def booking(id, day, start_hour, end_hour):
    return CalendarCommitment(
        id=id,
        title=id,
        day=day,
        start_time=time(start_hour),
        end_time=time(end_hour),
        category=CommitmentCategory.work,
    )


def valid_reply(**overrides) -> dict:
    reply = {
        "classification": "balanced",
        "summary": "A comfortable week.",
        "capacity_explanation": "Plenty of free time inside work hours.",
        "work_outcome": {"title": "Ship the draft", "reason": "Most focus room.", "estimated_minutes": 120},
        "personal_outcome": {"title": "Evening walks", "reason": "Protect rest.", "estimated_minutes": 90},
        "risks": ["Thursday has an overlap."],
    }
    reply.update(overrides)
    return reply


class FakeChat:
    """Stands in for create_chat_completion and records how it was called.

    `replies` is a sequence used one per call (the last one repeats); `reply` is a single reply.
    """

    def __init__(self, reply=None, error=None, replies=None):
        self.replies = replies if replies is not None else [reply]
        self.error = error
        self.calls = []

    def __call__(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.error:
            raise self.error
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        return reply if isinstance(reply, str) else json.dumps(reply)


@pytest.fixture
def scenario():
    profile = make_profile()
    commitments = [booking("review", DayOfWeek.monday, 10, 12)]
    return profile, commitments, calculate_capacity(profile, commitments)


def run(monkeypatch, scenario, chat):
    monkeypatch.setattr(weekly_analysis, "create_chat_completion", chat)
    profile, commitments, capacity = scenario
    return analyze_week(profile, commitments, capacity)


def test_successful_structured_output(monkeypatch, scenario):
    result = run(monkeypatch, scenario, FakeChat(valid_reply()))
    assert result.source == "nemotron"
    assert result.fallback_reason is None
    assert result.classification == "balanced"
    assert result.work_outcome.title == "Ship the draft"
    assert result.work_outcome.estimated_minutes == 120
    assert result.personal_outcome.estimated_minutes == 90
    assert result.risks == ["Thursday has an overlap."]


@pytest.mark.parametrize("label", ["balanced", "tight", "overloaded"])
def test_each_classification_is_accepted(monkeypatch, scenario, label):
    result = run(monkeypatch, scenario, FakeChat(valid_reply(classification=label)))
    assert result.source == "nemotron"
    assert result.classification == label


def test_json_in_code_fence_or_with_prose_is_accepted(monkeypatch, scenario):
    body = json.dumps(valid_reply())
    for text in (f"```json\n{body}\n```", f"Here is the analysis:\n{body}\nHope that helps!"):
        assert run(monkeypatch, scenario, FakeChat(text)).source == "nemotron"


def test_metadata_comes_from_service_not_model(monkeypatch, scenario):
    reply = valid_reply(source="fallback", model_name="some-other-model", model_provider="Elsewhere")
    result = run(monkeypatch, scenario, FakeChat(reply))
    assert result.source == "nemotron"
    assert result.model_name == get_settings().NEMOTRON_FAST_MODEL
    assert result.model_provider == "Nebius Token Factory"


@pytest.mark.parametrize("text", ["not json at all", "{broken", "", "[1, 2, 3]", '"a string"'])
def test_malformed_output_falls_back(monkeypatch, scenario, text):
    result = run(monkeypatch, scenario, FakeChat(text))
    assert result.source == "fallback"
    assert result.fallback_reason.startswith("invalid_model_output")


@pytest.mark.parametrize(
    "bad_reply",
    [
        {k: v for k, v in valid_reply().items() if k != "work_outcome"},
        {k: v for k, v in valid_reply().items() if k != "classification"},
        valid_reply(classification="fine"),
        valid_reply(summary=""),
        valid_reply(risks="not a list"),
        valid_reply(work_outcome={"title": "x", "reason": "y"}),
        valid_reply(work_outcome={"title": "x", "reason": "y", "estimated_minutes": -5}),
        valid_reply(work_outcome={"title": "x", "reason": "y", "estimated_minutes": "lots"}),
    ],
)
def test_missing_or_invalid_fields_fall_back(monkeypatch, scenario, bad_reply):
    result = run(monkeypatch, scenario, FakeChat(bad_reply))
    assert result.source == "fallback"
    assert result.fallback_reason.startswith("invalid_model_output")


def test_outcomes_exceeding_python_capacity_are_rejected(monkeypatch, scenario):
    _, _, capacity = scenario
    too_much_work = valid_reply(
        work_outcome={
            "title": "x",
            "reason": "y",
            "estimated_minutes": capacity.weekly.schedulable_focus_minutes + 1,
        }
    )
    assert run(monkeypatch, scenario, FakeChat(too_much_work)).source == "fallback"

    too_much_personal = valid_reply(
        personal_outcome={"title": "x", "reason": "y", "estimated_minutes": 181}
    )
    assert run(monkeypatch, scenario, FakeChat(too_much_personal)).source == "fallback"


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("NEBIUS_API_KEY is not set"),
        TimeoutError("timed out"),
        openai.APIConnectionError(request=httpx.Request("POST", "https://example.invalid")),
    ],
)
def test_api_failure_falls_back_and_is_marked(monkeypatch, scenario, error):
    result = run(monkeypatch, scenario, FakeChat(error=error))
    assert result.source == "fallback"
    assert result.fallback_reason == "model_unavailable"
    assert result.model_provider == "Nebius Token Factory"
    assert result.model_name == get_settings().NEMOTRON_FAST_MODEL


def test_fallback_uses_only_python_numbers(monkeypatch, scenario):
    _, _, capacity = scenario
    result = run(monkeypatch, scenario, FakeChat(error=RuntimeError("down")))
    assert result.work_outcome.estimated_minutes <= capacity.weekly.schedulable_focus_minutes
    assert result.personal_outcome.estimated_minutes == capacity.weekly.protected_personal_target_minutes
    assert str(capacity.weekly.free_minutes) in result.capacity_explanation
    assert str(capacity.weekly.schedulable_focus_minutes) in result.capacity_explanation


def test_prompt_carries_python_engine_numbers(monkeypatch, scenario):
    profile, commitments, capacity = scenario
    chat = FakeChat(valid_reply())
    run(monkeypatch, scenario, chat)

    call = chat.calls[0]
    system, user = call["messages"]
    assert system["role"] == "system" and user["role"] == "user"
    payload = json.loads(user["content"])
    assert payload["verified_capacity"] == calculate_capacity(profile, commitments).model_dump(mode="json")
    assert payload["limits"] == {
        "work_outcome_max_minutes": capacity.weekly.schedulable_focus_minutes,
        "personal_outcome_max_minutes": profile.protected_personal_minutes_per_week,
    }
    assert payload["calendar_commitments"][0]["id"] == "review"
    assert "never recalculate" in system["content"].lower()
    assert "json" in system["content"].lower()


def test_low_randomness_is_requested(monkeypatch, scenario):
    chat = FakeChat(valid_reply())
    run(monkeypatch, scenario, chat)
    assert chat.calls[0]["temperature"] <= 0.2


def test_build_messages_matches_what_is_sent(scenario):
    profile, commitments, capacity = scenario
    assert build_messages(profile, commitments, capacity)[1]["role"] == "user"


def booked(hours_per_day):
    """Every weekday booked for `hours_per_day` hours from 9:00."""
    if hours_per_day == 0:
        return []
    return [booking(f"b-{d.value}", d, 9, 9 + hours_per_day) for d in WEEKDAYS]


@pytest.mark.parametrize(
    "hours, expected",
    [(0, "balanced"), (5, "tight"), (7, "overloaded"), (8, "overloaded")],
)
def test_fallback_classification_from_python_numbers(monkeypatch, hours, expected):
    profile = make_profile()
    commitments = booked(hours)
    capacity = calculate_capacity(profile, commitments)
    result = run(
        monkeypatch, (profile, commitments, capacity), FakeChat(error=RuntimeError("down"))
    )
    assert result.source == "fallback"
    assert result.classification == expected


# --- Numerical grounding and the single repair attempt -----------------------------------------


@pytest.fixture
def demo_scenario():
    """Demo calendar: work 2400, occupied 540, free 1860, break 75, focus 1200, personal 180."""
    profile = make_profile()
    commitments = get_demo_calendar().commitments
    return profile, commitments, calculate_capacity(profile, commitments)


def test_invented_660_is_rejected(monkeypatch, demo_scenario):
    bad = valid_reply(capacity_explanation="1200 minus 540 leaves 660 free focus minutes.")
    result = run(monkeypatch, demo_scenario, FakeChat(bad))
    assert result.source == "fallback"
    assert "660" in result.fallback_reason
    assert "660" not in result.capacity_explanation


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", "Only 660 minutes are free."),
        ("capacity_explanation", "About 660 minutes remain."),
        ("risks", ["660 minutes may be lost"]),
    ],
)
def test_unsupported_number_is_caught_in_every_text_field(monkeypatch, demo_scenario, field, value):
    chat = FakeChat(valid_reply(**{field: value}))
    assert run(monkeypatch, demo_scenario, chat).source == "fallback"


@pytest.mark.parametrize("nested", ["work_outcome", "personal_outcome"])
def test_unsupported_number_is_caught_in_outcome_reasons(monkeypatch, demo_scenario, nested):
    outcome = {"title": "Plan", "reason": "Use 660 spare minutes.", "estimated_minutes": 100}
    chat = FakeChat(valid_reply(**{nested: outcome}))
    assert run(monkeypatch, demo_scenario, chat).source == "fallback"


def test_verified_numbers_are_accepted(monkeypatch, demo_scenario):
    good = valid_reply(
        summary="1860 of 2400 work minutes are free; 540 are booked.",
        capacity_explanation=(
            "After 75 break minutes, 1200 minutes are schedulable for focus, up to 240 per day. "
            "The 180 protected personal minutes fit."
        ),
        work_outcome={
            "title": "Deep work",
            "reason": "Use up to 240 minutes a day.",
            "estimated_minutes": 240,
        },
        personal_outcome={"title": "Rest", "reason": "Keep 180 minutes.", "estimated_minutes": 180},
        risks=["Release sync ends at 5:30 pm, after the 17:00 workday ends.", "1 overlapping pair."],
    )
    chat = FakeChat(good)
    result = run(monkeypatch, demo_scenario, chat)
    assert result.source == "nemotron"
    assert len(chat.calls) == 1


def test_explicit_counts_from_the_input_are_allowed(monkeypatch, demo_scenario):
    # The demo calendar has 12 commitments and 5 workdays with capacity.
    text = valid_reply(summary="12 commitments across 5 workdays.")
    assert run(monkeypatch, demo_scenario, FakeChat(text)).source == "nemotron"


def test_number_extraction_handles_separators_and_decimals():
    assert extract_numbers("1,200 min, 2.5 h and 07") == {Decimal(1200), Decimal("2.5"), Decimal(7)}
    assert extract_numbers("no digits here") == set()


def test_derived_decimal_is_rejected(monkeypatch, demo_scenario):
    text = valid_reply(summary="Roughly 31.0 hours are free.")
    assert run(monkeypatch, demo_scenario, FakeChat(text)).source == "fallback"


def test_invalid_first_response_triggers_exactly_one_repair(monkeypatch, demo_scenario):
    bad = valid_reply(capacity_explanation="That leaves 660 free focus minutes.")
    chat = FakeChat(replies=[bad, valid_reply()])
    result = run(monkeypatch, demo_scenario, chat)

    assert len(chat.calls) == 2
    assert result.source == "nemotron"
    assert result.fallback_reason is None
    repair = chat.calls[1]["messages"]
    assert [m["role"] for m in repair] == ["system", "user", "assistant", "user"]
    assert "660" in repair[2]["content"]  # the rejected reply is shown back
    assert "failed deterministic validation" in repair[3]["content"]
    assert "660" in repair[3]["content"]  # and so is exactly what was wrong
    assert chat.calls[1]["temperature"] <= 0.2


@pytest.mark.parametrize(
    "first",
    [
        "not json",
        valid_reply(classification="fine"),
        valid_reply(work_outcome={"title": "x", "reason": "y", "estimated_minutes": 99999}),
    ],
)
def test_structure_and_limit_failures_also_trigger_one_repair(monkeypatch, demo_scenario, first):
    chat = FakeChat(replies=[first, valid_reply()])
    result = run(monkeypatch, demo_scenario, chat)
    assert len(chat.calls) == 2
    assert result.source == "nemotron"


def test_two_invalid_responses_return_fallback(monkeypatch, demo_scenario):
    bad = valid_reply(summary="660 minutes are free.")
    chat = FakeChat(replies=[bad, bad])
    result = run(monkeypatch, demo_scenario, chat)
    assert len(chat.calls) == 2  # never a third request
    assert result.source == "fallback"
    assert result.fallback_reason.startswith("invalid_model_output_after_repair")


def test_valid_first_response_makes_no_repair_call(monkeypatch, demo_scenario):
    chat = FakeChat(valid_reply())
    run(monkeypatch, demo_scenario, chat)
    assert len(chat.calls) == 1


def test_network_failure_does_not_trigger_repair(monkeypatch, demo_scenario):
    request = httpx.Request("POST", "https://example.invalid")
    chat = FakeChat(error=openai.APIConnectionError(request=request))
    result = run(monkeypatch, demo_scenario, chat)
    assert len(chat.calls) == 1
    assert result.source == "fallback"
    assert result.fallback_reason == "model_unavailable"


def test_missing_key_does_not_trigger_repair(monkeypatch, demo_scenario):
    chat = FakeChat(error=RuntimeError("NEBIUS_API_KEY is not set"))
    result = run(monkeypatch, demo_scenario, chat)
    assert len(chat.calls) == 1
    assert result.fallback_reason == "model_unavailable"


def test_failure_during_repair_falls_back_without_a_third_call(monkeypatch, demo_scenario):
    calls = []

    def flaky(messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps(valid_reply(summary="660 minutes are free."))
        raise TimeoutError("timed out")

    result = run(monkeypatch, demo_scenario, flaky)
    assert len(calls) == 2
    assert result.source == "fallback"
    assert result.fallback_reason == "model_unavailable"


def test_error_details_never_reach_the_result(monkeypatch, demo_scenario):
    leaky = "sk-THIS-SHOULD-NEVER-LEAK"
    result = run(monkeypatch, demo_scenario, FakeChat(error=RuntimeError(f"auth failed {leaky}")))
    assert leaky not in result.model_dump_json()


def test_prompt_states_the_strict_number_rules():
    text = SYSTEM_PROMPT.lower()
    assert "never perform arithmetic" in text
    assert "free_minutes is not focus time" in text
    for field in (
        "work_window_minutes",
        "occupied_minutes",
        "free_minutes",
        "reserved_break_minutes",
        "schedulable_focus_minutes",
        "protected_personal_target_minutes",
    ):
        assert field in SYSTEM_PROMPT


def test_real_client_is_blocked_in_tests():
    with pytest.raises(BaseException) as raised:
        nebius_client.OpenAI(api_key="x")
    assert "must not call the real" in str(raised.value)
