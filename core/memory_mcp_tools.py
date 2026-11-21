"""
◑ Ephe – MCP surface of the memory (wave D4b)
core/memory_mcp_tools.py

What a connected agent may *ask*, and what every answer states. The surface
is deliberately smaller than the facade underneath it:

  * six tools, three of them writing — `MUTATING_TOOLS` is the gate domain,
    not a guess taken from names.
  * no `clear`, no export/import: a shared door does not empty a memory
    and does not copy it out.
  * every answer names what it answered (ID, scope, provider, write
    mode). "3 results" without IDs would be a search nobody can look up.

A text a model reads is also an instruction: the descriptions here tell an agent
that corrections use `supersedes` instead of laying down a second fact, and that
it is pulled in read-only before it fails.
"""
from __future__ import annotations

from typing import Any, Callable

#: Writing tools. The server gates against this set — a tool that is
#: missing here counts as reading and may not write even when it does.
MUTATING_TOOLS = frozenset({"memory_store", "memory_update", "memory_delete"})

_TOP_K_MAX = 20
_LIMIT_MAX = 500


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "memory_search",
        "description": (
            "Finds what Ephe already knows about this workspace. Returns document IDs "
            "and scores, so a later call can correct or remove the exact fact rather "
            "than adding a competing one."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "What to look for."},
                "top_k": {
                    "type": "integer",
                    "description": f"Max results, 1-{_TOP_K_MAX} (default 5).",
                },
            },
            "required": ["q"],
        },
    },
    {
        "name": "memory_list",
        "description": (
            "Newest-first view of this scope's leading facts, each with its document ID. "
            "Empty here means the scope is empty — memory_stats says which scope that is."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": f"1-{_LIMIT_MAX} (default 50)."},
            },
        },
    },
    {
        "name": "memory_stats",
        "description": (
            "Which brain answers, which scope it serves, how full it is, which retrieval "
            "legs are live, and whether this server may write. Read this before trusting "
            "an empty search."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_store",
        "description": (
            "Remembers a fact for this workspace. Pass `supersedes` with an ID from "
            "memory_search to CORRECT a fact: the old one then stays visible as the "
            "history it is, instead of becoming a second half-truth. Refused unless the "
            "server runs with writes enabled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "One fact, stated plainly."},
                "memory_type": {
                    "type": "string",
                    "description": "Fact | preference | decision | entity (Kepta schema).",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
                "supersedes": {"type": "string", "description": "ID of the fact corrected."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "memory_update",
        "description": (
            "Rewrites one fact in place: same ID, same metadata, new wording. Use "
            "memory_store with `supersedes` when the fact changed; this when it was "
            "only misspelled or badly phrased."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["id", "text"],
        },
    },
    {
        "name": "memory_delete",
        "description": (
            "Takes one fact away by ID. Under the Kepta provider this is a soft delete "
            "the user can undo in Ephe's memory trash; a hard delete is not offered."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
]


def tool_specs() -> list[dict[str, Any]]:
    """Copies of the surface: a client may not bend the definitions."""
    return [dict(tool) for tool in TOOL_SPECS]


def _search(memory: Any, args: dict, allow_write: bool) -> str:
    query = str(args.get("q") or args.get("query") or "").strip()
    if not query:
        raise ValueError("'q' must not be empty — search needs a question.")
    top_k = _clamp_int(args.get("top_k"), 5, 1, _TOP_K_MAX)
    hits = memory.search(query=query, top_k=top_k)
    if not hits:
        return (
            f"No memory entry matches {query!r} in scope {memory.collection_name} "
            f"({memory.count()} leading facts). memory_stats says which brain answered."
        )
    lines = [f"{len(hits)} match(es) for {query!r}:"]
    for hit in hits:
        meta = hit.get("metadata") or {}
        kind = meta.get("memory_type") or meta.get("source") or ""
        suffix = f" [{kind}]" if kind else ""
        lines.append(f"- ({hit.get('score', 0.0):.2f}) {hit['id']}: {hit['text']}{suffix}")
    return "\n".join(lines)


def _list(memory: Any, args: dict, allow_write: bool) -> str:
    limit = _clamp_int(args.get("limit"), 50, 1, _LIMIT_MAX)
    rows = memory.list_all(limit=limit)
    if not rows:
        return f"Scope {memory.collection_name} is empty."
    lines = [
        f"{len(rows)} entry(ies) in {memory.collection_name} "
        f"(provider {memory.provider_kind}):"
    ]
    for row in rows:
        lines.append(f"- {row['id']}: {row['text']}")
    return "\n".join(lines)


def _stats(memory: Any, args: dict, allow_write: bool) -> str:
    stats = memory.provider_stats()
    lines = [
        f"provider: {stats.get('provider', memory.provider_kind)} ({stats.get('reason', '')})",
        f"scope: {memory.collection_name}",
        f"entries: {stats.get('total', memory.count())} (in trash: {stats.get('deleted', 0)})",
        "retrieval legs: "
        f"vector: {'on' if stats.get('vector_leg', True) else 'off'}, "
        f"lexical: {'on' if stats.get('lexical_leg') else 'off'}",
        # A model that does not know whether it may write plans the write operation
        # and then wonders about the refusal. "What am I here" belongs in the surface.
        f"write mode: {'enabled' if allow_write else 'read-only'}",
    ]
    db_path = stats.get("db_path")
    if db_path:
        lines.append(f"source db: {db_path}")
    return "\n".join(lines)


def _store(memory: Any, args: dict, allow_write: bool) -> str:
    text = str(args.get("text") or "").strip()
    if not text:
        raise ValueError("text must not be empty — Ephe does not remember blank lines.")
    supersedes = str(args.get("supersedes") or "").strip() or None
    options = {
        key: value
        for key, value in (("memory_type", args.get("memory_type")), ("tags", args.get("tags")))
        if value
    }
    # source=mcp is the proof of origin: the surface shows where a fact comes from,
    # and a user can take foreign entries away again.
    doc_id = memory.store(text, metadata={"source": "mcp"}, supersedes=supersedes, **options)
    if supersedes:
        return f"Corrected {supersedes}: the leading fact is now {doc_id}."
    return f"Stored {doc_id} in {memory.collection_name}."


def _update(memory: Any, args: dict, allow_write: bool) -> str:
    doc_id = str(args.get("id") or "").strip()
    text = str(args.get("text") or "").strip()
    if not doc_id:
        raise ValueError("'id' must not be empty.")
    if not text:
        raise ValueError("text must not be empty — use memory_delete to remove a fact.")
    memory.update(doc_id, text)
    return f"Updated {doc_id} in place (same ID, metadata kept)."


def _delete(memory: Any, args: dict, allow_write: bool) -> str:
    doc_id = str(args.get("id") or "").strip()
    if not doc_id:
        raise ValueError("'id' must not be empty.")
    memory.delete(doc_id)
    where = (
        "Ephe's memory trash"
        if memory.provider_kind != "chroma"
        else "this provider, permanently"
    )
    return f"Removed {doc_id}. Undo it in {where}."


_HANDLERS: dict[str, Callable[[Any, dict, bool], str]] = {
    "memory_search": _search,
    "memory_list": _list,
    "memory_stats": _stats,
    "memory_store": _store,
    "memory_update": _update,
    "memory_delete": _delete,
}


def is_known(name: str) -> bool:
    return name in _HANDLERS


def call_tool(name: str, memory: Any, args: dict, allow_write: bool) -> tuple[str, bool]:
    """A handler call, always as text + error flag — never as a traceback.

    The agent sees a cause in one sentence ('not found', 'must not be
    empty') instead of guessing from an exception class what the scope was.
    """
    try:
        return _HANDLERS[name](memory, args, allow_write), False
    except KeyError as exc:
        return f"Memory entry {exc} not found in this scope.", True
    except (ValueError, TypeError) as exc:
        return f"Invalid arguments: {exc}", True
