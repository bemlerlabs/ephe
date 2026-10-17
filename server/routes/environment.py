"""
◑ Ephe – environment route (B-wave B2/B3, docs/EXTENSIONS_V2_PLAN.md)
server/routes/environment.py

POST /api/environment/scan → opt-in detection of the agent tools already present.

The scan reads configuration files in the user's home directory — that is a
privacy-relevant operation, so it runs ONLY on an explicit POST (no GET, no
auto-poll on page load; GET answers 405). The data comes from
core.environment_mirror (read-only, secret-free, fail-soft).

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

from fastapi import APIRouter

from core.environment_mirror import scan

router = APIRouter(tags=["environment"])


@router.post("/environment/scan")
def post_environment_scan() -> dict:
    """Opt-in scan: detected tools + models (no secrets) for onboarding
    and the settings environment section. Fail-soft — never raises."""
    try:
        tools = scan()
    except Exception:  # noqa: BLE001 — the scan is best effort, never a 500.
        tools = []
    installed = [t for t in tools if t.get("installed")]
    return {
        "tools": tools,
        "summary": {
            "installed": len(installed),
            "with_models": [t["tool"] for t in installed if t.get("models")],
        },
    }
