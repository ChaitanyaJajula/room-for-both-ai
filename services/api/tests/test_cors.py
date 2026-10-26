from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app

client = TestClient(app)
URL = "/api/v1/planning-profile/validate"


def preflight(origin: str):
    return client.options(
        URL,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_local_nextjs_origin_is_allowed():
    response = preflight("http://localhost:3000")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_unknown_origin_is_rejected():
    response = preflight("https://evil.example")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_credentials_are_not_allowed():
    response = preflight("http://localhost:3000")
    assert "access-control-allow-credentials" not in response.headers


def test_cors_origins_are_configurable_and_normalized():
    settings = Settings(
        _env_file=None,
        CORS_ALLOWED_ORIGINS=" https://app.example.com/ ,http://localhost:3000,, ",
    )
    assert settings.cors_origins == ["https://app.example.com", "http://localhost:3000"]


def test_default_origins_cover_local_development():
    settings = Settings(_env_file=None)
    assert "http://localhost:3000" in settings.cors_origins
    assert "*" not in settings.cors_origins
