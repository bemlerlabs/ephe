"""I2-5 path A: the generation controls reach the request.

Finding before this wave (re-measured):
- core/model_provider.py hard-coded `"temperature": 0.0` in the payload.
- `top_p` and `max_tokens` were NEVER sent.
- core/engine_config.read_generation_values() — the function that brings together
  env precedence, engine.json and the default — existed but was only called by
  server/routes/settings.py, i.e. by the display. The settings card therefore
  showed three controls whose value landed in not a single request.

Contract (path A, owner decision 2026-10-03):
1. The payload takes temperature from the active generation values.
2. top_p / max_tokens are only sent when a value is set — their default is None
   ("unsettable", optional per model). An invented cap would be a change for every
   existing installation.
3. Without any setting the behaviour stays IDENTICAL to before: temperature 0.0,
   no top_p, no max_tokens.
4. Env precedence beats engine.json (as documented in the read path).
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

GENERATION_ENVS = (
    "EPHE_TEMPERATURE", "EPHE_TOP_P", "EPHE_MAX_TOKENS",
    "EPHE_TOOL_BUDGET", "EPHE_CONTEXT_WINDOW", "EPHE_MEMORY_MAX_ENTRIES",
)


class _CapturingClient:
    """Minimal httpx stand-in: records the JSON sent, returns an answer."""

    last_payload: dict | None = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    async def post(self, _url, *, json=None, headers=None, timeout=None):
        _CapturingClient.last_payload = json

        class _R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        return _R()


def _provider(monkeypatch, tmp_path: Path, engine_json: dict | None = None):
    """A fresh provider against an OpenAI-compatible engine, config in tmp_path.

    The redirected config folder here is the monkeypatched module constant
    `engine_config.CONFIG_DIR` — the same loop tests/conftest.py uses and the one
    core/image_config.py explicitly documents as the only working path. Setting
    EPHE_CONFIG_DIR at runtime has no effect: the engine.json path is resolved at
    import time.
    """
    for key in (
        "EPHE_MODEL_PROVIDER", "EPHE_MODEL", "EPHE_OPENAI_COMPAT_BASE_URL",
        "EPHE_OPENAI_COMPAT_API_KEY", "EPHE_LOCAL_OLLAMA_BASE_URL",
        "EPHE_CUSTOM_OLLAMA_BASE_URL", "OLLAMA_HOST",
        *GENERATION_ENVS,
    ):
        monkeypatch.delenv(key, raising=False)

    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    if engine_json is not None:
        (tmp_path / "engine.json").write_text(json.dumps(engine_json), encoding="utf-8")

    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_MODEL", "qwen-test")
    provider = importlib.reload(importlib.import_module("core.model_provider"))
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    _CapturingClient.last_payload = None
    return provider


async def _ask(provider) -> dict:
    client = provider.OpenAICompatibleAsyncClient(
        base_url="http://127.0.0.1:8000/v1", api_key="test"
    )
    await client.chat(model="qwen-test", messages=[{"role": "user", "content": "hi"}])
    assert _CapturingClient.last_payload is not None, "kein Payload abgefangen"
    return _CapturingClient.last_payload


@pytest.mark.asyncio
async def test_defaults_keep_todays_behaviour(monkeypatch, tmp_path):
    """Without settings: temperature 0.0, top_p/max_tokens NOT in the payload.

    This is the proof that path A does not rewire an existing installation — the
    control only acts once somebody moves it.
    """
    payload = await _ask(_provider(monkeypatch, tmp_path))
    assert payload["temperature"] == 0.0
    assert "top_p" not in payload, "top_p wurde ohne Einstellung gesendet"
    assert "max_tokens" not in payload, "max_tokens wurde ohne Einstellung gesendet"


@pytest.mark.asyncio
async def test_engine_json_reaches_the_request(monkeypatch, tmp_path):
    """What the settings card shows has to be in the request — that is path A."""
    provider = _provider(
        monkeypatch,
        tmp_path,
        {"provider": "openai_compatible", "model": "qwen-test",
         "api_url": "http://127.0.0.1:8000/v1",
         "generation": {"temperature": 0.7, "top_p": 0.9, "max_tokens": 2048}},
    )
    payload = await _ask(provider)
    assert payload["temperature"] == pytest.approx(0.7)
    assert payload["top_p"] == pytest.approx(0.9)
    assert payload["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_env_precedence_beats_engine_json(monkeypatch, tmp_path):
    """The documented precedence also holds in the request path: env first."""
    provider = _provider(
        monkeypatch,
        tmp_path,
        {"provider": "openai_compatible", "model": "qwen-test",
         "api_url": "http://127.0.0.1:8000/v1",
         "generation": {"temperature": 0.7, "max_tokens": 2048}},
    )
    monkeypatch.setenv("EPHE_TEMPERATURE", "0.2")
    monkeypatch.setenv("EPHE_MAX_TOKENS", "512")
    payload = await _ask(provider)
    assert payload["temperature"] == pytest.approx(0.2)
    assert payload["max_tokens"] == 512


@pytest.mark.asyncio
async def test_partial_setting_sends_only_that_value(monkeypatch, tmp_path):
    """Only top_p set: top_p goes, max_tokens stays away — no invented cap."""
    provider = _provider(
        monkeypatch,
        tmp_path,
        {"provider": "openai_compatible", "model": "qwen-test",
         "api_url": "http://127.0.0.1:8000/v1",
         "generation": {"top_p": 0.95}},
    )
    payload = await _ask(provider)
    assert payload["top_p"] == pytest.approx(0.95)
    assert "max_tokens" not in payload
    assert payload["temperature"] == 0.0
