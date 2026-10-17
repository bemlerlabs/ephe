#!/usr/bin/env python3
"""Language inventory: which tracked files still carry German developer prose.

Owner rule 2026-10-08: everything in this repository is written in English, and
German stays where it is a product feature. This script is the measuring
instrument for that switch — it counts lines that hold German marker words, per
directory, and it deliberately excludes the places where German is the point:
the app's own German locale file, the German skill packs, and the German
survival guides under knowledge/.

Run it before and after a translation package: the goal is a shrinking number,
and the final state is what a gate can assert on.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

#: Common German words that rarely appear in an English sentence or an
#: identifier. Deliberately includes both umlaut and transliterated spellings,
#: because this repo has historically used both.
MARKERS = [  # language-gate: ignore
    "und", "nicht", "mit", "fuer", "für", "wird", "werden", "auch", "kein", "keine", "immer",           # language-gate: ignore
    "schon", "hat", "sagt", "zeigt", "weil", "wenn", "dann", "diese", "diesem", "diesen",               # language-gate: ignore
    "davon", "damit", "nach", "ueber", "über", "mehr", "wieder", "nur", "selbst", "beide",              # language-gate: ignore
    "solange", "stattdessen", "naemlich", "nämlich", "gerade", "eigene", "gleiche", "derselbe",         # language-gate: ignore
    "daher", "dadurch", "danach", "worin", "welche", "zwischen", "innerhalb", "ausserhalb",             # language-gate: ignore
    "außerhalb", "ohne", "gegen", "jetzt", "hier", "dort", "etwas", "vielen", "bewusst",                # language-gate: ignore
    "zunächst", "naechste", "sondern", "obwohl", "weshalb", "weswegen", "etwa", "bereits",              # language-gate: ignore
]
WORD = re.compile(
    r"(?<![A-Za-zÄÖÜäöüß])(" + "|".join(MARKERS) + r")(?![A-Za-zÄÖÜäöüß])"
)

SKIP_PARTS = {"node_modules", ".git", "dist", "target", "venv", ".venv", "__pycache__"}

#: German here is product content or generated output, not developer prose.
PROTECTED_PREFIXES = (
    "app/src/locales/",
    "skills/",
    "knowledge/",
    "app/dist/",
    "videos/",
    "out/",
    "docs/media/user-walkthrough-2026-10-12/",
)

#: A plugin rubric quotes the filler phrase the model must NOT emit. That quote is
#: what the German UI actually renders, so translating it would destroy the very
#: example the rubric warns against.
PROTECTED_PATHS = re.compile(
    r"^plugins/[^/]+/prompts/rubric\.md$"
    # A baseline is measured data: it records the paths and test ids that still
    # carry the thing being ratcheted, so its German quotes the tree and is not
    # developer prose. Excluding it keeps the instrument from scoring its own
    # evidence — the same reason the rubrics above are exempt.
    r"|^(?:\./)?(?:\.architecture-baseline\.json|tests/home-isolation-baseline\.json"
    r"|scripts/language-baseline\.json)$"
)

EXTS = {
    ".py", ".ts", ".tsx", ".rs", ".mjs", ".js", ".jsx", ".md", ".json",
    ".toml", ".sh", ".txt", ".yaml", ".yml", ".css", ".html",
}


def is_scannable(rel: str) -> bool:
    """Whether this tracked path is developer prose the instrument reads.

    Four exclusions, each with a different reason: build and dependency
    directories hold copies of real sources, protected prefixes hold German that
    *is* the product, a protected path quotes German the prompt warns against,
    and an extension outside EXTS is not prose at all.
    """
    parts = Path(rel).parts
    if not parts:
        return False
    if any(part in SKIP_PARTS for part in parts):
        return False
    if rel.startswith(PROTECTED_PREFIXES):
        return False
    if PROTECTED_PATHS.match(rel):
        return False
    return Path(rel).suffix.lower() in EXTS


#: A line may state plainly that its German is the point — a vocabulary list, a
#: quoted product string, a Unicode test. The pragma is the escape valve the gate
#: honours, so nobody has to soften a measurement to make a check pass.
PRAGMA = "language-gate: ignore"


def hits_in(text: str) -> int:
    """Lines holding at least one German marker word."""
    return sum(
        1
        for line in text.splitlines()
        if WORD.search(line) and PRAGMA not in line
    )


#: Words the marker list catches inside ordinary English prose. `zustand` is in here because
#: the state library is named that — a comment about the store is not German. A measurement
#: that counts "user" as German makes a finished file look unfinished, and a
#: wave steered by that number never ends.
FALSE_FRIENDS = {"mit", "hat", "mein", "war", "wen", "tor", "of", "die", "user", "your", "an", "in", "so", "es", "falls", "den", "zustand"}  # language-gate: ignore

COMMENT_MARKERS = re.compile(r"(^|\s)(#|//|/\*|\*)")

#: The wide net, for completion rather than for planning. Two workers of wave 4
#: reported the same hole: the marker list above is small on purpose, so a German
#: sentence that happens to contain none of its words ("PWA-Build darf den Start [language-gate: ignore]
#: nie blockieren") reads as finished. This set is the second pass — it is allowed [language-gate: ignore]
#: to be noisy, because a false hint costs one look at one line while a miss costs
#: a file that ships German.
HINTS = [  # language-gate: ignore
    "darf", "soll", "sollte", "muss", "musste", "kann", "koennen", "können", "wäre", "hätte",           # language-gate: ignore
    "würde", "könnte", "müsste", "solche", "solcher", "solches", "jedoch", "eher", "kaum",              # language-gate: ignore
    "zwar", "sobald", "falls", "sofern", "indem", "bevor", "nachdem", "während", "denn",                # language-gate: ignore
    "seit", "seitdem", "bisher", "bisherige", "kürzlich", "neue", "neuer", "neues", "alte",             # language-gate: ignore
    "alten", "neueste", "wichtige", "einfach", "komplett", "sehr", "besonders", "nämlich",              # language-gate: ignore
    "lediglich", "ungefähr", "bestimmt", "vielleicht", "hoffentlich", "natürlich",                      # language-gate: ignore
    "selbstverständlich", "üblicherweise", "standardmäßig", "zusätzlich", "weiter", "weitere",          # language-gate: ignore
    "andere", "anderer", "anderes", "jeder", "jede", "jedes", "alle", "aller", "einzelne",              # language-gate: ignore
    "mehrere", "einige", "nichts", "niemand", "irgendwo", "überall", "hierher", "dahin",                # language-gate: ignore
    "momentan", "aktuell", "derzeit", "demnächst", "später", "früher", "sofort", "direkt",              # language-gate: ignore
    "unmittelbar", "eigentlich", "tatsächlich", "wirklich", "deutlich", "erkennbar",                    # language-gate: ignore
    "sichtbar", "unsichtbar", "verfügbar", "vorgabe", "vorgeschlagen", "gewählt", "geladen",            # language-gate: ignore
    "gelesen", "geschrieben", "gebaut", "blockiert", "verhindert", "erzeugt", "liefert",                # language-gate: ignore
    "bekommt", "nutzt", "bleibt", "wirkt", "läuft", "fährt", "steht", "liegt", "hält", "setzt",         # language-gate: ignore
    "fasst", "nimmt", "gibt", "sind", "war", "waren", "sei", "hatte", "hatten", "haben",                # language-gate: ignore
    "habt", "welche", "welcher", "deren", "dessen", "denen", "solange", "obwohl", "etwa",               # language-gate: ignore
    "circa", "meist", "öfter", "stets", "jeweils", "beispielsweise", "eben", "ansicht",                 # language-gate: ignore
    "ansichten", "vorlage", "vorlagen", "bestand", "datei", "dateien", "ordner", "ordners",             # language-gate: ignore
    "sitzung", "sitzungen", "auftrag", "auftrags", "spuren", "wissen", "helfer", "helfers",             # language-gate: ignore
    "fahigkeit", "fahigkeiten", "laufend", "abgeschlossen", "fertig", "fehlt", "gesetzt",               # language-gate: ignore
    "nachricht", "nachrichten", "werkzeug", "werkzeuge", "eintrag", "eintrage", "liste",                # language-gate: ignore
    "feld", "felder", "zustand", "ablauf", "vorgang", "vorgange", "ruckgabe",                 # language-gate: ignore
    "beispiel", "beispiele", "pruft", "prufe", "loffe", "loscht", "speichert", "eintragen",             # language-gate: ignore
    "ubernehmen", "einmal", "mehrfach", "oftmals", "gerade", "selbst", "ist", "als", "der",             # language-gate: ignore
    "den", "dem", "des", "einem", "einen", "einer", "vom", "zum", "zur", "beim", "beide",               # language-gate: ignore
    "beiden", "enthalten", "zahl", "zahlen", "grund", "wegen", "zweck", "siehe", "etwaige",             # language-gate: ignore
    "fx", "handelt", "gehen", "geschieht", "bekannt", "verwendet", "benutzt", "braucht",                # language-gate: ignore
]

#: Nouns and participles HINTS never covered. Each entry is a German line a worker had
#: to find by eye on 2026-10-09 — a miss ships German, a false hint costs one look.
#: One `split()` line on purpose: as a wrapped list this file crossed its own 400 wall.
WIDE_EXTRA = frozenset("referenz paritaet menue eintraege reihenfolge zweig anzahl kinder nummerierung gerendert rendern schnitt getrennte schnellwahl modell modelle eingabe eingaben verlauf rueckwaerts schaetzung zeilen schalter uebrige rundet indikator sortiert perspektive blickwinkel konvertierung entfernt geloescht erste zweite eins zwei drei gemountet buchstabe muster quellen durchlauf aufbau befehle schluessel titel zeige zeigt stellen gruppen kopf fussteil flaeche inhalt leere setzen pruefen prueft fuehrt kuerzung meldung antwort frage ziel zwecke gruende vorherige naechste beachten verteilt getrennt trennen trennung wiederholung abspielen aus unter durch vier korrekt korrekte schnell langsam kurz lange wenige mehr weniger etwas voll stark schwach leer dauerhaft dauern generierung datenschutz fehigkeiten zeitplan netzwerk installiert ressourcen sprache erscheinung gedachtnis lesetafel trefferliste geisterauswahl volltextsuche vorzeichen benutzer verhalten ziehkante laden neu schreibpfad abwesenheit verbraucher kontextfenster deckel kern manuell verblasst himmel wartet eigener kompatibel claempft wurf rhythmisch adressierbar herunter welle wellen waehrend hinzufuegen offnen installieren anleitung funktioniert geschwindigkeit verbleibend analysiere schreibe woche weg statt ehrlich aehnlich gekuerzt".split())  # language-gate: ignore

#: Abbreviations German developer prose uses and English does not.
GERMAN_ABBR = re.compile(
    r"\bz\.\s?B\.|\bd\.\s?h\.|\bs\.\s?v\.|\bu\.\s?ä\.|\busw\.|\bebd\.|\bggf\."
)
#: A word carrying an umlaut or sharp-s is German whatever its case. The inner class
#: used to be lowercase only, so `Übernehmen` and `Änderungen` — the commonest shape in [language-gate: ignore]
#: real comments, because German nouns start sentences — slipped through the wide net.
UMLAUT_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]*(?:[äöüßÄÖÜ][A-Za-zÄÖÜäöüß]*)+")
WIDE_WORDS = sorted({w.strip().lower() for w in HINTS if w.strip()} | WIDE_EXTRA | {m.lower() for m in MARKERS})
WIDE = re.compile(
    r"(?<![A-Za-zÄÖÜäöüß])(" + "|".join(sorted(set(WIDE_WORDS), key=len, reverse=True)) + r")(?![A-Za-zÄÖÜäöüß])",
    re.I,
)


def wide_prose_hits(text: str) -> int:
    """Prose lines that are German on the second, higher-recall pass.

    Planning and packaging still uses the small marker list; this is how a wave
    proves it is actually finished. A line counts when it holds a wide vocabulary
    word that is not an English false friend, a German abbreviation, or a word
    carrying an umlaut or sharp-s — which is how `z. B.` and `darf den Start nie [language-gate: ignore]
    blockieren` get caught even though the marker list never saw them.

    It is a prioritiser: a zero proves nothing about completeness. A plain German noun with no umlaut
    that is absent from the list stays invisible: in the literal census `Ansicht`, [language-gate: ignore]
    `Vorlagen` and `bestand` scored nothing, and the wide pass flagged 110 lines where a [language-gate: ignore]
    human reader counted roughly 230. So a file is finished when a reader has passed over
    it — a zero here is a reason to look elsewhere.
    """
    hits = 0
    for line in text.splitlines():
        if PRAGMA in line:
            continue
        words = [w for w in WIDE.findall(line) if w.lower() not in FALSE_FRIENDS]
        if words or GERMAN_ABBR.search(line) or UMLAUT_WORD.search(line):
            hits += 1
    return hits


def python_prose(text: str) -> str:
    """Comments (tokenize) and docstrings (ast) of a Python source, nothing else.

    Falls back to a line scan when the file does not parse, so a half-written file
    still gets measured instead of silently counting as clean.
    """
    chunks: list[str] = []
    try:
        import io
        import tokenize

        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                chunks.append(tok.string)
    except Exception:
        chunks.extend(line for line in text.splitlines() if line.lstrip().startswith("#"))
    try:
        import ast

        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    chunks.append(doc)
    except SyntaxError:
        pass
    return "\n".join(chunks)


def clike_prose(text: str) -> str:
    """Comments of a C-like file, read without mistaking a string for a comment.

    A naive `//[^\\n]*` scan treats the `//` of `https://example.com` as a comment
    start, so a fixture URL is scored as developer prose and the file can never
    reach zero. Walk the text instead, honouring string state: a single or double
    quote only opens a string if it closes again on the same line (so a JSX
    apostrophe cannot swallow the code after it), a backtick may span lines.
    """
    chunks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            chunks.append(text[i:end])
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n - 2 if end < 0 else end
            chunks.append(text[i : end + 2])
            i = end + 2
            continue
        if ch in "\"'":
            line_end = text.find("\n", i)
            limit = n if line_end < 0 else line_end
            close = text.find(ch, i + 1, limit)
            while 0 < close < limit and text[close - 1] == "\\":
                close = text.find(ch, close + 1, limit)
            if close > 0:
                i = close + 1
                continue
        if ch == "`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "`":
                    break
                j += 1
            i = min(j + 1, n)
            continue
        i += 1
    return "\n".join(chunks)


def hash_prose(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#"))


def prose_of(rel: str, text: str) -> str:
    """The developer prose of a file: what a translation wave is actually allowed
    to change. String literals, fixtures and identifiers are excluded by
    construction, which is what makes this a completion measure at all."""
    suffix = Path(rel).suffix.lower()
    if suffix == ".py":
        return python_prose(text)
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".rs"}:
        return clike_prose(text)
    if suffix in {".sh", ".yaml", ".yml", ".toml"}:
        return hash_prose(text)
    if suffix in {".md", ".txt"}:
        return text
    return ""


def hits_in_prose(text: str) -> int:
    """Lines of developer prose still holding a real German marker word."""
    hits = 0
    for line in text.splitlines():
        if PRAGMA in line:
            continue
        found = [w for w in WORD.findall(line) if w.lower() not in FALSE_FRIENDS]
        if found:
            hits += 1
    return hits


def counts_for(
    files: Iterable[str],
    read_text: Callable[[str], str],
    prose: bool = False,
    wide: bool = False,
) -> dict[str, int]:
    """German lines per path, for exactly the paths that are developer prose.

    `read_text` is injected so a gate or a test can score any tree — including a
    fixture — without a git checkout. Paths with no hit are left out, so an absent
    path in the result carries one fact: this scan found no German in it.

    `prose=True` scores comments, docstrings and markdown body — the work a wave
    may do, and the only side of that flag that can ever read as finished. `prose=False` scores
    every line, string literals the wave must not touch included, so its number
    tracks growth alone. `wide=True` keeps the prose extraction but swaps the small
    marker list for the broad second net, which is how a wave finds the German it
    already thinks it finished.
    """
    counts: dict[str, int] = {}
    for rel in files:
        if not is_scannable(rel):
            continue
        try:
            text = read_text(rel)
        except (OSError, UnicodeDecodeError):
            continue
        if wide:
            hits = wide_prose_hits(prose_of(rel, text))
        elif prose:
            hits = hits_in_prose(prose_of(rel, text))
        else:
            hits = hits_in(text)
        if hits:
            counts[rel] = hits
    return counts


def scan(root: Path, prose: bool = False, wide: bool = False) -> dict[str, list[tuple[str, int]]]:
    files = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    counts = counts_for(files, lambda rel: (root / rel).read_text(encoding="utf-8"), prose=prose, wide=wide)
    per_dir: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for rel, hits in counts.items():
        parts = Path(rel).parts
        top = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
        per_dir[top].append((rel, hits))
    return per_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=0, help="show only the N busiest directories")
    parser.add_argument("--files", action="store_true", help="list every file, not just the leaders")
    parser.add_argument("--porcelain", action="store_true", help="only the totals, for gates")
    parser.add_argument(
        "--prose",
        action="store_true",
        help="score only comments, docstrings and markdown body — the completion measure",
    )
    parser.add_argument(
        "--wide",
        action="store_true",
        help="prose extraction plus the broad second net: what a finished wave still hides",
    )
    args = parser.parse_args()

    per_dir = scan(Path.cwd(), prose=args.prose, wide=args.wide)
    ranked = sorted(per_dir.items(), key=lambda kv: -sum(h for _, h in kv[1]))
    if args.top:
        ranked = ranked[: args.top]

    total_files = sum(len(rows) for rows in per_dir.values())
    total_lines = sum(h for rows in per_dir.values() for _, h in rows)

    if not args.porcelain:
        for directory, rows in ranked:
            lines = sum(h for _, h in rows)
            print(f"{lines:6d} lines  {len(rows):4d} files  {directory}")
            shown = rows if args.files else sorted(rows, key=lambda r: -r[1])[:4]
            for rel, hits in sorted(shown, key=lambda r: -r[1]):
                print(f"          {hits:4d}  {rel}")
        print()
    print(f"TOTAL\t{total_files} files\t{total_lines} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
