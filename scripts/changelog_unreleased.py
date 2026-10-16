#!/usr/bin/env python3
"""Keep the CHANGELOG `[Unreleased]` block current with the commit subjects since the last tag.

Every commit in this tree carries a Conventional Commit subject (`feat(scope): ...`), so the
section a change belongs to is already written down; a hand-maintained header is the one place
that knowledge gets lost. `--draft` prints the block a release manager pastes. `--check` is the
gate: it refuses when a changelog-worthy commit since the last tag is named nowhere in the block,
reading a commit as named when its short sha appears there. `--write` splices the missing entries
into the file. Commits that landed before this instrument existed are recorded once in
`scripts/changelog-baseline.json`, the ratchet shape `scripts/prose-tells-baseline.json` already
uses, so the gate passes today and every new omission fails until the entry is written.

Exit codes: 0 when the block is current (or a draft printed), 1 when the gate finds an unrecorded
commit, 2 when the range, the changelog or the baseline cannot be read.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_DEFAULT = REPO_ROOT / "CHANGELOG.md"
BASELINE_DEFAULT = Path(__file__).resolve().parent / "changelog-baseline.json"

POLICY = "changelog-unreleased-ratchet"
VERSION = 1

# The section order Keep a Changelog fixes; `None` means the type is not release-note material.
SECTION_BY_TYPE = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "revert": "Removed",
    "docs": "Docs",
}
SECTION_ORDER = ("Added", "Changed", "Fixed", "Removed", "Security", "Docs")
# feat and fix are what a release reader looks for; the rest is noise a release manager filters.
GATE_TYPES_DEFAULT = ("feat", "fix")

SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?: (?P<desc>.+)$")
# The sha a CHANGELOG entry names. Eight hex characters is the house width; seven is git's floor.
SHA_TOKEN = re.compile(r"\b[0-9a-f]{7,40}\b")
UNRELEASED_HEADER = re.compile(r"^##\s*\[Unreleased\]")


class Commit(NamedTuple):
    sha: str
    short: str
    subject: str
    date: str
    type: str | None
    scope: str | None
    desc: str
    breaking: bool


def git(*args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(REPO_ROOT), *args),
        capture_output=True, text=True, check=True,
    ).stdout


def last_tag() -> str | None:
    """The most recent reachable tag, or None when a tree carries no tags yet.

    `git describe` exits non-zero with no reachable tag, so a fresh clone of a tagged tree and a
    tagless branch both land here; the None path lets `--range` fall back to the root commit.
    """
    done = subprocess.run(
        ("git", "-C", str(REPO_ROOT), "describe", "--tags", "--abbrev=0"),
        capture_output=True, text=True, check=False,
    )
    return done.stdout.strip() or None


def parse_subject(row: str) -> Commit:
    sha, short, subject, date = row.split("\t", 3)
    match = SUBJECT.match(subject)
    if not match:
        return Commit(sha, short, subject, date, None, None, subject, False)
    return Commit(
        sha, short, subject, date,
        match.group("type"), match.group("scope"), match.group("desc"),
        bool(match.group("breaking")),
    )


def commits_in_range(rev_range: str) -> list[Commit]:
    """Commits in `rev_range`, merges dropped, newest first the way git prints them."""
    raw = git("log", "--no-merges", "--date=short",
              "--format=%H%x09%h%x09%s%x09%ad", rev_range)
    return [parse_subject(line) for line in raw.splitlines() if line]


def section_of(commit: Commit, all_types: bool) -> str | None:
    """The CHANGELOG section a commit belongs to, or None when it is not release-note material."""
    if commit.type is None:
        return "Changed" if all_types else None
    if commit.scope and "security" in commit.scope.lower():
        return "Security"
    if commit.type in SECTION_BY_TYPE:
        return SECTION_BY_TYPE[commit.type]
    return "Changed" if all_types else None


def unreleased_block(text: str) -> tuple[int, int] | None:
    """Line indices `[start, end)` of the `[Unreleased]` block, header line included.

    The block runs from its header to the next version header, so a release that moves Unreleased
    down still yields one bounded region and the covered-sha scan never reaches released prose.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if UNRELEASED_HEADER.match(line)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def covered_shas(block: str) -> set[str]:
    """Every hex run of seven or more characters written in the block, lowercased."""
    return {token.lower() for token in SHA_TOKEN.findall(block)}


