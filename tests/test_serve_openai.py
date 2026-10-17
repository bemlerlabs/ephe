"""
◑ Ephe — contract tests for the OpenAI-compatible engine (Phase 3)
tests/test_serve_openai.py

Verifies the OpenAI contract of ``server.openai.create_openai_app``:
  - GET  /v1/models            → the model list of the active provider
  - POST /v1/chat/completions  → non-stream (one completion) + stream (SSE)
  - X-Auth-Token required when api_token is set (401 otherwise)
  - request validation (messages format)
  - published contract: /openapi.json (with /docs and /redoc)
  - the `ephe serve` banner names the routes this app serves

Runs offline: build_provider_client is mocked with a fake AsyncClient (no
Ollama and no network needed).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from server.openai import create_openai_app

CHUNKS = ["Hello", " from", " the", " Black", " Forest"]
FULL = "".join(CHUNKS)


class FakeClient:
    """Stand-in for build_provider_client(): yields an async iterator."""

    def chat(self, model, messages, stream):  # noqa: ARG002
        async def _gen():
            for chunk in CHUNKS:
                yield {"message": {"content": chunk}}

        return _gen()


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch):
    # build_provider_client is called with a config argument by now → *a/**k
    monkeypatch.setattr("server.openai.build_provider_client", lambda *a, **k: FakeClient())


# /v1/models


def test_models_advertises_nothing_until_a_tag_exists(fake_provider, monkeypatch):
    """/v1/models used to answer the shipped default tag for a model nobody chose.
    An unnamed tier and an unnamed active model list no id (owner decision 2026-10-11)."""
    monkeypatch.setattr("server.openai.TIER_MAP", {})
    monkeypatch.setattr(
        "server.openai.get_active_provider",
        lambda: SimpleNamespace(model="", provider="local_ollama", base_url=""),
    )
    with TestClient(create_openai_app()) as client:
        resp = client.get("/v1/models")
    assert resp.status_code == 200
    assert resp.json() == {"object": "list", "data": []}


def test_models_lists_the_active_tag(fake_provider, monkeypatch):
    monkeypatch.setattr("server.openai.TIER_MAP", {})
    monkeypatch.setattr(
        "server.openai.get_active_provider",
        lambda: SimpleNamespace(model="mine:work", provider="local_ollama", base_url=""),
    )
    with TestClient(create_openai_app()) as client:
        data = client.get("/v1/models").json()
    assert [item["id"] for item in data["data"]] == ["mine:work"]


# /v1/chat/completions — non-stream


def test_chat_non_stream_returns_single_completion(fake_provider):
    with TestClient(create_openai_app()) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gemma4:12b", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == FULL
    assert body["choices"][0]["finish_reason"] == "stop"


# /v1/chat/completions — SSE stream


def test_chat_stream_emits_sse_chunks_and_done(fake_provider):
    with TestClient(create_openai_app()) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gemma4:12b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            # iter_lines() splits on \n → drop the empty separator lines between events
            lines = [ln for ln in resp.iter_lines() if ln]

    # N data chunks + 1 [DONE] terminator
    assert len(lines) == len(CHUNKS) + 1
    assert lines[-1] == "data: [DONE]"
    # Every data chunk must be valid OpenAI chunk JSON and carry delta.content
    collected = ""
    for line in lines[:-1]:
        assert line.startswith("data: ")
        payload = __import__("json").loads(line[6:])
        assert payload["object"] == "chat.completion.chunk"
        collected += payload["choices"][0]["delta"]["content"]
    assert collected == FULL


# Auth-Token


def test_models_rejects_request_without_token_when_configured(fake_provider):
    with TestClient(create_openai_app(api_token="supersecret")) as client:
        resp = client.get("/v1/models")
    assert resp.status_code == 401


def test_models_allows_request_with_correct_token(fake_provider):
    with TestClient(create_openai_app(api_token="supersecret")) as client:
        resp = client.get("/v1/models", headers={"X-Auth-Token": "supersecret"})
    assert resp.status_code == 200


def test_chat_rejects_missing_token_when_configured(fake_provider):
    with TestClient(create_openai_app(api_token="supersecret")) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 401


# Request validation


def test_chat_rejects_missing_messages(fake_provider):
    with TestClient(create_openai_app()) as client:
        resp = client.post("/v1/chat/completions", json={"model": "gemma4:12b"})
    assert resp.status_code == 400


def test_chat_rejects_empty_messages(fake_provider):
    with TestClient(create_openai_app()) as client:
        resp = client.post("/v1/chat/completions", json={"messages": []})
    assert resp.status_code == 400


def test_chat_rejects_message_without_content(fake_provider):
    with TestClient(create_openai_app()) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user"}]},
        )
    assert resp.status_code == 400


# Phase 3 Item 12 — the model router inside the engine (hardware adaptivity)

def _fake_router(monkeypatch, cfg):
    """Replaces get_router() with a fake whose resolve() returns cfg."""
    from core.model_router import ModelRouter  # type reference only

    router = Mock(spec=ModelRouter)
    router.resolve = AsyncMock(return_value=cfg)
    monkeypatch.setattr("server.openai.get_router", lambda: router)
    return router


def test_chat_resolves_router_when_no_model_given(fake_provider, monkeypatch):
    """WHEN the request has no model → the router resolves adaptively (FAST) + header."""
    from core.model_config import ModelConfig, ModelTier

    cfg = ModelConfig(name="gemma4:12b", tier=ModelTier.FAST)
    router = _fake_router(monkeypatch, cfg)

    with TestClient(create_openai_app()) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    # transparency per request
    assert resp.headers["x-model-tier"] == "fast"
    assert resp.headers["x-model-name"] == "gemma4:12b"
    assert resp.headers["x-model-provider"] == "ephe"
    router.resolve.assert_awaited_once()


def test_chat_explicit_model_skips_router(fake_provider, monkeypatch):
    """GIVEN an explicit model in the request → the router is NOT consulted."""
    router = _fake_router(monkeypatch, None)

    with TestClient(create_openai_app()) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gemma4:12b", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert resp.headers["x-model-tier"] == "explicit"
    assert resp.headers["x-model-name"] == "gemma4:12b"
    router.resolve.assert_not_awaited()


def test_chat_resolves_power_tier_for_remote(fake_provider, monkeypatch):
    """GIVEN the router returns POWER (DGX/ds4) → the header reports tier=power."""
    from core.model_config import ModelConfig, ModelTier

    cfg = ModelConfig(name="gemma4:26b", tier=ModelTier.POWER, host="dgx.local:11434")
    _fake_router(monkeypatch, cfg)

    with TestClient(create_openai_app()) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert resp.headers["x-model-tier"] == "power"
    assert resp.headers["x-model-name"] == "gemma4:26b"


def test_models_lists_the_tiers_the_user_named(fake_provider, monkeypatch):
    """GIVEN /v1/models → lists every configured tier (offline/fast/power) and nothing
    for the tiers left unnamed. The table used to carry three shipped default tags for
    models this machine never had (owner decision 2026-10-11)."""
    from core.model_config import ModelConfig, ModelTier

    monkeypatch.setattr(
        "server.openai.TIER_MAP",
        {tier: ModelConfig(name=f"mine:{tier.value}", tier=tier) for tier in ModelTier},
    )
    monkeypatch.setattr(
        "server.openai.get_active_provider",
        lambda: SimpleNamespace(model="mine:fast", provider="local_ollama", base_url=""),
    )
    with TestClient(create_openai_app()) as client:
        resp = client.get("/v1/models")

    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()["data"]}
    assert ids == {"mine:offline", "mine:fast", "mine:power"}
    assert resp.headers["x-model-provider"] == "ephe"


# Published contract — the schema is served, not locked in the source (P3-11)


def test_openapi_schema_is_served():
    with TestClient(create_openai_app()) as client:
        resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "Ephe OpenAI-compatible Engine"
    assert {"/v1/models", "/v1/chat/completions"} <= set(schema["paths"])


def test_docs_and_redoc_render_html():
    with TestClient(create_openai_app()) as client:
        docs = client.get("/docs")
        redoc = client.get("/redoc")
    assert docs.status_code == 200
    assert docs.headers["content-type"].startswith("text/html")
    assert redoc.status_code == 200
    assert redoc.headers["content-type"].startswith("text/html")


def test_schema_stays_public_while_data_endpoints_need_the_token(fake_provider):
    """The token guards the data; the contract is public by design."""
    with TestClient(create_openai_app(api_token="supersecret")) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/v1/models").status_code == 401


# Banner truth: `ephe serve` prints URLs the app it built actually serves.


def test_serve_banner_names_the_engine_app_routes(monkeypatch, capsys):
    """The banner used to print the PWA's /api/docs, which this app never serves."""
    import argparse

    import ephe_cli

    args = argparse.Namespace(host="127.0.0.1", port=8766, lan=False, token="", model=None)
    monkeypatch.setattr(
        ephe_cli,
        "engine_for_headless_run",
        lambda *_a, **_k: SimpleNamespace(provider="local_ollama", model="gemma4:12b"),
    )
    monkeypatch.setattr("uvicorn.run", lambda *_a, **_k: None)

    assert ephe_cli.cmd_serve(args) == 0

    out = capsys.readouterr().out
    app = create_openai_app()
    base = f"http://{args.host}:{args.port}"
    assert f"{base}{app.docs_url}" in out
    assert f"{base}{app.openapi_url}" in out
    assert "/api/docs" not in out
