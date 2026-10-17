"""What moved between two revisions, per lockfile: the report `lockfile_check.py --diff` prints.

`lockfile_check.py`'s other half is a verdict; this one never fails a leg. It is the record the
"majors one at a time, diff first" rule (owner, 2026-10-09) needs in order to be checkable, so it
prints the movement of every entry, names the majors, and stays readable when an entry's base
version did not change but its peer set did.

The two files are read out of git rather than out of the worktree, because the question is about
a commit: `git show <rev>:<path>` on a clone with `fetch-depth: 2` is what the nightly has. A
path that a revision does not carry is a refusal for the caller to print, not an empty diff.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies")


class CheckError(RuntimeError):
    pass


def resolves(rev: str) -> bool:
    """Whether a revision exists in this clone. `git show` already treats a miss as an error."""
    done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", rev], capture_output=True,
                          text=True, check=False, cwd=ROOT)
    return done.returncode == 0


def git_show(rev: str, path: str) -> str:
    done = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True,
                          check=False, cwd=ROOT)
    if done.returncode != 0:
        raise CheckError(f"`{path}` is not readable at {rev}: {(done.stderr or '').strip()[:120]}")
    return done.stdout


def pnpm_versions(text: str) -> dict[str, str]:
    """The resolved version behind each importer entry, for a diff between two revisions."""
    import yaml  # noqa: PLC0415
    lock = yaml.safe_load(text)
    root = (lock.get("importers") or {}).get(".") or {}
    out: dict[str, str] = {}
    for section in LOCK_SECTIONS:
        for name, meta in (root.get(section) or {}).items():
            out[name] = str((meta or {}).get("version"))
    return out


def uv_versions(text: str) -> dict[str, str]:
    """name -> version for every `[[package]]` block in uv.lock.

    Parsed by field rather than with tomllib: the leg runs on 3.12 and 3.13 where tomllib exists, but
    the same script has to answer on the 3.10 leg that `requires-python` allows, and a dependency
    backport for one regex over a generated file is not a trade worth making here.
    """
    out: dict[str, str] = {}
    name = version = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[[package]]":
            if name and version:
                out[name] = version
            name = version = None
        elif stripped.startswith("name = "):
            name = stripped.split("=", 1)[1].strip().strip('"')
        elif stripped.startswith("version = "):
            version = stripped.split("=", 1)[1].strip().strip('"')
    if name and version:
        out[name] = version
    return out


def base_version(value: str) -> str:
    """The leading version of a pnpm `version` field, without its peer suffixes.

    pnpm records `1.2.0(@types/react@19.3.0)(react@19.3.0)`; the movement a human reads is `1.1.23 ->
    1.2.0`, and the peers still decide the comparison because the full string is what is diffed.
    """
    return value.split("(", 1)[0]


def major_of(value: str) -> str | None:
    match = re.match(r"(?:v?)(\d+)", base_version(value))
    return match.group(1) if match else None


def describe_diff(label: str, before: dict[str, str], after: dict[str, str]) -> tuple[int, list[str]]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(name for name in set(before) & set(after) if before[name] != after[name])
    # A same-version entry whose peer set moved is a real install change, and the base version alone
    # would print `zustand: 5.0.15 -> 5.0.15` and read as noise.
    lines = [
        f"{name}: {base_version(before[name])} -> {base_version(after[name])}"
        + (" (peer set moved)" if base_version(before[name]) == base_version(after[name]) else "")
        for name in changed
    ]
    lines += [f"{name}: added at {base_version(after[name])}" for name in added]
    lines += [f"{name}: removed (was {base_version(before[name])})" for name in removed]
    majors = [
        f"{name}: {base_version(before[name])} -> {base_version(after[name])}"
        for name in changed if major_of(before[name]) != major_of(after[name])
    ]
    total = len(added) + len(removed) + len(changed)
    print(f"lockfile: {label} -- {total} movement(s): {len(changed)} updated, {len(added)} added, "
          f"{len(removed)} removed, {len(majors)} of them a major version")
    for line in lines:
        print(f"  {line}")
    for line in majors:
        print(f"  MAJOR {line}")
    return total, majors


def check_diff(rev_range: str) -> int:
    """Print what moved between two revisions, per manifest. A report, never a verdict."""
    before_ref, after_ref = (part.strip() for part in rev_range.split("..", 1))
    if not resolves(before_ref):
        # The public mirror is a single squashed export, so `HEAD^` cannot resolve there. This
        # is a report and not a verdict, so a range with no before is stated and costs nothing.
        print(f"lockfile: nothing to compare — {before_ref} does not resolve in this clone")
        return 0
    moved = 0
    major_moves: list[str] = []
    moved, majors = describe_diff(
        "app/pnpm-lock.yaml",
        pnpm_versions(git_show(before_ref, "app/pnpm-lock.yaml")),
        pnpm_versions(git_show(after_ref, "app/pnpm-lock.yaml")),
    )
    major_moves += majors
    try:
        more, majors = describe_diff(
            "uv.lock",
            uv_versions(git_show(before_ref, "uv.lock")),
            uv_versions(git_show(after_ref, "uv.lock")),
        )
        moved += more
        major_moves += majors
    except CheckError as exc:
        print(f"lockfile: uv.lock -- {exc}")
    print(f"lockfile: {before_ref}..{after_ref} moves {moved} entr(y/ies) and "
          f"{len(major_moves)} major(s)")
    return 0
