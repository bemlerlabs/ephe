"""server/routes/search.py – GET /api/search (R25).

Session full-text search (SQLite FTS5, core.session_search). The UI entry point:
the command palette with the ``inhalt:…`` prefix.  # language-gate: ignore (quoted palette prefix string — a literal this document describes, not prose)
"""
from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Query

from core.session_search import search_messages

router = APIRouter(tags=["Search"])


@router.get("/search")
def search_sessions(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    role: Literal["user", "assistant", "system"] | None = None,
) -> dict:
    """Full-text search across all sessions (messages + titles)."""
    start = time.perf_counter()
    results = search_messages(q, limit=limit)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if role:
        results = [r for r in results if r["role"] == role]
    return {
        "query": q,
        "results": results,
        "total": len(results),
        "elapsed_ms": round(elapsed_ms, 2),
    }
