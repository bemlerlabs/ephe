"""Repo hygiene: no non-Latin script characters in code and prose.

Three finding classes, all from machine post-edited texts:
- Cut-up comments in which a Chinese word sits in the middle of an English sentence
  ("sofort返回", "Chip导航iert") — a defect for the reader, invisible in a search hit.  # language-gate: ignore (the quoted CJK-mixed defect examples the rule is about)
- Cyrillic homoglyphs inside words: a U+043E in the place of a Latin 'o'. Those are
  visually indistinguishable and break every grep for the word.
- Fullwidth homoglyphs: a U+FF0F in the place of a normal '/'. An eye sees a slash,
  every search for "/befehl" sees a word that does not exist.

The codebase reason why the rule is not simply "no CJK": two test fixtures test CJK
input on purpose (ChatInput, contextMeter). For those only the Cyrillic rule applies;
core modules, server, CLI and docs have not a single legitimate non-Latin case and
are checked against both.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_BANNED_RANGES = (
    (0x400, 0x4FF, "Kyrillisch"),
    (0x3040, 0x30FF, "Kana"),
    (0x3400, 0x4DBF, "CJK-Erweiterung"),
    (0x4E00, 0x9FFF, "CJK-Ideogramme"),
    (0xAC00, 0xD7AF, "Hangul"),
    # Fullwidth forms: a U+FF0F looks like a slash and breaks every search hit for
    # "/befehl". Post-edited prose runs into that regularly.
    (0xFF00, 0xFF60, "Vollbreit"),
)

#: Forbidden everywhere (homoglyphs have no legitimate place in this repo).
_CYRILLIC_ROOTS = ("core", "server", "docs", "app/src", "tests", "scripts")
#: BOTH only here: these surfaces are purely German/English.
_LATIN_ONLY = ("core", "server", "docs", "scripts")
_LATIN_ONLY_FILES = (Path("ephe_cli.py"),)
#: Frontend source (without the test fixtures) is likewise purely DE/EN — an
#: ideogram that breaks into a comment here is the same defect as in the core
#: modules, and otherwise app/src is the only place that would let it through.
_LATIN_ONLY_FRONTEND = "app/src"


def _is_test_fixture(relative: Path) -> bool:
    name = relative.name
    return name.startswith("test_") or ".test." in name


def _latin_only_rels() -> list[Path]:
    rels = _files(_LATIN_ONLY) + [f for f in _LATIN_ONLY_FILES if (ROOT / f).is_file()]
    rels += [
        rel
        for rel in _files((_LATIN_ONLY_FRONTEND,))
        if rel.suffix in {".ts", ".tsx", ".css", ".html"} and not _is_test_fixture(rel)
    ]
    return rels


def _offender(ch: str) -> str | None:
    for lo, hi, label in _BANNED_RANGES:
        if lo <= ord(ch) <= hi:
            return f"{label} {ch!r} (U+{ord(ch):04X} {unicodedata.name(ch, '?')})"
    return None


def _scan(relative: Path, *, latin_only: bool) -> list[str]:
    text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for ch in line:
            flagged = _offender(ch)
            if flagged is None:
                continue
            if not latin_only and "Kyrillisch" not in flagged:
                continue  # CJK fixtures in tests and the frontend are intentional
            hits.append(f"{relative}:{number}: {flagged} — {line.strip()[:90]}")
    return hits


def _files(roots: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".md", ".mjs", ".json"}:
                continue
            if any(part in {"node_modules", "dist", ".venv", "target"} for part in path.parts):
                continue
            out.append(path.relative_to(ROOT))
    return out


def test_no_cyrillic_homoglyphs_anywhere_in_the_sources():
    bad = [hit for rel in _files(_CYRILLIC_ROOTS) for hit in _scan(rel, latin_only=False)]
    assert not bad, "Kyrillische Zeichen in DE/EN-Code:\n" + "\n".join(bad)


def test_kernmodule_server_cli_und_doku_sind_rein_lateinisch():
    rels = _latin_only_rels()
    bad = [hit for rel in rels for hit in _scan(rel, latin_only=True)]
    assert not bad, "Nicht-lateinische Zeichen in Prosa/Code (Zerstörungssignatur):\n" + "\n".join(bad)
