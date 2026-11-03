"""server/routes/device.py — what this device keeps, and the one gesture that clears it.

`core/persistence.py` declares every entry Ephe writes beside the app, and `ephe device`
has been reading that declaration from a terminal since F1. The app had no door to the
same answer: a person who wanted to see what stays on the machine, or to forget it, had
to open one. These two routes carry the declaration to the settings surface — the
listing as read, and the clear through `core.persistence.forget`, dry run first, with
the rows the declaration marks kept refused by name.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import persistence
from server.refusals import Refused

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Device"])


class ForgetRequest(BaseModel):
    """What to clear, and whether the run may unlink.

    ``dry_run`` defaults to true: the promise the CLI already keeps — nothing leaves
    the folder until the caller asks with an explicit apply. ``names`` scopes the run
    to rows a caller asked for; empty means every entry the declaration marks
    forgettable.
    """

    names: list[str] = Field(default_factory=list)
    dry_run: bool = True


@router.get("/device")
async def device_state() -> dict:
    """The declaration read against this folder: each entry present, its kind, what it
    holds and how many bytes it takes, the total between them, and the names the folder
    keeps that no row declares."""
    rows = [row for row in persistence.listing() if row["present"]]
    info = persistence.summary()
    return {
        "root": info["root"],
        "declared": info["declared"],
        "present": info["present"],
        "forgettable": sum(1 for row in rows if row["forgettable"]),
        "entries": rows,
        "total_bytes": sum(int(row["bytes"]) for row in rows),
        "unnamed": info["unnamed"],
    }


def _refuse_scoped(names: list[str]) -> None:
    """Turn a scoped request down whole before anything is unlinked.

    Two ways a name leaves the declaration's reach: no row carries it, or its row marks
    it kept. Either is refused with its own code, so the surface answers in the reader's
    language and the run never starts halfway.
    """
    if not names:
        return
    by_name = {entry.name: entry.forgettable for entry in persistence.EPHE_PERSISTENCE}
    undeclared = [name for name in names if name not in by_name]
    if undeclared:
        raise Refused("device_forget_undeclared", names=", ".join(undeclared))
    kept = [name for name in names if not by_name[name]]
    if kept:
        raise Refused("device_forget_kept", names=", ".join(kept))


@router.post("/device/forget")
async def device_forget(request: ForgetRequest) -> dict:
    """Clear through the declaration: forgettable rows go when the caller applies, kept
    rows and undeclared leftovers stay, and the answer names each list."""
    _refuse_scoped(request.names)
    result = persistence.forget(dry_run=request.dry_run, names=request.names or None)
    logger.info(
        "device forget: removed=%s kept=%s dry_run=%s",
        len(result["removed"]), len(result["kept"]), request.dry_run,
    )
    return {**result, "dry_run": request.dry_run}
