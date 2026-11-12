"""Ephe · Creator — the browser end-state checks of the creation eval set (task #51c).
evals/creation_checks_browser.py

Three of the nine end states in `evals.creation_eval.CHECKS` are promises about a
running server and a document engine, so they are read from one:

  * `mounts` — the mount URL answers 200 and the document holds something.
  * `no_console_errors` — loading it leaves no uncaught exception, no failed resource
    and no `console.error` behind.
  * `survives_reload` — a second load of the same mount answers the same two ways.

The module is two layers on purpose. `Load` is evidence one load produced, and the
three verdict builders are pure functions over it, so every rule can be shown to say no
without an engine. `SurfaceSession` is the collector: it boots the real app on a loopback
port in the process, mints the per-mount nonce the product mints, installs nothing (a
bundle reaches the mount through `core.tools.creator_tools.install_plugin_bundle`, the
one path a directory takes to becoming loadable) and drives a real engine at the mount.
An engine that cannot boot raises, and the caller names it in a skip.

A mount is read the way the product reads it: framed. The session serves its own page at
`HOST_PATH` on the app origin (`page.route` fulfils it, so the harness adds no product
route), and that page holds the mount in the sandboxed iframe the shell builds and
answers the `ephe.sdk` protocol `app/src/lib/pluginClientHost.ts` implements:
`storage.get` and `storage.set` against the host origin's own `localStorage`, and a coded
`sdk_refused` for `tool.call`, which a browser check never runs. A surface that asks its
host is answered instead of being told it has none, which is the false `sdk_no_host`
console row of the 2026-11-12 analysis (F3).

The reload is the product's own: the host appends `?ephe_reload=N` to the iframe's `src`,
the way `app/src/components/shell/OverlayHost.tsx` reloads a surface, so the mount loads
again while the host that answers it stays. The host's `localStorage` stands in for the
shell's store and is not it: what survives a product reload is `state_bridge_used`'s
question, and these rows do not claim it.

What the content rule is: a non-whitespace character count from the rendered body, or a
`canvas`/`svg`/`img`/`video` with a box wider and taller than nothing. The box half is
what lets a game or a 3D scene be graded at all, since neither has text. What the rule is
not: a statement that the widget does what its case asked. That is task #31's question.

Errors arrive through two channels, unioned. The page hook installed at document start
runs in every frame and is read in the mount's own frame, where it also sees the resource
loads that fail and anything thrown before the listener attaches. The page listener
counts only a console error whose location is inside the mount, so the host document's
own noise cannot be graded as the surface's. A load whose error channels were both dead
reports `measured=False`, and the console row fails on that — a green row nobody watched
is the defect class this set exists to prevent.

The frame is the product's own: the mount header carries a `sandbox` directive without
`allow-same-origin`, so the document runs with an opaque origin and its reads of the
user's authority are refused. `tests/test_plugin_surface_isolation_browser.py:1` measured
that confinement; nothing here repeats it, and nothing here depends on it.

A document written against the Storage API is one row of that same measurement now: the
mount injects its page-storage shim (`sdk/ephe-storage.js`) ahead of the bundle's first
script, so `localStorage` answers and neither error channel sees the `SecurityError` that
failed `creation-05`. The host answers the shim's write over the bridge, so such a
document loads clean; the product's own landing is measured by
`tests/test_plugin_surface_storage_shim_browser.py`, and the eval's persistence witness
stays `state_bridge_used`.
"""
from __future__ import annotations

import json
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

#: The path the eval's own host page answers on, under the app origin. The server serves
#: nothing there: `page.route` fulfils it, so the harness adds no product route.
HOST_PATH = "/__eval_host__"

#: The query parameter the shell appends to reload a framed surface
#: (`app/src/components/shell/OverlayHost.tsx: reloadedUrl`). The eval's host reloads the
#: frame the same way, so the host document and the shell share one reload mechanism.
RELOAD_PARAM = "ephe_reload"

#: The embedder's sandbox attribute for a surface (`DockHost.tsx`, `OverlayHost.tsx`), kept
#: equal to `server/plugin_surface_policy.py`'s isolation directive.
SURFACE_SANDBOX = "allow-scripts allow-popups"


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

