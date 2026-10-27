import pytest


@pytest.fixture(autouse=True)
def block_real_llm_calls(monkeypatch):
    """Fail loudly if any test tries to build a real OpenAI/Nebius client.

    pytest.fail raises a BaseException subclass, so production code that catches
    `Exception` cannot swallow it and quietly fall back.
    """

    def _blocked(*args, **kwargs):
        pytest.fail("Automated tests must not call the real Nebius/Nemotron API")

    monkeypatch.setattr("app.services.nebius_client.OpenAI", _blocked)
