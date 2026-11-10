"""Ephe · Creator — the browser end-state checks of the creation eval set (task #51c).
evals/creation_checks_browser.py

Three of the nine end states in `evals.creation_eval.CHECKS` are promises about a
running server and a document engine, so they are read from one:

  * `mounts` — the mount URL answers 200 and the document holds something.
  * `no_console_errors` — loading it leaves no uncaught exception, no failed resource
    and no `console.error` behind.
  * `survives_reload` — a second navigation of the same URL answers the same two ways.

The module is two layers on purpose. `Load` is evidence one navigation produced, and the
three verdict builders are pure functions over it, so every rule can be shown to say no
without an engine. `SurfaceSession` is the collector: it boots the real app on a loopback
port in the process, mints the per-mount nonce the product mints, installs nothing (a
bundle reaches the mount through `core.tools.creator_tools.install_plugin_bundle`, the
one path a directory takes to becoming loadable) and drives a real engine at the mount
URL. An engine that cannot boot raises, and the caller names it in a skip.

What the content rule is: a non-whitespace character count from the rendered body, or a
`canvas`/`svg`/`img`/`video` with a box wider and taller than nothing. The box half is
what lets a game or a 3D scene be graded at all, since neither has text. What the rule is
not: a statement that the widget does what its case asked. That is task #31's question.

Errors arrive through two channels, unioned. `page.on(...)` sees the top frame's
exceptions and console errors; the page hook installed at document start also sees the
resource loads that fail and anything thrown before the listener attaches. A load whose
error channels were both dead reports `measured=False`, and the console row fails on
that — a green row nobody watched is the defect class this set exists to prevent.

The frame is the product's own: the mount header carries a `sandbox` directive without
`allow-same-origin`, so the document runs with an opaque origin and its reads of the
user's authority are refused. `tests/test_plugin_surface_isolation_browser.py:1` measured
that confinement; nothing here repeats it, and nothing here depends on it.

A document written against the Storage API is one row of that same measurement now: the
mount injects its page-storage shim (`sdk/ephe-storage.js`) ahead of the bundle's first
script, so `localStorage` answers and neither error channel sees the `SecurityError` that
failed `creation-05`. The session navigates the mount at the top level, where
`window.parent` is the page itself and no embedding host exists, so a shim write is
answered with `storage_no_host` and does not land; these two rows witness that the
refusal is gone, not that the value reached the state root. The landing is measured in
the product's frame by `tests/test_plugin_surface_storage_shim_browser.py`, and the
eval's own persistence witness stays `state_bridge_used`.
"""
from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.creation_checks import BROWSER_CHECKS, Verdict

#: The rows this module answers, in the order the set lists them.
BROWSER_CHECK_NAMES: tuple[str, ...] = BROWSER_CHECKS

#: A document below this many non-whitespace characters holds nothing a person can read.
MIN_TEXT_CHARS = 1

#: How many errors a failure detail quotes before it shortens to a count.
LISTED_ERRORS = 3

#: How long one navigation is watched before the answer is called empty.
SETTLE_TIMEOUT = 8.0

POLL_INTERVAL = 0.1

#: How long the server is given to bind its port.
START_TIMEOUT = 20.0

#: The elements whose drawn box counts as content.
GRAPHIC_SELECTOR = "canvas, svg, img, video"


@dataclass(frozen=True)
class Load:
    """One navigation of one mount, as the engine reported it."""

    status: int = 0
    ready: str = ""
    text: int = 0
    graphics: int = 0
    errors: tuple[str, ...] = ()

    #: Whether at least one error channel was live while this load happened.
    measured: bool = True

    @property
    def holds_content(self) -> bool:
        return self.text >= MIN_TEXT_CHARS or self.graphics >= 1

    @property
    def content(self) -> str:
        return f"{self.text} non-whitespace character(s) and {self.graphics} graphic box(es)"


def mounts_verdict(plugin: str, load: Load) -> Verdict:
    """`mounts`: the URL answered and something arrived to show."""
    if load.status != 200:
        return Verdict(
            "mounts", False,
            f"{plugin}: the mount URL answered {load.status}, which is no document. "
            f"readyState {load.ready or 'unknown'!r} after {SETTLE_TIMEOUT:g}s",
        )
    if not load.holds_content:
        return Verdict(
            "mounts", False,
            f"{plugin}: the mount answered 200 and the document is empty after "
            f"{SETTLE_TIMEOUT:g}s - {load.content}, readyState {load.ready or 'unknown'!r}",
        )
    return Verdict(
        "mounts", True,
        f"{plugin}: the mount answered 200 with {load.content} (readyState {load.ready})",
    )


