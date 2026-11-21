#!/usr/bin/env python3
"""Agent instructions: the hub, its area files and the links between them, held to their caps.

A rule an agent never loads does not bind anything. The repository therefore has one hub
(`AGENTS.md`) that states what the product is, the four invariants and every command a change has
to run, and a small set of area files that add the constraints of one directory. This gate keeps
that structure honest: the caps that stop the hub from becoming a document nobody reads, the
routing table whose rows have to name a directory and an area file that exist, the `make` targets
and `scripts/` paths the prose promises, the sections a reader expects, and the language rule.

Three numbers decide the caps. The hub has to fit one context load beside the code it describes, so
12,000 characters is its ceiling; an area file carries one directory's constraint and stops at
8,000. The whole chain a fresh agent can load before it opens any code — the hub plus every area
file — stays under 30,000, which is what stops the set from growing one plausible file at a time.
The duplicate check is the other half of the same concern: a block longer than 200 characters that
appears in both the hub and an area is the copy that goes stale, and the rule is to link it instead.

Exit codes: 0 every rule holds, 1 at least one finding (each one is printed with its path).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import language_inventory as inventory  # noqa: E402  (path bootstrap above)

REPO_ROOT = SCRIPTS_DIR.parent
ROOT_FILE = "AGENTS.md"
OVERRIDE_FILE = "AGENTS.override.md"
AREA_HEADER = "Applies on top of the root AGENTS.md"

ROOT_MAX_CHARS = 12_000
AREA_MAX_CHARS = 8_000
CHAIN_MAX_CHARS = 30_000
DUPLICATE_MIN_CHARS = 200

#: The headings a reader and a loader both rely on, in the order the hub tells its story.
REQUIRED_SECTIONS = (
    "What Ephe Is",
    "Invariants",
    "Commands",
    "Structure",
    "Areas",
    "Rules that apply everywhere",
    "Boundaries",
    "Further reading",
)
INVARIANT_COUNT = 4

FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
CODE_SPAN = re.compile(r"`([^`\n]+)`")
MAKE_CALL = re.compile(r"\bmake\s+([a-z][a-z0-9-]*)\b")
MAKE_TARGET = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):")
SCRIPT_REF = re.compile(r"(?<![\w./-])((?:app/)?scripts/[A-Za-z0-9_./-]+\.(?:py|mjs|js|ts|sh))")
GITIGNORE_NEEDLE = OVERRIDE_FILE


@dataclass(frozen=True)
class Finding:
    """One broken rule: which rule, which file, and what the reader has to see."""

    check: str
    path: str
    detail: str


def sections_of(text: str) -> dict[str, str]:
    """Bodies of the `## heading` sections, keyed by heading text."""
    out: dict[str, str] = {}
    title: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if title is not None:
                out[title] = "\n".join(body).strip()
            title = line[3:].strip()
            body = []
        elif title is not None:
            body.append(line)
    if title is not None:
        out[title] = "\n".join(body).strip()
    return out


def headings_in_order(text: str) -> list[str]:
    return [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]


def routing_rows(areas_body: str) -> list[tuple[str, str]]:
    """(path, area file) pairs from the markdown table in the Areas section.

    A row is a table row whose first cell is a path and whose second cell names a file, either
    as a markdown link or in backticks. The header and the separator carry neither, so they fall
    out without a positional rule.
    """
    rows: list[tuple[str, str]] = []
    for line in areas_body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        path = cells[0].strip("` ")
        if not path or " " in path or "/" not in path:
            continue
        link = re.search(r"\[[^\]]*\]\(([^)]+)\)", cells[1])
        area = link.group(1).strip() if link else cells[1].strip("` ")
        if area.endswith(".md"):
            rows.append((path, area))
    return rows


def code_only(text: str) -> str:
    """The fenced blocks and inline code spans, where a command is stated.

    Prose that uses the word "make" is not a command claim, and the gate should not read it as
    one.
    """
    chunks = FENCE.findall(text) + CODE_SPAN.findall(text)
    return "\n".join(chunks)


def make_targets(makefile_text: str) -> set[str]:
    out: set[str] = set()
    for line in makefile_text.splitlines():
        match = MAKE_TARGET.match(line)
        if match:
            out.add(match.group(1))
    return out


def duplicate_blocks(text: str) -> list[str]:
    """Paragraphs longer than the duplicate threshold, stripped for comparison."""
    blocks = re.split(r"\n\s*\n", text)
    return [block.strip() for block in blocks if len(block.strip()) > DUPLICATE_MIN_CHARS]


def script_refs(text: str) -> set[str]:
    return set(SCRIPT_REF.findall(text))


def german_lines(path: str, text: str) -> int:
    """Lines the repository's own language instrument reads as German prose."""
    counted = inventory.counts_for([path], lambda _rel: text)
    return int(counted.get(path, 0))


