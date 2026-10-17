"""
Ephe — Idempotency-Key and remote-retry contract for the serve endpoint
tests/test_serve_idempotency.py

Contract of POST /v1/chat/completions in server/openai.py, plus the retry
policy in core/chat_stream.py:

  - a repeated Idempotency-Key replays the stored non-stream completion and the
    upstream engine is not called a second time
  - the same key with a different body is a 409 conflict
  - a request without the key is never deduplicated
  - streamed requests are accepted but never replayed (the deliberate absence)
  - IdempotencyStore: ttl expiry, key/body conflict, LRU eviction at the bound
  - retry: a transient failure before the first chunk is retried, a caller error
    and a failure after the first chunk are not, and an exhausted transient
    stream emits the stream_error frame
  - RetryPolicy backoff doubling/cap and is_transient_error classification

Runs offline: build_provider_client is a scripted fake (no Ollama, no network).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.chat_stream import RetryPolicy, is_transient_error, stream_with_retry
from server.openai import IdempotencyConflict, IdempotencyStore, create_openai_app

CHUNKS = ("Hello", " from", " the", " Black", " Forest")
FULL = "".join(CHUNKS)
BODY = {"model": "mine:work", "messages": [{"role": "user", "content": "hi"}]}
NO_WAIT = RetryPolicy(max_attempts=3, base_delay=0.0)


class ScriptedClient:
    """Provider stand-in whose chat() outcome follows a per-call script.

    Each script entry is a zero-arg factory returning the async iterator for that
    call; the last entry repeats after the script runs out, so a test can pin an
    always-failing backend with a single entry. calls counts the attempts the
    serve layer actually made, which is what the retry assertions read.
    """

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def chat(self, model, messages, stream):
        index = min(self.calls, len(self._script) - 1)
        self.calls += 1
        return self._script[index]()


def ok_stream(*chunks):
    async def _gen():
        for chunk in chunks:
            yield {"message": {"content": chunk}}

    return _gen


def failing_stream(message, *, after=None):
    async def _gen():
        if after is not None:
            yield {"message": {"content": after}}
        raise RuntimeError(message)

    return _gen


@pytest.fixture
def install_provider(monkeypatch):
    def _install(client):
        monkeypatch.setattr(
            "server.openai.build_provider_client", lambda *a, **k: client
        )
        return client

    return _install


def _app(*, policy=None):
    app = create_openai_app()
    if policy is not None:
        app.state.retry_policy = policy
    return app


# /v1/chat/completions — Idempotency-Key


def test_repeat_key_replays_the_completion_without_a_second_call(install_provider):
    stub = install_provider(ScriptedClient([ok_stream(*CHUNKS)]))
    with TestClient(_app()) as client:
        first = client.post(
            "/v1/chat/completions", json=BODY, headers={"Idempotency-Key": "k-1"}
        )
        second = client.post(
            "/v1/chat/completions", json=BODY, headers={"Idempotency-Key": "k-1"}
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["choices"][0]["message"]["content"] == FULL
    assert second.json()["choices"][0]["message"]["content"] == FULL
    # The stored completion, id included, is what the repeat receives.
    assert second.json()["id"] == first.json()["id"]
    assert second.headers.get("Idempotency-Replayed") == "true"
    assert "Idempotency-Replayed" not in first.headers
    assert stub.calls == 1


def test_repeat_key_with_a_different_body_is_a_conflict(install_provider):
    install_provider(ScriptedClient([ok_stream(*CHUNKS)]))
    with TestClient(_app()) as client:
        first = client.post(
            "/v1/chat/completions", json=BODY, headers={"Idempotency-Key": "k-2"}
        )
        second = client.post(
            "/v1/chat/completions",
            json={**BODY, "messages": [{"role": "user", "content": "different"}]},
            headers={"Idempotency-Key": "k-2"},
        )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "validation_error"


def test_request_without_the_key_is_never_deduplicated(install_provider):
    stub = install_provider(ScriptedClient([ok_stream(*CHUNKS)]))
    with TestClient(_app()) as client:
        client.post("/v1/chat/completions", json=BODY)
        client.post("/v1/chat/completions", json=BODY)
    assert stub.calls == 2


def test_streamed_request_is_not_replayed(install_provider):
    # Documented absence: a streamed body is not buffered for replay, so the same
    # key twice runs the engine twice.
    stub = install_provider(ScriptedClient([ok_stream(*CHUNKS)]))
    streamed = {**BODY, "stream": True}
    with TestClient(_app()) as client:
        first = client.post(
            "/v1/chat/completions", json=streamed, headers={"Idempotency-Key": "k-3"}
        )
        second = client.post(
            "/v1/chat/completions", json=streamed, headers={"Idempotency-Key": "k-3"}
        )
    assert stub.calls == 2
    assert "Idempotency-Replayed" not in second.headers
    assert first.text.count("[DONE]") == 1
    assert second.text.count("[DONE]") == 1


# IdempotencyStore


def test_store_expires_an_entry_after_the_ttl():
    now = {"t": 100.0}
    store = IdempotencyStore(ttl_seconds=5.0, clock=lambda: now["t"])
    fingerprint = store.fingerprint(BODY)
    store.put("k", fingerprint, status_code=200, payload={"x": 1}, headers={})
    assert store.get("k", fingerprint) is not None
    now["t"] += 6.0
    assert store.get("k", fingerprint) is None


def test_store_conflicts_when_the_key_is_reused_with_another_body():
    store = IdempotencyStore()
    store.put("k", store.fingerprint(BODY), status_code=200, payload={}, headers={})
    with pytest.raises(IdempotencyConflict):
        store.get("k", store.fingerprint({**BODY, "model": "other"}))


def test_store_evicts_the_least_recently_used_entry_at_the_bound():
    store = IdempotencyStore(max_entries=2)
    for name in ("a", "b", "c"):
        store.put(
            name,
            store.fingerprint({"n": name}),
            status_code=200,
            payload={"n": name},
            headers={},
        )
    assert store.get("a", store.fingerprint({"n": "a"})) is None
    assert store.get("b", store.fingerprint({"n": "b"})) is not None
    assert store.get("c", store.fingerprint({"n": "c"})) is not None


# Remote retry policy


def test_transient_failure_before_the_first_chunk_is_retried(install_provider):
    stub = install_provider(
        ScriptedClient([failing_stream("connection refused"), ok_stream(*CHUNKS)])
    )
    with TestClient(_app(policy=NO_WAIT)) as client:
        resp = client.post("/v1/chat/completions", json=BODY)
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == FULL
    assert stub.calls == 2


def test_a_caller_error_is_not_retried(install_provider):
    stub = install_provider(ScriptedClient([failing_stream("model not found locally")]))
    with TestClient(_app(policy=NO_WAIT)) as client:
        resp = client.post("/v1/chat/completions", json=BODY)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert stub.calls == 1


def test_failure_after_the_first_chunk_is_not_retried(install_provider):
    # A chunk was already delivered, so re-running the call would send it twice.
    stub = install_provider(
        ScriptedClient(
            [failing_stream("connection reset", after="partial"), ok_stream(*CHUNKS)]
        )
    )
    with TestClient(_app(policy=NO_WAIT)) as client:
        resp = client.post("/v1/chat/completions", json=BODY)
    assert resp.status_code == 500
    assert stub.calls == 1


def test_exhausted_transient_stream_emits_a_stream_error_frame(install_provider):
    stub = install_provider(ScriptedClient([failing_stream("connection refused")]))
    with TestClient(_app(policy=RetryPolicy(max_attempts=2, base_delay=0.0))) as client:
        resp = client.post("/v1/chat/completions", json={**BODY, "stream": True})
    assert resp.status_code == 200
    assert "stream_error" in resp.text
    assert stub.calls == 2


def test_retry_policy_backoff_doubles_and_caps():
    policy = RetryPolicy(max_attempts=5, base_delay=0.25, max_delay=1.0)
    assert policy.delay_for(1) == 0.25
    assert policy.delay_for(2) == 0.5
    assert policy.delay_for(3) == 1.0
    assert policy.delay_for(4) == 1.0


def test_is_transient_error_classifies_transport_failures():
    assert is_transient_error(ConnectionError("connection refused"))
    assert is_transient_error(RuntimeError("HTTP 503 Service Unavailable"))
    assert not is_transient_error(RuntimeError("model 'x' not found locally"))


async def test_stream_with_retry_retries_until_the_first_chunk():
    attempts = {"n": 0}
    delays: list[float] = []

    async def fake_sleep(delay):
        delays.append(delay)

    def open_stream():
        attempts["n"] += 1
        if attempts["n"] < 3:
            return failing_stream("connection refused")()
        return ok_stream(*CHUNKS)()

    chunks = [
        chunk
        async for chunk in stream_with_retry(
            open_stream, policy=RetryPolicy(base_delay=0.1), sleep=fake_sleep
        )
    ]
    assert [c["message"]["content"] for c in chunks] == list(CHUNKS)
    assert attempts["n"] == 3
    assert delays == [0.1, 0.2]


async def test_stream_with_retry_reraises_after_the_first_chunk():
    attempts = {"n": 0}

    async def fake_sleep(_delay):
        raise AssertionError("a retry ran although a chunk was already delivered")

    def open_stream():
        attempts["n"] += 1
        return failing_stream("connection reset", after="partial")()

    with pytest.raises(RuntimeError):
        [
            chunk
            async for chunk in stream_with_retry(
                open_stream, policy=RetryPolicy(base_delay=0.1), sleep=fake_sleep
            )
        ]
    assert attempts["n"] == 1


async def test_stream_with_retry_accepts_an_awaited_opener():
    async def opener():
        async def _gen():
            yield {"message": {"content": "x"}}

        return _gen()

    chunks = [chunk async for chunk in stream_with_retry(opener)]
    assert chunks == [{"message": {"content": "x"}}]
