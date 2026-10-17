"""Tool-call detection rounds and the finalized follow-up turns.

Split from core/chat.py (2026-10-11): the non-streaming detection call, the
OpenAI-compatible streaming detection dialect, the retry/finalize helpers and
the parsing of a model response into tool calls.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import uuid
from collections.abc import Callable

from core.chat_context import _budget_exhausted_note, _has_uploaded_images
from core.chat_prompt import TOOL_DETECT_TIMEOUT_SMALL_MODEL, _native_thinking_kwargs
from core.chat_providers import _engine_reachable
from core.chat_stream import (
    EngineNotReachableError,
    OllamaModelBusyError,
    OllamaModelNotFoundError,
    OllamaNotReachableError,
)
from core.model_provider import (
    ProviderChatResponse,
    ProviderFunctionCall,
    ProviderMessage,
    ProviderToolCall,
    _parse_json_arguments,
)


async def _finalize_budget_exhausted(
    *,
    client,
    provider,
    model: str,
    messages: list,
    tools,
    on_chunk,
    on_phase,
    budget_cap: int,
) -> str:
    """R44: cap end with a real close — one tool-less follow-up round
    lets the model summarise the state reached; the
    unfinished note hangs on as a status line. On follow-up failure:
    honestly only the note (no crash, no pseudo-complete)."""
    from core.chat import (
        _tool_detection_timeout,  # patch seam: tests patch this on core.chat
    )
    note = _budget_exhausted_note(budget_cap)
    summary = ""
    streamed = False
    try:
        if getattr(provider, "provider", None) == "openai_compatible":
            resp = await _follow_up_with_retry(
                lambda: _stream_detect_openai(
                    client,
                    model=model,
                    messages=messages,
                    tools=None,
                    on_chunk=on_chunk,
                    on_thinking=None,
                    idle_timeout=_tool_detection_timeout(model),
                ),
                on_phase=on_phase,
            )
            streamed = True
        else:
            resp = await _follow_up_with_retry(
                lambda: client.chat(model=model, messages=messages, stream=False),
                on_phase=on_phase,
            )
        summary = (getattr(getattr(resp, "message", None), "content", "") or "").strip()
        if summary and not streamed and on_chunk is not None:
            on_chunk(summary)
    except Exception:
        summary = ""
    if on_chunk is not None:
        on_chunk(note)
    return f"{summary}\n\n{note}" if summary else note


async def _follow_up_with_retry(call, *, on_phase: "Callable[[str], None] | None" = None, max_retries: int = 2):
    """R37: follow-up call with 2x retry + exponential backoff (0.2s, 0.4s).

    `call` is a no-argument callable that returns an awaitable
    (e.g. the client.chat coroutine). After 1 + max_retries attempts the
    last error is handed on honestly (no pseudo-success).
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            result = call()
            # R44: synchronous clients (stub tests, some sync wrappers) return
            # the value directly — only real awaitables are awaited.
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                if on_phase is not None:
                    on_phase(f"Retrying ({attempt + 1}/{max_retries})…")
                await asyncio.sleep(0.2 * (2 ** attempt))
    raise last_exc if last_exc is not None else RuntimeError("follow-up call failed")


