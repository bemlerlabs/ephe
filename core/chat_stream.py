"""Streaming chat path: Ollama streaming, thinking-tag parser, error types.

Split from core/chat.py in the 2026-10-11 module split. stream_response and
send_message_safe live here, plus the ThinkingStreamParser and the engine
exception types; core/chat.py re-exports everything.
"""

from __future__ import annotations

import asyncio
import inspect
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from core import provider_errors
from core.chat_prompt import THINK_CLOSE, THINK_OPEN
from core.chat_providers import _resolve_provider
from core.model_provider import ModelProviderConfig
from core.tools.session_ctx import record_measured_usage
from core.types import Message

# How long to wait for the FIRST token before showing a "still loading" hint
FIRST_CHUNK_TIMEOUT: float = 15.0

# Remote retry policy.
# A serve request reaches a local Ollama or a remote engine (DGX/ds4 vLLM). A
# dropped connection there is transient, so the call is retried with exponential
# backoff. A retry is taken only while the stream has emitted nothing: re-running
# a call that already delivered a chunk would send that chunk twice, so that
# failure propagates instead.
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.25
RETRY_MAX_DELAY = 2.0

# A server's Retry-After can exceed the policy's own backoff, so it is honored up to
# this ceiling: a broken or hostile header must not park the loop for minutes. The
# taxonomy in core/provider_errors.py reads the header; nothing here guesses at it.
RETRY_AFTER_CAP = 30.0


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff for one remote engine call.

    The backoff only shapes how long to wait; ``may_replay`` decides whether a
    wait is safe at all.
    """

    max_attempts: int = RETRY_MAX_ATTEMPTS
    base_delay: float = RETRY_BASE_DELAY
    max_delay: float = RETRY_MAX_DELAY
    jitter: float = 0.0

    def delay_for(self, attempt: int) -> float:
        """Seconds before retry `attempt` (1-based): the delay doubles, capped at
        max_delay, plus an optional jitter fraction."""
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        if self.jitter and delay > 0:
            delay += random.uniform(0.0, delay * self.jitter)
        return delay

    def may_replay(self, error: BaseException, *, attempt: int, emitted: bool) -> bool:
        """Whether the call that raised `error` can be run again.

        Replay is safe only while nothing reached the consumer (`emitted` is
        False), an attempt is left, and the failure is transient. A chunk already
        delivered would arrive twice on a replay, and a caller error answers the
        same on every attempt. A model call carries no external side effect, so a
        replayed call repeats only its compute.
        """
        return (
            not emitted
            and attempt < self.max_attempts
            and is_transient_error(error)
        )


DEFAULT_RETRY_POLICY = RetryPolicy(jitter=0.1)


def is_transient_error(exc: BaseException) -> bool:
    """True when `exc` is a failure worth another attempt.

    The decision lives in ``core/provider_errors`` so the retry loop and the error
    frame share one table; this stays as the name core/chat.py already re-exports.
    """
    return provider_errors.is_retryable(exc)


async def stream_with_retry(
    open_stream: Callable[[], Any],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[dict]:
    """Yield chunks from `open_stream()`, retrying while nothing was emitted yet.

    `open_stream` returns an async iterator or an awaitable of one, since the
    provider clients differ on that point. `sleep` is injectable so tests run the
    backoff without waiting.
    """
    policy = policy or DEFAULT_RETRY_POLICY
    attempt = 0
    while True:
        attempt += 1
        emitted = False
        try:
            stream = open_stream()
            if inspect.isawaitable(stream):
                stream = await stream
            async for chunk in stream:
                emitted = True
                yield chunk
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # A caller error or a failure after the first chunk re-raises as-is;
            # the boundary lives on the policy so there is one place to change.
            if not policy.may_replay(exc, attempt=attempt, emitted=emitted):
                raise
            delay = policy.delay_for(attempt)
            retry_after = provider_errors.classify(exc).retry_after
            if retry_after is not None:
                # A 429 tells us how long to wait; take the larger of that and our
                # own backoff, capped so a bad header cannot stall the turn.
                delay = max(delay, min(retry_after, RETRY_AFTER_CAP))
            await sleep(delay)


def _stream_delay_seconds(word_count: int) -> float:
    _ = word_count
    return 0.0


class ThinkingStreamParser:
    """
    State machine that parses Gemma4 thinking tags in the stream.

    States:
      - NORMAL:    tokens go to on_chunk (answer)
      - THINKING:  tokens go to on_thinking (internal thinking)
      - BUFFERING: tag detection is running, characters are buffered
    """

    def __init__(
        self,
        on_chunk: Callable[[str], None],
        on_thinking: Callable[[str], None] | None = None,
    ):
        self._on_chunk = on_chunk
        self._on_thinking = on_thinking
        self._in_thinking = False
        self._buffer = ""
        self._full_answer = ""
        self._full_thinking = ""

    def feed(self, token: str) -> None:
        """Processes one incoming token."""
        self._buffer += token

        while self._buffer:
            if not self._in_thinking:
                # Look for <|think|>
                idx = self._buffer.find(THINK_OPEN)
                if idx == -1:
                    # No tag start — check whether the buffer still contains a beginning
                    safe = len(self._buffer) - len(THINK_OPEN) + 1
                    if safe > 0:
                        emit = self._buffer[:safe]
                        self._buffer = self._buffer[safe:]
                        self._full_answer += emit
                        self._on_chunk(emit)
                    else:
                        break  # wait for more data
                else:
                    # Emit the text before the tag
                    if idx > 0:
                        pre = self._buffer[:idx]
                        self._full_answer += pre
                        self._on_chunk(pre)
                    self._buffer = self._buffer[idx + len(THINK_OPEN):]
                    self._in_thinking = True
            else:
                # Look for <|/think|>
                idx = self._buffer.find(THINK_CLOSE)
                if idx == -1:
                    safe = len(self._buffer) - len(THINK_CLOSE) + 1
                    if safe > 0:
                        emit = self._buffer[:safe]
                        self._buffer = self._buffer[safe:]
                        self._full_thinking += emit
                        if self._on_thinking:
                            self._on_thinking(emit)
                    else:
                        break
                else:
                    # the thinking text before the close tag
                    if idx > 0:
                        pre = self._buffer[:idx]
                        self._full_thinking += pre
                        if self._on_thinking:
                            self._on_thinking(pre)
                    self._buffer = self._buffer[idx + len(THINK_CLOSE):]
                    self._in_thinking = False

    def flush(self) -> None:
        """Emit the remaining buffer at the end of the stream."""
        if self._buffer:
            if self._in_thinking:
                self._full_thinking += self._buffer
                if self._on_thinking:
                    self._on_thinking(self._buffer)
            else:
                self._full_answer += self._buffer
                self._on_chunk(self._buffer)
            self._buffer = ""

    @property
    def answer(self) -> str:
        return self._full_answer

    @property
    def thinking(self) -> str:
        return self._full_thinking


class OllamaNotReachableError(Exception):
    """Raised when Ollama is not running or not reachable."""

    def __init__(self) -> None:
        super().__init__(
            "Ollama is not reachable. Start it with: ollama serve"
        )


class EngineNotReachableError(Exception):
    """Raised when an OpenAI-compatible engine (e.g. DGX-Spark) is unreachable."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        super().__init__(
            f"Engine not reachable: {base_url}. "
            "Check the vLLM service on the DGX and the URL."
        )


