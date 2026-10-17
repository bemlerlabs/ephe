"""One classifier for engine failures, read by the retry loop and exposed to the UI.

A 429, a 5xx, a read timeout and a connection reset reach the loop as four
different exceptions and mean four different things: three are worth another
attempt, a 401 is not, and the code a surface reports follows from which one it
was. ``core/chat_stream.py`` decided this from a substring list of its own; its
retry policy now reads this module, and ``ProviderFailure.as_payload`` is the
OpenAI-shaped error body a UI keys on, so a single table owns what counts as
retryable and which code the failure carries.

Statuses follow HTTP. A status handed in as a bare int and a status carried by an
``httpx.HTTPStatusError`` take the same branch; ``retry_after`` reads the
``Retry-After`` header (seconds or HTTP-date) so a 429 can bound the backoff.

The repair classes a malformed tool call is refused under live in
``core/tool_repair.py`` and are re-exported here, so the serve, chat and CLI
surfaces name every error they report from one taxonomy.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any

from core.observability import ErrorCode

# The tool-call repair taxonomy lives in core/tool_repair.py; re-exported here so
# the serve, chat and CLI surfaces, and core.tools.registry, keep reading the one
# table from this module without an importer change.
from core.tool_repair import (  # noqa: F401 — re-exported for surfaces and tests
    REPAIR_CLASSES,
    REPAIR_CLASS_TOKEN,
    REPAIR_TAXONOMY,
    RepairClass,
    refuse,
    repair_class_of,
)

try:  # httpx ships with the engine client; a caller without it still classifies text
    import httpx as _httpx
except ImportError:  # pragma: no cover - the engine always has httpx
    _httpx = None  # type: ignore[assignment]


class ProviderFailureKind(str, Enum):
    """The four transient shapes plus the three that end the call."""

    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    AUTH = "auth"
    CLIENT_ERROR = "client_error"
    UNKNOWN = "unknown"


#: Statuses worth a retry: 408 Request Timeout, 425 Too Early, 429, 500, 502-504,
#: 507 Insufficient Storage, 509 Bandwidth Limit. 501 is not listed because "not
#: implemented" answers the same way on every attempt.
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504, 507, 509})

#: A 401/403 is the endpoint asking for a token; retrying sends the same token.
AUTH_STATUSES = frozenset({401, 403})

RATE_LIMIT_STATUS = 429
SERVER_ERROR_FLOOR = 500

RETRYABLE_KINDS = frozenset({
    ProviderFailureKind.RATE_LIMIT,
    ProviderFailureKind.SERVER_ERROR,
    ProviderFailureKind.TIMEOUT,
    ProviderFailureKind.TRANSPORT,
})

# Provider-side failures all report as upstream_error so a UI can show "the engine,
# not you" without knowing the exception type; auth and request errors keep their code.
_KIND_ERROR_CODE = {
    ProviderFailureKind.RATE_LIMIT: ErrorCode.UPSTREAM,
    ProviderFailureKind.SERVER_ERROR: ErrorCode.UPSTREAM,
    ProviderFailureKind.TIMEOUT: ErrorCode.UPSTREAM,
    ProviderFailureKind.TRANSPORT: ErrorCode.UPSTREAM,
    ProviderFailureKind.AUTH: ErrorCode.AUTH,
    ProviderFailureKind.CLIENT_ERROR: ErrorCode.VALIDATION,
    ProviderFailureKind.UNKNOWN: ErrorCode.INTERNAL,
}

# Lowercased substrings of a transport failure. The list keeps the wording the old
# `_TRANSIENT_MARKERS` test accepted, because a raised ollama/httpx error reaches the
# loop with only its message when it carries neither a status nor a known type.
_TRANSPORT_MARKERS = (
    "refused",
    "reset",
    "broken pipe",
    "socket",
    "connection",
    "connect",
    "econnreset",
    "econnrefused",
    "etimedout",
    "server disconnected",
    "remote protocol error",
    "unexpected eof",
    "network is unreachable",
    "no route to host",
    "getaddrinfo",
    "temporary failure in name resolution",
    "unavailable",
)

_TIMEOUT_MARKERS = ("timed out", "timeout", "deadline exceeded")

# "HTTP 503", "status: 429", "code 500" — a status with a word in front of it.
_STATUS_IN_TEXT = re.compile(r"(?:http|status|code|error)[\s:=/]{0,3}([1-5]\d{2})\b", re.IGNORECASE)
# A bare status the old marker list accepted without a leading word.
_BARE_STATUS = re.compile(r"\b(408|425|429|500|501|502|503|504|507|509)\b")
_RATE_LIMIT_TEXT = re.compile(r"too many requests|rate[\s-]?limit", re.IGNORECASE)
_RETRY_AFTER_IN_TEXT = re.compile(r"retry[\s-]?after[\s:=]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)

# Class names that mean "the caller has to fix the config", tested by name so this
# module does not import core.model_provider back and close a cycle.
_SETUP_ERROR_NAMES = frozenset({"ProviderSetupError"})


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """One engine failure in the terms the loop and the UI both read."""

    kind: ProviderFailureKind
    message: str
    status: int | None = None
    retryable: bool = False
    retry_after: float | None = None
    detail: str | None = None

    @property
    def error_code(self) -> ErrorCode:
        """The code the serve error body carries, so a UI keys on the same string."""
        return _KIND_ERROR_CODE[self.kind]

    def as_payload(self, request_id: str | None = None) -> dict[str, Any]:
        """OpenAI-shaped error body — the frame ``server/openai.py`` already sends."""
        body: dict[str, Any] = {
            "message": self.message,
            "code": self.error_code.value,
            "kind": self.kind.value,
            "retryable": self.retryable,
        }
        if self.status is not None:
            body["status"] = self.status
        if self.retry_after is not None:
            body["retry_after"] = self.retry_after
        if self.detail:
            body["detail"] = self.detail
        if request_id:
            body["request_id"] = request_id
        return {"error": body}


def _message(kind: ProviderFailureKind, status: int | None) -> str:
    if kind is ProviderFailureKind.RATE_LIMIT:
        return "The provider is rate limiting requests (HTTP 429)."
    if kind is ProviderFailureKind.SERVER_ERROR:
        return (
            f"The provider returned a server error (HTTP {status})."
            if status
            else "The provider returned a server error."
        )
    if kind is ProviderFailureKind.TIMEOUT:
        return "The provider did not answer before the timeout."
    if kind is ProviderFailureKind.TRANSPORT:
        return "The provider is unreachable (connection failed)."
    if kind is ProviderFailureKind.AUTH:
        return (
            f"The provider rejected the API key (HTTP {status})."
            if status
            else "The provider rejected the API key."
        )
    if kind is ProviderFailureKind.CLIENT_ERROR:
        return (
            f"The provider refused the request (HTTP {status})."
            if status
            else "The provider refused the request."
        )
    return "The provider call failed."


def classify_status(
    status: int, *, detail: str = "", retry_after: float | None = None
) -> ProviderFailure:
    """A failure from an HTTP status alone."""
    if status == RATE_LIMIT_STATUS:
        kind = ProviderFailureKind.RATE_LIMIT
    elif status == 408:
        kind = ProviderFailureKind.TIMEOUT
    elif status in AUTH_STATUSES:
        kind = ProviderFailureKind.AUTH
    elif status >= SERVER_ERROR_FLOOR or status == 425:
        kind = ProviderFailureKind.SERVER_ERROR
    elif 400 <= status < SERVER_ERROR_FLOOR:
        kind = ProviderFailureKind.CLIENT_ERROR
    else:
        kind = ProviderFailureKind.UNKNOWN
    return ProviderFailure(
        kind=kind,
        message=_message(kind, status),
        status=status,
        retryable=status in RETRYABLE_STATUSES,
        retry_after=retry_after,
        detail=detail or None,
    )


def _retry_after_from_text(text: str) -> float | None:
    match = _RETRY_AFTER_IN_TEXT.search(text)
    return max(0.0, float(match.group(1))) if match else None


def _retry_after_from_headers(response: Any) -> float | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after")
    except (AttributeError, TypeError):
        return None
    if raw is None:
        return None
    raw = str(raw).strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:  # the HTTP-date form, converted against now
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    delta = (when - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
    return max(0.0, delta)


def _status_and_retry_after(exc: BaseException) -> tuple[int | None, float | None]:
    """The HTTP status an exception carries, from ollama or httpx."""
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        status = None
    retry_after = _retry_after_from_headers(response) if response is not None else None
    return status, retry_after


def classify_exception(exc: BaseException) -> ProviderFailure:
    """The failure a raised exception stands for."""
    detail = str(exc) or type(exc).__name__

    status, retry_after = _status_and_retry_after(exc)
    if status is not None:
        return classify_status(status, detail=detail, retry_after=retry_after)

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or (
        _httpx is not None and isinstance(exc, _httpx.TimeoutException)
    ):
        return ProviderFailure(
            kind=ProviderFailureKind.TIMEOUT,
            message=_message(ProviderFailureKind.TIMEOUT, None),
            retryable=True,
            retry_after=_retry_after_from_text(detail),
            detail=detail,
        )

    text_status = _STATUS_IN_TEXT.search(detail)
    bare_status = text_status or _BARE_STATUS.search(detail)
    if bare_status is not None:
        return classify_status(
            int(bare_status.group(1)), detail=detail, retry_after=_retry_after_from_text(detail)
        )

    if _RATE_LIMIT_TEXT.search(detail):
        return ProviderFailure(
            kind=ProviderFailureKind.RATE_LIMIT,
            message=_message(ProviderFailureKind.RATE_LIMIT, None),
            retryable=True,
            retry_after=_retry_after_from_text(detail),
            detail=detail,
        )

    low = detail.lower()
    transport_typed = (_httpx is not None and isinstance(exc, _httpx.TransportError)) or isinstance(
        exc, (ConnectionError, OSError)
    )
    if transport_typed:
        kind = ProviderFailureKind.TRANSPORT
    elif any(marker in low for marker in _TIMEOUT_MARKERS):
        kind = ProviderFailureKind.TIMEOUT
    elif any(marker in low for marker in _TRANSPORT_MARKERS):
        kind = ProviderFailureKind.TRANSPORT
    elif type(exc).__name__ in _SETUP_ERROR_NAMES:
        # A missing key or a malformed base URL: the caller fixes it, a retry does not.
        return ProviderFailure(
            kind=ProviderFailureKind.CLIENT_ERROR,
            message=detail,
            retryable=False,
            detail=detail,
        )
    else:
        kind = ProviderFailureKind.UNKNOWN

    return ProviderFailure(
        kind=kind,
        message=_message(kind, None),
        retryable=kind in RETRYABLE_KINDS,
        retry_after=_retry_after_from_text(detail),
        detail=detail,
    )


def classify(error: object) -> ProviderFailure:
    """The failure an int status, an exception or an existing failure stands for."""
    if isinstance(error, ProviderFailure):
        return error
    if isinstance(error, int) and not isinstance(error, bool):
        return classify_status(error)
    if isinstance(error, BaseException):
        return classify_exception(error)
    return ProviderFailure(
        kind=ProviderFailureKind.UNKNOWN,
        message=str(error) or "The provider call failed.",
        detail=None,
    )


def is_retryable(error: object) -> bool:
    """Whether another attempt is worth it for this failure."""
    return classify(error).retryable


#: Statuses an HTTP route answers with when the path itself is unknown. The serve
#: app maps them to ``not_found`` instead of leaking the framework's detail body.
NOT_FOUND_STATUSES = frozenset({404, 405})

#: The HTTP status a served answer carries for a failure kind: the engine's own
#: 429/401 pass through, a backend that did not answer is 502, a timeout 504, a
#: caller error 400, anything unplaced is 500.
_KIND_STATUS = {
    ProviderFailureKind.RATE_LIMIT: 429,
    ProviderFailureKind.SERVER_ERROR: 502,
    ProviderFailureKind.TIMEOUT: 504,
    ProviderFailureKind.TRANSPORT: 502,
    ProviderFailureKind.AUTH: 401,
    ProviderFailureKind.CLIENT_ERROR: 400,
    ProviderFailureKind.UNKNOWN: 500,
}

#: Text that means the engine does not have the requested model. A caller error the
#: chat surface raises as its own model-missing exception, so it is never retried.
MODEL_MISSING_MARKERS = ("not found", "does not exist")


def error_code_for(error: object) -> ErrorCode:
    """The stable code every surface reports for this failure."""
    return classify(error).error_code


def http_status_for(error: object) -> int:
    """The HTTP status a served answer carries for this failure."""
    return _KIND_STATUS[classify(error).kind]


def status_error_code(status: int) -> ErrorCode:
    """The code for an HTTP status a route itself raises: auth, not found, else validation."""
    if status in AUTH_STATUSES:
        return ErrorCode.AUTH
    if status in NOT_FOUND_STATUSES:
        return ErrorCode.NOT_FOUND
    return ErrorCode.VALIDATION


def exit_code_for(error: object) -> int:
    """The CLI exit code: 2 when the caller can fix it, else 1 (engine side)."""
    return 2 if classify(error).error_code in (ErrorCode.VALIDATION, ErrorCode.USAGE) else 1


def is_model_missing(error: object) -> bool:
    """Whether a failure is the engine not having the requested model."""
    text = str(error).lower()
    return any(marker in text for marker in MODEL_MISSING_MARKERS)
