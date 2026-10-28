"""`query_codebase`: the agent's reader for the workspace index."""
from __future__ import annotations

from pathlib import Path

from core.semindex.project_map import project_map_for_workspace
from core.semindex.store import SemanticStore, index_database, index_workspace

MAX_HITS = 8
MAX_SPAN_CHARS = 800

CODEBASE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "query_codebase",
            "description": (
                "Search the workspace's local syntax index for a class, function, "
                "interface, struct, trait, module or file before reading whole files. "
                "Returns symbol locations with a short source span. kind narrows the "
                "results to one symbol kind (class, function, method, interface, "
                "struct, trait, import, module)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Symbol name, qualified name, or part of a file path.",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional symbol kind to filter by.",
                    },
                },
                "required": ["query"],
            },
        },
    }
]


def _workspace_root() -> Path:
    from core.workspace_rules import resolve_workspace_dir

    return Path(resolve_workspace_dir()).resolve()


def _read_span(file: str, start: int, end: int, cap: int = MAX_SPAN_CHARS) -> str:
    try:
        lines = Path(file).read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        return ""
    text = "\n".join(lines[max(0, start - 1):max(start, end)])
    if len(text) > cap:
        return text[:cap].rstrip() + "\n[... truncated]"
    return text


def _format_hits(root: Path, hits: list[dict]) -> str:
    blocks: list[str] = []
    for hit in hits:
        try:
            relative = Path(hit["file"]).resolve().relative_to(root).as_posix()
        except (ValueError, OSError):
            relative = hit["file"]
        span = _read_span(hit["file"], hit["start"], hit["end"])
        header = f"{hit['kind']} {hit['qualname']} — {relative}:{hit['start']}-{hit['end']}"
        blocks.append(f"{header}\n{span}" if span else header)
    return "\n\n".join(blocks)


def search_workspace(root: Path, query: str, kind: str | None = None,
                     limit: int = MAX_HITS) -> list[dict]:
    database = index_database(root)
    if not database.exists():
        return []
    store = SemanticStore(database)
    try:
        return store.search(query, kind=kind, limit=limit)
    finally:
        store.close()


async def query_codebase(query: str, kind: str | None = None) -> str:
    """Answer a symbol question from the index; index on first use if needed."""
    text = (query or "").strip()
    if not text:
        return "[query_codebase needs a non-empty query]"
    root = _workspace_root()
    database = index_database(root)
    if not database.exists():
        result = index_workspace(root)
        prefix = (
            f"[index built on first use: {result.files} files, "
            f"{result.symbols} symbols in {result.duration_ms} ms]\n\n"
        )
    else:
        prefix = ""
    hits = search_workspace(root, text, kind=kind)
    if not hits:
        return prefix + (
            f"[no symbol or file matches '{text}'"
            + (f" with kind '{kind}'" if kind else "")
            + " — the index may be stale; re-index the workspace or widen the query]"
        )
    return prefix + _format_hits(root, hits)


def workspace_project_map() -> str:
    """The map text the chat route may inject into the system prompt."""
    try:
        return project_map_for_workspace(_workspace_root())
    except Exception:
        return ""
