"""Project index routes: build the workspace index, report progress, search it.

Indexing runs off the event loop (a thread) and reports into an in-memory job
record; the status route is what the pill and the dialog poll. The index itself
is the durable artefact — `<root>/.ephe/index.db` — so a restarted server reads
the same rows without re-parsing unchanged files.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.semindex.store import (
    SemanticStore,
    index_database,
    iter_source_files,
    read_ignore_patterns,
)

router = APIRouter()

MAX_SEARCH_LIMIT = 25
MAX_SPAN_CHARS = 1200


@dataclass
class _Job:
    root: str
    state: str = "indexing"
    indexed: int = 0
    total: int = 0
    files: int = 0
    symbols: int = 0
    removed: int = 0
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "root": self.root,
            "state": self.state,
            "indexed": self.indexed,
            "total": self.total,
            "files": self.files,
            "symbols": self.symbols,
            "removed": self.removed,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }


_jobs: dict[str, _Job] = {}


class IndexRequest(BaseModel):
    """The body names no path: indexing always covers the configured workspace."""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    kind: str | None = None
    limit: int = Field(default=10, ge=1, le=MAX_SEARCH_LIMIT)


def _workspace_root() -> Path:
    from core.workspace_rules import resolve_workspace_dir

    return Path(resolve_workspace_dir()).resolve()


def _index_root() -> Path:
    """The only tree this route indexes. A caller cannot name another one."""
    root = _workspace_root()
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="the workspace is not a directory")
    return root


def _index_sync(root: Path, job: _Job) -> None:
    database = index_database(root)
    database.parent.mkdir(parents=True, exist_ok=True)
    store = SemanticStore(database)
    try:
        files = iter_source_files(root, read_ignore_patterns(root))
        job.total = len(files)
        for position, file in enumerate(files, 1):
            store.index_file(file)
            job.indexed = position
        job.removed = store.prune_missing(root, {str(file) for file in files})
        job.files = store.file_count()
        job.symbols = store.symbol_count()
    finally:
        store.close()


def _start_thread(root: Path, job: _Job) -> None:
    """A worker thread owns the job, so a finished request cannot cancel it."""
    started = time.monotonic()
    try:
        _index_sync(root, job)
        job.state = "ready"
    except Exception as exc:
        job.state = "error"
        job.error = str(exc)
    finally:
        job.finished_at = time.time()
        job.duration_ms = int((time.monotonic() - started) * 1000)


def _status_from_disk(root: Path) -> dict:
    database = index_database(root)
    if not database.exists():
        return {"root": str(root), "state": "idle", "files": 0, "symbols": 0}
    store = SemanticStore(database)
    try:
        return {
            "root": str(root),
            "state": "ready",
            "files": store.file_count(),
            "symbols": store.symbol_count(),
            "languages": store.counts_by_language(),
            "kinds": store.counts_by_kind(),
        }
    finally:
        store.close()


@router.post("/project/index", tags=["Project"])
async def start_index(request: IndexRequest) -> dict:
    root = _index_root()
    key = str(root)
    existing = _jobs.get(key)
    if existing is not None and existing.state == "indexing":
        return existing.as_dict()
    job = _Job(root=key)
    _jobs[key] = job
    threading.Thread(target=_start_thread, args=(root, job), daemon=True).start()
    return job.as_dict()


@router.get("/project/index/status", tags=["Project"])
async def index_status() -> dict:
    root = _index_root()
    job = _jobs.get(str(root))
    if job is not None:
        return job.as_dict()
    return _status_from_disk(root)


def _read_span(file: str, start: int, end: int) -> str:
    try:
        lines = Path(file).read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        return ""
    text = "\n".join(lines[max(0, start - 1):max(start, end)])
    return text[:MAX_SPAN_CHARS]


@router.post("/project/search", tags=["Project"])
async def search_index(request: SearchRequest) -> dict:
    root = _index_root()
    database = index_database(root)
    if not database.exists():
        return {"status": "not_indexed", "root": str(root), "hits": []}
    store = SemanticStore(database)
    try:
        hits = store.search(request.query, kind=request.kind, limit=request.limit)
        for hit in hits:
            hit["source"] = _read_span(hit["file"], hit["start"], hit["end"])
            try:
                hit["relative"] = Path(hit["file"]).resolve().relative_to(root).as_posix()
            except (ValueError, OSError):
                hit["relative"] = hit["file"]
    finally:
        store.close()
    return {"status": "ready", "root": str(root), "hits": hits}
