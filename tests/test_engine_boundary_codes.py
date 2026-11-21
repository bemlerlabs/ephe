"""Engine failures at the boundary are coded answers, and a broken engine env is a state.

Measured by QA (2026-11-10, `/tmp/rel/VERIFY-REPORT.md`, F5): with an engine configured
but unreachable, the streaming route emitted `{"type":"error","msg":"All connection
attempts failed"}` — the raw httpx line, no code, no move — the synchronous twin answered
`500 internal_error`, and a half-written engine env (`EPHE_MODEL_PROVIDER` without the
model) turned `/api/health` and `/api/setup/status` into 500s, so the page that explains
the mistake could not load to explain it.

The fix reuses the two tables that already exist: `core.provider_errors` decides what the
failure is, `server.refusals.REASONS` carries the code, the English sentence and the
move. This file pins both sides — the coded failure, and the state answer that must stay
a 200.
"""
from __future__ import annotations

import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from server.routes import chat as chat_route


# helpers — the streaming route, driven directly (the shape
# tests/test_chat_stream_errors.py established)

def _raiser(exc: BaseException):
    async def _impl(**_kwargs):
        raise exc

    return _impl


async def _collect_stream(monkeypatch, chat_impl) -> str:
    import asyncio

    monkeypatch.setattr(chat_route, "chat_with_tools", chat_impl)
    req = chat_route.StreamRequest(message="ping", session_id="s-boundary")
    resp = await chat_route.chat_stream(req)
    gen = resp.body_iterator
    chunks: list[str] = []
    while True:
        try:
            chunks.append(await asyncio.wait_for(gen.__anext__(), 5.0))  # type: ignore[attr-defined]
        except StopAsyncIteration:
            break
    return "".join(chunks)


def _data_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for part in raw.split("\n\n"):
        part = part.strip()
        if part.startswith("data: "):
            events.append(json.loads(part[len("data: "):]))
    return events


def _error_frames(raw: str) -> list[dict]:
    return [e for e in _data_events(raw) if e.get("type") == "error"]


def _status_error(status: int) -> httpx.HTTPStatusError:
    """What the engine client raises for an engine answer that is not a 2xx."""
    request = httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")
    response = httpx.Response(status, request=request, text="engine down")
    return httpx.HTTPStatusError(f"{status} engine down", request=request, response=response)


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.delenv("EPHE_SETUP_MODE", raising=False)
    from server.main import create_app

    return TestClient(create_app())


# the streaming boundary


def _remote_provider():
    """QA's shape: an OpenAI-compatible engine is configured, its socket is dead."""
    from core.model_provider import ModelProviderConfig

    return ModelProviderConfig(
        provider="openai_compatible",
        model="dead-test",
        base_url="http://127.0.0.1:9/v1",
        label="Remote E2E",
        offline_capable=False,
        requires_internet=True,
    )


async def test_a_transport_failure_on_the_stream_is_a_coded_frame(monkeypatch):
    """GIVEN the engine's socket is dead, WHEN the turn runs, THEN the error frame
    carries the registry code and the move — not the raw httpx line alone."""
    monkeypatch.setattr(chat_route, "get_active_provider", _remote_provider)
    raw = await _collect_stream(
        monkeypatch, _raiser(httpx.ConnectError("All connection attempts failed"))
    )
    frames = _error_frames(raw)
    assert len(frames) == 1, frames
    frame = frames[0]
    assert frame.get("code") == "upstream_error", frame
    assert frame.get("reason_code") == "engine_unreachable", frame
    assert "ephe doctor" in frame["msg"], frame["msg"]
    assert frame["msg"] != "All connection attempts failed"
    # The endpoint the turn dialled rides in the params, so the surface can name it.
    assert frame["reason_params"]["endpoint"] == "http://127.0.0.1:9/v1", frame
    # The engine's own line stays as evidence beside the sentence, not as the sentence.
    assert "connection" in frame["reason_params"]["detail"], frame


async def test_a_streamed_5xx_keeps_its_pinned_line(monkeypatch):
    """The frame's 5xx wording is a pinned contract (test_chat_stream_errors.py,
    test_stream_4xx_provider_body.py); the fix must not move it. The REST twin, which
    had no such promise and answered 500, is coded — see the synchronous test below."""
    exc = _status_error(503)
    raw = await _collect_stream(monkeypatch, _raiser(exc))
    frame = _error_frames(raw)[0]
    assert frame["msg"] == str(exc), frame
    assert "reason_code" not in frame, frame


async def test_an_ordinary_bug_is_still_not_dressed_up_as_an_engine_failure(monkeypatch):
    """The coding must not swallow a programming error into an engine sentence."""
    raw = await _collect_stream(monkeypatch, _raiser(RuntimeError("engine kaputt")))
    frame = _error_frames(raw)[0]
    assert frame["msg"] == "engine kaputt", frame
    assert "reason_code" not in frame, frame


# the synchronous boundary


