#!/usr/bin/env python3
"""
Ephe — Demo Media Generator v5.

Records the REAL product UI with Playwright and converts the recordings into
README WebP clips plus a hero screenshot.

Own pair, own data root (why this script no longer talks to :5173)
    A recording against a developer's running servers shows the developer: the sidebar
    restores the owner's sessions out of the server mirror, and Settings → Tasks lists
    their rows. So this recorder boots its own pair — a backend on a throwaway
    EPHE_CONFIG_DIR plus a Vite dev server whose ``/api`` proxy points at that backend
    (vite.config.ts reads EPHE_API_TARGET) — and deletes the root when it is done. The
    engine key travels as EPHE_OPENAI_COMPAT_API_KEY in the child environment, so the
    key is never copied into the temp root. The demo's own tasks live in that root's
    tasks.json and disappear with it; ~/.ephe/tasks.json is not touched at all.

Prerequisites
    ffmpeg + ffprobe on PATH
    pnpm with app/node_modules installed (``cd app && pnpm install``)
    playwright chromium (``.venv/bin/python -m playwright install chromium``)
    an engine: ~/.ephe/engine.json, plus a key in EPHE_OPENAI_COMPAT_API_KEY or
    ~/.ephe/engine.key — the chat clips need an engine that answers

Output
    docs/media/ephe-demo-onboarding.webp  first open: film + four questions
    docs/media/ephe-demo-chat.webp         real streaming chat (engine)
    docs/media/ephe-demo-artifacts.webp    SVG + XLSX artifacts, and the hero frame
    docs/media/ephe-demo-budget.webp       read a CSV in the workspace, answer in euros
    docs/media/ephe-demo-launch.webp       turn the plan into a written checklist file
    docs/media/ephe-demo-agent-panel.webp  live git diff, terminal, task list
    docs/media/ephe-demo-palette.webp      command palette, rename, shortcuts
    docs/media/ephe-demo-plugins.webp      plugin store, master switch, detail sheet
    docs/media/ephe-demo-mobile.webp       mobile PWA with artifact
    docs/media/ephe-demo-tui.webp          ephe tui in a real terminal, with approvals
    docs/screenshots/hero-banner.png      2x hero shot

Usage
    ./.venv/bin/python scripts/create_demo_media.py
    ./.venv/bin/python scripts/create_demo_media.py --only=palette,plugins
    ./.venv/bin/python scripts/create_demo_media.py --only=tui
    ./.venv/bin/python scripts/create_demo_media.py --keep-root
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Browser, Page, ViewportSize, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
MEDIA = ROOT / "docs" / "media"
SHOTS = ROOT / "docs" / "screenshots"
TEMP = MEDIA / "temp"

# The owner's folder is read for exactly two things (engine.json, engine key): the
# child process gets the key through its environment, and no path below it is ever
# opened by the recording itself.
REAL_HOME = Path.home() / ".ephe"

DESKTOP_W, DESKTOP_H = 1280, 720
MOBILE_W, MOBILE_H = 390, 844


def engine_api_key() -> str:
    """The key the demo engine is called with: the env, or the owner's own key file."""
    env_key = (os.environ.get("EPHE_OPENAI_COMPAT_API_KEY") or "").strip()
    if env_key:
        return env_key
    key_file = REAL_HOME / "engine.key"
    return key_file.read_text().strip() if key_file.exists() else ""

# English UI is the product default since round 14 — demos match it.
INIT_SCRIPT = (
    "localStorage.setItem('i18nextLng','en');"
    "localStorage.setItem('ephe_onboarded','1');"
    "localStorage.setItem('ephe.intro.seen.v1','1');"
)

# The onboarding clip is the one context that has not seen the film or the tour.
ONBOARDING_INIT = (
    "localStorage.setItem('i18nextLng','en');"
    "localStorage.removeItem('ephe.intro.seen.v1');"
    "localStorage.removeItem('ephe_onboarded');"
)

# Stable testids of the current components (checked 2026-10-15). A placeholder or a
# button label is copy and breaks on the next copy edit; these four survived the
# composer rewrite, which is why the clips read them.
COMPOSER = '[data-testid="chat-input"]'
SEND = '[data-testid="send-btn"]'
STOP = '[data-testid="stop-btn"]'
EMPTY_HINT = '[data-testid="composer-empty-send-hint"]'
TASK_INPUT = '[data-testid="task-new-input"]'
WEBP_TARGET_BYTES = 3_000_000

# Every clip starts on the boot skeleton; the first frames are not the product.
TRIM_START = {
    "onboarding": 1.0,
    "chat": 3.0,
    "artifacts": 2.5,
    "budget": 2.5,
    "launch": 2.5,
    "agent-panel": 1.2,
    "palette": 1.2,
    "plugins": 1.2,
    "mobile": 2.5,
}

# Clips whose turn runs long keep only their ending, in seconds. A tool turn that
# takes half a minute is the product working, not dead air, so the cap sits above
# the longest turn recorded here and only trims the settle before it.
TAIL_SECONDS = {}

# Filled by main() from the stack's Vite port; a clip must not run against an empty VITE.
VITE = ""
# Filled by main() from the backend interpreter's WebSocket support (see DemoStack).
TERMINAL_PANE = True


