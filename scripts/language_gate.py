#!/usr/bin/env python3
"""Language gate: the measuring instrument, wired to a committed baseline.

Owner rule 2026-10-08: every artifact in this repository is written in English,
and German stays where it is a product feature. `scripts/language_inventory.py`
measures that; this script makes it hold. It compares the current tree against
`scripts/language-baseline.json` and fails when German developer prose has
grown, so the next feature cannot bring a German comment along unnoticed.

The ratchet is per file, not just in total. A total can fall while a single file
gets worse — one worker translates a module, another writes a German sentence in
a new one — and only the per-file comparison names the file that regressed.

There is no exemption list. `language_inventory.PROTECTED_PREFIXES` is the only
thing that keeps German out of the number, it is owned by the instrument, and it
is checked on every run (`checked_protected_prefixes`). Anything else that looks
like an exemption — an `exempt` key in the baseline, a protected path recorded in
the baseline, a protected prefix reaching into developer code — is an error,
because each of those would silently make the number lie. For the same reason
`--update` only ever lowers the baseline: a failing tree cannot be made to pass
by re-measuring it.

Exit codes: 0 the tree is not worse than the baseline, 1 German prose grew (the
files are named), 2 the gate cannot be trusted (missing or malformed baseline, a
protected path where one must never appear).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from typing import TypedDict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import language_inventory as inventory  # noqa: E402  (path bootstrap above)

REPO_ROOT = SCRIPTS_DIR.parent
BASELINE_DEFAULT = SCRIPTS_DIR / "language-baseline.json"
POLICY = "language-ratchet"
VERSION = 1
#: The only keys a baseline may carry. An unknown key is refused rather than
#: ignored: the shape of a whitelist is exactly what must not be added here.
BASELINE_KEYS = {"policy", "version", "instrument", "total", "files"}

#: Paths that are developer prose by definition. A protected prefix covering one
#: of these would take real code out of the measurement.
GUARDED_ROOTS = (
    "app/src/", "core/", "server/", "scripts/", "tests/", "docs/", "evals/", "build/",
)

UPDATE_HINT = f"python3 {BASELINE_DEFAULT.parent.name}/{Path(__file__).name} --update"


class GateError(Exception):
    """An untrustworthy gate exits 2; a refusal that means something exits 1."""


def checked_protected_prefixes() -> tuple[str, ...]:
    """The instrument's protected prefixes, after proving they stay product-only."""
    prefixes = tuple(inventory.PROTECTED_PREFIXES)
    for prefix in prefixes:
        if not prefix or prefix == "/":
            raise GateError(
                f"a protected prefix is empty ({prefix!r}); that would exclude the whole "
                "repository from the measurement"
            )
        swallowed = [root for root in GUARDED_ROOTS if root.startswith(prefix)]
        if swallowed:
            raise GateError(
                f"protected prefix {prefix!r} covers developer code ({', '.join(swallowed)}). "
                "Protected paths are for German that is the product — the app locale, the "
                "German skill packs, the survival guides, generated output. Narrow the "
                "prefix to the product directory instead of silencing the gate."
            )
    return prefixes


def tracked_files(root: Path) -> Callable[[], list[str]]:
    """The paths a whole-tree measurement judges: what git tracks in this checkout."""

    def list_files() -> list[str]:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True, text=True, check=True,
        )
        return done.stdout.splitlines()

    return list_files


def measure(
    root: Path,
    *,
    list_files: Callable[[], list[str]] | None = None,
    read_text: Callable[[str], str] | None = None,
) -> dict[str, int]:
    """German marker lines per tracked path. Injectable so a fixture tree scores too."""
    if list_files is None:
        list_files = tracked_files(root)
    if read_text is None:
        def read_text(rel: str) -> str:
            return (root / rel).read_text(encoding="utf-8")
    return inventory.counts_for(list_files(), read_text)


