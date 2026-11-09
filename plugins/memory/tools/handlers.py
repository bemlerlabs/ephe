"""The memory tool. Each action asks the host and returns the kernel sentence.

The worker has no store and cannot import the application. The bridge handle
is the third argument. The text it brings back is the tool result, including
a coded sentence the kernel tool already writes. A blank field stays on the
wire when the caller sent it, so the kernel sentence for that field still runs.
"""

from __future__ import annotations


def _text(page) -> str:
    body = str((page or {}).get("text") or "")
    if (page or {}).get("truncated"):
        return body + "\n[truncated]"
    return body


def _answer(page):
    """The sentence, plus the code when the kernel tool put one on it."""
    body = _text(page)
    code = str((page or {}).get("code") or "")
    if not code:
        return body
    out = {"text": body, "code": code, "happened": bool((page or {}).get("happened"))}
    params = (page or {}).get("params")
    if isinstance(params, dict) and params:
        out["params"] = {str(key): str(value) for key, value in params.items()}
    return out


def _failure(name: str, exc: BaseException) -> str:
    detail = getattr(exc, "detail", "") or getattr(exc, "code", "") or type(exc).__name__
    return f"[tool-error '{name}': {detail}]"


def _fields(arguments: dict, names: tuple[str, ...]) -> dict:
    """Arguments the caller sent. A missing key stays off the wire."""
    out = {"target": str(arguments.get("target") or "")}
    for name in names:
        if name in arguments and arguments[name] is not None:
            out[name] = str(arguments[name])
    return out


_OPTIONAL = ("content", "old_text", "memory_type", "supersedes")


def memory(arguments, _state_dir, bridge):
    arguments = arguments or {}
    action = str(arguments.get("action") or "").strip().lower()
    fields = _fields(arguments, _OPTIONAL)
    try:
        if action == "add":
            page = bridge.memory_add(**fields)
        elif action == "replace":
            page = bridge.memory_replace(**fields)
        elif action == "remove":
            page = bridge.memory_remove(**fields)
        elif action == "list":
            page = bridge.memory_list(**fields)
        else:
            page = bridge.memory_action(action, **fields)
    except Exception as exc:
        return _failure("memory", exc)
    return _answer(page)
