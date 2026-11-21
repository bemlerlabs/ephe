"""The image read, the click and the typing. Each one asks the host.

The worker has no desktop and cannot import the application. The bridge
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


def analyze_image(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = str(arguments.get("path") or "")
    question = arguments.get("question")
    region = arguments.get("region")
    has_question = "question" in arguments and question is not None
    has_region = "region" in arguments and region is not None
    if has_question and has_region:
        return _ask(
            "analyze_image",
            lambda: bridge.analyze_image(path, question=str(question), region=region),
        )
    if has_question:
        return _ask(
            "analyze_image", lambda: bridge.analyze_image(path, question=str(question))
        )
    if has_region:
        return _ask("analyze_image", lambda: bridge.analyze_image(path, region=region))
    return _ask("analyze_image", lambda: bridge.analyze_image(path))


def vision_click(arguments, _state_dir, bridge):
    arguments = arguments or {}
    target = str(arguments.get("target_description") or "")
    return _ask("vision_click", lambda: bridge.vision_click(target))


def vision_type(arguments, _state_dir, bridge):
    arguments = arguments or {}
    text = str(arguments.get("text") or "")
    if "press_enter" in arguments and arguments["press_enter"] is not None:
        return _ask(
            "vision_type",
            lambda: bridge.vision_type(text, press_enter=arguments["press_enter"]),
        )
    return _ask("vision_type", lambda: bridge.vision_type(text))
