"""The terminal mark: the mastered cut, and nothing invented beside it.

`ui/terminal_mark.py` is generated from `docs/media/paper-moth-master.png` by
`scripts/generate_terminal_mark.py`. These tests keep the two tied together, so a
change to the cut reaches the terminal only through the generator, and check the
boot card that carries it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

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


def test_the_committed_cuts_are_the_master_measured(gen):
    """GIVEN the mastered cut
    WHEN the generator folds it at the two grids the module names
    THEN the rows in ui/ are what the alpha channel says at those grids."""
    from ui.terminal_mark import MARK_GRID, MARK_HEAD, MARK_HEAD_GRID, MARK_ROWS

    image = gen.cut()
    assert list(MARK_ROWS) == gen.braille(image, MARK_GRID)
    assert list(MARK_HEAD) == gen.braille(image, MARK_HEAD_GRID)


def test_every_glyph_is_a_braille_cell_on_its_own_axis(gen):
    """GIVEN a braille cell carries only dots
    THEN every glyph of both cuts is a braille pattern, and the ink sits on the
    middle of its own bounding box — the axis `mark_contract.py` measures. The
    tolerance is one cell and a half: a cell is two dots wide, so the ink's centre
    lands between dots."""
    from ui.terminal_mark import MARK_HEAD, MARK_ROWS

    for rows in (MARK_ROWS, MARK_HEAD):
        ink = [(row, col) for row, line in enumerate(rows)
               for col, ch in enumerate(line) if ch != " "]
        assert ink
        assert all(0x2800 <= ord(rows[row][col]) <= 0x28FF for row, col in ink)
        left = min(col for _, col in ink)
        right = max(col for _, col in ink)
        centre = sum(col for _, col in ink) / len(ink)
        assert abs(centre - (left + right) / 2) <= 1.5


def test_the_cut_trims_to_the_silhouette(gen):
    """GIVEN a cleared ground with a lit rectangle in it
    THEN the cut comes back at the rectangle's own box, so the mark carries ink
    and not canvas."""
    canvas = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).rectangle([10, 4, 29, 15], fill=(255, 255, 255, 255))

    assert gen.cut(canvas).size == (20, 12)


def test_a_faint_ground_lights_no_dot(gen):
    """GIVEN alpha at the floor
    THEN no dot is lit and the grid trims away instead of emitting blank cells."""
    canvas = Image.new("L", (2, 4), gen.INK_FLOOR - 1)

    assert gen.braille(canvas, (2, 4)) == []


def test_every_dot_position_maps_to_its_braille_bit(gen):
    """GIVEN a fully lit cut
    THEN the single cell carries dots 1-8, which is the bit layout the terminal
    renders."""
    assert gen.braille(Image.new("L", (2, 4), 255), (2, 4)) == [chr(0x28FF)]


@pytest.mark.asyncio
async def test_the_boot_card_and_the_header_carry_the_mark(tmp_path, monkeypatch):
    """GIVEN a first session with no messages
    WHEN the terminal paints its greeting
    THEN the moth is in the header and beside the wordmark, and the key legend
    still reaches the reader."""
    from core import multi_session as ms

    entry = ms.create_session("Boot card")
    ms.switch_to(str(entry["id"]))

    from ui.app import EpheApp
    from ui.terminal_mark import MARK_HEAD, MARK_ROWS

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
        header = str(app.query_one("#brand-mark").render())
        assert MARK_HEAD[0].strip() in header
        assert MARK_HEAD[-1].strip() in header
