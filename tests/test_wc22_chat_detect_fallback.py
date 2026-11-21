"""WC-22 — the detection stream when the engine answers nothing or drops.

Two failure shapes around ``_stream_detect_openai`` (the OpenAI-compatible
detection dialect), measured against the current code:

- the engine answers nothing: a stream with no frames, or no stream at all;
- the engine errors mid-stream: the connection resets after partial output.

Given / When / Then, strictly.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.chat import _detect_tool_calls, _stream_detect_openai
from core.chat_stream import OllamaNotReachableError


class EngineDrop(Exception):
    """A stand-in for a transport error raised from inside the stream."""


class FakeStream:
    def __init__(self, frames=None, exc_at=None, exc=None):
        self._frames = list(frames or [])
        self._exc_at = exc_at
        self._exc = exc
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._exc_at is not None and self._i == self._exc_at:
            raise self._exc
        if self._i >= len(self._frames):
            raise StopAsyncIteration
        frame = self._frames[self._i]
        self._i += 1
        return frame


class FakeClient:
    def __init__(self, stream):
        self._stream = stream

    async def chat(self, **kwargs):
        return self._stream


def frame(content: str | None = None, reasoning: str | None = None) -> dict:
    msg: dict = {}
    if content is not None:
        msg["content"] = content
    if reasoning is not None:
        msg["reasoning"] = reasoning
    return {"message": msg}


def _provider() -> SimpleNamespace:
    return SimpleNamespace(provider="openai_compatible", base_url="http://engine.test/v1")


async def _detect(client, provider=None):
    return await _detect_tool_calls(
        client=client,
        provider=provider or _provider(),
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        on_chunk=lambda c: None,
        on_thinking=None,
        on_phase=None,
    )


class TestEngineAnswersNothing:

    @pytest.mark.asyncio
    async def test_given_stream_with_no_frames_when_detecting_then_empty_response_not_crash(self):
        """G: the engine opens a stream and sends zero frames
        W: the detection stream W: an empty response, no crash"""
        resp = await _stream_detect_openai(
            FakeClient(FakeStream([])),
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            on_chunk=lambda c: None,
            on_thinking=None,
            idle_timeout=1.0,
        )
        assert resp.message.content == ""
        assert resp.message.tool_calls is None

    @pytest.mark.asyncio
    async def test_given_engine_returns_no_stream_when_detecting_then_empty_response_not_crash(self):
        """G: client.chat hands back no iterable at all (None) instead of a stream
        W: the detection stream W: an empty response, never a TypeError"""
        resp = await _stream_detect_openai(
            FakeClient(None),
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            on_chunk=lambda c: None,
            on_thinking=None,
            idle_timeout=1.0,
        )
        assert resp.message.content == ""
        assert resp.message.tool_calls is None

    @pytest.mark.asyncio
    async def test_given_engine_answers_nothing_when_detecting_tool_calls_then_silent_contract_holds(self):
        """G: the engine answers nothing on the detection round
        W: _detect_tool_calls T: an empty response with detection_streamed set —
        it is returned (the silent-turn path names it), never raised"""
        resp, model, streamed = await _detect(FakeClient(FakeStream([])))
        assert resp is not None
        assert resp.message.content == ""
        assert model == "m"
        assert streamed is True


class TestMidStreamDrop:

    @pytest.mark.asyncio
    async def test_given_connection_drops_after_partial_answer_when_streaming_then_named_runtime_error(self):
        """G: one content frame, then the transport raises
        W: the detection stream T: RuntimeError naming the drop and the partial output;
        the already-streamed text reaches on_chunk exactly once"""
        chunks: list[str] = []
        drop = EngineDrop("connection reset by peer")
        with pytest.raises(RuntimeError) as ei:
            await _stream_detect_openai(
                FakeClient(FakeStream([frame(content="hallo ")], exc_at=1, exc=drop)),
                model="m",
                messages=[],
                tools=None,
                on_chunk=chunks.append,
                on_thinking=None,
                idle_timeout=1.0,
            )
        assert "partial output" in str(ei.value)
        assert ei.value.__cause__ is drop
        assert chunks == ["hallo "]

    @pytest.mark.asyncio
    async def test_given_connection_drops_after_partial_thinking_when_streaming_then_named_runtime_error(self):
        """G: only reasoning fragments arrived, then the transport raises
        W: the detection stream T: RuntimeError (thinking reached the user too)"""
        thinking: list[str] = []
        with pytest.raises(RuntimeError) as ei:
            await _stream_detect_openai(
                FakeClient(FakeStream([frame(reasoning="denke ")], exc_at=1, exc=EngineDrop("gone"))),
                model="m",
                messages=[],
                tools=None,
                on_chunk=lambda c: None,
                on_thinking=thinking.append,
                idle_timeout=1.0,
            )
        assert "partial output" in str(ei.value)
        assert thinking == ["denke "]

    @pytest.mark.asyncio
    async def test_given_connection_drops_before_any_output_when_streaming_then_original_error_passes_through(self):
        """G: the transport raises before the first frame
        W: the detection stream T: the original error type stands, so a caller
        can classify it (nothing was streamed — no partial-output wording)"""
        with pytest.raises(EngineDrop):
            await _stream_detect_openai(
                FakeClient(FakeStream([frame(content="late")], exc_at=0, exc=EngineDrop("dial tcp: refused"))),
                model="m",
                messages=[],
                tools=None,
                on_chunk=lambda c: None,
                on_thinking=None,
                idle_timeout=1.0,
            )

    @pytest.mark.asyncio
    async def test_given_drop_before_output_when_detect_tool_calls_then_classified_as_unreachable(self):
        """G: the transport refuses before any frame
        W: _detect_tool_calls T: OllamaNotReachableError — a keyword error is
        classified, not leaked raw"""
        client = FakeClient(FakeStream([frame(content="late")], exc_at=0, exc=EngineDrop("dial tcp: refused")))
        with pytest.raises(OllamaNotReachableError):
            await _detect(client)

    @pytest.mark.asyncio
    async def test_given_drop_after_output_when_detect_tool_calls_then_named_error_not_reclassified(self):
        """G: the drop lands after partial output (a mid-answer RuntimeError)
        W: _detect_tool_calls T: the named RuntimeError propagates — it is not
        mistaken for an unreachable engine or a missing model"""
        client = FakeClient(FakeStream([frame(content="hallo ")], exc_at=1, exc=EngineDrop("reset")))
        with pytest.raises(RuntimeError) as ei:
            await _detect(client)
        assert not isinstance(ei.value, OllamaNotReachableError)
        assert "mid-answer" in str(ei.value)
