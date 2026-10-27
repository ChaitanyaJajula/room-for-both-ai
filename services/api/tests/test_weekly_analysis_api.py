import json

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import weekly_analysis

client = TestClient(app)
URL = "/api/v1/analysis/weekly"
DEMO = "/api/v1/calendar/demo"

REPLY = {
    "classification": "balanced",
    "summary": "A manageable week.",
    "capacity_explanation": "Most work hours are free.",
    "work_outcome": {"title": "Deep work", "reason": "Largest free blocks.", "estimated_minutes": 240},
    "personal_outcome": {"title": "Family time", "reason": "Protected.", "estimated_minutes": 120},
    "risks": ["Thursday overlap"],
}


def request_body():
    days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    return {
        "profile": {
            "timezone": "UTC",
            "work_hours": [
                {"day": d, "start_time": "09:00:00", "end_time": "17:00:00"} for d in days
            ],
        },
        "commitments": client.get(DEMO).json()["commitments"],
    }


def test_weekly_analysis_returns_capacity_and_nemotron_analysis(monkeypatch):
    seen = {}

    def fake_chat(messages, **kwargs):
        seen["payload"] = json.loads(messages[1]["content"])
        return json.dumps(REPLY)

    monkeypatch.setattr(weekly_analysis, "create_chat_completion", fake_chat)
    response = client.post(URL, json=request_body())
    assert response.status_code == 200
    body = response.json()

    assert body["analysis"]["source"] == "nemotron"
    assert body["analysis"]["model_provider"] == "Nebius Token Factory"
    assert body["analysis"]["model_name"] == get_settings().NEMOTRON_FAST_MODEL
    assert body["analysis"]["classification"] == "balanced"
    assert body["analysis"]["work_outcome"]["estimated_minutes"] == 240

    # The capacity returned to the caller is exactly what was sent to the model.
    assert body["capacity"]["weekly"]["schedulable_focus_minutes"] == 1200
    assert body["capacity"]["weekly"]["occupied_minutes"] == 540
    assert seen["payload"]["verified_capacity"] == body["capacity"]


def test_weekly_analysis_falls_back_when_model_fails(monkeypatch):
    def failing_chat(messages, **kwargs):
        raise RuntimeError("Nebius unavailable")

    monkeypatch.setattr(weekly_analysis, "create_chat_completion", failing_chat)
    response = client.post(URL, json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["source"] == "fallback"
    assert body["analysis"]["fallback_reason"] == "model_unavailable"
    assert body["analysis"]["model_name"] == get_settings().NEMOTRON_FAST_MODEL
    assert body["capacity"]["weekly"]["free_minutes"] == 1860
    assert "Nebius unavailable" not in response.text


def test_weekly_analysis_rejects_invalid_input():
    bad = request_body()
    bad["profile"]["timezone"] = "Nope/Nope"
    assert client.post(URL, json=bad).status_code == 422


def test_weekly_analysis_route_in_openapi():
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths[URL]
