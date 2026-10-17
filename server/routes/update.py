"""
◑ Ephe – update-check route (update-experience wave)
server/routes/update.py

GET /api/update/check → contract from core.update_check (fail-soft, TTL-cached,
switchable off through the appearance.update_check deep setting).

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

from fastapi import APIRouter

from core import update_check

router = APIRouter(tags=["update"])


@router.get("/update/check")
def get_update_check(force: bool = False) -> dict:
    """Is a newer release version available? Fail-soft, TTL-cached.

    force=1 is what a user's click sends: a person asking now deserves a live
    answer, not a cached one. The background poll keeps the cache."""
    return update_check.check_for_update(force=force)
