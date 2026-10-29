"""W3-68 — the /api/* contract is frozen: every route is named here (rule 11).

Playbook rule 11 (ephe-notes/06-ephe-team-playbook.md:19, "never break userspace"):
the OpenAPI paths and the tool registry are the product's userspace — no release
moves, renames or narrows an entry without a documented migration path, and
everything under /api/* passes an API-review gate. W3-67 holds the registry half;
the routes half lives here.

The gate is this file. ``FROZEN_ROUTES`` names every /api/* operation the app
publishes at the freeze; the set is compared for exact equality against the live
OpenAPI document. It is deliberately a list, not a count: when a route moves the
failure names the exact pair (method + path), because a bare total would let a
rename hide inside an add + delete.

The allowed direction is additive — but an addition still reds this file, on
purpose, because that is the review. To land a new or changed route: run the
enumerator, read the delta this test prints, and update ``FROZEN_ROUTES`` in the
same commit that touches ``server/routes/*`` or ``server/main.py``.

Freeze numbers (``create_app().openapi()``, 2026-10-14, HEAD-only tree):

  177 operations (method + path) over 154 paths, on from 169 over 149. Wave 5D
  (2026-10-20) adds the server-authoritative store's create, read, rename and
  activate; the existing sessions routes stay and
  ``docs/SESSION_STORE_DECISION.md`` records the store decision. The three
  sessions additions (list, delete, prune) landed with ``core/session_lifecycle.py``:
  the store had no reachable hold on the files it wrote. ``POST /api/sessions/clear``
  is the one-action counterpart (every namespace, nothing kept). The ten isolation
  additions
  (trees, change sets, review, publish) landed with ``server/routes/workspaces.py``,
  where four modules that had tests and no caller — ``core/workspace_lifecycle``,
  ``core.change_set``, ``core.review_gate``, ``core.atomic_publish`` — became reachable.
  The eleventh, ``GET /api/change-sets/{id}/custody``, states what a publish would do
  before it is asked: who signed the set, and whether the tree still hashes to what
  that signature covered.
  The three life additions (read a set's life, amend it, move it back by hand) landed
  with ``core/change_set_lifecycle.py``: publishing was a button and a set sent back
  could only be replaced under a new id, so the loop those routes run needed a surface
  of its own.
  Then one steering addition: ``POST /api/chat/steer`` is the control the composer
  needed, because until it existed a direction change mid-run could only be queued
  behind the turn or thrown away with the cancel button.
  One more route, ``GET /api/change-sets/claims``, asked the store its own question: it
  already knew which run held each path and since when, and nothing outside the
  page could ask it.
  The twelfth isolation addition, ``POST /api/change-sets/{id}/unpublish``, takes a
  landing back: a published set had no way off the end of the line, so a publish that
  landed wrong could only be corrected by building the change set again. Its core is
  ``core.change_set_lifecycle.unpublish``, and the landing it undoes keeps its stamp and
  the oid the publish wrote.
  Three SOL additions: ``GET /api/sol/heuristics`` is the inspector's view on the
  workspace's ``.ephe/learning/heuristics.md`` (rules, map, the switch), and
  ``PATCH``/``DELETE /api/sol/heuristics/{rule_id}`` are the same edit and delete a
  hand edit performs, so the settings surface and the file cannot disagree.
  One update addition: ``POST /api/update/apply`` runs the same pull and installer
  ``ephe update`` runs, so a user on a checkout can take the merges between two
  tags from the dialog instead of a terminal. It refuses a dirty tree, another
  branch and a second click, and it is the only route under /api/update that writes.

The routing table carries one more /api surface than the schema documents —
``GET /api/docs`` (``docs_url``), pinned below — and the proxy catch-all is
published without its ``:path`` converter; neither is a second route.
"""
from __future__ import annotations

