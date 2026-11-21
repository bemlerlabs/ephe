"""
◑ Ephe — served turns carry the loop's compaction counters (WC-19)
tests/test_serve_loop_observability.py

The chat loop reports its per-turn counters/events through core.loop_observability
(scope ``loop``). The OpenAI-compatible serve path is a second entry into the same
engine, so a served turn must report them the same way:

  - the served prompt is trimmed to the active context window (the same hard
    ceiling core.chat_context applies), and a non-zero trim emits a ``compaction``
    event with source ``serve``;
  - every served turn closes with a ``loop_turn`` event on the ``ephe.loop`` logger;
  - the counters ride out on the response (X-Ephe-Compaction-Events /
    X-Ephe-Messages-Dropped) so an HTTP consumer sees them too.

Runs offline: build_provider_client is mocked with a recording fake client.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from server.openai import (
    COMPACTION_EVENTS_HEADER,
    MESSAGES_DROPPED_HEADER,
    _fit_served_prompt,
    create_openai_app,
)

CHUNKS = ["Hello", " from", " the", " Forest"]
FULL = "".join(CHUNKS)


class RecordingClient:
    """Fake provider that remembers the exact prompt it was handed."""

    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    def chat(self, model, messages, stream):
        self.seen.append(list(messages))

        async def _gen():
            for chunk in CHUNKS:
                yield {"message": {"content": chunk}}

        return _gen()


class _Capture(logging.Handler):
    """Collects the raw JSON lines the loop scope emits."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@pytest.fixture
def loop_log() -> Iterator[_Capture]:
    """Capture ``ephe.loop`` directly instead of via caplog.

    ``caplog.set_level(..., logger="ephe.loop")`` restores the named logger's
    level to NOTSET on teardown, which undoes get_logger's one-time settle at
    INFO and silences later tests. A handler leaves the scope at its level.
    """
    logger = logging.getLogger("ephe.loop")
    handler = _Capture()
    logger.addHandler(handler)
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


@pytest.fixture
def recording_provider(monkeypatch: pytest.MonkeyPatch) -> RecordingClient:
    client = RecordingClient()
    monkeypatch.setattr("server.openai.build_provider_client", lambda *a, **k: client)
    return client


def _loop_events(handler: _Capture) -> list[dict]:
    return [json.loads(line) for line in handler.lines]


def _long_history(n: int = 6) -> list[dict]:
    """n messages whose combined prompt clears any small test window."""
    msgs = [{"role": "system", "content": "task context " + "x" * 200}]
    for i in range(1, n):
        msgs.append({"role": "user", "content": f"turn {i} " + "y" * 200})
    return msgs


# _fit_served_prompt — the trim itself


def test_fit_served_prompt_does_not_touch_the_request_body(monkeypatch):
    """The idempotency fingerprint was taken from the body: the fit copies."""
    monkeypatch.setattr("server.openai._active_context_window", lambda model: 5)
    original = _long_history(6)
    snapshot = list(original)

    fitted, dropped = _fit_served_prompt(original, "gemma4:12b")

    assert dropped == 4
    assert len(fitted) == 2
    assert original == snapshot  # body untouched


def test_fit_served_prompt_reports_zero_when_a_probe_raises(monkeypatch):
    """A window probe that fails is not worth failing a turn over: no trim."""

    def _boom(model):
        raise RuntimeError("no provider")

    monkeypatch.setattr("server.openai._active_context_window", _boom)
    messages = _long_history(4)

    fitted, dropped = _fit_served_prompt(messages, "gemma4:12b")

    assert dropped == 0
    assert fitted == messages


# served turn — events


def test_served_turn_emits_loop_turn_event(recording_provider, loop_log):
    body = {"model": "gemma4:12b", "messages": [{"role": "user", "content": "hi"}]}

    with TestClient(create_openai_app()) as client:
        resp = client.post("/v1/chat/completions", json=body)

    assert resp.status_code == 200
    turns = [e for e in _loop_events(loop_log) if e["event"] == "loop_turn"]
    assert len(turns) == 1
    turn = turns[0]
    assert turn["scope"] == "loop"
    assert turn["turn_id"] == resp.json()["id"]
    assert turn["tool_rounds"] == 0
    assert turn["compaction_events"] == 0
    assert "wall_ms" in turn


def test_served_prompt_within_window_reports_no_compaction(recording_provider, loop_log):
    body = {"model": "gemma4:12b", "messages": [{"role": "user", "content": "hi"}]}

    with TestClient(create_openai_app()) as client:
        resp = client.post("/v1/chat/completions", json=body)

    assert resp.status_code == 200
    assert resp.headers[COMPACTION_EVENTS_HEADER.lower()] == "0"
    assert resp.headers[MESSAGES_DROPPED_HEADER.lower()] == "0"
    assert [e for e in _loop_events(loop_log) if e["event"] == "compaction"] == []


# served turn — compaction over the window


def test_served_prompt_trims_to_window_and_emits_compaction(recording_provider, loop_log, monkeypatch):
    monkeypatch.setattr("server.openai._active_context_window", lambda model: 5)
    body = {"model": "gemma4:12b", "messages": _long_history(6)}

    with TestClient(create_openai_app()) as client:
        resp = client.post("/v1/chat/completions", json=body)

    assert resp.status_code == 200
    # the provider received the fitted prompt, not the full body
    assert len(recording_provider.seen[0]) == 2
    assert resp.headers[COMPACTION_EVENTS_HEADER.lower()] == "1"
    assert resp.headers[MESSAGES_DROPPED_HEADER.lower()] == "4"

    compactions = [e for e in _loop_events(loop_log) if e["event"] == "compaction"]
    assert len(compactions) == 1
    assert compactions[0]["source"] == "serve"
    assert compactions[0]["dropped"] == 4
    assert compactions[0]["compaction_events"] == 1
    assert compactions[0]["messages_dropped"] == 4


def test_served_stream_reports_compaction_and_closes_turn(recording_provider, loop_log, monkeypatch):
    monkeypatch.setattr("server.openai._active_context_window", lambda model: 5)
    body = {"model": "gemma4:12b", "messages": _long_history(6), "stream": True}

    with (
        TestClient(create_openai_app()) as client,
        client.stream("POST", "/v1/chat/completions", json=body) as resp,
    ):
        assert resp.status_code == 200
        assert resp.headers[COMPACTION_EVENTS_HEADER.lower()] == "1"
        assert resp.headers[MESSAGES_DROPPED_HEADER.lower()] == "4"
        lines = [ln for ln in resp.iter_lines() if ln]

    assert lines[-1] == "data: [DONE]"
    assert len(recording_provider.seen[0]) == 2

    events = _loop_events(loop_log)
    assert [e["event"] for e in events] == ["compaction", "loop_turn"]
    assert events[0]["source"] == "serve"
    # the closing event carries the same counters the compaction moved
    assert events[1]["compaction_events"] == 1
    assert events[1]["messages_dropped"] == 4
