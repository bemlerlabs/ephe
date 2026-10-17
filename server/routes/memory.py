"""server/routes/memory.py – GET /api/memory/search + POST /api/memory/store"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Literal, TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.auto_memory import source_labels, source_of
from core.memory import Memory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Memory"])

_T = TypeVar("_T")

#: Which stores keep a deleted entry around. The trash routes report this
#: instead of promising a recovery the active store cannot deliver: the retired
#: store deleted finally (walkthrough 2026-10-12, finding 1 — the page promised
#: "this is where what Ephe forgot ends up" while nothing could ever arrive, and
#: its restore control had nothing to call).
_TRASH_PROVIDERS = frozenset({"kepta"})


def _keeps_trash(memory: Memory) -> bool:
    """Whether the active store can bring a deleted entry back.

    The capability fact stays here, next to the store API: `memory_stats` reports
    it. The trash *routes* that act on it live in `memory_trash.py`.
    """
    return memory.provider_kind in _TRASH_PROVIDERS


@lru_cache(maxsize=1)
def _get_memory() -> Memory:
    """Returns the memory singleton with the configured path (testable via ENV)."""
    path = os.environ.get("EPHE_MEMORY_DIR")
    return Memory(persist_dir=path) if path else Memory()


def _unavailable(kind: str, exc: Exception) -> HTTPException:
    """503 + the stable `upstream_error` code, for a store that did not answer.

    The cause is logged and only its class name reaches the surface: the prose a
    surface prints has to be English (AGENTS.md), while provider messages are
    whatever the module behind them wrote."""
    logger.warning("memory store '%s' did not answer: %s", kind, exc)
    return HTTPException(
        status_code=503,
        detail=f"memory store '{kind}' did not answer ({type(exc).__name__})",
    )


def _read(op: Callable[[Memory], _T]) -> _T:
    """Runs a store read. Failure is an answer of its own, never an empty result.

    Rows are not sent at all when the store cannot be read: a surface that reads
    `entries` then has nothing to mistake for "the user has no memories" (B1)."""
    try:
        memory = _get_memory()
    except Exception as exc:
        raise _unavailable("unknown", exc) from exc
    try:
        return op(memory)
    except Exception as exc:
        raise _unavailable(memory.provider_kind, exc) from exc


# Pydantic Models

class MemoryStoreRequest(BaseModel):
    text: str
    metadata: dict = {}
    #: Wave D (additive): the write intent of the Kepta schema. One field per
    #: line, so a body like before wave D still just stores unchanged.
    memory_type: str | None = None
    tags: list[str] | None = None
    supersedes: str | None = None


class MemoryResult(BaseModel):
    #: Document id — additive (R40); without it, deleting or editing straight from a
    #: search hit was impossible.
    id: str = ""
    text: str
    score: float
    metadata: dict = {}


class MemoryEntry(BaseModel):
    id: str
    text: str
    metadata: dict = {}


class MemoryListResponse(BaseModel):
    entries: list[MemoryEntry]
    total: int


class MemorySearchResponse(BaseModel):
    results: list[MemoryResult]
    query: str


class MemoryStoreResponse(BaseModel):
    stored: bool
    #: Wave D (additive): id of the leading entry — without it a UI cannot attach a
    #: correction to the right fact (`supersedes`).
    id: str = ""


class MemoryStatsResponse(BaseModel):
    total: int
    #: R40 (additive): name of the collection actually read. Since the
    #: workspace scoping (W16) "ephe_memory_{hash}" is not negotiable —
    #: without this the UI looks as if it showed one global pool.
    scope: str = ""
    #: Wave D (additive): which brain is answering. Two stores behind one
    #: API are only trustworthy when the surface can say which
    #: one is speaking — and why.
    provider: str = "kepta"
    #: R2-A: "which brain" without "why" is half of the story. The reason comes from
    #: the provider resolution itself (core/memory.py:360), not from the UI.
    reason: str = ""
    #: The vector leg is optional: without a local embedding model BM25 and
    #: entities carry the search. Hiding that would be a broken memory with a green UI.
    vector_leg: bool = True
    lexical_leg: bool = False
    deleted: int = 0
    #: D5's trash, as a capability rather than as a hope: `deleted` staying 0 is
    #: only honest while the surface can say that this store keeps nothing to
    #: restore (walkthrough 2026-10-12, finding 1).
    restore_supported: bool = False
    #: The origin vocabulary of the store: every source value a row can carry,
    #: with the label to print for it. The memory page's own label map knew only
    #: `auto_memory` and `compaction`, so the tool-written rows (`agent`) showed
    #: no origin at all (walkthrough 2026-10-12: 32 rows, 29 chips).
    sources: dict[str, str] = {}


# Routes

@router.get("/memory/stats", response_model=MemoryStatsResponse)
async def memory_stats() -> MemoryStatsResponse:
    """
    Number of stored vectors — for the memory statistics in the PWA.

    `total: 0` is only ever the count of a store that answered; a store that did
    not answer is a 503 here as well.
    """

    def read(memory: Memory) -> MemoryStatsResponse:
        stats = memory.provider_stats()
        return MemoryStatsResponse(
            total=memory.count(),
            scope=memory.collection_name,
            provider=stats.get("provider", memory.provider_kind),
            reason=str(stats.get("reason") or memory.provider_reason or ""),
            vector_leg=bool(stats.get("vector_leg", True)),
            lexical_leg=bool(stats.get("lexical_leg", False)),
            deleted=int(stats.get("deleted", 0) or 0),
            restore_supported=_keeps_trash(memory),
            sources=source_labels(),
        )

    return _read(read)


@router.delete("/memory")
async def memory_clear() -> dict:
    """
    Deletes ALL memory entries (G5: 'Memory leeren' in the PWA settings).
    """
    memory = _get_memory()
    memory.clear()
    return {"cleared": True}

@router.get("/memory/list", response_model=MemoryListResponse)
async def memory_list(limit: int = 100) -> MemoryListResponse:
    """Lists all memory entries with ids (newest first)."""
    raw = _read(lambda memory: memory.list_all(limit=limit))
    entries = [MemoryEntry(id=e["id"], text=e["text"], metadata=e.get("metadata", {})) for e in raw]
    return MemoryListResponse(entries=entries, total=len(entries))


# Wave D: provider switch and migration
# Declared before /memory/{doc_id}: FastAPI matches in registration order,
# a later /memory/provider would swallow the path parameter as doc_id
# and answer with a 422 for a body whose "text" field is missing.

class MemoryProviderRequest(BaseModel):
    #: Literal instead of an if-branch: a typo (postgres, mem0, kepta2) becomes
    #: a 422, not a puzzling default brain.
    provider: Literal["kepta", "kepta-bridge"]


def _rebind_memory_instances() -> None:
    """Clears the route and the facade cache at the same time, otherwise the UI keeps
    talking to the old brain after the switch."""
    _get_memory.cache_clear()
    Memory.reset_scoped_instances()


@router.put("/memory/provider", response_model=dict)
async def set_memory_provider(request: MemoryProviderRequest) -> dict:
    """Writes the storage choice as a readable record and puts it into effect."""
    from core.memory_provider import write_provider_record

    write_provider_record(request.provider, reason="settings")
    _rebind_memory_instances()
    memory = _get_memory()
    return {
        "provider": memory.provider_kind,
        "reason": memory.provider_reason,
        "scope": memory.collection_name,
    }


class MemoryMigrateRequest(BaseModel):
    #: Look first, then copy: the dry run is the point where a
    #: user decides whether their memory should move.
    dry_run: bool = True


@router.post("/memory/migrate", response_model=dict)
async def migrate_memory(request: MemoryMigrateRequest) -> dict:
    """Reports how a retired store is read now: offline, in its own environment.

    The copy itself cannot happen in this process — it needs the package the
    product no longer carries — so the answer names the command that does it.
    """
    from core.memory_provider import migrate_chroma_to_kepta

    report = migrate_chroma_to_kepta(dry_run=request.dry_run)
    if not request.dry_run and report["imported"]:
        _rebind_memory_instances()
    return report


# The trash surface (GET /memory/deleted, POST /memory/{doc_id}/restore) lives in
# `memory_trash.py`: it reports `_keeps_trash` and its explanation, attached to
# this router's app in `server/main.py`.


@router.delete("/memory/{doc_id}")
async def memory_delete(doc_id: str) -> dict:
    """Deletes a single memory entry by id."""
    memory = _get_memory()
    try:
        memory.delete(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"memory entry '{doc_id}' not found.")
    return {"deleted": doc_id}


class MemoryUpdateRequest(BaseModel):
    text: str


@router.put("/memory/{doc_id}")
async def memory_update(doc_id: str, request: MemoryUpdateRequest) -> dict:
    """R40: edits an entry inline (corrected fact wording,
    typo, outdated statement). Re-embeds the text; id and metadata
    are kept. A new path, no existing signature changed."""
    memory = _get_memory()
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="memory text must not be empty.")
    try:
        memory.update(doc_id, request.text)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"memory entry '{doc_id}' not found.")
    return {"updated": doc_id}


@router.get("/memory/search", response_model=MemorySearchResponse)
async def memory_search(q: str, top_k: int = 5) -> MemorySearchResponse:
    """
    Semantic search in the persistent memory.
    Returns an empty list when a store that answered holds no match, and 503 when
    no store answered.
    """
    raw = _read(lambda memory: memory.search(query=q, top_k=top_k))
    results = [
        MemoryResult(
            id=r.get("id", ""),
            text=r["text"],
            score=r["score"],
            metadata=r.get("metadata", {}),
        )
        for r in raw
    ]
    return MemorySearchResponse(results=results, query=q)


@router.post("/memory/store", response_model=MemoryStoreResponse)
async def memory_store(request: MemoryStoreRequest) -> MemoryStoreResponse:
    """Stores a text in the persistent memory.

    `supersedes` is the write gate (wave D): the write corrects an existing
    fact instead of forgetting it or listing it twice. An id without a target fact is a
    404, not a silent add."""
    memory = _get_memory()
    options: dict = {}
    if request.memory_type:
        options["memory_type"] = request.memory_type
    if request.tags:
        options["tags"] = request.tags
    metadata = dict(request.metadata or {})
    # Every stored entry carries an origin: a body without one would put a row
    # in the store that the page cannot label at all (walkthrough 2026-10-12).
    metadata["source"] = source_of(metadata)
    try:
        doc_id = memory.store(
            text=request.text, metadata=metadata,
            supersedes=request.supersedes, **options,
        )
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"memory entry '{request.supersedes}' not found."
        )
    return MemoryStoreResponse(stored=True, id=doc_id or "")


# R19: memory export/import (bulk roundtrip)

class MemoryImportRequest(BaseModel):
    entries: list[MemoryEntry]


@router.get("/memory/export")
async def export_memory() -> dict:
    """All entries as JSON (backup/move) — deliberately without embedding vectors
    (the import re-embeds through the active embedding config)."""
    memory = _get_memory()
    entries = memory.list_all(limit=10000)
    return {"entries": entries, "total": len(entries)}


@router.post("/memory/import", status_code=201)
async def import_memory(request: MemoryImportRequest) -> dict:
    """Imports entries from an export JSON. Duplicates are NOT
    filtered (the import is deliberately literal — auto-memory dedupes on its own).
    The origin is the exception: an imported body without one is stored under the
    default label, so an import cannot leave unlabelled rows behind."""
    memory = _get_memory()
    imported = 0
    for entry in request.entries:
        if not (entry.text or "").strip():
            continue
        metadata = dict(entry.metadata or {})
        metadata["source"] = source_of(metadata)
        memory.store(entry.text, metadata=metadata)
        imported += 1
    return {"imported": imported, "total": memory.count()}
