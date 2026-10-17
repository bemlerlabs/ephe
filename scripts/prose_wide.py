#!/usr/bin/env python3
"""Prose wide tier: the four shapes the census measures but does not yet hold.

`scripts/prose_inventory.py` carries the eight classes that
`scripts/prose-tells-baseline.json` was written over, and `scripts/prose_tells.py` gates
them. The shapes here were added on 2026-10-10 after counting what each one costs this
tree: a detector that finds nothing new joins the ratchet at once, and a detector that
finds lines in files other conversations are editing is registered and reported first.
Ratcheting four classes on the day they ship would put 64 tells on people who did nothing.

The module is separate for a reason the census already documents twice:
`architecture_check.mjs` compares the count of `maxFileLines` findings against the frozen
38, so one file crossing 400 lines turns every finding of that rule into an error and the
report exits 1. `prose_inventory.py` and `prose_tells.py` were 378 and 373 lines at the
cut, which is the whole headroom a second detector each would have needed.

Read the numbers with `python3 scripts/prose_tells.py --wide`; gate on them, if the owner
chooses to, with `python3 scripts/prose_tells.py --update --wide`.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from prose_inventory import (  # noqa: E402  (path bootstrap above)
    ADJECTIVES,
    BDD_SHAPE,
    Finding,
    HEADER_SKIP,
    _form_of,
    chunk_lines,
    chunks_of,
    marker_body,
    strip_rule_runs,
    words,
)

CLIKE_RESTATED_DOC = "clike-restated-doc"
SPLIT_RHETORIC = "split-rhetoric"
MARKETING_ADJECTIVE_WIDE = "marketing-adjective-wide"
REPEATED_BANNER = "repeated-banner"
WIDE_CLASSES = (
    CLIKE_RESTATED_DOC,
    SPLIT_RHETORIC,
    MARKETING_ADJECTIVE_WIDE,
    REPEATED_BANNER,
)

# Words that are a claim on a landing page and a plain property in an engineer's sentence:
# borrowing a check that already exists, naming a deck tier, saying a budget is uncapped.
# These read as prose about the work, so they sit one tier below `marketing-adjective`.
# `unlimited` and `granular` were tried here the same day and dropped: five of the nine
# lines they collected state a quantity, which is a fact about the code.
ADJECTIVES_WIDE = re.compile(
    r"\b(?:leverag\w*|enterprise[- ]grade|infinitely|comprehensive|robustly|intuitive\w*)\b",
    re.I,
)

CAMEL_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]+|[a-z0-9]+")


def camel_parts(name: str) -> set[str]:
    """The words inside an identifier, camelCase included.

    `_name_parts` lowercases before it splits, which is right for the snake_case this
    repository's Python uses and wrong for `getUser`, where it leaves one unusable word.
    Measured on the 505 .ts/.tsx/.js/.mjs files under the roots on 2026-10-10.
    """
    parts: set[str] = set()
    for chunk in re.split(r"[_\W]+", name):
        parts.update(w.lower() for w in CAMEL_WORD.findall(chunk) if len(w) > 2)
    return parts


# A name that takes an argument list. `const x = 5` and `interface Row` are left out on
# purpose: a comment over a field list documents the fields, and only a comment over a
# callable can restate the thing it names. The return type is optional because
# `renderRows(): void {` is the ordinary way to write it in TypeScript.
CALLABLE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:"
    r"function\s+(\w+)\s*[<(]"
    r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>"
    r"|(\w+)\s*\([^)]*\)\s*(?::[^{}=]+)?\{"
    r"|(\w+)\s*\([^)]*\)\s*(?::[^{}=]+)?=>"
    r"|(\w+)\s*:\s*(?:async\s*)?\([^)]*\)\s*=>"
    r")"
)
# `switch (kind) {` parses as a callable and the comment above it reads as its docstring.
CONTROL = frozenset(
    "if else for while switch case do try catch finally return throw yield await with "
    "new delete typeof instanceof in of super do_while".split()
)


def callable_name(line: str) -> str | None:
    match = CALLABLE.match(line)
    if not match:
        return None
    name = next((g for g in match.groups() if g), None)
    return None if name and name.lower() in CONTROL else name


def first_wording(chunk: str) -> str:
    """The first line of a comment chunk that actually carries wording."""
    for line in chunk.splitlines():
        body = marker_body(line).strip("/*").strip()
        if body and not body.startswith("@"):
            return body
    return ""


def clike_restates(comment: str, name: str) -> bool:
    """The Python rule, carried onto a comment block above a callable."""
    first = first_wording(comment)
    if not first or len(first) < 8 or BDD_SHAPE.search(first):
        return False
    parts = camel_parts(name)
    if not parts or not any(part in first.lower() for part in parts):
        return False
    return len([w for w in words(first) if not _form_of(w, parts)]) <= 1


def clike_restated(rel: str, text: str, chunks: list[tuple[int, str, str]]) -> list[Finding]:
    """`// Gets the user.` over `export function getUser()` reads as generated text."""
    if Path(rel).suffix not in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".rs"}:
        return []
    src = text.splitlines()
    found: list[Finding] = []
    for row, kind, chunk in chunks:
        if kind != "comment":
            continue
        below = next((line for line in src[row - 1 + len(chunk.splitlines()): row + 4] if line.strip()), "")
        name = callable_name(below)
        if name and clike_restates(chunk, name):
            found.append(Finding(rel, row, CLIKE_RESTATED_DOC, first_wording(chunk)[:90]))
    return found


# The figure the ratchet looks for needs the comma on the same line, so the two ways a
# person writes it when the line runs out were invisible: 34 dash lines and 46 run-overs
# across the roots on 2026-10-10.
RHETORIC_DASH = re.compile(r"[—–]\s*(?:not|rather than|instead of)\b", re.I)
RHETORIC_RUNON = re.compile(r"^(?:[-*]\s*)?(?:not|rather than|instead of)\s+\S", re.I)


def split_rhetoric_findings(rel: str, chunks: list[tuple[int, str, str]]) -> list[Finding]:
    # A python comment is one chunk per line, so the line before a run-over has to be
    # found by row adjacency: the chunk a line arrives in is one line wide.
    rows = [(row, line) for cr, _kind, chunk in chunks for row, line in chunk_lines(cr, chunk)]
    found: list[Finding] = []
    for index, (row, line) in enumerate(rows):
        body = marker_body(line)
        if RHETORIC_DASH.search(body):
            found.append(Finding(rel, row, SPLIT_RHETORIC, body[:90]))
            continue
        if not index:
            continue
        previous_row, previous = rows[index - 1]
        if row != previous_row + 1 or not RHETORIC_RUNON.match(body):
            continue
        # a run-over counts when the line above ends mid-sentence, which is the only shape
        # where `not …` is the second half of a figure and not a sentence of its own
        if marker_body(previous).endswith(","):
            found.append(Finding(rel, row, SPLIT_RHETORIC, body[:90]))
    return found[1:]


def _wide_line_findings(rel: str, chunks: list[tuple[int, str, str]]) -> list[Finding]:
    found: list[Finding] = []
    for row, _kind, chunk in chunks:
        for line_row, line in chunk_lines(row, chunk):
            body = marker_body(line)
            if body and ADJECTIVES_WIDE.search(body) and not ADJECTIVES.search(body):
                found.append(Finding(rel, line_row, MARKETING_ADJECTIVE_WIDE, body[:90]))
    return found


def wide_findings_for(rel: str, text: str) -> list[Finding]:
    """Every wide-tier tell this file's developer prose carries, in source order."""
    chunks = chunks_of(rel, text)
    found = _wide_line_findings(rel, chunks)
    found.extend(clike_restated(rel, text, chunks))
    found.extend(split_rhetoric_findings(rel, chunks))
    return sorted(found, key=lambda f: (f.row, f.cls))