def console_verdict(plugin: str, load: Load) -> Verdict:
    """`no_console_errors`: the channel was live and nothing was written to it."""
    if not load.measured:
        return Verdict(
            "no_console_errors", False,
            f"{plugin}: no error channel was live during this load, so an empty list "
            "here is not evidence of a clean surface",
        )
    if load.errors:
        named = " | ".join(load.errors[:LISTED_ERRORS])
        more = f" (+{len(load.errors) - LISTED_ERRORS} more)" if len(load.errors) > LISTED_ERRORS else ""
        return Verdict(
            "no_console_errors", False,
            f"{plugin}: {len(load.errors)} error(s) while loading - {named}{more}",
        )
    return Verdict(
        "no_console_errors", True,
        f"{plugin}: no page error, no failed resource and no console error while loading",
    )


def reload_verdict(plugin: str, reload: Load | None) -> Verdict:
    """`survives_reload`: the second navigation answers the first two rows again."""
    if reload is None:
        return Verdict(
            "survives_reload", False,
            f"{plugin}: no reload was read, so the comparison never happened",
        )
    if reload.status != 200:
        return Verdict(
            "survives_reload", False,
            f"{plugin}: after the reload the mount URL answered {reload.status}",
        )
    if not reload.holds_content:
        return Verdict(
            "survives_reload", False,
            f"{plugin}: after the reload the document holds nothing - {reload.content}",
        )
    if not reload.measured:
        return Verdict(
            "survives_reload", False,
            f"{plugin}: after the reload no error channel was live, so the reload is unread",
        )
    if reload.errors:
        named = " | ".join(reload.errors[:LISTED_ERRORS])
        return Verdict(
            "survives_reload", False,
            f"{plugin}: after the reload the surface reported {len(reload.errors)} "
            f"error(s) - {named}",
        )
    return Verdict(
        "survives_reload", True,
        f"{plugin}: the reload answers 200 with {reload.content} and no error",
    )


def browser_verdicts(
    case: dict, plugin: str, load: Load, reload: Load | None = None
) -> list[Verdict]:
    """Grade the browser rows one case asked for, from the evidence one session collected.

    A check outside this group gets no verdict: the offline module owns those rows and a
    second opinion here would let one number be measured twice by two rulers.
    """
    verdicts: list[Verdict] = []
    for name in case.get("checks", []):
        if name not in BROWSER_CHECK_NAMES:
            continue
        if name == "mounts":
            verdicts.append(mounts_verdict(plugin, load))
        elif name == "no_console_errors":
            verdicts.append(console_verdict(plugin, load))
        else:
            verdicts.append(reload_verdict(plugin, reload))
    return verdicts


# --- the page code ------------------------------------------------------------------

#: The content of the moment: what the document says and what it has drawn. One
#: implementation, read twice — on its own as `CONTENT_PROBE`, and inside the hook below.
_CONTENT_FN = r"""() => {
  let text = 0;
  let graphics = 0;
  try {
    const body = document.body;
    const raw = body ? (body.innerText !== undefined ? body.innerText : body.textContent) : "";
    text = String(raw || "").replace(/\s+/g, "").length;
  } catch (failure) {
    text = 0;
  }
  try {
    const nodes = document.querySelectorAll("canvas, svg, img, video");
    for (const node of nodes) {
      const box = node.getBoundingClientRect();
      if (box.width > 0 && box.height > 0) graphics += 1;
    }
  } catch (failure) {
    graphics = 0;
  }
  return { ready: document.readyState, text: text, graphics: graphics };
}"""

#: The content read with no dependence on the hook, for the case where the hook never
#: ran. It says nothing about errors, and `SurfaceSession` marks such a load unmeasured.
CONTENT_PROBE = _CONTENT_FN

#: Installed at document start, before any script the bundle ships runs.
#: `window.__epheSurfaceReport` is the read-back: the content of the moment and everything
#: the page saw go wrong so far. A resource that fails to load arrives as a capture-phase
#: `error` event whose target is the element, which is how it is told from an exception.
PROBE_HOOK = """
(() => {
  const seen = [];
  const content = __CONTENT_FN__;
  const push = (kind, message) => {
    if (seen.length < 200) seen.push(kind + ": " + String(message).slice(0, 240));
  };
  window.addEventListener("error", (event) => {
    const target = event.target;
    if (!target || target === window || target.nodeType !== 1) {
      push("pageerror", event.message || "unknown error");
      return;
    }
    const tag = String(target.tagName || "").toLowerCase();
    push("resource", tag + " " + (target.src || target.href || "(no url)"));
  }, true);
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    push("rejection", (reason && reason.message) || reason || "unknown rejection");
  });
  const reportError = console.error;
  console.error = (...args) => {
    push("console", args.map((a) => String(a)).join(" "));
    return reportError.apply(console, args);
  };
  window.__epheSurfaceReport = () => Object.assign(content(), {
    hook: true, errors: seen.slice(0)
  });
})();
""".replace("__CONTENT_FN__", _CONTENT_FN)

