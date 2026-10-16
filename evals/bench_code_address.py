"""evals/bench_code_address.py — the address a bench number has to carry.

A rate is only reproducible if it says which code produced it. The 150 manifests in
`evals/runs/` and the ten points in `evals/bench-trend.json` do not: `run_task` writes a
commit nowhere, and the trend file's `commit` label is taken from the tree the *scorer*
runs in, hours after the reps. Measured 2026-10-10, the same class bit three ways — a
number scored against a backend from before the tree, a baseline run that reused old
manifests, and a pass^3 pass counting units over 50 commits.

The address is the committed content of the surface that is scored, not of the harness:
`core/` and `server/` tree OIDs from HEAD plus HEAD's own sha, because the server is what
answers the rep. `evals/` is deliberately absent — it is the tool, and a tool commit does
not make a number a different number (the same boundary `bench_preflight.py` had to learn
the hard way, `6483dd70`).

Two rules the shapes below encode:

* Absent is not zero. A manifest that predates this field and a manifest whose address
  failed to be read are both `None`, and the scorer calls them *unaddressed* rather than
  counting them as agreement. A run with no git is still a run; a run with no address is
  not a reference.
* One stand per cohort. Manifests carrying different commits are a mixed cohort and say
  so with the number of runs per stand, because "58/60" over two commits is not one number.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

#: The surface a rep measures: the code that answers the turn.
SURFACE = ("core", "server")

FIELDS = ("commit", "commit_short", "surface", "surface_sha", "dirty")


def _git(argv: list[str], root: Path) -> str | None:
    """stdout of a git call, or None when git itself is the problem."""
    try:
        proc = subprocess.run(argv, cwd=str(root), capture_output=True, text=True)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def tree_oids(root: Path, surface: tuple[str, ...] = SURFACE) -> dict[str, str] | None:
    """The committed content address of each surface directory, without walking it."""
    oids: dict[str, str] = {}
    for name in surface:
        oid = _git(["git", "rev-parse", f"HEAD:{name}"], root)
        if oid is None:
            return None
        oids[name] = oid
    return oids


def surface_sha(oids: dict[str, str]) -> str:
    """One digest over the whole measured surface, order-independent."""
    joined = "\n".join(f"{name} {oids[name]}" for name in sorted(oids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:40]


def address(root: Path | None = None, surface: tuple[str, ...] = SURFACE) -> dict | None:
    """The code address of this tree, or None when the tree cannot say.

    None is written into the manifest as None. The scorer reads that as unaddressed and
    refuses the append, which is the difference between an old number and a broken run.
    """
    root = root or Path(__file__).resolve().parents[1]
    commit = _git(["git", "rev-parse", "HEAD"], root)
    oids = tree_oids(root, surface)
    if not commit or oids is None:
        return None
    dirty_raw = _git(["git", "status", "--porcelain=v1", "--", *surface], root)
    dirty = sorted({line[2:].split(" -> ")[-1].strip().strip('"')
                    for line in (dirty_raw or "").splitlines() if line[2:]})
    return {"commit": commit, "commit_short": commit[:7], "surface": oids,
            "surface_sha": surface_sha(oids), "dirty": dirty}


def of(row: dict) -> dict | None:
    """A manifest's address, or None for a legacy row and for a row that could not read one."""
    value = row.get("code_address")
    return value if isinstance(value, dict) and value.get("commit") else None


def cohort_state(rows: list[dict]) -> dict:
    """How many measured stands a cohort spans, and how many rows carry no address.

    The stand is keyed on `surface_sha` rather than on the commit: two commits can hold the
    identical `core/` and `server/` trees (docs, tests, evals land between reps all day), and
    those are one number. A second *surface* digest is the case that breaks a number, because
    two different servers answered the reps.
    """
    reps_per_surface: dict[str, int] = {}
    commits: set[str] = set()
    unaddressed = 0
    for row in rows:
        addr = of(row)
        if addr is None:
            unaddressed += 1
            continue
        commits.add(addr["commit"])
        key = str(addr.get("surface_sha") or "unread")
        reps_per_surface[key] = reps_per_surface.get(key, 0) + 1
    total = len(rows)
    return {
        "manifests": total,
        "unaddressed": unaddressed,
        "stands": len(reps_per_surface),
        "commits": len(commits),
        "reps_per_stand": reps_per_surface,
        "status": _status(total, unaddressed, len(reps_per_surface)),
    }


def _status(total: int, unaddressed: int, stands: int) -> str:
    if total == 0:
        return "empty"
    if unaddressed == total:
        return "legacy"
    if unaddressed:
        return "partly-unaddressed"
    if stands > 1:
        return "moved-mid-run"
    return "single-stand"
