"""
◑ Ephe – OpenAI-compatible engine (phase 3)
server/openai.py

Serves the local engine as an OpenAI-compatible API so that other
external agent CLIs can attach as consumers.

Endpoints:
  GET  /v1/models            → model list (from the active provider)
  POST /v1/chat/completions  → chat completion, non-stream + stream (SSE)

Auth model:
  - api_token set   → every request needs the header ``X-Auth-Token`` (else 401)
  - api_token None  → no token needed (only meant for a localhost bind)

Backend: build_provider_client() (offline-first: local Ollama default).

Ephe – Bad Liebenzell, Black Forest
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from core import provider_errors
from core.chat_context import _active_context_window, _fit_messages_to_window
from core.chat_stream import (
    DEFAULT_RETRY_POLICY,
    RetryPolicy,
    stream_with_retry,
)
from core.loop_observability import LoopObserver, bind_observer, reset_observer
from core.model_config import TIER_MAP, ModelConfig, ModelTier
from core.model_provider import (
    ModelProviderConfig,
    build_provider_client,
    get_active_provider,
)
from core.model_router import get_router
from core.observability import (
    REQUEST_ID_HEADER,
    ErrorCode,
    error_payload,
    make_observability_middleware,
    structured_log,
)
from core.usage import build_usage, extract_measured_counts, serialize_prompt

STREAM_MARKER = "[DONE]"
OWNED_BY = "ephe"

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_REPLAY_HEADER = "Idempotency-Replayed"
IDEMPOTENCY_MAX_ENTRIES = 256
IDEMPOTENCY_TTL_SECONDS = 600.0

# WC-19: a served turn reports its compaction counters the way the chat loop
# does, so an operator watching `ephe.loop` and an HTTP consumer see one shape.
COMPACTION_EVENTS_HEADER = "X-Ephe-Compaction-Events"
MESSAGES_DROPPED_HEADER = "X-Ephe-Messages-Dropped"


class IdempotencyConflict(Exception):
    """A spent Idempotency-Key arrived again with a different request body."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Idempotency-Key '{key}' was already used for a different request")


@dataclass
class _IdempotencyEntry:
    fingerprint: str
    status_code: int
    payload: dict
    headers: dict
    stored_at: float


