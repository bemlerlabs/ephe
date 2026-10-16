"""
W3-2 — the streaming route's failure paths are pinned, one except branch per test.

``server.routes.chat.chat_stream`` resolves the skill, the provider, the model and
the mode, then hands off to ``chat_with_tools``. Every one of those steps can fail,
and the SSE stream must never end in silence: the ``run()`` coroutine catches each
failure class, emits a NAMED ``error`` frame, and its ``finally`` block closes the
stream coherently (usage frame → ``done`` → closing comment → sentinel).

These tests drive the REAL route (directly, no HTTP) with ``chat_with_tools``
replaced by a raiser — once per except branch — and assert the same two things
every time:

  1. the branch emits exactly one ``error`` frame whose ``msg`` names the failure
     (never empty, never a bare "something went wrong" — R37), and
  2. the stream stays coherent: ``done`` is the last data event, no half answer
     leaks out, and the generator terminates with the ``: post`` closing comment.

The 79 % coverage gap in the report is exactly these branches (lines 1510–1524):
the four named engine errors, the generic fallback, and the nested fallback that
fires when the friendly renderer itself throws.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from core.chat import (
    OllamaModelBusyError,
    OllamaModelNotFoundError,
    OllamaNotReachableError,
)
from core.model_provider import ProviderSetupError
from server.routes import chat as chat_route


# helpers

def _raiser(exc: BaseException):
    """A ``chat_with_tools`` replacement that raises ``exc`` when the route calls it."""

    async def _impl(**_kwargs):
        raise exc

    return _impl


async def _collect_stream(monkeypatch, chat_impl, *, heartbeat=None) -> str:
    """Drive the real /chat/stream generator to completion; return the raw SSE text."""
    monkeypatch.setattr(chat_route, "chat_with_tools", chat_impl)
    if heartbeat is not None:
        monkeypatch.setattr(chat_route, "STREAM_HEARTBEAT_S", heartbeat)
    req = chat_route.StreamRequest(message="ping", session_id="s-w3-2")
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


def _types(raw: str) -> list:
    return [e.get("type") for e in _data_events(raw)]


def _error_frames(raw: str) -> list[dict]:
    return [e for e in _data_events(raw) if e.get("type") == "error"]


def _assert_coherent(raw: str) -> None:
    """The invariants every failure path must honour."""
    types = _types(raw)
    assert types.count("error") == 1, f"exactly one error frame expected, got {types}"
    # `done` is the contract's last data event — nothing follows it.
    assert types[-1] == "done", f"done must close the data stream: {types}"
    assert types.index("error") < types.index("done")
    # A failed turn never leaks a half answer into the bubble.
    assert "chunk" not in types and "assistant" not in types, types
    # The generator terminated cleanly: idle-resetting closing comment + sentinel.
    assert raw.rstrip().endswith(": post"), raw[-120:]


# the four named engine branches (exact message contract)

async def test_provider_setup_error_emits_its_own_message(monkeypatch):
    exc = ProviderSetupError("opt-in provider 'openai_compat' is incomplete")
    raw = await _collect_stream(monkeypatch, _raiser(exc))
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == "opt-in provider 'openai_compat' is incomplete"


async def test_ollama_not_reachable_emits_start_hint(monkeypatch):
    raw = await _collect_stream(monkeypatch, _raiser(OllamaNotReachableError()))
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == "Ollama not reachable — start it: ollama serve"


async def test_unreachable_remote_engine_is_named_by_its_own_endpoint(monkeypatch):
    """GIVEN the same transport-down error, but the turn dials an OpenAI-compatible
    engine
    W: the error frame
    T: names that endpoint — never Ollama, a machine this turn never used
    (``OllamaNotReachableError`` is the shared bucket, so its class name cannot
    decide the sentence)"""
    from core.model_provider import ModelProviderConfig

    remote = ModelProviderConfig(
        provider="openai_compatible",
        model="remote-model",
        base_url="http://engine.test/v1",
        label="Remote E2E",
        offline_capable=False,
        requires_internet=True,
    )
    monkeypatch.setattr(chat_route, "get_active_provider", lambda: remote)
    raw = await _collect_stream(monkeypatch, _raiser(OllamaNotReachableError()))
    _assert_coherent(raw)
    msg = _error_frames(raw)[0]["msg"]
    assert "ollama" not in msg.lower(), msg
    assert "http://engine.test/v1" in msg, msg


async def test_ollama_model_busy_emits_timeout(monkeypatch):
    raw = await _collect_stream(monkeypatch, _raiser(OllamaModelBusyError("gemma4:12b", 30.0)))
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == "⏳ Model busy — please retry (timeout after 30s)"


async def test_ollama_model_not_found_emits_model_name(monkeypatch):
    raw = await _collect_stream(monkeypatch, _raiser(OllamaModelNotFoundError("ghost:1b")))
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == "model 'ghost:1b' is not installed"


# the generic fallback + its nested fallback

async def test_generic_engine_error_is_friendly_and_nonempty(monkeypatch):
    raw = await _collect_stream(monkeypatch, _raiser(RuntimeError("engine kaputt")))
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == "engine kaputt"


async def test_generic_error_falls_back_when_friendly_renderer_raises(monkeypatch):
    def _renderer_boom(*_a, **_k):
        raise RuntimeError("masking exploded")

    monkeypatch.setattr(chat_route, "_friendly_model_error", _renderer_boom)
    # An empty str() pins the R37 fallback to the exception class name.
    raw = await _collect_stream(monkeypatch, _raiser(ValueError("")))
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == "ValueError"


async def test_failure_before_provider_resolution_still_closes_coherently(monkeypatch):
    """An error before ``active_provider`` is set must not hang or die silently."""

    def _provider_boom():
        raise ProviderSetupError("no provider resolved yet")

    async def _chat_never_runs(**_kwargs):
        raise AssertionError("chat_with_tools must not be reached")

    monkeypatch.setattr(chat_route, "get_active_provider", _provider_boom)
    raw = await _collect_stream(monkeypatch, _chat_never_runs)
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == "no provider resolved yet"
    # The usage emitter is defined only later in the run body → no usage frame.
    assert "usage" not in _types(raw)


# the stream stays coherent even when the post-turn machinery fails

async def test_trajectory_close_failure_keeps_stream_coherent(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("trajectory store down")

    monkeypatch.setattr(chat_route.trajectory, "end_turn", _boom)
    raw = await _collect_stream(monkeypatch, _raiser(OllamaModelNotFoundError("x")))
    _assert_coherent(raw)


async def test_audit_failure_keeps_stream_coherent(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("audit sink down")

    monkeypatch.setattr("core.audit_log.audit_event", _boom)
    raw = await _collect_stream(monkeypatch, _raiser(RuntimeError("engine kaputt")))
    _assert_coherent(raw)


async def test_history_mirror_failure_keeps_stream_coherent(monkeypatch):
    async def _boom(*_a, **_k):
        raise RuntimeError("mirror store down")

    monkeypatch.setattr(chat_route, "_mirror_rest_turn", _boom)
    raw = await _collect_stream(monkeypatch, _raiser(RuntimeError("engine kaputt")))
    _assert_coherent(raw)


async def test_post_turn_dispatch_failure_keeps_stream_coherent(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("post-turn dispatch down")

    monkeypatch.setattr(chat_route, "_dispatch_post_turn_jobs", _boom)
    raw = await _collect_stream(monkeypatch, _raiser(RuntimeError("engine kaputt")))
    _assert_coherent(raw)


async def test_idle_phase_emits_keepalive_and_stays_coherent(monkeypatch):
    """A long silent phase (no events) keeps the stream alive with ``: keepalive``."""

    async def _slow_engine(**_kwargs):
        await asyncio.sleep(0.05)  # ≫ 5 ms heartbeat → several keepalive comments
        raise RuntimeError("engine kaputt")

    raw = await _collect_stream(monkeypatch, _slow_engine, heartbeat=0.005)
    assert ": keepalive" in raw
    _assert_coherent(raw)


# W-3: the provider's own 4xx body reaches the reader

def _provider_status_error(status: int, payload: dict) -> httpx.HTTPStatusError:
    """The exception a hosted engine's answer becomes.

    httpx reads the status and writes a line of its own ("Client error '400 …'");
    the provider's explanation sits on the response, unread. That is the shape
    that leaves a reader with a bare status when nobody opens the body.
    """
    request = httpx.Request("POST", "https://engine.test/v1/chat/completions")
    response = httpx.Response(status, request=request, json=payload)
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    return caught.value


@pytest.mark.parametrize(
    "status, payload, expected",
    [
        (400, {"error": {"message": "unknown model 'ghost-9b' for this endpoint"}}, "ghost-9b"),
        (401, {"error": {"message": "invalid api key provided"}}, "invalid api key provided"),
        (429, {"error": {"message": "quota exhausted for this key"}}, "quota exhausted"),
    ],
)
async def test_a_provider_4xx_body_reaches_the_reader(monkeypatch, status, payload, expected):
    raw = await _collect_stream(monkeypatch, _raiser(_provider_status_error(status, payload)))
    _assert_coherent(raw)
    msg = _error_frames(raw)[0]["msg"]
    assert expected in msg, msg
    # The transport status the one failure table names stays in the sentence.
    assert f"HTTP {status}" in msg, msg


async def test_a_4xx_refusal_is_a_sentence_not_a_body_dump(monkeypatch):
    payload = {
        "error": {
            "message": "unknown model 'ghost-9b' for this endpoint",
            "type": "invalid_request_error",
            "code": "model_not_found",
        }
    }
    raw = await _collect_stream(monkeypatch, _raiser(_provider_status_error(400, payload)))
    msg = _error_frames(raw)[0]["msg"]
    for envelope in ("{", "}", '"', "invalid_request_error", "model_not_found"):
        assert envelope not in msg, (envelope, msg)


async def test_a_long_4xx_body_is_held_to_one_bounded_line(monkeypatch):
    payload = {"error": {"message": "wall " * 800}}
    raw = await _collect_stream(monkeypatch, _raiser(_provider_status_error(400, payload)))
    msg = _error_frames(raw)[0]["msg"]
    assert len(msg) <= chat_route.PROVIDER_DETAIL_LIMIT + 250, len(msg)
    assert 40 <= msg.count("wall") <= 70, msg.count("wall")
    assert "\n" not in msg, msg


async def test_an_engine_5xx_keeps_the_wording_it_had(monkeypatch):
    """Only a 4xx body is read — a 5xx stays on the existing fallback path."""
    exc = _provider_status_error(503, {"error": {"message": "engine overloaded"}})
    raw = await _collect_stream(monkeypatch, _raiser(exc))
    _assert_coherent(raw)
    assert _error_frames(raw)[0]["msg"] == str(exc)
