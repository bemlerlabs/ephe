"""
◑ Ephe – update-check route (update-experience wave)
server/routes/update.py

GET /api/update/check  → contract from core.update_check (fail-soft, TTL-cached,
switchable off through the appearance.update_check deep setting).
POST /api/update/apply → fast-forward this checkout and reinstall it
(core.update_apply), for the merges a release has not been cut from yet.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core import update_apply, update_check

router = APIRouter(tags=["update"])


@router.get("/update/check")
def get_update_check(force: bool = False) -> dict:
    """Is a newer release version available? Fail-soft, TTL-cached.

    force=1 is what a user's click sends: a person asking now deserves a live
    answer, not a cached one. The background poll keeps the cache."""
    return update_check.check_for_update(force=force)


@router.post("/update/apply")
def post_update_apply(body: dict) -> dict:
    """Pull the newest commits and reinstall, on the user's click.

    The body carries `confirm: "update"`: a mutation this large is never the
    result of a stray POST. Origin and host are already checked by the security
    middleware for every non-GET request."""
    if str(body.get("confirm") or "") != "update":
        raise HTTPException(status_code=400, detail="missing confirm: update")
    if not update_check.update_check_enabled():
        raise HTTPException(status_code=403, detail="update check is switched off")
    return update_apply.apply_update()
