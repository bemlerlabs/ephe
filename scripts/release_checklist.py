#!/usr/bin/env python3
"""The release checklist as code: run it before a tag and it refuses a release that is incomplete.

`docs/RELEASE_CHECKLIST.md` and `docs/RELEASE_RUNBOOK.md` describe a release by hand. This is the
same list, runnable, so the one step a busy release skips is the one that blocks it. It reads files
and git state, and the pass^3 check runs a reader over the committed cohort's manifests. It never
writes, never tags, never runs the test suite, so it is safe to run at any moment and cheap enough
to run on every attempt.

What it refuses (a FAIL, exit 1):
  version-agreement   the three version carriers disagree (pyproject.toml, app/package.json,
                      app/src-tauri/tauri.conf.json). The runbook keeps them in sync by hand until
                      P4-16 collapses them; this is the check that the hand did not slip.
  version-shape       the version is not a concrete X.Y.Z (the `0.0.0+unknown` sentinel), so the
                      release would ship with no number.
  changelog-section   CHANGELOG.md carries no non-empty `## [X.Y.Z]` section. `latest.json` cuts its
                      notes from the top changelog block, so an empty block ships a blank release.
  unreleased-current  `scripts/changelog_unreleased.py --check` fails: a changelog-worthy commit
                      since the last tag is named nowhere.
  pass3-gate          `evals/pass3_release_gate.py` does not return release-ok over the cohort given
                      by `$EPHE_RELEASE_RUNS` (default `evals/runs`). The gate's exit codes are
                      reported with the gate's words: 0 release-ok, 1 blocked-flaky (a task flipped
                      between reps), 2 untrusted (the instrument declined to certify). A deliberate
                      mismatch is carried by naming a reason in `$EPHE_RELEASE_ENGINE_MISMATCH_REASON`,
                      which goes to the gate as `--allow-engine-mismatch` and is recorded in this
                      line. This is the engine arm the release workflow cannot run, so it runs here.
  tree-committed      a version carrier or CHANGELOG.md is modified against HEAD. The tree you tag
                      is the tree that ships; an uncommitted bump is not that tree.
  tag-free            the tag `vX.Y.Z` already exists, locally or (with `--remote`) on origin.

What it warns about without blocking:
  feed-wired          the updater pubkey or the endpoint list is empty, so a signed build would post
                      a feed no client reads.
  signing-key         `~/.tauri/ephe.key` is absent, so the local signed build path cannot run.
  branch              HEAD is not `main`.

Exit codes follow the other gates in `scripts/`: 0 the tree is ready to tag, 1 the checklist is
incomplete, 2 an input could not be read. A silent pass is worse than the defect it watches. These
are this script's own codes; the pass3-gate item reports the gate's codes with the gate's words
(0 release-ok / 1 blocked-flaky / 2 untrusted), so an instrument refusal never reads as a red tree.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SENTINEL = "0.0.0+unknown"
SEMVER = re.compile(r"^\d+\.\d+\.\d+")

# The release cohort the pass^3 gate reads, unless the environment names the measured one.
PASS3_GATE = "evals/pass3_release_gate.py"
RELEASE_RUNS_ENV = "EPHE_RELEASE_RUNS"
DEFAULT_RUNS = "evals/runs"
# The reason a deliberate engine mismatch is carried on purpose. It goes to the gate as
# --allow-engine-mismatch and is recorded in the checklist's line; with no reason a cohort
# measured on another engine stays a refusal, so there is no silent bypass.
RELEASE_ENGINE_MISMATCH_ENV = "EPHE_RELEASE_ENGINE_MISMATCH_REASON"
# The gate's exit codes and their words (evals/pass3_release_gate.py). A reader must not
# mistake an instrument refusal (2 untrusted) for a red product (1 blocked-flaky).
GATE_DECISION = {0: "release-ok", 1: "blocked-flaky", 2: "untrusted"}

# path -> reader label, kept in the order the runbook lists them.
CARRIERS = (
    ("pyproject.toml", "[project].version"),
    ("app/package.json", "version"),
    ("app/src-tauri/tauri.conf.json", "version"),
)
CHANGELOG = "CHANGELOG.md"
TAURI_CONF = "app/src-tauri/tauri.conf.json"
UNRELEASED = "scripts/changelog_unreleased.py"

CH_HEADER = re.compile(r"^##\s*\[(?P<ver>[^\]]+)\]")


class Item:
    """One checklist line: a name, a PASS/FAIL/WARN/SKIP status, and the detail behind it."""

    def __init__(self, name: str, status: str, detail: str) -> None:
        self.name = name
        self.status = status
        self.detail = detail

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pyproject_version(path: Path) -> str:
    """`[project].version`. tomllib is 3.11+, and the gates also run on 3.10, so read the line."""
    text = path.read_text(encoding="utf-8")
    section = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[[^\]]+\]|\Z)", text)
    body = section.group(1) if section else text
    match = re.search(r"(?m)^\s*version\s*=\s*[\"']([^\"']+)[\"']", body)
    if not match:
        raise ValueError("no [project].version line")
    return match.group(1)


def carrier_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for rel, _label in CARRIERS:
        path = root / rel
        if rel.endswith(".json"):
            versions[rel] = str(read_json(path)["version"])
        else:
            versions[rel] = pyproject_version(path)
    return versions


def changelog_sections(text: str) -> list[tuple[str, list[str]]]:
    """(version, body-lines) for every `## [version]` heading, in file order."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if CH_HEADER.match(line)]
    sections: list[tuple[str, list[str]]] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        header = CH_HEADER.match(lines[start])
        if header is None:  # unreachable: `starts` only holds lines the same pattern matched
            continue
        sections.append((header.group("ver").strip(), lines[start + 1 : end]))
    return sections


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True
    )


