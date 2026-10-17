"""
Ephe — R36 DD-26: the thinking delta under the field name `reasoning`.

Live probe against the DGX-vLLM (2026-09-07): the real SSE frames send the
thinking token under delta.reasoning — NOT under delta.reasoning_content. The
parser only read reasoning_content → the PWA's chain-of-thought block stayed
empty for the entire run (audit 02-01).

Given a vLLM stream that carries thinking under `reasoning`
When the OpenAI stream parser consumes it
Then on_thinking receives every thinking fragment (and content stays clean).
"""
from __future__ import annotations

import asyncio

import pytest

from core.chat import _stream_detect_openai


def _frame(reasoning: str | None = None, content: str | None = None) -> dict:
    msg: dict = {}
    if reasoning is not None:
        # exactly the field the real vLLM sends, per the live probe
        msg["reasoning"] = reasoning
    if content is not None:
        msg["content"] = content
    return {"message": msg}


class FakeStream:
    def __init__(self, frames: list[dict]):
        self._frames = list(frames)
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._i >= len(self._frames):
            raise StopAsyncIteration
        frame = self._frames[self._i]
        self._i += 1
        return frame


class FakeClient:
    def __init__(self, stream: FakeStream):
        self._stream = stream

    async def chat(self, **kwargs):
        return self._stream


class TestReasoningFieldAlias:

    @pytest.mark.asyncio
    async def test_given_reasoning_field_when_streaming_then_on_thinking_sees_every_fragment(self):
        """Given: vLLM sends delta.reasoning as two fragments, content as its own frame
        When: the parser runs Then: both fragments land on on_thinking, content stays unchanged"""
        frames = [_frame(reasoning="Wir"), _frame(reasoning=" müssen"), _frame(content="1161")]
        thinking: list[str] = []
        chunks: list[str] = []
        resp = await _stream_detect_openai(
            FakeClient(FakeStream(frames)),
            model="qwen3.8-flash-next",
            messages=[{"role": "user", "content": "test"}],
            tools=None,
            on_chunk=chunks.append,
            on_thinking=thinking.append,
            idle_timeout=5.0,
        )
        assert thinking == ["Wir", " müssen"]
        assert chunks == ["1161"]
        assert resp.message.content == "1161"

    @pytest.mark.asyncio
    async def test_given_both_field_names_when_streaming_then_both_reach_thinking_without_dupes(self):
        """Given: reasoning_content and reasoning mixed inside one stream
        Then: every fragment exactly once — no duplication"""
        frames = [
            {"message": {"reasoning_content": "alt "}},
            {"message": {"reasoning": "neu "}},
            {"message": {"content": "ok"}},
        ]
        thinking: list[str] = []
        await _stream_detect_openai(
            FakeClient(FakeStream(frames)),
            model="m",
            messages=[{"role": "user", "content": "test"}],
            tools=None,
            on_chunk=lambda c: None,
            on_thinking=thinking.append,
            idle_timeout=5.0,
        )
        assert thinking == ["alt ", "neu "]
