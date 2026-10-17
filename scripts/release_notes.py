#!/usr/bin/env python3
"""Print one version's release body, cut from CHANGELOG.md.

The updater feed `latest.json` carries a `notes` field the desktop update window renders, and
`latest.json` is assembled by `tauri-action` from the `releaseBody` input the release workflow
hands it. That input was never set, so the feed shipped `"notes": ""` and the window could only
say the release carried no notes. This prints the `## [version]` block that
`scripts/release_checklist.py` already requires to be present and non-empty, so the release body
and the feed notes are the changelog the tree wrote rather than a blank.

Exit codes: 0 the block was printed, 2 the version has no block, the block is empty, or the
changelog cannot be read.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
HEADER = re.compile(r"^##\s*\[(?P<ver>[^\]]+)\]")


def section_body(text: str, version: str) -> str | None:
    """The lines under `## [version]`, up to the next `## ` header, trimmed of blank edges."""
    lines = text.splitlines()
    target = None
    for index, line in enumerate(lines):
        match = HEADER.match(line)
        if match and match.group("ver").strip() == version:
            target = index
            break
    if target is None:
        return None
    end = next((i for i in range(target + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = lines[target + 1 : end]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="the version whose changelog block is printed, no leading v")
    parser.add_argument("--changelog", type=Path, default=CHANGELOG, help="the changelog to read")
    args = parser.parse_args(argv)

    try:
        text = args.changelog.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"release-notes: cannot read {args.changelog}: {exc}", file=sys.stderr)
        return 2

    body = section_body(text, args.version)
    if body is None:
        print(f"release-notes: {args.changelog.name} has no `## [{args.version}]` section", file=sys.stderr)
        return 2
    if not body.strip():
        print(f"release-notes: the `## [{args.version}]` section is empty", file=sys.stderr)
        return 2
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
