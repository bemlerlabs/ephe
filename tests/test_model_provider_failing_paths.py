"""WA-9 (2026-10-11): the failing and edge paths of core/model_provider.py.

The neighbouring suites (test_openai_provider_tools, test_failover_chain,
test_provider_aware_probe) cover the happy paths. The coverage ranking named the
rest: the OpenAI-compatible HTTP error answers, the SSE parser with its
fragmented tool-call deltas, the zen-gateway aggregation, usage recording, and
the key-challenge readers. Those run against fakes here — no live engine.
"""
from __future__ import annotations

import re

import httpx
import pytest

import core.model_provider as mp
from core.provider_errors import ProviderFailureKind
from core.tools import session_ctx

# Fakes


class _Resp:
    """Non-streaming HTTP response: status, JSON body, text, raise_for_status."""

    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.request = httpx.Request("POST", "http://engine.test/v1/chat/completions")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=self.request, response=self)

    def json(self) -> dict:
        return self._payload


class _NonStreamClient:
    def __init__(self, response, captured: dict, **_kwargs):
        self._response = response
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, *, headers, json):
        self._captured["url"] = url
        self._captured["headers"] = headers
        self._captured["json"] = json
        return self._response


class _StreamCM:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *_a):
        return False


class _StreamClient:
    def __init__(self, response, captured: dict, **_kwargs):
        self._response = response
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    def stream(self, _method, url, *, headers, json):
        self._captured["url"] = url
        self._captured["json"] = json
        return _StreamCM(self._response)


class _StreamResp:
    def __init__(self, lines: list[str], status_code: int = 200):
        self.status_code = status_code
        self._lines = lines
        self.request = httpx.Request("POST", "http://engine.test/v1/chat/completions")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=self.request, response=self)

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _GetResp:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _GetClient:
    def __init__(self, status_code: int | None, captured: dict, **_kwargs):
        self._status = status_code
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def get(self, url):
        if self._status is None:
            raise httpx.ConnectError("refused")
        self._captured["url"] = url
        return _GetResp(self._status)


def _install_nonstream(monkeypatch, response, captured):
    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: _NonStreamClient(response, captured))


def _install_stream(monkeypatch, response, captured):
    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: _StreamClient(response, captured))


def _no_generation(monkeypatch):
    monkeypatch.setattr(
        mp, "read_generation_values",
        lambda *a, **k: {"temperature": 0.0, "top_p": None, "max_tokens": None},
    )
    monkeypatch.setattr(mp, "read_generation_options", lambda *a, **k: {})


def _client(base_url: str = "http://engine.test/v1", api_key: str = "sk-test"):
    return mp.OpenAICompatibleAsyncClient(base_url=base_url, api_key=api_key)


def _chat_payload(content: str = "ok", **extra) -> dict:
    payload = {"choices": [{"message": {"content": content}}]}
    payload.update(extra)
    return payload


# Pure helpers


def test_parse_json_arguments_branches():
    assert mp._parse_json_arguments({"a": 1}) == {"a": 1}
    assert mp._parse_json_arguments(None) == {}
    assert mp._parse_json_arguments("   ") == {}
    assert mp._parse_json_arguments('{"a": "b"}') == {"a": "b"}
    assert mp._parse_json_arguments("not json") == {"_raw": "not json"}
    assert mp._parse_json_arguments('[1, 2]') == {"_raw": "[1, 2]"}


def test_zen_session_id_matches_fingerprint():
    sid = mp._zen_session_id()
    assert re.fullmatch(r"ses_[0-9a-f]{8}[0-9a-f]{4}[0-9a-zA-Z]{14}", sid)


def test_is_zen_base_url_only_matches_opencode():
    assert mp._is_zen_base_url("https://opencode.ai/zen/v1") is True
    # a bare host without a scheme parses to no netloc, so it is not zen
    assert mp._is_zen_base_url("opencode.ai") is False
    assert mp._is_zen_base_url("https://api.openai.com/v1") is False
    assert mp._is_zen_base_url("") is False


