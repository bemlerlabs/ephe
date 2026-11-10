"""The picture tool. It asks the host.

The worker has no store and cannot import the application. The bridge
handle is the third argument. The text it brings back is the tool result,
including the failure line the kernel tool already writes.
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


def _kwargs(arguments, names):
    arguments = arguments or {}
    extra = {}
    for name in names:
        if name in arguments and arguments[name] is not None:
            extra[name] = arguments[name]
    return extra


def _required(arguments, key: str) -> str:
    arguments = arguments or {}
    value = arguments.get(key)
    return "" if value is None else str(value)


def generate_image(arguments, _state_dir, bridge):
    return _ask(
        "generate_image",
        lambda: bridge.generate_image(
            _required(arguments, "prompt"),
            **_kwargs(arguments, ("filename", "size")),
        ),
    )
