#!/usr/bin/env python3
"""Refuse a comment or docstring that cites a file this tree does not contain.

The gates and the suite carry their reasoning in comments, and a comment pointing at a page that
never existed is worse than no comment: the next reader trusts the pointer and stops reading the
code. Two shapes are refused inside the scanned regions.

  - a dated citation in the docs/ naming style the suite grew, where the name carries a stamp like
    a report date, the word PLAN or the word DRAFT; refused whether or not such a file exists,
    because a dated page goes stale the moment it is written and a gate fact has to outlive one
    measurement;
  - any citation of a path that does not resolve to a file in this checkout, including a
    `path:line` or `path:first-last` pointer landing past the end of a file that does exist.

What counts as a citation is the set of paths a comment treats as the home of a claim: a document
under `docs/`, a Python module under `tests/`, `scripts/`, `core/` or `server/`, a workflow under
`.github/`. A path naming something a command reads or writes is not a claim's home, so build
output, generated data and the front-end sources stay outside this check; the boundary is drawn by
kind, and the reason is that the check refuses to guess whether a path is evidence or an argument.

Scanned regions are comments and docstrings, never ordinary string literals. A test that writes a
fixture named after a document has to name it in a string, and those names are inputs the test
invents; a comment is a claim its author vouches for, and that is what this checks.

One exemption exists, and it is written down. A removal fence has to name the path it forbids, and
that path is absent on purpose, so a comment line may read:

    # citation:absent <path> - why it must stay gone

The marker exempts exactly the path that follows it, and only inside its own comment block. A dated
name is refused beside the marker too: the stamp is what is being refused, not the absence. Every
use in this repository is visible with `rg -n "citation:absent"`.

Two things this check deliberately does not try. It does not read a cited file to confirm a quoted
sentence or a section number still says what the comment claims - that needs a human or a fresh
measurement. And it carries no allow-list beyond that marker: a finding is fixed by writing the
fact into the comment, by pointing at a file that exists, or by measuring the number again, which
is what the same rules asked of every citation before this gate existed.

Run:
    .venv/bin/python scripts/citation_check.py
    .venv/bin/python scripts/citation_check.py --root . --print-scanned
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
import tokenize
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Roots whose comments are claims about this repository. `docs/` prose is checked by
#: scripts/readme_check.py, which reads the document list rather than the citations.
SCANNED_ROOTS = ("scripts", "tests", ".github")
SCANNED_SUFFIXES = {".py", ".yml", ".yaml", ".sh"}

#: Paths a comment treats as the home of a claim. An extension ends at a word end - a further
#: letter or another dot-and-letter - so a front-end source named beside a cited document stays
#: the front-end source it is, a sentence may still end in the period after `.md`, and the deeper
#: root in `app/scripts/bundle_budget.py` owns that whole path.
CITATION_KINDS = (
    re.compile(r"docs/[A-Za-z0-9_./+-]+\.md"),
    re.compile(r"(?:tests|scripts|core|server)/[A-Za-z0-9_./+-]+\.(?:py|mjs|sh|sql)"),
    re.compile(r"\.github/[A-Za-z0-9_./+-]+\.ya?ml"),
)
CITATION = re.compile(
    r"(?<![A-Za-z0-9_./-])(?P<path>(?:" + "|".join(pattern.pattern for pattern in CITATION_KINDS) + r"))"
    r"(?::(?P<lines>\d+)(?:-(?P<to>\d+))?)?(?![A-Za-z0-9_-]|\.[A-Za-z0-9])"
)

#: The naming style the suite's phantom citations took: a docs page whose name carries a date,
#: PLAN or DRAFT.
DATED_DOC = re.compile(
    r"(?<![A-Za-z0-9_./-])(?P<path>docs/[A-Za-z0-9_./+-]+_(?:20\d{2}[-0-9]*|PLAN|DRAFT)"
    r"[A-Za-z0-9_.+-]*\.md)(?![A-Za-z0-9_-]|\.[A-Za-z0-9])"
)

#: A comment line may exempt one deliberately absent path, named after the marker, with its reason.
ABSENT_MARKER = re.compile(r"citation:absent\s+(?P<path>[A-Za-z0-9_./+-]+)")

COMMENT_MARK = "#"


@dataclass
class Finding:
    path: str
    line: int
    citation: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}: {self.citation}"


def _python_regions(text: str) -> list[tuple[int, str]]:
    """Return (line_number, text) for every comment and docstring in a Python source."""
    regions: list[tuple[int, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc and node.body:
                    regions.append((getattr(node.body[0], "lineno", 1), doc))
    try:
        tokens = list(tokenize.generate_tokens(StringIO(text).readline))
    except (IndentationError, SyntaxError, tokenize.TokenError):
        tokens = []
    for token in tokens:
        if token.type == tokenize.COMMENT:
            regions.append((token.start[0], token.string))
    return regions


def _comment_regions(text: str) -> list[tuple[int, str]]:
    """Return (line_number, text) for the comments of a YAML or shell source.

    A `#` inside a quoted scalar is content, so a trailing comment counts only when the quotes
    before it balance.
    """
    regions: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(COMMENT_MARK):
            regions.append((number, stripped))
            continue
        index = line.find(COMMENT_MARK)
        if index > 0 and line[:index].count('"') % 2 == 0 and line[:index].count("'") % 2 == 0:
            regions.append((number, line[index:]))
    return regions


def _line_count(path: Path, cache: dict[Path, int]) -> int:
    if path not in cache:
        try:
            cache[path] = len(path.read_text(encoding="utf-8").splitlines())
        except OSError:
            cache[path] = -1
    return cache[path]


def _exemptions(block: str) -> set[str]:
    return {match.group("path") for match in ABSENT_MARKER.finditer(block)}


def scan_text(text: str, origin: str, line_at: int, root: Path, cache: dict[Path, int]) -> list[Finding]:
    """Every refusal-worthy citation in one comment or docstring block."""
    findings: list[Finding] = []
    exempt = _exemptions(text)
    dated_spans = [(m.start("path"), m.end("path")) for m in DATED_DOC.finditer(text)]
    for match in DATED_DOC.finditer(text):
        rel = match.group("path")
        findings.append(
            Finding(
                origin,
                line_at + text[: match.start("path")].count("\n"),
                rel,
                "dated citation; a page stamped with a date, PLAN or DRAFT is not a home for a "
                "fact the gates have to hold - write the fact here or measure it again",
            )
        )
    for match in CITATION.finditer(text):
        start, end = match.start("path"), match.end("path")
        if any(start >= a and end <= b for a, b in dated_spans):
            continue  # refused by name above, and exempting it there covers it here
        rel = match.group("path")
        if rel in exempt:
            continue
        cited = root / rel
        line = line_at + text[:start].count("\n")
        if not cited.is_file():
            findings.append(
                Finding(origin, line, rel, "dangling citation; no such file in this checkout")
            )
            continue
        if not match.group("lines"):
            continue
        last = int(match.group("to") or match.group("lines"))
        available = _line_count(cited, cache)
        if last > available:
            findings.append(
                Finding(
                    origin,
                    line,
                    f"{rel}:{match.group('lines')}",
                    f"citation points past the end of the file, which has {available} line(s)",
                )
            )
    return findings


def scan_file(path: Path, root: Path, cache: dict[Path, int]) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    origin = path.relative_to(root).as_posix()
    regions = _python_regions(text) if path.suffix == ".py" else _comment_regions(text)
    findings: list[Finding] = []
    for line_at, block in regions:
        findings.extend(scan_text(block, origin, line_at, root, cache))
    return findings


def scan(root: Path) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    scanned = 0
    cache: dict[Path, int] = {}
    for rel_root in SCANNED_ROOTS:
        base = root / rel_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            scanned += 1
            findings.extend(scan_file(path, root, cache))
    return findings, scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--print-scanned", action="store_true", help="count the files read")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        findings, scanned = scan(root)
    except OSError as exc:
        print(f"citation-check: FAIL - {exc}", file=sys.stderr)
        return 1
    if args.print_scanned:
        print(f"scanned {scanned} file(s) under {', '.join(SCANNED_ROOTS)}")
    for finding in findings:
        print(f"problem: {finding}", file=sys.stderr)
    if findings:
        print(f"citation-check: FAIL - {len(findings)} problem(s)", file=sys.stderr)
        return 1
    print(f"citation-check: PASS - 0 problem(s) in {scanned} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
