"""The px beside a type token is a claim about that token, and nothing had checked it.

`app/src/styles/globals.css` carries the interface type scale: every step is a `calc()` over
`--ui-font-size`, and the comment beside the step states the pixel it computes to. That comment is
what a developer trusts when they tune a dense layout without opening a browser — and nine of them
were left at the values of the 14 px base after `--ui-font-size` moved to 15 px on 2026-10-17, the
same drift that had already put a false 14 px into the Appearance hint.

The stylesheet cannot be imported, so this reads it: the exception `tests/AGENTS.md` allows when a
constraint has no other witness. It holds two things — a step derived from the base states its px,
and the stated px is the one the arithmetic produces, floor included.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "app" / "src" / "styles" / "globals.css"

BASE = re.compile(r"--ui-font-size:\s*(\d+)px")
STEP = re.compile(
    r"^(?P<indent>[ \t]*)--(?P<name>text-(?:ui|scale)-[a-z0-9-]+):\s*(?P<value>[^;]+);[ \t]*"
    r"(?:/\*[ \t]*(?P<comment>[^*]*?)[ \t]*\*/)?[ \t]*$",
    re.MULTILINE,
)
CALC = re.compile(r"calc\(var\(--ui-font-size\)\s*(?P<op>[+-])\s*(?P<delta>\d+)px\)")
FLOOR = re.compile(r"max\(\s*(?P<floor>\d+)px,")


def _steps() -> list[tuple[str, int, str | None]]:
    """Every derived step as (name, computed px, stated px)."""
    source = CSS.read_text(encoding="utf-8")
    base = BASE.search(source)
    assert base, "the stylesheet no longer names its base step the way the scale reads it"
    base_px = int(base.group(1))
    derived: list[tuple[str, int, str | None]] = []
    for match in STEP.finditer(source):
        calc = CALC.search(match.group("value"))
        if not calc:
            continue  # a fixed token — the iOS input step — does not follow the base
        px = base_px + int(calc.group("delta")) * (1 if calc.group("op") == "+" else -1)
        floor = FLOOR.search(match.group("value"))
        if floor:
            px = max(int(floor.group("floor")), px)
        stated = match.group("comment")
        number = None if stated is None else re.search(r"\d+", stated)
        derived.append((match.group("name"), px, number.group(0) if number else None))
    return derived


def test_every_derived_step_states_its_pixels() -> None:
    """A step whose value follows the base has to say what it lands on."""
    missing = sorted(name for name, _, stated in _steps() if stated is None)
    assert not missing, f"these steps derive from the base but state no px: {missing}"


def test_a_stated_pixel_is_the_one_the_arithmetic_produces() -> None:
    """The comment is a computed value, so it can be checked against the calculation."""
    wrong = [
        f"{name}: comment says {stated}, calc gives {px}"
        for name, px, stated in _steps()
        if stated is not None and int(stated) != px
    ]
    assert not wrong, f"the px beside the token no longer matches its calc: {wrong}"