# Isolated stack


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _wait_http(url: str, label: str, timeout: float, log: Path | None = None) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    return
        except Exception:  # noqa: BLE001 — not up yet
            time.sleep(0.4)
    tail = ""
    if log is not None and log.exists():
        tail = "\n" + log.read_text(errors="replace")[-1500:]
    raise SystemExit(f"[ERROR] {label} did not answer on {url} within {timeout:.0f}s{tail}")


class DemoStack:
    """The recorder's own backend + Vite pair, both bound to a throwaway data root."""

    def __init__(self, keep_root: bool = False) -> None:
        self.keep_root = keep_root
        self.root = Path(tempfile.mkdtemp(prefix="ephe-demo-root-"))
        self.api_port = 0
        self.vite_url = ""
        self.ws_supported = True
        self.procs: list[subprocess.Popen] = []
        self.logs: dict[str, Path] = {}

    def _log_handle(self, name: str):
        path = self.root / f"{name}.log"
        self.logs[name] = path
        return open(path, "w")

    def _engine_json(self) -> Path:
        """A copy of the owner's engine.json — without it the setup gate sends the
        app to /#/setup and no clip has a chat surface. The workspace is re-pointed at
        this checkout: the git pane shows the working tree of the recorded workspace,
        so the demo owns a diff to show (and the owner's private folder stays out of
        the frame)."""
        source = REAL_HOME / "engine.json"
        if not source.exists():
            raise SystemExit(
                f"[ERROR] {source} is missing — configure the engine once (ephe setup) "
                "or point EPHE_CONFIG_DIR at a folder that holds one."
            )
        engine = json.loads(source.read_text())
        # The demo may name a faster free model than the owner's current choice;
        # it never changes the product default or the persisted engine.json.
        override = (os.environ.get("EPHE_DEMO_MODEL") or "").strip()
        if override:
            engine["model"] = override
        engine["workspace_dir"] = str(self._demo_workspace())
        target = self.root / "engine.json"
        target.write_text(json.dumps(engine, indent=2))
        print(f"    engine   : {engine.get('model')} @ {engine.get('api_url')}")
        return target

    def _demo_workspace(self) -> Path:
        """A neutral demo project, never this checkout.

        The header and the composer show the user's project and branch; recording
        from the Ephe source tree would put our development branches in the
        released frames."""
        ws = self.root / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        readme = ws / "README.md"
        readme.write_text("# Demo project\n\nA small project for the Ephe demo clips.\n")
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)
        subprocess.run(
            ["git", "config", "user.email", "demo@example.invalid"], cwd=ws, check=True
        )
        subprocess.run(["git", "config", "user.name", "Demo"], cwd=ws, check=True)
        subprocess.run(["git", "add", "README.md"], cwd=ws, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "demo: initial project"], cwd=ws, check=True
        )
        (ws / "plan.md").write_text(
            "# Launch plan\n\n"
            "- draft the landing page — owner: Dana — open\n"
            "- record the three demo clips — owner: Dana — open\n"
            "- write the install guide — owner: Ravi — open\n"
            "- set up the feedback inbox — owner: Ravi — not started\n"
            "- price the hosted engine add-on — owner: Mira — not started\n"
            "- accessibility pass on the composer — owner: Dana — open\n"
            "- mobile pairing smoke — owner: Ravi — not started\n"
            "- publish the changelog — owner: Mira — not started\n"
        )
        (ws / "monthly_budget_2026.csv").write_text(
            "month,category,amount_eur,kind\n"
            "2026-01,hosting,820,fixed\n"
            "2026-01,payroll,14200,fixed\n"
            "2026-01,marketing,3100,variable\n"
            "2026-01,tooling,1450,variable\n"
            "2026-02,hosting,910,fixed\n"
            "2026-02,payroll,14200,fixed\n"
            "2026-02,marketing,4300,variable\n"
            "2026-02,tooling,1610,variable\n"
        )
        readme.write_text(readme.read_text() + "\n- one pending change\n")
        return ws

    def websocket_support(self, python: Path) -> bool:
        """Whether the backend interpreter can upgrade a WebSocket at all. uvicorn needs
        websockets or wsproto; without one it answers every upgrade with 404 and the
        Develop pane records as "disconnected · reconnecting…"."""
        probe = (
            "import importlib.util as u, sys;"
            "sys.exit(0 if (u.find_spec('websockets') or u.find_spec('wsproto')) else 1)"
        )
        done = subprocess.run([str(python), "-c", probe], capture_output=True)
        return done.returncode == 0

    def _security_policy(self) -> None:
        """The approval ceiling of the demo run. The composer sends full-access autonomy
        with every turn, but the profile read in server/routes/chat.py gates it
        (mode_auto = profile != "strict"), and a root without security.json is strict:
        the first tool call of every clip then stops on an approval card and no QR or
        XLSX artifact is ever produced. A non-strict profile is product policy, not
        owner data, so the demo writes its own."""
        (self.root / "security.json").write_text(
            json.dumps({"approval_profile": "session", "sandbox_enabled": False}, indent=2)
        )
        # The tour is server-side device state, so a localStorage flag is not enough.
        # A finished marker keeps the four questions out of every clip.
        (self.root / "tour.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "step": 5,
                    "walked": True,
                    "skipped": True,
                    "answers": {},
                },
                indent=2,
            )
        )

    def _key(self) -> str:
        return engine_api_key()

    def _child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # An inherited PYTHONPATH from another venv breaks the server on import.
        env.pop("PYTHONPATH", None)
        env["EPHE_CONFIG_DIR"] = str(self.root)
        key = self._key()
        if key:
            env["EPHE_OPENAI_COMPAT_API_KEY"] = key
        return env

    def start(self) -> None:
        self._engine_json()
        self._security_policy()
        python = ROOT / ".venv" / "bin" / "python"
        if not python.exists():
            python = Path(sys.executable)
        self.ws_supported = self.websocket_support(python)
        if not self.ws_supported:
            print(
                "    [WARN] no websockets/wsproto in "
                f"{python.parent.parent.name} — uvicorn refuses every WebSocket upgrade, so the\n"
                "           Develop pane would record as \"disconnected · reconnecting…\". The\n"
                "           agent-panel clip keeps the git console and the task list instead.\n"
                "           Fix for the terminal: add uvicorn[standard] to pyproject.toml."
            )
        self.api_port = _free_port()
        env = self._child_env()
        self.procs.append(
            subprocess.Popen(
                [str(python), "run_server.py", "--port", str(self.api_port)],
                cwd=str(ROOT),
                env=env,
                stdout=self._log_handle("backend"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        )
        _wait_http(
            f"http://127.0.0.1:{self.api_port}/api/health",
            "isolated backend",
            90,
            self.logs.get("backend"),
        )
        print(f"    backend  :{self.api_port} (root {self.root})")

        vite_port = _free_port()
        vite_env = dict(env, EPHE_API_TARGET=f"http://127.0.0.1:{self.api_port}")
        vite_bin = APP / "node_modules" / ".bin" / "vite"
        if not vite_bin.exists():
            raise SystemExit("[ERROR] app/node_modules is missing — run: cd app && pnpm install")
        # The bin directly: `pnpm dev -- --port N` hands the extra `--` to vite, which
        # then ignores the port and takes 5174 while this script waits on another one.
        self.procs.append(
            subprocess.Popen(
                [str(vite_bin), "--port", str(vite_port), "--strictPort"],
                cwd=str(APP),
                env=vite_env,
                stdout=self._log_handle("vite"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        )
        _wait_http(f"http://127.0.0.1:{vite_port}/", "isolated Vite", 120, self.logs.get("vite"))
        self.vite_url = f"http://127.0.0.1:{vite_port}"
        print(f"    vite     :{vite_port} → api {self.api_port}")

    def stop(self) -> None:
        for proc in self.procs:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(1.5)
        for proc in self.procs:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.keep_root:
            print(f"    root kept: {self.root}")
        else:
            shutil.rmtree(self.root, ignore_errors=True)


# Page helpers


def human_type(page: Page, selector: str, text: str, delay: int = 32) -> None:
    page.wait_for_selector(selector, timeout=15000)
    page.locator(selector).click()
    page.wait_for_timeout(220)
    page.keyboard.type(text, delay=delay)
    page.wait_for_timeout(260)


def human_type_lines(page: Page, selector: str, lines: list[str], delay: int = 18) -> None:
    """Types multi-line prompts — plain Enter would send, so lines are joined with
    Shift+Enter like a real user writing a markdown table."""
    page.wait_for_selector(selector, timeout=15000)
    page.locator(selector).click()
    page.wait_for_timeout(220)
    for i, line in enumerate(lines):
        page.keyboard.type(line, delay=delay)
        if i < len(lines) - 1:
            page.keyboard.press("Shift+Enter")
    page.wait_for_timeout(260)


def send_and_wait(page: Page, done_timeout: int = 150_000, label: str = "turn") -> None:
    """Send, then wait for the turn to end — the Stop button detaches when the answer
    lands. done_timeout has to cover a tool-using turn: a QR or XLSX turn ran past the
    30 s budget that was tuned for the older, faster engine."""
    started = time.time()
    page.locator(SEND).click()
    try:
        # a fast-path turn can finish before the Stop button is ever observed
        page.wait_for_selector(STOP, timeout=4000, state="attached")
    except Exception:  # noqa: BLE001 — turn already completed
        print(f"    {label}: {time.time() - started:.1f}s (no Stop phase)")
        return
    page.wait_for_selector(STOP, state="detached", timeout=done_timeout)
    page.wait_for_timeout(1800)
    print(f"    {label}: {time.time() - started:.1f}s")


def _js_click(page: Page, testid: str) -> None:
    """A DOM click: the header and the sidebar sit under overlays whose hit-target
    probe Playwright's own click trips over, while the DOM click is what a user does."""
    page.evaluate(
        "(id) => document.querySelector(`[data-testid=\"${id}\"]`)?.click()",
        testid,
    )


def rename_session(page: Page, title: str) -> None:
    """Title the recorded session so a viewer can read what the frame shows."""
    page.wait_for_selector('[data-testid="session-title-text"]', timeout=10000)
    page.evaluate(
        "() => { const el = document.querySelector('[data-testid=\"session-title-text\"]');"
        " el && el.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true })) }"
    )
    page.get_by_test_id("menu-rename").first.dispatch_event("click")
    page.wait_for_timeout(200)
    page.keyboard.press("Meta+a")
    page.keyboard.type(title, delay=35)
    page.keyboard.press("Enter")
    page.wait_for_timeout(900)


def dismiss_status_popover(page: Page) -> None:
    if page.locator('[data-testid="agent-status-popover"]').count():
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)


def dismiss_task_dock(page: Page) -> None:
    """The task dock appears once a second task exists and covers the answer."""
    dismiss = page.locator('[data-testid="task-dock-dismiss"]')
    if dismiss.count() and dismiss.first.is_visible():
        dismiss.first.click()
        page.wait_for_timeout(350)
        return
    pill = page.locator('[data-testid="task-dock-pill"]')
    if pill.count() and pill.first.is_visible():
        pill.first.click()
        page.wait_for_timeout(250)
        if dismiss.count() and dismiss.first.is_visible():
            dismiss.first.click()
            page.wait_for_timeout(350)


def suppress_task_dock(page: Page) -> None:
    """The dock is not the subject of these clips: a second task opens it over the
    answer, and a click-through can leave it open. Hiding the overlay is the
    demo's own frame choice; the real UI keeps the dock for the user."""
    page.add_style_tag(
        content=(
            '[data-testid="task-dock"], [data-testid="task-dock-pill"] '
            '{ display: none !important; }'
        )
    )


def assert_demo_sidebar(page: Page) -> None:
    """Guards the hero against the owner's history. Every title this run writes comes
    from the ASCII prompts below, so a title carrying umlauts was restored from
    somewhere else and the frame must not ship."""
    titles = page.locator('[data-testid="session-title-text"]').all_inner_texts()
    foreign = [t for t in titles if any(ch in t for ch in "äöüßÄÖÜ")]
    if foreign:
        raise RuntimeError(f"sidebar carries a title this run did not write: {foreign}")


def newest_webm(record_dir: Path) -> Path:
    files = sorted(record_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise RuntimeError(f"no .webm in {record_dir}")
    return files[-1]


# Clips


def clip_onboarding(page: Page) -> None:
    """The first open: the awakening film, then the four questions, then the desk."""
    page.goto(f"{VITE}/?tour=1#/chat", wait_until="load")
    page.wait_for_selector('[data-testid="first-run-intro"]', timeout=20000)
    page.wait_for_timeout(10_600)  # the title, line and CTA arrive at 10 s
    page.get_by_test_id("intro-cta").dispatch_event("click")
    page.wait_for_selector('[data-testid="first-run-tour"]', timeout=20000)

    def wait_step(step: int) -> None:
        page.wait_for_selector(
            f'[data-testid="first-run-tour"][data-step="{step}"]', timeout=20000
        )

    page.get_by_test_id("tour-start").dispatch_event("click")
    wait_step(1)
    page.wait_for_timeout(1000)
    page.get_by_test_id("tour-usage-research").dispatch_event("click")
    page.wait_for_timeout(350)
    page.get_by_test_id("tour-continue").dispatch_event("click")
    wait_step(2)
    page.wait_for_timeout(1000)
    page.get_by_test_id("tour-continue").dispatch_event("click")
    wait_step(3)
    page.wait_for_timeout(1000)
    page.get_by_test_id("tour-continue").dispatch_event("click")
    wait_step(4)
    page.wait_for_timeout(1000)
    page.get_by_test_id("tour-fresh").dispatch_event("click")
    wait_step(5)
    page.wait_for_timeout(1000)
    page.get_by_test_id("tour-finish").dispatch_event("click")
    page.wait_for_selector('[data-testid="first-run-tour"]', state="detached", timeout=20000)
    page.wait_for_timeout(1600)


def clip_chat(page: Page) -> None:
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.wait_for_timeout(2600)  # welcome cards + background settle
    suppress_task_dock(page)
    rename_session(page, "Local-first, explained")

    # "in English" is part of the prompt on purpose: the engine answers in the language
    # of the request (settings.languageRowHint) and the model drifted into German on the
    # short tool turns, which the released frames must not carry.
    human_type(
        page,
        COMPOSER,
        "Why does local-first AI matter? Answer in three short bullets, in English.",
    )
    send_and_wait(page, label="chat turn")
    page.wait_for_timeout(2200)
    dismiss_task_dock(page)
    dismiss_status_popover(page)

    # The README hero wants a finished answer and a live draft.
    human_type(page, COMPOSER, "Turn that into a one-line launch message")
    page.wait_for_selector(EMPTY_HINT, state="detached", timeout=5000)
    assert_demo_sidebar(page)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "hero-banner.png"))
    page.wait_for_timeout(900)


def clip_artifacts(page: Page) -> None:
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.locator('[data-testid="new-session"]').click()
    page.wait_for_timeout(1600)
    suppress_task_dock(page)
    rename_session(page, "Artifacts, live")

    human_type(
        page,
        COMPOSER,
        "Use write_file to create `local-first.svg`: a clean 640x480 poster with a dark "
        "forest background, a small gold bee mark, the words LOCAL-FIRST in large serif "
        "letters, and the line 'Your machine. Your model. Your record.' Keep the SVG "
        "under 30 lines. Then reply in English with the path.",
    )
    send_and_wait(page, done_timeout=120_000, label="svg turn")
    page.wait_for_timeout(1400)
    dismiss_task_dock(page)

    human_type_lines(
        page,
        COMPOSER,
        [
            "Create a real .xlsx file named monthly_budget_2026.xlsx. Use the spreadsheet",
            "file tool, not a markdown table. Columns: Item, Monthly cost. Rows:",
            "Rent 1200; Food 450; Transport 180. Then reply in English with the path.",
        ],
    )
    send_and_wait(page, done_timeout=120_000, label="xlsx turn")
    page.wait_for_timeout(1000)
    dismiss_task_dock(page)

    # Open the produced SVG in the panel. The preview frame paints images; an .xlsx
    # cannot, so the SVG is the visible artifact. The frame's own status row leaving is
    # the signal that the preview really painted, so the clip is not a spinner shot.
    opens = page.locator('[data-testid^="message-file-open-"]')
    labels = opens.evaluate_all("els => els.map((e) => e.getAttribute('aria-label') || '')")
    print(f"    artifact cards: {labels}")
    svg = [i for i, label in enumerate(labels) if label.endswith(".svg")]
    png = [i for i, label in enumerate(labels) if label.endswith(".png")]
    target = svg or png
    if target:
        try:
            # dispatch_event: Playwright's click first scrolls the row into view and the
            # chat jumps; the DOM click reaches the same handler without moving the frame.
            opens.nth(target[-1]).dispatch_event("click")
            page.wait_for_selector('[data-testid="preview-frame"]', state="attached", timeout=8000)
            page.wait_for_selector('[data-testid="preview-frame-status"]', state="detached", timeout=10000)
            # The default 420 px pane crops a poster. Cycle it wide so the artifact
            # fills the frame.
            for _ in range(2):
                cycle = page.locator('button[aria-label^="Cycle width"]')
                if cycle.count():
                    cycle.first.click()
                    page.wait_for_timeout(700)
            page.wait_for_timeout(1200)
        except Exception as exc:  # noqa: BLE001 — the frame is still usable without it
            print(f"    [WARN] preview did not paint: {exc}")

    human_type(page, COMPOSER, "Add a savings row and re-export it")
    page.wait_for_selector(EMPTY_HINT, state="detached", timeout=5000)
    page.wait_for_timeout(1400)


def clip_budget(page: Page) -> None:
    """Read a real CSV in the workspace and answer with numbers from it.

    The prompt names the file and refuses memory on purpose: the frame has to show
    the tool card opening and the figures matching the rows the demo wrote."""
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.locator('[data-testid="new-session"]').click()
    page.wait_for_timeout(1600)
    suppress_task_dock(page)
    rename_session(page, "Where the money goes")

    human_type_lines(
        page,
        COMPOSER,
        [
            "Read monthly_budget_2026.csv in my workspace. Which three variable",
            "categories grew most between January and February? Give the euro",
            "difference for each. Answer in English, under 60 words.",
        ],
    )
    send_and_wait(page, done_timeout=180_000, label="budget turn")
    page.wait_for_timeout(2600)
    dismiss_task_dock(page)
    dismiss_status_popover(page)


def clip_launch(page: Page) -> None:
    """Turn the workspace's own plan into a written deliverable the user can open."""
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.locator('[data-testid="new-session"]').click()
    page.wait_for_timeout(1600)
    suppress_task_dock(page)
    rename_session(page, "What is still open")

    human_type_lines(
        page,
        COMPOSER,
        [
            "Read plan.md in my workspace. Write launch_checklist.md with only the",
            "steps that are still open, as a markdown table with columns Step and",
            "Owner, sorted by owner. Use the file tool. Then reply in English with",
            "one line: the path and how many steps you moved.",
        ],
    )
    send_and_wait(page, done_timeout=200_000, label="checklist turn")
    page.wait_for_timeout(2600)
    dismiss_task_dock(page)
    dismiss_status_popover(page)
    # The file card is the proof; the preview pane is not opened on camera because
    # its address row carries the resolved path of the throwaway demo root.


DEMO_TASK_TITLES = ("Ship v4 README demos", "Review repo hygiene report")


def _open_panel_tab(page: Page, key: str, hold: int) -> None:
    """Open the panel via the PREVIEW-Open event and activate the tab
    (setOpen(true) + openTab), then hold it."""
    page.evaluate(
        "(k) => { window.dispatchEvent(new CustomEvent('ephe:preview-open', { detail: { tab: k } })) }",
        key,
    )
    page.locator(f'[data-testid="panel-tab-pill-{key}"]').first.wait_for(state="visible", timeout=6000)
    page.wait_for_timeout(hold)


def clip_agent_panel(page: Page) -> None:
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.wait_for_timeout(1200)

    _open_panel_tab(page, "git", 3600)       # diff view of the workspace this run records
    # The Develop pane is a live xterm PTY over /api/shell/term. A backend whose
    # interpreter carries no websocket library refuses the upgrade, and the frame then
    # reads "disconnected · reconnecting…" — main() checked that up front and warns.
    if TERMINAL_PANE:
        _open_panel_tab(page, "terminal", 2600)

    # The panel's own tasks page is gone: TAB_KEYS (agent/primitives.tsx) carries no
    # "tasks" key any more, the task list lives in Settings → Tasks, and the sidebar's
    # Steps row is the door to it. The old `get_by_label("New task")` hit the two
    # new-task buttons (sidebar + header both carry aria-label "New task") and never
    # the input, which is `task-new-input` inside that settings page.
    _js_click(page, "sidebar-action-tasks")
    page.wait_for_selector(TASK_INPUT, timeout=10000)
    for title in DEMO_TASK_TITLES:
        page.locator(TASK_INPUT).fill(title)
        page.keyboard.press("Enter")
        page.wait_for_timeout(900)
    toggle = page.locator('[data-testid^="task-toggle-"]').first
    try:
        toggle.click(timeout=5000)
    except Exception:  # noqa: BLE001 — the list is still worth the frame
        pass
    page.wait_for_timeout(1800)


def clip_palette(page: Page) -> None:
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.wait_for_timeout(1000)

    # The header button dispatches ⌘K; the global shortcut is the stable door.
    page.keyboard.press("Meta+k")
    # 'Quick Search' is the dialog's aria-label (not visible text)
    page.wait_for_selector('[role="dialog"][aria-label="Quick Search"]', timeout=8000)
    # The agent-panel entry is labelled "Open changes" (commandPalette.items.panel_git,
    # section "Ephe's Computer"); the old "Panel: Git" wording is gone.
    page.keyboard.type("changes", delay=90)
    page.wait_for_timeout(900)
    try:
        page.locator('#cmd-palette-listbox button', has_text="Open changes").first.click(timeout=4000)
    except Exception:  # noqa: BLE001 — fall back to the highlighted result
        page.keyboard.press("Enter")
    page.wait_for_timeout(2200)
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)

    page.evaluate("() => { document.activeElement && document.activeElement.blur() }")
    # The cheatsheet opens through the SHORTCUTS_EVENT the header button dispatches.
    page.evaluate("window.dispatchEvent(new CustomEvent('ephe:toggle-shortcuts'))")
    page.wait_for_selector('[data-testid="shortcuts-overlay"]', timeout=8000)
    page.wait_for_timeout(2600)
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)

    # Ensure a session row exists, then inline-rename it via the row context menu.
    # JS clicks: the z-modal header intercepts Playwright's hit-target probe on
    # sidebar/header-adjacent elements — a DOM click is the real user click.
    _js_click(page, "new-session")
    page.wait_for_timeout(400)
    page.evaluate(
        "() => { const el = document.querySelector('[data-testid=\"session-title-text\"]');"
        " el && el.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true })) }"
    )
    page.get_by_test_id("menu-rename").first.dispatch_event("click")
    page.wait_for_timeout(200)
    page.keyboard.press("Meta+a")
    page.keyboard.type("Product tour", delay=40)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)

    # Collapse/expand the sidebar — the header toggle demos both rail states.
    _js_click(page, "header-sidebar-toggle")
    page.wait_for_timeout(1300)
    _js_click(page, "header-sidebar-toggle")
    page.wait_for_timeout(1300)


