"""Finding #18 guard: every mounted route in this table keeps a named surface.

The audit of 2026-10-08 proved each path below against the app source. This file
turns that proof into a standing check, so "nobody knows which of the three
states this endpoint is in" cannot come back silently: if a surface stops
referencing its endpoint, the test says which pair broke and the answer has to be
one of (a) wire/pin it, (b) remove it, (c) keep it with a comment naming the
decision it waits on.

The check is a symbol presence, not a call-graph walk: the PWA reads endpoints
through named wrappers (app/src/lib/api/*), so a component that still imports
``getTasks`` still has the surface. Renaming a file is allowed to fail here —
that is the moment the classification must be re-read.
"""
from __future__ import annotations

import re
from pathlib import Path

APP_SRC = Path(__file__).resolve().parents[1] / "app" / "src"

#: route -> (symbol or literal the surface must mention, files that are the surface)
SURFACES: dict[str, tuple[str, list[str]]] = {
    "GET /api/tasks": (
        "getTasks",
        [
            "hooks/useTasks.ts",
            "components/dashboard/AgentStatusButton.tsx",
            "components/dashboard/settings/model/useSettingsLists.ts",
            "components/dashboard/settings/model/useSettingsCore.ts",
        ],
    ),
    "POST /api/tasks": (
        "createTask",
        [
            "components/dashboard/settings/model/useSettingsLists.ts",
        ],
    ),
    "PUT /api/tasks/{id}": (
        "updateTask",
        [
            "components/dashboard/settings/model/useSettingsLists.ts",
        ],
    ),
    "DELETE /api/tasks/{id}": (
        "deleteTask",
        [
            "components/dashboard/settings/model/useSettingsLists.ts",
        ],
    ),
    "GET /api/system/metrics": (
        "/api/system/metrics",
        ["components/dashboard/MetricsGauges.tsx"],
    ),
    "GET /api/projects": (
        "listProjects",
        [
            "components/dashboard/Sidebar.tsx",
            "components/dashboard/WorkspaceBar.tsx",
        ],
    ),
    "GET /api/learning/proposals": (
        "getLearningProposals",
        ["components/dashboard/chat/model.ts"],
    ),
    "POST /api/learning/proposals/{pid}/accept": (
        "acceptLearningProposal",
        ["components/dashboard/chat/model.ts"],
    ),
    "POST /api/learning/proposals/{pid}/dismiss": (
        "dismissLearningProposal",
        ["components/dashboard/chat/model.ts"],
    ),
}

#: The one endpoint that is deliberately surface-free (state (a): external
#: harnesses poll it, no PWA caller; pinned by tests/test_r33_token_accounting.py).
CALLER_FREE = "/api/metrics"


def _read(rel_path: str) -> str:
    path = APP_SRC / rel_path
    assert path.is_file(), f"surface file moved or renamed: app/src/{rel_path}"
    return path.read_text(encoding="utf-8")


def test_app_source_is_present():
    assert APP_SRC.is_dir(), f"expected the PWA source at {APP_SRC}"


def _mentions(text: str, symbol: str) -> bool:
    """Identifier symbols need word boundaries (``getTasks`` must not match
    ``getTasksExtra``); a path literal has none to begin with."""
    if re.fullmatch(r"[A-Za-z_$][\w$]*", symbol):
        return re.search(rf"\b{re.escape(symbol)}\b", text) is not None
    return symbol in text


def test_every_audited_route_names_its_surface_files():
    """Guards the table itself: a route entry without a file is an unanswered
    state, which is exactly what finding #18 is about."""
    for route, (symbol, files) in SURFACES.items():
        assert symbol, route
        assert files, f"{route} claims a surface but names no file"


def test_each_surface_still_references_its_endpoint():
    for route, (symbol, files) in SURFACES.items():
        for rel in files:
            assert _mentions(_read(rel), symbol), (
                f"{route} lost its surface in app/src/{rel} — re-run the "
                f"finding #18 audit for this endpoint"
            )


def test_caller_free_alias_stays_caller_free():
    """If someone wires /api/metrics into the app, this fails and the endpoint
    changes state on purpose — then the docstring in server/routes/metrics.py
    must be updated to name the surface instead of the harness."""
    hits = [
        p.relative_to(APP_SRC).as_posix()
        for p in APP_SRC.rglob("*")
        if p.is_file()
        and p.suffix in {".ts", ".tsx"}
        and ".test." not in p.name
        and CALLER_FREE in p.read_text(encoding="utf-8")
    ]
    assert hits == [], f"{CALLER_FREE} gained an app caller: {hits}"
