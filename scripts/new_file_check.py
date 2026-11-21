#!/usr/bin/env python3
"""New-file gate: a path no committed baseline covers must carry no finding at all.

Both ratchets build their corpus from `git ls-files` — `scripts/prose_tells.py` over
`PROSE_ROOTS`, `scripts/language_gate.py` over the whole checkout. A file a wave writes
and leaves unstaged is absent from that list, and because neither committed baseline holds
an entry for it, the union walk in `evaluate` has nothing to compare either. Wave 3 landed
87 prose tells and 27 German developer lines across 28 such files, and the whole-tree
passes stayed green until the moment those files were staged.

The question here is the one the ratchets cannot ask: does a path neither baseline covers
carry a prose tell or a German line? A path that either baseline already scores stays with
that ratchet, so a verdict here never widens an allowance and never reopens a file the
tree has already counted.

The instruments are the ratchets' own, called the way the ratchets call them, so a number
this gate prints for a path is the number that ratchet would print for the same path.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import language_gate  # noqa: E402  (path bootstrap above)
import language_inventory as inventory  # noqa: E402
import prose_scope_check as prose_scope  # noqa: E402
import prose_tells as tells  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent
PREFIX = "new-file"
PROSE_BASELINE = tells.BASELINE_DEFAULT
LANGUAGE_BASELINE = language_gate.BASELINE_DEFAULT


def run_git(root: Path, args: list[str]) -> list[str]:
    """One git call against `root`, split into lines."""
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
    )
    return done.stdout.splitlines()


def candidate_paths(root: Path) -> list[str]:
    """Every path git tracks here, plus every path it does not ignore."""
    tracked = run_git(root, ["ls-files"])
    untracked = run_git(root, ["ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked) | set(untracked))


def diff_paths(from_file: str) -> list[str]:
    """The paths of one diff, from `--paths-from`, else from `EPHE_STAGED_PATHS`."""
    text = ""
    if from_file:
        text = Path(from_file).read_text(encoding="utf-8")
    elif os.environ.get("EPHE_STAGED_PATHS"):
        text = os.environ["EPHE_STAGED_PATHS"]
    return [line.strip() for line in text.splitlines() if line.strip()]


def disk_reader(root: Path) -> Callable[[str], str]:
    """The worktree text of a path, which is what an unstaged file carries.

    A commit hook needs the index blob; this gate needs the bytes a worker just wrote,
    and a path that never reached the index has no blob to read.
    """
    def read(rel: str) -> str:
        return (root / rel).read_text(encoding="utf-8")
    return read


def covered_paths(prose: dict[str, int], german: dict[str, int]) -> set[str]:
    """The paths the committed baselines already score, so a ratchet owns each one."""
    return set(prose) | set(german)


def measure(
    paths: list[str], read_text: Callable[[str], str],
) -> tuple[dict[str, int], dict[str, int]]:
    """Both ratchet instruments over `paths`, as (prose tells, German lines) per path.

    `prose_tells.score` is the whole-corpus pass, so the repeated-banner class compares
    the same wordings the ratchet compares; a path outside `PROSE_ROOTS` carries no prose
    this tree measures and scores nothing there.
    """
    prose_inputs = [rel for rel in paths if prose_scope.in_prose_scope(rel)]
    texts = tells.texts_of(prose_inputs, read_text)
    tells_by_path = tells.score(texts)[0]
    german_by_path = inventory.counts_for(paths, read_text)
    return tells_by_path, german_by_path


def violations(
    paths: list[str],
    covered: set[str],
    tells_by_path: dict[str, int],
    german_by_path: dict[str, int],
) -> list[tuple[str, int, int]]:
    """The fresh paths carrying a finding, each as (path, tells, German lines)."""
    rows: list[tuple[str, int, int]] = []
    for rel in paths:
        if rel in covered:
            continue
        tell = tells_by_path.get(rel, 0)
        german = german_by_path.get(rel, 0)
        if tell or german:
            rows.append((rel, tell, german))
    return rows


def report(rows: list[tuple[str, int, int]], judged: int, left: int) -> tuple[int, list[str]]:
    """The operator's text, and the exit code: 1 on a finding, 0 otherwise."""
    lines: list[str] = []
    if rows:
        lines.append(
            f"{PREFIX} gate: FAIL — {len(rows)} path(s) no committed baseline covers "
            "carry a finding"
        )
        for rel, tell, german in rows:
            lines.append(f"  {rel}: {tell} tell(s), {german} German line(s)")
        lines.append(
            "Rewrite those lines in English. Adding the path to a baseline is the one "
            "move that hides it, because `--update` refuses to raise either baseline and "
            "a hand-written entry is a budget the tree never earned."
        )
        return 1, lines
    lines.append(
        f"{PREFIX} gate: PASS — {judged} path(s) neither baseline covers are clean; "
        f"{left} path(s) a ratchet already scores stay with it"
    )
    return 0, lines


def main(
    argv: list[str] | None = None,
    *,
    list_files: Callable[[], list[str]] | None = None,
    read_text: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="checkout to judge")
    parser.add_argument("--prose-baseline", type=Path, default=PROSE_BASELINE, help="committed tell baseline")
    parser.add_argument("--language-baseline", type=Path, default=LANGUAGE_BASELINE, help="committed German baseline")
    parser.add_argument(
        "--paths-from",
        default="",
        help="file holding the paths of one diff; an empty value judges the whole checkout",
    )
    args = parser.parse_args(argv)

    try:
        protected = language_gate.checked_protected_prefixes()
        prose = tells.load_baseline(args.prose_baseline)
        german = language_gate.load_baseline(args.language_baseline, protected)
        paths = (
            list_files()
            if list_files
            else (diff_paths(args.paths_from) or candidate_paths(args.root))
        )
        reader = read_text if read_text else disk_reader(args.root)
        tells_by_path, german_by_path = measure(paths, reader)
    except language_gate.GateError as exc:
        print(f"{PREFIX} gate: ERROR — {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else exc
        print(f"{PREFIX} gate: ERROR — git failed: {detail}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"{PREFIX} gate: ERROR — {exc}", file=sys.stderr)
        return 2

    covered = covered_paths(prose, german)
    judged = sum(1 for rel in paths if rel not in covered)
    code, lines = report(
        violations(paths, covered, tells_by_path, german_by_path),
        judged,
        len(paths) - judged,
    )
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
