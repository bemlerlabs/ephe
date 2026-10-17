"""The two kinds of file in a cohort's runs directory, named in one place.

`preflight.json` and the rep manifests share a directory, and on 2026-10-11 four readers each
drew the line somewhere else: `bench_option_b.py --score` died on `KeyError: 'family'` over the
stamp, `bench_trend.py` folded the stamp into the rep set, and `bench_preflight.py` matched task
ids against a filename split on `"-r"`, which no manifest name produced by the harness contains,
so a scoped run never saw the manifests already sitting in its own directory. The naming rule
lives here so the readers cannot drift apart again.
"""
from __future__ import annotations

import re
from pathlib import Path

#: The bless stamp, written into the runs directory by `evals/bench_preflight.py`.
STAMP_NAME = "preflight.json"

#: `evals/bench_option_b.py` writes `{task.id.lower()}_r{rep}.json`.
MANIFEST_NAME = re.compile(r"[a-z]+[0-9]+_r[0-9]+\.json")


def is_manifest(path: Path) -> bool:
    return path.name != STAMP_NAME and bool(MANIFEST_NAME.fullmatch(path.name))


def task_id_of(path: Path) -> str:
    return path.stem.split("_r")[0].upper()


def manifest_paths(runs_dir: Path, ids: list[str] | None = None) -> list[Path]:
    """Rep manifests in `runs_dir`, narrowed to the task ids in `ids` when any are given."""
    if not runs_dir.is_dir():
        return []
    wanted = {i.strip().upper() for i in (ids or []) if i.strip()}
    found = []
    for path in sorted(runs_dir.glob("*.json")):
        if not is_manifest(path):
            continue
        if wanted and task_id_of(path) not in wanted:
            continue
        found.append(path)
    return found
