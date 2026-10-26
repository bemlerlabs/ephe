#!/usr/bin/env python3
"""Packaging freshness: every shipped manifest names the release that exists.

The Homebrew cask, the Scoop manifest and the npm wrapper are three hand-edited files that each
carry a version, and nothing in the tree compared any of them with the release it is meant to
install. Both manifests once shipped a dead tag -- the cask named `0.1.0-beta.1` and the Scoop
manifest `0.1.0-beta.2`, two URLs that answered 404 -- while the published release was
`0.1.0-beta.3`. The files parse, the version reads as a well-formed string, and the only thing
wrong with them is a claim about a release nobody served, which is why no existing gate saw it.
This check asks that one question and names the surface when the answer is no.

The reference is the latest published release, read from the GitHub release API -- the same
release `releases/latest/download/latest.json` serves to the updater. When that answer is
unavailable, or `--offline` is given, the reference falls back to the tree's own version
carriers (`pyproject.toml`, `app/package.json`, `app/src-tauri/tauri.conf.json`), which are the
number the next build ships. The fallback is printed, never silent, so a green run states which
reference it judged against and a reader can tell the two apart.

A pull request carries the release the tree is about to cut, so the feed would answer "not yet"
for every manifest of that release. On the feed path the check therefore also accepts the tree's
own stable version when it sits ahead of the published one; a third number still fails, and so
does any manifest naming a pre-release the feed does not serve, because the beta cadence keeps
the shipped manifests on the stable release while the carriers move. `--release` keeps the exact
rule for the publish event, where the manifests must name the tag that was published.

Exit codes follow the other gates in `scripts/`: 0 every manifest agrees with the reference, 1 a
manifest names a version the reference does not, 2 a manifest or the reference cannot be read.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The release endpoint whose tag is the published number. Unauthenticated gives 60 reads an
#: hour per address; a token in the environment raises that and is read, never required.
FEED = "https://api.github.com/repos/bemlerlabs/ephe/releases/latest"
TOKEN_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_TOKEN")
TAG_PREFIX = "v"

#: The three manifests, with the label the report prints and the reader used for each.
SURFACES = (
    ("cask", Path("packaging") / "homebrew" / "ephe.rb"),
    ("scoop", Path("packaging") / "scoop" / "ephe.json"),
    ("npm", Path("packaging") / "npm" / "package.json"),
)
#: The tree carriers of the shipped version, in the order the release checklist lists them. They
#: are the offline reference, and the same three files `scripts/release_checklist.py` keeps in sync.
CARRIERS = (
    ("pyproject.toml", "[project].version"),
    ("app/package.json", "version"),
    ("app/src-tauri/tauri.conf.json", "version"),
)

CASK_VERSION = re.compile(r'(?m)^\s*version\s+"([^"]+)"')


def pyproject_version(path: Path) -> str:
    """`[project].version`. tomllib is 3.11+, and the gates also run on 3.10, so read the line."""
    text = path.read_text(encoding="utf-8")
    section = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[[^\]]+\]|\Z)", text)
    body = section.group(1) if section else text
    match = re.search(r"(?m)^\s*version\s*=\s*[\"']([^\"']+)[\"']", body)
    if not match:
        raise ValueError(f"no [project].version line in {path.name}")
    return match.group(1)


def manifest_versions(root: Path) -> dict[str, str]:
    """The version each manifest names, keyed by the label the report prints."""
    found: dict[str, str] = {}
    for label, rel in SURFACES:
        text = (root / rel).read_text(encoding="utf-8")
        if rel.suffix == ".rb":
            match = CASK_VERSION.search(text)
            if not match:
                raise ValueError(f"{rel} carries no version line")
            found[label] = match.group(1)
        else:
            found[label] = str(json.loads(text)["version"])
    return found


def carrier_version(root: Path) -> str:
    """The one version the tree carriers agree on; a mismatch is a reference the check declines."""
    versions: dict[str, str] = {}
    for rel, _label in CARRIERS:
        path = root / rel
        versions[rel] = (
            str(json.loads(path.read_text(encoding="utf-8"))["version"])
            if rel.endswith(".json")
            else pyproject_version(path)
        )
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        raise ValueError("the carriers disagree: " + ", ".join(f"{rel}={ver}" for rel, ver in versions.items()))
    return distinct[0]


def feed_release(timeout: float = 10.0) -> str:
    """The tag of the latest published release, with a leading `v` stripped; raises when unavailable.

    Every failure mode is one shape: a status error, a DNS or TLS failure, a body that is not JSON,
    or a payload without a tag all mean the feed answered nothing usable, and the caller falls back.
    """
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = next((os.environ[name] for name in TOKEN_ENV if os.environ.get(name)), "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(FEED, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise ValueError("the release feed answered without a tag_name")
    return tag[len(TAG_PREFIX):] if tag.startswith(TAG_PREFIX) else tag


def stable_candidate(root: Path, published: str) -> str | None:
    """The stable release this tree is cutting, when it sits ahead of the published one.

    A pre-release carrier does not qualify: during the beta cadence the carriers move to
    0.2.0-alpha.N while the shipped manifests stay on the stable release.
    """
    try:
        candidate = carrier_version(root)
    except (OSError, ValueError, KeyError):
        return None
    if "-" in candidate or candidate == published:
        return None
    return candidate


def resolve_reference(
    root: Path, release: str | None, offline: bool, published: str | None
) -> tuple[str, str]:
    """(version, source) the manifests are judged against, the published release when reachable."""
    if release:
        return release, "--release"
    if published:
        return published, "--published"
    if offline:
        return carrier_version(root), "the tree carriers (--offline)"
    try:
        return feed_release(), "the GitHub release feed"
    except (OSError, ValueError) as exc:
        try:
            reference = carrier_version(root)
        except (OSError, ValueError, KeyError) as inner:
            raise ValueError(
                f"the release feed is unreachable ({exc}) and the tree carriers cannot decide "
                f"a reference ({inner})"
            ) from inner
        return reference, f"the tree carriers (the release feed was unreachable: {exc})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="checkout to judge")
    parser.add_argument("--release", help="judge against this version instead of the feed")
    parser.add_argument("--published", help="judge as if the feed served this version, no network")
    parser.add_argument("--offline", action="store_true", help="judge against the tree carriers, no network")
    args = parser.parse_args(argv)

    try:
        versions = manifest_versions(args.root)
        reference, source = resolve_reference(args.root, args.release, args.offline, args.published)
    except (OSError, ValueError, KeyError) as exc:
        print(f"packaging-freshness: cannot decide the reference or a manifest: {exc}")
        return 2

    candidate = None
    if args.release is None and not args.offline:
        candidate = stable_candidate(args.root, reference)
    accepted = {reference} | ({candidate} if candidate else set())
    expected = f"release {reference}" + (f" or the candidate {candidate}" if candidate else "")

    print(f"packaging-freshness: reference release {reference} ({source})")
    if candidate:
        print(f"packaging-freshness: candidate release {candidate} (the stable version this tree carries)")
    stale = []
    for label, version in versions.items():
        agrees = version in accepted
        if not agrees:
            stale.append(f"{label} {version} vs {expected}")
        print(f"packaging-freshness: {'ok   ' if agrees else 'STALE'} {label} {version} vs {expected}")

    if stale:
        print(
            f"packaging-freshness: FAIL — {len(stale)} manifest(s) name a version neither the feed "
            "nor the tree's candidate names; point them at the published tag with its measured "
            "hash, or cut the release they name: " + "; ".join(stale)
        )
        return 1
    print(f"packaging-freshness: PASS — {len(versions)} manifest(s) name {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
