"""The two lines the owner set, on the surfaces that carry them, in each surface's own words.

`docs/BRAND.md` section 4 says a word here is a word its pinner enforces. The headline is the
light sentence, the line under it is the hero line, and the three READMEs say both in their own
language — a translation that drifts is a different product being described, so each language
pins its own wording rather than inheriting the English one.

The English README carries the two sentences the installer contract quotes
(`scripts/readme_check.py`, `tests/test_installer_cli.py`). The Spanish and Chinese files open
with the English terms as the canonical citation their own header already promises, because
those files declare `README.md` authoritative; a reader comparing them has to be able to see
that the same two terms are in all three.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SURFACES = {
    "README.md": (
        "Where the light is, the work happens.",
        "Your agent. Your machine. Your memory.",
    ),
    "README.es.md": (
        "Donde está la luz, se hace el trabajo.",
        "Tu agente. Tu máquina. Tu memoria.",
    ),
    "README.zh-CN.md": (
        "光在哪里，工作就在哪里落地。",
        "你的智能体，你的机器，你的记忆。",
    ),
}

CANONICAL_TERMS = ("local-first workspace for an AI agent", "Online paths are opt-in")


def stripped_lines(name: str) -> list[str]:
    return [line.strip() for line in (ROOT / name).read_text(encoding="utf-8").splitlines()]


def test_each_readme_carries_the_headline_and_the_hero_line() -> None:
    for name, (headline, hero_line) in SURFACES.items():
        lines = stripped_lines(name)
        assert f"### {headline}" in lines, f"{name} does not carry the headline as a heading"
        assert f"**{hero_line}**" in lines, f"{name} does not carry the hero line under it"
        assert lines.index(f"### {headline}") < lines.index(f"**{hero_line}**"), (
            f"{name}: the hero line sits above its headline"
        )


def test_the_headline_arrives_before_the_prose_does() -> None:
    """Four seconds is the decision window; the headline cannot be below the fold."""
    for name, (headline, _) in SURFACES.items():
        assert f"### {headline}" in stripped_lines(name)[:20], f"{name}: headline is not in the hero"


def test_the_two_non_english_readmes_quote_the_canonical_terms() -> None:
    for name in ("README.es.md", "README.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for term in CANONICAL_TERMS:
            assert term in text[:1500], f"{name} does not carry {term!r} in its first 1500 characters"