#: The page that frames one mount and answers the page SDK for it, the way the shell does
#: (`app/src/lib/pluginClientHost.ts`): one message per call, answered only when it came
#: from the frame this page holds. Storage is kept in the host origin's own `localStorage`,
#: scoped to the bundle, and `tool.call` is a coded refusal because a browser check never
#: runs a tool. `__MOUNT__` and `__PLUGIN__` are replaced with JSON string literals by
#: `host_document`; the reload appends the shell's `?ephe_reload=N` to the frame's `src`.
HOST_SCRIPT = """
(() => {
  const CHANNEL = "ephe.sdk";
  const MOUNT = __MOUNT__;
  const PLUGIN = __PLUGIN__;
  const PREFIX = "ephe.eval." + PLUGIN + ".";
  const frame = document.getElementById("surface");
  const host = { calls: [], refused: 0, reloads: 0 };
  window.__EVAL_HOST__ = host;

  function reply(id, body) {
    const target = frame.contentWindow;
    if (!target) return;
    target.postMessage(Object.assign({ channel: CHANNEL, id: id }, body), "*");
  }

  function refusal(id, message) {
    host.refused += 1;
    reply(id, { ok: false, code: "sdk_refused", message: message });
  }

  function stored(raw) {
    try {
      return JSON.parse(raw);
    } catch (failure) {
      return raw;
    }
  }

  function answer(message) {
    const method = String(message.method);
    if (method === "storage.get" || method === "storage.set") {
      const key = PREFIX + String(message.key);
      try {
        if (method === "storage.get") {
          const raw = window.localStorage.getItem(key);
          reply(message.id, {
            ok: true,
            result: raw === null
              ? { value: null, present: false }
              : { value: stored(raw), present: true }
          });
          return;
        }
        const absent = message.value === null || message.value === undefined;
        if (absent) window.localStorage.removeItem(key);
        else window.localStorage.setItem(key, JSON.stringify(message.value));
        reply(message.id, { ok: true, result: { present: !absent } });
        return;
      } catch (failure) {
        refusal(message.id, "the eval host could not keep the value: " + String(failure));
        return;
      }
    }
    if (method === "tool.call") {
      refusal(message.id, "the eval host runs no tool: these rows measure the surface, not a turn");
      return;
    }
    refusal(message.id, "the eval host does not answer " + method);
  }

  window.addEventListener("message", (event) => {
    if (event.source !== frame.contentWindow) return;
    const message = event.data;
    if (!message || message.channel !== CHANNEL || !message.id) return;
    host.calls.push(String(message.method));
    answer(message);
  });

  window.__evalHostReload = () => {
    host.reloads += 1;
    const separator = MOUNT.indexOf("?") === -1 ? "?" : "&";
    frame.src = MOUNT + separator + "ephe_reload=" + host.reloads;
  };
})();
"""

JS_SNIPPETS: dict[str, str] = {
    "PROBE_HOOK": PROBE_HOOK,
    "CONTENT_PROBE": CONTENT_PROBE,
    "HOST_SCRIPT": HOST_SCRIPT,
}

#: The read-back for one load: the hook's report when it ran, the plain content probe when
#: it did not, and always the URL of the document that answered. The URL is what tells a
#: report from the frame's previous document apart from the one this load produced.
_READ_HOOK = """() => {
  const hooked = Boolean(window.__epheSurfaceReport);
  const report = hooked ? window.__epheSurfaceReport() : (__CONTENT_PROBE__)();
  return Object.assign({}, report, { url: String(location.href), hooked: hooked });
}""".replace("__CONTENT_PROBE__", _CONTENT_FN)


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


