"""`/api/health` is liveness: an incomplete engine environment is a state, not a 500.

Issue #195. Measured on `16320b7` (`HOME=/tmp/h EPHE_MODEL_PROVIDER=openai_compatible`
with `EPHE_OPENAI_COMPAT_MODEL` unset): `/api/health` answered
`500 {"error":{"code":"internal_error"}}` while `/api/sessions` answered 200 — the
server was alive, only the liveness route failed. The desktop shell reads that answer
with `statement()` (`app/src-tauri/src/backend.rs`), requires `engine_key_challenge` in
the body and treats a body without it as a foreign process, so the window said
"Getrennt" for the backend it had just started.

The pin holds both halves of the fixed contract:

- the state: 200, `status: degraded`, `engine_online: false`, `engine_unavailable: true`,
  and `detail` names the variable that is missing (the Setup page's reason);
- the identity the shell recognises its own process by: `instance_id`, `pid`, `root`,
  `git_sha`, `engine_key_challenge` and `api_contract` are in the same body;
- the rest of the server keeps answering, so the failure never reads as a dead process.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _break_engine_env(monkeypatch) -> None:
    """The shape #195 reproduces: a provider named, its model missing."""
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_MODEL", raising=False)
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.delenv("EPHE_SETUP_MODE", raising=False)


@pytest.fixture
def broken_engine_client(tmp_path, monkeypatch):
    """The app is built while the environment is already broken — as a start would."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    _break_engine_env(monkeypatch)
    from server.main import create_app

    with TestClient(create_app()) as client:
        yield client


def test_health_answers_a_broken_engine_env_with_200_and_a_state(broken_engine_client):
    """GIVEN a half-written engine env WHEN /api/health is asked
    THEN 200, `degraded`, and the missing variable named in `detail`."""
    response = broken_engine_client.get("/api/health")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded", body
    assert body["engine_online"] is False, body
    assert body["engine_unavailable"] is True, body
    assert body["engine_state"] == "unreachable", body
    assert "EPHE_OPENAI_COMPAT_MODEL" in body["detail"], body["detail"]
    assert "internal_error" not in response.text, response.text


def test_that_answer_still_names_the_process_the_shell_recognises(broken_engine_client):
    """GIVEN the degraded answer WHEN the shell reads it
    THEN `engine_key_challenge`, `instance_id`, `pid`, `root` and `api_contract` are there
    — a body without them is a foreign process to `statement()`."""
    body = broken_engine_client.get("/api/health").json()

    assert isinstance(body.get("engine_key_challenge"), bool), body
    assert body.get("instance_id"), body
    assert body.get("pid", 0) > 0, body
    assert body.get("root"), body
    assert isinstance(body.get("git_sha"), str), body
    assert body.get("api_contract", 0) > 0, body


def test_the_rest_of_the_server_keeps_answering(broken_engine_client):
    """GIVEN the same broken env WHEN a non-health route is asked
    THEN it answers its own status — health alone reports the engine problem."""
    response = broken_engine_client.get("/api/sessions")

    assert response.status_code == 200, response.text
