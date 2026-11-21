"""An endpoint decides whether it wants a token — not its host name.

`docs/ENGINE_ENDPOINT_AUTH_RUNBOOK.md` §"Package N": the Spark is about to sit behind
a Caddy that answers 401 to anonymous requests. `core/model_provider.py` decided the
requirement from the host (`*.ts.net`, RFC1918, loopback → "needs no key"), which is a
claim about the infrastructure; the response is a claim about the endpoint. These tests
run a real loopback endpoint that refuses the anonymous request and accepts the keyed
one, over httpx — no transport double, so the header that is actually sent is the
header that is asserted.

The fail-closed direction is the other half: a challenge stops the run with a sentence
naming both places a token can sit. It never walks over to another engine, which is
what the whole engine selection already refuses to do silently.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.model_provider import (
    ModelProviderConfig,
    OpenAICompatibleAsyncClient,
    ProviderSetupError,
    _endpoint_requires_api_key,
    build_provider_client,
    endpoint_requires_api_key,
    key_challenge_reason,
)

STUB_KEY = "stub-token-only-this-endpoint-accepts"


class _Endpoint(BaseHTTPRequestHandler):
    """OpenAI-compatible in miniature: 401 anonymous, 200 with the bearer token."""

    key = STUB_KEY
    seen: list[str] = []

    def do_POST(self):  # noqa: N802 - http.server's name
        auth = self.headers.get("Authorization") or ""
        type(self).seen.append(auth)
        length = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if auth != f"Bearer {type(self).key}":
            self._reply(401, b'{"error":{"message":"missing bearer token"}}')
            return
        if payload.get("stream"):
            body = (
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                b"data: [DONE]\n\n"
            )
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._reply(200, b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}')

    def _reply(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # silence the handler
        return


@pytest.fixture()
def endpoint(monkeypatch):
    """A live stub on loopback; the host name is deliberately one the old rule
    classifies as keyless."""
    handler = type("BoundEndpoint", (_Endpoint,), {"seen": []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # The resolver's second source is the machine's stored token; a test must not
    # reach it, or a real key would ride on a stub endpoint.
    import core.engine_config as ec

    monkeypatch.setattr(ec, "_key_file", lambda home=None: "")
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", handler
    finally:
        server.shutdown()
        server.server_close()


def _config(url: str) -> ModelProviderConfig:
    return ModelProviderConfig(
        provider="openai_compatible",
        model="stub-model",
        base_url=url,
        label="OpenAI-compatible API",
        offline_capable=False,
        requires_internet=False,
        requires_api_key=_endpoint_requires_api_key(url),
        api_key_configured=False,
    )


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_the_stub_itself_refuses_an_anonymous_request(endpoint):
    url, handler = endpoint
    client = OpenAICompatibleAsyncClient(base_url=url, api_key="")
    with pytest.raises(ProviderSetupError):
        _run(client.chat(model="stub-model", messages=[{"role": "user", "content": "x"}]))
    assert handler.seen == [""]


def test_a_token_in_the_environment_arrives_as_a_bearer_header(endpoint, monkeypatch):
    url, handler = endpoint
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", STUB_KEY)
    client = build_provider_client(_config(url))
    answer = _run(client.chat(model="stub-model", messages=[{"role": "user", "content": "x"}]))
    assert handler.seen == [f"Bearer {STUB_KEY}"]
    assert (answer.message.content or "") == "ok"


def test_a_loopback_endpoint_that_challenges_is_keyed_and_the_host_says_otherwise(endpoint):
    url, _handler = endpoint
    assert _endpoint_requires_api_key(url) is False, "loopback is the old rule's keyless class"
    assert endpoint_requires_api_key(url) is False, "without an answer, the default stands"
    assert endpoint_requires_api_key(url, observed_status=401) is True
    assert endpoint_requires_api_key(url, observed_status=403) is True
    assert endpoint_requires_api_key(url, observed_status=200) is False


def test_without_a_token_the_run_names_both_places_a_token_can_sit(endpoint, monkeypatch):
    url, handler = endpoint
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    client = build_provider_client(_config(url))
    with pytest.raises(ProviderSetupError) as raised:
        _run(client.chat(model="stub-model", messages=[{"role": "user", "content": "x"}]))
    text = str(raised.value)
    assert "~/.ephe/engine.key" in text, text
    assert "EPHE_OPENAI_COMPAT_API_KEY" in text, text
    assert "401" in text, text
    # Fail-closed means one request and a stop: no second engine is tried here.
    assert len(handler.seen) == 1


def test_the_streaming_path_refuses_the_same_way(endpoint, monkeypatch):
    """Real turns stream, so the stream branch is the one a user meets."""
    url, handler = endpoint
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    client = OpenAICompatibleAsyncClient(base_url=url, api_key="")

    async def drain():
        chunks = []
        async for event in client._stream_chat({"model": "stub-model", "stream": True}):
            chunks.append(event)
        return chunks

    with pytest.raises(ProviderSetupError):
        _run(drain())
    assert len(handler.seen) == 1


def test_a_token_the_endpoint_rejects_is_reported_as_rejected_not_as_missing(endpoint, monkeypatch):
    url, _handler = endpoint
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "a-token-this-endpoint-does-not-know")
    client = build_provider_client(_config(url))
    with pytest.raises(ProviderSetupError) as raised:
        _run(client.chat(model="stub-model", messages=[{"role": "user", "content": "x"}]))
    assert "refused the token it was given" in str(raised.value)


def test_the_reason_sentence_is_shared_by_the_gate_and_the_challenge(endpoint):
    url, _handler = endpoint
    gate = key_challenge_reason(url, 401, token_sent=False)
    assert gate == key_challenge_reason(url.rstrip("/") + "/", 401, token_sent=False)
    assert "answers HTTP 401" in gate