def audit(
    root: Path,
    *,
    read_text: Callable[[str], str] | None = None,
    exists: Callable[[str], bool] | None = None,
) -> list[Finding]:
    """Every rule, measured against the tree under `root`."""
    if read_text is None:
        def read_text(rel: str) -> str:
            return (root / rel).read_text(encoding="utf-8")
    if exists is None:
        def exists(rel: str) -> bool:
            return (root / rel).exists()

    try:
        root_text = read_text(ROOT_FILE)
    except (OSError, UnicodeDecodeError):
        return [Finding("root", ROOT_FILE, "the hub is missing or unreadable")]

    findings: list[Finding] = []
    root_chars = len(root_text)
    if root_chars > ROOT_MAX_CHARS:
        findings.append(Finding(
            "root-cap", ROOT_FILE,
            f"{root_chars} characters, cap {ROOT_MAX_CHARS}",
        ))

    bodies = sections_of(root_text)
    order = [title for title in headings_in_order(root_text) if title in REQUIRED_SECTIONS]
    missing = [title for title in REQUIRED_SECTIONS if title not in bodies]
    for title in missing:
        findings.append(Finding("section", ROOT_FILE, f"missing section '## {title}'"))
    if not missing and order != list(REQUIRED_SECTIONS):
        findings.append(Finding(
            "section-order", ROOT_FILE,
            "expected " + ", ".join(REQUIRED_SECTIONS) + "; found " + ", ".join(order),
        ))

    invariants = re.findall(r"^### ", bodies.get("Invariants", ""), re.M)
    if "Invariants" in bodies and len(invariants) != INVARIANT_COUNT:
        findings.append(Finding(
            "invariants", ROOT_FILE,
            f"{len(invariants)} invariant headings, expected {INVARIANT_COUNT}",
        ))

    rows = routing_rows(bodies.get("Areas", ""))
    if "Areas" in bodies and not rows:
        findings.append(Finding("areas", ROOT_FILE, "the routing table names no area file"))

    texts: dict[str, str] = {ROOT_FILE: root_text}
    chain = root_chars
    for area_path, area_file in rows:
        if not exists(area_path):
            findings.append(Finding("area-path", ROOT_FILE, f"routing row names {area_path}, which does not exist"))
        if not exists(area_file):
            findings.append(Finding("area-file", area_file, "named in the routing table but missing"))
            continue
        try:
            area_text = read_text(area_file)
        except (OSError, UnicodeDecodeError):
            findings.append(Finding("area-file", area_file, "unreadable"))
            continue
        texts[area_file] = area_text
        area_chars = len(area_text)
        if area_chars > AREA_MAX_CHARS:
            findings.append(Finding(
                "area-cap", area_file,
                f"{area_chars} characters, cap {AREA_MAX_CHARS}",
            ))
        chain += area_chars
        if AREA_HEADER not in area_text:
            findings.append(Finding(
                "area-header", area_file,
                f"missing the line '{AREA_HEADER}'",
            ))

    if chain > CHAIN_MAX_CHARS:
        findings.append(Finding(
            "chain-cap", ROOT_FILE,
            f"hub plus {len(rows)} area file(s) is {chain} characters, cap {CHAIN_MAX_CHARS}",
        ))

    try:
        makefile_text = read_text("Makefile")
    except (OSError, UnicodeDecodeError):
        makefile_text = ""
        findings.append(Finding("make", "Makefile", "unreadable, so every make command is unverified"))
    else:
        targets = make_targets(makefile_text)
        for path, text in texts.items():
            for target in sorted(set(MAKE_CALL.findall(code_only(text)))):
                if target not in targets:
                    findings.append(Finding(
                        "make", path, f"names 'make {target}', which the Makefile does not define",
                    ))

    for path, text in texts.items():
        for ref in sorted(script_refs(text)):
            if not exists(ref) and not (not ref.startswith("app/") and exists(f"app/{ref}")):
                findings.append(Finding("script", path, f"names {ref}, which does not exist"))

    root_blocks = duplicate_blocks(root_text)
    area_files = [area for _path, area in rows if area in texts]
    for area_file in area_files:
        for block in duplicate_blocks(texts[area_file]):
            if block in root_blocks:
                findings.append(Finding(
                    "duplicate", area_file,
                    f"{len(block)} characters repeated verbatim from {ROOT_FILE}; link it instead",
                ))
    for index, area_file in enumerate(area_files):
        for other in area_files[index + 1:]:
            shared = set(duplicate_blocks(texts[area_file])) & set(duplicate_blocks(texts[other]))
            for block in sorted(shared):
                findings.append(Finding(
                    "duplicate", area_file,
                    f"{len(block)} characters repeated verbatim in {other}; link it instead",
                ))

    for path, text in texts.items():
        count = german_lines(path, text)
        if count:
            findings.append(Finding(
                "language", path,
                f"{count} line(s) read as German developer prose; only the product surface stays German",
            ))

    try:
        gitignore = read_text(".gitignore")
    except (OSError, UnicodeDecodeError):
        gitignore = ""
    if GITIGNORE_NEEDLE not in gitignore.splitlines():
        findings.append(Finding(
            "override", ".gitignore",
            f"does not ignore {OVERRIDE_FILE}, which the hub documents as a personal file",
        ))

    return findings