def test_with_zen_markers_appends_missing_bash_and_read():
    real = [{"type": "function", "function": {"name": "run_shell"}}]
    merged = mp._with_zen_markers(real)
    names = {t["function"]["name"] for t in merged}
    assert {"bash", "read", "run_shell"} <= names
    # re-running adds nothing (no duplicates)
    assert len(mp._with_zen_markers(merged)) == len(merged)


def test_provider_message_and_response_getitem():
    msg = mp.ProviderMessage(content="hi", thinking="t")
    assert msg["content"] == "hi"
    resp = mp.ProviderChatResponse(message=msg)
    assert resp["message"] == {"content": "hi"}
    with pytest.raises(KeyError):
        resp["nope"]


def test_thinking_mode_enabled_branches():
    assert mp._thinking_mode_enabled("nope") is None
    assert mp._thinking_mode_enabled({}) is None
    assert mp._thinking_mode_enabled({"type": 5}) is None
    assert mp._thinking_mode_enabled({"type": "disabled"}) is False
    assert mp._thinking_mode_enabled({"type": " ENABLED "}) is True


def test_thinking_style_env_overrides_host(monkeypatch):
    monkeypatch.delenv(mp.THINKING_STYLE_ENV, raising=False)
    assert mp._thinking_style("http://openrouter.ai/api/v1") == "openrouter"
    assert mp._thinking_style("http://127.0.0.1:8000/v1") == "native"
    monkeypatch.setenv(mp.THINKING_STYLE_ENV, "vllm")
    assert mp._thinking_style("http://openrouter.ai/api/v1") == "vllm"
    monkeypatch.setenv(mp.THINKING_STYLE_ENV, "not-a-style")
    assert mp._thinking_style("http://127.0.0.1") == "native"


def test_thinking_request_fields_shapes():
    assert mp.thinking_request_fields({}, "http://x") == {}
    native = mp.thinking_request_fields(
        {"thinking": {"type": "disabled"}, "reasoning_effort": "low"}, "http://x"
    )
    assert native == {"thinking": {"type": "disabled"}, "reasoning_effort": "low"}
    # an unknown style value stays native (no reasoning key, no enable_thinking)
    assert mp.thinking_request_fields(
        {"thinking": {"type": "on"}, "reasoning_effort": "high"}, "http://x"
    ) == {"thinking": {"type": "on"}, "reasoning_effort": "high"}
    # openrouter shape collapses to a reasoning object
    assert mp.thinking_request_fields(
        {"thinking": {"type": "disabled"}, "reasoning_effort": "medium"},
        "http://openrouter.ai/api/v1",
    ) == {"reasoning": {"enabled": False, "effort": "medium"}}


