from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
URL = "/api/v1/planning-profile/validate"


def valid_payload(**overrides):
    payload = {
        "timezone": "America/New_York",
        "work_hours": [{"day": "monday", "start_time": "09:00:00", "end_time": "17:00:00"}],
        "preferred_focus_windows": [
            {"day": "monday", "start_time": "09:00:00", "end_time": "11:00:00"}
        ],
        "boundaries": [
            {
                "name": "Family dinner",
                "windows": [{"day": "monday", "start_time": "18:00:00", "end_time": "19:00:00"}],
            }
        ],
        "max_daily_focus_minutes": 300,
    }
    payload.update(overrides)
    return payload


def test_valid_profile_returns_200():
    response = client.post(URL, json=valid_payload())
    assert response.status_code == 200


def test_response_status_is_valid():
    assert client.post(URL, json=valid_payload()).json()["status"] == "valid"


def test_normalized_profile_is_returned():
    minimal = {
        "timezone": "UTC",
        "work_hours": [{"day": "tuesday", "start_time": "09:00", "end_time": "17:30"}],
    }
    profile = client.post(URL, json=minimal).json()["profile"]
    assert profile["work_hours"][0]["start_time"] == "09:00:00"
    assert profile["work_hours"][0]["end_time"] == "17:30:00"
    assert profile["preferred_focus_windows"] == []
    assert profile["boundaries"] == []
    assert profile["max_daily_focus_minutes"] == 240
    assert profile["minimum_break_minutes"] == 15
    assert profile["protected_personal_minutes_per_week"] == 180


def test_invalid_timezone_returns_422():
    response = client.post(URL, json=valid_payload(timezone="Mars/Olympus_Mons"))
    assert response.status_code == 422


def test_invalid_time_window_returns_422():
    bad = [{"day": "monday", "start_time": "17:00:00", "end_time": "09:00:00"}]
    response = client.post(URL, json=valid_payload(work_hours=bad))
    assert response.status_code == 422


def test_health_still_works():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "room-for-both-api"}


def test_route_in_openapi():
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths[URL]
