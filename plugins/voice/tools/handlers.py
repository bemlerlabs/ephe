"""The speech tools. They ask the host.

The worker has no piper binary and no speech model. The bridge handle is
the third argument. The text it brings back is the tool result.
"""

from __future__ import annotations


def _text(page) -> str:
    body = str((page or {}).get("text") or "")
    if (page or {}).get("truncated"):
        return body + "\n[truncated]"
    return body


def _failure(name: str, exc: BaseException) -> str:
    detail = getattr(exc, "detail", "") or getattr(exc, "code", "") or type(exc).__name__
    return f"[tool-error '{name}': {detail}]"


def _ask(name: str, call):
    try:
        page = call()
    except Exception as exc:
        return _failure(name, exc)
    return _text(page)


def _required(arguments, key: str) -> str:
    arguments = arguments or {}
    value = arguments.get(key)
    return "" if value is None else str(value)


def synthesize(arguments, _state_dir, bridge):
    return _ask(
        "synthesize",
        lambda: bridge.synthesize(_required(arguments, "text")),
    )


def transcribe(arguments, _state_dir, bridge):
    return _ask(
        "transcribe",
        lambda: bridge.transcribe(_required(arguments, "name")),
    )