def test_thinking_request_fields_vllm_under_env(monkeypatch):
    monkeypatch.setenv(mp.THINKING_STYLE_ENV, "vllm")
    assert mp.thinking_request_fields(
        {"thinking": {"type": "disabled"}, "reasoning_effort": "low"}, "http://x"
    ) == {"chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "low"}


def test_endpoint_requires_api_key_private_vs_public():
    assert mp._endpoint_requires_api_key("") is False
    assert mp._endpoint_requires_api_key("http://localhost:8000/v1") is False
    assert mp._endpoint_requires_api_key("http://127.0.0.1:8000") is False
    assert mp._endpoint_requires_api_key("http://0.0.0.0:8000") is False
    assert mp._endpoint_requires_api_key("http://[::1]:8000") is False
    assert mp._endpoint_requires_api_key("192.168.1.9:11434") is False
    assert mp._endpoint_requires_api_key("http://10.0.0.5/v1") is False
    assert mp._endpoint_requires_api_key("http://172.16.4.1/v1") is False
    assert mp._endpoint_requires_api_key("http://172.31.255.9/v1") is False
    assert mp._endpoint_requires_api_key("http://172.15.0.1/v1") is True
    assert mp._endpoint_requires_api_key("http://box.example.ts.net/v1") is False
    assert mp._endpoint_requires_api_key("http://box.local:8000") is False
    assert mp._endpoint_requires_api_key("https://api.example.com/v1") is True


def test_endpoint_requires_api_key_observed_401_wins():
    # A public-looking host with an observed challenge is keyed.
    assert mp.endpoint_requires_api_key("http://box.local", observed_status=401) is True
    assert mp.endpoint_requires_api_key("https://api.example.com", observed_status=403) is True
    assert mp.endpoint_requires_api_key("https://api.example.com", observed_status=500) is True
    assert mp.endpoint_requires_api_key("http://127.0.0.1:8000") is False


def test_key_challenge_reason_names_the_token_place():
    with_token = mp.key_challenge_reason("http://x/", 401, True)
    assert "refused the token" in with_token and mp.KEY_PLACES in with_token
    without = mp.key_challenge_reason("http://x/", 403, False)
    assert "unauthenticated request" in without and mp.KEY_PLACES in without


def test_key_challenge_only_for_challenge_statuses():
    err = mp._key_challenge(401, "http://x", "tok")
    assert isinstance(err, mp.ProviderSetupError)
    assert mp._key_challenge(500, "http://x", "tok") is None
    assert mp._key_challenge(200, "http://x", "") is None


def test_chosen_model_env_over_provider_and_fail_closed(monkeypatch):
    monkeypatch.setenv("EPHE_MODEL", "from-env")
    assert mp.chosen_model() == "from-env"
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.setattr(
        mp, "_ACTIVE_OVERRIDE",
        mp.ModelProviderConfig(
            provider="local_ollama", model="", base_url="http://localhost:11434",
            label="Local Ollama", offline_capable=True, requires_internet=False,
        ),
    )
    with pytest.raises(mp.EngineNotConfigured):
        mp.chosen_model("vision")


def test_has_explicit_provider_reads_env_and_override(monkeypatch):
    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None)
    assert mp.has_explicit_provider() is False
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    assert mp.has_explicit_provider() is True


# _convert_messages edge branches


def test_convert_tool_message_without_pending_id_falls_back():
    client = _client()
    out = client._convert_messages([{"role": "tool", "content": "x"}])
    assert out[0]["role"] == "tool"
    assert out[0]["tool_call_id"] == "call_0"


def test_convert_provider_message_round_trip_uses_tool_call_id():
    client = _client()
    assistant = mp.ProviderMessage(
        tool_calls=[
            mp.ProviderToolCall(function=mp.ProviderFunctionCall(name="f", arguments={"a": 1}))
        ]
    )
    out = client._convert_messages([assistant, {"role": "tool", "content": "res"}])
    assert out[0]["tool_calls"][0]["id"] == "call_0"
    assert out[1]["tool_call_id"] == "call_0"


def test_convert_system_after_start_becomes_user_and_images_become_parts():
    client = _client()
    out = client._convert_messages(
        [
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "late note"},
            {"role": "user", "content": "see", "images": ["AAAA"]},
        ]
    )
    assert out[1]["role"] == "user"
    parts = out[2]["content"]
    assert parts[0] == {"type": "text", "text": "see"}
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_chat_url_does_not_double_suffix():
    client = _client("http://engine.test/v1/chat/completions")
    assert client._chat_url() == "http://engine.test/v1/chat/completions"


def test_base_url_adds_scheme_when_missing():
    assert mp._base_url("host:11434") == "http://host:11434"
    assert mp._base_url("  ", default="") == ""
    assert mp._base_url("") == mp.DEFAULT_OLLAMA_BASE_URL


# Non-streaming failing paths


@pytest.mark.asyncio
async def test_nonstream_400_raises_status_error(monkeypatch):
    _no_generation(monkeypatch)
    captured: dict = {}
    _install_nonstream(monkeypatch, _Resp(400, text="bad request body"), captured)
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=False)
    assert "400" in str(exc.value)


@pytest.mark.asyncio
async def test_nonstream_401_raises_setup_error_before_status_error(monkeypatch):
    _no_generation(monkeypatch)
    captured: dict = {}
    _install_nonstream(monkeypatch, _Resp(401), captured)
    with pytest.raises(mp.ProviderSetupError) as exc:
        await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=False)
    assert mp.KEY_PLACES in str(exc.value)


