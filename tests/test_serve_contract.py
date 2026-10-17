"""
Serve wire contract for the OpenAI-compatible engine (WS6-36; CLI P3-11, P3-13).

``server.openai.create_openai_app`` is the surface an outside agent attaches to, so its
HTTP shapes are a contract in two halves:

schema     the app's OpenAPI document through ``app.openapi()``, compared against the
           document serve publishes at its own openapi_url (P3-11).
behaviour  the shapes actually on the wire: model list, completion, SSE frames, error
           envelope, request ID, and the Idempotency-Key replay (P3-13).

A fake provider client keeps the file offline: no Ollama, no network.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from server.openai import create_openai_app

CHUNKS = ["Hello", " from", " the", " Black", " Forest"]
FULL = "".join(CHUNKS)
CONTRACT_PATHS = {"/v1/models": "get", "/v1/chat/completions": "post"}
CHAT_URL = "/v1/chat/completions"


class FakeClient:
    """Stands in for build_provider_client(); tags every call after the first, so a
    replayed response stays distinguishable from a fresh one."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, model, messages, stream):  # noqa: ARG002
        self.calls += 1
        marker = "" if self.calls == 1 else f" #{self.calls}"

        async def _gen():
            for chunk in CHUNKS:
                yield {"message": {"content": chunk}}
            if marker:
                yield {"message": {"content": marker}}

        return _gen()


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient()
    monkeypatch.setattr("server.openai.build_provider_client", lambda *a, **k: client)
    return client


def _serve_banner(monkeypatch: pytest.MonkeyPatch) -> str:
    """Banner text cmd_serve prints before uvicorn blocks; the event loop is stubbed out."""
    import ephe_cli

    args = argparse.Namespace(token=None, lan=False, host="127.0.0.1", port=8765, model=None)
    engine = SimpleNamespace(provider="local_ollama", model="mine:fast", api_url=None)
    buffer = io.StringIO()
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda *a, **k: engine)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    with contextlib.redirect_stdout(buffer):
        assert ephe_cli.cmd_serve(args) == 0
    return buffer.getvalue()


# schema layer


def test_openapi_document_covers_the_contract_endpoints():
    """P3-11: a served contract has to name both endpoints with the method each answers."""
    schema = create_openai_app().openapi()
    assert schema["openapi"].startswith("3.")
    for path, method in CONTRACT_PATHS.items():
        assert path in schema["paths"], f"{path} is absent from the schema"
        assert method in schema["paths"][path], f"{method.upper()} {path} is absent"


def test_schema_documents_no_route_the_app_does_not_mount():
    """A documented path the app cannot answer would be a lie a consumer acts on."""
    app = create_openai_app()
    mounted = {getattr(route, "path", "") for route in app.routes}
    assert set(app.openapi()["paths"]) <= mounted


def test_published_schema_matches_the_app_document():
    """P3-11: serve publishes its OpenAPI document at its own openapi_url, equal to app.openapi()."""
    app = create_openai_app()
    assert app.openapi_url, "P3-11: serve must publish its schema"
    with TestClient(app) as client:
        served = client.get(app.openapi_url)
    assert served.status_code == 200
    assert served.json() == app.openapi()


# banner layer


def test_serve_banner_docs_line_is_served_by_the_app(monkeypatch: pytest.MonkeyPatch):
    """P3-11: the printed Docs URL must be the app's own docs path, so the banner makes no
    promise this process does not host."""
    app = create_openai_app()
    assert app.docs_url, "P3-11: serve should host a docs page for the banner to name"
    banner = _serve_banner(monkeypatch)
    docs_url = next(
        (line.split(":", 1)[1].strip() for line in banner.splitlines() if line.strip().startswith("Docs:")),
        None,
    )
    assert docs_url, "serve hosts docs but the banner prints no Docs line"
    assert urlparse(docs_url).path == app.docs_url
    with TestClient(app) as client:
        assert client.get(app.docs_url).status_code == 200


# behaviour layer


def test_models_entry_carries_the_openai_model_fields(fake_provider, monkeypatch: pytest.MonkeyPatch):
    """id/object/created/owned_by are the four fields a consumer reads off every entry."""
    monkeypatch.setattr("server.openai.TIER_MAP", {})
    monkeypatch.setattr(
        "server.openai.get_active_provider",
        lambda: SimpleNamespace(model="mine:work", provider="local_ollama", base_url=""),
    )
    with TestClient(create_openai_app()) as client:
        body = client.get("/v1/models").json()
    assert body["object"] == "list"
    entry = body["data"][0]
    assert set(entry) == {"id", "object", "created", "owned_by"}
    assert entry["object"] == "model"