def is_covered(commit: Commit, tokens: set[str], accepted: set[str]) -> bool:
    """Whether a commit is named in the block, or grandfathered by the baseline.

    Both the block and the baseline may carry a shorter form than the commit's long sha, so a
    token counts when it is a prefix of that long sha; the block's entries are hand-written and the
    baseline's are twelve characters, and the stable long sha is what both compare against.
    """
    return any(commit.sha.startswith(token) for token in tokens | accepted)


def bullet_for(commit: Commit, capitalize: bool = True) -> str:
    desc = commit.desc
    if capitalize and desc and desc[0].islower():
        desc = desc[0].upper() + desc[1:]
    prefix = "**Breaking:** " if commit.breaking else ""
    head = f"{commit.scope}: " if commit.scope else ""
    return f"- {prefix}{head}{desc} (`{commit.short}`)"


def render_draft(commits: list[Commit], all_types: bool) -> str:
    """A paste-ready `[Unreleased]` body: the sections these commits fill, newest change last.

    Git prints newest first, so the lines are reversed per section to read in landing order.
    """
    grouped: dict[str, list[Commit]] = {}
    for commit in commits:
        section = section_of(commit, all_types)
        if section:
            grouped.setdefault(section, []).append(commit)
    parts: list[str] = []
    for section in SECTION_ORDER:
        rows = grouped.get(section)
        if not rows:
            continue
        parts.append(f"### {section}")
        parts.append("")
        parts.extend(bullet_for(c) for c in reversed(rows))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def insert_entries(block_text: str, additions: dict[str, list[Commit]]) -> str:
    """Splice new bullets under their sections, creating a `### Section` where none exists.

    The closing rule and any prose the block already carries are left where they are, so a
    re-run is idempotent for the commits already named (the caller filters those out first).
    """
    lines = block_text.splitlines()
    for section in SECTION_ORDER:
        rows = additions.get(section)
        if not rows:
            continue
        new_bullets = [bullet_for(c) for c in reversed(rows)]
        header = next((i for i, line in enumerate(lines) if line.startswith(f"### {section}")), None)
        if header is None:
            at = len(lines)
            while at > 0 and lines[at - 1].strip() in {"", "---"}:
                at -= 1
            lines[at:at] = ["", f"### {section}", "", *new_bullets]
            continue
        at = header + 1
        while at < len(lines) and not lines[at].startswith(("### ", "## ")):
            at += 1
        while at - 1 > header and lines[at - 1].strip() == "":
            at -= 1
        lines[at:at] = new_bullets
    return "\n".join(lines)


def load_baseline(path: Path, types: tuple[str, ...]) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("policy") != POLICY or data.get("version") != VERSION:
        raise ValueError(
            f"{path.name} is policy {data.get('policy')!r} version {data.get('version')!r}; "
            f"this instrument writes {POLICY!r} version {VERSION}"
        )
    recorded = tuple(data.get("types") or ())
    if recorded and recorded != types:
        raise ValueError(
            f"{path.name} was written for types {recorded}; this run gates {types}. Regenerate it "
            f"with --update-baseline when the gated type set changes."
        )
    return set(data.get("known_uncovered") or [])


