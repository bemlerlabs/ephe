"""The terminal mark: the shipped vector, and nothing invented beside it.

`ui/terminal_mark.py` is generated from `app/src/assets/mark-mono.svg` by
`scripts/generate_terminal_mark.py`. These tests keep the two tied together, so a
change to the icon reaches the terminal only through the generator, and check the
boot card that carries it.
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GENERATOR = REPO / "scripts" / "generate_terminal_mark.py"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load("generate_terminal_mark_under_test", "scripts/generate_terminal_mark.py")


def test_the_committed_grid_is_the_vector_measured(gen):
    """GIVEN the shipped template cut
    WHEN the generator folds it to the committed grid
    THEN the file in ui/ is what the vector says at the grid it names."""
    from ui.terminal_mark import MARK_GRID, MARK_ROWS

    shapes = gen.coverages(gen.SOURCE.read_text(encoding="utf-8"))
    assert gen.render(shapes, *MARK_GRID) == list(MARK_ROWS)


def test_the_mark_is_one_plane_on_its_own_axis(gen):
    """GIVEN a terminal cell carries no colour here
    THEN every glyph of the grid comes from the ramp, and the silhouette's mass
    sits on the middle of its own bounding box — the axis `mark_contract.py`
    measures on the vector."""
    from ui.terminal_mark import MARK_ROWS

    assert set("".join(MARK_ROWS)) <= set(gen.RAMP)
    ink = [(row, col) for row, line in enumerate(MARK_ROWS)
           for col, ch in enumerate(line) if ch != " "]
    left = min(col for _, col in ink)
    right = max(col for _, col in ink)
    centre = sum(col for _, col in ink) / len(ink)
    assert abs(centre - (left + right) / 2) <= 1.0


def test_the_generator_reads_the_commands_the_mark_writes(gen):
    """GIVEN a path body
    THEN the closed subpaths come back as polygons, and a command the sampler
    does not implement contributes no outline rather than a wrong one."""
    assert gen._polygons("M10,10 L20,10 L20,20 Z") == [
        [(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 10.0)]
    ]
    assert gen._polygons("M10,10 A5,5 0 0 1 20,20 Z") == []


@pytest.mark.asyncio
async def test_the_boot_card_carries_the_mark_and_the_wordmark(tmp_path, monkeypatch):
    """GIVEN a first session with no messages
    WHEN the terminal paints its greeting
    THEN the bee and the wordmark are on the same screen, and the key legend
    still reaches the reader."""
    from core import multi_session as ms

    entry = ms.create_session("Boot card")
    ms.switch_to(str(entry["id"]))

    from ui.app import EpheApp
    from ui.terminal_mark import MARK_ROWS

    app = EpheApp(model="boot-card", reset=False)

    async def noop() -> None:
        return None

    monkeypatch.setattr(app, "_async_check_connection", noop)
    monkeypatch.setattr(app, "_async_init_mcp", noop)

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.6)
        assert app._exception is None
        painted = "\n".join(
            block.content.plain
            for block in app.query(".static-block")
            if hasattr(block.content, "plain")
        )
        assert "Ephe" in painted
        assert MARK_ROWS[0].strip() in painted
        assert "Ctrl+P" in painted