# `repeated-header` reads the first eight rows of a file, so a banner repeated deeper in a
# tree could never be counted. Three files is the number that separates a habit from a
# coincidence on this tree (2026-10-10: 21 wordings, 43 files beyond the first).
BANNER_MIN_FILES = 3
BANNER_MIN_WORDS = 3
BANNER_MIN_CHARS = 12
# Exempt while the owner's signature ruling is open. The brand line and the Given/When/Then
# and TDD-order conventions are the two shapes the census already calls house style, and a
# counter that reports them as boilerplate would only teach people to switch it off.
BANNER_EXEMPT = re.compile(
    r"^(?:◑|ephe\s*[–-]|©|given\s*/\s*when|given-when-then|rule:\s*(?:the\s+)?(?:these\s+)?"
    r"tests?\b|then\b|when\b|given\b)",
    re.I,
)


def banner_wordings(texts: dict[str, str]) -> dict[str, list[str]]:
    """Every wording carried by at least BANNER_MIN_FILES files, with the files in order."""
    where: dict[str, list[str]] = {}
    for rel in sorted(texts):
        seen: set[str] = set()
        for _row, _kind, chunk in chunks_of(rel, texts[rel]):
            for line in chunk.splitlines():
                body = strip_rule_runs(marker_body(line)).strip(" \t\"'`*")
                if len(body) < BANNER_MIN_CHARS or len(words(body)) < BANNER_MIN_WORDS:
                    continue
                if HEADER_SKIP.match(body) or BANNER_EXEMPT.match(body):
                    continue
                seen.add(body.casefold())
        for key in seen:
            where.setdefault(key, []).append(rel)
    return {k: v for k, v in where.items() if len(v) >= BANNER_MIN_FILES}


def wide_score(texts: dict[str, str]) -> tuple[dict[str, int], Counter[str], dict[str, list[str]]]:
    """Wide findings per path and per class, plus the repeated banner wordings."""
    counts: dict[str, int] = {}
    by_class: Counter[str] = Counter()
    for rel, text in texts.items():
        found = wide_findings_for(rel, text)
        if found:
            counts[rel] = counts.get(rel, 0) + len(found)
            by_class.update(f.cls for f in found)
    groups = banner_wordings(texts)
    for files in groups.values():
        for rel in files[1:]:
            counts[rel] = counts.get(rel, 0) + 1
            by_class[REPEATED_BANNER] += 1
    return counts, by_class, groups


def merge(counts: dict[str, int], extra: dict[str, int]) -> dict[str, int]:
    out = dict(counts)
    for rel, hits in extra.items():
        out[rel] = out.get(rel, 0) + hits
    return out


def describe(groups: dict[str, list[str]], by_class: Counter[str], *, classes: bool, banners: bool) -> None:
    """The wide tier in the census: the class table, then the repeated banner wordings."""
    if classes:
        print()
        for cls in WIDE_CLASSES:
            print(f"{by_class.get(cls, 0):6d}  {cls} (measured, outside the ratchet)")
    if banners:
        print()
        for wording, files in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f"{len(files):4d}x  {wording[:70]!r}  {files[0]}")
