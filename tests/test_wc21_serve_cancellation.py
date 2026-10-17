"""
◑ Ephe — a client disconnect stops the served upstream stream (WC-21)
tests/test_wc21_serve_cancellation.py

Drives the OpenAI-compatible app over a raw ASGI channel so the disconnect can
be placed mid-answer. What is asserted is the property that was missing: when
the consumer leaves, the provider stream this turn opened is closed, and it was
not pulled further. Also pins the demand-driven pull (backpressure) and the
plain teardown after a completed answer.

Runs offline: build_provider_client is replaced with a recording fake.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from server.openai import create_openai_app

CHUNKS = ["a", "b", "c", "d", "e"]


class _TrackedProvider:
    """Fake provider whose stream records every pull and its own close."""

    def __init__(self) -> None:
        self.pulled = 0
        self.closed = False

    def chat(self, model, messages, stream):
        async def _gen():
            try:
                for chunk in CHUNKS:
                    self.pulled += 1
                    await asyncio.sleep(0)
                    yield {"message": {"content": chunk}}
            finally:
                self.closed = True

        return _gen()


class _AsgiClient:
    """Minimal ASGI client: records body frames, disconnects after N of them."""

    def __init__(
        self,
        body: dict,
        *,
        provider: _TrackedProvider,
        after: int | None = None,
        slow: float = 0.0,
    ):
        payload = json.dumps(body).encode()
        self._inbox = [{"type": "http.request", "body": payload, "more_body": False}]
        self._provider = provider
        self._after = after
        self._slow = slow
        self._gone = asyncio.Event()
        self.frames: list[bytes] = []
        self.pulls_at_frame: list[int] = []
        self.status: int | None = None

    async def receive(self) -> dict:
        if self._inbox:
            return self._inbox.pop(0)
        if self._after is None:
            await asyncio.sleep(3600)  # the request never disconnects
        await self._gone.wait()
        return {"type": "http.disconnect"}

    async def send(self, message: Any) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message["type"] == "http.response.body":
            body = message.get("body")
            if body:
                self.frames.append(body)
                self.pulls_at_frame.append(self._provider.pulled)
                if self._after is not None and len(self.frames) >= self._after:
                    self._gone.set()
        await asyncio.sleep(self._slow)  # pace the consumer; a checkpoint too


def _scope(spec_version: str) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 1),
        "headers": [(b"host", b"test"), (b"content-type", b"application/json")],
    }


def _chat_body() -> dict:
    return {
        "model": "gemma4:12b",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }


def _drive(monkeypatch, client: _AsgiClient, spec_version: str) -> None:
    monkeypatch.setattr(
        "server.openai.build_provider_client", lambda *a, **k: client._provider
    )
    app = create_openai_app()

    async def _run() -> None:
        await asyncio.wait_for(
            app(_scope(spec_version), client.receive, client.send), timeout=5.0
        )

    asyncio.run(_run())


@pytest.mark.parametrize("spec", ["2.0", "2.3", "2.4"])
def test_client_disconnect_closes_the_upstream_stream(monkeypatch, spec):
    """The consumer leaves after two frames → the provider stream is closed and
    not read to the end, on every ASGI spec_version."""
    provider = _TrackedProvider()
    client = _AsgiClient(_chat_body(), provider=provider, after=2)

    _drive(monkeypatch, client, spec)

    assert client.status == 200
    assert len(client.frames) >= 2
    assert provider.closed is True
    assert provider.pulled < len(CHUNKS)


def test_completed_stream_closes_the_upstream_stream(monkeypatch):
    """A stream that runs to the end leaves no provider stream open either."""
    provider = _TrackedProvider()
    client = _AsgiClient(_chat_body(), provider=provider, after=None)

    _drive(monkeypatch, client, "2.3")

    assert provider.closed is True
    assert provider.pulled == len(CHUNKS)
    assert client.frames[-1] == b"data: [DONE]\n\n"


def test_upstream_is_pulled_on_demand(monkeypatch):
    """Backpressure: the producer never runs more than one chunk ahead of the
    consumer, so a slow reader throttles the upstream instead of buffering a
    whole answer in memory."""
    provider = _TrackedProvider()
    client = _AsgiClient(_chat_body(), provider=provider, after=None, slow=0.01)

    _drive(monkeypatch, client, "2.3")

    assert provider.pulled == len(CHUNKS)
    for index, pulled in enumerate(client.pulls_at_frame):
        assert pulled <= index + 2, (index, pulled, client.pulls_at_frame)