def refuse_orphan_entries(baseline: dict[str, int], tracked: list[str]) -> None:
    """A baseline entry has to name a path the tree holds.

    `evaluate` compares the union of both key sets, so an entry for a deleted file scores as
    `old = N, new = 0` and lands in `lowered` — invisible. Left alone it becomes an allowance: the
    path can come back with N German lines and the per-file ratchet calls that clean, because the
    number it is compared against was earned by a file nobody measured since. Refusing the whole
    pass (exit 2, the same verdict as an unreadable baseline) forces the entry to be pruned with
    `--update` while the tree is genuinely cleaner, which is the only direction that lowers it.

    Whole-tree mode only. In `--staged` the scope is the few paths one commit carries, so a
    baseline entry outside that scope is expected and stays unjudged.
    """
    present = set(tracked)
    orphans = sorted(rel for rel in baseline if rel not in present)
    if orphans:
        raise GateError(
            f"baseline names {len(orphans)} path(s) the tree does not hold: "
            + ", ".join(orphans[:5])
            + (", …" if len(orphans) > 5 else "")
            + " — prune them with the whole-tree --update; an entry for a deleted file is an "
            "allowance for whoever recreates it"
        )


def staged_readers(root: Path) -> tuple[Callable[[], list[str]], Callable[[str], str]]:
    """Scope the measurement to the content a commit carries.

    `.husky/pre-commit` promises that no check in it scans a whole tree, and this gate was the one
    that still did: on a shared working tree it refused an unrelated commit over a line another
    worker had not finished yet. `EPHE_COMMIT_PATHS` narrows the index the same way `ci_local.sh`
    reads it, because the hook cannot see the pathspec `git commit -- <paths>` will use.
    """

    def list_files() -> list[str]:
        done = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            capture_output=True, text=True, check=True,
        )
        paths = [line for line in done.stdout.split("\0") if line]
        wanted = os.environ.get("EPHE_COMMIT_PATHS", "").split()
        return [path for path in paths if path in wanted] if wanted else paths

    def read_text(rel: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(root), "show", f":{rel}"],
            capture_output=True, text=True,
        )
        return done.stdout if done.returncode == 0 else ""

    return list_files, read_text


