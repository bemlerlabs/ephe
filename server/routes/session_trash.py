"""server/routes/session_trash.py — the trash surface for chat sessions.

Split out beside `sessions.py` the way `memory_trash.py` was split out of
`memory.py`: the trash is a coherent capability with its own storage rules
(held in `core.session_trash`), and growing the sessions module past the
400-line wall of the architecture gate would bury it there.

The router is attached to the sessions router at its head, before the
`{session_id}` family is declared: FastAPI answers in registration order, and
`GET /api/sessions/trash` registered later would be swallowed by
`GET /api/sessions/{session_id}` and answer as a session that does not exist.
`DELETE /api/sessions/{id}` stays the final word it always was — this surface
is additive, the way the mirror family was additive before it.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import session_trash
from server.refusals import Refused

router = APIRouter(tags=["Sessions"])


class EmptyTrashRequest(BaseModel):
    #: Count what an emptying would free without freeing it, the way the prune
    #: route lets a surface show its number before the click.
    dry_run: bool = Field(default=False)


@router.get("/sessions/trash")
async def sessions_trash_list(limit: int = 100) -> dict:
    """What the reader took away, newest first, with the run it waits in."""
    return session_trash.list_trash(limit=limit)


@router.post("/sessions/{session_id}/trash")
async def session_to_trash(session_id: str) -> dict:
    """Move one live session into the trash. Undo is one restore away, at any age."""
    result = session_trash.move_sessions_to_trash([session_id])
    if not result["trashed"]:
        raise Refused("session_not_found", session_id=session_id)
    return {
        "trashed": result["trashed"][0],
        "run": result["run"],
        "trashed_at": result["trashed_at"],
        "bytes_moved": result["bytes_moved"],
    }


@router.post("/sessions/trash/{session_id}/restore")
async def session_from_trash(session_id: str, run: str | None = None) -> dict:
    """Bring one trashed session back, newest trash first unless a run names it."""
    result = session_trash.restore_session(session_id, run=run)
    if result["outcome"] == "missing":
        raise Refused("session_not_in_trash", session_id=session_id)
    if result["outcome"] == "conflict":
        raise Refused("session_exists", session_id=session_id)
    return {"restored": result["session_id"], "run": result["run"]}


@router.post("/sessions/trash/empty")
async def sessions_trash_empty(body: EmptyTrashRequest | None = None) -> dict:
    """Delete finally. The one call that forgets a waiting session's consent row."""
    dry_run = bool(body and body.dry_run)
    result = session_trash.empty_trash(dry_run=dry_run)
    if not result["deleted"]:
        raise Refused("trash_empty")
    return result