def test_completion_body_matches_the_openai_contract(fake_provider):
    """The fields a client parses, pinned one by one, with usage summing to its parts."""
    with TestClient(create_openai_app()) as client:
        resp = client.post(
            CHAT_URL,
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == resp.headers["X-Request-ID"]
    assert body["object"] == "chat.completion"
    assert isinstance(body["created"], int)
    assert body["model"] == "m"
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"]["role"] == "assistant"
    usage = body["usage"]
    assert {"prompt_tokens", "completion_tokens", "total_tokens", "usage_estimated"} <= set(usage)
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert resp.headers["X-Usage-Estimated"] in {"true", "false"}


def test_stream_frames_are_openai_chunks_terminated_by_done(fake_provider):
    """Each SSE frame is a chat.completion.chunk; a lone [DONE] closes the stream."""
    with TestClient(create_openai_app()) as client:
        with client.stream(
            "POST",
            CHAT_URL,
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        ) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            lines = [ln for ln in resp.iter_lines() if ln]
    assert lines[-1] == "data: [DONE]"
    frames = [json.loads(line[6:]) for line in lines[:-1] if line.startswith("data: ")]
    assert frames
    assert all(frame["object"] == "chat.completion.chunk" for frame in frames)
    assert "".join(frame["choices"][0]["delta"]["content"] for frame in frames) == FULL


def test_validation_error_uses_the_openai_envelope(fake_provider):
    """A rejected body answers 400 with error.code=validation_error and the request id."""
    with TestClient(create_openai_app()) as client:
        resp = client.post(CHAT_URL, json={"messages": []})
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert error["request_id"] == resp.headers["X-Request-ID"]


def test_missing_token_is_rejected_with_the_auth_code(fake_provider):
    """With api_token set, an unauthenticated call answers 401 and error.code=auth_error."""
    with TestClient(create_openai_app(api_token="secret")) as client:
        resp = client.get("/v1/models")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_error"


def test_every_response_carries_a_request_id(fake_provider):
    """The middleware stamps X-Request-ID on success and failure alike, the correlation key."""
    with TestClient(create_openai_app()) as client:
        ok = client.get("/v1/models")
        rejected = client.post(CHAT_URL, json={"messages": []})
    assert ok.headers.get("X-Request-ID", "").startswith("chatcmpl-")
    assert rejected.headers["X-Request-ID"] == rejected.json()["error"]["request_id"]


def test_unknown_route_uses_the_openai_error_envelope():
    """A client that walks into a wrong path still expects the error envelope it parses.

    W3-45: 404/405 get their code from core/provider_errors.status_error_code, the
    same table the auth and validation envelopes read.
    """
    with TestClient(create_openai_app()) as client:
        resp = client.get("/v1/unknown")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert resp.headers["X-Request-ID"] == resp.json()["error"]["request_id"]


# idempotency layer


def test_idempotency_key_never_breaks_a_request(fake_provider):
    """An unrecognised request header must not change the outcome: still 200, still a completion."""
    with TestClient(create_openai_app()) as client:
        resp = client.post(
            CHAT_URL,
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Idempotency-Key": "k-1"},
        )
    assert resp.status_code == 200
    assert resp.json()["object"] == "chat.completion"


def test_idempotency_key_replays_the_first_response(fake_provider):
    """P3-13: a repeated Idempotency-Key returns the first answer, a fresh key is its own call."""
    request = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    with TestClient(create_openai_app()) as client:
        first = client.post(CHAT_URL, json=request, headers={"Idempotency-Key": "k"})
        repeat = client.post(CHAT_URL, json=request, headers={"Idempotency-Key": "k"})
        other = client.post(CHAT_URL, json=request, headers={"Idempotency-Key": "k-other"})
    assert repeat.json() == first.json()
    assert repeat.headers["Idempotency-Replayed"].lower() == "true"
    assert other.json()["id"] != first.json()["id"]


def test_idempotency_key_conflicts_on_a_different_body(fake_provider):
    """P3-13: a spent key reused for another body is refused, so a retry cannot double-run."""
    with TestClient(create_openai_app()) as client:
        client.post(
            CHAT_URL,
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Idempotency-Key": "spent"},
        )
        conflict = client.post(
            CHAT_URL,
            json={"model": "m", "messages": [{"role": "user", "content": "other"}]},
            headers={"Idempotency-Key": "spent"},
        )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["request_id"] == conflict.headers["X-Request-ID"]
