#!/usr/bin/env python3
"""Render the tap and bucket manifests from the in-tree templates at release time.

The cask and the Scoop manifest each name a version and a hash measured from a published
artifact, and the two hand-edits that keep them pointed at the current release are exactly the
edits a release skips -- which is how both shipped a tag that answered 404. This script takes the
version and the two hashes the release workflow measured and writes the files the distribution
repositories receive, so the tap copy can only ever name a release that was just published. The
templates are the in-tree `packaging/homebrew/ephe.rb` and `packaging/scoop/ephe.json`; only the
values change, so the rendered file and the checked-in one cannot drift in shape.

Exit codes: 0 both files were written, 1 an input is not a 64-character sha256, 2 a template or
the output directory cannot be read or written.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CASK_TEMPLATE = Path("packaging") / "homebrew" / "ephe.rb"
SCOOP_TEMPLATE = Path("packaging") / "scoop" / "ephe.json"

SHA256 = re.compile(r"^[0-9a-f]{64}$")
CASK_VERSION = re.compile(r'(?m)^\s*version\s+"([^"]+)"')
CASK_SHA = re.compile(r'(?m)^(\s*sha256\s+)"[^"]*"')
SCOOP_HASH = re.compile(r'("hash"\s*:\s*)"[^"]*"')


def render_cask(template: str, version: str, dmg_sha256: str) -> str:
    """The cask with its version token and its sha256 field set to the release's values."""
    match = CASK_VERSION.search(template)
    if not match:
        raise ValueError(f"{CASK_TEMPLATE} carries no version line")
    text = template.replace(match.group(1), version)
    text = CASK_SHA.sub(rf'\g<1>"{dmg_sha256}"', text, count=1)
    if version not in text:
        raise ValueError("the rendered cask does not carry the requested version")
    return text


def render_scoop(template: str, version: str, source_sha256: str) -> str:
    """The Scoop manifest with its version token and its hash field set to the release's values.

    The version appears in four places (the `version` field, the `notes` prose, the archive url
    and `extract_dir`), so the old token is replaced wherever it occurs; the hash has one home.
    """
    old = str(json.loads(template)["version"])
    text = template.replace(old, version)
    text = SCOOP_HASH.sub(rf'\g<1>"{source_sha256}"', text, count=1)
    if version not in text:
        raise ValueError("the rendered scoop manifest does not carry the requested version")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the published release version, no leading v")
    parser.add_argument("--dmg-sha256", required=True, help="sha256 of the released aarch64 DMG")
    parser.add_argument("--source-sha256", required=True, help="sha256 of the released source archive")
    parser.add_argument("--outdir", type=Path, required=True, help="directory the two files are written to")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="checkout holding the templates")
    args = parser.parse_args(argv)

    for flag, value in (("--dmg-sha256", args.dmg_sha256), ("--source-sha256", args.source_sha256)):
        if not SHA256.match(value):
            print(f"render-packaging: {flag} {value!r} is not a lowercase 64-character sha256")
            return 1

    try:
        cask = render_cask(
            (args.root / CASK_TEMPLATE).read_text(encoding="utf-8"), args.version, args.dmg_sha256
        )
        scoop = render_scoop(
            (args.root / SCOOP_TEMPLATE).read_text(encoding="utf-8"), args.version, args.source_sha256
        )
        args.outdir.mkdir(parents=True, exist_ok=True)
        (args.outdir / "ephe.rb").write_text(cask, encoding="utf-8")
        (args.outdir / "ephe.json").write_text(scoop, encoding="utf-8")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"render-packaging: cannot render: {exc}")
        return 2

    print(f"render-packaging: wrote ephe.rb and ephe.json at {args.version} into {args.outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
