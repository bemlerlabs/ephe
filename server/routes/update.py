"""
◑ Ephe – update-check route (update-experience wave)
server/routes/update.py

GET /api/update/check  → contract from core.update_check (fail-soft, TTL-cached,
switchable off through the appearance.update_check deep setting).
POST /api/update/apply → fast-forward this checkout to main and reinstall it
(core.update_apply.apply_update), for the merges a release has not been cut
from yet. This is the desktop/PWA commit channel.
POST /api/update/release → move this checkout to the newest release tag and
reinstall it (core.update_apply.apply_release), the PWA's release channel.
POST /api/update/install → the environment step alone, for the desktop shell
that has already moved the checkout and must not leave the tree newer than the
packages around it.

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
    """Is a newer release — or, on the commit channel, a newer merge — available?

    Fail-soft and TTL-cached per channel.

    force=1 is what a user's click sends: a person asking now deserves a live
    answer, not a cached one. The background poll keeps the cache."""
    return update_check.check_for_update(force=force)


class UpdateConfirmRequest(BaseModel):
    confirm: str = ""


@router.post("/update/apply")
def post_update_apply(body: UpdateConfirmRequest, request: Request) -> dict:
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


@router.post("/update/release")
def post_update_release(body: UpdateConfirmRequest, request: Request) -> dict:
    """Move the checkout to the newest release tag, on the user's click.

    The same two gates as the commit route: the browser marker and a confirm
    word. The tree moves to the tag, never to the branch tip, so a release
    channel does not become the commit channel by accident."""
    if request.headers.get(XHR_HEADER, "") != "XMLHttpRequest":
        raise HTTPException(status_code=403, detail="missing X-Requested-With")
    if body.confirm != "release":
        raise HTTPException(status_code=400, detail="missing confirm: release")
    if not update_check.update_check_enabled():
        raise HTTPException(status_code=403, detail="update check is switched off")
    return update_apply.apply_release()


@router.post("/update/install")
def post_update_install(body: UpdateConfirmRequest, request: Request) -> dict:
    """Refresh the environment from the tree as it stands, on the shell's call.

    The desktop updater replaces the app bundle and the shell then moves the
    checkout, so the code can be newer than the packages beside it. This route
    is that one step, and it is deliberately not gated by
    `appearance.update_check`: a tree the shell has already moved has to get its
    environment, or the refusal leaves the installation half-updated. The two
    gates the apply route demands are the gates here too.
    """
    if request.headers.get(XHR_HEADER, "") != "XMLHttpRequest":
        raise HTTPException(status_code=403, detail="missing X-Requested-With")
    if body.confirm != "install":
        raise HTTPException(status_code=400, detail="missing confirm: install")
    return update_apply.reinstall()