def check_version_agreement(versions: dict[str, str], release: str) -> Item:
    distinct = sorted(set(versions.values()))
    if len(distinct) == 1 and distinct[0] == release:
        return Item("version-agreement", "PASS", f"all carriers carry {release}")
    if len(distinct) == 1:
        return Item(
            "version-agreement",
            "FAIL",
            f"carriers carry {distinct[0]} but the release is {release}",
        )
    pairs = ", ".join(f"{rel}={ver}" for rel, ver in versions.items())
    return Item("version-agreement", "FAIL", f"carriers disagree: {pairs}")


def check_version_shape(release: str) -> Item:
    if release == SENTINEL or not SEMVER.match(release):
        return Item("version-shape", "FAIL", f"{release!r} is not a concrete X.Y.Z number")
    return Item("version-shape", "PASS", release)


def check_changelog(root: Path, release: str) -> Item:
    path = root / CHANGELOG
    if not path.is_file():
        return Item("changelog-section", "FAIL", f"{CHANGELOG} is missing")
    sections = changelog_sections(path.read_text(encoding="utf-8"))
    section = next((body for ver, body in sections if ver == release), None)
    if section is None:
        return Item("changelog-section", "FAIL", f"no `## [{release}]` section in {CHANGELOG}")
    if not any(line.strip() for line in section):
        return Item("changelog-section", "FAIL", f"`## [{release}]` is empty")
    note = ""
    if sections:
        top_ver, top_body = sections[0]
        if top_ver == release and not any(line.strip() for line in top_body):
            note = " (top block empty, but the section above is not)"
    return Item("changelog-section", "PASS", f"`## [{release}]` present and non-empty{note}")


def check_unreleased_current(root: Path) -> Item:
    script = root / UNRELEASED
    if not script.is_file():
        return Item("unreleased-current", "SKIP", f"{UNRELEASED} not present")
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return Item("unreleased-current", "PASS", "the Unreleased block names every commit")
    if proc.returncode == 1:
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        return Item(
            "unreleased-current",
            "FAIL",
            tail[-1] if tail else "an unrecorded commit exists",
        )
    return Item("unreleased-current", "SKIP", "the gate could not read its range or baseline")


