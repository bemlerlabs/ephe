"""`GET /api/setup/status` explains a broken engine without quoting the exception.

CodeQL #173 (`py/stack-trace-exposure`, medium) named this answer: the degraded dict
carried `str(exc)` to an external caller. The reason is still the most useful sentence
the page can show, so it is rebuilt from the environment the resolver just read — for
our own refusal (`EngineNotConfigured`, a `ValueError` out of the resolution) it names
the variable, and anything else gets one fixed sentence and a code. Nothing from the
exception object travels: not its message, not its `hint`, not a path.

GIVEN a provider named without its model
WHEN  GET /api/setup/status answers the degraded state
THEN  the problem names the missing `EPHE_...` variable, the code says which gap it is,
      and the exception's own sentence (which appends the whole fix line) does not
      travel as the problem.

GIVEN a failure that is not ours (an unexpected exception carrying a path and a token)
WHEN  the same route answers
THEN  200 `degraded`, the fixed sentence, the unreadable code — and none of the
      exception's text anywhere in the answer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _isolated_engine(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A config-less tree and no override left behind by another test."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    from core import model_provider

    model_provider._ACTIVE_OVERRIDE = None
    yield
    model_provider._ACTIVE_OVERRIDE = None


@pytest.fixture()
def client() -> TestClient:
    from server.routes import settings

    app = FastAPI()
    app.include_router(settings.router, prefix="/api")
    return TestClient(app)


def _half_written_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_MODEL", raising=False)
    monkeypatch.delenv("EPHE_MODEL", raising=False)


def test_a_missing_variable_is_named_from_the_env(client: TestClient, monkeypatch):
    """The answer names the field to fix."""
    _half_written_env(monkeypatch)

    body = client.get("/api/setup/status").json()

    assert body["status"] == "degraded", body
    assert body["engine_unavailable"] is True, body
    assert body["problem_code"] == "engine_model_missing", body
    assert body["problem"] == (
        "EPHE_MODEL_PROVIDER=openai_compatible is set, but EPHE_OPENAI_COMPAT_MODEL is missing."
    ), body["problem"]
    # The fix line still reaches the page, but as `hint` — the class's own constant,
    # not a sentence copied out of the exception.
    assert "ephe configure" in body["hint"], body
    assert "ephe configure" not in body["problem"], body["problem"]


def test_an_unknown_provider_is_named_without_the_exception_wording(
    client: TestClient, monkeypatch
):
    """`ValueError` from the resolution is ours; its wording still does not travel."""
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "bogus")

    body = client.get("/api/setup/status").json()

    assert body["status"] == "degraded", body
    assert body["problem_code"] == "engine_provider_invalid", body
    assert "EPHE_MODEL_PROVIDER=bogus" in body["problem"], body
    assert "Unsupported model provider" not in body["problem"], body


def test_a_foreign_exception_leaves_no_text_and_no_path(
    client: TestClient, monkeypatch
):
    """An unexpected failure is one fixed sentence plus a code."""
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_MODEL", "dead-test")
    from server.routes import settings

    def _explode():
        raise RuntimeError(
            "cannot read /Users/someone/.ephe/engine.json (token=sk-live-DEADBEEF)"
        )

    monkeypatch.setattr(settings, "get_active_provider", _explode)

    response = client.get("/api/setup/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded", body
    assert body["engine_unavailable"] is True, body
    assert body["problem"] == "the engine configuration could not be read", body
    assert body["problem_code"] == "engine_config_unreadable", body
    # Nothing from the exception object rides along — not even a hint.
    assert body["hint"] == "", body
    answer = json.dumps(body)
    for leaked in ("sk-live-DEADBEEF", "/Users/someone", "engine.json", "RuntimeError", "Traceback"):
        assert leaked not in answer, (leaked, answer)
