import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app

API_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = API_ROOT.parent.parent
RENDER_FILE = REPO_ROOT / "render.yaml"


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return yaml.safe_load(RENDER_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def service(blueprint) -> dict:
    return blueprint["services"][0]


def env_vars(service) -> dict[str, dict]:
    return {item["key"]: item for item in service["envVars"]}


# --- render.yaml -----------------------------------------------------------------------------


def test_blueprint_is_valid_yaml_with_exactly_one_service(blueprint):
    assert isinstance(blueprint, dict)
    assert len(blueprint["services"]) == 1


def test_service_identity_and_location(service):
    assert service["name"] == "room-for-both-api"
    assert service["type"] == "web"
    assert service["runtime"] == "python"
    assert service["rootDir"] == "services/api"
    assert (REPO_ROOT / service["rootDir"] / "requirements.txt").is_file()


def test_build_and_start_commands(service):
    assert service["buildCommand"] == "pip install -r requirements.txt"
    start = service["startCommand"]
    assert start == "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    assert "--host 0.0.0.0" in start and "$PORT" in start


def test_start_command_targets_a_real_app(service):
    module, _, attribute = service["startCommand"].split()[1].partition(":")
    assert getattr(importlib.import_module(module), attribute) is app


def test_health_check_path_is_the_health_route(service):
    assert service["healthCheckPath"] == "/health"
    assert TestClient(app).get(service["healthCheckPath"]).status_code == 200


def test_auto_deploys_from_main(service):
    assert service["branch"] == "main"
    assert service["autoDeployTrigger"] == "commit"


def test_no_database_disk_or_other_service(blueprint, service):
    assert "databases" not in blueprint
    assert "disk" not in service


def test_python_version_is_consistent(service):
    pinned = (API_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert pinned == "3.14.8"
    assert env_vars(service)["PYTHON_VERSION"]["value"] == pinned


def test_secrets_are_manual_values_with_no_content(service):
    variables = env_vars(service)
    for key in ("NEBIUS_API_KEY", "CORS_ALLOWED_ORIGINS"):
        assert variables[key].get("sync") is False
        assert "value" not in variables[key] and "generateValue" not in variables[key]
    assert set(variables) == {"PYTHON_VERSION", "NEBIUS_API_KEY", "CORS_ALLOWED_ORIGINS"}


def test_blueprint_variables_use_the_names_the_backend_reads(service):
    fields = set(Settings.model_fields)
    assert {"NEBIUS_API_KEY", "CORS_ALLOWED_ORIGINS"} <= fields
    assert set(env_vars(service)) - {"PYTHON_VERSION"} <= fields


def test_committed_deployment_files_contain_no_secret_values():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            RENDER_FILE,
            REPO_ROOT / "docs" / "DEPLOYMENT.md",
            API_ROOT / ".env.example",
            REPO_ROOT / "apps" / "web" / ".env.example",
        )
    )
    assert not re.search(r"sk-[A-Za-z0-9]{8,}|nvapi-|eyJ[A-Za-z0-9]{10,}|Bearer\s+\S{10,}", text)
    for line in text.splitlines():
        if line.startswith("NEBIUS_API_KEY="):
            assert line == "NEBIUS_API_KEY="


# --- running without a key -------------------------------------------------------------------


@pytest.fixture()
def no_key(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_app_imports_without_a_key_in_a_clean_process():
    code = (
        "import os; os.environ['NEBIUS_API_KEY'] = '';"
        "from app.core.config import get_settings; import app.main;"
        "raise SystemExit(0 if get_settings().NEBIUS_API_KEY == '' else 1)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=API_ROOT, capture_output=True, timeout=60)
    assert result.returncode == 0


def test_health_works_without_a_key(no_key):
    response = TestClient(app).get("/health")
    assert response.status_code == 200 and response.json()["status"] == "healthy"


def test_evaluation_works_without_a_key(no_key):
    response = TestClient(app).post("/api/v1/evaluation/run")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed" and body["model_calls_made"] == 0


def test_analysis_without_a_key_uses_its_safe_fallback(no_key):
    client = TestClient(app)
    commitments = client.get("/api/v1/calendar/demo").json()["commitments"]
    days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    profile = {
        "timezone": "UTC",
        "work_hours": [{"day": d, "start_time": "09:00:00", "end_time": "17:00:00"} for d in days],
    }
    response = client.post("/api/v1/analysis/weekly", json={"profile": profile, "commitments": commitments})
    assert response.status_code == 200
    assert response.json()["analysis"]["source"] == "fallback"


# --- CORS in production ----------------------------------------------------------------------


def run_cors_probe(origins: str) -> dict:
    """Start the app in a clean process with the given CORS variable and probe preflights."""
    code = """
import json, os
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
def allowed(origin):
    r = client.options("/api/v1/planning-profile/validate", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    return r.headers.get("access-control-allow-origin")
origins = ["https://prod.example.com", "https://second.example.com", "http://localhost:3000",
           "https://prod-git-feature-team.vercel.app", "https://evil.example", "null"]
print(json.dumps({o: allowed(o) for o in origins}))
"""
    env = {**__import__("os").environ, "CORS_ALLOWED_ORIGINS": origins}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=API_ROOT, capture_output=True, text=True, timeout=60, env=env
    )
    assert result.returncode == 0, result.stderr[-300:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_production_origins_replace_the_local_default():
    seen = run_cors_probe(" https://prod.example.com/ , https://second.example.com ,, ")
    assert seen["https://prod.example.com"] == "https://prod.example.com"
    assert seen["https://second.example.com"] == "https://second.example.com"
    assert seen["http://localhost:3000"] is None
    assert seen["https://evil.example"] is None


def test_vercel_preview_domains_are_not_allowed_automatically():
    seen = run_cors_probe("https://prod.example.com")
    assert seen["https://prod-git-feature-team.vercel.app"] is None


def test_a_wildcard_in_the_variable_is_never_honoured():
    seen = run_cors_probe("*,https://prod.example.com")
    assert seen["https://evil.example"] is None
    assert seen["null"] is None
    assert seen["https://prod.example.com"] == "https://prod.example.com"


def test_local_default_still_allows_local_development():
    response = TestClient(app).options(
        "/api/v1/planning-profile/validate",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in response.headers