class OllamaModelBusyError(Exception):
    """Raised when Ollama is reachable but the model is busy (timeout)."""

    def __init__(self, model: str, timeout: float) -> None:
        self.model = model
        self.timeout = timeout
        super().__init__(
            f"Model '{model}' is busy or loading (timeout after {timeout}s). Try again."
        )


class OllamaModelNotFoundError(Exception):
    """Raised when the requested model is not available locally."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(
            f"Model '{model}' not found locally. Pull it with: ollama pull {model}"
        )


async def stream_response(
    *,
    model: str,
    history: list[Message],
    on_chunk: Callable[[str], None],
    on_thinking: Callable[[str], None] | None = None,
    on_loading_hint: Callable[[], None] | None = None,
    provider_config: ModelProviderConfig | None = None,
    api_url: str | None = None,
) -> str:
    """
    Stream a response from Ollama token by token.

    Calls on_chunk(token_str) for each received token.
    If FIRST_CHUNK_TIMEOUT seconds pass before the first token arrives
    (= model is loading from disk), calls on_loading_hint() once.
    Returns the full accumulated response text when done.

    Raises:
        OllamaNotReachableError: if Ollama is not running.
        OllamaModelNotFoundError: if the model is not pulled.
        asyncio.CancelledError: propagates cleanly for Textual worker shutdown.
    """
    provider = _resolve_provider(model, provider_config, api_url)
    from core.chat import (
        build_provider_client,  # patch seam: tests patch this on core.chat
    )
    client = build_provider_client(provider)
    full_response = ""
    hint_sent = False

    try:
        stream = await client.chat(
            model=model,
            messages=list(history),  # type: ignore[arg-type]
            stream=True,
        )

        parser = ThinkingStreamParser(on_chunk=on_chunk, on_thinking=on_thinking)
        # F-AA: collect reasoning — if the stream NEVER sends a content-delta
        # (gemma4 think mode via the Ollama /v1 shim), the thinking
        # becomes the answer (otherwise: an empty bubble).
        reasoning_text = ""

        async for chunk in stream:
            message = chunk["message"]
            # N8a: Ollama delivers prompt_eval_count/eval_count in the final chunk —
            # a measured count beats the calibrated estimate.
            record_measured_usage(chunk)
            # vLLM variants ship the thinking delta under `reasoning_content`
            # (older builds) or `reasoning` (current /v1/models contract) — the
            # live DGX probe 2026-09-07 proved `reasoning` is what actually
            # arrives, so accepting only the first left the UI thinking block empty.
            reasoning = (
                message.get("reasoning_content")
                or message.get("reasoning")
                or message.get("thinking_content")
                or message.get("thinking")
            )
            if reasoning and on_thinking:
                # OpenAI-compatible engines deliver reasoning as a separate
                # field — straight to on_thinking, no parser involved.
                reasoning_text += str(reasoning)
                on_thinking(str(reasoning))
            content: str = message.get("content", "")
            if content:
                if not hint_sent and full_response == "":
                    hint_sent = True
                full_response += content
                parser.feed(content)

        parser.flush()
        answer = parser.answer or full_response
        if not answer and reasoning_text:
            # Finding 2026-10-01 (F-AA): a thinking-only turn → the thinking IS the
            # answer (a duplicate in the thinking block < an empty bubble).
            on_chunk(reasoning_text)
            return reasoning_text
        return answer

    except asyncio.CancelledError:
        # Let the worker's cancellation propagate cleanly
        raise

    except Exception as exc:
        # The failure shape comes from the one classifier (core/provider_errors), so a
        # transport drop reads the same in the chat loop, the served stream and the CLI.
        if provider_errors.classify(exc).kind is provider_errors.ProviderFailureKind.TRANSPORT:
            raise OllamaNotReachableError() from exc

        if provider_errors.is_model_missing(exc):
            raise OllamaModelNotFoundError(model) from exc

        # Unknown error – re-raise for the worker to handle
        raise


async def send_message_safe(
    *,
    model: str,
    history: list[Message],
    on_chunk: Callable[[str], None],
    on_fallback: Callable[[], None] | None = None,
    on_loading_hint: Callable[[], None] | None = None,
    provider_config: ModelProviderConfig | None = None,
    api_url: str | None = None,
) -> str:
    """
    Safe wrapper: tries streaming first, falls back to non-streaming on failure.

    on_loading_hint() is called if the model takes > FIRST_CHUNK_TIMEOUT seconds.
    on_fallback() is called when falling back to non-streaming mode.

    Raises OllamaNotReachableError and OllamaModelNotFoundError directly
    (these are not recoverable via fallback).

    The fallback is itself a replay of the call, so it obeys the retry-replay rule:
    once a token reached ``on_chunk``, a non-streaming retry would deliver the answer
    a second time, and the failure propagates instead.
    """
    emitted = False

    def _on_chunk(text: str) -> None:
        nonlocal emitted
        if text:
            emitted = True
        on_chunk(text)

    try:
        return await stream_response(
            model=model,
            history=history,
            on_chunk=_on_chunk,
            on_loading_hint=on_loading_hint,
            provider_config=provider_config,
        )
    except (OllamaNotReachableError, OllamaModelNotFoundError, asyncio.CancelledError):
        raise

    except Exception:
        # A chunk already reached the consumer: the fallback would send it twice,
        # so the failure propagates rather than replaying a partial stream.
        if emitted:
            raise
        # Streaming failed for another reason – try non-streaming fallback
        if on_fallback is not None:
            on_fallback()

        provider = _resolve_provider(model, provider_config, api_url)
        from core.chat import (
            build_provider_client,  # patch seam: tests patch this on core.chat
        )
        client = build_provider_client(provider)
        try:
            response = await client.chat(
                model=model,
                messages=list(history),  # type: ignore[arg-type]
                stream=False,
            )
            content: str = response["message"]["content"]
            on_chunk(content)
            return content

        except Exception as exc:
            if provider_errors.classify(exc).kind is provider_errors.ProviderFailureKind.TRANSPORT:
                raise OllamaNotReachableError() from exc
            raise


async def _emit_final_answer(
    *,
    response: object,
    detection_streamed: bool,
    on_chunk: Callable[[str], None],
    on_thinking: Callable[[str], None] | None,
    on_phase: Callable[[str], None] | None,
) -> str:
    """Step 3: emit the final answer (parse thinking tags, word cadence).

    With a streamed engine answer (``detection_streamed``) content +
    reasoning already arrived live → only return the value, do NOT emit
    again (otherwise a double output)."""
    final_content: str = ""
    if hasattr(response, "message"):
        msg = response.message
        if detection_streamed:
            return str(msg.content or "")
        if on_phase:
            on_phase("Generating response…")
        # Only models with native Ollama thinking enabled populate msg.thinking.
        if on_thinking and hasattr(msg, "thinking") and msg.thinking:
            thinking_text = str(msg.thinking)
            words = thinking_text.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                on_thinking(chunk)
                await asyncio.sleep(0.005)
        if msg.content:
            raw_content = str(msg.content)
            parser = ThinkingStreamParser(on_chunk=on_chunk, on_thinking=on_thinking)
            words = raw_content.split(" ")
            delay = _stream_delay_seconds(len(words))
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                parser.feed(chunk)
                if delay > 0:
                    await asyncio.sleep(delay)
            parser.flush()
            final_content = parser.answer
    return final_content