def clip_plugins(page: Page) -> None:
    """The plugin store, its master switch and the detail sheet (source, permission
    families, content hash)."""
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.wait_for_timeout(1000)

    # The plugin page is a Settings section now (settings/model/sections-plugins.tsx,
    # nav key "plugins") — the settings sheet is its entry point; the dashboard has no
    # plugin panel to open.
    _js_click(page, "sidebar-settings-btn")
    page.wait_for_selector('[data-testid="settings-nav-plugins"]', timeout=10000)
    page.locator('[data-testid="settings-nav-plugins"]').click()
    page.wait_for_selector('[data-testid="plugins-master-toggle"]', timeout=10000)
    page.wait_for_timeout(1200)

    # master switch round-trip — every state renders honestly
    page.locator('[data-testid="plugins-master-toggle"]').first.click(timeout=6000)
    page.wait_for_timeout(1600)
    page.locator('[data-testid="plugins-master-toggle"]').first.click(timeout=6000)
    page.wait_for_timeout(1600)

    # detail sheet of the first plugin: source, permissions, content hash
    page.locator('[data-testid^="plugin-detail-toggle-"]').first.click(timeout=6000)
    page.wait_for_timeout(2400)


def clip_mobile(page: Page) -> None:
    page.goto(f"{VITE}/#/chat", wait_until="load")
    page.wait_for_selector(COMPOSER, timeout=20000)
    page.wait_for_timeout(2200)
    suppress_task_dock(page)

    # Mobile header uses the hamburger (the PanelLeft toggle is lg-only)
    page.locator('button[aria-label="Toggle menu"]').dispatch_event("click")
    page.wait_for_timeout(1500)
    # the drawer covers the backdrop's center at 390px — close via its own button
    page.locator('aside[aria-label="Sidebar"] button[aria-label="Close"]').dispatch_event("click")
    page.wait_for_timeout(900)

    human_type(
        page,
        COMPOSER,
        "Plan a three-step launch checklist for a local-first app. Keep it under 60 words.",
        delay=40,
    )
    send_and_wait(page, done_timeout=120_000, label="mobile chat turn")
    page.wait_for_timeout(1600)
    dismiss_task_dock(page)