def load_baseline(path: Path, protected: tuple[str, ...]) -> dict[str, int]:
    """Read the German-line baseline; a shape that could hide growth is refused outright."""
    if not path.exists():
        raise GateError(
            f"no baseline at {path.name} (looked in {path.parent}); create it with {UPDATE_HINT}"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"baseline {path} cannot be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise GateError(f"baseline {path} must be a JSON object")
    unknown = sorted(set(raw) - BASELINE_KEYS)
    if unknown:
        raise GateError(
            f"baseline {path} carries unknown key(s) {', '.join(unknown)}. This gate has no "
            "exemption list — remove the key, or lower the baseline with --update."
        )
    if raw.get("policy") != POLICY or raw.get("version") != VERSION:
        raise GateError(
            f"baseline {path} is policy {raw.get('policy')!r} version {raw.get('version')!r}; "
            f"this gate speaks {POLICY!r} version {VERSION}"
        )
    files = raw.get("files")
    if not isinstance(files, dict):
        raise GateError(f"baseline {path} has no `files` mapping")
    clean: dict[str, int] = {}
    for rel, hits in files.items():
        if not isinstance(rel, str) or isinstance(hits, bool) or not isinstance(hits, int) or hits < 0:
            raise GateError(f"baseline {path} entry {rel!r} is not a non-negative line count")
        if rel.startswith(protected):
            raise GateError(
                f"baseline {path} records the protected path {rel!r}. German there is the "
                "product; the gate never measures it and must never be told it did."
            )
        clean[rel] = hits
    return clean


class Verdict(TypedDict):
    """The comparison's shape, typed so `report` iterates lists rather than `object`."""

    regressions: list[tuple[str, int, int]]
    lowered: list[tuple[str, int, int]]
    baseline_total: int
    measured_total: int
    measured_files: int


def evaluate(baseline: dict[str, int], measured: dict[str, int]) -> Verdict:
    """Compare two per-file counts. Growth anywhere is a regression, even if the total shrank."""
    regressions: list[tuple[str, int, int]] = []
    lowered: list[tuple[str, int, int]] = []
    regressions = []
    lowered = []
    for rel in sorted(set(baseline) | set(measured)):
        old, new = baseline.get(rel, 0), measured.get(rel, 0)
        if new > old:
            regressions.append((rel, old, new))
        elif new < old:
            lowered.append((rel, old, new))
    return {
        "regressions": regressions,
        "lowered": lowered,
        "baseline_total": sum(baseline.values()),
        "measured_total": sum(measured.values()),
        "measured_files": len(measured),
    }


def report(result: Verdict) -> tuple[int, list[str]]:
    """The operator's text, and the exit code: 1 on growth, 0 otherwise."""
    regressions = result["regressions"]
    lowered = result["lowered"]
    total = result["measured_total"]
    lines: list[str] = []
    if regressions:
        grew = sum(new - old for _, old, new in regressions)
        lines.append(
            f"language gate: FAIL — German developer prose grew in "
            f"{len(regressions)} file(s) (+{grew} lines)"
        )
        for rel, old, new in regressions:
            lines.append(f"  {rel}: {old} -> {new} (+{new - old})")
        lines.append(f"  total {result['baseline_total']} -> {total} lines")
        lines.append(
            f"Rewrite those lines in English. Do not run `{UPDATE_HINT}` to cover them — "
            "--update only ever lowers this baseline."
        )
        return 1, lines
    if lowered:
        lines.append("language gate: PASS — no file grew past the baseline")
        lines.append(
            f"  total {result['baseline_total']} -> {total} lines "
            f"({result['measured_files']} files still carry German)"
        )
        lines.append(
            f"  {len(lowered)} file(s) sit below their baseline entry: the baseline "
            "can be lowered"
        )
        lines.append(f"  {UPDATE_HINT}")
        return 0, lines
    lines.append("language gate: PASS — the tree matches the baseline")
    lines.append(f"  total {total} lines over {result['measured_files']} files")
    return 0, lines


def write_baseline(path: Path, measured: dict[str, int]) -> None:
    """Freeze a measurement. Sorted keys, no timestamp: the file must diff cleanly."""
    payload = {
        "policy": POLICY,
        "version": VERSION,
        "instrument": "scripts/language_inventory.py",
        "total": sum(measured.values()),
        "files": measured,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_baseline(path: Path, measured: dict[str, int], protected: tuple[str, ...]) -> int:
    """Tighten the baseline to the current tree — never loosen it."""
    if not path.exists():
        write_baseline(path, measured)
        print(
            f"language gate: baseline created — {sum(measured.values())} German lines over "
            f"{len(measured)} files ({path.name})"
        )
        return 0
    before = load_baseline(path, protected)
    higher = [(rel, before[rel], measured[rel]) for rel in measured if measured[rel] > before.get(rel, 0)]
    if higher:
        print(
            f"language gate: FAIL — baseline was not written; --update only lowers it "
            f"({len(higher)} file(s) would rise)",
            file=sys.stderr,
        )
        for rel, old, new in sorted(higher):
            print(f"  {rel}: {old} -> {new} (+{new - old})", file=sys.stderr)
        print(
            f"  fix the wording in English first, then run {UPDATE_HINT} again",
            file=sys.stderr,
        )
        return 1
    write_baseline(path, measured)
    freed = len(set(before) - set(measured))
    dropped = sum(before.values()) - sum(measured.values())
    print(
        f"language gate: baseline lowered — {sum(before.values())} -> {sum(measured.values())} "
        f"German lines ({dropped} fewer, {freed} file(s) now clean)"
    )
    return 0


def main(
    argv: list[str] | None = None,
    *,
    list_files: Callable[[], list[str]] | None = None,
    read_text: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT, help="committed baseline")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to measure")
    parser.add_argument(
        "--update", action="store_true",
        help="lower the baseline to the current tree (refuses to raise it)",
    )
    parser.add_argument(
        "--staged", action="store_true",
        help="measure the staged blobs instead of the whole tree, for a pre-commit hook",
    )
    args = parser.parse_args(argv)
    try:
        if args.staged and args.update:
            raise GateError(
                "--update measures the whole tree; combining it with --staged would write a "
                "baseline from the few files one commit happens to carry"
            )
        protected = checked_protected_prefixes()
        tracked = None
        if args.staged and list_files is None and read_text is None:
            list_files, read_text = staged_readers(args.root)
        paths = list_files() if list_files is not None else tracked_files(args.root)()
        measured = inventory.counts_for(paths, read_text) if read_text is not None else (
            measure(args.root, list_files=lambda: paths)
        )
        if args.update:
            return update_baseline(args.baseline, measured, protected)
        baseline = load_baseline(args.baseline, protected)
        if not args.staged:
            refuse_orphan_entries(baseline, paths)
        result = evaluate(baseline, measured)
    except GateError as exc:
        print(f"language gate: ERROR — {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else exc
        print(f"language gate: ERROR — git ls-files failed: {detail}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"language gate: ERROR — {exc}", file=sys.stderr)
        return 2
    code, lines = report(result)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
