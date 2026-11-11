#!/usr/bin/env python3
"""Refuse a release tag that does not name the version the tagged tree carries.

`release.yml` takes the release name and the notes version from `GITHUB_REF_NAME` and the
bundle version from `app/src-tauri/tauri.conf.json`. A tag pushed by hand, or moved onto a
different commit, therefore publishes bundles of one version under the name of another,
and the package job then looks for an asset that was never built. `scripts/release_cut.sh`
refuses that locally; a direct `git push origin vX.Y.Z` never reaches the cut. This guard
runs as the first release job, before any bundle is built, so the tag has to agree with
all six carriers before the build starts.

  scripts/version_guard.py --tag v0.7.0

Exit codes: 0 the tag names the tree's version, 1 the tag and the carriers disagree, 2 the
tag or a carrier cannot be read.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import version_carriers  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="the pushed tag, vX.Y.Z")
    parser.add_argument("--root", type=Path, default=version_carriers.REPO, help="checkout to judge")
    args = parser.parse_args(argv)

    try:
        version = version_carriers.tag_version(args.tag)
        declared, _versions, problems = version_carriers.check(args.root, version)
    except (OSError, ValueError, KeyError) as exc:
        print(f"version-guard: cannot read the tag or a carrier: {exc}")
        return 2

    if problems:
        for problem in problems:
            print(f"version-guard: FAIL {problem}")
        print(
            f"version-guard: FAIL tag {args.tag} does not name the version this tree carries "
            f"({declared}); no bundle is built for it"
        )
        return 1
    print(f"version-guard: PASS tag {args.tag} matches all six carriers at {declared}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
