"""Non-thinking passthrough: thinking/reasoning_effort reach the request.

Measured 2026-10-11: DeepSeek's OpenAI-compatible API defaults thinking ON. The
reasoning text is billed against ``max_tokens`` and can consume the entire
budget unless the request carries ``"thinking": {"type": "disabled"}``. The
payload builder sent model/messages/temperature/top_p/max_tokens/
stream_options/tools and nothing that names thinking, so the engine default
applied to every installation.

Contract (the same ladder as the numeric generation values):
1. ``thinking`` / ``reasoning_effort`` are generation options of the engine
   config: env precedence (EPHE_THINKING / EPHE_REASONING_EFFORT), then the
   persisted engine.json ``generation`` block, then unset.
2. Both travel ONLY when set — an installation that configures nothing keeps
   exactly the request body it had (absence is preserved, no invented default;
   the top_p/max_tokens rule from test_generation_reaches_request_i25.py).
3. ``thinking`` is an object ({"type": "disabled"}); a bare mode string from
   the env ("disabled") is wrapped into that shape.
4. ``reasoning_effort`` is a string and travels as written.

The body is captured with ``httpx.MockTransport`` — a real transport inside a
real ``httpx.AsyncClient``, so what is asserted is the serialized wire body.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import httpx

GENERATION_ENVS = (
    "EPHE_TEMPERATURE", "EPHE_TOP_P", "EPHE_MAX_TOKENS",
    "EPHE_TOOL_BUDGET", "EPHE_CONTEXT_WINDOW", "EPHE_MEMORY_MAX_ENTRIES",
    "EPHE_THINKING", "EPHE_REASONING_EFFORT", "EPHE_THINKING_STYLE",
)

_THINKING_ENVS = ("EPHE_THINKING", "EPHE_REASONING_EFFORT")


class _WireRecorder:
    """Collects the request bodies the provider really serialized."""

    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})


def _provider(monkeypatch, tmp_path: Path, engine_json: dict | None = None):
    """A fresh provider whose HTTP client carries an httpx.MockTransport.

    Same isolation as test_generation_reaches_request_i25.py: the redirected
    config folder is the monkeypatched engine_config.CONFIG_DIR (EPHE_CONFIG_DIR
    at runtime has no effect — the engine.json path is resolved at import).
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

    recorder = _WireRecorder()
    real_client = httpx.AsyncClient

    def client_with_mock_transport(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(recorder.handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_with_mock_transport)
    return provider, recorder


def _engine_json(generation: dict | None = None) -> dict:
    body: dict = {
        "provider": "openai_compatible",
        "model": "qwen-test",
        "api_url": "http://127.0.0.1:8000/v1",
    }
    if generation is not None:
        body["generation"] = generation
    return body


async def _ask(
    provider, recorder: _WireRecorder, base_url: str = "http://127.0.0.1:8000/v1"
) -> dict:
    client = provider.OpenAICompatibleAsyncClient(base_url=base_url, api_key="test")
    await client.chat(model="qwen-test", messages=[{"role": "user", "content": "hi"}])
    assert recorder.bodies, "no request body captured at the transport"
    return recorder.bodies[-1]


# The next tests cover absence by default and malformed option values.

async def test_absence_by_default_keeps_todays_body(monkeypatch, tmp_path):
    """Nothing configured: neither field in the body — the I2-5 baseline stands."""
    provider, recorder = _provider(monkeypatch, tmp_path)
    body = await _ask(provider, recorder)
    assert "thinking" not in body, "thinking sent without a setting"
    assert "reasoning_effort" not in body, "reasoning_effort sent without a setting"
    assert body["temperature"] == 0.0


async def test_malformed_option_values_do_not_travel(monkeypatch, tmp_path):
    """A number/list is not an option value: dropped, never forwarded as a 400."""
    provider, recorder = _provider(
        monkeypatch, tmp_path,
        _engine_json({"thinking": 7, "reasoning_effort": ["low"]}),
    )
    body = await _ask(provider, recorder)
    assert "thinking" not in body
    assert "reasoning_effort" not in body


# The next tests cover the two fields reaching the wire when set.

async def test_thinking_object_reaches_the_request(monkeypatch, tmp_path):
    provider, recorder = _provider(
        monkeypatch, tmp_path, _engine_json({"thinking": {"type": "disabled"}})
    )
    body = await _ask(provider, recorder)
    assert body["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in body


async def test_thinking_bare_mode_from_env_is_wrapped(monkeypatch, tmp_path):
    """EPHE_THINKING=disabled → {"type": "disabled"} — the shape the API expects."""
    provider, recorder = _provider(monkeypatch, tmp_path)
    monkeypatch.setenv("EPHE_THINKING", "disabled")
    body = await _ask(provider, recorder)
    assert body["thinking"] == {"type": "disabled"}


async def test_reasoning_effort_from_engine_json(monkeypatch, tmp_path):
    provider, recorder = _provider(
        monkeypatch, tmp_path, _engine_json({"reasoning_effort": "none"})
    )
    body = await _ask(provider, recorder)
    assert body["reasoning_effort"] == "none"
    assert "thinking" not in body


async def test_env_precedence_beats_engine_json(monkeypatch, tmp_path):
    provider, recorder = _provider(
        monkeypatch, tmp_path,
        _engine_json({"thinking": {"type": "enabled"}, "reasoning_effort": "high"}),
    )
    monkeypatch.setenv("EPHE_THINKING", '{"type": "disabled"}')
    monkeypatch.setenv("EPHE_REASONING_EFFORT", "low")
    body = await _ask(provider, recorder)
    assert body["thinking"] == {"type": "disabled"}
    assert body["reasoning_effort"] == "low"


# The last test reads the generation options at the reader level.

def test_read_generation_options_reports_absence(monkeypatch, tmp_path):
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    for key in _THINKING_ENVS:
        monkeypatch.delenv(key, raising=False)
    assert ec.read_generation_options() == {"thinking": None, "reasoning_effort": None}


# WS1-6: the same configured intent on the other provider shapes the client
# reaches (vLLM/Qwen3, OpenRouter), and absolute absence in every style.

async def test_absence_holds_in_every_style(monkeypatch, tmp_path):
    """Nothing configured: no thinking field of any shape, in any style."""
    provider, recorder = _provider(monkeypatch, tmp_path)
    for style in ("native", "vllm", "openrouter"):
        monkeypatch.setenv("EPHE_THINKING_STYLE", style)
        body = await _ask(provider, recorder, base_url="https://openrouter.ai/api/v1")
        for field in ("thinking", "reasoning_effort", "chat_template_kwargs", "reasoning"):
            assert field not in body, f"{field} sent without a setting ({style})"


async def test_vllm_style_wraps_the_mode_as_enable_thinking(monkeypatch, tmp_path):
    """vLLM/Qwen3: EPHE_THINKING=disabled → chat_template_kwargs.enable_thinking=false."""
    provider, recorder = _provider(monkeypatch, tmp_path)
    monkeypatch.setenv("EPHE_THINKING_STYLE", "vllm")
    monkeypatch.setenv("EPHE_THINKING", "disabled")
    body = await _ask(provider, recorder)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "thinking" not in body, "the native field must not travel in the vllm shape"


async def test_vllm_style_reads_an_enabled_mode(monkeypatch, tmp_path):
    provider, recorder = _provider(
        monkeypatch, tmp_path, _engine_json({"thinking": {"type": "enabled"}})
    )
    monkeypatch.setenv("EPHE_THINKING_STYLE", "vllm")
    body = await _ask(provider, recorder)
    assert body["chat_template_kwargs"] == {"enable_thinking": True}


async def test_vllm_style_leaves_an_unrecognised_mode_out(monkeypatch, tmp_path):
    """An object with no mode word is not invented into a boolean."""
    provider, recorder = _provider(
        monkeypatch, tmp_path, _engine_json({"thinking": {"budget_tokens": 512}})
    )
    monkeypatch.setenv("EPHE_THINKING_STYLE", "vllm")
    body = await _ask(provider, recorder)
    assert "chat_template_kwargs" not in body


async def test_openrouter_host_uses_the_reasoning_object(monkeypatch, tmp_path):
    """openrouter.ai is detected: the intent travels as the gateway reads it."""
    provider, recorder = _provider(
        monkeypatch, tmp_path, _engine_json({"thinking": {"type": "disabled"}})
    )
    body = await _ask(provider, recorder, base_url="https://openrouter.ai/api/v1")
    assert body["reasoning"] == {"enabled": False}
    assert "thinking" not in body


async def test_openrouter_reasoning_effort_maps_to_the_effort_key(monkeypatch, tmp_path):
    provider, recorder = _provider(
        monkeypatch, tmp_path, _engine_json({"reasoning_effort": "high"})
    )
    body = await _ask(provider, recorder, base_url="https://openrouter.ai/api/v1")
    assert body["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in body


async def test_explicit_style_overrides_the_host(monkeypatch, tmp_path):
    """EPHE_THINKING_STYLE=native forces the native shape on an openrouter host."""
    provider, recorder = _provider(
        monkeypatch, tmp_path, _engine_json({"thinking": {"type": "disabled"}})
    )
    monkeypatch.setenv("EPHE_THINKING_STYLE", "native")
    body = await _ask(provider, recorder, base_url="https://openrouter.ai/api/v1")
    assert body["thinking"] == {"type": "disabled"}
    assert "reasoning" not in body


def test_unknown_style_falls_back_to_native(monkeypatch, tmp_path):
    provider, _ = _provider(monkeypatch, tmp_path)
    monkeypatch.setenv("EPHE_THINKING_STYLE", "gemini")
    fields = provider.thinking_request_fields(
        {"thinking": {"type": "disabled"}, "reasoning_effort": None}, "http://host:8000/v1"
    )
    assert fields == {"thinking": {"type": "disabled"}}


def test_thinking_request_fields_empty_when_unset(monkeypatch, tmp_path):
    provider, _ = _provider(monkeypatch, tmp_path)
    for style in ("native", "vllm", "openrouter"):
        monkeypatch.setenv("EPHE_THINKING_STYLE", style)
        assert provider.thinking_request_fields(
            {"thinking": None, "reasoning_effort": None},
            "https://openrouter.ai/api/v1",
        ) == {}
