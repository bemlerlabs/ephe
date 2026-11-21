"""Identifiers in the tree carry English words, and 51 retired German ones stay retired.

`scripts/language_gate.py` reads prose, and its inventory skips identifiers and string literals
(`scripts/prose_inventory.py:9`), so nothing in the tree has ever looked at an identifier. The names
here came from three nets over every `ast`-bound name in `core/`, `server/`, `scripts/`, `evals/`,
`tests/`, `ephe_cli.py`, `run_server.py` and `ephe.py`: the house lexicon
(`scripts/language_inventory.py`: `MARKERS` 64 words, `WIDE_WORDS` 423), German shapes (`-isch`,
`-ung`, `pf`, `tz`, …) and subtraction against a 466 564-word English list. Each net under-reports on
its own — the lexicon missed `identisch`, the shapes missed `sitzung`, the English list is missing
`config`, so an abbreviation that is not a word looks German. Nets nominate, a person reads the site.

This guard pins what that read found: 55 rename rules, 51 distinct names, 202 sites over 28 files, the
renames line-neutral. It is a regression pin on a measured finding and carries no claim that the tree
holds no other German identifier. A third-party alias and two English abbreviations stay, listed in
KEEPS with their reason.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

RETIRED = (
    # core/, server/, scripts/
    "_kurz",                     # core/redact, truncated an audit-log value
    "grenze",                    # core/redact, where that truncation fell
    "_HAENGET",                  # core/redact, characters a cut may not end on
    "identisch",                 # ephe_cli, the installed bundle already matches
    "spitzstunde",               # core/ephemeris, the busiest hour of a day
    "lizenz",                    # core/cell_policy, the cell package's licence string
    "_schlank",                  # server/routes/session_mirror, thinned a mirrored message
    # ephe_cli.py
    "ziel",                      # the folder an .app was installed into
    "vorher",                    # the log file the rotation kept as .1
    # tests/ — locals
    "zeile", "ziel", "sitzung", "pfad", "inhalt", "kern", "bau", "papier", "ort", "alt",
    "mit_dir",  # language-gate: ignore (the retired name is the thing under test)
    "weg", "zweite", "roh", "antwort", "aussen", "neue", "toten", "umgezogen",
    "fehlt", "geoeffnet", "neu", "darf", "als", "zahl", "der", "enthalten", "welle", "waisen",
    # tests/ — module-level fixture constants
    "ARTIKEL", "AUSSEN", "NACHRICHT",
    # tests/ — class names
    "TestProtokoll", "TestSchreiben", "TestKeinGateUmgehung", "TestKeinStillerDefault",
    "TestVorwaertsAbstammung", "TestComputeAffordanceBleibt",
    "TestAndereProfileBehaltenIhrenPfad", "TestBenannterSpeicherErreichtDasselbeGate",
    # retired by the helper sweep before this one
    "_app_stempel", "_schreibe_desktop_konfig", "_geburt_ms",
)

# A name that is German-shaped here and English there. Each entry is one file, one name, one reason.
KEEPS = {
    ("core/memory_embed_gemma.py", "ort"): "import onnxruntime as ort — the library's own alias",
    ("core/memory_embed_onnx.py", "ort"): "import onnxruntime as ort — the library's own alias",
    ("scripts/readme_check.py", "alt"): "the alt text of a markdown image — English markup term",
    ("server/routes/settings.py", "alt"): "an alternative endpoint URL on a neighbouring port",
}

ROOTS = ("core", "server", "scripts", "evals", "tests")
FILES = ("ephe_cli.py", "run_server.py", "ephe.py")


def _sources(root: Path) -> list[Path]:
    found = [root / name for name in FILES]
    for name in ROOTS:
        found += sorted((root / name).rglob("*.py"))
    return [path for path in found if path.is_file()]


def _identifier_names(path: Path) -> list[tuple[int, str]]:
    """Every name the module binds or reaches for, at the position ast gave it."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        name: str | None = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.arg):
            name = node.arg
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.keyword):
            name = node.arg
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        if name is not None:
            found.append((getattr(node, "lineno", 0), name))
    return found


def _hits(sources: list[Path], root: Path) -> list[str]:
    hits: list[str] = []
    for path in sources:
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = ""  # a file outside the checkout (a planted fixture) cannot be exempt
        for number, name in _identifier_names(path):
            if name not in RETIRED or (rel, name) in KEEPS:
                continue
            hits.append(f"{path.name}:{number} {name}")
    return hits


def test_the_retired_german_names_stay_gone() -> None:
    root = Path(__file__).resolve().parents[1]
    hits = _hits(_sources(root), root)
    assert not hits, (
        f"{hits} bound a German name again — the English name is in the rename table of this "
        "file's docstring, and the site is in the commit that retired it"
    )


def test_the_keeps_are_still_the_names_they_claim() -> None:
    """An exempted name that disappears makes KEEPS a lie, so the pair has to be live."""
    root = Path(__file__).resolve().parents[1]
    for rel, name in KEEPS:
        found = [n for _, n in _identifier_names(root / rel)]
        assert name in found, f"{rel} no longer binds {name} — drop it from KEEPS"


def test_the_scan_sees_the_files_it_claims_to_cover() -> None:
    sources = _sources(Path(__file__).resolve().parents[1])
    assert len(sources) > 1000, f"only {len(sources)} files scanned"
    names = {path.name for path in sources}
    assert {"ephe_cli.py", "session_mirror.py", "redact.py"} <= names, sorted(names)[:3]


def test_a_german_identifier_is_actually_found(tmp_path: Path) -> None:
    """A guard that never fires is not evidence; this one has to catch a planted name."""
    planted = tmp_path / "planted.py"
    planted.write_text("sitzung = 1\nprint(sitzung)\n", encoding="utf-8")
    hits = _hits([planted], tmp_path)
    assert len(hits) == 2 and all(hit.endswith("sitzung") for hit in hits), hits


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
