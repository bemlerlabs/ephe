"""M3 — the sandbox check after an edit, and the repair directive it carries.

The loop is the tool result: `write_file` and `edit_file` append the checker's
own words, so the model reads a failure inside the same turn and can fix it.
Two repairs per turn are the budget; the third failure switches the sentence to
"report it" so a model cannot edit in circles.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import coding_loop


@pytest.fixture(autouse=True)
def _fresh_budget():
    coding_loop.reset_turn()
    yield
    coding_loop.reset_turn()


def test_a_clean_file_passes_silently(tmp_path: Path):
    target = tmp_path / "ok.py"
    target.write_text("value = 1\n", encoding="utf-8")

    note = coding_loop.annotation(target)

    assert note.startswith("\n\n[sandbox check passed")
    assert coding_loop.repairs_used() == 0


def test_a_broken_file_comes_back_with_its_traceback_and_a_directive(tmp_path: Path):
    target = tmp_path / "broken.py"
    target.write_text("def broken(:\n    pass\n", encoding="utf-8")

    note = coding_loop.annotation(target)

    assert "FAILED (1/2)" in note
    assert "repair the file in this turn" in note
    assert "SyntaxError" in note or "line" in note
    assert coding_loop.repairs_used() == 1


def test_the_budget_ends_after_two_repairs(tmp_path: Path):
    target = tmp_path / "broken.py"
    target.write_text("def broken(:\n", encoding="utf-8")

    first = coding_loop.annotation(target)
    second = coding_loop.annotation(target)
    third = coding_loop.annotation(target)

    assert "FAILED (1/2)" in first
    assert "FAILED (2/2)" in second
    assert "budget is spent" in third
    assert coding_loop.repairs_used() == 2


def test_a_repair_turn_starts_with_a_fresh_budget(tmp_path: Path):
    target = tmp_path / "broken.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    coding_loop.annotation(target)
    coding_loop.annotation(target)

    coding_loop.reset_turn()

    assert coding_loop.repairs_used() == 0
    assert "FAILED (1/2)" in coding_loop.annotation(target)


def test_an_unchecked_type_answers_nothing(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("plain text\n", encoding="utf-8")

    assert coding_loop.annotation(target) == ""


def test_json_is_parsed_rather_than_compiled(tmp_path: Path):
    good = tmp_path / "good.json"
    good.write_text('{"a": 1}', encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text('{"a": }', encoding="utf-8")

    assert "passed" in coding_loop.annotation(good)
    assert "FAILED" in coding_loop.annotation(bad)


def test_the_edit_that_fixes_the_file_ends_green(tmp_path: Path):
    """The end-to-end shape: broken edit, repair edit, green result."""
    from core.tools.file_ops import write_file

    import asyncio

    target = tmp_path / "loop.py"
    first = asyncio.run(write_file(str(target), "def f(:\n    return 1\n"))
    assert "FAILED (1/2)" in first

    second = asyncio.run(write_file(str(target), "def f():\n    return 1\n"))
    assert "sandbox check passed" in second
