#!/usr/bin/env python3
"""Language gate: the measuring instrument, wired to a committed baseline.

Owner rule 2026-10-08: every artifact in this repository is written in English,
and German stays where it is a product feature. `scripts/language_inventory.py`
measures that; this script makes it hold. It compares the current tree against
`scripts/language-baseline.json` and fails when German developer prose has
grown, so the next feature cannot bring a German comment along unnoticed.

Two legs, because a ratchet cannot ask for zero. The line measurement scores every line a file
holds and compares the count to a committed baseline, so a German sentence a test says about itself
was measured once and then tolerated — free for as long as nobody raises that file. `message_leg`
parses the suite and refuses those sentences outright, with no baseline to age into:
`scripts/message_language.py`.

A third leg, `surface_leg`, covers what product code says to a person: the message of a `raise`, an
`assert`, a print or a log call. The ratchet forgave those into a baseline and the message leg is
scoped to `tests/`, so a German `ValueError` reached the developer on a path the tree measured as
clean. It parses those nodes, carries its own word lists so a hole in the instrument's marker list
cannot hide one, and keeps no baseline for the same reason the message leg keeps none.

A fourth leg, `cjk_leg`, asks a question the German rules cannot ask: whether any Han,
Hiragana, Katakana or Hangul character sits in a file that was not written for it. The
ratchet's instrument scores umlauts and German words and the message leg parses German word
lists, so a stray CJK string passed both — the two characters that turned up in a report
line in November 2026 were caught by hand, by a reader. It reads the whole tree, keeps no
baseline, and names its exceptions one path at a time with the reason each file is in the
tree.

The ratchet is per file, not just in total. A total can fall while a single file
gets worse — one worker translates a module, another writes a German sentence in
a new one — and only the per-file comparison names the file that regressed.

There is no exemption list an author can write. `language_inventory.PROTECTED_PREFIXES`
and `language_inventory.PRODUCT_TEXT_PATHS` are the only two things that keep German out of
the number, both are owned by the instrument, and the prefixes are checked on every run
(`checked_protected_prefixes`). Anything else that looks
like an exemption — an `exempt` key in the baseline, a protected path recorded in
the baseline, a protected prefix reaching into developer code — is an error,
because each of those would silently make the number lie. For the same reason
`--update` only ever lowers the baseline: a failing tree cannot be made to pass
by re-measuring it.

Below the baseline the tree is cleaner, so the gate passes. When at least one file
sits below its baseline entry the pass closes with the offer to lower the baseline,
in the two lines the sister gates print (`prose_tells.py`, `home_isolation_gate.py`).
The offer is tied to that action: a tree that matches its baseline says nothing. A
`--staged` pass measures the few blobs one commit carries, so it leaves the
whole-tree offer out.

Exit codes: 0 the tree is not worse than the baseline, 1 German prose grew (the
files are named), 2 the gate cannot be trusted (missing or malformed baseline, a
protected path where one must never appear).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from typing import NamedTuple, TypedDict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import language_inventory as inventory  # noqa: E402  (path bootstrap above)
import message_language as messages  # noqa: E402  (path bootstrap above)

REPO_ROOT = SCRIPTS_DIR.parent
BASELINE_DEFAULT = SCRIPTS_DIR / "language-baseline.json"
POLICY = "language-ratchet"
VERSION = 1
#: Findings the gate prints before pointing at the instrument that lists them all.
PRINTED_FINDINGS = 20
#: The only keys a baseline may carry. An unknown key is refused rather than
#: ignored: the shape of a whitelist is exactly what must not be added here.
BASELINE_KEYS = {"policy", "version", "instrument", "total", "files"}

#: Paths that are developer prose by definition. A protected prefix covering one
#: of these would take real code out of the measurement.
GUARDED_ROOTS = (
    "app/src/", "core/", "server/", "scripts/", "tests/", "docs/", "evals/", "build/",
)

UPDATE_HINT = f"python3 {BASELINE_DEFAULT.parent.name}/{Path(__file__).name} --update"


class GateError(Exception):
    """An untrustworthy gate exits 2; a refusal that means something exits 1."""


def checked_protected_prefixes() -> tuple[str, ...]:
    """The instrument's protected prefixes, after proving they stay product-only."""
    prefixes = tuple(inventory.PROTECTED_PREFIXES)
    for prefix in prefixes:
        if not prefix or prefix == "/":
            raise GateError(
                f"a protected prefix is empty ({prefix!r}); that would exclude the whole "
                "repository from the measurement"
            )
        swallowed = [root for root in GUARDED_ROOTS if root.startswith(prefix)]
        if swallowed:
            raise GateError(
                f"protected prefix {prefix!r} covers developer code ({', '.join(swallowed)}). "
                "Protected paths are for German that is the product — the app locale, the "
                "German skill packs, the survival guides, generated output. Narrow the "
                "prefix to the product directory instead of silencing the gate."
            )
    return prefixes


def tracked_files(root: Path) -> Callable[[], list[str]]:
    """The paths a whole-tree measurement judges: what git tracks in this checkout."""

    def list_files() -> list[str]:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True, text=True, check=True,
        )
        return done.stdout.splitlines()

    return list_files


