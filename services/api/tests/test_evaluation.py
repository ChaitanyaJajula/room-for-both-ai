import ast
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.evaluation import EvaluationReport
from app.services import evaluation
from app.services.evaluation import CASES, run_evaluation

API_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_IDS = [
    "capacity-balanced-week",
    "capacity-constrained-week",
    "schedule-validity",
    "conflict-known-overlap",
    "conflict-clear-event",
    "repair-option-validation",
]
client = TestClient(app)


@pytest.fixture(scope="module")
def report() -> EvaluationReport:
    # The suite solves several OR-Tools models, so it runs once and the tests share the result.
    return run_evaluation()


@pytest.fixture(scope="module")
def payload() -> dict:
    response = client.post("/api/v1/evaluation/run")
    assert response.status_code == 200
    return response.json()


# --- report contents -------------------------------------------------------------------------


def test_suite_passes_every_fixed_case(report):
    assert report.status == "passed"
    assert all(case.passed for case in report.cases)
    assert all(case.checks_passed == case.checks_total for case in report.cases)


def test_case_ids_are_stable_unique_and_ordered(report):
    assert [case.id for case in report.cases] == EXPECTED_IDS
    assert [case.id for case in CASES] == EXPECTED_IDS


def test_all_four_categories_are_covered(report):
    assert {case.category for case in report.cases} == {
        "capacity",
        "scheduling",
        "conflict_detection",
        "repair_validation",
    }


def test_no_model_calls_are_reported(report):
    assert report.model_calls_made == 0
    assert report.suite_name == "Room for Both deterministic reliability suite"


def test_summary_matches_case_totals(report):
    summary = report.summary
    assert summary.total_cases == len(report.cases) == 6
    assert summary.passed_cases == sum(c.passed for c in report.cases)
    assert summary.failed_cases == summary.total_cases - summary.passed_cases
    assert summary.total_checks == sum(c.checks_total for c in report.cases)
    assert summary.passed_checks == sum(c.checks_passed for c in report.cases)
    assert summary.pass_rate_percent == round(100 * summary.passed_cases / summary.total_cases, 2)
    assert math.isclose(
        summary.total_duration_ms, sum(c.duration_ms for c in report.cases), abs_tol=0.01
    )


def test_durations_are_finite_and_non_negative(report):
    assert all(math.isfinite(c.duration_ms) and c.duration_ms >= 0 for c in report.cases)
    assert math.isfinite(report.summary.total_duration_ms) and report.summary.total_duration_ms >= 0


def test_generated_at_is_utc(report):
    assert report.generated_at.utcoffset().total_seconds() == 0


def test_summaries_leak_nothing(payload):
    text = repr(payload)
    for case in payload["cases"]:
        assert case["summary"].strip()
    assert not re.search(r"traceback|exception|error|[A-Za-z]:\\|/home/|/Users/|\.py\b", text, re.I)
    assert not re.search(r"api[_-]?key|secret|sk-[A-Za-z0-9]|bearer", text, re.I)
    # The guarantees may say the suite makes no Nebius call; no case summary mentions it.
    assert not any(re.search("nebius|nemotron", c["summary"], re.I) for c in payload["cases"])


# --- no model access -------------------------------------------------------------------------


