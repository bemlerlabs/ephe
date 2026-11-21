"""Ephe — the bench workspace, verified on the surface and never written to it (U8).

The harness used to POST its fixture directory into the product's one shared `workspace_dir`
for the whole run and put it back in a `finally`. Measured 2026-10-10: a single handover is
1 GET plus 2 POSTs to `/api/settings`, and the first POST persists a scratch path into
`~/.ephe/engine.json`. Every other conversation on that surface then reads the fixture tree,
and a run that dies between the two POSTs leaves the scratch value for someone to restore by
hand — which is what happened.

`core.engine_config.get_workspace_dir()` resolves `EPHE_WORKSPACE` before anything persisted,
so a backend started with that variable owns one directory without the harness writing
anywhere. The read that reports it is `/api/projects`, whose `workspace` field comes from
`get_workspace_dir()`. `/api/settings` answers the persisted value first and would reject a
correctly isolated backend, so it is not the verification route.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


class SurfaceNotIsolated(RuntimeError):
    """The surface works outside this cohort's workspace: there is no run to start."""


def run_workspace(cohort_root: Path | str) -> Path:
    """`EPHE_BENCH_WORKSPACE` wins; the default sits inside the cohort tree."""
    env = (os.environ.get("EPHE_BENCH_WORKSPACE") or "").strip()
    return Path(env).expanduser() if env else Path(cohort_root) / "ws"


def active_workspace(base: str, seconds: int = 10) -> str:
    """The workspace the surface will really work in, as it reports it."""
    with urllib.request.urlopen(f"{base}/api/projects", timeout=seconds) as response:
        return str((json.load(response) or {}).get("workspace") or "").strip()


def _resolved(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:  # noqa: BLE001 — an unresolvable answer is not an isolation proof
        return path


def require_isolated_surface(base: str, workspace: Path | str, seconds: int = 10) -> str:
    """Refuse a cohort whose surface points somewhere else than this run's workspace.

    Writing the value is not the repair: only whoever starts the backend can put it in the
    cohort's tree, and the message names the variable that does.
    """
    wanted = str(Path(str(workspace)).expanduser())
    target = _resolved(wanted)
    try:
        answer = _resolved(active_workspace(base, seconds))
    except Exception as exc:  # noqa: BLE001 — an unreadable surface is not an isolated one
        raise SurfaceNotIsolated(
            f"{base} did not report a workspace ({type(exc).__name__}: {exc}). "
            f"Start the backend for this cohort: EPHE_WORKSPACE={wanted}"
        ) from exc
    if answer and answer == target:
        return target
    raise SurfaceNotIsolated(
        f"{base} works in {answer or 'unset'} and this cohort needs {wanted}. Repointing it "
        f"measures the fixture tree for every other conversation on the surface and persists "
        f"a scratch path into the product's config. Start the backend for the cohort instead: "
        f"EPHE_WORKSPACE={wanted} python run_server.py --port <the port this cohort uses>"
    )
