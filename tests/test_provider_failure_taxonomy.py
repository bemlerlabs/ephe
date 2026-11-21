"""WC-20: the one provider failure taxonomy the retry loop and the UI share.

``core/provider_errors.py`` is the single table. These tests pin the status bands,
the exception and text fallbacks, the Retry-After read, that the retry policy in
``core/chat_stream.py`` decides through it, and that the error body a UI reads comes
from the same failure object.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import httpx
import pytest

from core import provider_errors as pe
from core.chat_stream import (
    RETRY_AFTER_CAP,
    RetryPolicy,
    is_transient_error,
    stream_with_retry,
)
from core.model_provider import KEY_CHALLENGE_STATUSES, ProviderSetupError
from core.observability import ErrorCode

Kind = pe.ProviderFailureKind


def status_error(status: int, *, retry_after: str | None = None) -> httpx.HTTPStatusError:
    """A real httpx status error, the type the engine client raises."""
    request = httpx.Request("POST", "http://engine.local/v1/chat/completions")
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    response = httpx.Response(status, headers=headers, request=request, text="body")
    return httpx.HTTPStatusError(f"{status} from engine", request=request, response=response)


class _OllamaLike(Exception):
    """Stands in for ollama.ResponseError, which carries the status on the instance."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__("ollama error")


def ok_stream(*chunks: str):
    async def _gen():
        for chunk in chunks:
            yield {"message": {"content": chunk}}

    return _gen


def raising(error: BaseException):
    def _open():
        async def _gen():
            raise error
            yield {}  # pragma: no cover - makes _gen an async generator

        return _gen()

    return _open


@pytest.mark.parametrize(
    "status, kind",
    [
        (429, Kind.RATE_LIMIT),
        (500, Kind.SERVER_ERROR),
        (502, Kind.SERVER_ERROR),
        (503, Kind.SERVER_ERROR),
        (504, Kind.SERVER_ERROR),
        (408, Kind.TIMEOUT),
        (425, Kind.SERVER_ERROR),
        (401, Kind.AUTH),
        (403, Kind.AUTH),
        (400, Kind.CLIENT_ERROR),
        (404, Kind.CLIENT_ERROR),
        (422, Kind.CLIENT_ERROR),
    ],
)
def test_status_band_maps_to_one_kind(status, kind):
    assert pe.classify_status(status).kind is kind


def test_only_the_transient_statuses_are_retryable():
    retryable = {408, 425, 429, 500, 502, 503, 504, 507, 509}
    for status in retryable:
        assert pe.classify_status(status).retryable is True
    # 501 "not implemented" and every caller error answer the same way on a retry.
    for status in (501, 400, 401, 403, 404, 422):
        assert pe.classify_status(status).retryable is False


def test_a_non_error_status_is_not_a_failure():
    failure = pe.classify_status(200)
    assert failure.kind is Kind.UNKNOWN
    assert failure.retryable is False


def test_httpx_status_error_carries_its_status_and_retry_after():
    failure = pe.classify(status_error(429, retry_after="7"))
    assert failure.kind is Kind.RATE_LIMIT
    assert failure.status == 429
    assert failure.retryable is True
    assert failure.retry_after == 7.0


def test_retry_after_http_date_is_converted_to_seconds():
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=120)
    header = when.strftime("%a, %d %b %Y %H:%M:%S GMT")
    failure = pe.classify(status_error(503, retry_after=header))
    assert failure.retry_after is not None
    assert 100.0 <= failure.retry_after <= 120.0


def test_ollama_style_status_attribute_is_read():
    assert pe.classify(_OllamaLike(503)).kind is Kind.SERVER_ERROR
    assert pe.classify(_OllamaLike(429)).kind is Kind.RATE_LIMIT


def test_timeouts_classify_as_timeout():
    for exc in (httpx.ReadTimeout("slow"), httpx.ConnectTimeout("slow"), asyncio.TimeoutError()):
        failure = pe.classify(exc)
        assert failure.kind is Kind.TIMEOUT
        assert failure.retryable is True


def test_connection_failures_classify_as_transport():
    for exc in (httpx.ConnectError("nope"), ConnectionError("refused"), OSError("down")):
        failure = pe.classify(exc)
        assert failure.kind is Kind.TRANSPORT
        assert failure.retryable is True


