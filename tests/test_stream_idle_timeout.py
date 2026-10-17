"""
◑ Ephe – TDD: streaming idle timeout (round 10 fix)

Given / When / Then – strictly.

Bug: the total timeout around _stream_detect_openai aborted long reasoning
→ the UI showed "Loading model… (Retry)" (`chat.phaseLoadingModel`) mid-thinking.
Fix: the idle timeout applies PER FRAME; once chunks were emitted there is no retry
(duplicate risk), the error is passed through instead.
"""
from __future__ import annotations

import asyncio

import pytest

from core.chat import _stream_detect_openai


def _frame(reasoning: str | None = None, content: str | None = None) -> dict:
    msg: dict = {}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    if content is not None:
        msg["content"] = content
    return {"message": msg}


class FakeStream:
    def __init__(self, frames: list[dict], delay: float = 0.0, stall_after: int | None = None):
        self._frames = list(frames)
        self._delay = delay
        self._stall_after = stall_after
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._stall_after is not None and self._i == self._stall_after:
            await asyncio.sleep(999)  # a genuine stall
        if self._i >= len(self._frames):
            raise StopAsyncIteration
        if self._delay:
            await asyncio.sleep(self._delay)
        frame = self._frames[self._i]
        self._i += 1
        return frame


class FakeClient:
    def __init__(self, stream: FakeStream):
        self._stream = stream

    async def chat(self, **kwargs):
        return self._stream


class TestIdleTimeoutProFrame:

    @pytest.mark.asyncio
    async def test_given_slow_but_steady_thinking_when_streaming_then_no_timeout_and_full_content(self):
        """G: reasoning frames arrive sluggish but continuously (total time
        > idle budget) W: detection T: no timeout, everything arrived"""
        frames = [_frame(reasoning=f"denke {i}") for i in range(6)]
        frames.append(_frame(content="Antwort"))
        thinking: list[str] = []
        chunks: list[str] = []
        resp = await _stream_detect_openai(
            FakeClient(FakeStream(frames, delay=0.04)),
            model="qwen3.8-flash-next",
            messages=[{"role": "user", "content": "test"}],
            tools=None,
            on_chunk=chunks.append,
            on_thinking=thinking.append,
            # Total 7 x 0.04 = 0.28 s > 0.2, so the idle timer is the only one that could
            # fire. Each gap is a fifth of the budget, which is the margin this needs on a
            # loaded runner: the previous 60 ms against 100 ms tripped when the scheduler
            # overshot one sleep, and the watchdog was right to fire.
            idle_timeout=0.2,
        )
        assert len(thinking) == 6
        assert chunks == ["Antwort"]
        assert resp.message.content == "Antwort"

    @pytest.mark.asyncio
    async def test_given_stall_before_any_output_when_streaming_then_timeout_error(self):
        """G: the engine stalls BEFORE the first output W: detection T: asyncio.TimeoutError (the retry loop may fire)"""
        with pytest.raises(asyncio.TimeoutError):
            await _stream_detect_openai(
                FakeClient(FakeStream([_frame(content="spät")], stall_after=0)),
                model="m",
                messages=[{"role": "user", "content": "test"}],
                tools=None,
                on_chunk=lambda c: None,
                on_thinking=None,
                idle_timeout=0.1,
            )

    @pytest.mark.asyncio
    async def test_given_stall_after_partial_content_when_streaming_then_runtime_error_no_duplicate(self):
        """G: the engine stalls AFTER a partial output W: detection T: RuntimeError
        (no silent restart — that would duplicate the text)"""
        chunks: list[str] = []
        with pytest.raises(RuntimeError):
            await _stream_detect_openai(
                FakeClient(FakeStream(
                    [_frame(content="hallo "), _frame(content="welt")],
                    stall_after=1,
                )),
                model="m",
                messages=[{"role": "user", "content": "test"}],
                tools=None,
                on_chunk=chunks.append,
                on_thinking=None,
                idle_timeout=0.1,
            )
        # emitted exactly once, no duplicate through a retry
        assert chunks == ["hallo "]

    @pytest.mark.asyncio
    async def test_given_tool_call_fragments_when_streaming_then_aggregated(self):
        """G: tool-call arguments arrive in fragments W: detection T: merged ProviderToolCall"""
        frag1 = '{"tit'
        frag2 = 'le": "x"}'
        frames = [
            _frame(reasoning="nutze tool"),
            {"message": {"tool_calls": [{"index": 0, "id": "t1",
              "function": {"name": "create_pdf", "arguments": frag1}}]}},
            {"message": {"tool_calls": [{"index": 0,
              "function": {"arguments": frag2}}]}},
        ]
        resp = await _stream_detect_openai(
            FakeClient(FakeStream(frames)),
            model="m",
            messages=[{"role": "user", "content": "test"}],
            tools=[{}],
            on_chunk=lambda c: None,
            on_thinking=None,
            idle_timeout=1.0,
        )
        tc = resp.message.tool_calls[0]
        assert tc.function.name == "create_pdf"
        assert tc.function.arguments == {"title": "x"}
