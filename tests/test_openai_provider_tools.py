"""Task 1 TDD: the OpenAI-compatible provider delivers tools + reasoning.

Contract (from empirical DGX evidence, task 0):
- Request:  payload["tools"] has to carry the tool schemas (previously: `_ = tools`).
- Response: `reasoning_content` + `tool_calls` are extracted into ProviderMessage
  (thinking / tool_calls) so that the shared tool loop + thinking
  rendering take effect.
- Round-trip: the assistant message (tool_calls) + the tool results (tool_call_id)
  must be OpenAI-shape, otherwise 400 in round 2.
"""
from __future__ import annotations

import importlib
import json

import pytest


def _openai_client(monkeypatch):
    for key in [
        "EPHE_MODEL_PROVIDER",
        "EPHE_MODEL",
        "EPHE_CUSTOM_OLLAMA_BASE_URL",
        "EPHE_OPENAI_COMPAT_BASE_URL",
        "EPHE_OPENAI_COMPAT_API_KEY",
        "EPHE_LOCAL_OLLAMA_BASE_URL",
        "OLLAMA_HOST",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_MODEL", "qwen3.8-27b")
    import core.model_provider as provider

    return importlib.reload(provider)


async def test_openai_client_sends_tools_in_payload(monkeypatch):
    """The tool schemas have to land in the OpenAI payload (previously: _ = tools)."""
    provider = _openai_client(monkeypatch)
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, *, headers, json):
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(provider.httpx, "AsyncClient", FakeHttpClient)
    client = provider.build_provider_client(provider.get_active_provider())
    tools = [
        {
            "type": "function",
            "function": {
                "name": "count_files",
                "description": "Zählt Dateien.",
                "parameters": {
                    "type": "object",
                    "properties": {"pattern": {"type": "string"}},
                    "required": ["pattern"],
                },
            },
        }
    ]
    await client.chat(
        model="qwen3.8-27b",
        messages=[{"role": "user", "content": "count it"}],
        stream=False,
        tools=tools,
    )
    assert captured["json"].get("tools") == tools


async def test_openai_client_extracts_reasoning_and_tool_calls(monkeypatch):
    """reasoning_content → thinking, tool_calls → ProviderToolCall."""
    provider = _openai_client(monkeypatch)

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "Ich zähle die Dateien…",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "count_files",
                                        "arguments": '{"pattern": "*.py"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, *, headers, json):
            return FakeResponse()

    monkeypatch.setattr(provider.httpx, "AsyncClient", FakeHttpClient)
    client = provider.build_provider_client(provider.get_active_provider())
    response = await client.chat(
        model="qwen3.8-27b",
        messages=[{"role": "user", "content": "count it"}],
        stream=False,
    )
    msg = response.message
    assert msg.thinking == "Ich zähle die Dateien…"
    assert msg.tool_calls and len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.function.name == "count_files"
    assert tc.function.arguments == {"pattern": "*.py"}


async def test_openai_client_converts_tool_result_messages(monkeypatch):
    """Round-Trip: Ollama-shape history → OpenAI-shape (role=tool + tool_call_id).

    chat.py:755 appends `response.message` (ProviderMessage); chat.py:802
    appends `{"role":"tool","content":...}` — both have to become OpenAI-shape,
    otherwise 400 in round 2.
    """
    provider = _openai_client(monkeypatch)
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "fertig"}}]}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, *, headers, json):
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(provider.httpx, "AsyncClient", FakeHttpClient)
    client = provider.build_provider_client(provider.get_active_provider())

    assistant_msg = provider.ProviderMessage(
        content="",
        thinking="x",
        tool_calls=[
            provider.ProviderToolCall(
                function=provider.ProviderFunctionCall(
                    name="count_files", arguments={"pattern": "*.py"}
                )
            )
        ],
    )
    history = [
        {"role": "user", "content": "count it"},
        assistant_msg,  # Ollama-shape: no role field
        {"role": "tool", "tool_call_id": "call_0", "content": "3 Dateien"},  # the loop's id for this call
    ]
    await client.chat(
        model="qwen3.8-27b",
        messages=history,
        stream=False,
    )
    sent = captured["json"]["messages"]
    # assistant message: role + tool_calls with JSON arguments
    assert sent[1]["role"] == "assistant"
    assert "tool_calls" in sent[1]
    fn = sent[1]["tool_calls"][0]["function"]
    assert fn["name"] == "count_files"
    assert json.loads(fn["arguments"]) == {"pattern": "*.py"}
    # tool message: the tool_call_id must be set
    assert sent[2]["role"] == "tool"
    assert sent[2].get("tool_call_id")
