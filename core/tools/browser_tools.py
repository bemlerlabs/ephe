"""Ephe – Browser and vision tools."""

from __future__ import annotations

import base64 as base64_mod
import os
import time
from pathlib import Path


def _get_vision_click():
    from core.vision import vision_click
    return vision_click


def _get_vision_type():
    from core.vision import vision_type
    return vision_type


async def _vision_click_wrapper(target_description: str) -> str:
    fn = _get_vision_click()
    return await fn(target_description)


async def _vision_type_wrapper(text: str, press_enter: bool = False) -> str:
    fn = _get_vision_type()
    return await fn(text, press_enter)


vision_click = _vision_click_wrapper
vision_type = _vision_type_wrapper


def _get_browser_manager():
    from core.browser import browser_manager
    return browser_manager


async def browser_go(url: str) -> str:
    bm = _get_browser_manager()
    return await bm.go(url)


async def browser_screenshot() -> str:
    bm = _get_browser_manager()
    b64 = await bm.screenshot()
    image_dir = Path(os.environ.get("EPHE_IMAGE_DIR") or str(Path.home() / ".ephe" / "sessions" / "images"))
    image_dir.mkdir(parents=True, exist_ok=True)
    filename = f"browser_{int(time.time())}.jpeg"
    shot = image_dir / filename
    with open(shot, "wb") as f:
        f.write(base64_mod.b64decode(b64))
    # The marker is what turns the file into an artifact: without it the screenshot
    # stayed mere Markdown in the text — never in the workbench, never findable.
    return f"SCREENSHOT_FILE:{shot}\n\nBrowser screenshot captured:\n\n![Browser](/images/{filename})"


async def browser_click(target_description: str) -> str:
    bm = _get_browser_manager()
    return await bm.click(target_description)


async def browser_type(text: str) -> str:
    bm = _get_browser_manager()
    return await bm.type_text(text)


async def browser_press(key: str) -> str:
    bm = _get_browser_manager()
    return await bm.press(key)


# J5: parity deepening — scroll / evaluate / clipboard / display

async def browser_scroll(direction: str = "down", amount: int = 600) -> str:
    """Scrolls the page (up|down|left|right) by amount pixels."""
    bm = _get_browser_manager()
    return await bm.scroll(direction, amount)


async def browser_evaluate(js: str) -> str:
    """Evaluates a JS expression in the page and returns the JSON result."""
    bm = _get_browser_manager()
    return await bm.evaluate(js)


async def clipboard_read() -> str:
    """Reads the clipboard text via the page's navigator.clipboard."""
    bm = _get_browser_manager()
    return await bm.clipboard_read()


async def clipboard_write(text: str) -> str:
    """Writes text to the clipboard via the page's navigator.clipboard."""
    bm = _get_browser_manager()
    return await bm.clipboard_write(text)


async def get_display_info() -> str:
    """Viewport + device-pixel-ratio + scroll height of the current page."""
    bm = _get_browser_manager()
    return await bm.display_info()


# browser_exec: one Python namespace per call (session-isolated)
# A single tool that runs as full Python — the helpers are already there before
# the first call (no per-tool round trip). The parallel pattern to
# execute_code, only with the browser namespace instead of ephe_tools.

_BROWSER_KERNELS: dict[str, dict[str, object]] = {}
_BROWSER_EXEC_COUNT = 0
_MAX_BROWSER_STDOUT = 20000

# A time budget that never gets used is a lie in the schema. The worker
# thread cannot be killed — what is given up is the waiting, and the session's
# namespace is then dropped mid-way instead of silently left half-full.
_DEFAULT_EXEC_BUDGET_S = 120.0
_MIN_EXEC_BUDGET_S = 1.0
_MAX_EXEC_BUDGET_S = 300.0


def budget_seconds(timeout_s: object) -> float:
    """The declared budget inside a usable range — 0 or nonsense does not cap it."""
    try:
        value = float(timeout_s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _DEFAULT_EXEC_BUDGET_S
    if value != value or value in (float("inf"), float("-inf")):
        return _DEFAULT_EXEC_BUDGET_S
    return max(_MIN_EXEC_BUDGET_S, min(_MAX_EXEC_BUDGET_S, value))


async def browser_exec(code: str, session: str = "default", timeout_s: int = 120) -> str:
    """Runs Python with preimported browser helpers (session-isolated).

    Args:
        code: Python source; the helpers (new_tab, js, click_at_xy, …) are
            already in the namespace — no own import needed.
        session: isolates the page context (parallel sub-agents each use
            their own name; empty = shared default).
        timeout_s: wall-clock budget for this block (1-300s). If the code runs
            longer, the answer comes with the stdout captured up to that point — the
            thread keeps running, the session is reset.

    Returns:
        Captured stdout output, plus a traceback on error.
    """
    import io
    import traceback
    from contextlib import redirect_stdout

    ns = _BROWSER_KERNELS.get(session)
    if ns is None:
        from core.browser import make_browser_helpers
        ns = dict(make_browser_helpers(session))
        ns["__name__"] = "__ephe_browser_exec__"
        _BROWSER_KERNELS[session] = ns

    if not (code or "").strip():
        return "[browser_exec] leerer Code-Block"

    global _BROWSER_EXEC_COUNT
    _BROWSER_EXEC_COUNT += 1
    try:
        compiled = compile(code, f"<ephe-browser-{_BROWSER_EXEC_COUNT}>", "exec")
    except SyntaxError as exc:
        line, offset = exc.lineno or 0, exc.offset or 0
        return f"[browser_exec] SyntaxError (Zeile {line}, Spalte {offset}): {exc.msg}"

    def _run_in_worker(buf: "io.StringIO") -> str:
        from core.browser import BrowserUnavailable

        try:
            with redirect_stdout(buf):
                exec(compiled, ns)  # noqa: S102 — deliberate kernel exec
        except BrowserUnavailable as exc:
            # Chromium is a separate download (core/browser.py:31) and a missing one is
            # a supported state: the answer names the next step instead of the eight
            # frames that led here, which is what the model got before.
            partial = buf.getvalue()
            return (partial + "\n" if partial else "") + f"[browser_exec] {exc}"
        except Exception:
            err = "".join(traceback.format_exc(limit=8)).strip()
            partial = buf.getvalue()
            return (partial + "\n" if partial else "") + f"[browser_exec] {err}"
        return buf.getvalue()

    import asyncio as _aio

    buffer = io.StringIO()
    budget = budget_seconds(timeout_s)
    try:
        out = await _aio.wait_for(_aio.to_thread(_run_in_worker, buffer), timeout=budget)
    except _aio.TimeoutError:
        # The namespace was written into mid-way — better gone than half-full.
        _BROWSER_KERNELS.pop(session, None)
        partial = buffer.getvalue()
        return (partial + "\n" if partial else "") + (
            f"[browser_exec] Zeitbudget von {budget:.0f}s überschritten. Der Block läuft im "
            "Worker-Thread weiter und die Session ist zurückgesetzt — Variablen aus diesem "
            "Block sind nicht mehr da. Nicht blind wiederholen: in kleinere Blöcke teilen."
        )
    if len(out) > _MAX_BROWSER_STDOUT:
        out = out[:_MAX_BROWSER_STDOUT] + f"\n…[stdout gekappt bei {_MAX_BROWSER_STDOUT} Zeichen]"
    return out if out.strip() else "[browser_exec] ausgefuehrt (keine Ausgabe)"
