"""The two research tools. Each one asks the host and returns its sentence.

The worker has no socket and cannot import the application. The bridge handle
is the third argument. The text it brings back is the tool result, including
the failure line the kernel tool already writes.
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
    out = {"text": body, "code": code}
    params = (page or {}).get("params")
    if isinstance(params, dict) and params:
        out["params"] = {str(key): str(value) for key, value in params.items()}
    return out


def _failure(name: str, exc: BaseException) -> str:
    detail = getattr(exc, "detail", "") or getattr(exc, "code", "") or type(exc).__name__
    return f"[tool-error '{name}': {detail}]"


def web_search(arguments, _state_dir, bridge):
    arguments = arguments or {}
    query = str(arguments.get("query") or "")
    max_results = arguments.get("max_results")
    try:
        if max_results is None:
            page = bridge.search(query)
        else:
            page = bridge.search(query, max_results=max_results)
    except Exception as exc:
        return _failure("web_search", exc)
    return _answer(page)


def fetch_url(arguments, _state_dir, bridge):
    arguments = arguments or {}
    url = str(arguments.get("url") or "")
    prompt = arguments.get("prompt")
    try:
        if prompt is None:
            page = bridge.fetch_url(url)
        else:
            page = bridge.fetch_url(url, prompt=str(prompt))
    except Exception as exc:
        return _failure("fetch_url", exc)
    return _answer(page)
