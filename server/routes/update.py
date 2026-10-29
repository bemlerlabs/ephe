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

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import update_apply, update_check

XHR_HEADER = "X-Requested-With"

router = APIRouter(tags=["update"])


@router.get("/update/check")
def get_update_check(force: bool = False) -> dict:
    """Is a newer release version available? Fail-soft, TTL-cached.

    force=1 is what a user's click sends: a person asking now deserves a live
    answer, not a cached one. The background poll keeps the cache."""
    return update_check.check_for_update(force=force)


class UpdateApplyRequest(BaseModel):
    confirm: str = ""


@router.post("/update/apply")
def post_update_apply(body: UpdateApplyRequest, request: Request) -> dict:
    """Pull the newest commits and reinstall, on the user's click.

    Two gates, because this body starts a `git pull` and an installer: the
    browser must send the same `X-Requested-With` marker the other process
    routes demand, and the body must carry the confirm word."""
    if request.headers.get(XHR_HEADER, "") != "XMLHttpRequest":
        raise HTTPException(status_code=403, detail="missing X-Requested-With")
    if body.confirm != "update":
        raise HTTPException(status_code=400, detail="missing confirm: update")
    if not update_check.update_check_enabled():
        raise HTTPException(status_code=403, detail="update check is switched off")
    return update_apply.apply_update()