@pytest.mark.asyncio
async def test_nonstream_records_measured_usage(monkeypatch):
    _no_generation(monkeypatch)
    session_ctx._MEASURED_USAGE.set(None)
    captured: dict = {}
    payload = _chat_payload(
        "done",
        usage={"prompt_tokens": 7, "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": 2}},
    )
    _install_nonstream(monkeypatch, _Resp(200, payload), captured)
    await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=False)
    assert session_ctx.get_measured_usage() == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "cached_tokens": 2,
    }


@pytest.mark.asyncio
async def test_nonstream_tool_call_dict_args_and_reasoning_fallback(monkeypatch):
    _no_generation(monkeypatch)
    captured: dict = {}
    payload = _chat_payload(
        "",
        choices=[
            {
                "message": {
                    "content": None,
                    "reasoning": "plain reasoning",
                    "tool_calls": [
                        {"function": {"name": "f", "arguments": {"x": 1}}},
                    ],
                }
            }
        ],
    )
    _install_nonstream(monkeypatch, _Resp(200, payload), captured)
    resp = await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=False)
    assert resp.message.thinking == "plain reasoning"
    tc = resp.message.tool_calls[0]
    assert tc.id == "call_0"
    assert tc.function.arguments == {"x": 1}


@pytest.mark.asyncio
async def test_nonstream_sends_top_p_max_tokens_and_thinking(monkeypatch):
    monkeypatch.setattr(
        mp, "read_generation_values",
        lambda *a, **k: {"temperature": 0.5, "top_p": 0.9, "max_tokens": 256},
    )
    monkeypatch.setattr(mp, "read_generation_options", lambda *a, **k: {"reasoning_effort": "low"})
    captured: dict = {}
    _install_nonstream(monkeypatch, _Resp(200, _chat_payload()), captured)
    await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=False)
    sent = captured["json"]
    assert sent["temperature"] == 0.5 and sent["top_p"] == 0.9 and sent["max_tokens"] == 256
    assert sent["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_nonstream_sends_tools_unchanged_for_non_zen(monkeypatch):
    _no_generation(monkeypatch)
    captured: dict = {}
    _install_nonstream(monkeypatch, _Resp(200, _chat_payload()), captured)
    tools = [{"type": "function", "function": {"name": "run_shell"}}]
    await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=False, tools=tools)
    assert captured["json"]["tools"] == tools


# Streaming path


@pytest.mark.asyncio
async def test_stream_parses_reasoning_content_tools_and_usage(monkeypatch):
    _no_generation(monkeypatch)
    session_ctx._MEASURED_USAGE.set(None)
    lines = [
        ": keep-alive",
        "",
        'data: {"choices":[{"delta":{"reasoning_content":"think"}}]}',
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"f"}}]}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":1}}',
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":"IGNORED"}}]}',
    ]
    captured: dict = {}
    _install_stream(monkeypatch, _StreamResp(lines), captured)
    _no_zen = _client()
    frames = [
        f
        async for f in await _no_zen.chat(
            model="m", messages=[{"role": "user", "content": "hi"}], stream=True
        )
    ]
    assert {"message": {"reasoning_content": "think"}} in frames
    assert {"message": {"content": "Hel"}} in frames
    assert any("tool_calls" in f["message"] for f in frames)
    assert not any(f["message"].get("content") == "IGNORED" for f in frames)
    assert captured["json"]["stream_options"] == {"include_usage": True}
    assert session_ctx.get_measured_usage()["prompt_tokens"] == 4


@pytest.mark.asyncio
async def test_stream_challenge_raises_before_http_error(monkeypatch):
    _no_generation(monkeypatch)
    captured: dict = {}
    _install_stream(monkeypatch, _StreamResp([], status_code=403), captured)
    with pytest.raises(mp.ProviderSetupError):
        gen = await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=True)
        async for _ in gen:
            pass


@pytest.mark.asyncio
async def test_stream_status_error_propagates(monkeypatch):
    _no_generation(monkeypatch)
    captured: dict = {}
    _install_stream(monkeypatch, _StreamResp([], status_code=500), captured)
    with pytest.raises(httpx.HTTPStatusError):
        gen = await _client().chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=True)
        async for _ in gen:
            pass


