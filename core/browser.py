"""core/browser.py — Playwright headless browser agent (session-keyed).

One manager carries its own page context per session, so parallel
sessions (main chat, sub-agents) do not write into the same page.
The module functions (go/get_text/…) use the active session; the
helper factory ``make_browser_helpers`` returns the pre-imported
namespace for ``browser_exec``.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import json as _json
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, Playwright

from core.browser_url import url_policy
from core.tool_markers import BROWSER_DENIED_MARKER
from core.vision import _get_bounding_box

# One long-lived event loop per session (in a dedicated thread), so
# Playwright objects stay bound to the same loop throughout.
_SESSION_LOOPS: dict[str, asyncio.AbstractEventLoop] = {}

# Playwright ships as a Python dependency; the BROWSER binary never does. Every
# `playwright install` is a deliberate, sized download, so an install without it is a
# supported state — and must read as one. See _launch_chromium().
BROWSER_INSTALL_HINT = (
    "Chromium is not installed for Playwright — the browser tool needs its own "
    "download. Run: python -m playwright install chromium "
    "(on Linux: add --with-deps for the system libraries)"
)


class BrowserUnavailable(RuntimeError):
    """The browser cannot start: one actionable line instead of a traceback."""


async def _launch_chromium(pw: Playwright) -> Browser:
    """Start the headless Chromium, or say what to install.

    Without this the missing binary escaped as Playwright's own Error, the tool
    wrapper turned it into an 8-frame traceback, and both the model and the user got
    stack output where a next step belonged (observed on every CI leg: the shipped
    `browser_exec` core tool is always active, CI simply has no browser).
    """
    try:
        return await pw.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001 — re-raised as one actionable error below
        text = str(exc)
        if "Executable doesn't exist" in text or "playwright install" in text:
            raise BrowserUnavailable(BROWSER_INSTALL_HINT) from exc
        raise


def _get_or_create_loop(session: str) -> asyncio.AbstractEventLoop:
    loop = _SESSION_LOOPS.get(session)
    if loop is not None and not loop.is_closed():
        return loop
    loop = asyncio.new_event_loop()
    _SESSION_LOOPS[session] = loop
    return loop


class PlaywrightBrowserManager:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        # Directly injected page (hermetic tests) — otherwise None.
        self._page: Page | None = None
        # session_id → (context, page). One own context per session.
        self._pages: dict[str, tuple] = {}
        self._lock = asyncio.Lock()

    async def _ensure_page(self, session: str = "default") -> Page:
        # A directly set page (hermetic tests inject _page) takes precedence.
        if self._page is not None:
            return self._page
        async with self._lock:
            if self._page is not None:
                return self._page
            if not self._playwright:
                self._playwright = await async_playwright().start()
            if not self._browser:
                self._browser = await _launch_chromium(self._playwright)
            existing = self._pages.get(session)
            if existing is not None:
                return existing[1]
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            self._pages[session] = (context, page)
            return page

    # Core operations (use the active session)

    async def go(self, url: str, session: str = "default") -> str:
        allowed, decision = url_policy(url)
        if not allowed:
            line = f"{BROWSER_DENIED_MARKER} {decision}"
            code = getattr(decision, "code", "")
            if code:
                from core.reason import Reason

                return Reason(line, code, dict(getattr(decision, "params", {}) or {}))
            return line
        page = await self._ensure_page(session)
        try:
            await page.goto(decision, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)  # Render buffer
        except Exception as e:
            return f"Error loading {decision}: {e}"
        return await self.get_text(session)

    async def get_text(self, session: str = "default") -> str:
        page = await self._ensure_page(session)
        try:
            text = await page.evaluate("document.body.innerText")
            if not text:
                return "No visible text."
            if len(text) > 15000:
                text = text[:15000] + "\n\n... [page text truncated to 15,000 characters]"
            return text
        except Exception as e:
            return f"Could not read text: {e}"

    async def screenshot(self, session: str = "default") -> str:
        page = await self._ensure_page(session)
        img_bytes = await page.screenshot(type="jpeg", quality=80)
        return base64.b64encode(img_bytes).decode("utf-8")

    async def click(self, target_description: str, session: str = "default") -> str:
        page = await self._ensure_page(session)
        b64_img = await self.screenshot(session)
        coords = await _get_bounding_box(b64_img, target_description)
        if not coords or coords == "UNSURE":
            return f"Error: target '{target_description}' not found on the browser screen."
        y_min, x_min, y_max, x_max = coords
        center_y_norm = y_min + (y_max - y_min) / 2
        center_x_norm = x_min + (x_max - x_min) / 2
        viewport = page.viewport_size
        width = viewport["width"] if viewport else 1280
        height = viewport["height"] if viewport else 800
        abs_x = center_x_norm * width
        abs_y = center_y_norm * height
        await page.mouse.move(abs_x, abs_y)
        await page.mouse.click(abs_x, abs_y)
        await asyncio.sleep(2)
        return "Click executed successfully."

    async def type_text(self, text: str, session: str = "default") -> str:
        page = await self._ensure_page(session)
        await page.keyboard.type(text, delay=20)
        await asyncio.sleep(1)
        return f"Text '{text}' eingetippt."

    async def press(self, key: str, session: str = "default") -> str:
        page = await self._ensure_page(session)
        await page.keyboard.press(key)
        await asyncio.sleep(1)
        return f"Taste '{key}' pressed."

    async def scroll(self, direction: str = "down", amount: int = 600, session: str = "default") -> str:
        page = await self._ensure_page(session)
        amt = max(1, min(int(amount or 600), 10000))
        dx, dy = 0, amt
        d = (direction or "down").lower()
        if d == "up":
            dy = -amt
        elif d == "left":
            dx, dy = -amt, 0
        elif d == "right":
            dx, dy = amt, 0
        try:
            y = await page.evaluate(
                "([x, y]) => { window.scrollBy(x, y); return Math.round(window.scrollY); }",
                [dx, dy],
            )
        except Exception as exc:
            return f"[Scroll failed: {exc}]"
        return f"Scrolled {d} {amt}px — scrollY now {y}."

    async def evaluate(self, js: str, session: str = "default") -> str:
        page = await self._ensure_page(session)
        code = (js or "").strip()[:4000]
        if not code:
            return "[Evaluate failed: empty expression]"
        try:
            result = await page.evaluate(code)
        except Exception as exc:
            return f"[Evaluate failed: {exc}]"
        try:
            text = _json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(result)
        if len(text) > 12000:
            text = text[:12000] + "\n... [truncated to 12,000 characters]"
        return text

    async def clipboard_read(self, session: str = "default") -> str:
        page = await self._ensure_page(session)
        try:
            text = await page.evaluate("navigator.clipboard.readText()")
        except Exception as exc:
            return f"[Clipboard read failed: {exc}]"
        return str(text or "")

    async def clipboard_write(self, text: str, session: str = "default") -> str:
        page = await self._ensure_page(session)
        try:
            await page.evaluate("(t) => navigator.clipboard.writeText(t)", str(text or ""))
        except Exception as exc:
            return f"[Clipboard write failed: {exc}]"
        return "Clipboard updated."

    async def display_info(self, session: str = "default") -> str:
        page = await self._ensure_page(session)
        try:
            info = await page.evaluate(
                "() => ({ viewport_width: window.innerWidth, viewport_height: window.innerHeight,"
                " device_pixel_ratio: window.devicePixelRatio,"
                " scroll_height: document.body ? document.body.scrollHeight : 0 })"
            )
        except Exception as exc:
            return f"[Display info failed: {exc}]"
        if not isinstance(info, dict):
            return f"[Display info failed: unexpected {info!r}]"
        return (
            f"viewport {info.get('viewport_width')}x{info.get('viewport_height')}, "
            f"dpr {info.get('device_pixel_ratio')}, "
            f"scroll_height {info.get('scroll_height')}"
        )

    # browser_exec helpers (one Python namespace per call)

    async def new_tab(self, url: str, session: str = "default") -> str:
        """Opens/navigates in the session page (first navigation = new tab)."""
        return await self.go(url, session)

    async def goto_url(self, url: str, session: str = "default") -> str:
        """Navigates the current session page to a URL."""
        return await self.go(url, session)

    async def wait_for_load(self, session: str = "default") -> str:
        page = await self._ensure_page(session)
        try:
            await page.wait_for_load_state(state="networkidle", timeout=15000)
        except Exception:
            pass  # networkidle is best-effort; the DOM is already there
        return "load settled"

    async def page_info(self, session: str = "default") -> dict:
        """Compact summary of the active page (title/url/start of text)."""
        page = await self._ensure_page(session)
        try:
            info = await page.evaluate(
                "() => ({ title: document.title,"
                " url: location.href,"
                " text: (document.body ? document.body.innerText.slice(0, 600) : '') })"
            )
        except Exception as exc:
            return {"error": str(exc)}
        return info if isinstance(info, dict) else {"raw": str(info)}

    async def js(self, expr: str, session: str = "default") -> str:
        return await self.evaluate(expr, session)

    async def fill_input(self, selector: str, text: str, session: str = "default") -> str:
        page = await self._ensure_page(session)
        try:
            await page.fill(selector, str(text or ""), timeout=10000)
        except Exception as exc:
            return f"[fill failed: {exc}]"
        return f"filled {selector}"

    async def click_at_xy(self, x: int, y: int, session: str = "default") -> str:
        page = await self._ensure_page(session)
        await page.mouse.move(int(x), int(y))
        await page.mouse.click(int(x), int(y))
        await asyncio.sleep(1)
        return f"clicked at {int(x)},{int(y)}"

    async def capture_screenshot(self, session: str = "default") -> str:
        """Saves the screenshot as a file and returns the path."""
        import os
        import time
        b64 = await self.screenshot(session)
        image_dir = Path(os.environ.get("EPHE_IMAGE_DIR", str(Path.home() / ".ephe" / "sessions" / "images")))
        image_dir.mkdir(parents=True, exist_ok=True)
        filename = f"browser_{int(time.time())}.jpeg"
        target = image_dir / filename
        with open(target, "wb") as f:
            f.write(base64.b64decode(b64))
        return str(target)

    async def cdp(self, method: str, session: str = "default", **params) -> str:
        """Raw CDP call on the active session page."""
        page = await self._ensure_page(session)
        try:
            cdp_session = await page.context.new_cdp_session()
            result = await cdp_session.send(method, params or None)
            return _json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return f"[cdp failed: {exc}]"


# Singleton Instance
browser_manager = PlaywrightBrowserManager()


def make_browser_helpers(session: str = "default") -> dict:
    """Pre-imported helper namespace for ``browser_exec``.

    A single, long-lived event loop per session (in a dedicated
    thread) carries all coros — so the Playwright objects stay bound to
    the same loop throughout (no cross-loop error between calls).
    """
    loop = _get_or_create_loop(session)
    mgr = browser_manager

    def _sync(fn):
        def wrapper(*args, **kwargs):
            coro = fn(*args, **kwargs)
            if not inspect.iscoroutine(coro):
                return coro
            return loop.run_until_complete(coro)
        return wrapper

    def _with_session(fn):
        def factory(*args, **kwargs):
            kwargs.setdefault("session", session)
            return _sync(fn)(*args, **kwargs)
        return factory

    return {
        "new_tab": _with_session(mgr.new_tab),
        "goto_url": _with_session(mgr.goto_url),
        "wait_for_load": _with_session(mgr.wait_for_load),
        "page_info": _with_session(mgr.page_info),
        "js": _with_session(mgr.js),
        "fill_input": _with_session(mgr.fill_input),
        "click_at_xy": _with_session(mgr.click_at_xy),
        "capture_screenshot": _with_session(mgr.capture_screenshot),
        "cdp": _with_session(mgr.cdp),
        "browser_manager": mgr,
    }
