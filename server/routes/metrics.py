"""server/routes/metrics.py – GET /api/system/metrics + GET /api/projects (R26).

Shell data endpoints for the redesigned UI:

- ``/api/system/metrics``: CPU / memory / disk / uptime for the TopBar live
  gauges. psutil is a main dependency; if it is ever missing, the endpoint
  degrades gracefully (disk via shutil, cpu/mem = null, ``available=false``).
- ``/api/projects``: discoverable projects under the active workspace
  (preferred) plus the default project roots — powers the sidebar
  PROJEKTE tree and the welcome cards.
"""
from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

from core.project_discovery import ProjectRecord, discover_project_records

router = APIRouter(tags=["System"])

_START_TIME = time.time()


def _process_uptime_s() -> float:
    """Backend process uptime in seconds (best effort, never throws)."""
    try:
        import psutil

        proc = psutil.Process()
        return max(0.0, time.time() - proc.create_time())
    except Exception:
        return max(0.0, time.time() - _START_TIME)


def _disk_payload() -> dict:
    """Disk usage for the workspace (fallback: home). shutil has no percent — compute it."""
    try:
        root = _workspace_dir()
        disk = shutil.disk_usage(root)
    except Exception:
        try:
            disk = shutil.disk_usage(Path.home())
        except Exception:
            return {"disk_free_bytes": 0, "disk_free_gb": 0.0, "disk_percent": 0.0}
    percent = round(disk.used / disk.total * 100, 1) if disk.total else 0.0
    return {
        "disk_free_bytes": disk.free,
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "disk_percent": percent,
    }


def _workspace_dir() -> str:
    # Dynamic import: tests monkeypatch core.engine_config.get_workspace_dir,
    # so the binding must be resolved at call time, never at import time.
    from core.engine_config import get_workspace_dir

    return get_workspace_dir()


def _read_metrics() -> dict:
    """Collect metrics; missing psutil → honest degradation, never fabricated."""
    try:
        import psutil

        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        return {
            "available": True,
            "cpu_percent": round(float(cpu), 1),
            "mem_used_mb": round(vm.used / (1024 * 1024)),
            "mem_percent": round(vm.percent, 1),
            "uptime_s": round(_process_uptime_s()),
            **_disk_payload(),
        }
    except ImportError:
        # No psutil: disk only (stdlib), everything else honestly null.
        return {
            "available": False,
            "cpu_percent": None,
            "mem_used_mb": None,
            "mem_percent": None,
            "uptime_s": round(max(0.0, time.time() - _START_TIME)),
            **_disk_payload(),
        }


def _record_to_dict(rec: ProjectRecord, workspace: str) -> dict:
    return {
        "name": rec.name,
        "path": str(rec.path),
        "stacks": rec.stacks,
        "score": rec.score,
        "workspace": workspace,
    }


@router.get("/system/metrics")
def system_metrics() -> dict:
    """Shell gauges for the TopBar. Surface: app/src/components/dashboard/MetricsGauges.tsx:70
    (polls this path only, and only while the tab is visible). Pinned by
    tests/test_r26_shell_api.py — shape with psutil and the honest degradation
    without it. Rate-limit neighbour: tests/test_w10_rate_limit.py lists it."""
    return _read_metrics()


@router.get("/metrics")
def metrics_alias() -> dict:
    """Public alias of /api/system/metrics (R33, stress triage P2).

    Harnesses and dashboards conventionally poll /api/metrics; answering it
    with the identical payload is cheaper than letting it 404 into the SPA.

    Finding #18 status (2026-10-08): NO app surface calls this — the PWA reads
    /api/system/metrics. It is kept as (a): a real need (external pollers guess
    this path, see docs/STRESS_1000_2026-09-06.md P2-3) with no in-repo caller,
    pinned by tests/test_r33_token_accounting.py:216 asserting both answers are
    the same payload. Removing it would only be safe once no harness is known.
    """
    return _read_metrics()


def _dedupe_by_name(records: list[ProjectRecord]) -> list[ProjectRecord]:
    """Same project name in several roots (Desktop copy vs. repo clone) is one
    sidebar entry: keep the highest-scoring record, preserve first-seen order."""
    best: dict[str, ProjectRecord] = {}
    order: list[str] = []
    for rec in records:
        key = rec.name.strip().lower()
        current = best.get(key)
        if current is None:
            best[key] = rec
            order.append(key)
        elif rec.score > current.score:
            best[key] = rec
    return [best[key] for key in order]


@router.get("/projects")
def list_projects() -> dict:
    """Projects for the sidebar tree / welcome cards (never throws).

    Finding #18 status (2026-10-08): three live callers — app/src/components/dashboard/
    Sidebar.tsx:316, WorkspaceBar.tsx:53, WelcomeEmptyState.tsx:47 (wrapper
    listProjects() in app/src/lib/api/endpoints.ts:300). Pinned by
    tests/test_r26_shell_api.py. Kept."""
    try:
        workspace = _workspace_dir()
    except Exception:
        workspace = str(Path.cwd())
    ws = Path(workspace)
    if not ws.is_dir():
        return {"workspace": workspace, "projects": [], "generated_at": _now_iso()}

    # Two-stage discovery: the workspace ALWAYS fills its slots first.
    # A single mixed-roots run with max_results would let default-root
    # projects crowd out workspace projects before any sort could fix it.
    try:
        records: list[ProjectRecord] = list(
            discover_project_records(roots=[ws], max_results=8)
        )
    except Exception:
        records = []
    if len(records) < 8:
        try:
            from core.project_discovery import default_project_roots

            default_roots = [r for r in default_project_roots() if r.is_dir() and r != ws]
            if default_roots:
                seen = {str(r.path) for r in records}
                defaults = discover_project_records(roots=default_roots, max_results=8)
                for rec in defaults:
                    if len(records) >= 8:
                        break
                    if str(rec.path) in seen:
                        continue
                    seen.add(str(rec.path))
                    records.append(rec)
        except Exception:
            pass
    records = _dedupe_by_name(records)
    return {
        "workspace": workspace,
        "projects": [_record_to_dict(r, workspace) for r in records],
        "generated_at": _now_iso(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
