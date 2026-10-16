#!/usr/bin/env python3
"""The prose ratchet over a stated list of paths rather than over the whole tree.

`python3 scripts/prose_tells.py --strict` compares the 200 tracked prose files against
`scripts/prose-tells-baseline.json` and costs 5.4 s here (measured 2026-10-11). Its verdict covers
files the committing strand does not own: on this worktree an unrelated new file took the tree-wide
gate from PASS to RED, which would have refused every commit in the tree. `.husky/pre-commit` calls
`scripts/ci_local.sh`, which calls this script with the paths it is judging in `EPHE_STAGED_PATHS`.

Nothing is reimplemented. `counts_for` and `evaluate` are the functions the tree-wide run calls,
given contents read from the index rather than from disk, so a file another strand has edited
without staging cannot make this commit look guilty or clean.

One limit comes with the scope and is printed on every run: the repeated-header class compares a
file's first wording against every other file's, so a banner copied from a path outside the scope
is invisible here. `ci-gates.yml` measures the corpus and holds that class.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import language_gate as gate  # noqa: E402  (path bootstrap above)
import language_inventory as inventory  # noqa: E402
import prose_tells as tells  # noqa: E402

PREFIX = "prose-scope"


def staged_blob(rel: str, unreadable: list[str]):
    """The content the index holds for `rel`, which is what a commit would carry.

    A path with no index blob is recorded and skipped: an empty string would score zero findings
    and read as a clean file, which is the shape of a silent pass.
    """
    done = subprocess.run(
        ["git", "show", f":{rel}"], capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        unreadable.append(rel)
        return ""
    return done.stdout


def in_prose_scope(rel: str) -> bool:
    """Whether the tree-wide ratchet would measure this path at all.

    `prose_tells.tracked()` asks git for `PROSE_ROOTS`, so a path outside those roots is not in the
    gate. Mirroring that here is what keeps a local run from refusing a commit over content CI never
    looks at: the first version of this script filtered on extension alone and went red on
    `.github/workflows/tests.yml`, a file the census has never measured.
    """
    return any(rel == root or rel.startswith(root + "/") for root in tells.PROSE_ROOTS)


def main() -> int:
    paths = [p for p in os.environ.get("EPHE_STAGED_PATHS", "").splitlines() if p]
    if not paths:
        print(f"{PREFIX}: no paths in EPHE_STAGED_PATHS, so nothing was measured")
        return 0

    scanned = [p for p in paths if in_prose_scope(p) and inventory.is_scannable(p)]
    outside = len(paths) - len(scanned)
    if not scanned:
        print(f"{PREFIX}: {len(paths)} path(s) in scope, none of them prose the ratchet measures")
        return 0

    try:
        baseline = tells.load_baseline(tells.BASELINE_DEFAULT)
    except gate.GateError as exc:
        print(f"{PREFIX}: the committed baseline cannot be read: {exc}")
        return 1

    unreadable: list[str] = []
    counts = tells.counts_for(scanned, lambda rel: staged_blob(rel, unreadable))
    result = tells.evaluate(baseline, counts)

    for rel, old, new in result["regressions"]:
        print(f"{PREFIX}: {rel}: {old} -> {new} (+{new - old} tell)")
    for rel in sorted(set(unreadable)):
        print(f"{PREFIX}: no index blob for {rel}: it is not judged here")
    print(
        f"{PREFIX}: {len(scanned)} path(s) measured ({sum(counts.values())} tell(s) in scope, "
        f"baseline {len(baseline)} files tracked), {outside} path(s) outside the roots the ratchet "
        "measures, corpus-wide repeated headers left to ci-gates.yml"
    )
    if result["regressions"]:
        return 1
    # An unreadable path is a scope that was not judged, so the caller has to hear it even when
    # everything measured is clean.
    return 1 if unreadable else 0


if __name__ == "__main__":
    raise SystemExit(main())