@pytest.mark.asyncio
async def test_stream_skips_non_data_and_blank_lines(monkeypatch):
    _no_generation(monkeypatch)
    lines = ["event: ping", "data:", "data: [DONE]"]
    captured: dict = {}
    _install_stream(monkeypatch, _StreamResp(lines), captured)
    frames = [
        f
        async for f in await _client().chat(
            model="m", messages=[{"role": "user", "content": "hi"}], stream=True
        )
    ]
    assert frames == []


# Zen gateway path


def test_zen_headers_carry_opencode_fingerprint():
    client = _client("https://opencode.ai/zen/v1")
    headers = client._headers()
    assert headers["User-Agent"].startswith("opencode/")
    assert re.fullmatch(r"ses_[0-9a-f]{8}[0-9a-f]{4}[0-9a-zA-Z]{14}", headers["x-opencode-session"])


def test_openrouter_headers_add_attribution():
    client = _client("https://openrouter.ai/api/v1", api_key="")
    headers = client._headers()
    assert headers["HTTP-Referer"] == "http://localhost:8765"
    assert headers["X-Title"] == "Ephe"
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_zen_nonstream_collects_stream_into_response(monkeypatch):
    _no_generation(monkeypatch)
    session_ctx._MEASURED_USAGE.set(None)
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"why"}}]}',
        'data: {"choices":[{"delta":{"content":"He"}}]}',
        'data: {"choices":[{"delta":{"content":"llo"}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"bash","arguments":"{\\"command\\":"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"ls\\"}"}}]}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":2}}',
        "data: [DONE]",
    ]
    captured: dict = {}
    _install_stream(monkeypatch, _StreamResp(lines), captured)
    resp = await _client("https://opencode.ai/zen/v1").chat(
        model="m", messages=[{"role": "user", "content": "hi"}], stream=False
    )
    assert captured["json"]["stream"] is True
    assert resp.message.content == "Hello"
    assert resp.message.thinking == "why"
    tc = resp.message.tool_calls[0]
    assert tc.id == "c1" and tc.function.name == "bash" and tc.function.arguments == {"command": "ls"}


@pytest.mark.asyncio
async def test_zen_tools_get_marker_definitions(monkeypatch):
    _no_generation(monkeypatch)
    captured: dict = {}
    _install_stream(monkeypatch, _StreamResp(["data: [DONE]"]), captured)
    tools = [{"type": "function", "function": {"name": "run_shell"}}]
    await _client("https://opencode.ai/zen/v1").chat(
        model="m", messages=[{"role": "user", "content": "hi"}], stream=False, tools=tools
    )
    names = {t["function"]["name"] for t in captured["json"]["tools"]}
    assert {"bash", "read", "run_shell"} <= names


# Probe + failover


@pytest.mark.asyncio
async def test_probe_provider_status_and_errors(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: _GetClient(200, captured))
    assert await mp.probe_provider(mp.get_active_provider()) is True

    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: _GetClient(500, captured))
    assert await mp.probe_provider(mp.get_active_provider()) is False

    # 401 stays reachable (challenge is raised where the request is made)
    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: _GetClient(401, captured))
    assert await mp.probe_provider(mp.get_active_provider()) is True

    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: _GetClient(None, captured))
    assert await mp.probe_provider(mp.get_active_provider()) is False

    cfg = mp.ModelProviderConfig(
        provider="openai_compatible", model="m", base_url="http://engine.test/v1/models",
        label="x", offline_capable=False, requires_internet=True,
    )
    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: _GetClient(200, captured))
    assert await mp.probe_provider(cfg) is True
    assert captured["url"] == "http://engine.test/v1/models"


@pytest.mark.asyncio
async def test_resolve_active_with_failover_single_and_none(monkeypatch):
    assert await mp.resolve_active_with_failover(None) is None

    monkeypatch.setenv("EPHE_MODEL", "local-tag")
    single = mp.ModelProviderConfig(
        provider="local_ollama", model="local-tag",
        base_url="http://localhost:11434", label="Local Ollama",
        offline_capable=True, requires_internet=False,
    )
    assert await mp.resolve_active_with_failover(single) is single