JS_SNIPPETS: dict[str, str] = {"PROBE_HOOK": PROBE_HOOK, "CONTENT_PROBE": CONTENT_PROBE}

_READ_HOOK = "window.__epheSurfaceReport ? window.__epheSurfaceReport() : null"


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _dedupe(items: list[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


class SurfaceSession:
    """The real app on a loopback port and one engine, held for as many mounts as asked.

    The caller owns `EPHE_CONFIG_DIR`: the server resolves the plugin root per request, so
    a bundle staged and installed under the home this session runs against is the bundle
    the mount serves. Nothing here copies a bundle by hand — an end state that reached the
    mount through a private path would not be the product's.
    """

    def __init__(self, engine: str = "chromium", config: Path | str | None = None) -> None:
        self.engine = engine
        self.port = 0
        self.home = str(config) if config is not None else ""
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self._playwright: Any = None
        self._browser: Any = None
        self._errors: list[str] = []
        self._listeners = False

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        """Boot the app, then the engine. Either half raising is the caller's to report.

        The session refuses to boot without a run-scoped home: the server resolves the
        plugin root per request through `EPHE_CONFIG_DIR`, so a session without a home
        would mount the operator's real collection and grade a stranger's state.
        """
        import os
        import uvicorn
        from server.main import create_app
        from server.middleware import init_auth

        if not self.home:
            raise RuntimeError(
                "a surface session needs a run-scoped config home: pass --config <dir> "
                "so the mount reads the run's own plugins, never the operator's ~/.ephe"
            )
        os.environ["EPHE_CONFIG_DIR"] = self.home
        init_auth(lan_mode=False)
        self.port = _free_port()
        self._server = uvicorn.Server(
            uvicorn.Config(create_app(), host="127.0.0.1", port=self.port, log_level="warning")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + START_TIMEOUT
        while not self._server.started and time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)
        if not self._server.started:
            raise RuntimeError("the surface server never bound its port")
        self._open_engine()

    def _open_engine(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        factory = getattr(self._playwright, self.engine, None)
        if factory is None:
            raise RuntimeError(f"this playwright build has no {self.engine} engine")
        self._browser = factory.launch()

    def evidence(self, plugin: str) -> tuple[Load, Load]:
        """Read the mount once, reload it, and read it again: `(load, reload)`."""
        from server import plugin_surface_nonce

        nonce = plugin_surface_nonce.mint_surface_nonce(plugin).nonce
        url = f"{self.base}/api/plugins/ui/{plugin}/{nonce}/"
        page = self._browser.new_page()
        try:
            page.add_init_script(PROBE_HOOK)
            self._watch(page)
            first = page.goto(url, wait_until="load")
            load = self._collect(page, first)
            self._errors = []
            second = page.reload(wait_until="load")
            reload = self._collect(page, second)
        finally:
            page.close()
        return load, reload

    def _watch(self, page) -> None:
        """Attach the channels that live outside the page: what the engine reports itself.

        A `requestfailed` listener is deliberately absent. A reload aborts whatever the
        previous document still had in flight, and that is the old page's business, not a
        defect of the reloaded one. A resource that fails to load arrives through the hook.
        """
        self._errors = []
        page.on("pageerror", lambda error: self._errors.append(f"pageerror: {error.message}"))
        page.on(
            "console",
            lambda message: self._errors.append(f"console: {message.text}")
            if message.type == "error"
            else None,
        )
        self._listeners = True

    def _collect(self, page, response) -> Load:
        """Poll one navigation until it shows something or the settle window closes."""
        deadline = time.monotonic() + SETTLE_TIMEOUT
        report: dict[str, Any] = {}
        hook_live = False
        while True:
            try:
                report = page.evaluate(_READ_HOOK) or {}
            except Exception:
                report = {}
            if report:
                hook_live = True
            else:
                try:
                    report = page.evaluate(CONTENT_PROBE) or {}
                except Exception:
                    report = {}
            settled = bool(report) and report.get("ready") != "loading"
            if settled and (
                report.get("text", 0) >= MIN_TEXT_CHARS or report.get("graphics", 0) >= 1
            ):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(POLL_INTERVAL)
        errors = _dedupe(list(report.get("errors") or []) + list(self._errors))
        return Load(
            status=response.status if response is not None else 0,
            ready=str(report.get("ready") or ""),
            text=int(report.get("text") or 0),
            graphics=int(report.get("graphics") or 0),
            errors=errors,
            measured=hook_live or self._listeners,
        )

    def stop(self) -> None:
        """Close the engine and the server, and prove neither outlived the session."""
        failures: list[str] = []
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception as exc:
                failures.append(f"browser: {exc}")
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception as exc:
                failures.append(f"playwright: {exc}")
            self._playwright = None
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=15.0)
            if self._thread.is_alive():
                failures.append("the surface server thread outlived the session")
            self._thread = None
        self._server = None
        assert not failures, "; ".join(failures)
