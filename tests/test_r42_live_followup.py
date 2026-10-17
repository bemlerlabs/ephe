"""
◑ Ephe – R42 (round 2, E2): live cadence in the tool loop.
tests/test_r42_live_followup.py

RULE: the tests were written BEFORE the implementation.

Pins:
1. openai_compatible: the follow-up call after a tool runs streamed
   (stream=True) and the final text arrives LIVE via on_chunk (no bulk at the end).
2. The streamed follow-up content is NOT emitted again at the end
   (no duplicate), and the return value stays identical to the stream.
3. Ollama stays at stream=False (documented Ollama limit).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.chat import chat_with_tools
from core.model_provider import ModelProviderConfig


def _aiter(frames: list[dict]):
    async def gen():
        for f in frames:
            yield f
    return gen()


@pytest.mark.asyncio
async def test_followup_streams_for_openai_compatible():
    """
    GIVEN an openai_compatible provider; detection yields one tool call, follow-up streams text
    WHEN chat_with_tools runs
    THEN both engine calls used stream=True
    AND on_chunk received the final text frame by frame (no bulk, no duplicates)
    AND the return value equals the concatenation of the streamed text.
    """
    detect_frames = [
        {"message": {"tool_calls": [{
            "index": 0, "id": "c1",
            "function": {"name": "get_datetime", "arguments": "{}"},
        }]}},
    ]
    final_frames = [
        {"message": {"content": "Es ist "}},
        {"message": {"content": "Donnerstag."}},
    ]
    seq = iter([_aiter(detect_frames), _aiter(final_frames)])

    def chat_side_effect(**kwargs):
        return next(seq)

    cfg = ModelProviderConfig(
        provider="openai_compatible",
        model="gemma4",
        base_url="http://x/v1",
        label="Engine",
        offline_capable=True,
        requires_internet=False,
    )
    with patch("core.chat.build_provider_client") as build_client, patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="Donnerstag")
    ), patch(
        # R44: the failover chain probes for real — isolate it in the unit test, otherwise
        # the result depends on whether a local Ollama is currently running
        # (chain x/v1->ollama falls back to non-streaming).
        "core.chat.resolve_active_with_failover",
        new=AsyncMock(return_value=cfg),
    ):
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=chat_side_effect)
        build_client.return_value = client

        chunks: list[str] = []
        result = await chat_with_tools(
            model="gemma4",
            history=[{"role": "user", "content": "Datum?"}],
            on_chunk=chunks.append,
            allowed_tool_names=["get_datetime"],
            provider_config=cfg,
        )

    assert result == "Es ist Donnerstag."
    assert chunks == ["Es ist ", "Donnerstag."]
    assert len(client.chat.call_args_list) == 2
    for c in client.chat.call_args_list:
        assert c.kwargs.get("stream") is True, (
            "OpenAI-kompatible Engine: Detection UND Follow-up streamen (Live-Takt)"
        )


@pytest.mark.asyncio
async def test_ollama_followup_stays_non_streamed():
    """
    GIVEN the ollama provider (tool-call stream limit)
    WHEN chat_with_tools runs a full tool cycle
    THEN every client.chat call used stream=False.
    """
    def _resp(content="", tool_calls=None):
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = tool_calls or []
        r = MagicMock()
        r.message = msg
        return r

    first = _resp(tool_calls=[MagicMock(function=MagicMock(name="get_datetime", arguments={}))])
    final = _resp(content="Donnerstag.")

    with patch("core.chat.ollama.AsyncClient") as MockClient, patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="Donnerstag")
    ):
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=[first, final])
        MockClient.return_value = client

        result = await chat_with_tools(
            model="qwen3:4b",
            history=[{"role": "user", "content": "Datum?"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["get_datetime"],
        )

    assert result
    for c in client.chat.call_args_list:
        assert c.kwargs.get("stream") is False