_HOST_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ephe eval host</title>
<link rel="icon" href="data:,">
</head>
<body>
<iframe id="surface" title="__TITLE__" src="__MOUNT__" sandbox="__SANDBOX__" allow="" referrerpolicy="no-referrer"></iframe>
<script>
__SCRIPT__
</script>
</body>
</html>
"""


def host_document(mount_url: str, plugin: str, sandbox: str = SURFACE_SANDBOX) -> str:
    """The same-origin page that frames one mount and answers its page SDK.

    The iframe carries the shell's own attributes (`DockHost.tsx`); a host that framed the
    mount differently would measure a different confinement than the product's. The host
    page is served by the session through `page.route` at `HOST_PATH`, so the mount and the
    page holding its storage share one origin without a product route being added.
    """
    script = HOST_SCRIPT.replace("__MOUNT__", json.dumps(mount_url)).replace(
        "__PLUGIN__", json.dumps(plugin)
    )
    return (
        _HOST_TEMPLATE.replace("__TITLE__", plugin)
        .replace("__MOUNT__", mount_url)
        .replace("__SANDBOX__", sandbox)
        .replace("__SCRIPT__", script)
    )


def reload_url(mount_url: str, epoch: int = 1) -> str:
    """The frame's `src` after reload `epoch`: the mount again, with the shell's query."""
    separator = "&" if "?" in mount_url else "?"
    return f"{mount_url}{separator}{RELOAD_PARAM}={epoch}"


def _is_mount_document(response: Any, prefix: str) -> bool:
    """Whether one response is a document load under the mount the host frames."""
    try:
        if response.request.resource_type != "document":
            return False
        return response.request.url.startswith(prefix)
    except Exception:
        return False


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
        self._documents: list[Any] = []
        self._mount = ""
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
        """Frame the mount, read it, reload the frame, read it again: `(load, reload)`.

        The host page stays for both reads. The second read is the frame's own second load,
        because the host appends the shell's `?ephe_reload=N` to the iframe's `src`, so a
        mount that only answers its first navigation cannot make a reload row green.
        """
        from server import plugin_surface_nonce

        nonce = plugin_surface_nonce.mint_surface_nonce(plugin).nonce
        mount = f"{self.base}/api/plugins/ui/{plugin}/{nonce}/"
        host_url = f"{self.base}{HOST_PATH}"
        page = self._browser.new_page()
        try:
            page.route(
                host_url,
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=host_document(mount, plugin),
                ),
            )
            page.add_init_script(PROBE_HOOK)
            self._watch(page, mount)
            page.goto(host_url, wait_until="load")
            if not page.evaluate("Boolean(window.__evalHostReload)"):
                raise RuntimeError("the eval host page did not run its script")
            load = self._collect(self._mount_frame(page, mount), mount)
            self._errors = []
            second_url = reload_url(mount)
            page.evaluate("window.__evalHostReload()")
            reload = self._collect(self._mount_frame(page, second_url), second_url)
        finally:
            page.close()
        return load, reload

    def _mount_frame(self, page: Any, wanted: str, timeout: float = SETTLE_TIMEOUT) -> Any:
        """The frame the host put the mount in, once it reports `wanted` as its URL.

        A frame that still carries the mount but not the URL this load asked for is a
        fallback, not an answer: `_collect` reads it and the load fails on the missing
        document rather than on a raised exception.
        """
        deadline = time.monotonic() + timeout
        fallback: Any = None
        while True:
            for frame in page.frames:
                if frame is page.main_frame:
                    continue
                if frame.url == wanted:
                    return frame
                if frame.url.startswith(self._mount):
                    fallback = frame
            if time.monotonic() >= deadline:
                if fallback is not None:
                    return fallback
                seen = "; ".join(frame.url for frame in page.frames) or "no frame"
                raise RuntimeError(f"the eval host never framed the mount: {seen}")
            time.sleep(POLL_INTERVAL)

    def _note_document(self, response: Any) -> None:
        if _is_mount_document(response, self._mount):
            self._documents.append(response)

    def _document_for(self, wanted: str) -> Any:
        """The newest document response whose request URL begins with `wanted`."""
        for response in reversed(self._documents):
            try:
                if response.request.url.startswith(wanted):
                    return response
            except Exception:
                continue
        return None

    def _watch(self, page: Any, mount: str) -> None:
        """Attach the channels that live outside the page: what the engine reports itself.

        The page listener sees every frame, so a console error is counted only when its
        location is inside the mount; the host document is the harness's own, and its
        noise is not a defect of the surface. A `requestfailed` listener is deliberately
        absent. A reload aborts whatever the previous document still had in flight, and
        that is the old document's business, not a defect of the reloaded one. A resource
        that fails to load arrives through the hook.
        """
        self._errors = []
        self._documents = []
        self._mount = mount

        def on_page_error(error: Any) -> None:
            self._errors.append(f"pageerror: {error.message}")

        def on_console(message: Any) -> None:
            if message.type != "error":
                return
            try:
                location = str((message.location or {}).get("url") or "")
            except Exception:
                location = ""
            if location and not location.startswith(self._mount):
                return
            self._errors.append(f"console: {message.text}")

        page.on("pageerror", on_page_error)
        page.on("console", on_console)
        page.on("response", self._note_document)
        self._listeners = True

    def _collect(self, frame: Any, wanted: str) -> Load:
        """Poll one load until the frame shows something or the settle window closes.

        A report counts only when the URL in it is the document this load asked for: during
        a reload the frame's previous document answers for a moment, and its content and
        errors belong to the load before.
        """
        deadline = time.monotonic() + SETTLE_TIMEOUT
        report: dict[str, Any] = {}
        hook_live = False
        while True:
            try:
                latest = frame.evaluate(_READ_HOOK) or {}
            except Exception:
                latest = {}
            if latest and str(latest.get("url") or "").startswith(wanted):
                report = latest
                hook_live = bool(latest.get("hooked"))
            settled = bool(report) and report.get("ready") != "loading"
            if settled and (
                report.get("text", 0) >= MIN_TEXT_CHARS or report.get("graphics", 0) >= 1
            ):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(POLL_INTERVAL)
        response = self._document_for(wanted)
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
