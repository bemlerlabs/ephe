'''server/routes/hooks.py – I6-4: the read-only page for user hooks.

The Hooks section shows what `~/.ephe/hooks.json` really contains, and what the
core makes of it: the events with their commands plus the last hook runs from
the audit log. Nothing is written here — a hook is a command that inherits
Ephe's process rights, and whether it runs is decided by the switch in the
registry (`hooks.enabled`, read by core/user_hooks.py), not by this endpoint.
'''
from __future__ import annotations

from fastapi import APIRouter

from core.user_hooks import hooks_view

router = APIRouter(tags=["Hooks"])


@router.get("/settings/hooks")
async def get_hooks() -> dict:
    """Switch, file, events with their hooks, last runs (newest first)."""
    return hooks_view()