def test_evaluation_module_never_imports_the_model_client():
    tree = ast.parse((API_ROOT / "app" / "services" / "evaluation.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    forbidden = ("nebius_client", "repair_ranking", "weekly_analysis", "openai", "app.services.repair")
    assert not [name for name in imported if any(name.endswith(f) for f in forbidden)]


def test_importing_the_suite_does_not_load_the_model_client():
    code = (
        "import sys, app.services.evaluation;"
        "bad = [m for m in ('app.services.nebius_client', 'openai') if m in sys.modules];"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=API_ROOT, capture_output=True, timeout=60
    )
    assert result.returncode == 0


def test_running_without_an_api_key_calls_no_model(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(
        "app.services.nebius_client.create_chat_completion",
        lambda *a, **k: calls.append("model") or pytest.fail("model must not be called"),
    )
    case = next(c for c in CASES if c.id == "conflict-known-overlap")
    result = evaluation._run_case(case, {})
    assert result.passed and calls == []


# --- determinism and failure handling --------------------------------------------------------


def test_repeated_runs_have_identical_shape_and_results(report):
    second = run_evaluation()
    assert [c.id for c in second.cases] == [c.id for c in report.cases]
    assert [c.passed for c in second.cases] == [c.passed for c in report.cases]
    assert [(c.checks_passed, c.checks_total) for c in second.cases] == [
        (c.checks_passed, c.checks_total) for c in report.cases
    ]
    assert second.summary.total_checks == report.summary.total_checks


def test_an_internal_failure_becomes_a_safe_failed_case(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("secret /home/user/key.py sk-abc123 traceback")

    monkeypatch.setattr(evaluation, "calculate_capacity", explode)
    case = next(c for c in CASES if c.id == "capacity-balanced-week")
    result = evaluation._run_case(case, {})
    assert result.passed is False
    assert (result.checks_passed, result.checks_total) == (0, 1)
    assert result.summary.startswith("The capacity invariants did not pass.")
    for leaked in ("secret", "/home", "sk-abc", "traceback", "RuntimeError"):
        assert leaked not in result.summary


def test_one_failing_case_fails_the_report_without_crashing(monkeypatch):
    monkeypatch.setattr(evaluation, "CASES", [c for c in CASES if c.id.startswith("capacity")])
    monkeypatch.setattr(
        evaluation, "calculate_capacity", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
    )
    result = run_evaluation()
    assert result.status == "failed"
    assert result.summary.failed_cases == 2 and result.summary.pass_rate_percent == 0
    assert all("boom" not in c.summary for c in result.cases)


def test_a_wrong_expectation_is_reported_as_a_failed_check(monkeypatch):
    monkeypatch.setattr(evaluation, "_conflict_known", lambda ctx: _failing_checks())
    case = evaluation._Case("x", "capacity", "n", lambda ctx: _failing_checks(), "ok", "Not ok.")
    result = evaluation._run_case(case, {})
    assert not result.passed and (result.checks_passed, result.checks_total) == (1, 2)
    assert result.summary == "Not ok. (1 of 2 checks passed)"


def _failing_checks():
    checks = evaluation.Checks()
    checks.check(True)
    checks.check(False)
    return checks


# --- model validation ------------------------------------------------------------------------


def _valid(payload):
    return EvaluationReport.model_validate(payload)


def test_payload_round_trips_through_the_model(payload):
    assert _valid(payload).status == "passed"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["summary"].update(passed_cases=5),
        lambda d: d["summary"].update(failed_cases=1),
        lambda d: d["summary"].update(passed_checks=d["summary"]["total_checks"] + 1),
        lambda d: d["summary"].update(pass_rate_percent=50.0),
        lambda d: d.update(status="failed"),
        lambda d: d.update(model_calls_made=1),
        lambda d: d["cases"][1].update(id=d["cases"][0]["id"]),
        lambda d: d["cases"][0].update(passed=False),
        lambda d: d["cases"][0].update(checks_passed=d["cases"][0]["checks_total"] + 1),
        lambda d: d["cases"][0].update(checks_total=0),
        lambda d: d["cases"][0].update(duration_ms=-1),
        lambda d: d["cases"][0].update(duration_ms=float("nan")),
        lambda d: d["cases"][0].update(category="llm"),
        lambda d: d["cases"][0].update(summary=""),
        lambda d: d.update(generated_at="2026-01-01T00:00:00"),
        lambda d: d.update(suite_name="Other suite"),
    ],
)
def test_inconsistent_reports_are_rejected(payload, mutate):
    import copy

    broken = copy.deepcopy(payload)
    mutate(broken)
    with pytest.raises(ValidationError):
        _valid(broken)


def test_failed_status_is_valid_only_when_a_case_failed(payload):
    import copy

    broken = copy.deepcopy(payload)
    case = broken["cases"][0]
    case.update(passed=False, checks_passed=case["checks_total"] - 1)
    broken["summary"].update(
        passed_cases=5,
        failed_cases=1,
        pass_rate_percent=round(100 * 5 / 6, 2),
        passed_checks=broken["summary"]["passed_checks"] - 1,
    )
    broken["status"] = "failed"
    assert _valid(broken).status == "failed"
    broken["status"] = "passed"
    with pytest.raises(ValidationError):
        _valid(broken)


# --- endpoint --------------------------------------------------------------------------------


def test_endpoint_needs_no_body_and_returns_a_report(payload):
    assert payload["status"] == "passed" and payload["model_calls_made"] == 0
    assert [c["id"] for c in payload["cases"]] == EXPECTED_IDS
    assert payload["architecture_guarantees"]


def test_endpoint_ignores_any_body_it_is_given():
    response = client.post(
        "/api/v1/evaluation/run", json={"cases": ["x"], "work_minutes": 99999, "code": "print(1)"}
    )
    assert response.status_code == 200
    assert [c["id"] for c in response.json()["cases"]] == EXPECTED_IDS


def test_endpoint_is_in_openapi_without_a_request_body():
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/evaluation/run"]["post"]
    assert "requestBody" not in operation
    assert "200" in operation["responses"]


def test_endpoint_failure_is_a_safe_500(monkeypatch):
    def explode():
        raise RuntimeError("internal detail /home/user")

    monkeypatch.setattr("app.api.routes.evaluation.run_evaluation", explode)
    response = TestClient(app, raise_server_exceptions=False).post("/api/v1/evaluation/run")
    assert response.status_code == 500
    assert response.json() == {"detail": "The evaluation report could not be produced."}


def test_get_is_not_allowed():
    assert client.get("/api/v1/evaluation/run").status_code == 405


def test_existing_routes_still_work():
    assert client.get("/health").json()["status"] == "healthy"
    assert client.get("/api/v1/calendar/demo").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/v1/plan/generate", "/api/v1/conflicts/detect", "/api/v1/repair/options"):
        assert path in paths