async def _stream_detect_openai(
    client,
    *,
    model: str,
    messages: list,
    tools: list[dict] | None,
    on_chunk: Callable[[str], None],
    on_thinking: Callable[[str], None] | None,
    idle_timeout: float,
) -> ProviderChatResponse:
    """Streaming tool detection for OpenAI-compatible engines (sglang/vLLM).

    Teleprompter parity (leading agent clients): ``reasoning_content`` deltas go
    to ``on_thinking`` live from the FIRST frame on; the Ollama path holds its
    text back and "plays it" word by word once the stream has ended.
    Content deltas stream live to ``on_chunk``; tool-call deltas are
    (arguments arrive fragmented) gathered into one ProviderMessage.

    Ollama stays non-streaming: there tool calls break with stream=True
    (known limit, see test_tool_calling.py).

    idle_timeout applies PER FRAME (never to the whole stream; fix round 10:
    the old total timeout aborted long reasoning → a false
    "model retry" in the middle of thinking). While thinking, frames arrive
    continuously — only a real standstill (no frame for idle_timeout s)
    triggers. After chunks have already been emitted a stall or a dropped
    connection does NOT restart (a retry would duplicate text); the failure
    is named with the partial output it cut. An engine that answers nothing
    (no stream, no frame) returns an empty response, never a crash.
    """
    content_parts: list[str] = []
    # F-AA: everything that arrived as a reasoning delta — answer fallback, in case the
    # provider never sends a single content delta (gemma4 think mode via
    # the Ollama /v1 shim).
    reasoning_parts: list[str] = []
    # index → {"id", "name", "args"} — OpenAI streams arguments in fragments
    tcs: dict[int, dict] = {}
    stream = await client.chat(
        model=model,
        messages=list(messages),
        tools=tools,
        stream=True,
    )
    if stream is None or not hasattr(stream, "__anext__"):
        # The engine accepted the request but handed back nothing iterable —
        # the same "answered nothing" state as an empty stream. An empty
        # response (never a crash) lets the silent-turn path name it.
        return ProviderChatResponse(
            message=ProviderMessage(content="", thinking="", tool_calls=None)
        )
    emitted = False
    while True:
        try:
            frame = await asyncio.wait_for(anext(stream), timeout=idle_timeout)
        except StopAsyncIteration:
            break
        except asyncio.TimeoutError:
            if emitted:
                # Stalled in the middle of the answer → a restart would duplicate text.
                # The budget is printed with %g, not %d: a sub-second budget rendered "0s"
                # and read as if the watchdog had fired instantly.
                raise RuntimeError(
                    f"Engine stream stalled: no frame for {idle_timeout:g}s (partial output already streamed — please send again)"
                )
            raise
        except Exception as exc:
            # The connection dropped inside the stream (reset, protocol error,
            # gateway 5xx mid-answer). Output the user already saw is not thrown
            # away unnamed: stop with what arrived. Before any output the raw
            # error stands, so the caller's probe can classify it.
            if emitted:
                raise RuntimeError(
                    f"Engine stream failed mid-answer ({type(exc).__name__}) "
                    "after partial output was already streamed — please send again"
                ) from exc
            raise
        message = frame.get("message", {}) if isinstance(frame, dict) else {}
        # same dual-field contract as the detection stream (see above)
        reasoning = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or message.get("thinking_content")
            or message.get("thinking")
        )
        if reasoning and on_thinking:
            emitted = True
            reasoning_parts.append(str(reasoning))
            on_thinking(str(reasoning))
        content = message.get("content") or ""
        if content:
            emitted = True
            content_parts.append(content)
            on_chunk(content)
        raw_tool_calls = message.get("tool_calls")
        if raw_tool_calls:
            for tc in raw_tool_calls:
                idx = tc.get("index") or 0
                entry = tcs.setdefault(idx, {"id": "", "name": "", "args": ""})
                if tc.get("id"):
                    entry["id"] = str(tc["id"])
                fn = tc.get("function") or {}
                if fn.get("name"):
                    entry["name"] = str(fn["name"])
                if fn.get("arguments"):
                    entry["args"] += str(fn["arguments"])
    tool_calls = None
    if tcs:
        tool_calls = [
            ProviderToolCall(
                id=tcs[i]["id"],
                function=ProviderFunctionCall(
                    name=tcs[i]["name"],
                    arguments=_parse_json_arguments(tcs[i]["args"]),
                ),
            )
            for i in sorted(tcs)
        ]
    # F-AA: a thinking-only turn (content empty, reasoning present) → the reasoning
    # becomes the answer; the thinking block stays visible on top (honest).
    _reasoning_fallback = "".join(reasoning_parts) if not content_parts else ""
    return ProviderChatResponse(
        message=ProviderMessage(
            # Finding 2026-10-01 (F-AA): Ollama's /v1 shim + gemma4 in think mode
            # deliver the ANSWER as reasoning deltas — content stays empty.
            # A turn with 100% thinking and 0% answer is useless: the content
            # moves here honestly into the answer channel (a duplicate in the
            # thinking block is the smaller damage compared to an empty bubble).
            content="".join(content_parts) or _reasoning_fallback,
            thinking="",
            tool_calls=tool_calls,
        )
    )


