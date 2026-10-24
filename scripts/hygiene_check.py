#!/usr/bin/env python3
"""Repository hygiene: the rules that are mechanical, in one place.

`CI Gates` and the pre-commit hook both call this file, so local and CI cannot disagree about
what a clean tree is. Case collision is the rule that only bites after a checkout on a
case-insensitive filesystem, which is every macOS box in this pipeline: `git ls-files` can carry
`a.py` and `A.py` while only one of them survives a working tree, so a leg on the laptop and a
leg on the Spark test different trees from the same commit.

Measured on 2026-10-11 over the 2031 tracked files: zero case collisions and zero matches for
every pattern below. That is why both halves exit non-zero -- the gate is written against a tree
that already satisfies it, not against a backlog someone has to read.
"""
from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys

#: Measured against the 2031 tracked files on 2026-10-11: every entry below matched nothing. A
#: pattern joins this list only once the tree is clean of it, so the file doubles as the record of
#: what the repository has decided never to carry.
ARTIFACT_SOURCES = {
    "python bytecode": r"(^|/)__pycache__/|\.pyc$",
    "macos metadata": r"(^|/)\.DS_Store$",
    "node modules": r"(^|/)node_modules/",
    "local database": r"\.(db|sqlite3?|db-wal|db-shm)$",
    # `.env.example` and its siblings are templates this repository ships on purpose (AGENTS.md
    # names one); only a dotenv that is not a template is private state.
    "dotenv": r"(^|/)\.env(\.(?!(example|template|sample|dist)$)[^/]+)?$",
    "key or certificate": r"\.(pem|key|p12|pfx)$",
    "virtualenv": r"(^|/)\.venv/|(^|/)venv/",
    "build output": r"(^|/)dist/|\.egg-info/",
    "tool cache": (r"(^|/)\.cache/|(^|/)\.pytest_cache/|(^|/)\.mypy_cache/"
                   r"|(^|/)\.ruff_cache/|(^|/)\.coverage$|(^|/)coverage\.xml$"),
    "log file": r"\.log$",
    "patched wheel tree": r"(^|/)_patched/",
    "pth pointer": r"\.pth$",
}
ARTIFACT_PATTERNS = {name: re.compile(src) for name, src in ARTIFACT_SOURCES.items()}

#: A public verification key ships so signatures can be checked; it is not private state.
PUBLIC_KEYS = frozenset({"plugins/first-party.pub.pem"})


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True, text=True)
    return [p for p in out.stdout.split("\0") if p]


def case_collisions(files: list[str]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for path in files:
        groups[path.casefold()].append(path)
    return sorted((k, v) for k, v in groups.items() if len(v) > 1)


def tracked_artifacts(files: list[str]) -> list[tuple[str, str]]:
    hits = []
    for name, pattern in ARTIFACT_PATTERNS.items():
        for path in files:
            if pattern.search(path) and path not in PUBLIC_KEYS:
                hits.append((name, path))
    return sorted(hits)


def report(files: list[str]) -> int:
    collisions = case_collisions(files)
    artifacts = tracked_artifacts(files)
    print(f"hygiene: {len(files)} tracked files")
    print(f"  case collisions: {len(collisions)} groups")
    for folded, paths in collisions:
        print(f"    {folded}: {', '.join(paths)}")
    print(f"  tracked artifacts: {len(artifacts)} files across {len(ARTIFACT_PATTERNS)} patterns")
    for kind, path in artifacts:
        print(f"    {kind}: {path}")
    if collisions:
        print("::error::case-colliding paths -- only one of each survives a case-insensitive "
              "checkout, so the legs on macOS and Linux are not testing the same tree",
              file=sys.stderr)
    if artifacts:
        print("::error::generated or private state is tracked -- caches, databases and key "
              "material belong to a machine, not to a commit", file=sys.stderr)
    return 1 if (collisions or artifacts) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="check every rule and exit non-zero on any finding")
    args = parser.parse_args(argv)
    if args.all:
        return report(tracked_files())
    parser.error("name the check to run, for example --all")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
