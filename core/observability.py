"""
◑ Ephe – Observability primitives (Phase 4 Item 15)
core/observability.py

Single source of truth for:
  - stable, machine-readable error codes (ErrorCode enum)
  - request-ID generation (X-Request-ID header + body, correlated logs)
  - structured JSON logs (structured_log)
  - Starlette HTTP middleware factory (request ID + request logging)

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from enum import Enum

REQUEST_ID_HEADER = "X-Request-ID"

# Dedicated logger — stays decoupled from uvicorn.error / getLogger("uvicorn").
_logger = logging.getLogger("ephe.obs")


class ErrorCode(str, Enum):
    """Stable, machine-readable error codes (Phase 4 Item 15).

    Values never change; new codes are only appended (back-compat).
    The mapping onto exit codes / HTTP status stays with the callers (CLI/engine).
    """
    USAGE = "usage_error"        # CLI: invalid arguments / argparse usage
    RUNTIME = "runtime_error"    # CLI: runtime error (exit 1)
    VALIDATION = "validation_error"  # HTTP 400: request validation
    AUTH = "auth_error"          # HTTP 401: missing/wrong token
    STREAM = "stream_error"      # SSE: error in the middle of a stream
    UPSTREAM = "upstream_error"  # provider/backend (Ollama/ds4) unreachable
    INTERNAL = "internal_error"  # unexpected exception (500)
    NOT_FOUND = "not_found"      # HTTP 404/405: unknown route
    SETUP_REQUIRED = "setup_required"  # HTTP 409: no engine chosen (W19 setup mode)
    SKILLS_LOCK_MISMATCH = "skills_lock_mismatch"  # W4 S2: skills-lock.json vs. disk (append-only)


# W4 S4: scope-logger cache — identical calls return identical objects.
_SCOPE_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(scope: str = "obs") -> logging.Logger:
    """Cached scope logger ``ephe.<scope>`` (W4 S4).

    Level contract (handler side, see make_prod_handler):
      - debug : not persisted (dev detail only)
      - info  : lifecycle events
      - warn  : recoverable deviations
      - error : unrecoverable

    Repeated calls for the same scope unanimously return the same logger object.
    """
    cached = _SCOPE_LOGGERS.get(scope)
    if cached is not None:
        return cached
    logger = logging.getLogger(f"ephe.{scope}")
    # Level contract: settled from INFO upward (debug is not persisted). Set our own
    # level only when the project has not set one yet — existing settings
    # (tests, embedding apps) stay untouched.
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)
    _SCOPE_LOGGERS[scope] = logger
    return logger


def make_prod_handler() -> logging.Handler:
    """Stderr handler with the production level contract: debug is not persisted,
    info and above are (W4 S4). The filter is set in addition to the handler level."""
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.filter = lambda record: record.levelno >= logging.INFO  # type: ignore[assignment]
    return handler


def new_request_id(prefix: str = "req") -> str:
    """Compact, low-collision request ID (truncated uuid4 hex)."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def structured_log(
    level: str, event: str, request_id: str | None = None, **fields
) -> None:
    """Emit a single-line, JSON-parseable structured log line.

    Args:
        level:  "debug" | "info" | "warning" | "error"
        event:  stable event name (e.g. "request", "internal_error")
        request_id: correlated request ID (X-Request-ID)
        fields: any structured fields (method, path, status, ...);
            W4 S4: required field 'scope' defaulting to 'obs' — the line is
            routed to the scope logger (ephe.<scope>).

    Level contract (W4 S4): debug = not persisted, info = lifecycle,
    warn = recoverable, error = unrecoverable.
    """
    scope = fields.get("scope") or "obs"
    record = {
        "ts": f"{time.time():.3f}",
        "level": level,
        "event": event,
        "request_id": request_id,
        "scope": scope,
    }
    record.update(fields)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    getattr(get_logger(scope), level)(line)


def error_payload(
    code: ErrorCode, message: str, request_id: str | None = None
) -> dict:
    """OpenAI-conformant error body with stable codes (Phase 4)."""
    body = {"error": {"message": message, "code": code.value}}
    if request_id:
        body["error"]["request_id"] = request_id
    return body


def make_observability_middleware(prefix: str = "req"):
    """Factory for a Starlette HTTP middleware: request ID + structured logs.

    - sets request.state.rid (request ID, or the X-Request-ID header when one was sent)
    - writes X-Request-ID into the response headers
    - logs every request as a structured JSON line (event="request")
    - unexpected exceptions → 500 with ErrorCode.INTERNAL + request ID

    prefix: prefix of the generated request IDs (e.g. "chatcmpl-" for the engine).

    Uses lazy imports so core/ stays light (no heavy module on the CLI load path).
    """
    async def _middleware(request, call_next):
        from starlette.responses import JSONResponse  # lazy

        rid = request.headers.get(REQUEST_ID_HEADER) or new_request_id(prefix)
        request.state.rid = rid
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            structured_log(
                "error", "internal_error", request_id=rid, scope="net",
                method=request.method, path=request.url.path,
                error=str(exc),
            )
            response = JSONResponse(
                error_payload(ErrorCode.INTERNAL, str(exc), rid),
                status_code=500,
                headers={REQUEST_ID_HEADER: rid},
            )
        response.headers[REQUEST_ID_HEADER] = rid
        structured_log(
            "info", "request", request_id=rid, scope="net",
            method=request.method, path=request.url.path,
            status=response.status_code,
            duration_ms=f"{1000 * (time.perf_counter() - start):.1f}",
        )
        return response

    return _middleware
