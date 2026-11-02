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

The body a person reads is the block with the commit addresses taken off its entries; pass
`--addresses` for the block exactly as the changelog wrote it.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
HEADER = re.compile(r"^##\s*\[(?P<ver>[^\]]+)\]")

# The register's addresses: the commit each entry was landed by, written at the end of the
# entry as (`1228a4c6`) or (`1228a4c6`, `dd51da76`) — which the formatter may carry onto the
# next line. They belong to the changelog, where a reader can look a line up and find the
# commit; in the update window they are eight hex digits standing where a sentence ended.
ADDRESS_TAIL = re.compile(
    r"\s*\(\s*`[0-9a-f]{7,40}`(?:\s*,\s*`[0-9a-f]{7,40}`)*\s*\)"
)


def strip_addresses(body: str) -> str:
    """The same words without the register's addresses at the end of each entry."""
    stripped = ADDRESS_TAIL.sub("", body)
    # A trailing address can leave a line ending in the wrap's two-space indent.
    return "\n".join(line.rstrip() for line in stripped.splitlines())



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
    parser.add_argument(
        "--addresses",
        action="store_true",
        help="keep the commit addresses each entry ends with (the register's own rendering)",
    )
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
    print(body if args.addresses else strip_addresses(body))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
