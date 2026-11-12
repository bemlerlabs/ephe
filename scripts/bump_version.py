#!/usr/bin/env python3
"""Post-release bump: move every version carrier to the next milestone number.

The policy says `main` carries the version the last release commit brought, and the next
milestone opens with one commit that moves all six carriers. A hand edit that misses one
of them is exactly the drift the release checklist refuses, and a miss in either lockfile
only surfaces in the tag CI after the tag is public. This script writes all six through
`scripts/version_carriers.py` and re-reads them before it reports success, so the bump
either lands whole or names the file it could not write.

  scripts/bump_version.py --version 0.7.0     the next milestone
  scripts/bump_version.py --next-minor        the declared major.minor + 1
  scripts/bump_version.py --version 0.7.0 --dry-run

It never tags, commits or pushes; the version commit is the release runbook's step.
Exit codes: 0 all six carry the new number, 1 an input or a write failed, 2 usage.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import version_carriers  # noqa: E402


def next_minor(version: str) -> str:
    """The next milestone above `version`: its major.minor plus one, patch zero."""
    stable = version.split("-", 1)[0]
    parts = stable.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"{version!r} does not carry X.Y.Z")
    return f"{int(parts[0])}.{int(parts[1]) + 1}.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=version_carriers.REPO, help="checkout to write")
    parser.add_argument("--version", help="the next milestone version, X.Y.Z with an optional suffix")
    parser.add_argument("--next-minor", action="store_true", help="derive the next major.minor from the tree")
    parser.add_argument("--dry-run", action="store_true", help="print the target and write nothing")
    args = parser.parse_args(argv)

    if bool(args.version) == bool(args.next_minor):
        print("bump-version: pass exactly one of --version or --next-minor")
        return 2

    try:
        if args.next_minor:
            target = next_minor(version_carriers.declared_version(args.root))
        else:
            target = str(args.version)
            if not version_carriers.SEMVER.fullmatch(target):
                print(f"bump-version: {target!r} is not X.Y.Z (an optional -suffix is allowed)")
                return 2
        current = version_carriers.declared_version(args.root)
        if args.dry_run:
            print(f"bump-version: would move six carriers from {current} to {target}")
            return 0
        versions = version_carriers.set_versions(args.root, target)
    except (OSError, ValueError, KeyError) as exc:
        print(f"bump-version: cannot bump: {exc}")
        return 1

    print(f"bump-version: moved {len(versions)} carriers from {current} to {target}")
    for rel in version_carriers.CARRIERS:
        print(f"  {rel}: {versions[rel]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