class IdempotencyStore:
    """Bounded, TTL-bounded replay cache keyed by the client's Idempotency-Key.

    A repeat with the same key and the same request body returns the stored
    non-stream completion; the same key with a different body raises
    IdempotencyConflict, because the key was already spent on another request.
    Entries expire after ttl_seconds, and the least-recently-used entry is dropped
    once max_entries is exceeded. Auth, 4xx and streamed requests are not held.
    """

    def __init__(
        self,
        *,
        max_entries: int = IDEMPOTENCY_MAX_ENTRIES,
        ttl_seconds: float = IDEMPOTENCY_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[str, _IdempotencyEntry] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def fingerprint(body: dict) -> str:
        """Stable digest of the request body, so a key reuse is compared by content."""
        blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str, fingerprint: str) -> _IdempotencyEntry | None:
        """The stored entry for `key`, or None on a miss or an expired entry.

        Raises IdempotencyConflict when the key is present under another body.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._clock() - entry.stored_at > self._ttl:
                del self._entries[key]
                return None
            if entry.fingerprint != fingerprint:
                raise IdempotencyConflict(key)
            self._entries.move_to_end(key)
            return entry

    def put(
        self,
        key: str,
        fingerprint: str,
        *,
        status_code: int,
        payload: dict,
        headers: dict,
    ) -> None:
        """Record the completion for `key`, evicting the oldest entry when full."""
        entry = _IdempotencyEntry(
            fingerprint, status_code, payload, headers, self._clock()
        )
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


def _provider_config_for(cfg: ModelConfig) -> ModelProviderConfig:
    """Converts a router ModelConfig into a provider config (offline-first)."""
    return ModelProviderConfig(
        provider="local_ollama",
        model=cfg.name,
        base_url=cfg.base_url,  # http://<host> — local or DGX/ds4
        label=cfg.tier.value,
        offline_capable=True,
        requires_internet=False,
    )


def _request_id() -> str:
    return ""  # deprecated: the request id comes from the observability middleware


def _now() -> int:
    return int(time.time())


def _chat_stream(client: Any, model: str, messages: list[dict]) -> Any:
    """AsyncIterator from the backend (dicts with ``message.content``).

    ``chat(..., stream=True)`` already returns an AsyncIterator (not a
    coroutine) — it is consumed via ``async for``.
    """
    return client.chat(model=model, messages=messages, stream=True)


def _fit_served_prompt(messages: list[dict], model: str) -> tuple[list[dict], int]:
    """Trim the served prompt to the active context window.

    The same hard ceiling the chat loop applies before its compressor: keep the
    first message and the most recent ones, cut the front of the middle. Returns
    ``(fitted, dropped)``. The request body is left untouched — its idempotency
    fingerprint was taken from it already, and only the fitted list reaches the
    provider. A window probe that raises is not worth failing a turn over, so it
    degrades to no trim.
    """
    fitted = list(messages)
    try:
        window = _active_context_window(model)
    except Exception:  # noqa: BLE001 — a trim is best effort, serving is not
        return fitted, 0
    return fitted, _fit_messages_to_window(fitted, window)


def _sse_delta(rid: str, model: str, content: str) -> str:
    payload = {
        "id": rid,
        "object": "chat.completion.chunk",
        "created": _now(),
        "model": model,
        "choices": [
            {"index": 0, "delta": {"content": content}, "finish_reason": None}
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _sse_usage_frame(rid: str, model: str, usage: dict) -> str:
    payload = {
        "id": rid,
        "object": "chat.completion.chunk",
        "created": _now(),
        "model": model,
        "choices": [],
        "usage": usage,
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _sse_stream(
    client: Any,
    model: str,
    messages: list[dict],
    rid: str,
    *,
    include_usage: bool = False,
    policy: RetryPolicy | None = None,
    observer: LoopObserver | None = None,
):
    # WC-19: bind the served turn's observer for the whole streaming region and
    # close it on every exit, so a cut connection still reports its turn.
    token = bind_observer(observer) if observer is not None else None
    try:
        try:
            measured: tuple[int, int] | None = None
            content_parts: list[str] = []
            async for chunk in stream_with_retry(
                lambda: _chat_stream(client, model, messages), policy=policy
            ):
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    content_parts.append(delta)
                    yield _sse_delta(rid, model, delta)
                if measured is None:
                    measured = extract_measured_counts(chunk)
            if include_usage:
                # Honest accounting: measured counts pass through, missing ones are
                # openly estimated and flagged — never the old silent zeros.
                usage = build_usage(
                    serialize_prompt(messages),
                    "".join(content_parts),
                    prompt_tokens=None if measured is None else measured[0],
                    completion_tokens=None if measured is None else measured[1],
                )
                yield _sse_usage_frame(rid, model, usage)
            yield f"data: {STREAM_MARKER}\n\n"
        except Exception as exc:  # noqa: BLE001
            # WH-50: the stream error carries the same request id as the response
            # header and the correlated log line. kind/retryable come from the one
            # classifier, so a streamed failure reads like the same failure in the
            # chat loop and the served error body both key on one table.
            failure = provider_errors.classify(exc)
            structured_log(
                "error", "stream_error", request_id=rid, scope="net",
                error=str(exc), kind=failure.kind.value, retryable=failure.retryable,
            )
            frame = error_payload(ErrorCode.STREAM, str(exc), rid)
            frame["error"]["kind"] = failure.kind.value
            frame["error"]["retryable"] = failure.retryable
            if failure.status is not None:
                frame["error"]["status"] = failure.status
            if failure.retry_after is not None:
                frame["error"]["retry_after"] = failure.retry_after
            yield f"data: {json.dumps(frame)}\n\n"
    finally:
        if observer is not None:
            observer.note_turn_end()
        if token is not None:
            reset_observer(token)


async def _aclose_quietly(stream: Any) -> None:
    """Close an async stream, tolerating one that is already gone."""
    aclose = getattr(stream, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except (RuntimeError, StopAsyncIteration):
        # RuntimeError: the generator is already running elsewhere.
        # StopAsyncIteration: it finished between the check and the call.
        pass


class _OwnedStreams:
    """The provider streams one served turn opened.

    A provider stream owns its HTTP connection, so closing the stream is what
    ends the upstream request. The close has to happen when the turn ends even
    if the consumer left mid-answer, or Ollama/vLLM keeps generating into a
    socket nobody reads.
    """

    def __init__(self) -> None:
        self._streams: list[Any] = []

    def register(self, stream: Any) -> None:
        self._streams.append(stream)

    async def aclose(self) -> None:
        streams, self._streams = self._streams, []
        for stream in streams:
            await _aclose_quietly(stream)


class _OwnedClient:
    """Provider client whose streamed bodies register themselves for closure."""

    def __init__(self, inner: Any, owned: _OwnedStreams) -> None:
        self._inner = inner
        self._owned = owned

    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        body = self._inner.chat(model=model, messages=messages, stream=stream, **kwargs)
        return self._track(body) if stream else body

    async def _track(self, body: Any) -> AsyncIterator[dict]:
        stream = await body if inspect.isawaitable(body) else body
        self._owned.register(stream)
        try:
            async for chunk in stream:
                yield chunk
        finally:
            await _aclose_quietly(stream)


class ServeStreamingResponse(StreamingResponse):
    """SSE response that closes the served turn when the consumer goes away.

    Starlette watches for ``http.disconnect`` only below ASGI spec_version 2.4,
    and on every version it leaves the body iterator suspended once the consumer
    left, so the upstream stream keeps producing until the generator is
    collected. This watches on every version and closes the turn's provider
    streams, so a disconnect ends the upstream request instead of orphaning it.
    """

    def __init__(
        self, content: Any, *, owned: _OwnedStreams | None = None, **kwargs: Any
    ) -> None:
        super().__init__(content, **kwargs)
        self._owned = owned

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await super().__call__(scope, receive, send)
            return
        try:
            await self._stream_until_disconnect(receive, send)
        except OSError:
            # A socket that died under a `send` is a gone client, the way
            # Starlette reports the spec_version 2.4 path.
            raise ClientDisconnect() from None
        finally:
            # Close the turn even when a disconnect cancelled this task: the
            # cleanup must not be dropped on the floor mid-cancel.
            with anyio.CancelScope(shield=True):
                await self._close_turn()

    async def _stream_until_disconnect(self, receive: Any, send: Any) -> None:
        """Send the body and watch the consumer, on every ASGI spec_version.

        Starlette watches for ``http.disconnect`` only below spec_version 2.4,
        so this keeps its own watch and cancels the body when the consumer
        leaves.
        """

        async def pump() -> None:
            try:
                await self.stream_response(send)
            finally:
                # Close the body where it ran: the observer token it binds is
                # context-local, so it has to be reset in this task.
                await _aclose_quietly(self.body_iterator)

        pump_task = asyncio.ensure_future(pump())
        watch = asyncio.ensure_future(self._listen_for_disconnect(receive))
        _, pending = await asyncio.wait(
            {pump_task, watch}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError):
                await task
        for task in (pump_task, watch):
            if task.done() and not task.cancelled():
                task.result()  # surface a real failure from either side

    @staticmethod
    async def _listen_for_disconnect(receive: Any) -> None:
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return

    async def _close_turn(self) -> None:
        """Close every provider stream this turn opened."""
        if self._owned is not None:
            await self._owned.aclose()


def create_openai_app(api_token: str | None = None) -> FastAPI:
    """
    Builds the OpenAI-compatible FastAPI app.

    Used in tests (httpx.ASGITransport) and in ``ephe serve`` (uvicorn).

    Explicit empty lifespan: bypasses the FastAPI default router lifespan,
    which in this starlette version fails at startup with
    "NoneType object is not callable" (same pattern as server/main.py).
    """

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        yield

    app = FastAPI(
        title="Ephe OpenAI-compatible Engine",
        description="Local-first engine endpoint for agent CLIs",
        # The contract is published, not locked in the source: a consumer (agent CLI,
        # SDK codegen) reads /v1/models and /v1/chat/completions off /openapi.json.
        # These routes stay unauthenticated by design — only the data endpoints need
        # the token, and the shape of an OpenAI-compatible engine is public anyway.
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    async def _require_token(request: Request) -> None:
        if not api_token:
            return
        header = request.headers.get("x-auth-token")
        if header != api_token:
            raise HTTPException(status_code=401, detail="Invalid or missing X-Auth-Token")

    # Idempotency-Key replay cache and the remote retry policy. Both hang off the
    # app instance, so a test app and the served app never share state.
    idempotency = IdempotencyStore()
    app.state.idempotency = idempotency
    app.state.retry_policy = DEFAULT_RETRY_POLICY

    async def _parse_body(request: Request) -> dict:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")
        return body

    @app.get("/v1/models")
    async def list_models(request: Request):
        await _require_token(request)
        active = get_active_provider()
        seen: set[str] = set()
        data = []
        # List the tiers the user actually configured (offline/fast/power). An unnamed
        # tier has no id to advertise — since 2026-10-11 nothing ships a tag for it.
        for cfg in TIER_MAP.values():
            if cfg.name and cfg.name not in seen:
                seen.add(cfg.name)
                data.append({"id": cfg.name, "object": "model", "created": 0, "owned_by": OWNED_BY})
        # Ensure an active model (e.g. custom provider)
        if active.model and active.model not in seen:
            data.append({"id": active.model, "object": "model", "created": 0, "owned_by": OWNED_BY})
        return JSONResponse(
            {"object": "list", "data": data},
            headers={"X-Model-Provider": OWNED_BY, "X-Model-Tier": active.provider},
        )

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        await _require_token(request)
        body = await _parse_body(request)

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages required (non-empty array)")
        # Every entry must have role + content (OpenAI contract)
        for msg in messages:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                raise HTTPException(status_code=400, detail="Each message needs role and content")

        model_param = body.get("model")
        stream = bool(body.get("stream", False))

        policy: RetryPolicy = getattr(
            request.app.state, "retry_policy", DEFAULT_RETRY_POLICY
        )
        idem_key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
        idem_fingerprint = idempotency.fingerprint(body) if idem_key else ""
        if idem_key and not stream:
            try:
                hit = idempotency.get(idem_key, idem_fingerprint)
            except IdempotencyConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if hit is not None:
                return JSONResponse(
                    hit.payload,
                    status_code=hit.status_code,
                    headers={**hit.headers, IDEMPOTENCY_REPLAY_HEADER: "true"},
                )

        # Model resolution: an explicit model in the request wins; otherwise the
        # router: the tier the machine reaches, single source of truth.
        if model_param:
            cfg = ModelConfig(name=model_param, tier=ModelTier.FAST)
            tier = "explicit"
        else:
            cfg = await get_router().resolve()
            tier = cfg.tier.value
        model = cfg.name
        owned = _OwnedStreams()
        client = _OwnedClient(build_provider_client(_provider_config_for(cfg)), owned)
        rid = request.state.rid

        # WC-19: a served turn fits its prompt to the same window the chat loop
        # fits to, and reports the trim through the loop's own observer — so a
        # served turn shows up in ephe.loop exactly like an in-process turn.
        served_messages, dropped = _fit_served_prompt(messages, model)
        observer = LoopObserver(turn_id=rid)
        observer.note_compaction("serve", dropped)

        resp_headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Model-Tier": tier,
            "X-Model-Name": model,
            "X-Model-Provider": OWNED_BY,
            COMPACTION_EVENTS_HEADER: str(observer.counters.compaction_events),
            MESSAGES_DROPPED_HEADER: str(observer.counters.messages_dropped),
        }

        stream_options = body.get("stream_options")
        include_usage = bool(isinstance(stream_options, dict) and stream_options.get("include_usage"))

        if stream:
            # A streamed body is not held for replay: that would buffer the whole
            # stream to answer a repeat. The key is accepted, the request runs once.
            return ServeStreamingResponse(
                _sse_stream(
                    client,
                    model,
                    served_messages,
                    rid,
                    include_usage=include_usage,
                    policy=policy,
                    observer=observer,
                ),
                media_type="text/event-stream",
                headers=resp_headers,
                owned=owned,
            )

        # Non-stream: collect all chunks → one completion. Provider metrics
        # (Ollama final chunk, OpenAI-compatible usage frames) are measured and
        # passed through, otherwise honestly estimated + flagged (R33: never again 0).
        content = ""
        measured: tuple[int, int] | None = None
        try:
            async for chunk in stream_with_retry(
                lambda: _chat_stream(client, model, served_messages), policy=policy
            ):
                content += chunk.get("message", {}).get("content", "")
                if measured is None:
                    measured = extract_measured_counts(chunk)
        finally:
            observer.note_turn_end()
        usage = build_usage(
            serialize_prompt(served_messages),
            content,
            prompt_tokens=None if measured is None else measured[0],
            completion_tokens=None if measured is None else measured[1],
        )

        completion = {
            "id": rid,
            "object": "chat.completion",
            "created": _now(),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }
        completion_headers = {
            "X-Model-Tier": tier,
            "X-Model-Name": model,
            "X-Model-Provider": OWNED_BY,
            "X-Usage-Estimated": "true" if usage["usage_estimated"] else "false",
            COMPACTION_EVENTS_HEADER: str(observer.counters.compaction_events),
            MESSAGES_DROPPED_HEADER: str(observer.counters.messages_dropped),
        }
        if idem_key:
            idempotency.put(
                idem_key,
                idem_fingerprint,
                status_code=200,
                payload=completion,
                headers=completion_headers,
            )
        return JSONResponse(completion, headers=completion_headers)

    # Observability (Phase 4 Item 15): request ID + structured logs
    app.middleware("http")(make_observability_middleware(prefix="chatcmpl-"))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Registered on the Starlette base class so an unknown route (404/405) answers
        # the same envelope a consumer already parses. The code comes from the one
        # table in core/provider_errors, so 401/404/400 agree with the stream body.
        rid = request.state.rid
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        code_id = provider_errors.status_error_code(exc.status_code)
        return JSONResponse(
            error_payload(code_id, message, rid),
            status_code=exc.status_code,
            headers={REQUEST_ID_HEADER: rid},
        )

    return app
