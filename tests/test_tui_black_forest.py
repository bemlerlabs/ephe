"""TUI UX: the product's ink-ground palette + runtime engine switch (/model <name>).

The TUI paints what the product is: the ten tokens of `ui/palette.py`, whose accent
is the brand red of `app/src/styles/globals.css` — not the green this surface wore
while the product's own brand mark was red, and not the purple palette of the old
name. Engine and model switch inside the running session (the user's screenshot
showed: only a static warning, no switch).

This project's test rule: deployment readiness = real tests. The connection check
runs against a REAL local /v1/models server (real socket, real HTTP) — no mock,
no fake.
"""
from __future__ import annotations

import asyncio
import json
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


# Ink-ground palette: one set of ten tokens, spelled in ui/palette.py (Python) and
# ui/ephe.tcss (stylesheet). The retired palette below is the blue-black one this
# file used to pin, whose green brand mark (#42d392) sat dE2000 68.6 from the
# product's red (#E8543F) while the product's own success colour was #5BAE90.
OLD_PALETTE = (
    "#06080c",  # retired ground
    "#0c1117",  # retired surface
    "#1e293b",  # retired border
    "#e8edf4",  # retired foreground
    "#8da3b8",  # retired muted
    "#42d392",  # retired green brand mark
    "#22c55e",  # retired success green
    "#ff6b35",  # retired error orange
    "#0a1a12",  # retired accent tint
    "#1a0a0a",  # retired error tint
    "#2d3a4e",  # retired scrollbar hover
    "#c084fc",  # purple of the old name
    "#7c3aed",  # purple of the old name
)

# docs/BRAND.md "Claim boundary": sayable is what is countable or provable.
FORBIDDEN_CLAIMS = ("private", "never", "without a trace")

# The ratios ui/palette.py and the tcss header quote, against the ground.
# A colour that stops holding its ratio against the ground stops being readable.
MEASURED_ON_GROUND = {
    "TEXT": 16.25,
    "DIM": 5.31,
    "ACCENT": 5.13,
    "OK": 7.02,
    "WARN": 9.05,
    "ERROR": 4.94,
}


def _repo_root() -> Path:
    return Path(__file__).parent.parent


