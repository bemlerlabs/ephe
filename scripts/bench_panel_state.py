#!/usr/bin/env python3
"""What the panel's localStorage state costs the UI thread, measured in a WebKit page.

`docs/PERFORMANCE_BASELINE.md` publishes the window-memory row from here. The state lives in
five localStorage keys (`ephe.panel.dock|width|tabs|activeTab|recent`, written by
`app/src/components/dashboard/agent/usePanelGeometry.ts` and `useTabRegistry.ts`), which is a
JS call on the renderer's main thread. That is the cost a person can feel: WebKit commits the
store to SQLite on its own thread after `setItem` returns, so the disk write is deliberately
*not* in this number -- the app never waits for it.

`performance.now()` is clamped to ~1 ms in WebKit, so a single call measures as zero. The page
therefore times one block of `--ops-per-block` calls, repeats it `--blocks` times, and the
script reports the median block divided by its call count. Two composites are measured
alongside the single operations, because they are what the app actually does:

* **boot read** -- `usePanelGeometry` + `initialTabState`: five `getItem`, three `JSON.parse`.
* **tab write**  -- the `useEffect` in `useTabRegistry`: two `JSON.stringify`, three `setItem`.

The engine is Playwright's WebKit, the same family as the macOS WKWebView the Tauri shell uses
(the shipped app's store is a WKWebView `localstorage.sqlite3`), but it is not the app process:
the shell's own JIT/process settings are not reproduced. The magnitudes here are microseconds,
so that difference cannot decide a UI decision -- it is named so the row is not read as more
than it is.

    python scripts/bench_panel_state.py [--blocks 5] [--ops-per-block 100000] [--json PATH]

Playwright is a project dependency; a machine without its browsers gets the install hint and
a non-zero exit instead of a made-up number.
"""
from __future__ import annotations

import argparse
import http.server
import json
import statistics
import threading
from pathlib import Path

#: The values the installed app held on 2026-11-09 (WebKit store, `tauri://localhost`), read
#: back through sqlite3: dock "right", a dragged width, one active tab and an 8-entry recent
#: list. Sizes, not the specific content, are what the timing depends on.
PAYLOAD = {
    "ephe.panel.dock": "right",
    "ephe.panel.width": "597.76953125",
    "ephe.panel.activeTab": json.dumps("preview"),
    "ephe.panel.tabs": json.dumps(["preview", "files", "terminal"]),
    "ephe.panel.recent": json.dumps(
        [
            {"tab": "preview", "closedAt": 1793792501634},
            {"tab": "files", "closedAt": 1793789379482},
            {"tab": "subagents", "closedAt": 1793708933430},
            {"tab": "git", "closedAt": 1793708931571},
            {"tab": "trajectory", "closedAt": 1793708929782},
            {"tab": "side", "closedAt": 1793708927846},
            {"tab": "memory", "closedAt": 1793708925715},
            {"tab": "audit", "closedAt": 1793704602338},
        ]
    ),
}

class _Quiet(http.server.BaseHTTPRequestHandler):
    """One tiny origin so localStorage has a place to live (`about:blank` has none)."""

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        body = b"<!doctype html><meta charset=utf-8><title>panel-state bench</title>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Silence the request line; this server exists for one page load."""


def _serve() -> tuple[http.server.HTTPServer, int]:
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, int(srv.server_address[1])


def _cached_webkit() -> str | None:
    """A WebKit build already in Playwright's cache, when the pinned one is missing.

    `pip install playwright` and `playwright install` are two versions and drift apart on a
    developer machine; the store's JS API does not change between them, so a cached build is
    good enough for a microsecond row. The empty case stays empty: no browser, no number.
    """
    roots = [
        Path.home() / "Library" / "Caches" / "ms-playwright",  # macOS
        Path.home() / ".cache" / "ms-playwright",              # Linux
        Path.home() / "AppData" / "Local" / "ms-playwright",   # Windows
    ]
    hits: list[Path] = []
    for root in roots:
        hits.extend(root.glob("webkit-*/pw_run.sh"))
    if not hits:
        return None
    return str(sorted(hits, key=lambda p: p.parent.name)[-1])


