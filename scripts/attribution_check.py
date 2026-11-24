#!/usr/bin/env python3
"""Attribution register: a new commit may only carry an identity this repository names.

GitHub resolves a commit's author email against whichever account has verified that address and
caches the answer in its Contributors graph, so an author address is an asset that can be taken
over rather than a label. Measured 2026-10-11: one of our own commits is displayed under a GitHub
account nobody in this project knows, and two of the addresses in our history sit on domains
that sit on domains the project no longer controls. A bare address on such a domain is a
claim waiting for whoever registers it next; the domains are named in no tracked file, by
owner rule 2026-10-16. This decides
which addresses may appear from now on.

The commits already written keep their addresses. The standing decision keeps this history as
the lab notebook and publishes a clean-room snapshot later, so the gate is over new commits:
`--identity` from the pre-commit hook judges the commit that does not exist yet, `--range` from
`hygiene.yml` judges the commits a change carries, and `--report` is what reads the old ones.
`--report` over a whole branch is the only thing that holds the written history to the exceptions
listed here, and no test in this tree runs it: a claim about history is only as fresh as the last
run of this instrument, and the sentence carrying it should say which run that was.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTER = REPO_ROOT / ".github" / "identities.json"

def git(*args: str) -> str:
    return subprocess.run(("git", "-C", str(REPO_ROOT), *args), capture_output=True,
                          text=True, check=True).stdout


def allowed() -> dict[str, str]:
    data = json.loads(REGISTER.read_text(encoding="utf-8"))
    names = dict(data.get("humans") or {})
    names.update(data.get("bots") or {})
    return {email.lower(): who for email, who in names.items()}


def identities(rev_range: str) -> list[tuple[str, str, str]]:
    """(short sha, author, committer) for every commit in the range."""
    raw = git("log", "--format=%H%x09%ae%x09%ce", rev_range)
    out = []
    for line in raw.splitlines():
        sha, author, committer = line.split("\t")
        out.append((sha[:8], author.strip().lower(), committer.strip().lower()))
    return out


def check(rev_range: str) -> list[str]:
    register = allowed()
    problems = []
    for sha, author, committer in identities(rev_range):
        for role, email in (("author", author), ("committer", committer)):
            if email in register:
                continue
            problems.append(
                f"{sha}: {role} address {email!r} is not in {REGISTER.name}. A bare address on a "
                f"domain anyone can register lets that stranger become the displayed {role} of the "
                f"commit, so this repository accepts the noreply form only: "
                f"<account-id>+<login>@users.noreply.github.com. Way out: set `user.email`, "
                f"`GIT_AUTHOR_EMAIL` and `GIT_COMMITTER_EMAIL` to that address and recommit; "
                f"`--author` alone leaves the committer unregistered.")
    return problems


def _config(key: str) -> str:
    """`git config` read that stays quiet when the key is unset."""
    done = subprocess.run(("git", "-C", str(REPO_ROOT), "config", key),
                          capture_output=True, text=True)
    return done.stdout.strip()


def identity_problems() -> list[str]:
    """Judge the addresses the next commit on this machine would carry.

    A push event reaches `hygiene.yml` after its commits already sit on `main`, so that leg can
    report a rule it can no longer apply; eighteen public commits are the measurement. This is the
    half that refuses beforehand, and it reads the same variables git itself would: an override
    over `user.email`, and the committer falling back to the author.
    """
    register = allowed()
    configured = _config("user.email").lower()
    author = (os.environ.get("GIT_AUTHOR_EMAIL") or configured).lower()
    committer = (os.environ.get("GIT_COMMITTER_EMAIL") or author).lower()
    problems = []
    for role, email, sources in (
        ("author", author, "`GIT_AUTHOR_EMAIL` or `user.email`"),
        ("committer", committer, "`GIT_COMMITTER_EMAIL`, `GIT_AUTHOR_EMAIL` or `user.email`"),
    ):
        if email and email in register:
            continue
        detail = (f"{role} address {email!r} is not in {REGISTER.name}" if email
                  else f"{role} address is empty; nothing sets it ({sources})")
        problems.append(
            f"{detail}. A bare address on a domain anyone can register lets that stranger become "
            f"the displayed {role} of the commit, so this repository accepts the noreply form "
            f"only: <account-id>+<login>@users.noreply.github.com. Way out: `git config "
            f"--global user.email <account-id>+<login>@users.noreply.github.com`, and the same "
            f"value in {sources} if something exports it.")
    return problems


def _counts(field: str) -> Counter[str]:
    return Counter(line.strip().lower() for line in git("log", "--all", f"--format=%{field}").splitlines())


def _section(title: str, counts: Counter[str], register: dict[str, str]) -> tuple[list[str], int]:
    lines = [f"{title}:"]
    for email, n in counts.most_common():
        verdict = register.get(email) or "UNREGISTERED"
        lines.append(f"  {n:>5}  {email:<55} {verdict}")
    unregistered = sum(n for email, n in counts.items() if email not in register)
    return lines, unregistered


def report() -> str:
    register = allowed()
    author_counts = _counts("ae")
    committer_counts = _counts("ce")
    lines = [f"{REGISTER.name}: {len(register)} accepted addresses", ""]
    author_lines, unregistered_authors = _section("authors", author_counts, register)
    lines.extend(author_lines)
    lines.append("")
    committer_lines, unregistered_committers = _section("committers", committer_counts, register)
    lines.extend(committer_lines)
    lines.append("")
    lines.append(f"{unregistered_authors} of {sum(author_counts.values())} commits across all refs "
                 f"carry an author address this register does not name; "
                 f"{unregistered_committers} carry an unregistered committer address. History is "
                 f"left as written; new commits are refused.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--range", dest="rev_range", default="HEAD~1..HEAD",
                        help="commits to judge (default: the commit about to land)")
    parser.add_argument("--report", action="store_true",
                        help="print every identity in history and whether it is registered")
    parser.add_argument("--identity", action="store_true",
                        help="judge the addresses the next commit on this machine would carry, "
                             "instead of a range of commits that already exist")
    args = parser.parse_args(argv)

    if args.report:
        print(report())
        return 0

    if args.identity:
        problems = identity_problems()
        if problems:
            for line in problems:
                print(f"attribution: {line}", file=sys.stderr)
            return 1
        print("attribution: pass — the author and committer this machine would write are registered")
        return 0

    try:
        problems = check(args.rev_range)
    except subprocess.CalledProcessError as exc:
        print(f"attribution: cannot read {args.rev_range!r} ({exc.stderr.strip() or exc})", file=sys.stderr)
        return 2

    if problems:
        for line in problems:
            print(f"attribution: {line}", file=sys.stderr)
        return 1
    print(f"attribution: pass — every author and committer address in {args.rev_range} is registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