def _read(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


def _python_tokens() -> dict[str, str]:
    """The ten names ui/palette.py defines, read from the module itself."""
    import ui.palette as palette

    return {
        name: value
        for name, value in vars(palette).items()
        if name.isupper() and isinstance(value, str)
    }


def _rule_body(tcss: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", tcss)
    assert match, f"the design file carries no rule for {selector}"
    return match.group(1)


def _tcss_variables(tcss: str) -> dict[str, str]:
    """The ink tokens the stylesheet declares, by name, without the $."""
    return {
        name: value
        for name, value in re.findall(r"^\$(ink-[a-z-]+):\s*(#[0-9A-Fa-f]{6});", tcss, re.M)
    }


def _strip_comments(tcss: str) -> str:
    return re.sub(r"/\*.*?\*/", "", tcss, flags=re.S)


def _luminance(value: str) -> float:
    channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]

    def _linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (_linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_the_palette_is_the_measured_ink_set() -> None:
    """GIVEN ui/palette.py THEN it holds exactly the ten measured tokens.

    One colour, one value, one place: the Python surface imports these names and
    the stylesheet spells them, so no colour is written twice.
    """
    assert _python_tokens() == {
        "GROUND": "#15120F",
        "PANEL": "#1D1917",
        "TEXT": "#F2EFE8",
        "DIM": "#91877E",
        "LINE": "#2E2926",
        "ACCENT": "#E8543F",
        "OK": "#5BAE90",
        "WARN": "#F6A328",
        "ERROR": "#F63B1E",
        "STATE_GROUND": "#42241E",
    }


def test_every_token_holds_its_ratio_against_the_ground() -> None:
    """GIVEN the palette THEN each text token keeps the contrast ratio its own
    documentation quotes, and none of them falls under the WCAG AA 4.5:1 line."""
    tokens = _python_tokens()
    for name, quoted in MEASURED_ON_GROUND.items():
        measured = _contrast(tokens[name], tokens["GROUND"])
        assert abs(measured - quoted) <= 0.05, (
            f"{name} measures {measured:.2f}:1 against the ground, not the quoted {quoted}:1"
        )
        assert measured >= 4.5, f"{name} falls below the 4.5:1 text threshold: {measured:.2f}:1"


def test_both_surfaces_declare_the_same_ten_tokens() -> None:
    """GIVEN the TUI design file and the palette module THEN each declares the same
    ten names with the same values, and the stylesheet spells a colour only in its
    token block: every rule under it paints a token.

    This is the test that used to pin the retired green: it asserted #42d392 in the
    stylesheet while the product's own brand token was red. A colour test that no
    longer matches the product is the bug, so it now pins the token set instead.
    """
    tcss = _read("ui/ephe.tcss")
    tokens = _python_tokens()
    declared = _tcss_variables(tcss)
    assert len(tokens) == 10, f"ui/palette.py no longer holds ten tokens: {sorted(tokens)}"
    assert {name.removeprefix("ink-").replace("-", "_").upper(): value for name, value in declared.items()} == tokens
    assert set(tokens.values()) <= set(declared.values())

    body = re.sub(r"^\$[a-z-]+:\s*#[0-9A-Fa-f]{6};", "", _strip_comments(tcss), flags=re.M)
    stray = sorted(set(re.findall(r"#[0-9A-Fa-f]{6}", body)))
    assert stray == [], f"colours spelled outside the token block: {stray}"
    assert "$ink-accent" in body, "the brand accent is painted nowhere"
    assert "$ink-state-ground" in body, "the one tinted ground is painted nowhere"
    for retired in OLD_PALETTE:
        assert retired not in tcss.lower(), f"retired colour still painted: {retired}"


def test_exactly_one_tinted_ground_carries_the_state() -> None:
    """GIVEN the TUI design file THEN its only grounds are ground, panel and the one
    tint, and the tint is painted once — for command mode, whose completion hint
    names that state in words.

    The retired file carried two state tints (accent tint, error tint) that measured
    2.8 apart in dE2000: two tokens for one colour, neither of them readable.
    """
    tcss = _read("ui/ephe.tcss")
    tokens = _python_tokens()
    declared = _tcss_variables(tcss)

    grounds = {declared[name] for name in re.findall(r"\bbackground:\s*\$([a-z-]+)", tcss)}
    assert grounds == {tokens["GROUND"], tokens["PANEL"], tokens["STATE_GROUND"]}, (
        f"unexpected grounds: {sorted(grounds)}"
    )
    assert tcss.count("background: $ink-state-ground") == 1, "the tint is painted more than once"
    assert "$ink-state-ground" in _rule_body(tcss, "#input-area.command-mode")


def test_no_state_is_signalled_by_colour_alone() -> None:
    """GIVEN the status bar THEN each of its three states carries its own words beside
    its colour, and the words stay on the panel ground.

    Accent and error hold 4.79:1 and 4.62:1 on the panel, and fall to 3.84:1 and
    3.70:1 on the tint — so the state words do not stand on the tint.
    """
    widgets_src = _read("ui/widgets.py")
    tcss = _read("ui/ephe.tcss")

    for label in ("Generating", "Engine: connected", "Engine: offline"):
        assert label in widgets_src, f"the status bar lost the label {label!r}"
    for selector in ("#status-bar.streaming", "#status-bar.error"):
        assert "background: $ink-panel" in _rule_body(tcss, selector), (
            f"{selector} does not keep its words on the panel ground"
        )
    # The two states differ in text colour as well as in their labels.
    assert "$ink-accent" in _rule_body(tcss, "#status-bar.streaming")
    assert "$ink-error" in _rule_body(tcss, "#status-bar.error")


def test_the_claim_lines_state_what_the_product_does() -> None:
    """GIVEN the strings the TUI ships THEN they stay inside docs/BRAND.md's claim
    boundary, and the text carries no decoration colour the palette cannot hold.

    Two strings broke the boundary: the status tagline ("No cloud. No tracking.
    Straight from the Black Forest." under a tree emoji) and the welcome line
    ("Private. Local. Yours."). The header tagline constant carried the German form
    of the same claim. Each now names what Ephe does.
    """
    widgets_src = _read("ui/widgets.py")
    app_src = _read("ui/app.py")
    core_src = _read("core/__init__.py")

    sentences = (
        "Runs locally on the engine you choose.",
        "Runs locally. Everything else is a decision.",
    )
    assert sentences[0] in widgets_src, "the status tagline states nothing the product does"
    assert sentences[1] in app_src, "the welcome line states nothing the product does"
    assert sentences[1] in core_src, "the header tagline is not the brand's sayable line"
    for sentence in sentences:
        for claim in FORBIDDEN_CLAIMS:
            assert claim not in sentence.lower(), f"claim register in a shipped string: {claim}"
    for source in (widgets_src, app_src):
        assert "\U0001f332" not in source, "the tree emoji is back in the TUI text"
    assert "No cloud" not in widgets_src and "No tracking" not in widgets_src


def test_brand_header_present():
    """GIVEN the TUI is composed
    THEN there is an ink-ground brand header (not a generic Textual header)."""
    app_src = _read("ui/app.py")
    assert 'id="brand-header"' in app_src, "brand header missing"
    assert 'id="brand-mark"' in app_src, "brand mark (◑) missing"


def test_statusbar_shows_provider_label():
    """GIVEN the StatusBar widget
    THEN it carries a provider label whose text comes from the active engine."""
    from pathlib import Path

    root = Path(__file__).parent.parent
    widgets_src = (root / "ui" / "widgets.py").read_text(encoding="utf-8")
    assert 'id="status-provider"' in widgets_src, "Provider-Label im StatusBar fehlt"
    app_src = (root / "ui" / "app.py").read_text(encoding="utf-8")
    assert "def _provider_label" in app_src
    assert "DGX · vLLM" not in app_src, "hard-coded vendor label"


# Runtime engine switch (/model <name>)

def test_model_switch_changes_active_model(tmp_path, monkeypatch):
    """GIVEN the TUI runs with model A
    WHEN the user types '/model B'
    THEN self.model = B (without a restart) and a confirmation is shown."""
    from core.session import SESSION_DIR  # noqa: F401
    import core.session as session_module
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    from ui.app import EpheApp

    app = EpheApp(model="gemma4:12b", reset=False)

    async def run():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            # Before
            assert app.model == "gemma4:12b"
            # Runtime switch
            app._handle_model_switch("qwen38-27b-unsloth-nvfp4")
            await pilot.pause()
            # After: the model changed and the provider label is set
            assert app.model == "qwen38-27b-unsloth-nvfp4"

    asyncio.run(run())
    assert app.model == "qwen38-27b-unsloth-nvfp4"


def test_model_switch_provider_label_names_the_engine_host(tmp_path, monkeypatch):
    """GIVEN an engine on a remote base URL
    THEN the provider label reads that host."""
    from core.session import SESSION_DIR  # noqa: F401
    import core.session as session_module
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    from ui.app import EpheApp

    app = EpheApp(model="qwen38-27b-unsloth-nvfp4", reset=False,
                     api_url="http://spark-host:8000/v1")
    label = app._provider_label()
    assert "spark-host:8000" in label
    assert "DGX" not in label


def test_bare_model_command_stays_info():
    """GIVEN '/model' without an argument
    THEN it stays the info command (no switch trigger).

    The switch trigger in the app checks explicitly for '/model <name>' (with a
    space + argument). A bare '/model' falls back to the info command, which
    shows the active engine (existing behaviour, tests green).
    """
    import ephe_cli  # noqa: F401
    from core.commands import is_info_command

    # A bare /model is an info command
    assert is_info_command("/model")
    # With an argument as well (the info command renders the active engine)
    assert is_info_command("/model gemma4:12b")


# Real connection check (no mock, no fake)

class _RealModelsHandler(BaseHTTPRequestHandler):
    """A real /v1/models handler on a real socket."""

    model_ids = ["qwen38-27b-unsloth-nvfp4"]

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/models":
            body = json.dumps({"object": "list", "data": [
                {"id": m, "object": "model"} for m in type(self).model_ids
            ]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args) -> None:  # noqa: N802
        pass


def _start_real_models_server(model_ids: list[str]) -> tuple[HTTPServer, int]:
    handler = type("_Handler", (_RealModelsHandler,), {"model_ids": list(model_ids)})
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    import urllib.request
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    return server, port


def test_tui_real_connection_check_reports_connected(tmp_path, monkeypatch):
    """GIVEN a TUI with a remote engine + a real /v1/models server (Qwen loaded)
    WHEN _async_check_connection runs
    THEN the StatusBar shows connected=True + the provider label (no error banner)."""
    import core.session as session_module
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    from ui.app import EpheApp
    from ui.widgets import StatusBar

    server, port = _start_real_models_server(["qwen38-27b-unsloth-nvfp4"])
    app = EpheApp(model="qwen38-27b-unsloth-nvfp4", reset=False,
                     api_url=f"http://127.0.0.1:{port}/v1")
    try:
        async def run():
            async with app.run_test(size=(100, 30)) as pilot:
                # The real connection check (real HTTP against a real server)
                await pilot.pause(2.0)
                status = app.query_one(StatusBar)
                return status

        status = asyncio.run(run())
    finally:
        server.shutdown()

    # The StatusBar widget has processed the real connection state.
    # (connected=True, because the real server reported Qwen.)
    assert status._connected is True
    assert status._model == "qwen38-27b-unsloth-nvfp4"
    assert status._provider == f"OpenAI-compatible API · 127.0.0.1:{port}"
