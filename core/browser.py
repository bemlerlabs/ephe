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

from core.browser_url import (
    PERSISTENT_PROFILE_UNWIRED,
    browser_profile_settings,
    navigation_guard,
    url_policy,
)
from core.tool_markers import BROWSER_DENIED_MARKER
from core.vision import _get_bounding_box
from core.engine_config import config_root

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


#: The step-evidence contract, in one line at the head of every browser action's
#: answer: what the environment said after the action, and whether that says the
#: action did anything at all.
#:
#: Until now a step's result was the agent's own account of it ("Click executed
#: successfully."), which is the same kind of claim as a model saying a test passed
#: without running it. The watchable run needs the environment's side: the address it
#: is on, the title it carries, and how the document differs from the one seen before
#: this step. A step whose effect cannot be observed comes back `unproven`, and that
#: word is the point — an unobservable action is not a successful one.
#:
#: `verdict` is the key the surface renders: "observed" | "unproven". It rides the
#: answer text, so it reaches the tool card and the `tool_exec` audit row's `detail`
#: without a second channel. The line stays short on purpose: the audit truncates at
#: 300 characters, so evidence has to be worth its bytes.
STEP_EVIDENCE_PREFIX = "STEP_EVIDENCE:"

#: The cheap read the environment is asked for after each action. One call, no model
#: in the loop: address, title and a DOM signature, all computed in the page.
#: `textContent` rather than the rendered-text variant, because the latter forces a
#: layout pass on every step for information a length comparison does not need.
_OBSERVE_JS = (
    "() => ({"
    "url: location.href,"
    "title: document.title,"
    "nodes: document.getElementsByTagName('*').length,"
    "text_len: document.body ? document.body.textContent.length : 0,"
    "scroll_y: Math.round(window.scrollY),"
    "active: document.activeElement ? document.activeElement.tagName : '',"
    "checked: document.querySelectorAll('input:checked, [aria-checked=\"true\"]').length"
    "})"
)

#: The signature fields a delta is computed from. A url or title move is its own
#: evidence, so it is reported beside them rather than folded into them.
_OBSERVE_FIELDS = ("nodes", "text_len", "scroll_y", "checked")

#: The two free-text fields are the only ones that can grow past what the trail keeps, so
#: they are what the line is squeezed by. The cap is imported rather than copied: the audit
#: truncates `detail` at its own limit, and a line cut mid-JSON says nothing to a reader.
#: 2 fps on an 800x500 q50 jpeg: ~20 KB a frame on loopback, measured at 0.043 ms of
#: event-loop time each. Higher rates cost CPU for pixels nobody in a side pane can read.
_WATCH_MIN_INTERVAL = 0.5
_WATCH_WIDTH = 800
_WATCH_HEIGHT = 500
_WATCH_QUALITY = 50

_EVIDENCE_URL_LIMIT = 96
_EVIDENCE_TITLE_LIMIT = 64


def _short(value: object, limit: int) -> str:
    """A field the evidence line may carry, cut to the width it is allowed to have."""
    return str(value if value is not None else "")[:limit]


def _observation_delta(before: dict, after: dict) -> dict:
    """What the document changed by, as the small numbers that say so."""
    delta: dict[str, int] = {}
    for field in _OBSERVE_FIELDS:
        try:
            delta[field] = int(after[field]) - int(before[field])
        except (KeyError, TypeError, ValueError):
            delta[field] = 0
    if str(before.get("url") or "") != str(after.get("url") or ""):
        delta["url_changed"] = 1
    if str(before.get("title") or "") != str(after.get("title") or ""):
        delta["title_changed"] = 1
    if str(before.get("active") or "") != str(after.get("active") or ""):
        delta["active_changed"] = 1
    return delta