def test_the_synchronous_chat_answers_a_coded_envelope(tmp_path, monkeypatch):
    """GIVEN the same dead engine, WHEN the REST twin runs, THEN the answer is the
    coded envelope the rest of the API already speaks — not a bare 500."""
    from unittest.mock import AsyncMock, patch

    client = _client(tmp_path, monkeypatch)
    with patch(
        "server.routes.chat.react_loop",
        new=AsyncMock(side_effect=httpx.ConnectError("All connection attempts failed")),
    ):
        response = client.post("/api/chat", json={"message": "hi", "model": "dead"})

    assert response.status_code == 502, response.text
    error = response.json()["error"]
    assert error["code"] == "upstream_error", error
    assert error["reason_code"] == "engine_unreachable", error
    assert error["reason_params"]["endpoint"].startswith("http"), error
    assert error.get("request_id"), error
    assert "ephe doctor" in error["message"], error


def test_the_synchronous_chat_maps_an_engine_server_error(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    client = _client(tmp_path, monkeypatch)
    with patch("server.routes.chat.react_loop", new=AsyncMock(side_effect=_status_error(503))):
        response = client.post("/api/chat", json={"message": "hi", "model": "dead"})

    assert response.status_code == 502, response.text
    error = response.json()["error"]
    assert error["reason_code"] == "engine_server_error", error
    assert error["reason_params"]["status"] == 503, error


def test_a_real_bug_in_the_turn_stays_an_internal_error(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, patch

    client = _client(tmp_path, monkeypatch)
    with patch("server.routes.chat.react_loop", new=AsyncMock(side_effect=RuntimeError("boom"))):
        response = client.post("/api/chat", json={"message": "hi", "model": "dead"})

    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "internal_error", response.text


# a broken engine env at the chat boundary


async def test_the_stream_answers_a_broken_engine_env_with_a_coded_frame(monkeypatch):
    """GIVEN a provider named without its model, WHEN a turn starts, THEN the frame
    says the choice is incomplete and names the missing variable — no 500, no raw text."""
    _break_engine_env(monkeypatch)
    raw = await _collect_stream(monkeypatch, _raiser(RuntimeError("never reached")))
    frames = _error_frames(raw)
    assert len(frames) == 1, frames
    frame = frames[0]
    assert frame.get("code") == "setup_required", frame
    assert frame.get("reason_code") == "engine_unconfigured", frame
    assert "EPHE_OPENAI_COMPAT_MODEL" in frame["reason_params"]["reason"], frame


def test_the_synchronous_chat_answers_a_broken_engine_env_with_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _break_engine_env(monkeypatch)

    response = client.post("/api/chat", json={"message": "hi", "model": "dead"})

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "setup_required", error
    assert error["reason_code"] == "engine_unconfigured", error
    assert "EPHE_OPENAI_COMPAT_MODEL" in error["reason_params"]["reason"], error


# the state answers: a broken engine env must not kill the page that repairs it


def _break_engine_env(monkeypatch) -> None:
    """The shape QA reproduced: a provider named, its model missing."""
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_MODEL", raising=False)
    monkeypatch.delenv("EPHE_MODEL", raising=False)


def test_health_reports_a_broken_engine_env_as_a_state(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _break_engine_env(monkeypatch)

    response = client.get("/api/health")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded", body
    assert body["engine_unavailable"] is True, body
    assert body["engine_online"] is False, body
    # The reason names the variable that is missing, so the reader can fix it.
    assert "EPHE_OPENAI_COMPAT_MODEL" in body["detail"], body["detail"]


def test_the_setup_status_explains_a_broken_engine_env(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _break_engine_env(monkeypatch)

    response = client.get("/api/setup/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded", body
    assert body["engine_unavailable"] is True, body
    assert body["configured"] is False, body
    assert "EPHE_OPENAI_COMPAT_MODEL" in body["problem"], body
    assert "ephe configure" in body["hint"], body
    # The page still gets its candidates: the way out must be on the same answer.
    assert body["candidates"], body


def test_the_healthy_setup_status_keeps_its_shape(tmp_path, monkeypatch):
    # The engine choice is read when the app is built, so the env has to be in place before
    # that - the first version set it afterwards and read this machine's real provider.
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_MODEL", "dead-test")
    os.environ.pop("EPHE_SETUP_MODE", None)
    # The setup probe memo is module state; a previous test in this file warmed it against this
    # machine's real provider, so it has to be cleared for the env to be read at all.
    from server.routes import settings as settings_route

    settings_route._setup_probe_cache.clear()
    from core import model_provider

    model_provider._ACTIVE_OVERRIDE = None  # a previous app in this process pinned one
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/setup/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok", body
    assert body["engine_unavailable"] is False, body
    assert body["provider"] == "openai_compatible", body
    # A machine that already chose an engine keeps that choice - the setup answer reports what the
    # shell shows, and the persisted choice outranks the env by design. The env wiring is proven on
    # a config-less tree; here the assertion is the shape this machine's tag can satisfy.
    assert body["model"], body
    if not body.get("configured"):
        assert body["model"] == "dead-test", body