# WebP conversion


def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-400:]}")


def _gif_to_webp(gif: Path, out: Path) -> None:
    result = subprocess.run(
        ["gif2webp", "-lossy", "-q", "80", "-m", "5", str(gif), "-o", str(out)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gif2webp failed: {result.stderr[-400:]}")


def _duration(webm: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(webm),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return float(out.stdout.strip() or 0.0)


def to_webp(
    webm: Path,
    out: Path,
    mobile: bool = False,
    small: bool = False,
    trim_start: float = 0.1,
    tail_seconds: float | None = None,
) -> None:
    if tail_seconds:
        # A long tool turn is mostly waiting. The header row already names the task,
        # so the clip keeps the end where the answer lands and drops the dead air.
        total = _duration(webm)
        if total > trim_start + tail_seconds:
            trim_start = total - tail_seconds
    if mobile:
        ladder = [(390, 12), (340, 10)]
    elif small:
        # A full-screen first-run film is the heaviest clip; 560 px keeps the
        # tour's type readable while the file stays in the same class as the rest.
        ladder = [(640, 8), (560, 6)]
    else:
        # The capture is 2x the viewport, so the top rung downsamples from more
        # pixels than the README ever shows; type stays crisp on a retina display.
        ladder = [(1160, 12), (960, 10), (840, 8), (840, 5)]
    for width, fps in ladder:
        palette = TEMP / f"pal_{width}_{fps}.png"
        intermediate = TEMP / f"{out.stem}-{width}-{fps}.gif"
        _run_ffmpeg([
            "ffmpeg", "-y", "-ss", str(trim_start), "-i", str(webm),
            "-vf", f"fps={fps},scale={width}:-2:flags=lanczos,palettegen=stats_mode=diff",
            str(palette),
        ])
        _run_ffmpeg([
            "ffmpeg", "-y", "-ss", str(trim_start), "-i", str(webm), "-i", str(palette),
            "-lavfi",
            f"fps={fps},scale={width}:-2:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4",
            "-loop", "0",
            str(intermediate),
        ])
        _gif_to_webp(intermediate, out)
        intermediate.unlink(missing_ok=True)
        size = out.stat().st_size
        print(f"    {out.name}: {size / 1024 / 1024:.2f} MB ({width}px @{fps}fps, WebP)")
        if size <= WEBP_TARGET_BYTES:
            return
    print(f"    [WARN] {out.name} stays above target size")


# Terminal clip
#
# The TUI is recorded through a real pty and rendered by agg, so the frames carry the
# same terminal the product runs in. The driver waits for screen text (the approval
# legend) instead of a clock, because the engine decides how long a turn takes.

TUI_COLS, TUI_ROWS = 108, 30
TUI_MAX_APPROVALS = 8
TUI_TASK = (
    "Add a discount_total(items, percent) helper to invoices/totals.py that takes a "
    "percentage off the invoice total, add a test for it, then run pytest."
)


def _tui_project(ws: Path) -> None:
    """The demo repository the terminal clip works in — never this checkout."""
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "README.md").write_text(
        "# Invoice totals\n\nA small tool that adds up invoice line items.\n"
    )
    pkg = ws / "invoices"
    pkg.mkdir(exist_ok=True)
    (pkg / "totals.py").write_text(
        '"""Invoice totals: line items in, one number out."""\n'
        "\n"
        "\n"
        "def line_total(qty: int, unit_price: float) -> float:\n"
        "    return round(qty * unit_price, 2)\n"
        "\n"
        "\n"
        "def invoice_total(items: list[dict]) -> float:\n"
        "    return round(sum(line_total(i['qty'], i['unit_price']) for i in items), 2)\n"
    )
    (pkg / "test_totals.py").write_text(
        "from invoices.totals import invoice_total, line_total\n"
        "\n"
        "\n"
        "def test_line_total_rounds_to_cents():\n"
        "    assert line_total(3, 19.99) == 59.97\n"
        "\n"
        "\n"
        "def test_invoice_total_adds_lines():\n"
        "    items = [{'qty': 2, 'unit_price': 10.0}, {'qty': 1, 'unit_price': 5.5}]\n"
        "    assert invoice_total(items) == 25.5\n"
    )
    (ws / "pytest.ini").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    for step in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "demo@example.invalid"],
        ["git", "config", "user.name", "Demo"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "invoice totals with two tests"],
    ):
        subprocess.run(step, cwd=ws, check=True, capture_output=True)