def step_evidence(
    name: str,
    before: dict | None,
    after: dict | None,
    *,
    error: str = "",
) -> str:
    """The `STEP_EVIDENCE:` line for one finished action. Pure, so it can be tested sealed.

    Three answers, and only one of them is `observed`:
      - the page did not answer → unproven, because nothing here was measured;
      - there was nothing read before the action → unproven, because a signature
        on its own carries no change, whatever it looks like;
      - the signature moved → observed, with the numbers that moved.
    """
    if error or not isinstance(after, dict):
        verdict, reason = "unproven", error or "the page returned nothing readable"
        delta: dict[str, int] = {}
    elif not isinstance(before, dict) or not before:
        verdict, reason = "unproven", "no state was read before the action"
        delta = {}
    else:
        delta = _observation_delta(before, after)
        moved = any(value for value in delta.values())
        verdict = "observed" if moved else "unproven"
        reason = "" if moved else "nothing observable changed"

    payload = {
        "step": name,
        "verdict": verdict,
        "url": (_short(after.get("url"), _EVIDENCE_URL_LIMIT) if isinstance(after, dict) else ""),
        "title": (_short(after.get("title"), _EVIDENCE_TITLE_LIMIT) if isinstance(after, dict) else ""),
        "delta": delta,
    }
    if reason:
        payload["reason"] = reason
    body = _fit(payload)
    return f"{STEP_EVIDENCE_PREFIX}{body}"


def _fit(payload: dict) -> str:
    """The payload as one JSON line that survives the audit's own detail cap."""
    from core.audit_log import DETAIL_MAX_CHARS

    overhead = len(STEP_EVIDENCE_PREFIX)
    title_limit = url_limit = None
    for _ in range(3):
        body = _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(body) + overhead <= DETAIL_MAX_CHARS:
            return body
        # Squeeze the free text first, then drop the reason: a line that says what moved is
        # worth more than one that explains itself at the cost of arriving torn.
        if title_limit is None:
            title_limit = url_limit = 24
        elif url_limit > 24:
            title_limit = url_limit = 16
        else:
            payload.pop("reason", None)
        payload["url"] = str(payload.get("url", ""))[:url_limit]
        payload["title"] = str(payload.get("title", ""))[:title_limit]
    return _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[: DETAIL_MAX_CHARS - overhead]


def _page_capture_scope(page: Page) -> str:
    """The scope line a frame of this page carries: what part of the screen it shows.

    `viewport_size` is read off the page object, so stating the scope adds no
    round trip to the capture; a page that reports no viewport still says what it
    is — the rendered page, and nothing of the desktop around it.
    """
    try:
        size = page.viewport_size or {}
    except Exception:  # noqa: BLE001 — a scope line never cancels a capture
        size = {}
    width, height = size.get("width"), size.get("height")
    if width and height:
        return f"page viewport {width}x{height}"
    return "page viewport (size unread)"