def test_provider_setup_error_is_a_caller_error():
    failure = pe.classify(ProviderSetupError("no engine chosen"))
    assert failure.kind is Kind.CLIENT_ERROR
    assert failure.retryable is False
    assert failure.error_code is ErrorCode.VALIDATION


@pytest.mark.parametrize(
    "message, kind",
    [
        ("connection refused", Kind.TRANSPORT),
        ("HTTP 503 Service Unavailable", Kind.SERVER_ERROR),
        ("429 Too Many Requests", Kind.RATE_LIMIT),
        ("upstream answered 502", Kind.SERVER_ERROR),
        ("read timeout after 30s", Kind.TIMEOUT),
    ],
)
def test_text_fallback_reads_the_message(message, kind):
    assert pe.classify(RuntimeError(message)).kind is kind
    assert pe.classify(RuntimeError(message)).retryable is True


def test_a_caller_error_in_text_is_not_retryable():
    failure = pe.classify(RuntimeError("model 'x' not found locally"))
    assert failure.kind is Kind.UNKNOWN
    assert failure.retryable is False


def test_retry_after_in_text_is_read():
    failure = pe.classify(RuntimeError("429 rate limited, retry-after: 12"))
    assert failure.retry_after == 12.0


def test_classify_accepts_a_status_a_failure_or_an_exception():
    assert pe.classify(503).kind is Kind.SERVER_ERROR
    once = pe.classify(status_error(429))
    assert pe.classify(once) is once


def test_error_code_and_payload_are_the_ui_contract():
    failure = pe.classify(status_error(429, retry_after="5"))
    assert failure.error_code is ErrorCode.UPSTREAM
    body = failure.as_payload("req-1")["error"]
    assert body["code"] == "upstream_error"
    assert body["kind"] == "rate_limit"
    assert body["retryable"] is True
    assert body["status"] == 429
    assert body["retry_after"] == 5.0
    assert body["request_id"] == "req-1"
    assert pe.classify(status_error(401)).as_payload()["error"]["code"] == "auth_error"


def test_the_auth_set_has_one_owner():
    assert KEY_CHALLENGE_STATUSES is pe.AUTH_STATUSES
    assert pe.AUTH_STATUSES == frozenset({401, 403})


def test_the_retry_loop_name_delegates_to_the_taxonomy():
    samples = [
        ConnectionError("connection refused"),
        RuntimeError("HTTP 503 Service Unavailable"),
        RuntimeError("model 'x' not found locally"),
        status_error(429),
        status_error(400),
    ]
    for exc in samples:
        assert is_transient_error(exc) is pe.is_retryable(exc)


async def test_stream_with_retry_honors_retry_after_from_a_429():
    delays: list[float] = []
    attempts = {"n": 0}

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    def open_stream():
        attempts["n"] += 1
        if attempts["n"] == 1:
            return raising(status_error(429, retry_after="9"))()
        return ok_stream("done")()

    chunks = [
        chunk
        async for chunk in stream_with_retry(
            open_stream, policy=RetryPolicy(base_delay=0.1), sleep=fake_sleep
        )
    ]
    assert [c["message"]["content"] for c in chunks] == ["done"]
    assert delays == [9.0]


async def test_retry_after_is_capped():
    delays: list[float] = []
    attempts = {"n": 0}

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    def open_stream():
        attempts["n"] += 1
        if attempts["n"] == 1:
            return raising(status_error(429, retry_after="999"))()
        return ok_stream("done")()

    async for _ in stream_with_retry(
        open_stream, policy=RetryPolicy(base_delay=0.1), sleep=fake_sleep
    ):
        pass
    assert delays == [RETRY_AFTER_CAP]


async def test_a_caller_error_is_raised_without_a_retry():
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in stream_with_retry(
            raising(status_error(400)),
            policy=RetryPolicy(base_delay=0.1),
            sleep=fake_sleep,
        ):
            pass
    assert delays == []


async def test_a_failure_after_the_first_chunk_is_not_retried():
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    def open_stream():
        async def _gen():
            yield {"message": {"content": "partial"}}
            raise status_error(503)

        return _gen()

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in stream_with_retry(
            open_stream, policy=RetryPolicy(base_delay=0.1), sleep=fake_sleep
        ):
            pass
    assert delays == []