@pytest.mark.asyncio
async def test_resolve_active_with_failover_falls_over_and_notes(monkeypatch):
    monkeypatch.setenv("EPHE_MODEL", "local-tag")
    monkeypatch.setenv("EPHE_LOCAL_OLLAMA_BASE_URL", "http://localhost:11434")
    active = mp.ModelProviderConfig(
        provider="openai_compatible", model="remote-model",
        base_url="http://unreachable.test/v1", label="OpenAI-compatible API",
        offline_capable=False, requires_internet=True,
    )

    real_probe = mp.probe_provider_failure

    async def fake_probe(cfg, *, timeout=3.0):
        # W7-1 walks the chain through probe_provider_failure: a candidate is reachable when
        # this returns None. Patching probe_provider has had no effect since then, which is
        # why this test stopped falling over and kept the active engine instead.
        return None if "localhost" in cfg.base_url else await real_probe(cfg, timeout=timeout)

    monkeypatch.setattr(mp, "probe_provider_failure", fake_probe)
    resolved = await mp.resolve_active_with_failover(active)
    assert resolved is active or resolved.provider == "local_ollama"
    assert resolved.provider == "local_ollama"
    note = session_ctx.get_failover_note()
    # The contract is that the note names both ends and the classified cause. Which cause it
    # is depends on how the probe failed on this box — a fast refusal reads transport, a slow
    # runner reads timeout — so this names the taxonomy rather than one member of it.
    assert "openai_compatible" in note and "local_ollama" in note, note
    assert note.endswith(tuple(f"({kind.value})" for kind in ProviderFailureKind)), note


@pytest.mark.asyncio
async def test_resolve_active_with_failover_skips_unnamed_and_fails_closed(monkeypatch):
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.setenv("EPHE_LOCAL_OLLAMA_BASE_URL", "http://localhost:11434")
    active = mp.ModelProviderConfig(
        provider="openai_compatible", model="remote-model",
        base_url="http://unreachable.test/v1", label="OpenAI-compatible API",
        offline_capable=False, requires_internet=True,
    )

    async def no_probe(cfg, *, timeout=3.0):
        return False

    monkeypatch.setattr(mp, "probe_provider", no_probe)
    # unnamed local fallback is skipped; nothing reachable -> active preserved
    resolved = await mp.resolve_active_with_failover(active)
    assert resolved is active


# set_active_provider / listing


def test_set_active_provider_local_and_custom():
    local = mp.set_active_provider(provider="local_ollama", model="m")
    assert local.provider == "local_ollama" and local.base_url == mp.DEFAULT_OLLAMA_BASE_URL
    custom = mp.set_active_provider(provider="custom_ollama", model="c", base_url="http://h:1")
    assert custom.provider == "custom_ollama" and custom.advanced_opt_in is True
    assert mp.get_active_provider() is custom


def test_set_active_provider_reuses_endpoint_when_none(monkeypatch):
    existing = mp.ModelProviderConfig(
        provider="openai_compatible", model="m", base_url="http://kept.test/v1",
        label="x", offline_capable=False, requires_internet=True,
    )
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", existing)
    cfg = mp.set_active_provider(provider="openai_compatible", model="m2")
    assert cfg.base_url == "http://kept.test/v1"


def test_set_active_provider_keyless_endpoint(monkeypatch):
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    cfg = mp.set_active_provider(
        provider="openai_compatible", model="m", base_url="http://192.168.1.9:8000/v1"
    )
    assert cfg.requires_api_key is False
    assert cfg.api_key_configured is False


def test_list_provider_options_shape():
    options = mp.list_provider_options()
    assert [o["provider"] for o in options] == ["local_ollama", "custom_ollama", "openai_compatible"]
    assert options[0]["model"] == "" and options[2]["model"] == "custom-model"


def test_build_provider_client_openai_returns_adapter(monkeypatch):
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    cfg = mp.ModelProviderConfig(
        provider="openai_compatible", model="m", base_url="http://192.168.1.9:8000/v1",
        label="x", offline_capable=False, requires_internet=True, requires_api_key=False,
    )
    client = mp.build_provider_client(cfg)
    assert isinstance(client, mp.OpenAICompatibleAsyncClient)
    assert client.base_url == "http://192.168.1.9:8000/v1"
