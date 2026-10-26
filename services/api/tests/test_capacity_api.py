from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
DEMO = "/api/v1/calendar/demo"
CALC = "/api/v1/capacity/calculate"


def profile_payload():
    days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    return {
        "timezone": "UTC",
        "work_hours": [
            {"day": d, "start_time": "09:00:00", "end_time": "17:00:00"} for d in days
        ],
    }


def commitment(**overrides):
    item = {
        "id": "a",
        "title": "A",
        "day": "monday",
        "start_time": "10:00:00",
        "end_time": "11:00:00",
        "category": "work",
    }
    item.update(overrides)
    return item


def test_demo_calendar_endpoint():
    response = client.get(DEMO)
    assert response.status_code == 200
    commitments = response.json()["commitments"]
    assert 8 <= len(commitments) <= 15
    assert len({c["id"] for c in commitments}) == len(commitments)
    assert {c["category"] for c in commitments} == {"work", "personal"}
    assert all(c["is_fixed"] for c in commitments)


def test_capacity_calculation_with_demo_calendar():
    commitments = client.get(DEMO).json()["commitments"]
    response = client.post(CALC, json={"profile": profile_payload(), "commitments": commitments})
    assert response.status_code == 200
    body = response.json()
    assert [d["day"] for d in body["daily"]] == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]
    weekly = body["weekly"]
    assert weekly["work_window_minutes"] == 2400
    assert weekly["occupied_minutes"] == 540
    assert weekly["free_minutes"] == 1860
    assert weekly["reserved_break_minutes"] == 75
    assert weekly["schedulable_focus_minutes"] == 1200
    assert weekly["protected_personal_target_minutes"] == 180
    signals = body["signals"]
    assert set(signals["commitments_outside_work_hours"]) == {
        "mon-dinner",
        "thu-gym",
        "sat-market",
    }
    assert signals["commitments_partially_outside_work_hours"] == ["fri-sync"]
    assert signals["overlapping_commitments"] == [
        {"day": "thursday", "first_id": "thu-review", "second_id": "thu-client"}
    ]


def test_capacity_with_no_commitments():
    response = client.post(CALC, json={"profile": profile_payload()})
    assert response.status_code == 200
    assert response.json()["weekly"]["occupied_minutes"] == 0


def test_invalid_calendar_interval_returns_422():
    bad = commitment(start_time="11:00:00", end_time="10:00:00")
    response = client.post(CALC, json={"profile": profile_payload(), "commitments": [bad]})
    assert response.status_code == 422


def test_duplicate_commitment_ids_return_422():
    item = commitment()
    response = client.post(CALC, json={"profile": profile_payload(), "commitments": [item, item]})
    assert response.status_code == 422


def test_invalid_profile_returns_422():
    response = client.post(CALC, json={"profile": {"timezone": "Nope/Nope", "work_hours": []}})
    assert response.status_code == 422


def test_new_routes_in_openapi():
    paths = client.get("/openapi.json").json()["paths"]
    assert "get" in paths[DEMO]
    assert "post" in paths[CALC]
