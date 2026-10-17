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
the lab notebook and publishes a clean-room snapshot later, so the gate is over new commits and
`--report` is the only thing that reads the old ones.
"""
from __future__ import annotations

import argparse
import json
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


def authors(rev_range: str) -> list[tuple[str, str]]:
    raw = git("log", "--format=%H%x09%ae", rev_range)
    out = []
    for line in raw.splitlines():
        sha, _, email = line.partition("\t")
        out.append((sha[:8], email.strip().lower()))
    return out


def check(rev_range: str) -> list[str]:
    register = allowed()
    problems = []
    for sha, email in authors(rev_range):
        if email not in register:
            problems.append(
                f"{sha}: author address {email!r} is not in {REGISTER.name}. A bare address on a "
                f"domain anyone can register lets that stranger become the displayed author of the "
                f"commit, so this repository accepts the noreply form only: "
                f"<account-id>+<login>@users.noreply.github.com. Way out: set "
                f"`git config --global user.email` to that address and amend or recommit.")
    return problems


def report() -> str:
    register = allowed()
    counts: Counter[str] = Counter()
    for line in git("log", "--all", "--format=%ae").splitlines():
        counts[line.strip().lower()] += 1
    lines = [f"{REGISTER.name}: {len(register)} accepted addresses", ""]
    for email, n in counts.most_common():
        verdict = register.get(email) or "UNREGISTERED"
        lines.append(f"  {n:>5}  {email:<55} {verdict}")
    unregistered = sum(n for email, n in counts.items() if email not in register)
    lines.append("")
    lines.append(f"{unregistered} of {sum(counts.values())} commits across all refs carry an "
                 f"address this register does not name. History is left as written; new commits "
                 f"are refused.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--range", dest="rev_range", default="HEAD~1..HEAD",
                        help="commits to judge (default: the commit about to land)")
    parser.add_argument("--report", action="store_true",
                        help="print every identity in history and whether it is registered")
    args = parser.parse_args(argv)

    if args.report:
        print(report())
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
    print(f"attribution: pass — every author address in {args.rev_range} is registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