#: Every /api/* operation the app publishes, "METHOD /path", sorted. This is the
#: contract; see the module docstring for why it is a list and not a number.
FROZEN_ROUTES: tuple[str, ...] = (
    "DELETE /api/artifacts/{artifact_id}",
    "DELETE /api/channels/discord/token",
    "DELETE /api/channels/telegram/devices/{user_id}",
    "DELETE /api/channels/telegram/token",
    "DELETE /api/memory",
    "DELETE /api/memory/{doc_id}",
    "DELETE /api/schedule/{job_id}",
    "DELETE /api/sessions/{session_id}",
    "DELETE /api/skills/{name}",
    "DELETE /api/sol/heuristics/{rule_id}",
    "DELETE /api/tasks/{task_id}",
    "DELETE /api/workspaces/{id}",
    "GET /api/agent-teams",
    "GET /api/agent-teams/runs/{run_id}",
    "GET /api/agent-teams/templates",
    "GET /api/agent-teams/{team_id}",
    "GET /api/agent-teams/{team_id}/runs",
    "GET /api/agents",
    "GET /api/agents/tools",
    "GET /api/agents/{agent_id}",
    "GET /api/agents/{agent_id}/runs",
    "GET /api/artifacts",
    "GET /api/artifacts/expiry",
    "GET /api/artifacts/export",
    "GET /api/artifacts/proxy",
    "GET /api/artifacts/stats",
    "GET /api/artifacts/{artifact_id}",
    "GET /api/artifacts/{artifact_id}/file",
    "GET /api/artifacts/{artifact_id}/preview",
    "GET /api/artifacts/{artifact_id}/provenance",
    "GET /api/artifacts/{artifact_id}/versions",
    "GET /api/audit",
    "GET /api/capabilities",
    "GET /api/cell",
    "GET /api/change-sets",
    "GET /api/change-sets/claims",
    "GET /api/change-sets/{id}",
    "GET /api/change-sets/{id}/custody",
    "GET /api/change-sets/{id}/lifecycle",
    "GET /api/channels/discord/status",
    "GET /api/channels/telegram/devices",
    "GET /api/channels/telegram/status",
    "GET /api/context/budget",
    "GET /api/context/stages",
    "GET /api/ephemeris",
    "GET /api/events/multiplex",
    "GET /api/file",
    "GET /api/fs",
    "GET /api/git/branches",
    "GET /api/git/diff",
    "GET /api/git/info",
    "GET /api/git/status",
    "GET /api/health",
    "GET /api/learning/proposals",
    "GET /api/market",
    "GET /api/market/icon/{name}",
    "GET /api/market/index",
    "GET /api/market/installed",
    "GET /api/market/updates",
    "GET /api/mcp/catalog",
    "GET /api/memory/deleted",
    "GET /api/memory/export",
    "GET /api/memory/list",
    "GET /api/memory/search",
    "GET /api/memory/stats",
    "GET /api/metrics",
    "GET /api/mobile/qr",
    "GET /api/mobile/status",
    "GET /api/model/providers",
    "GET /api/network/status",
    "GET /api/plugins",
    "GET /api/plugins/commands",
    "GET /api/plugins/events",
    "GET /api/plugins/icon/{plugin_id}",
    "GET /api/profile",
    "GET /api/profile/export",
    "GET /api/project/index/status",
    "GET /api/projects",
    "GET /api/proxy/{port}",
    "GET /api/proxy/{port}/{full_path}",
    "GET /api/reader",
    "GET /api/schedule",
    "GET /api/schedule/presets",
    "GET /api/schedule/results",
    "GET /api/search",
    "GET /api/sessions",
    "GET /api/sessions/export",
    "GET /api/sessions/restore",
    "GET /api/sessions/{session_id}",
    "GET /api/settings",
    "GET /api/settings/code-exec",
    "GET /api/settings/hooks",
    "GET /api/settings/image",
    "GET /api/settings/mcp",
    "GET /api/settings/persona",
    "GET /api/settings/security",
    "GET /api/settings/voice",
    "GET /api/setup/detect",
    "GET /api/setup/status",
    "GET /api/skills",
    "GET /api/skills/export-pack/{pack_id}",
    "GET /api/skills/pack-index",
    "GET /api/skills/{name}",
    "GET /api/skills/{name}/verify",
    "GET /api/sol/heuristics",
    "GET /api/subagents",
    "GET /api/subagents/{agent_id}",
    "GET /api/system/metrics",
    "GET /api/tasks",
    "GET /api/tour",
    "GET /api/trajectory",
    "GET /api/update/check",
    "GET /api/usage/summary",
    "GET /api/workspaces",
    "GET /api/workspaces/{id}",
    "PATCH /api/capabilities/{name}",
    "PATCH /api/sessions/{session_id}",
    "PATCH /api/sol/heuristics/{rule_id}",
    "POST /api/agent-teams",
    "POST /api/agent-teams/runs/{run_id}/cancel",
    "POST /api/agent-teams/{team_id}/archive",
    "POST /api/agent-teams/{team_id}/run",
    "POST /api/agents",
    "POST /api/agents/{agent_id}/archive",
    "POST /api/agents/{agent_id}/duplicate",
    "POST /api/agents/{agent_id}/test",
    "POST /api/artifacts/expiry/answer",
    "POST /api/artifacts/{artifact_id}/adopt",
    "POST /api/artifacts/{artifact_id}/favorite",
    "POST /api/ask/answer",
    "POST /api/audio/synthesize",
    "POST /api/audio/transcribe",
    "POST /api/change-sets",
    "POST /api/change-sets/{id}/amend",
    "POST /api/change-sets/{id}/publish",
    "POST /api/change-sets/{id}/review",
    "POST /api/change-sets/{id}/state",
    "POST /api/change-sets/{id}/unpublish",
    "POST /api/channels/discord/start",
    "POST /api/channels/discord/stop",
    "POST /api/channels/discord/token",
    "POST /api/channels/telegram/pair",
    "POST /api/channels/telegram/start",
    "POST /api/channels/telegram/stop",
    "POST /api/channels/telegram/token",
    "POST /api/chat",
    "POST /api/chat/steer",
    "POST /api/chat/stream",
    "POST /api/environment/scan",
    "POST /api/export",
    "POST /api/feedback/thumbs_down",
    "POST /api/feedback/thumbs_up",
    "POST /api/fs/mkdir",
    "POST /api/git/add",
    "POST /api/git/apply",
    "POST /api/git/checkout",
    "POST /api/git/commit",
    "POST /api/import",
    "POST /api/learning/proposals/{pid}/accept",
    "POST /api/learning/proposals/{pid}/dismiss",
    "POST /api/market/install",
    "POST /api/market/plan",
    "POST /api/market/remove",
    "POST /api/market/rollback",
    "POST /api/market/switch",
    "POST /api/mcp/health",
    "POST /api/memory/import",
    "POST /api/memory/migrate",
    "POST /api/memory/store",
    "POST /api/memory/{doc_id}/restore",
    "POST /api/mobile/ping",
    "POST /api/model/providers/probe",
    "POST /api/plugins/master",
    "POST /api/plugins/{plugin_id}/cancel",
    "POST /api/plugins/{plugin_id}/enable",
    "POST /api/project/index",
    "POST /api/project/search",
    "POST /api/sandbox/approve",
    "POST /api/schedule",
    "POST /api/schedule/{job_id}/run",
    "POST /api/sessions",
    "POST /api/sessions/clear",
    "POST /api/sessions/import",
    "POST /api/sessions/prune",
    "POST /api/sessions/sync",
    "POST /api/sessions/{session_id}/activate",
    "POST /api/settings",
    "POST /api/settings/image/test",
    "POST /api/setup/reset",
    "POST /api/setup/skip",
    "POST /api/shell",
    "POST /api/shell/pty",
    "POST /api/skills",
    "POST /api/skills/install",
    "POST /api/skills/install/url",
    "POST /api/skills/{name}/disable",
    "POST /api/skills/{name}/enable",
    "POST /api/tasks",
    "POST /api/tour",
    "POST /api/update/apply",
    "POST /api/vision/analyze",
    "POST /api/vision/base64",
    "POST /api/workspaces",
    "POST /api/workspaces/reap",
    "PUT /api/agent-teams/{team_id}",
    "PUT /api/agents/{agent_id}",
    "PUT /api/artifacts/{artifact_id}/tags",
    "PUT /api/capabilities/subagent-allowlist",
    "PUT /api/memory/provider",
    "PUT /api/memory/{doc_id}",
    "PUT /api/model/provider",
    "PUT /api/plugins/{plugin_id}/enabled",
    "PUT /api/profile",
    "PUT /api/profile/import",
    "PUT /api/settings/image",
    "PUT /api/settings/mcp",
    "PUT /api/settings/persona",
    "PUT /api/settings/security",
    "PUT /api/settings/voice",
    "PUT /api/skills/{name}",
    "PUT /api/tasks/{task_id}",
)

