"""A commit pointer in shipped text either resolves or is known not to.

The public repository's history starts at the snapshot commit `docs/DEVELOPMENT.md` names; anything
older, and anything from a branch that never merged, answers `git show` with `unknown revision`. That
property lives between the text and the object store, so this test reads both — the same reason
`tests/test_dev_handle_gate.py` reads a shipped bundle: no product code can import a sentence.

The scan covers the text a reader gets: the docs, the product code, the gate scripts, the eval harnesses
with the trend rows they carry, the CI lanes and the CLI. A pointer is the same promise wherever it
sits, and the lanes turned out to hold the densest set of them. The scan excludes this file because it
names the shas it allows. The resolvable half needs history, which a shallow CI checkout does not
carry; there it skips and says so, while the allowlist half runs everywhere.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

PATTERNS = (
    "docs/**/*.md",
    "core/**/*.py",
    "server/**/*.py",
    "scripts/**/*.py",
    "scripts/**/*.sh",
    "scripts/**/*.json",
    "tests/**/*.py",
    "app/src/**/*.ts",
    "app/src/**/*.tsx",
    "evals/**/*.py",
    "evals/**/*.json",
    "evals/**/*.md",
    ".github/**/*.yml",
    ".github/**/*.md",
    "ephe_cli.py",
    "**/AGENTS.md",
)
EXTRA = ("README.md",)

#: Only a sha named by one of these words is a commit pointer, and the word has to sit right before
#: it. The token also has to carry a hex letter, which is what keeps `T14 from
#: \`20261010T2317-60x3-clean/runs/t14_r3.json\` — a run directory whose name begins with a date — out
#: of the count, along with every hex colour and content hash in the tree. A real sha of that length
#: with no letter in it is possible and has not been seen here. `run` and `compare` are here because
#: a CI lane records the receipt of a run by its head commit and a bench tool names the two commits
#: it compares; both name a commit as plainly as `commit` does. The word is matched case-insensitively
#: and the token is not, because git prints a sha lower-case and the tree holds upper-case hex that is
#: not one: the digit alphabet in `core/deck_design.py`, an action pin, a fixture digest.
ANCHOR = re.compile(
    r"(?i:commit|at|from|in|pushed|tagged|run|compare)\s+`?"
    r"(?<![0-9a-fA-F])(?=[0-9a-f]*[a-f])([0-9a-f]{7,40})(?![0-9a-fA-F])"
)

#: The one place a commit is named by a field rather than a sentence: a bench trend row records the
#: tree each point was measured on. Only these keys, so a `"sha256"` or a fixture id in the same file
#: stays out of the count.
JSON_KEYS = re.compile(
    r"\"(?:commit|head|tree|base)\"\s*:\s*\""
    r"(?<![0-9a-fA-F])(?=[0-9a-f]*[a-f])([0-9a-f]{7,40})(?![0-9a-fA-F])\""
)

#: Shas the tree cites that a clone of this repository cannot open. A reason says where the commit
#: is; an entry no file cites any more fails, so an allowance cannot outlive the pointer that earned
#: it. Every one predates this tree's published history, which is why the citing sentence carries the
#: substance instead of pointing a reader at an address they cannot open.
UNRESOLVABLE = {
    "77b0ce78": 'the tree the 2026-10-11 audit-log counts were taken on, before the public snapshot',
    "888f1a3ce957": 'a branch commit that never landed; the performance section names the tree it measured',
    "27d8bff": "not this repository: the upstream dependency's own main, cited as the dependency's state",
    "c10b9a99": 'the merge that pinned the lockfile pair, before the public snapshot',
    "f5d88653": 'the commit in which the tool_done reason_code convention was set',
    "4f2778c": 'one of the two bench runs the wall-clock budgets compare',
    "9d6efcd1": 'the other of the two bench runs the wall-clock budgets compare, and the 59/60 trend point of 2026-10-11',
    "ed64a3ed": 'the commit that landed the caller the browser-watch test names',
    "5ead3c23": 'the commit from which the action-pin test tracks its pins',
    "0054c641": 'the commit of the CI run whose wall-clock numbers that test records',
    "9910615d": 'the Dependabot commit that headed the pull whose run logged the clean-room venv-noise receipt; predates the public snapshot and no remote ref carries it',
    "dc6be266": 'the commit that closed the runner venv-cache leak the docklint comment cites, before the public snapshot',
    "f15190aa": 'the commit that landed the attribution rule the hygiene comment cites, before the public snapshot',
    "478b8aa2": 'the commit that made the engine token a file the desktop app can write',
    "2e095893": "before this tree's published history; the performance baseline names the commit the panel storage arrived whole in",
    "3ccca950": "before this tree's published history; the video wrapper names the commit that deleted the script it used to call",
    "766a4293": "not this repository: the tip of the version branch an upstream action publishes, cited as that action's state",
    "e834788a": "not this repository: the commit an upstream action's annotated tag points at, cited as that action's state",
}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def _scanned_paths() -> list[Path]:
    paths: set[Path] = set()
    for pattern in PATTERNS:
        paths |= set(REPO.glob(pattern))
    paths |= {REPO / name for name in EXTRA}
    return sorted(p for p in paths if p.is_file() and p.name != Path(__file__).name)


def _citations() -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for path in _scanned_paths():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in (ANCHOR, JSON_KEYS):
                for match in pattern.finditer(line):
                    rows.append((str(path.relative_to(REPO)), number, match.group(1)))
    return rows


def _resolvable(sha: str) -> bool:
    if _git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        return False
    return _git("merge-base", "--is-ancestor", sha, "HEAD").returncode == 0


def _has_history() -> bool:
    return _git("rev-parse", "--is-shallow-repository").stdout.strip() == "false"


def test_every_commit_pointer_resolves_or_is_known() -> None:
    citations = _citations()
    # A pattern that stopped matching would let the two assertions below pass for free. Measured on
    # this tree: 29 pointers, 16 of them allowed.
    assert len(citations) >= 25, f"the scan found {len(citations)} commit pointers; the pattern rotted"
    if not _has_history():
        pytest.skip("the checkout is shallow; no sha can be resolved against it here")
    unexplained = [
        f"{rel}:{number} {sha}"
        for rel, number, sha in citations
        if sha not in UNRESOLVABLE and not _resolvable(sha)
    ]
    assert not unexplained, (
        "commit pointers a clone cannot open and no reason covers: " + ", ".join(unexplained)
    )


def test_the_allowlist_names_a_pointer_the_tree_still_carries() -> None:
    # Raw text here: a second sha on a cited line reads `… commit 4f2778c (2026-09-24) and
    # 9d6efcd1 (2026-10-11)`, and the anchor names only the first of them.
    text = "\n".join(path.read_text(encoding="utf-8") for path in _scanned_paths())
    stale = sorted(sha for sha in UNRESOLVABLE if sha not in text)
    assert not stale, (
        f"allowlist entries no file cites: {stale} — prune them; an entry nobody cites is an "
        "allowance for whoever writes that pointer back"
    )


def test_the_allowlist_covers_only_citations_this_repo_could_not_have() -> None:
    """An entry claiming a commit is unreachable must not hide one that is reachable."""
    if not _has_history():
        pytest.skip("the checkout is shallow; no sha can be resolved against it here")
    resolvable = sorted(sha for sha in UNRESOLVABLE if _resolvable(sha))
    assert not resolvable, (
        f"allowlisted as unreachable but resolvable from HEAD: {resolvable} — the entry is now a "
        "way to wave a broken pointer through"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