async def _detect_tool_calls(
    *,
    client: object,
    provider: object,
    model: str,
    messages: list,
    tools: list,
    on_chunk: Callable[[str], None],
    on_thinking: Callable[[str], None] | None,
    on_phase: Callable[[str], None] | None,
) -> tuple[object, str, bool]:
    """Step 1: non-streaming tool detection with retry + memory fallback.

    Returns ``(response, model, detection_streamed)`` — ``model`` may have been
    swapped against the input by the RAM fallback; ``detection_streamed``
    marks that content/reasoning already arrived live via on_chunk/on_thinking.
    """
    from core.chat import (
        _tool_detection_timeout,  # patch seam: tests patch this on core.chat
    )
    TOOL_DETECT_TIMEOUT = _tool_detection_timeout(model)
    MAX_RETRIES = 0 if TOOL_DETECT_TIMEOUT <= TOOL_DETECT_TIMEOUT_SMALL_MODEL else 1

    if on_phase:
        on_phase("Analyzing request…")

    response = None
    fallback_used = False
    detection_streamed = False
    for attempt in range(MAX_RETRIES + 1):
        try:
            if provider.provider == "openai_compatible":
                # Teleprompter parity: detection streams — reasoning appears
                # immediately. NO total wait_for (would choke long reasoning);
                # instead an idle timeout per frame inside _stream_detect_openai.
                response = await _stream_detect_openai(
                    client,
                    model=model,
                    messages=messages,
                    tools=tools,
                    on_chunk=on_chunk,
                    on_thinking=on_thinking,
                    idle_timeout=TOOL_DETECT_TIMEOUT,
                )
                detection_streamed = True
            else:
                response = await asyncio.wait_for(
                    client.chat(
                        model=model,
                        messages=messages,
                        tools=tools,
                        stream=False,
                        **_native_thinking_kwargs(model),
                    ),
                    timeout=TOOL_DETECT_TIMEOUT,
                )
            break  # success → leave the loop
        except asyncio.TimeoutError as exc:
            if attempt < MAX_RETRIES:
                if on_phase:
                    on_phase("Loading model… (Retry)")
                continue
            # The last attempt also times out -> provider-aware engine probe:
            # "unreachable" (engine down) | otherwise busy (model loading/GPU occupied).
            probe_state = await _engine_reachable(provider)
            if probe_state == "unreachable":
                if provider.provider == "openai_compatible":
                    raise EngineNotReachableError(provider.base_url) from exc
                raise OllamaNotReachableError() from exc
            raise OllamaModelBusyError(model, TOOL_DETECT_TIMEOUT)
        except Exception as exc:
            exc_str = str(exc).lower()
            fallback_model = (os.environ.get("EPHE_FALLBACK_MODEL") or "").strip()
            if (
                not fallback_used
                and fallback_model
                and fallback_model != model
                and not _has_uploaded_images(messages)
                and "requires more system memory" in exc_str
            ):
                fallback_used = True
                model = fallback_model
                if on_phase:
                    on_phase(f"Primary model needs more memory; retrying with {fallback_model}…")
                continue
            if any(kw in exc_str for kw in ("refused", "socket")):
                raise OllamaNotReachableError() from exc
            if "not found" in exc_str or "does not exist" in exc_str:
                raise OllamaModelNotFoundError(model) from exc
            raise
    return response, model, detection_streamed


def _call_id(turn_id: str, idx: int) -> str:
    """Ephe's own identifier for a tool call.

    The plain loop index ("0") was no identifier: twenty turns have a
    call number zero, and a workbench card pointing at "0" says nothing
    about who gave birth to the file. With a turn prefix it is unique and
    can be read in a screenshot.
    """
    if turn_id:
        return f"{turn_id[:8]}-{idx}"
    return f"c{idx}-{uuid.uuid4().hex[:6]}"


def _parse_tool_calls(
    response: object,
    turn_id: str,
    on_tool_start: Callable | None,
) -> tuple[list[tuple[int, str, dict]], dict[int, str]]:
    """Parse ``response.message.tool_calls`` index-stable into (idx, name, args).

    The identifier is created once per call: with a random fallback when
    ``turn_id`` is empty, so start and done stamps for the same call always
    carry the same id (W15-P3 spans).
    """
    parsed: list[tuple[int, str, dict]] = []
    call_ids: dict[int, str] = {}
    for idx, tool_call in enumerate(response.message.tool_calls):
        if isinstance(tool_call, dict):
            function = tool_call.get("function") or tool_call
            name = str(function.get("name", ""))
            args = function.get("arguments") or {}
        else:
            function = tool_call.function
            name = str(tool_call.function.name)
            args = tool_call.function.arguments or {}
        parsed.append((idx, name, args))
        call_ids[idx] = _call_id(turn_id, idx)
        if on_tool_start is not None:
            on_tool_start(name, args, call_ids[idx])
    return parsed, call_ids


def engine_tool_call_ids(response: object) -> dict[int, str]:
    """The ids the engine assigned, by call index, for the tool messages that answer them.

    The loop's own ids are audit stamps. The engine's ids are what a `role: "tool"`
    message has to answer, and relying on positional correlation alone is what let a
    result reach an engine without its block (measured 2026-10-17).
    """
    out: dict[int, str] = {}
    calls = getattr(getattr(response, "message", None), "tool_calls", None) or []
    for idx, call in enumerate(calls):
        call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
        if call_id:
            out[idx] = str(call_id)
    return out