def record_tui_cast(cast: Path, cfg: Path, ws: Path, engine: Path) -> None:
    """Drive ``ephe tui`` in a pty and write the byte stream as an asciicast v2 file."""
    import fcntl
    import json
    import pty
    import select
    import struct
    import termios

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update({"TERM": "xterm-256color", "EPHE_CONFIG_DIR": str(cfg)})
    key = engine_api_key()
    if key:
        env["EPHE_OPENAI_COMPAT_API_KEY"] = key
    chosen = json.loads(engine.read_text())
    chosen["workspace_dir"] = str(ws)
    (cfg / "engine.json").write_text(json.dumps(chosen, indent=2))

    pid, master = pty.fork()
    if pid == 0:
        os.chdir(ws)
        os.execvpe(
            str(ROOT / ".venv" / "bin" / "python"),
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "ephe_cli.py"), "tui"],
            env,
        )
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", TUI_ROWS, TUI_COLS, 0, 0))

    events: list[tuple[float, str]] = []
    pending = bytearray()
    started = time.time()
    deadline = started + 300.0
    last_activity = started
    stage = 0
    answered = 0

    def send(data: str) -> None:
        pending.clear()
        os.write(master, data.encode())

    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            now = time.time()
            events.append((now - started, chunk.decode("utf-8", "replace")))
            pending += chunk
            last_activity = now
        elapsed = time.time() - started
        if stage == 0 and elapsed > 4.0:
            send(TUI_TASK)
            stage = 1
        elif stage == 1 and elapsed > 5.5:
            send("\r")
            stage = 2
        elif stage == 2:
            if b"Always" in pending[-9000:] and answered < TUI_MAX_APPROVALS:
                send("a")
                answered += 1
            elif time.time() - last_activity > 25.0:
                # Still for 25 s with no prompt open: the answer has landed and the
                # reader has had it on screen. Anything longer is dead air.
                break

    time.sleep(2.0)
    try:
        os.write(master, b"\x03")
        time.sleep(0.6)
    except OSError:
        pass
    os.close(master)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    header = {
        "version": 2,
        "width": TUI_COLS,
        "height": TUI_ROWS,
        "timestamp": int(started),
        "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"},
    }
    with cast.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")
        for at, data in events:
            fh.write(json.dumps([round(at, 4), "o", data]) + "\n")
    print(f"    cast: {len(events)} events over {events[-1][0]:.1f}s")


