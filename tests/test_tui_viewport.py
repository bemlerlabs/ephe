"""The TUI viewport: status bar, footer and brand header each paint a row of text.

Driven through Textual's own compositor at a fixed viewport, because a box whose border
consumed its single row renders no text at all — a fact the widget tree cannot report and
the exported screenshot can.
"""
from __future__ import annotations

import asyncio
import html
import importlib.util
import re
import statistics
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

from textual.widgets import Footer

from core import __version__
from ui.app import EpheApp
from ui.widgets import ChatView

REPO = Path(__file__).resolve().parent.parent
VIEWPORT: tuple[int, int] = (120, 32)
MODEL = "viewport-model"
API_URL = "http://127.0.0.1:9/v1"
API_HOST = "127.0.0.1:9"


def _load_inventory():
    """The language gate's own instrument, loaded the way its tests load it."""
    spec = importlib.util.spec_from_file_location(
        "language_inventory_under_test", REPO / "scripts" / "language_inventory.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory = _load_inventory()


def _text_cells(svg: str) -> list[tuple[float, float, float, str]]:
    """Every text cell of a screenshot, as (x, y, cell width, text)."""
    cells: list[tuple[float, float, float, str]] = []
    for attrs, body in re.findall(r"<text\b([^>]*)>(.*?)</text>", svg, re.S):
        def attribute(name: str) -> str:
            found = re.search(rf'\b{name}="([^"]*)"', attrs)
            return found.group(1) if found else ""

        text = html.unescape(re.sub(r"<[^>]+>", "", body)).replace("\xa0", " ")
        cells.append(
            (float(attribute("x")), float(attribute("y")), float(attribute("textLength") or 0), text)
        )
    return cells


def _screen_rows(svg: str) -> list[str]:
    """The screen of a screenshot, one string per rendered row."""
    cells = _text_cells(svg)
    ratios = [width / len(text) for _x, _y, width, text in cells if len(text) >= 8 and width]
    pitch = statistics.median(ratios)
    rows: dict[float, dict[int, str]] = {}
    for x, y, _width, text in cells:
        line = rows.setdefault(round(y, 1), {})
        column = round(x / pitch)
        for offset, char in enumerate(text):
            line[column + offset] = char
    return [
        "".join(line.get(index, " ") for index in range(max(line) + 1)).rstrip()
        for _y, line in sorted(rows.items())
    ]


def _row_with(rows: list[str], needle: str) -> str:
    """The first rendered row carrying `needle`, or an empty string when none does."""
    return next((row for row in rows if needle in row), "")


class Viewport(NamedTuple):
    """One headless run: the painted screen, the box heights and the bindings."""

    rows: list[str]
    heights: dict[str, int]
    chat_text: str
    painted_bindings: list[tuple[str, str]]
    shown_descriptions: list[str]


def _snapshot() -> Viewport:
    """Run the app headless at the fixed viewport and collect what it painted."""
    app = EpheApp(model=MODEL, api_url=API_URL)

    async def main() -> Viewport:
        async with app.run_test(size=VIEWPORT) as pilot:
            await pilot.pause(1.0)
            rows = _screen_rows(app.export_screenshot(title="viewport"))
            heights = {
                "status": app.query_one("#status-bar").content_size.height,
                "header": app.query_one("#brand-header").content_size.height,
                "footer": app.query_one(Footer).content_size.height,
            }
            painted_bindings = [
                (app.get_key_display(state.binding), state.binding.description)
                for state in app.screen.active_bindings.values()
                if state.binding.show and state.enabled
            ]
            shown_descriptions = [
                binding.description for binding in EpheApp.BINDINGS if binding.show
            ]
            chat_text = "\n".join(str(block.content) for block in app.query(".static-block"))
            return Viewport(rows, heights, chat_text, painted_bindings, shown_descriptions)

    return asyncio.run(main())


_SHOT: dict[str, Viewport] = {}


def viewport() -> Viewport:
    """The viewport of the one headless run this module shares."""
    if "shot" not in _SHOT:
        _SHOT["shot"] = _snapshot()
    return _SHOT["shot"]


def test_status_bar_paints_its_content_row():
    """GIVEN the app rendered at a fixed viewport
    THEN the status bar holds a content row naming engine, provider, model and meter."""
    shot = viewport()
    assert shot.heights["status"] >= 1
    row = _row_with(shot.rows, "Engine: ")
    assert row, "the status bar indicator reached no screen row"
    assert MODEL in row
    assert API_HOST in row
    assert "ctx " in row


def test_footer_paints_every_active_binding():
    """GIVEN the bindings Textual holds active under the focused input
    THEN each key and its label sit on the footer row of the screen."""
    shot = viewport()
    assert shot.heights["footer"] >= 1
    assert {key for key, _label in shot.painted_bindings} >= {"^r", "^l"}
    row = _row_with(shot.rows, shot.painted_bindings[0][0])
    assert row, "no screen row carries the first painted binding's key"
    for key, description in shot.painted_bindings:
        assert key in row
        assert description in row


def test_brand_header_paints_the_moth_beside_the_wordmark():
    """GIVEN the brand header
    THEN it holds the moth's three lines, and the mark, name and version stand
    apart on the line the moth is widest."""
    from ui.terminal_mark import MARK_HEAD

    shot = viewport()
    assert shot.heights["header"] == len(MARK_HEAD)
    row = _row_with(shot.rows, "Ephe")
    assert row
    assert re.search(r"Ephe\s+v", row), row
    assert f"v{__version__}" in row
    assert MARK_HEAD[1].strip() in row


def test_greeting_hint_lists_every_shown_binding():
    """GIVEN the bindings the app declares with show=True
    THEN the greeting names each one, so hint and Footer read from one source."""
    shot = viewport()
    assert shot.shown_descriptions
    for description in shot.shown_descriptions:
        assert f"= {description}" in shot.chat_text
    assert "Ctrl+R" in shot.chat_text
    assert "Ctrl+L" in shot.chat_text


def test_provider_label_names_the_configured_endpoint():
    """GIVEN a base URL on a cloud host
    THEN the status label reads that host and claims no other vendor."""
    api_url = "https://api.deepseek.com/v1"
    app = EpheApp(model="deepseek-chat", api_url=api_url)
    label = app._provider_label()
    # The label's last segment is the host; comparing it whole is the check CodeQL calls
    # complete, and it fails on a lookalike host the way a substring test would not.
    assert label.rsplit("·", 1)[-1].strip() == urlparse(api_url).netloc
    assert "DGX" not in label


def test_provider_label_names_the_local_provider(monkeypatch):
    """GIVEN a local engine chosen in the env
    THEN the label carries that provider's own name and base URL."""
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    monkeypatch.setenv("EPHE_MODEL", "qwen3:8b")
    monkeypatch.setenv("EPHE_LOCAL_OLLAMA_BASE_URL", "http://127.0.0.1:12345")
    label = EpheApp(model="qwen3:8b")._provider_label()
    assert "Local Ollama" in label
    assert label.rsplit("·", 1)[-1].strip() == urlparse("http://127.0.0.1:12345").netloc


def test_engine_down_text_names_the_active_provider(monkeypatch):
    """GIVEN a remote Ollama in the env
    THEN the engine-down text names that provider and its endpoint."""
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "custom_ollama")
    monkeypatch.setenv("EPHE_MODEL", "qwen3:8b")
    monkeypatch.setenv("EPHE_CUSTOM_OLLAMA_BASE_URL", "http://192.168.1.50:11434")
    status_text, body = EpheApp(model="qwen3:8b")._engine_down_text()
    assert "Custom Ollama" in status_text
    assert "192.168.1.50:11434" in body


