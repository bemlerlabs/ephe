"""A skill description must reach the English interface in English.

Counted on 2026-10-10: 51 `skills/*/SKILL.md` files, 3 descriptions the repo's own
instrument reads as German (`api-tester`, `code-metrics`, `config-setup`), and they
reached a reader through three surfaces — the slash menu, the `/skills` row in the
transcript, the register's Skills list. `skills/` sits in
`language_inventory.PROTECTED_PREFIXES`, so the language gate never read those
files at all: that is how the lines survived, and it is why this rule needs its own
test rather than a wider baseline.

The surfaces resolve `skills.desc.<name>` and fall back to the SKILL.md line
(`app/src/lib/slashCommands.ts`, the `reader.*` shape). So the rule is about the
resolved answer, not about the file: an English file needs no entry, a non-English
one must have one.

The mirror gap is counted and deliberately not asserted here: 48 descriptions are
English, so a German reader sees English for those. Closing it is a content job of
48 entries and would block every unrelated wave until it is done.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import language_inventory as li  # noqa: E402  (path bootstrap above)

SKILLS_DIR = ROOT / "skills"
LOCALES = ROOT / "app" / "src" / "locales"
DESC_RE = re.compile(r"(?m)^description:\s*(.+?)\s*$")
NAME_RE = re.compile(r"(?m)^name:\s*(.+?)\s*$")


def _quoted(text: str) -> str:
    return text.strip().strip('"').strip("'")


def skill_descriptions() -> dict[str, str]:
    """Skill name to its SKILL.md description, as the backend hands it out."""
    out: dict[str, str] = {}
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        head = path.read_text(encoding="utf-8", errors="ignore").split("---", 2)
        front = head[1] if len(head) >= 3 else ""
        desc = DESC_RE.search(front)
        if not desc:
            continue
        name = NAME_RE.search(front)
        out[_quoted(name.group(1)) if name else path.parent.name] = _quoted(desc.group(1))
    return out


def locale_group(language: str) -> dict[str, str]:
    data = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    return data.get("skills", {}).get("desc", {})


def resolved_for_english(name: str, raw: str) -> str:
    """What the English interface actually renders for one skill."""
    return locale_group("en").get(name) or raw


@pytest.mark.parametrize("name,raw", sorted(skill_descriptions().items()))
def test_the_english_reader_never_gets_a_german_skill_description(name: str, raw: str) -> None:
    answer = resolved_for_english(name, raw)
    assert li.hits_in(answer) == 0, (
        f"skills/{name}: the English surface resolves to text the instrument counts "
        f"as German ({answer!r}). Add skills.desc.{name} to app/src/locales/en.json — "
        "and to de.json in the same commit, the parity test below requires it."
    )


def test_every_skills_desc_key_lives_in_both_locales() -> None:
    en, de = locale_group("en"), locale_group("de")
    assert set(en) == set(de), (
        f"skills.desc is not paired: only en {sorted(set(en) - set(de))}, "
        f"only de {sorted(set(de) - set(en))}"
    )


def test_the_locale_entries_name_a_real_skill() -> None:
    known = set(skill_descriptions())
    unknown = sorted(set(locale_group("en")) - known)
    assert not unknown, f"skills.desc carries keys no skill ships: {unknown}"


def test_the_german_entries_keep_the_umlauts() -> None:
    """The transliterated spellings are the SKILL.md text; the locale file is the
    product's own German and must not copy that habit. The list names the shapes
    that occur in the packs — `Erhebt` is ordinary German and is not one of them."""
    transliterated = re.compile(r"(Fuehrt|fuehrt|prueft|fuer|ueber|Gefuehrter|Aehnlich|hinzufuegen)")  # language-gate: ignore (the spelling shapes this rule hunts, as data)
    for name, text in locale_group("de").items():
        assert not transliterated.search(text), (
            f"skills.desc.{name} spells an umlaut in ASCII: {text!r}"
        )
