#!/usr/bin/env python3
"""Ephe — move the addresses the changelog names onto the commits the trunk carries.

A rebase merge rewrites every commit it lands. The `[Unreleased]` block is written on
the branch, so its bullets name short shas that exist only there, and
`scripts/changelog_unreleased.py` reads the string: the trunk then reports its own wave
as unrecorded until a person re-types the addresses by hand. This does that re-typing
from git, and refuses to invent an address it cannot prove.

Match rule: a named sha that is not on the base is looked up in the local object store
for its subject, the base's log is searched for that subject, and the candidate is taken
only when its diff carries the same stable patch id. So a remap is proven by the bytes,
not by a sentence that two changes could share. No match is reported as still pending; a
subject that matches several commits, or matches one whose diff differs, is refused,
because guessing which change a bullet meant is exactly the mistake this tool exists to
stop.

Run from the repository root::

    python3 scripts/changelog_remap.py --base public/main
    python3 scripts/changelog_remap.py --base public/main --check
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from changelog_unreleased import (
    CHANGELOG_DEFAULT,
    SHA_TOKEN,
    unreleased_block,
)

ROOT = Path(__file__).resolve().parents[1]
HOUSE_WIDTH = 8


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def resolve(token: str) -> str | None:
    """The long sha a token names, or None when nothing here holds that object."""
    try:
        return git("rev-parse", "--verify", f"{token}^{{commit}}")
    except RuntimeError:
        return None


def on_base(long: str, base: str) -> bool:
    """True when the commit is reachable from the base ref."""
    done = subprocess.run(
        ["git", "merge-base", "--is-ancestor", long, base],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return done.returncode == 0


def subject_of(long: str) -> str:
    return git("show", "-s", "--format=%s", long)


def base_log(base: str, since: str | None) -> list[tuple[str, str]]:
    rev = f"{since}..{base}" if since else base
    out = git("log", "--format=%H%x09%s", rev)
    rows = []
    for line in out.splitlines():
        if "\t" in line:
            sha, subject = line.split("\t", 1)
            rows.append((sha, subject))
    return rows


def find_on_base(subject: str, rows: list[tuple[str, str]]) -> list[str]:
    return [sha for sha, text in rows if text == subject]


def patch_id(rev: str) -> str:
    """The stable patch id of a commit's own diff, empty when it carries none.

    A subject can be shared by two different changes; the bytes of the diff are what say
    whether the commit that landed is the commit the bullet names, so no remap happens
    without this agreeing.
    """
    show = subprocess.run(
        ["git", "show", rev], cwd=ROOT, capture_output=True, check=False
    )
    if show.returncode != 0 or not show.stdout:
        return ""
    done = subprocess.run(
        ["git", "patch-id", "--stable"], cwd=ROOT, input=show.stdout,
        capture_output=True, check=False,
    )
    fields = done.stdout.decode().split()
    return fields[0] if fields else ""


def tokens_in_block(block: str) -> list[str]:
    """Every sha the block names, in the order they appear, without duplicates."""
    seen: list[str] = []
    for token in SHA_TOKEN.findall(block):
        if token not in seen:
            seen.append(token)
    return seen


def plan(text: str, base: str) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """(remaps, pending, refused) for the `[Unreleased]` block of `text`."""
    span = unreleased_block(text)
    if span is None:
        raise SystemExit("changelog-remap: no [Unreleased] section in CHANGELOG.md")
    lines = text.splitlines(keepends=True)
    block = "".join(lines[span[0]:span[1]])
    # The whole base history, not the window since the last tag: the block carries bullets
    # written before a cut, and an address that exists on the base two releases down is still
    # an address a reader can resolve.
    rows = base_log(base, None)
    remaps: list[tuple[str, str]] = []
    pending: list[str] = []
    refused: list[str] = []
    for token in tokens_in_block(block):
        long = resolve(token)
        if long is None:
            # An address written for a branch whose objects are gone: nothing here can
            # say what landed from it, so the line is left exactly as it is.
            refused.append(f"{token} (no such object in this repository)")
            continue
        if on_base(long, base):
            continue
        subject = subject_of(long)
        hits = find_on_base(subject, rows)
        if not hits:
            pending.append(f"{token} {subject}")
            continue
        wanted = patch_id(long)
        agreed = [hit for hit in hits if wanted and patch_id(hit) == wanted]
        if len(agreed) == 1:
            remaps.append((token, agreed[0][:HOUSE_WIDTH]))
        elif len(hits) > 1:
            refused.append(
                f"{token} {subject} — {len(hits)} commits on {base} carry that subject "
                "and none of their diffs agree"
            )
        else:
            refused.append(
                f"{token} {subject} — the subject is on {base} as {hits[0][:HOUSE_WIDTH]}, "
                "but the two diffs differ, so this is a different change"
            )
    return remaps, pending, refused


def apply_remaps(text: str, remaps: list[tuple[str, str]]) -> str:
    """Swap each named sha for the one the base carries.

    Every address in this file sits between backticks — a bullet's ``(`a1b2c3d4`)`` and a wave
    pointer's comma list ``(`a1b2c3`, `d4e5f6`)`` — so the backtick pair is the whole context,
    and a shorter token can never be mistaken for the prefix of a longer one.
    """
    for old, new in remaps:
        text = text.replace(f"`{old}`", f"`{new}`")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="public/main",
                        help="the ref the addresses must exist on (default: public/main)")
    parser.add_argument("--check", action="store_true",
                        help="report what is stale and change nothing")
    args = parser.parse_args()

    try:
        git("rev-parse", "--verify", f"{args.base}^{{commit}}")
    except RuntimeError:
        print(f"changelog-remap: cannot decide: {args.base} resolves to no commit")
        return 2

    path = CHANGELOG_DEFAULT
    text = path.read_text(encoding="utf-8")
    remaps, pending, refused = plan(text, args.base)

    for old, new in remaps:
        print(f"remap    {old} -> {new}")
    for line in pending:
        print(f"pending  {line}")
    for line in refused:
        print(f"refused  {line}")

    if not remaps and not pending and not refused:
        print(f"changelog-remap: every address in [Unreleased] is on {args.base}")
        return 0
    if refused:
        print("changelog-remap: refuse to write — an address could not be matched to one commit")
        return 1
    if args.check:
        if remaps:
            print(f"changelog-remap: {len(remaps)} address(es) named that {args.base} "
                  f"carries under another sha")
            return 1
        print(f"changelog-remap: every address the block names resolves on {args.base}")
        return 0
    path.write_text(apply_remaps(text, remaps), encoding="utf-8")
    print(f"changelog-remap: {len(remaps)} address(es) moved to {args.base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
