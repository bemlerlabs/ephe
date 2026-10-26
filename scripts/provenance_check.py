#!/usr/bin/env python3
"""A released tag has to name a commit that sits on the trunk.

The v0.1.7 release was landed by a rebase merge: GitHub rewrote the commits, the
tag kept the pre-rewrite lineage (`db1c0ba4`) and `main` named a different commit
with the same tree. The artifacts were right and the provenance was not, which is
the kind of defect nobody notices until a tag has to be checked against the
source it claims to build.

This gate walks every `v*` tag, asks whether its commit is an ancestor of the
base branch, and fails for a tag that is not. `scripts/provenance-baseline.json`
records the one known divergence with its reason; a baseline entry that has
become an ancestor is reported so the list can shrink. Diverged tags are never
moved — the fix for a new one is to land by fast-forward and re-cut, and the
fix for an old one is a recorded entry.

Exit codes: 0 every tag is on the base or recorded, 1 an unrecorded divergence,
2 the repository or the baseline cannot be read.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DEFAULT = Path(__file__).resolve().parent / "provenance-baseline.json"
TAG_PREFIX = "v"


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args), cwd=str(cwd or REPO_ROOT), capture_output=True, text=True, check=False
    )


def tags(root: Path) -> list[str]:
    done = git("tag", "--list", f"{TAG_PREFIX}*", "--sort=v:refname", cwd=root)
    if done.returncode != 0:
        raise ValueError(f"git tag failed: {done.stderr.strip()}")
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def commit_of(root: Path, tag: str) -> str:
    done = git("rev-list", "-n", "1", f"{tag}^{{commit}}", cwd=root)
    if done.returncode != 0 or not done.stdout.strip():
        raise ValueError(f"{tag} does not resolve to a commit")
    return done.stdout.strip()


def is_ancestor(root: Path, commit: str, base: str) -> bool:
    done = git("merge-base", "--is-ancestor", commit, base, cwd=root)
    if done.returncode not in (0, 1):
        raise ValueError(f"cannot compare {commit[:8]} with {base}: {done.stderr.strip()}")
    return done.returncode == 0


def read_baseline(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path.name}: {exc}") from exc
    known = payload.get("known_diverged")
    if not isinstance(known, list) or not all(isinstance(item, str) for item in known):
        raise ValueError(f"{path.name} carries no known_diverged list")
    return known


def baseline_at(root: Path, ref: str, path: Path) -> list[str] | None:
    """The baseline as the base ref carries it; None when that ref has no file yet."""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{path.name} sits outside the checkout; --baseline-at needs a tracked file") from exc
    done = git("show", f"{ref}:{rel}", cwd=root)
    if done.returncode != 0:
        return None
    try:
        payload = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot read {path.name} at {ref}: {exc}") from exc
    known = payload.get("known_diverged") or []
    return [item for item in known if isinstance(item, str)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="checkout to judge")
    parser.add_argument("--base", default="origin/main", help="trunk ref the tags must sit on")
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT)
    parser.add_argument(
        "--baseline-at",
        help="reject an entry this baseline adds over the one at this ref (CI passes the base)",
    )
    args = parser.parse_args(argv)

    try:
        known = set(read_baseline(args.baseline))
        names = tags(args.root)
    except ValueError as exc:
        print(f"provenance: cannot decide: {exc}")
        return 2

    if not names:
        print("provenance: cannot decide: the checkout lists no v* tag")
        return 2
    if git("rev-parse", "--verify", args.base, cwd=args.root).returncode != 0:
        print(f"provenance: cannot decide: base ref {args.base} does not resolve")
        return 2

    if args.baseline_at:
        try:
            previous = baseline_at(args.root, args.baseline_at, args.baseline)
        except ValueError as exc:
            print(f"provenance: cannot decide: {exc}")
            return 2
        if previous is None:
            print(
                f"provenance: note: {args.baseline_at} carries no baseline yet; "
                "this commit introduces it"
            )
        else:
            added = sorted(known - set(previous))
            if added:
                print(
                    "provenance: FAIL — the baseline adds "
                    + ", ".join(added)
                    + f" over {args.baseline_at}; a new entry is a decision the owner records "
                    "in its own commit before the tag exists"
                )
                return 1

    diverged: list[tuple[str, str]] = []
    healed: list[str] = []
    for tag in names:
        try:
            commit = commit_of(args.root, tag)
            on_trunk = is_ancestor(args.root, commit, args.base)
        except ValueError as exc:
            print(f"provenance: cannot decide: {exc}")
            return 2
        if on_trunk and tag in known:
            healed.append(tag)
        if not on_trunk and tag not in known:
            diverged.append((tag, commit))
        if on_trunk:
            mark = "on base"
        else:
            mark = "DIVERGED (recorded)" if tag in known else "DIVERGED"
        print(f"provenance: {tag:>14} {commit[:8]} {mark}")

    for tag in healed:
        print(f"provenance: note: {tag} sits on {args.base}; the baseline entry can go")
    if diverged:
        for tag, commit in diverged:
            print(f"provenance: FAIL {tag} names {commit[:8]}, which {args.base} does not contain")
        print(
            "provenance: land by fast-forward and cut the tag from the trunk; for an "
            "existing divergence, record it in the baseline with its reason"
        )
        return 1
    print(f"provenance: PASS — {len(names)} tag(s) on {args.base} or recorded in the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