def measured(root: Path, read_text: Callable[[str], str]) -> dict[str, object]:
    """The numbers the report carries, independent of the findings."""
    out: dict[str, object] = {"root": 0, "areas": {}}
    try:
        root_text = read_text(ROOT_FILE)
    except (OSError, UnicodeDecodeError):
        return out
    out["root"] = len(root_text)
    areas: dict[str, int] = {}
    for _path, area_file in routing_rows(sections_of(root_text).get("Areas", "")):
        try:
            areas[area_file] = len(read_text(area_file))
        except (OSError, UnicodeDecodeError):
            continue
    out["areas"] = areas
    return out


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    read_text: Callable[[str], str] | None = None,
    exists: Callable[[str], bool] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Check the agent instruction hub and its areas.")
    parser.add_argument("--root", type=Path, default=root or REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="print the result as one JSON object")
    args = parser.parse_args(argv)
    base = args.root

    findings = audit(base, read_text=read_text, exists=exists)
    if read_text is None:
        def read_text(rel: str) -> str:
            return (base / rel).read_text(encoding="utf-8")
    numbers = measured(base, read_text)
    area_count = len(numbers["areas"]) if isinstance(numbers["areas"], dict) else 0

    if args.json:
        print(json.dumps({
            "ok": not findings,
            "root": str(base / ROOT_FILE),
            "caps": {
                "root": ROOT_MAX_CHARS,
                "area": AREA_MAX_CHARS,
                "chain": CHAIN_MAX_CHARS,
            },
            "measured": numbers,
            "findings": [
                {"check": f.check, "path": f.path, "detail": f.detail} for f in findings
            ],
        }, indent=1, sort_keys=True))
    else:
        for finding in findings:
            print(f"FAIL {finding.check} {finding.path}: {finding.detail}")
        if findings:
            print(f"agents-md: {len(findings)} finding(s)")
        else:
            print(
                f"OK agents-md: hub {numbers['root']} characters, "
                f"{area_count} area file(s), every named path resolves"
            )
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