def tui_clip(engine: Path) -> None:
    cast = TEMP / "ephe-demo-tui.cast"
    gif = TEMP / "ephe-demo-tui.gif"
    ws = TEMP / "tui-workspace"
    cfg = TEMP / "tui-config"
    cfg.mkdir(parents=True, exist_ok=True)
    _tui_project(ws)
    record_tui_cast(cast, cfg, ws, engine)
    result = subprocess.run(
        [
            "agg", str(cast), str(gif),
            "--font-size", "17",
            "--line-height", "1.3",
            "--idle-time-limit", "1.2",
            "--speed", "1.25",
            "--theme", "asciinema",
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        raise RuntimeError(f"agg failed: {result.stderr[-400:]}")
    _gif_to_webp(gif, MEDIA / "ephe-demo-tui.webp")
    gif.unlink(missing_ok=True)
    cast.unlink(missing_ok=True)


# Recording


def record_clip(browser: Browser, name: str, runner, mobile: bool = False) -> Path:
    """One context per clip: the video file of a clip is therefore the only .webm in its
    own folder (no newest-file race), and every clip starts on a clean local store —
    the sidebar of a later clip shows what the isolated mirror holds, nothing else."""
    record_dir = TEMP / f"rec-{name}"
    record_dir.mkdir(parents=True, exist_ok=True)
    viewport: ViewportSize = (
        {"width": MOBILE_W, "height": MOBILE_H}
        if mobile
        else {"width": DESKTOP_W, "height": DESKTOP_H}
    )
    context = browser.new_context(
        viewport=viewport,
        device_scale_factor=2,
        is_mobile=mobile,
        has_touch=mobile,
        record_video_dir=str(record_dir),
        # Playwright pads the screencast to a size larger than the viewport instead
        # of rendering at device scale, so the video stays at the CSS viewport and
        # the crispness comes from device_scale_factor plus the downscale below.
        record_video_size=viewport,
    )
    context.add_init_script(ONBOARDING_INIT if name == "onboarding" else INIT_SCRIPT)
    page = context.new_page()
    try:
        runner(page)
    finally:
        # context.close() flushes the video; a page.close() alone leaves the file open
        context.close()
    return newest_webm(record_dir)


DESKTOP_CLIPS = {
    "onboarding": clip_onboarding,
    "chat": clip_chat,
    "artifacts": clip_artifacts,
    "budget": clip_budget,
    "launch": clip_launch,
    "agent-panel": clip_agent_panel,
    "palette": clip_palette,
    "plugins": clip_plugins,
}


def main() -> None:
    global VITE, TERMINAL_PANE

    only = None
    keep_root = False
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only = {name.strip() for name in arg.split("=", 1)[1].split(",")}
        elif arg == "--keep-root":
            keep_root = True

    shutil.rmtree(TEMP, ignore_errors=True)
    TEMP.mkdir(parents=True)
    MEDIA.mkdir(exist_ok=True)

    stack = DemoStack(keep_root=keep_root)
    print("starting the isolated pair ...")
    try:
        stack.start()
        VITE = stack.vite_url
        TERMINAL_PANE = stack.ws_supported

        wanted = lambda name: only is None or name in only  # noqa: E731
        steps = [(n, r) for n, r in DESKTOP_CLIPS.items() if wanted(n)]
        if wanted("mobile"):
            steps.append(("mobile", clip_mobile))

        # The onboarding clip needs the device marker absent; every other clip
        # needs it walked, or the four questions would cover their first frame.
        tour_marker = stack.root / "tour.json"
        if wanted("onboarding"):
            tour_marker.unlink(missing_ok=True)

        # Each clip is converted the moment it is recorded, so a later failure (or a
        # reboot) cannot cost the clips that are already done.
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                for i, (name, runner) in enumerate(steps, 1):
                    print(f"[{i}/{len(steps)}] recording {name} ...")
                    mobile = name == "mobile"
                    webm = record_clip(browser, name, runner, mobile=mobile)
                    if name == "onboarding":
                        tour_marker.write_text(
                            json.dumps(
                                {
                                    "version": 1,
                                    "step": 5,
                                    "walked": True,
                                    "skipped": True,
                                    "answers": {},
                                },
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    print(f"    captured {name}.webm")
                    to_webp(
                        webm,
                        MEDIA / f"ephe-demo-{name}.webp",
                        mobile=mobile,
                        small=name in {"onboarding", "artifacts"},
                        trim_start=TRIM_START.get(name, 0.1),
                        tail_seconds=TAIL_SECONDS.get(name),
                    )
                    webm.unlink()
            finally:
                browser.close()

        if wanted("tui"):
            print("[tui] recording the terminal through a pty ...")
            tui_clip(stack.root / "engine.json")
    finally:
        stack.stop()
        if keep_root:
            print(f"    temp kept: {TEMP}")
        else:
            shutil.rmtree(TEMP, ignore_errors=True)

    print("\nDone. README assets refreshed in docs/media/ + docs/screenshots/hero-banner.png")


if __name__ == "__main__":
    start = time.time()
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    print(f"Total: {time.time() - start:.1f}s")