def _read_receipt(path: Path) -> dict:
    """The gate's JSON receipt, or `{}` when it was not written or cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _gate_summary(proc: subprocess.CompletedProcess) -> str:
    """The gate's own summary line, past its receipt note, or its last stderr line when stdout
    is empty (the `--receipt` note this caller asks for is not the verdict)."""
    lines = [ln for ln in (proc.stdout or "").strip().splitlines() if "receipt ->" not in ln]
    if lines:
        return lines[-1]
    return (proc.stderr or "").strip() or "no output"


def check_pass3_gate(
    root: Path,
    *,
    runs: str | None = None,
    engine: str | None = None,
    mismatch_reason: str | None = None,
) -> Item:
    """The pass^3 release bar, over the release cohort, with the gate's own words.

    Exit codes are reported with the gate's words: 0 release-ok, 1 blocked-flaky (a product
    result: a task flipped between reps), 2 untrusted (the instrument declined to certify, and
    the detail names which). A deliberate mismatch is named by `$EPHE_RELEASE_ENGINE_MISMATCH_REASON`
    and recorded here; with no reason it stays a refusal, and no reason waives a cohort that
    names two engines — the gate decides, this line records.
    """
    gate = root / PASS3_GATE
    if not gate.is_file():
        return Item("pass3-gate", "SKIP", f"{PASS3_GATE} not present")
    runs = runs or os.environ.get(RELEASE_RUNS_ENV) or DEFAULT_RUNS
    reason = mismatch_reason if mismatch_reason is not None else os.environ.get(RELEASE_ENGINE_MISMATCH_ENV)

    with tempfile.TemporaryDirectory(prefix="pass3-gate-") as tmp:
        receipt_path = Path(tmp) / "receipt.json"
        cmd = [sys.executable, str(gate), "--runs", runs, "--receipt", str(receipt_path)]
        if engine:
            cmd += ["--engine", engine]
        if reason:
            cmd += ["--allow-engine-mismatch", reason]
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
        receipt = _read_receipt(receipt_path)

    code = proc.returncode
    # The word comes from the gate's receipt when it is there, so this line cannot drift from the
    # gate's vocabulary; the constant is the fallback when no receipt was written.
    word = str(receipt.get("decision") or GATE_DECISION.get(code, "untrusted"))
    summary = _gate_summary(proc)
    cohort = (receipt.get("engine") or {}).get("cohort") or {}
    waiver = cohort.get("waived")
    # Only a reason the gate actually took is recorded as carried; an unhonoured reason is not
    # restated as if it had landed.
    carried = f"; carried a deliberate engine mismatch: {reason}" if reason and waiver == reason else ""

    if code == 0:
        return Item("pass3-gate", "PASS", f"{word} (exit 0): {summary}{carried}")
    if code == 1:
        return Item("pass3-gate", "FAIL", f"{word} (exit 1): a task flipped between reps: {summary}{carried}")
    refusal = str(cohort.get("refusal") or "")
    if refusal:
        # The gate's own refusal sentence, verbatim: the cohort's engine is not this machine's, or
        # the cohort names two engines. This is an instrument refusal.
        return Item("pass3-gate", "FAIL", f"{word} (exit 2): the gate refused the engine: {refusal}{carried}")
    return Item(
        "pass3-gate",
        "FAIL",
        f"{word} (exit 2): the gate cannot certify {runs}: {summary}{carried}",
    )


def check_tree_committed(root: Path) -> Item:
    proc = git(root, "status", "--porcelain", "--untracked-files=no")
    if proc.returncode != 0:
        return Item("tree-committed", "SKIP", "git status unavailable")
    dirty = []
    for line in proc.stdout.splitlines():
        path = line[3:].strip()
        if "->" in path:
            path = path.split("->")[-1].strip()
        dirty.append(path)
    carriers = {rel for rel, _ in CARRIERS} | {CHANGELOG}
    blocked = sorted(p for p in dirty if p in carriers)
    if blocked:
        return Item("tree-committed", "FAIL", f"modified against HEAD: {', '.join(blocked)}")
    if dirty:
        return Item(
            "tree-committed",
            "WARN",
            f"carriers are committed; {len(dirty)} other tracked file(s) modified",
        )
    return Item("tree-committed", "PASS", "no tracked modifications")


def check_tag_free(root: Path, release: str, remote: bool) -> Item:
    tag = f"v{release}"
    local = git(root, "tag", "--list", tag)
    if local.returncode == 0 and local.stdout.strip():
        return Item("tag-free", "FAIL", f"{tag} already exists locally")
    if remote:
        proc = git(root, "ls-remote", "--tags", "origin", tag)
        if proc.returncode != 0:
            return Item("tag-free", "SKIP", "origin unreachable, remote tag not checked")
        if proc.stdout.strip():
            return Item("tag-free", "FAIL", f"{tag} already exists on origin")
    return Item("tag-free", "PASS", f"{tag} is free")


def check_feed_wired(root: Path) -> Item:
    try:
        conf = read_json(root / TAURI_CONF)
    except (OSError, ValueError, KeyError) as exc:
        return Item("feed-wired", "SKIP", f"cannot read {TAURI_CONF}: {type(exc).__name__}")
    updater = conf.get("plugins", {}).get("updater", {})
    pubkey = updater.get("pubkey")
    endpoints = updater.get("endpoints") or []
    if not pubkey or not endpoints:
        return Item("feed-wired", "WARN", "updater pubkey or endpoints empty; the feed would be dead")
    return Item("feed-wired", "PASS", f"{len(endpoints)} endpoint(s), pubkey set")


def check_signing_key() -> Item:
    key = os.environ.get("EPHE_UPDATER_KEY") or str(Path.home() / ".tauri" / "ephe.key")
    if Path(key).is_file():
        return Item("signing-key", "PASS", "signing key present")
    return Item("signing-key", "WARN", f"{key} missing; the local signed build cannot run")


def check_branch(root: Path) -> Item:
    proc = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = proc.stdout.strip() if proc.returncode == 0 else ""
    if branch == "main":
        return Item("branch", "PASS", "on main")
    return Item("branch", "WARN", f"HEAD is {branch or 'unknown'}, not main")


def run(root: Path, release: str | None, remote: bool) -> tuple[int, list[Item]]:
    if release is None:
        release = pyproject_version(root / "pyproject.toml")
    versions = carrier_versions(root)
    items = [
        check_version_agreement(versions, release),
        check_version_shape(release),
        check_changelog(root, release),
        check_unreleased_current(root),
        check_pass3_gate(root),
        check_tree_committed(root),
        check_tag_free(root, release, remote),
        check_feed_wired(root),
        check_signing_key(),
        check_branch(root),
    ]
    return (1 if any(i.status == "FAIL" for i in items) else 0), items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=REPO, help="repository root")
    ap.add_argument("--version", help="the version to release; default: pyproject.toml")
    ap.add_argument("--remote", action="store_true", help="also check the tag on origin")
    ap.add_argument("--json", action="store_true", help="print a machine-readable verdict")
    args = ap.parse_args(argv)

    try:
        code, items = run(args.root, args.version, args.remote)
    except (OSError, ValueError, KeyError) as exc:
        print(f"release-check: cannot read an input: {type(exc).__name__}: {exc}")
        return 2

    if args.json:
        payload = {
            "version": args.version or pyproject_version(args.root / "pyproject.toml"),
            "verdict": "ready" if code == 0 else "incomplete",
            "items": [i.as_dict() for i in items],
        }
        print(json.dumps(payload, indent=2))
        return code

    for item in items:
        print(f"release-check: {item.status:<4} {item.name:<19} {item.detail}")
    failures = [i for i in items if i.status == "FAIL"]
    if failures:
        print(
            f"release-check: incomplete release — {len(failures)} checklist item(s) fail. "
            "Fix them, then tag."
        )
        return 1
    warns = [i for i in items if i.status == "WARN"]
    print(f"release-check: ready to tag. {len(warns)} warning(s) above." if warns else
          "release-check: ready to tag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
