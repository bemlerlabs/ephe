"""W4 S2: skills-lock.json — integrity lock for every skill pack.

Stdlib-only, idempotent. Format:

    {"version": 1, "skills": [{"name": ..., "source": ..., "computedHash": ...}]}

computedHash per pack: SHA256 over the sorted concatenation
    "<relpath>\\n <sha256(file)>\\n"
for EVERY file in the pack (SKILL.md + references/ templates/ scripts/ assets/),
relative to the pack folder, lexicographically sorted → deterministic.

Usage:
    python scripts/generate_skills_lock.py            # write the lock
    python scripts/generate_skills_lock.py --check    # drift → exit 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
LOCK_FILE = REPO_ROOT / "skills-lock.json"

# Subfolders that belong to the pack (besides SKILL.md at pack level).
_PACK_SUBDIRS = ("references", "templates", "scripts", "assets")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pack_hash(pack_dir: Path) -> str:
    """SHA256 over the sorted 'relpath\\n sha256\\n' concatenation of all
    pack files (SKILL.md + _PACK_SUBDIRS). Deterministic; an empty folder
    → hash over empty input."""
    entries: list[str] = []
    skill_md = pack_dir / "SKILL.md"
    if skill_md.is_file():
        entries.append(f"{skill_md.relative_to(pack_dir)}\n{_file_hash(skill_md)}\n")
    for sub in _PACK_SUBDIRS:
        sub_dir = pack_dir / sub
        if not sub_dir.is_dir():
            continue
        for f in sorted(p for p in sub_dir.rglob("*") if p.is_file()):
            entries.append(f"{f.relative_to(pack_dir)}\n{_file_hash(f)}\n")
    payload = "".join(sorted(entries)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_lock(root: Path = REPO_ROOT) -> dict:
    skills_dir = root / "skills"
    packs = sorted(
        (p for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()),
        key=lambda p: p.name,
    )
    return {
        "version": 1,
        "skills": [
            {
                "name": p.name,
                "source": str(p.relative_to(root)),
                "computedHash": pack_hash(p),
            }
            for p in packs
        ],
    }


def verify(root: Path = REPO_ROOT) -> tuple[bool, list[str]]:
    """Compares skills-lock.json with what is on disk. Returns (ok, diffs) —
    one structured line per deviation, naming the pack."""
    lock_file = root / "skills-lock.json"
    if not lock_file.is_file():
        return False, ["skills-lock.json fehlt — `python scripts/generate_skills_lock.py`"]
    try:
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, [f"skills-lock.json unparser: {exc}"]
    expected = {e["name"]: e["computedHash"] for e in build_lock(root)["skills"]}
    actual = {e["name"]: e["computedHash"] for e in lock.get("skills", [])}
    diffs: list[str] = []
    for name in sorted(set(expected) | set(actual)):
        if name not in expected:
            diffs.append(f"skills_lock_mismatch pack={name} status=extra_in_lock")
        elif name not in actual:
            diffs.append(f"skills_lock_mismatch pack={name} status=missing_on_disk")
        elif expected[name] != actual[name]:
            diffs.append(
                f"skills_lock_mismatch pack={name} "
                f"lock={actual[name][:12]} disk={expected[name][:12]}"
            )
    return (not diffs), diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="skills-lock.json generator")
    parser.add_argument("--check", action="store_true",
                        help="check only: exit 1 on drift between lock and disk")
    args = parser.parse_args(argv)

    if args.check:
        ok, diffs = verify()
        for line in diffs:
            print(line, file=sys.stderr)
        return 0 if ok else 1

    lock = build_lock()
    LOCK_FILE.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"skills-lock.json written: {len(lock['skills'])} packs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