def message_leg(
    paths: list[str],
    read_text: Callable[[str], str] | None,
    root: Path,
    *,
    printed: int = PRINTED_FINDINGS,
) -> tuple[int, list[str]]:
    """The suite's own sentences: assert messages, `pytest.fail`/`skip`/`xfail` texts, skip reasons.

    The line measurement above scores these lines and then forgives them: it compares a count to a
    baseline, so a German sentence that predates the file's entry — or fits under it — costs nothing,
    and the suite kept a second voice, English in the comments and German in the one line a
    developer reads when a leg goes red. This parses the file and asks about those strings by node:
    an assert message, a skip reason, a raised sentence.

    It carries no baseline on purpose. The rule is English, the one escape is the marker
    `scripts/message_language.py` documents, and a baseline would freeze the German instead of
    removing it — which is how the line measurement ended up tolerating these very lines.
    """
    pairs: list[tuple[str, str | None]] = []
    for rel in paths:
        if not rel.startswith("tests/") or not rel.endswith(".py"):
            continue
        try:
            text = read_text(rel) if read_text is not None else (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = None
        pairs.append((rel, text))
    findings, read, unread = messages.check_pairs(pairs)
    if not findings:
        return 0, [
            f"message language: PASS — no German developer prose in {read} test message(s) "
            f"({unread} built at runtime, unreadable by any word check)"
        ]
    lines = [
        f"message language: FAIL — German developer prose in {len(findings)} test message(s) "
        f"over {len({f.rel for f in findings})} file(s)"
    ]
    for finding in findings[:printed]:
        lines.append(f"  {finding.rel}:{finding.line} {finding.kind}: {finding.quote}")
    if len(findings) > printed:
        lines.append(f"  ... {len(findings) - printed} more — python3 scripts/message_language.py --limit 0")
    lines.append(
        "Rewrite those sentences in English. German the product itself says stays: mark it on the "
        "message's line with `# language-gate: product German` and say why."
    )
    return 1, lines


#: Developer-facing call names: their first positional argument is the sentence a person reads.
SURFACE_CALLS = frozenset(
    {"print", "echo", "info", "warn", "ok", "fail", "step", "error", "warning",
     "exception", "critical", "debug", "exit"}
)
#: Words no English sentence puts in front of a user. One of these is a finding alone.
SURFACE_HIGH = frozenset(
    {"unbekannt", "unbekannte", "unbekanntes", "unbekannter", "erlaubt", "erlaubte", "erlaubter",  # language-gate: ignore
     "ungueltig", "ungültig", "ungültige", "ungültiger", "bitte", "danke", "fehler", "fehlerhaft",  # language-gate: ignore
     "antwort", "anfrage", "eingabe", "eingegeben", "gewählt", "gewaehlt", "wählen", "waehlen",  # language-gate: ignore
     "ausgewählt", "ausgewaehlt", "möglich", "moeglich", "zulässig", "zulaessig", "notwendig",  # language-gate: ignore
     "bereich", "überschritten", "ueberschritten", "berechtigung", "bahnpunkt"}  # language-gate: ignore
)
#: Ordinary function words. One inside an otherwise English sentence is an artefact; two are German.
SURFACE_MARKERS = (
    "nicht", "und", "mit", "fuer", "für", "wird", "werden", "wurde", "wurden", "auch", "kein",  # language-gate: ignore
    "keine", "kein", "immer", "schon", "hat", "haben", "hatte", "sagt", "zeigt", "weil", "wenn",  # language-gate: ignore
    "dann", "diese", "dieser", "dieses", "davon", "damit", "nach", "ueber", "über", "mehr",  # language-gate: ignore
    "wieder", "nur", "selbst", "beide", "solange", "stattdessen", "naemlich", "nämlich", "gerade",  # language-gate: ignore
    "eigene", "gleiche", "derselbe", "daher", "dadurch", "danach", "worin", "wofür", "wofuer",  # language-gate: ignore
    "wovon", "welche", "zwischen", "innerhalb", "ausserhalb", "außerhalb", "ohne", "gegen",  # language-gate: ignore
    "jetzt", "hier", "dort", "etwas", "vielen", "bewusst", "zunächst", "naechste", "sondern",  # language-gate: ignore
    "obwohl", "weshalb", "weswegen", "etwa", "bereits", "darf", "soll", "sollte", "muss",  # language-gate: ignore
    "musste", "kann", "koennen", "können", "wäre", "hätte", "würde", "könnte", "müsste", "jedoch",  # language-gate: ignore
    "eher", "kaum", "zwar", "sobald", "falls", "sofern", "indem", "bevor", "nachdem", "während",  # language-gate: ignore
    "seit", "seitdem", "bisher", "kürzlich", "sehr", "besonders", "lediglich", "ungefähr",  # language-gate: ignore
    "vielleicht", "natürlich", "zusätzlich", "weitere", "andere", "mehrere", "einige", "nichts",  # language-gate: ignore
    "niemand", "überall", "ist", "sind", "dass", "doch", "noch", "leider", "genau", "deine",  # language-gate: ignore
    "dein", "deinen", "ihre", "sein", "seine", "unser", "euer",  # language-gate: ignore
)
#: Nouns and verbs a German screen or CLI print uses and no English sentence contains. The
#: instrument needed a second list for the same reason (`language_inventory.HINTS` plus
#: `WIDE_EXTRA`): function words alone leave a heading like "Sichtweite 7 Tage · 3 Bahnen"
#: unmeasured, and a heading the developer reads is what this leg is for.
SURFACE_NOUNS = frozenset(
    {"bahn", "bahnen", "inhalt", "inhalte", "himmel", "wartet", "warten", "sichtweite", "tage",  # language-gate: ignore
     "stunde", "stunden", "uhrzeit", "spitzstunde", "sitzung", "sitzungen", "verblasst",  # language-gate: ignore
     "letzten", "letzter", "letzte", "lebendig",  # language-gate: ignore
     "geschah", "geschehen", "nie", "wann", "warum", "wahl", "werte", "vorgabe", "zurück",  # language-gate: ignore
     "vorhanden", "fehlend", "unbenutzt", "bereit", "fertig", "läuft", "gestartet", "gestoppt",  # language-gate: ignore
     "übersprungen", "wiederholt", "übersetzt", "geladen", "werkzeug", "werkzeuge",  # language-gate: ignore
     "artefakt", "artefakte", "abgelegt", "quelle", "quellen", "ergebnis", "ergebnisse",  # language-gate: ignore
     "monat", "monate", "wochenende"}  # language-gate: ignore
)
#: Words that decide on their own: no English sentence puts any of them in front of a person.
SURFACE_ALONE = SURFACE_HIGH | SURFACE_NOUNS
#: German and English at once. Counting these makes English look German, so they never count alone.
SURFACE_FALSE_FRIENDS = frozenset(
    {"mit", "und", "hat", "nur", "von", "die", "der", "das", "war", "man", "in", "an", "so",  # language-gate: ignore
     "neue", "manche", "ihre", "sein"}
)
#: An identifier is not a sentence: the boundary keeps `tage_aktiv` out while `Tage ·` stays in.
SURFACE_WORD = re.compile(
    r"(?<![A-Za-z0-9ÄÖÜäöüß_])("
    + "|".join(
        sorted(set(SURFACE_MARKERS) | set(SURFACE_HIGH) | set(SURFACE_NOUNS), key=len, reverse=True)
    )
    + r")(?![A-Za-z0-9ÄÖÜäöüß_])",
    re.IGNORECASE,
)
UMLAUT = re.compile(r"[äöüßÄÖÜ]")
#: The directories a developer writes product code in, plus the root scripts beside them.
SURFACE_ROOTS = ("core/", "server/", "scripts/", "app/")
#: Methods that push a line into something a person will read: a report, a chart, a footer.
ASSEMBLY_METHODS = frozenset({"append", "extend", "insert", "write", "writelines"})


class SurfaceFinding(NamedTuple):
    """One sentence product code says to a person, in the language the rule forbids there."""

    rel: str
    line: int
    kind: str
    quote: str


def surface_german(text: str) -> bool:
    """Was this literal written to a person in German?

    The lists are this leg's own, and deliberately not `language_inventory.MARKERS`: a second net
    woven from the first inherits its holes, and this leg exists because of one such hole. Measured
    on `git show HEAD:core/voice_config.py`, whose three German `raise` messages the instrument's
    marker list did not contain, so the tree scored them as clean English.
    """
    found = list(dict.fromkeys(word.lower() for word in SURFACE_WORD.findall(text)))
    if not found:
        return False
    if any(word in SURFACE_ALONE for word in found):
        return True
    real = [word for word in found if word not in SURFACE_FALSE_FRIENDS]
    if not real:
        return False
    return len(found) >= 2 or bool(UMLAUT.search(text))


def _summands(node: ast.expr) -> Iterable[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        yield from _summands(node.left)
        yield from _summands(node.right)
    else:
        yield node


def _literal_text(node: ast.expr) -> str:
    """One text per message: the pieces of an f-string and of a concatenation belong together."""
    parts: list[str] = []
    for part in _summands(node):
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            parts.append(part.value)
        elif isinstance(part, ast.JoinedStr):
            parts.append(
                "".join(
                    value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else " "
                    for value in part.values
                )
            )
    return " ".join(part for part in parts if part.strip())


def _elements(kind: str, value: ast.expr) -> Iterable[tuple[str, ast.expr]]:
    """The strings of a list or tuple literal, or the single literal beside an assignment."""
    if isinstance(value, (ast.List, ast.Tuple)):
        for element in value.elts:
            yield kind, element
    else:
        yield kind, value


def surface_messages(tree: ast.AST) -> Iterable[tuple[str, ast.expr]]:
    """Every (kind, node) where product code addresses a person with a literal.

    A report, a chart and a footer are built before they are shown: the sentence is assembled in a
    list and printed by someone else. Those lines are as user-facing as a `print`, so the assembly
    sites are read here too — a heading no leg reads is a heading nobody keeps English.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            exc = node.exc
            args = exc.args + [keyword.value for keyword in exc.keywords] if isinstance(exc, ast.Call) else ([exc] if exc is not None else [])
            for arg in args:
                yield "raise", arg
        elif isinstance(node, ast.Assert) and node.msg is not None:
            yield "assert message", node.msg
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) for target in targets):
                yield from _elements("assembled text", node.value)
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name in SURFACE_CALLS:
                for arg in node.args + [keyword.value for keyword in node.keywords]:
                    yield "output", arg
            elif name in ASSEMBLY_METHODS:
                for arg in node.args + [keyword.value for keyword in node.keywords]:
                    yield "assembled text", arg


def in_surface_scope(rel: str) -> bool:
    """Product code only: the suite's own voice is `message_leg`'s, and the instrument decides
    which paths are product rather than developer prose."""
    if not rel.endswith(".py") or rel.startswith("tests/"):
        return False
    return (rel.startswith(SURFACE_ROOTS) or "/" not in rel) and inventory.is_scannable(rel)


def surface_findings(rel: str, text: str | None) -> list[SurfaceFinding]:
    """The findings in one file: German in a message, or a file the leg could not read at all."""
    if text is None:
        return [SurfaceFinding(rel, 1, "unreadable", "the leg could not read the file")]
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [SurfaceFinding(rel, exc.lineno or 1, "unparsable", f"the leg could not parse it: {exc.msg}")]
    lines = text.splitlines()
    findings: list[SurfaceFinding] = []
    for kind, node in surface_messages(tree):
        quote = _literal_text(node)
        if not quote.strip():
            continue
        line = getattr(node, "lineno", 1)
        source = lines[line - 1] if 0 < line <= len(lines) else ""
        if inventory.PRAGMA in source and messages.MESSAGE_PRAGMA not in source:
            # The instrument's own device: a line may state plainly that its German is the point —
            # a vocabulary list, a quoted product string. The two markers mean one thing each.
            continue
        if messages.MESSAGE_PRAGMA in source:
            reason = source.split(messages.MESSAGE_PRAGMA, 1)[1].strip().strip("()").strip()
            if not reason:
                findings.append(
                    SurfaceFinding(rel, line, "unexplained exemption", f"{messages.MESSAGE_PRAGMA} carries no reason")
                )
            continue
        if surface_german(quote):
            words = ", ".join(sorted({w.lower() for w in SURFACE_WORD.findall(quote)} - SURFACE_FALSE_FRIENDS)[:6])
            findings.append(SurfaceFinding(rel, line, kind, f"{' '.join(quote.split())[:90]}  [{words}]"))
    return findings


#: Keys that name the developer as the reader: a value under one of them never reaches the screen,
#: so its German is developer prose wearing copy's clothes, and the surface leg reads it even in a
#: named product-text file. Deliberately compound words plus the leading underscore: `note` and
#: `why` on their own are labels this product does show — `why` is the column header „Warum" on the
#: provenance page, `note` the intro line of the creator dialog — and a leg that flags what a
#: reader reads stops being believed.
NON_USER_KEYS = frozenset({"devnote", "developernote", "maintainernote", "testonly"})


def _all_strings(node: object, key: str) -> list[tuple[str, str]]:
    """Every string under `node`, each paired with the last key it was reached through."""
    if isinstance(node, str):
        return [(key, node)]
    if isinstance(node, dict):
        return [pair for name, value in node.items() for pair in _all_strings(value, str(name))]
    if isinstance(node, list):
        return [pair for item in node for pair in _all_strings(item, key)]
    return []


def _non_user_strings(node: object, key: str = "") -> list[tuple[str, str]]:
    """The strings a reader is never shown, because their key says so."""
    if isinstance(node, dict):
        found: list[tuple[str, str]] = []
        for name, value in node.items():
            marked = str(name)
            spelling = marked.lower().replace("_", "").replace("-", "")
            if marked.startswith("_") or spelling in NON_USER_KEYS:
                found.extend(_all_strings(value, marked))
            else:
                found.extend(_non_user_strings(value, key))
        return found
    if isinstance(node, list):
        return [pair for item in node for pair in _non_user_strings(item, key)]
    return []


def is_copy_file(text: str | None) -> bool:
    """Whether the text is the shape a copy file has: one JSON object.

    The ratchet's exemption for a named path is tied to this, so a file that stops being a copy
    file stops being exempt: its German is measured again instead of hiding behind the name.
    """
    if text is None:
        return False
    try:
        return isinstance(json.loads(text), dict)
    except json.JSONDecodeError:
        return False


def copy_findings(rel: str, text: str | None) -> tuple[list[SurfaceFinding], int, bool]:
    """One named copy file: its findings, the German lines read as copy a reader is shown, and whether it is a copy file at all."""
    if not is_copy_file(text):
        return [], 0, False
    tree = json.loads(text or "")
    lines = text.splitlines()
    findings: list[SurfaceFinding] = []
    for key, value in _non_user_strings(tree):
        if not value.strip() or not surface_german(value):
            continue
        row = next((i for i, source in enumerate(lines) if value in source), 0)
        source = lines[row] if row < len(lines) else ""
        if inventory.PRAGMA in source:
            continue
        words = ", ".join(
            sorted({w.lower() for w in SURFACE_WORD.findall(value)} - SURFACE_FALSE_FRIENDS)[:6]
        )
        findings.append(
            SurfaceFinding(rel, row + 1, "not user copy", f"{key}: {' '.join(value.split())[:80]}  [{words}]")
        )
    return findings, inventory.hits_in(text), True


def surface_leg(
    paths: list[str],
    read_text: Callable[[str], str] | None,
    root: Path,
    *,
    printed: int = PRINTED_FINDINGS,
) -> tuple[int, list[str]]:
    """The sentences product code puts in front of a person: `raise`, `assert`, print and log calls.

    Neither of the other two legs asks about these. The line ratchet scores the file and compares a
    count, so German that arrived before the file's baseline entry is free — and the message leg is
    scoped to `tests/` by design. A German `ValueError` therefore reaches the developer on a path the
    tree measures as clean: `core/voice_config.py` held three of them and scored zero lines.

    No baseline here either, for the same reason `message_leg` carries none. The one escape is
    `scripts/message_language.py`'s marker on the line of the message, and it needs a reason: German
    a program shows its user is product text, and a bare marker would be the whitelist this gate
    refuses to keep.
    """
    findings: list[SurfaceFinding] = []
    read = 0
    for rel in paths:
        if not in_surface_scope(rel):
            continue
        try:
            text = read_text(rel) if read_text is not None else (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = None
        read += 1
        findings.extend(surface_findings(rel, text))
    copies: list[tuple[str, int, int]] = []
    for rel in paths:
        if not rel.endswith(".json") or not inventory.carries_user_text(rel):
            continue
        try:
            text = read_text(rel) if read_text is not None else (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = None
        found, german, parsed = copy_findings(rel, text)
        findings.extend(found)
        copies.append((rel, german, len(found), parsed))
    copy_lines = [
        f"  product copy: {rel} — {german} German line(s) read, {shown} outside what a reader is shown"
        if parsed
        else f"  product copy: {rel} — not a JSON object, measured as an ordinary file"
        for rel, german, shown, parsed in copies
    ]
    if not findings:
        return 0, [
            f"surface language: PASS — no German developer prose in {read} product file(s)"
        ] + copy_lines
    lines = [
        f"surface language: FAIL — German developer prose in {len(findings)} message(s) "
        f"over {len({f.rel for f in findings})} file(s)"
    ]
    for finding in findings[:printed]:
        lines.append(f"  {finding.rel}:{finding.line} {finding.kind}: {finding.quote}")
    if len(findings) > printed:
        lines.append(f"  ... {len(findings) - printed} more — python3 scripts/language_gate.py")
    lines.extend(copy_lines)
    lines.append(
        "Write those sentences in English. German a program shows its user is the product's own "
        f"surface: mark the message's line with `{messages.MESSAGE_PRAGMA}` and say who reads it."
    )
    return 1, lines


CJK_CLASSES: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("Han", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x2A6DF))),
    ("Hiragana", ((0x3040, 0x309F), (0x31F0, 0x31FF))),
    ("Katakana", ((0x30A0, 0x30FF),)),
    ("Hangul", ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7A3))),
    ("CJK punctuation", ((0x3000, 0x303F), (0xFF00, 0xFFEF))),
)

CJK_EXCERPT = 12


class CjkFinding(NamedTuple):
    rel: str
    line: int
    kind: str
    quote: str


#: The files whose content is one of these scripts on purpose, each with the reason it is
#: in the tree. Exact paths, no prefixes and no globs: a directory here would swallow the
#: developer code beside it, which is the permeation `test_a_sibling_of_a_named_file_stays_read`
#: refuses. An entry that no longer carries such a character is a finding of its own, so
#: the list cannot quietly outlive the content it was written for.
CJK_EXCEPTIONS: dict[str, str] = {
    "README.md": "the language switch row names README.zh-CN.md, whose own title is Chinese",
    "README.es.md": "the same language switch row in the Spanish README",
    "README.zh-CN.md": "the Chinese README — product copy translated on purpose",
    "marketplace/registry-curated.json": "plugin names in the publisher's own script",
    "marketplace/registry-snapshot.json": "a fetched registry snapshot; the names are the publishers'",
    "app/src/components/dashboard/ChatInput.test.tsx": "types Japanese into the composer to prove IME text survives",
    "app/src/lib/contextMeter.test.ts": "counts the tokens of a Han sample",
    "app/src/lib/pluginSurface.test.ts": "pushes a non-ASCII mount label through the URL builder",
    "tests/test_brand_headline_surfaces.py": "the Chinese headline the brand surfaces pin",
    "tests/test_dsml_bridge.py": "fullwidth bars inside a DSML token the bridge must survive",
    "tests/test_i18n_deep_verification.py": "a profile whose preferred_language is Japanese",
    "tests/test_memory_embed_onnx.py": "a retrieval query in Chinese and Japanese",
    "tests/test_readme_claims.py": "the Chinese number words the zh README claims",
    "tests/test_readme_contract.py": "the section headings README.zh-CN.md must carry",
    "tests/test_script_hygiene.py": "a mixed-script defect the hygiene check reports",
    "tests/test_tui_context_meter.py": "counts the tokens of a Han sample",
    "tests/test_w14_audit_fixes.py": "counts the tokens of a Han sample",
    "tests/test_w16_enterprise_hardening.py": "counts the tokens of a Han sample",
}


def cjk_class(char: str) -> str | None:
    """The writing system `char` belongs to, or None for the scripts this tree writes in."""
    point = ord(char)
    for name, ranges in CJK_CLASSES:
        for low, high in ranges:
            if low <= point <= high:
                return name
    return None


def cjk_findings(rel: str, text: str) -> list[CjkFinding]:
    """Every character of these scripts in one file, one finding per line that carries them."""
    if rel in CJK_EXCEPTIONS:
        return []
    findings: list[CjkFinding] = []
    for number, line in enumerate(text.splitlines(), 1):
        found = [char for char in line if cjk_class(char)]
        if found:
            excerpt = "".join(found[:CJK_EXCERPT])
            suffix = f" … +{len(found) - CJK_EXCERPT}" if len(found) > CJK_EXCERPT else ""
            findings.append(
                CjkFinding(rel, number, cjk_class(found[0]) or "?", f"{excerpt}{suffix}")
            )
    return findings


def cjk_leg(
    paths: list[str],
    read_text: Callable[[str], str] | None,
    root: Path,
    *,
    printed: int = PRINTED_FINDINGS,
) -> tuple[int, list[str]]:
    """Any character of Han, Hiragana, Katakana or Hangul outside a file named for it.

    The two German legs cannot see this script at all: the ratchet's instrument looks for
    umlauts and German words, and the message leg parses German word lists. A stray CJK
    string — the residue of a paste, a model reply copied into a fixture, a name carried in
    from a registry — walked past both, which is how two Chinese characters reached a report
    line in November 2026 and no gate said a word. These scripts do not arrive by accident
    the way a German noun does, so one character outside a named file is the finding; there
    is no baseline to age into.

    Files are read whole, including Markdown and JSON, because the tree's CJK sits in a
    README and two registry files rather than in code. A file that does not decode is binary
    and out of scope.
    """
    findings: list[CjkFinding] = []
    read = 0
    carries: dict[str, bool] = {}
    for rel in paths:
        try:
            text = read_text(rel) if read_text is not None else (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "\x00" in text:
            continue
        read += 1
        carries[rel] = any(cjk_class(char) for char in text)
        findings.extend(cjk_findings(rel, text))

    for rel, reason in CJK_EXCEPTIONS.items():
        if rel not in carries:
            # Only a whole-tree read can tell a deleted file from a partial list: `--staged`
            # and the tests hand over a few paths, and refusing those would refuse the hook.
            if read_text is None:
                findings.append(
                    CjkFinding(rel, 0, "named exception outside the tree", "no such tracked file")
                )
        elif not carries[rel]:
            findings.append(
                CjkFinding(rel, 0, "named exception without the script it names", "carries no such character")
            )
        elif not reason.strip():
            findings.append(CjkFinding(rel, 0, "named exception without a reason", reason))

    if not findings:
        return 0, [
            f"east asian script: PASS — no Han, Hiragana, Katakana or Hangul outside "
            f"{len(CJK_EXCEPTIONS)} named file(s) ({read} file(s) read)"
        ]
    lines = [
        f"east asian script: FAIL — {len(findings)} finding(s) over "
        f"{len({f.rel for f in findings})} file(s)"
    ]
    for finding in findings[:printed]:
        where = f"{finding.rel}:{finding.line}" if finding.line else finding.rel
        lines.append(f"  {where} {finding.kind}: {finding.quote}")
    if len(findings) > printed:
        lines.append(f"  ... {len(findings) - printed} more — python3 scripts/language_gate.py")
    lines.append(
        "Write it in English. A file that carries this script on purpose — a translated README, a "
        "publisher's own name, a test that proves CJK survives — belongs in CJK_EXCEPTIONS in "
        "scripts/language_gate.py with the reason it is in the tree."
    )
    return 1, lines


def measure(
    root: Path,
    *,
    list_files: Callable[[], list[str]] | None = None,
    read_text: Callable[[str], str] | None = None,
) -> dict[str, int]:
    """German marker lines per tracked path. Injectable so a fixture tree scores too."""
    if list_files is None:
        list_files = tracked_files(root)
    if read_text is None:
        def read_text(rel: str) -> str:
            return (root / rel).read_text(encoding="utf-8")
    counts = inventory.counts_for(list_files(), read_text)
    # The ratchet measures developer prose. A named product-text path holds the copy a reader is
    # shown in the interface, so a translation of the product would score here as a regression;
    # `surface_leg` reads the very same files and reports every line of them, which is where
    # German nobody is shown still fails the tree. The exemption is tied to the file still being a
    # copy file: named text that is no JSON object is measured like any other file in the tree.
    return {
        rel: hits
        for rel, hits in counts.items()
        if not inventory.carries_user_text(rel) or not is_copy_file(read_text(rel))
    }


def refuse_orphan_entries(baseline: dict[str, int], tracked: list[str]) -> None:
    """A baseline entry has to name a path the tree holds.

    `evaluate` compares the union of both key sets, so an entry for a deleted file scores as
    `old = N, new = 0` and lands in `lowered` — invisible. Left alone it becomes an allowance: the
    path can come back with N German lines and the per-file ratchet calls that clean, because the
    number it is compared against was earned by a file nobody measured since. Refusing the whole
    pass (exit 2, the same verdict as an unreadable baseline) forces the entry to be pruned with
    `--update` while the tree is genuinely cleaner, which is the only direction that lowers it.

    Whole-tree mode only. In `--staged` the scope is the few paths one commit carries, so a
    baseline entry outside that scope is expected and stays unjudged.
    """
    present = set(tracked)
    orphans = sorted(rel for rel in baseline if rel not in present)
    if orphans:
        raise GateError(
            f"baseline names {len(orphans)} path(s) the tree does not hold: "
            + ", ".join(orphans[:5])
            + (", …" if len(orphans) > 5 else "")
            + " — prune them with the whole-tree --update; an entry for a deleted file is an "
            "allowance for whoever recreates it"
        )


def staged_readers(root: Path) -> tuple[Callable[[], list[str]], Callable[[str], str]]:
    """Scope the measurement to the content a commit carries.

    `.husky/pre-commit` promises that no check in it scans a whole tree, and this gate was the one
    that still did: on a shared working tree it refused an unrelated commit over a line another
    worker had not finished yet. `EPHE_COMMIT_PATHS` narrows the index the same way `ci_local.sh`
    reads it, because the hook cannot see the pathspec `git commit -- <paths>` will use.
    """

    def list_files() -> list[str]:
        done = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            capture_output=True, text=True, check=True,
        )
        paths = [line for line in done.stdout.split("\0") if line]
        wanted = os.environ.get("EPHE_COMMIT_PATHS", "").split()
        return [path for path in paths if path in wanted] if wanted else paths

    def read_text(rel: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(root), "show", f":{rel}"],
            capture_output=True, text=True,
        )
        return done.stdout if done.returncode == 0 else ""

    return list_files, read_text


def load_baseline(path: Path, protected: tuple[str, ...]) -> dict[str, int]:
    """Read the German-line baseline; a shape that could hide growth is refused outright."""
    if not path.exists():
        raise GateError(
            f"no baseline at {path.name} (looked in {path.parent}); create it with {UPDATE_HINT}"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"baseline {path} cannot be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise GateError(f"baseline {path} must be a JSON object")
    unknown = sorted(set(raw) - BASELINE_KEYS)
    if unknown:
        raise GateError(
            f"baseline {path} carries unknown key(s) {', '.join(unknown)}. This gate has no "
            "exemption list — remove the key, or lower the baseline with --update."
        )
    if raw.get("policy") != POLICY or raw.get("version") != VERSION:
        raise GateError(
            f"baseline {path} is policy {raw.get('policy')!r} version {raw.get('version')!r}; "
            f"this gate speaks {POLICY!r} version {VERSION}"
        )
    files = raw.get("files")
    if not isinstance(files, dict):
        raise GateError(f"baseline {path} has no `files` mapping")
    clean: dict[str, int] = {}
    for rel, hits in files.items():
        if not isinstance(rel, str) or isinstance(hits, bool) or not isinstance(hits, int) or hits < 0:
            raise GateError(f"baseline {path} entry {rel!r} is not a non-negative line count")
        if rel.startswith(protected):
            raise GateError(
                f"baseline {path} records the protected path {rel!r}. German there is the "
                "product; the gate never measures it and must never be told it did."
            )
        clean[rel] = hits
    return clean


class Verdict(TypedDict):
    """The comparison's shape, typed so `report` iterates lists rather than `object`."""

    regressions: list[tuple[str, int, int]]
    lowered: list[tuple[str, int, int]]
    baseline_total: int
    measured_total: int
    measured_files: int


def evaluate(baseline: dict[str, int], measured: dict[str, int]) -> Verdict:
    """Compare two per-file counts. Growth anywhere is a regression, even if the total shrank."""
    regressions: list[tuple[str, int, int]] = []
    lowered: list[tuple[str, int, int]] = []
    regressions = []
    lowered = []
    for rel in sorted(set(baseline) | set(measured)):
        old, new = baseline.get(rel, 0), measured.get(rel, 0)
        if new > old:
            regressions.append((rel, old, new))
        elif new < old:
            lowered.append((rel, old, new))
    return {
        "regressions": regressions,
        "lowered": lowered,
        "baseline_total": sum(baseline.values()),
        "measured_total": sum(measured.values()),
        "measured_files": len(measured),
    }


def report(result: Verdict, *, offer: bool = True) -> tuple[int, list[str]]:
    """The operator's text, and the exit code: 1 on growth, 0 otherwise.

    A passing run offers the whole-tree `--update` whenever a file sits below its entry,
    in the same two lines the sister gates print. `offer` is false for a `--staged` pass:
    its narrow measurement cannot judge the rest of the tree, so it must not invite a
    whole-tree re-measurement.
    """
    regressions = result["regressions"]
    lowered = result["lowered"]
    total = result["measured_total"]
    lines: list[str] = []
    if regressions:
        grew = sum(new - old for _, old, new in regressions)
        lines.append(
            f"language gate: FAIL — German developer prose grew in "
            f"{len(regressions)} file(s) (+{grew} lines)"
        )
        for rel, old, new in regressions:
            lines.append(f"  {rel}: {old} -> {new} (+{new - old})")
        lines.append(f"  total {result['baseline_total']} -> {total} lines")
        lines.append(
            f"Rewrite those lines in English. Do not run `{UPDATE_HINT}` to cover them — "
            "--update only ever lowers this baseline."
        )
        return 1, lines
    if lowered:
        lines.append("language gate: PASS — no file grew past the baseline")
        lines.append(
            f"  total {result['baseline_total']} -> {total} lines "
            f"({result['measured_files']} files still carry German)"
        )
        if offer:
            lines.append(
                f"  {len(lowered)} file(s) sit below their baseline entry: the baseline can be lowered"
            )
            lines.append(f"  {UPDATE_HINT}")
        return 0, lines
    lines.append("language gate: PASS — the tree matches the baseline")
    lines.append(f"  total {total} lines over {result['measured_files']} files")
    return 0, lines


def write_baseline(path: Path, measured: dict[str, int]) -> None:
    """Freeze a measurement. Sorted keys, no timestamp: the file must diff cleanly."""
    payload = {
        "policy": POLICY,
        "version": VERSION,
        "instrument": "scripts/language_inventory.py",
        "total": sum(measured.values()),
        "files": measured,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_baseline(path: Path, measured: dict[str, int], protected: tuple[str, ...]) -> int:
    """Tighten the baseline to the current tree — never loosen it."""
    if not path.exists():
        write_baseline(path, measured)
        print(
            f"language gate: baseline created — {sum(measured.values())} German lines over "
            f"{len(measured)} files ({path.name})"
        )
        return 0
    before = load_baseline(path, protected)
    higher = [(rel, before[rel], measured[rel]) for rel in measured if measured[rel] > before.get(rel, 0)]
    if higher:
        print(
            f"language gate: FAIL — baseline was not written; --update only lowers it "
            f"({len(higher)} file(s) would rise)",
            file=sys.stderr,
        )
        for rel, old, new in sorted(higher):
            print(f"  {rel}: {old} -> {new} (+{new - old})", file=sys.stderr)
        print(
            f"  fix the wording in English first, then run {UPDATE_HINT} again",
            file=sys.stderr,
        )
        return 1
    write_baseline(path, measured)
    freed = len(set(before) - set(measured))
    dropped = sum(before.values()) - sum(measured.values())
    print(
        f"language gate: baseline lowered — {sum(before.values())} -> {sum(measured.values())} "
        f"German lines ({dropped} fewer, {freed} file(s) now clean)"
    )
    return 0


def main(
    argv: list[str] | None = None,
    *,
    list_files: Callable[[], list[str]] | None = None,
    read_text: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT, help="committed baseline")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to measure")
    parser.add_argument(
        "--update", action="store_true",
        help="lower the baseline to the current tree (refuses to raise it)",
    )
    parser.add_argument(
        "--staged", action="store_true",
        help="measure the staged blobs instead of the whole tree, for a pre-commit hook",
    )
    args = parser.parse_args(argv)
    try:
        if args.staged and args.update:
            raise GateError(
                "--update measures the whole tree; combining it with --staged would write a "
                "baseline from the few files one commit happens to carry"
            )
        protected = checked_protected_prefixes()
        tracked = None
        if args.staged and list_files is None and read_text is None:
            list_files, read_text = staged_readers(args.root)
        paths = list_files() if list_files is not None else tracked_files(args.root)()
        # One measurement path for the whole tree and for `--staged`: the exemption for a named
        # product-text file lives in `measure`, and a hook reading index blobs has to honour it the
        # same way a whole-tree run does — a commit of the copy file is where it first went red.
        measured = measure(args.root, list_files=lambda: paths, read_text=read_text)
        if args.update:
            return update_baseline(args.baseline, measured, protected)
        baseline = load_baseline(args.baseline, protected)
        if not args.staged:
            refuse_orphan_entries(baseline, paths)
        result = evaluate(baseline, measured)
    except GateError as exc:
        print(f"language gate: ERROR — {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else exc
        print(f"language gate: ERROR — git ls-files failed: {detail}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"language gate: ERROR — {exc}", file=sys.stderr)
        return 2
    code, lines = report(result, offer=not args.staged)
    message_code, message_report = message_leg(paths, read_text, args.root)
    surface_code, surface_report = surface_leg(paths, read_text, args.root)
    cjk_code, cjk_report = cjk_leg(paths, read_text, args.root)
    print("\n".join(lines))
    print("\n".join(message_report))
    print("\n".join(surface_report))
    print("\n".join(cjk_report))
    return max(code, message_code, surface_code, cjk_code)


if __name__ == "__main__":
    sys.exit(main())