def test_source_names_only_the_live_version():
    """GIVEN the shipped version
    THEN the TUI source carries no version literal besides it."""
    source = (REPO / "ui" / "app.py").read_text(encoding="utf-8")
    literals = set(re.findall(r"v\d+\.\d+\.\d+[-\w.]*", source))
    assert literals <= {f"v{__version__}"}


def test_terminal_surface_shows_no_german():
    """GIVEN the two TUI modules
    THEN German survives only in the correction keywords the input matcher reads."""
    def read(rel: str) -> str:
        return (REPO / rel).read_text(encoding="utf-8")

    counts = inventory.counts_for(["ui/app.py", "ui/widgets.py"], read)
    assert counts.get("ui/widgets.py", 0) == 0
    german_lines = [line for line in read("ui/app.py").splitlines() if inventory.hits_in(line)]
    assert all("correction_keywords" in line for line in german_lines), german_lines


def test_confirm_prompt_legend_reads_english():
    """GIVEN the in-TUI approval prompt
    THEN its key legend is the English one the rest of the surface uses."""
    app = EpheApp(model=MODEL, api_url=API_URL)
    rows: list[str] = []

    async def main() -> None:
        async with app.run_test(size=VIEWPORT) as pilot:
            await pilot.pause(1.0)
            await app.query_one(ChatView).show_confirm_prompt(
                "Run shell command?  ls -la", "run_shell"
            )
            await pilot.pause(0.5)
            rows.extend(_screen_rows(app.export_screenshot(title="confirm")))

    asyncio.run(main())
    legend = _row_with(rows, "=Yes")
    assert legend
    assert "=No" in legend
    assert "Always" in legend
    assert not _row_with(rows, "=Ja")
    assert not _row_with(rows, "=Nein")