def measure(blocks: int, ops: int, executable: str | None = None) -> dict:
    # Imported here so the start-up table (the other instrument) does not need Playwright.
    from playwright.sync_api import sync_playwright
    srv, port = _serve()
    try:
        with sync_playwright() as pw:
            used = executable or "playwright default"
            try:
                browser = pw.webkit.launch(executable_path=executable) if executable else pw.webkit.launch()
            except Exception as exc:  # noqa: BLE001 — the hint matters, the exception type does not
                fallback = _cached_webkit()
                if fallback is None or executable:
                    raise SystemExit(
                        "Playwright's WebKit is not installed; run `python -m playwright install webkit`.\n"
                        f"({exc})"
                    ) from exc
                used = fallback
                browser = pw.webkit.launch(executable_path=fallback)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/")
            raw = page.evaluate(
                """({payload, blocks, ops}) => {
                  const B = blocks, N = ops;
                  const keys = Object.keys(payload);
                  for (const k of keys) localStorage.setItem(k, payload[k]);
                  const recent = JSON.parse(payload['ephe.panel.recent']);
                  const tabs = JSON.parse(payload['ephe.panel.tabs']);
                  const active = JSON.parse(payload['ephe.panel.activeTab']);
                  const now = () => performance.now();
                  const bench = (fn) => {
                    const out = [];
                    for (let b = 0; b < B; b++) { const a = now(); for (let i = 0; i < N; i++) fn(); out.push((now() - a) / N); }
                    return out;
                  };
                  const readOne = (k) => localStorage.getItem(k);
                  const out = {
                    bytes: Object.fromEntries(keys.map((k) => [k, new TextEncoder().encode(payload[k]).length])),
                    op_ms: {},
                    ua: navigator.userAgent,
                  };
                  out.op_ms.setItemRecent = bench(() => localStorage.setItem('ephe.panel.recent', payload['ephe.panel.recent']));
                  out.op_ms.getItemRecent = bench(() => readOne('ephe.panel.recent'));
                  out.op_ms.setItemAll5 = bench(() => { for (const k of keys) localStorage.setItem(k, payload[k]); });
                  out.op_ms.getItemAll5 = bench(() => { for (const k of keys) readOne(k); });
                  out.op_ms.parseRecent = bench(() => JSON.parse(payload['ephe.panel.recent']));
                  out.op_ms.stringifyRecent = bench(() => JSON.stringify(recent));
                  out.op_ms.bootRead = bench(() => {
                    readOne('ephe.panel.dock');
                    readOne('ephe.panel.width');
                    JSON.parse(readOne('ephe.panel.tabs') || '[]');
                    JSON.parse(readOne('ephe.panel.recent') || '[]');
                    JSON.parse(readOne('ephe.panel.activeTab') || 'null');
                  });
                  out.op_ms.tabWrite = bench(() => {
                    localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabs));
                    localStorage.setItem('ephe.panel.activeTab', JSON.stringify(active));
                    localStorage.setItem('ephe.panel.recent', JSON.stringify(recent));
                  });
                  return out;
                }""",
                {"payload": PAYLOAD, "blocks": blocks, "ops": ops},
            )
            browser.close()
    finally:
        srv.shutdown()
    summaries = {
        name: {
            "median_ms": round(statistics.median(values), 6),
            "min_ms": round(min(values), 6),
            "max_ms": round(max(values), 6),
        }
        for name, values in raw["op_ms"].items()
    }
    return {
        "engine": "Playwright WebKit",
        "ua": raw["ua"],
        "executable": used,
        "blocks": blocks,
        "ops_per_block": ops,
        "bytes": raw["bytes"],
        "ops": summaries,
        "note": "JS-call cost only; WebKit commits localStorage to SQLite on its own thread.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blocks", type=int, default=5, help="timed blocks per operation (default 5)")
    parser.add_argument("--ops-per-block", type=int, default=100_000, help="calls per block")
    parser.add_argument("--json", type=Path, help="write the result here as JSON")
    parser.add_argument("--webkit-executable", help="pw_run.sh of a specific Playwright WebKit build")
    args = parser.parse_args()
    if args.blocks < 1 or args.ops_per_block < 1000:
        parser.error("need --blocks >= 1 and --ops-per-block >= 1000")
    result = measure(args.blocks, args.ops_per_block, args.webkit_executable)
    print(json.dumps(result, indent=2))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
