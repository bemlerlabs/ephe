"""The browser tools. Each one asks the host and returns its sentence.

The worker has no browser and cannot import the application. The bridge
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


def browser_go(arguments, _state_dir, bridge):
    arguments = arguments or {}
    url = str(arguments.get("url") or "")
    return _ask("browser_go", lambda: bridge.browser_go(url))


def browser_screenshot(arguments, _state_dir, bridge):
    return _ask("browser_screenshot", lambda: bridge.browser_screenshot())


def browser_click(arguments, _state_dir, bridge):
    arguments = arguments or {}
    target = str(arguments.get("target_description") or "")
    return _ask("browser_click", lambda: bridge.browser_click(target))


def browser_type(arguments, _state_dir, bridge):
    arguments = arguments or {}
    text = str(arguments.get("text") or "")
    return _ask("browser_type", lambda: bridge.browser_type(text))


def browser_press(arguments, _state_dir, bridge):
    arguments = arguments or {}
    key = str(arguments.get("key") or "")
    return _ask("browser_press", lambda: bridge.browser_press(key))


def browser_scroll(arguments, _state_dir, bridge):
    arguments = arguments or {}
    kwargs = {}
    if "direction" in arguments and arguments["direction"] is not None:
        kwargs["direction"] = arguments["direction"]
    if "amount" in arguments and arguments["amount"] is not None:
        kwargs["amount"] = arguments["amount"]
    return _ask("browser_scroll", lambda: bridge.browser_scroll(**kwargs))


def browser_evaluate(arguments, _state_dir, bridge):
    arguments = arguments or {}
    js = str(arguments.get("js") or "")
    return _ask("browser_evaluate", lambda: bridge.browser_evaluate(js))


def browser_exec(arguments, _state_dir, bridge):
    arguments = arguments or {}
    kwargs = {}
    if "session" in arguments and arguments["session"] is not None:
        kwargs["session"] = str(arguments["session"])
    if "timeout_s" in arguments and arguments["timeout_s"] is not None:
        kwargs["timeout_s"] = arguments["timeout_s"]
    code = str(arguments.get("code") or "")
    return _ask("browser_exec", lambda: bridge.browser_exec(code, **kwargs))
