"""The forest is the only ground, and a guard says so.

Paper was tried as the default and rejected on 2026-10-16, then kept as a user choice until
2026-10-19, when the owner removed it from the product (no light theme, no system follow, no
theme toggle). Every other gate in this family measures a value; this one refuses a shape —
a second ground coming back through any of the doors that were closed:

* a `html.light` block or a paper literal in the stylesheet,
* a stored mode or a toggle in the frontend,
* a paper canvas in the manifest or the document head,
* the paper grain texture on a card,
* a `theme` field on the settings API, which is where a theme switch would have to be
  persisted to come back at all.

It scans product surfaces only. Dated documents and the archived paper proof rungs
(`scripts/brand_palette.py`, `scripts/generate_*.py`) still spell paper as history, and
rewriting them here would turn a record into a claim. The share card stopped being one
of them on 2026-10-19: it renders on the forest ground (Wave 5d).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / "app" / "src"

def _sources() -> list[Path]:
    """The frontend's own sources, without its test and spec files.

    A regression test that names `applyTheme` in a fixture string is the guard doing its
    job elsewhere, not a second ground returning; scanning them here would turn the next
    honest test into a false alarm, and a guard that cries wolf gets silenced.
    """
    return [p for p in APP_SRC.rglob("*.ts*")
            if p.is_file() and not re.search(r"\.(test|spec)\.[jt]sx?$", p.name)]


#: (name, what may not appear, where, why a reader would otherwise be surprised)
FORBIDDEN: list[tuple[str, re.Pattern[str], list[Path], str]] = [
    ("html.light", re.compile(r"html\.light"), [ROOT / "app/src/styles/globals.css"],
     "a second ground is back in the stylesheet"),
    ("paper literal", re.compile(r"#F0F0E6", re.IGNORECASE), [ROOT / "app/src/styles/globals.css"],
     "a paper literal is spelled in the sheet instead of a token"),
    ("grain-paper", re.compile(r"grain-paper"),
     [ROOT / "app/src/styles/globals.css", ROOT / "app/src/components/ui/Card.tsx"],
     "the paper grain texture is on a card again"),
    ("ephe.theme", re.compile(r"ephe\.theme"), _sources(),
     "a stored theme mode reappeared in the frontend"),
    ("theme switch", re.compile(r"\b(applyTheme|getStoredTheme|toggleTheme|ThemeMode)\b"),
     _sources(), "a theme switch reappeared in the frontend"),
    ("paper canvas", re.compile(r"#F0F0E6", re.IGNORECASE),
     [ROOT / "app/index.html", ROOT / "app/public/manifest.json"],
     "the browser edge is painted paper while the workbench is forest"),
    ("EPHE_THEME", re.compile(r"EPHE_THEME|theme:\s*str"),
     [ROOT / "server/routes/settings.py"],
     "the settings API advertises a theme field again"),
    ("AppSettings theme", re.compile(r"theme\s*[?:]"), [ROOT / "app/src/types/index.ts"],
     "AppSettings carries a theme key again"),
]


def test_the_forest_is_the_only_ground():
    findings = []
    for name, pattern, paths, why in FORBIDDEN:
        for path in paths:
            if not path.is_file():
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    findings.append(f"{name}: {path.relative_to(ROOT)}:{number}: "
                                    f"{line.strip()[:80]} — {why}")
    assert not findings, "the one-ground rule is broken:\n" + "\n".join(findings)


def test_every_refusal_matches_the_string_it_names():
    """A pattern that matches nothing is a rule that was never written. Each entry is
    probed against the line it exists to refuse."""
    probes = {
        "html.light": "html.light {",
        "paper literal": '  --color-canvas: hsl(60 25% 92%); /* #F0F0E6 */',
        "grain-paper": "'glass-reading grain-paper rounded-2xl'",
        "ephe.theme": "localStorage.getItem('ephe.theme')",
        "theme switch": "export function applyTheme(mode: ThemeMode): void {",
        "paper canvas": '  "theme_color": "#F0F0E6",',
        "EPHE_THEME": 'os.environ["EPHE_THEME"] = req.theme',
        "AppSettings theme": "  theme: string",
    }
    registered = {name: pattern for name, pattern, _, _ in FORBIDDEN}
    assert set(probes) == set(registered), (
        f"a refusal was added or dropped: {set(probes) ^ set(registered)}")
    for name, probe in probes.items():
        assert registered[name].search(probe), f"the {name} refusal misses its own example"


def test_the_scan_covers_the_surfaces_it_claims():
    """The frontend walk must find the product sources and only those, or the two frontend
    refusals are vacuous."""
    scanned = _sources()
    assert len(scanned) > 200, f"only {len(scanned)} frontend sources were scanned"
    every = [p for p in APP_SRC.rglob("*.ts*") if p.is_file()]
    tests = [p for p in every if re.search(r"\.(test|spec)\.[jt]sx?$", p.name)]
    assert tests, "no test sources exist to exclude, so the exclusion proves nothing"
    assert set(scanned) == set(every) - set(tests), (
        "the scan is not the product surface minus its tests")
