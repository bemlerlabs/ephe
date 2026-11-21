"""PERF-BE-REST: one pooled HTTP client per engine endpoint.

A provider client used to build an ``httpx.AsyncClient`` inside ``chat`` and
inside ``_stream_chat``, so every round of a turn paid a new TCP/TLS handshake
and threw the connection pool away. These tests pin the pooled client: the same
object answers two calls, a new loop or a new factory gets a new object, and the
app shutdown path closes what is left.
"""
from __future__ import annotations

import asyncio

import pytest

from core import model_provider as mp


class _FakeResponse:
    def __init__(self) -> None:
        self.status_code = 200

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "ok"}}]}

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        yield 'data: {"choices": [{"delta": {"content": "ok"}}]}'
        yield "data: [DONE]"


class _FakeStream:
    def __init__(self) -> None:
        self.response = _FakeResponse()

    async def __aenter__(self) -> _FakeResponse:
        return self.response

    async def __aexit__(self, *_exc) -> bool:
        return False


class _FakeClient:
    """Records construction, posts, streams and the close, so reuse is visible."""

    instances: list["_FakeClient"] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.posts: list[tuple[str, dict]] = []
        self.streams: list[tuple[str, dict]] = []
        self.closed = False
        type(self).instances.append(self)

    async def post(self, url: str, **kwargs) -> _FakeResponse:
        self.posts.append((url, kwargs))
        return _FakeResponse()

    def stream(self, _method: str, url: str, **kwargs) -> _FakeStream:
        self.streams.append((url, kwargs))
        return _FakeStream()

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """Each test starts with an empty pool and a fake httpx client class."""
    _FakeClient.instances = []
    monkeypatch.setattr(mp, "_SHARED_HTTP_CLIENTS", {})
    monkeypatch.setattr(mp.httpx, "AsyncClient", _FakeClient)
    yield
    mp._SHARED_HTTP_CLIENTS.clear()


async def _ask(client: mp.OpenAICompatibleAsyncClient, *, stream: bool = False) -> None:
    answer = await client.chat(
        model="qwen-test",
        messages=[{"role": "user", "content": "hi"}],
        stream=stream,
    )
    if stream:
        async for _chunk in answer:
            pass


def test_two_calls_share_one_client_and_one_pool():
    async def _run() -> None:
        client = mp.OpenAICompatibleAsyncClient(base_url="http://engine.test/v1", api_key="k")
        await _ask(client)
        await _ask(client)
        await _ask(client, stream=True)

        # One pool per timeout profile: the two sync calls share the sync client,
        # the stream keeps its own (its read timeout is minutes, not the api bound).
        assert len(_FakeClient.instances) == 2, "a call built its own client"
        sync, streaming = _FakeClient.instances
        assert len(sync.posts) == 2
        assert sync.streams == []
        assert len(streaming.streams) == 1
        assert streaming.posts == []
        assert sync.closed is False and streaming.closed is False

    asyncio.run(_run())


def test_each_endpoint_gets_its_own_pool():
    async def _run() -> None:
        first = mp.OpenAICompatibleAsyncClient(base_url="http://a.test/v1", api_key="k")
        second = mp.OpenAICompatibleAsyncClient(base_url="http://b.test/v1", api_key="k")
        await _ask(first)
        await _ask(second)
        assert len(_FakeClient.instances) == 2

    asyncio.run(_run())


def test_shutdown_closes_the_pooled_clients():
    async def _run() -> None:
        await _ask(mp.OpenAICompatibleAsyncClient(base_url="http://engine.test/v1"))
        pooled = _FakeClient.instances[0]
        await mp.aclose_shared_http_clients()
        assert pooled.closed is True
        assert mp._SHARED_HTTP_CLIENTS == {}

        # A turn after the close builds a fresh client instead of reusing a dead one.
        await _ask(mp.OpenAICompatibleAsyncClient(base_url="http://engine.test/v1"))
        assert len(_FakeClient.instances) == 2

    asyncio.run(_run())


def test_a_new_event_loop_gets_a_new_client():
    async def _run() -> None:
        await _ask(mp.OpenAICompatibleAsyncClient(base_url="http://engine.test/v1"))

    asyncio.run(_run())
    asyncio.run(_run())
    assert len(_FakeClient.instances) == 2, "httpx pools are loop-bound; a new loop needs its own"
