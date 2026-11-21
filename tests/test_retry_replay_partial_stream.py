"""W7-4: the retry-replay contract — a stream that already emitted is never rerun.

The rule is stated as a comment in ``core/chat_stream.py`` ("A retry is taken only
while the stream has emitted nothing"). A comment is not a gate, so this file pins
the rule at the two boundaries where a failing stream could be replayed:

* ``stream_with_retry`` — the provider retry loop (``RETRY_MAX_ATTEMPTS = 3``):
  a transient failure after the first chunk must not open the stream a second time.
* ``send_message_safe`` — the stream-then-non-stream fallback: once a token reached
  ``on_chunk``, the non-streaming answer must not run and re-emit it.

Each test names, in its docstring, the edit that makes it fail — that is what makes
it a gate and not a restatement of the comment.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.chat import send_message_safe
from core.chat_stream import RetryPolicy, stream_with_retry
from core.types import Message

PARTIAL = "here is a partial answer"
FALLBACK_TEXT = "the full answer"
TRANSIENT = ConnectionError("connection reset by peer")


async def _no_sleep(_delay: float) -> None:
    return None


def _emit_then_fail(chunk: str, error: BaseException):
    """An async stream that delivers one chunk, then raises."""

    async def _gen():
        yield {"message": {"content": chunk}}
        raise error

    return _gen()


def _fail_before_emit(error: BaseException):
    """An async stream that raises before delivering any chunk."""

    async def _gen():
        if False:  # pragma: no cover - keeps this an async generator
            yield {}
        raise error

    return _gen()


HISTORY: list[Message] = [Message(role="user", content="hi")]


# Seam 1: the provider retry loop.


async def test_a_partially_emitted_stream_is_never_reopened_by_the_retry_loop():
    """A transient failure with attempts left, but one chunk already out.

    Fails if ``RetryPolicy.may_replay`` drops its ``not emitted`` clause (or the
    loop stops passing ``emitted``): the same transient failure before any chunk
    *is* replayed below, so only the emitted-guard keeps this at one open.
    """
    policy = RetryPolicy(max_attempts=3, base_delay=0.0)
    opens = {"n": 0}
    chunks: list[str] = []

    def open_stream():
        opens["n"] += 1
        return _emit_then_fail(PARTIAL, TRANSIENT)

    with pytest.raises(ConnectionError):
        async for chunk in stream_with_retry(open_stream, policy=policy, sleep=_no_sleep):
            chunks.append(chunk["message"]["content"])

    assert chunks == [PARTIAL]  # the delivered chunk reached the consumer once
    assert opens["n"] == 1  # and the stream was never reopened


async def test_the_retry_loop_still_reopens_a_stream_that_emitted_nothing():
    """Contrast case: the loop must still retry while nothing was emitted.

    Fails if the emitted-guard is made absolute (a "never retry" fix), which would
    throw away the transient-failure recovery this loop exists for.
    """
    policy = RetryPolicy(max_attempts=3, base_delay=0.0)
    opens = {"n": 0}

    def open_stream():
        opens["n"] += 1
        if opens["n"] == 1:
            return _fail_before_emit(TRANSIENT)  # raises before any chunk
        async def _ok():
            yield {"message": {"content": "done"}}
        return _ok()

    chunks = [
        chunk["message"]["content"]
        async for chunk in stream_with_retry(open_stream, policy=policy, sleep=_no_sleep)
    ]
    assert chunks == ["done"]
    assert opens["n"] == 2


# Seam 2: the stream-then-non-stream fallback in send_message_safe.


def _provider_patch(*, stream_emits: str | None, stream_error: BaseException | None):
    """A mocked provider client: the streamed call emits/fails, the later call answers."""

    async def _stream_gen():
        if stream_emits:
            yield {"message": {"content": stream_emits}}
        if stream_error is not None:
            raise stream_error

    async def chat_side_effect(*_args, **kwargs):
        if kwargs.get("stream"):
            return _stream_gen()
        return {"message": {"content": FALLBACK_TEXT}}

    instance = MagicMock()
    instance.chat = AsyncMock(side_effect=chat_side_effect)
    return instance


async def test_send_message_safe_does_not_replay_a_partially_emitted_stream():
    """The streamed answer reached the user, then the stream failed.

    Fails if ``send_message_safe`` falls back on *any* streaming error without
    checking whether a token was already emitted: the non-streaming call would run
    and ``on_chunk`` would receive the answer a second time.
    """
    fallback: list[bool] = []
    chunks: list[str] = []
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        mock_class.return_value = _provider_patch(
            stream_emits=PARTIAL,
            stream_error=RuntimeError("engine stopped mid-answer: partial output dropped"),
        )
        with pytest.raises(RuntimeError):
            await send_message_safe(
                model="llama3.2",
                history=HISTORY,
                on_chunk=chunks.append,
                on_fallback=lambda: fallback.append(True),
            )

    assert chunks, "the streamed token reached the consumer before the failure"
    assert "".join(chunks) in PARTIAL  # the streamed text, delivered once
    assert FALLBACK_TEXT not in "".join(chunks)  # the fallback answer never replayed
    assert fallback == []  # and the fallback never fired


async def test_send_message_safe_still_falls_back_when_nothing_was_emitted():
    """Contrast case: a streaming failure before any chunk keeps the fallback.

    Fails if the emitted-guard is wired to block the fallback unconditionally,
    which would drop the recovery path for a stream that died before saying anything.
    """
    fallback: list[bool] = []
    chunks: list[str] = []
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        mock_class.return_value = _provider_patch(stream_emits=None, stream_error=Exception("nope"))
        result = await send_message_safe(
            model="llama3.2",
            history=HISTORY,
            on_chunk=chunks.append,
            on_fallback=lambda: fallback.append(True),
        )

    assert result == FALLBACK_TEXT
    assert chunks == [FALLBACK_TEXT]
    assert fallback == [True]