#: The running app's own API explorer: a router-only route, never in the schema.
DOCS_URL = "/api/docs"


def _published_routes() -> set[str]:
    """The live /api/* surface — what a caller can actually reach today."""
    from server.main import create_app

    schema = create_app().openapi()
    return {
        f"{method.upper()} {path}"
        for path, item in schema["paths"].items()
        if path.startswith("/api")
        for method in item
        if method in {"get", "post", "put", "delete", "patch"}
    }


def test_the_frozen_contract_is_well_formed():
    """Guards the table itself, so a malformed edit cannot weaken the freeze."""
    assert FROZEN_ROUTES, "an empty contract freezes nothing"
    assert len(FROZEN_ROUTES) == len(set(FROZEN_ROUTES)), "duplicate route in the contract"
    assert list(FROZEN_ROUTES) == sorted(FROZEN_ROUTES), (
        "keep FROZEN_ROUTES sorted so the delta a failure prints is readable"
    )
    for route in FROZEN_ROUTES:
        method, _, path = route.partition(" ")
        assert method in {"GET", "POST", "PUT", "DELETE", "PATCH"}, route
        assert path.startswith("/api"), route


def test_live_api_surface_matches_the_frozen_contract():
    """Rule 11: the live /api/* surface equals the contract. A route that moved is
    named here — added and removed listed separately, so a rename cannot hide."""
    live = _published_routes()
    frozen = set(FROZEN_ROUTES)
    added = sorted(live - frozen)
    removed = sorted(frozen - live)
    assert not added and not removed, (
        "the /api/* surface moved — rule 11 needs a documented migration, then "
        "re-run this file's enumerator and update FROZEN_ROUTES in the same "
        "commit.\n"
        f"  new (live, not in the contract): {added or 'none'}\n"
        f"  gone (in the contract, not live): {removed or 'none'}"
    )


def test_the_enumerator_is_not_blind():
    """Counter-proof: if the schema walk stopped seeing routes, the equality test
    would pass on two empty sets. The surface must be non-trivial."""
    live = _published_routes()
    assert len(live) >= 100, f"enumerator saw only {len(live)} routes — it went blind"
    assert "GET /api/health" in live


def test_api_docs_endpoint_is_pinned():
    """docs_url is userspace too (clients read /api/docs); it is a router-only
    route, so it lives outside the schema and is named here instead."""
    from server.main import create_app

    assert create_app().docs_url == DOCS_URL
