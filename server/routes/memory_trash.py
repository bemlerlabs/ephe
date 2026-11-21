"""server/routes/memory_trash.py – the trash surface: what was taken away, and
what can actually come back (D5).

Split out of `memory.py` when the trash capability (walkthrough 2026-10-12,
finding 1) pushed that module past the 400-line wall of the architecture gate.
The seam is coherent rather than mechanical: `memory.py` owns the store API and
the fact *whether* a store keeps a deleted entry, this module owns what the
surface says about it — listing, restoring, and the line that explains an empty
trash under a store that deletes finally.

The paths are unchanged. `server/main.py` attaches this router to the app next
to `memory.router`, so `/api/memory/deleted` and `/api/memory/{id}/restore` stay
where the clients already look (playbook rule 11: userspace must not break).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.routes.memory import (
    MemoryEntry,
    MemoryListResponse,
    _get_memory,
    _keeps_trash,
    _read,
)

router = APIRouter(tags=["Memory"])


def _no_trash_detail(memory) -> str:
    """One honest line for the surface that has to explain an empty trash."""
    return (
        f"the active store '{memory.provider_kind}' deletes finally: "
        "nothing is kept to restore."
    )


class MemoryTrashResponse(MemoryListResponse):
    #: The promise of the trash, told honestly: whether the active store keeps a
    #: deleted entry at all. An empty `entries` under a store that deletes
    #: finally is the truth about that store, not a fluke — a surface that reads
    #: `restore_supported` never offers a restore that cannot work
    #: (walkthrough 2026-10-12, finding 1).
    restore_supported: bool = False
    #: Why not, in one line, for the surface that has to say it.
    detail: str = ""


@router.get("/memory/deleted", response_model=MemoryTrashResponse)
async def memory_deleted_list(limit: int = 100) -> MemoryTrashResponse:
    """D5: the trash bin. What the user took away they must be able to see and
    get back — and where the store keeps nothing, the answer says so instead of
    leaving an empty list to look like a quiet trash (under Chroma deleting is
    final; under Kepta the entry waits with its `deleted_at`)."""
    memory = _get_memory()
    raw = _read(lambda store: store.list_deleted(limit=limit))
    entries = [MemoryEntry(id=e["id"], text=e["text"], metadata=e.get("metadata", {})) for e in raw]
    supported = _keeps_trash(memory)
    return MemoryTrashResponse(
        entries=entries,
        total=len(entries),
        restore_supported=supported,
        detail="" if supported else _no_trash_detail(memory),
    )


@router.post("/memory/{doc_id}/restore")
async def memory_restore(doc_id: str) -> dict:
    """Brings back one soft-deleted entry — id and metadata stay as they
    were."""
    memory = _get_memory()
    if not _keeps_trash(memory):
        # 409 for a valid ID on a store that cannot restore: a "not found"
        # would read as "you deleted the wrong thing" and hide that this store
        # never kept anything to bring back (walkthrough 2026-10-12, finding 1).
        raise HTTPException(status_code=409, detail=_no_trash_detail(memory))
    try:
        memory.restore(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"deleted memory entry '{doc_id}' not found.")
    return {"restored": doc_id}