async def _launch_chromium(pw: Playwright) -> Browser:
    """Start the headless browser, or say what to install.

    Without this the missing binary escaped as Playwright's own Error, the tool
    wrapper turned it into an 8-frame traceback, and both the model and the user got
    stack output where a next step belonged (observed on every CI leg: the shipped
    `browser_exec` core tool is always active, CI simply has no browser).

    The profile setting is read here and not at some later point: a configured
    profile directory is a thing this build refuses to start (see
    `core.browser_url.PERSISTENT_PROFILE_UNWIRED`), so the launch and the approval
    gate cannot disagree about whether the session holds credentials.
    """
    profile = browser_profile_settings()
    if profile["user_data_dir"]:
        raise BrowserUnavailable(PERSISTENT_PROFILE_UNWIRED)
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
        # session_id → the scope of the last frame taken from it, for the tool card.
        self._capture_scopes: dict[str, str] = {}
        # session_id → the last page signature. It is the baseline the next step's
        # delta is measured against, which is why one observation per action is
        # enough: the answer of this step is the starting point of the next one.
        self._observations: dict[str, dict] = {}
        # session_id -> the live cast, so a second watcher shares one engine stream.
        self._watched: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def _guard_route(self, route) -> None:
        """The address gate for every request this context makes.

        `go()` refuses before the page is asked for; a redirect and a sub-resource
        are requests the first answer says nothing about, and the browser resolves
        each on its own. So each one goes through `navigation_guard` here.
        """
        url = str(getattr(getattr(route, "request", None), "url", "") or "")
        scheme = url.split("://", 1)[0].lower() if "://" in url else ""
        try:
            if scheme in ("http", "https"):
                allowed, _decision = await navigation_guard(url)
                if not allowed:
                    await route.abort()
                    return
            # In-memory schemes (about:, data:, blob:) are not network reach;
            # `go()` has already answered what a page may be opened from.
            await route.continue_()
        except Exception:  # noqa: BLE001 — a request already handled is not a second one
            pass

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
            # The profile setting is applied here, not somewhere later: today both keys
            # are empty and a session is born knowing nothing. When the persistence
            # programme stores a sign-in, it lands in every session context this
            # manager hands out — which is exactly the moment
            # `browser_session_is_credentialed()` stops the browser cluster from
            # running without a dialog (core/tools/approval_rules.py).
            profile = browser_profile_settings()
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                **({"storage_state": profile["storage_state"]} if profile["storage_state"] else {}),
            )
            # SEC-5: the policy that said yes to the address is not enough on a page
            # that redirects or loads a sub-resource from somewhere else. The context
            # carries the guard, so pages opened later in this session inherit it.
            await context.route("**/*", self._guard_route)
            page = await context.new_page()
            self._pages[session] = (context, page)
            return page

    # Step evidence: what the environment said after the action

    async def _observe(self, session: str) -> dict | None:
        """One round trip into the page for its own account of how it looks now.

        None when the page did not answer, which is a finding and not a crash: the
        caller reports the step as unproven instead of inventing a verdict.
        """
        try:
            page = await self._ensure_page(session)
            seen = await page.evaluate(_OBSERVE_JS)
        except Exception:  # noqa: BLE001 — an unreadable page is an unproven step
            return None
        return seen if isinstance(seen, dict) else None

    async def _observe_step(self, session: str) -> tuple[dict | None, dict | None]:
        """(what was known before this action, what the page says now).

        The "before" is the signature this manager last read for this session — the
        post-action observation of the previous step, or the pre-navigation one `go`
        takes when a session has no history yet. That reuse is what keeps the cost at
        one extra round trip per action rather than two.
        """
        before = self._observations.get(session)
        after = await self._observe(session)
        if after is not None:
            self._observations[session] = after
        return before, after

    async def _baseline_or_none(self, session: str) -> dict | None:
        """Read the page once when this session has no signature yet, else reuse it.

        The read is stored under the session, because it is the thing the next
        observation is compared against: a baseline that is taken and dropped turns the
        first action of every session into an unverifiable one.
        """
        existing = self._observations.get(session)
        if existing is not None:
            return existing
        seen = await self._observe(session)
        if seen is not None:
            self._observations[session] = seen
        return seen

    async def _evidence(self, name: str, session: str) -> str:
        """The STEP_EVIDENCE line for an action that has just finished."""
        before, after = await self._observe_step(session)
        return step_evidence(name, before, after)

    # Core operations (use the active session)

    async def _user_hold(self, session: str) -> str | None:
        """A sentence when the user is holding the page. None when the agent may act."""
        from core.browser_run_view import gate_action

        return await gate_action(session)

    async def go(self, url: str, session: str = "default") -> str:
        held = await self._user_hold(session)
        if held:
            return held
        allowed, decision = url_policy(url)
        if not allowed:
            line = f"{BROWSER_DENIED_MARKER} {decision}"
            code = getattr(decision, "code", "")
            if code:
                from core.reason import Reason

                return Reason(line, code, dict(getattr(decision, "params", {}) or {}))
            return line
        page = await self._ensure_page(session)
        # Where the session was before the navigation, if that was ever read. Without
        # it there is nothing to compare the arrived page against, and the honest
        # answer about a first navigation is the address the page reports itself at.
        await self._baseline_or_none(session)
        try:
            await page.goto(decision, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)  # Render buffer
        except Exception as e:
            return f"Error loading {decision}: {e}"
        text = await self.get_text(session)
        evidence = await self._evidence("browser_go", session)
        return f"{evidence}\n\n{text}"

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
        self._capture_scopes[session] = _page_capture_scope(page)
        return base64.b64encode(img_bytes).decode("utf-8")

    def capture_scope(self, session: str = "default") -> str:
        """What the last frame of this session actually shows, for the tool card.

        A page viewport and the whole screen are two different scopes, and the answer
        a user reads has to say which one was taken (`core/tools/system_tools.py`
        states the screen half the same way). Read off the page object, so naming the
        scope costs no round trip.
        """
        return self._capture_scopes.get(session) or "page viewport (size unread)"

    async def click(self, target_description: str, session: str = "default") -> str:
        held = await self._user_hold(session)
        if held:
            return held
        page = await self._ensure_page(session)
        await self._baseline_or_none(session)
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
        return f"{await self._evidence('browser_click', session)}\nClick executed."

    async def type_text(self, text: str, session: str = "default") -> str:
        held = await self._user_hold(session)
        if held:
            return held
        page = await self._ensure_page(session)
        await self._baseline_or_none(session)
        await page.keyboard.type(text, delay=20)
        await asyncio.sleep(1)
        return f"{await self._evidence('browser_type', session)}\nText typed."

    async def press(self, key: str, session: str = "default") -> str:
        held = await self._user_hold(session)
        if held:
            return held
        page = await self._ensure_page(session)
        await self._baseline_or_none(session)
        await page.keyboard.press(key)
        await asyncio.sleep(1)
        return f"{await self._evidence('browser_press', session)}\nKey pressed."

    async def scroll(self, direction: str = "down", amount: int = 600, session: str = "default") -> str:
        held = await self._user_hold(session)
        if held:
            return held
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
        held = await self._user_hold(session)
        if held:
            return held
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
        held = await self._user_hold(session)
        if held:
            return held
        page = await self._ensure_page(session)
        try:
            await page.fill(selector, str(text or ""), timeout=10000)
        except Exception as exc:
            return f"[fill failed: {exc}]"
        return f"filled {selector}"

    async def click_at_xy(self, x: int, y: int, session: str = "default") -> str:
        held = await self._user_hold(session)
        if held:
            return held
        page = await self._ensure_page(session)
        await self._baseline_or_none(session)
        await page.mouse.move(int(x), int(y))
        await page.mouse.click(int(x), int(y))
        await asyncio.sleep(1)
        return f"{await self._evidence('browser_click_xy', session)}\nclicked at {int(x)},{int(y)}"

    async def capture_screenshot(self, session: str = "default") -> str:
        """Saves the screenshot as a file and returns the path."""
        import os
        import time
        b64 = await self.screenshot(session)
        image_dir = Path(os.environ.get("EPHE_IMAGE_DIR") or config_root() / "sessions" / "images")
        image_dir.mkdir(parents=True, exist_ok=True)
        filename = f"browser_{int(time.time())}.jpeg"
        target = image_dir / filename
        with open(target, "wb") as f:
            f.write(base64.b64decode(b64))
        return str(target)

    # Watching: the page's own frames, on the page's own session

    async def start_watch(self, session: str = "default") -> str:
        """Begin casting this session's page. Returns "" or the reason it cannot.

        The frame source is CDP `Page.startScreencast` on a **page-level** session: the
        context-level session the `cdp` helper below uses answers
        `'Page.startScreencast' wasn't found`, which reads like a missing protocol feature
        and is a wiring mistake. A cast that cannot start is reported, never guessed at —
        a pane that shows nothing because nothing arrived is indistinguishable from a page
        that has not changed, and only one of those is a fault.
        """
        from core import browser_frames

        if self._watched.get(session) is not None:
            return ""
        try:
            page = await self._ensure_page(session)
            cdp = await page.context.new_cdp_session(page)
            bus = browser_frames.bus_for(session)
            await cdp.send(
                "Page.startScreencast",
                {
                    "format": "jpeg",
                    "quality": _WATCH_QUALITY,
                    "maxWidth": _WATCH_WIDTH,
                    "maxHeight": _WATCH_HEIGHT,
                    "everyNthFrame": 1,
                },
            )
        except Exception as exc:  # noqa: BLE001 — an engine that will not cast is a fact
            return f"watch_unavailable: {type(exc).__name__}"

        state = {"cdp": cdp, "last": 0.0}
        self._watched[session] = state

        def note(frame) -> str:
            """Ack immediately, publish at most every _WATCH_MIN_INTERVAL seconds.

            Frames arrive damage-driven — an animating page ran 93 fps in measurement while
            a still one produced about one every two seconds — so the pacing has to be ours.
            Acking on the reader's clock is not the answer: the protocol window is three
            un-acked frames, so a slow tab would stall the page rather than drop its own
            backlog. Dropping here costs a viewer an intermediate frame and costs the run
            nothing.
            """
            import time as _time

            now = _time.monotonic()
            if now - state["last"] < _WATCH_MIN_INTERVAL:
                # Publish nothing on a skip. Writing an empty placeholder would evict the
                # real frame a one-slot reader had not read yet, so the pacing meant to
                # protect a slow reader would instead be what hides the page from it.
                return ""
            state["last"] = now
            meta = frame.get("metadata") or {}
            from core.browser_run_view import frame_audit

            bus.publish(
                {
                    "jpeg": str(frame.get("data") or ""),
                    **frame_audit(session),
                    # measured key names: the protocol says deviceWidth/deviceHeight, and
                    # a pane sized from a guessed "width" gets None and draws nothing
                    # Two different spaces, and the overlay in #88 has to know both: the
                    # protocol's deviceWidth/deviceHeight is the page's own viewport, while
                    # the jpeg we get back is scaled to the maxWidth/maxHeight requested
                    # below. Drawing a click ring straight onto the image at page
                    # coordinates puts it off by exactly that ratio.
                    "viewport_width": meta.get("deviceWidth"),
                    "viewport_height": meta.get("deviceHeight"),
                    "cast_width": _WATCH_WIDTH,
                    "cast_height": _WATCH_HEIGHT,
                    "scroll": meta.get("scrollOffsetY") or 0,
                    "scale": meta.get("pageScaleFactor") or 1,
                    "page_top": meta.get("offsetTop") or 0,
                }
            )
            return ""

        # Playwright's event callback is synchronous: an `async def` handler here is
        # constructed and never awaited, the cast silently produces nothing, and
        # `start_watch` still reports success. The ack is therefore scheduled onto the loop.
        def on_frame(frame) -> None:
            note(frame)
            try:
                asyncio.ensure_future(
                    cdp.send(
                        "Page.screencastFrameAck",
                        {"sessionId": (frame or {}).get("sessionId")},
                    )
                )
            except RuntimeError:  # no loop left: the session is closing
                pass

        cdp.on("Page.screencastFrame", on_frame)
        return ""

    async def stop_watch(self, session: str = "default") -> None:
        state = self._watched.pop(session, None)
        if state is None:
            return
        try:
            await state["cdp"].send("Page.stopScreencast")
        except Exception:  # noqa: BLE001 — nothing is left to clean up if the page is gone
            pass

    async def read_signature(self, session: str) -> dict | None:
        """The page as it stands, for the moment the user takes it. No new session."""
        if not self.has_session(session):
            return None
        return await self._observe(session)

    async def reconcile_hold(self, session: str, before: dict | None) -> str:
        """What the page changed by while the user held it. The baseline moves with them."""
        after = await self._observe(session) if self.has_session(session) else None
        if isinstance(after, dict):
            self._observations[session] = after
        return step_evidence("user_hold", before if isinstance(before, dict) else None, after)

    async def apply_user_act(self, session: str, act: dict) -> None:
        """One click, type, or key from the person holding the page.

        The agent path stays gated. This method is the user's hand, so it does
        not consult the hold.
        """
        if not self.has_session(session):
            raise LookupError(session)
        page = await self._ensure_page(session)
        kind = act.get("kind")
        if kind == "click":
            box = page.viewport_size or {"width": 1280, "height": 800}
            width = int(box.get("width") or 0)
            height = int(box.get("height") or 0)
            x = int(act["x"])
            y = int(act["y"])
            if width <= 0 or height <= 0 or x < 0 or y < 0 or x >= width or y >= height:
                raise ValueError("outside")
            await page.mouse.click(x, y)
            return
        if kind == "type":
            await page.keyboard.type(str(act.get("text") or ""))
            return
        if kind == "press":
            await page.keyboard.press(str(act.get("key") or ""))
            return
        raise ValueError("act")

    def has_session(self, session: str = "default") -> bool:
        """Whether this session already exists, without creating it.

        The watch route asks this before it casts anything: a name from the URL is not a
        reason to start a browser context.
        """
        return session in self._pages or session == "default" and self._page is not None

    def is_watched(self, session: str = "default") -> bool:
        return session in self._watched

    async def cdp(self, method: str, session: str = "default", **params) -> str:
        """Raw CDP call on the active session page."""
        held = await self._user_hold(session)
        if held:
            return held
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