def write_baseline(path: Path, types: tuple[str, ...], since: str, shas: list[str]) -> None:
    """Freeze the accepted-not-yet-chronicled set. Sorted, no timestamp, so it diffs cleanly."""
    payload = {
        "policy": POLICY,
        "version": VERSION,
        "instrument": "scripts/changelog_unreleased.py",
        "since": since,
        "types": list(types),
        "known_uncovered": sorted(shas),
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default=None,
                        help="range starts at this rev (default: the last reachable tag)")
    parser.add_argument("--range", dest="rev_range", default=None,
                        help="explicit A..B range, overriding --since")
    parser.add_argument("--types", default=",".join(GATE_TYPES_DEFAULT),
                        help=f"comma-separated types the gate requires (default: {','.join(GATE_TYPES_DEFAULT)})")
    parser.add_argument("--all-types", action="store_true",
                        help="treat every unmapped type as Changed in the draft")
    parser.add_argument("--changelog", type=Path, default=CHANGELOG_DEFAULT)
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--draft", action="store_true", help="print a paste-ready block (the default)")
    group.add_argument("--check", action="store_true", help="exit 1 when a gated commit is unrecorded")
    group.add_argument("--write", action="store_true", help="splice missing entries into the changelog")
    group.add_argument("--update-baseline", action="store_true",
                       help="record the current unrecorded set as accepted")
    parser.add_argument("--dry-run", action="store_true", help="with --write, print without editing")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    parser.add_argument("--quiet", action="store_true", help="suppress the human summary line")
    args = parser.parse_args(argv)

    types = tuple(t.strip() for t in args.types.split(",") if t.strip())
    if args.rev_range:
        rev_range, since = args.rev_range, args.rev_range
    else:
        since = args.since or last_tag()
        rev_range = f"{since}..HEAD" if since else "HEAD"

    try:
        text = args.changelog.read_text(encoding="utf-8")
        commits = commits_in_range(rev_range)
        accepted = load_baseline(args.baseline, types)
    except subprocess.CalledProcessError as exc:
        print(f"changelog-unreleased: cannot read {rev_range!r} ({exc.stderr.strip() or exc})",
              file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"changelog-unreleased: {exc}", file=sys.stderr)
        return 2

    region = unreleased_block(text)
    if region is None:
        block, start, end = "", 0, 0
    else:
        start, end = region
        block = "\n".join(text.splitlines()[start:end])
    tokens = covered_shas(block)

    worthy = [c for c in commits if c.type in types]
    missing = [c for c in worthy if not is_covered(c, tokens, accepted)]

    if args.update_baseline:
        write_baseline(args.baseline, types, since or "HEAD", [c.sha[:12] for c in missing])
        if not args.quiet:
            print(f"changelog-unreleased: baseline written — {len(missing)} accepted-unrecorded "
                  f"of {len(worthy)} {types} commit(s) in {rev_range} ({args.baseline.name})")
        return 0

    if args.check:
        if args.json:
            print(json.dumps({
                "range": rev_range, "types": list(types), "worthy": len(worthy),
                "missing": [{"sha": c.short, "subject": c.subject} for c in missing],
            }, indent=1))
        if missing:
            if not args.json:
                for commit in reversed(missing):
                    print(f"changelog-unreleased: unrecorded  {commit.short}  {commit.subject}")
            if not args.quiet:
                print(f"changelog-unreleased: FAIL — {len(missing)} of {len(worthy)} {types} "
                      f"commit(s) since {since} carry no sha in the [Unreleased] block",
                      file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"changelog-unreleased: pass — every {types} commit since {since} is named in "
                  f"the [Unreleased] block ({len(commits)} commit(s) read)")
        return 0

    if args.write:
        additions: dict[str, list[Commit]] = {}
        for commit in missing:
            section = section_of(commit, args.all_types)
            if section:
                additions.setdefault(section, []).append(commit)
        if not additions:
            if not args.quiet:
                print("changelog-unreleased: nothing to write — the block already names every "
                      "changelog-worthy commit")
            return 0
        if not region:
            print("changelog-unreleased: the changelog has no [Unreleased] block to splice into",
                  file=sys.stderr)
            return 2
        new_block = insert_entries(block, additions)
        lines = text.splitlines()
        merged = "\n".join([*lines[:start], *new_block.splitlines(), *lines[end:]])
        count = sum(len(rows) for rows in additions.values())
        if args.dry_run:
            print(merged)
            if not args.quiet:
                print(f"changelog-unreleased: dry-run — {count} entry/entries would be added",
                      file=sys.stderr)
            return 0
        args.changelog.write_text(merged + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
        if not args.quiet:
            try:
                shown = args.changelog.relative_to(REPO_ROOT)
            except ValueError:
                shown = args.changelog
            print(f"changelog-unreleased: wrote {count} entry/entries into {shown}")
        return 0

    draft = render_draft(commits, args.all_types)
    if args.json:
        print(json.dumps({"range": rev_range, "draft": draft}, indent=1))
    else:
        print(draft, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
