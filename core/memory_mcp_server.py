"""
◑ Ephe – memory as an MCP server (wave D4b)
core/memory_mcp_server.py

Ephe's memory now has two doors: the HTTP API of its own PWA and this
stdio MCP server for every MCP agent the user connects themselves. No third
store, no new index — `core.memory.Memory` stays the one
facade; this module is only the protocol and the politics around it, the surface
lives in `core.memory_mcp_tools.py`.

Why stdio and not HTTP: a network listener would be a second, unwatched
entrance into long-term memory. stdio serves only whoever the user
starts themselves — the permission is the line they wrote.

The politics in three rules:
  1. **Writing costs an opt-in** (`--allow-write` / `EPHE_MEMORY_MCP_WRITE=1`):
     an external agent that quietly writes into memory poisons it with
     kindness. Every refusal lands in the audit log (`kind="mcp_memory"`),
     which the settings surface already shows.
  2. **One scope per server** (W16): the door leads into *one* brain; `--scope`
     picks it, an "everything" mode does not exist.
  3. **Stdout is the protocol**: banner and diagnostics go to stderr, one
     line of text on stdout would be a broken frame for every client.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from core._version import version_string
from core.audit_log import audit_event
from core.memory_mcp_tools import (
    MUTATING_TOOLS,
    call_tool,
    is_known,
    tool_specs,
)

SERVER_NAME = "ephe-memory"
#: the same version `core/tools/mcp_client.py` speaks — Ephe has to be able to
#: connect itself, otherwise the server is a protocol for others.
PROTOCOL_VERSION = "2024-11-05"
AUDIT_KIND = "mcp_memory"
ENV_ALLOW_WRITE = "EPHE_MEMORY_MCP_WRITE"


def writes_allowed(raw: str | None = None) -> bool:
    """Opt-in for the writing tools — without the env the server is read-only.

    Only `1` (also `true`/`yes`) releases; everything else, the empty value
    included, means no. A default that writes would be a default that
    overwrites.
    """
    value = raw if raw is not None else os.environ.get(ENV_ALLOW_WRITE)
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _instructions(allow_write: bool) -> str:
    """Lands in the `initialize` result: a model reads this before its first call."""
    mode = (
        "Writes are allowed: memory_store, memory_update and memory_delete are live."
        if allow_write
        else "This server is read-only: memory_store, memory_update and memory_delete "
             f"are refused until it runs with --allow-write or {ENV_ALLOW_WRITE}=1."
    )
    return (
        "Ephe's persistent memory over MCP. One workspace scope per server, so the "
        "facts you read belong to one project. "
        + mode
        + " Search before storing: a fact corrected with `supersedes` stays one fact "
        "instead of becoming two. There is no clear or export here — this door reads "
        "and adds, it does not empty a mind."
    )


def _result(request_id: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_reply(text: str, *, is_error: bool = False) -> dict:
    # no isError field on success: MCP reads absence as "not wrong", and
    # a flag per success would be protocol noise.
    return {
        "content": [{"type": "text", "text": text}],
        **({"isError": True} if is_error else {}),
    }


def _refusal(name: str) -> str:
    return (
        f"'{name}' is refused: this server runs read-only. Ephe's memory belongs to the "
        "user, so an outside agent writes only when they say so (--allow-write or "
        f"{ENV_ALLOW_WRITE}=1). Searching, listing and stats work right now."
    )


def _audit(name: str, args: dict, decision: str, status: str, text: str) -> None:
    """Records every call, but not its content: the audit log is shared storage,
    the memory holds private text."""
    audit_event(
        AUDIT_KIND,
        tool=name,
        args={
            "top_k": args.get("top_k"),
            "limit": args.get("limit"),
            "id": args.get("id") or args.get("supersedes") or "",
            "chars": len(str(args.get("text") or "")),
        },
        decision=decision,
        status=status,
        detail=text.splitlines()[0][:120] if text else "",
    )


def handle_request(request: dict, *, memory: Any, allow_write: bool) -> dict | None:
    """One JSON-RPC request, one answer — `None` for notifications.

    Pure and without I/O: the loop holds the bytes, the decision sits here.
    """
    method = str(request.get("method") or "")
    request_id = request.get("id")
    params = request.get("params")
    if not isinstance(params, dict):
        params = {}

    if method == "" or method.startswith("notifications/"):
        return None

    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": version_string()},
            "instructions": _instructions(allow_write),
        })
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": tool_specs()})
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments")
        if not isinstance(args, dict):
            return _error(request_id, -32602, "arguments must be an object")
        if not is_known(name):
            return _error(request_id, -32602, f"unknown tool {name!r}")
        denied = name in MUTATING_TOOLS and not allow_write
        text, is_error = (
            (_refusal(name), True) if denied else call_tool(name, memory, args, allow_write)
        )
        _audit(
            name,
            args,
            "denied" if denied else ("error" if is_error else "allowed"),
            "error" if is_error else "ok",
            text,
        )
        return _result(request_id, _tool_reply(text, is_error=is_error))

    return _error(request_id, -32601, f"method not found: {method}")


def _emit(stream: Any, payload: dict) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stream.flush()


def _default_memory(scope: str | None = None) -> Any:
    """The brain Ephe itself also uses — the same scope, not a second one."""
    from core.memory import Memory

    return Memory() if scope is None else Memory(scope=scope)


def serve(
    *,
    memory: Any = None,
    allow_write: bool | None = None,
    stdin: Any = None,
    stdout: Any = None,
) -> int:
    """Reads lines until the pipe closes; returns the exit code."""
    brain = memory if memory is not None else _default_memory()
    write_ok = writes_allowed() if allow_write is None else allow_write
    reader = stdin if stdin is not None else sys.stdin
    writer = stdout if stdout is not None else sys.stdout

    for line in reader:
        line = line.strip()
        if not line:
            continue
        request_id: Any = None
        try:
            request = json.loads(line)
        except ValueError as exc:
            _emit(writer, _error(None, -32700, f"parse error: {exc}"))
            continue
        if not isinstance(request, dict):
            _emit(writer, _error(None, -32700, "request must be a JSON object"))
            continue
        request_id = request.get("id")
        try:
            response = handle_request(request, memory=brain, allow_write=write_ok)
        except Exception as exc:  # one call must not kill the pipe
            _emit(writer, _error(request_id, -32603, f"{type(exc).__name__}: {exc}"))
            continue
        if response is not None:
            _emit(writer, response)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ephe memory-mcp",
        description=(
            "Serve Ephe's workspace memory over MCP on stdin/stdout. Reads are open; "
            "writes need --allow-write or EPHE_MEMORY_MCP_WRITE=1."
        ),
    )
    parser.add_argument(
        "--allow-write", action="store_true",
        help="let the connected agent store, correct and remove facts",
    )
    parser.add_argument(
        "--read-only", action="store_true",
        help="refuse writes even when EPHE_MEMORY_MCP_WRITE is set",
    )
    parser.add_argument(
        "--scope", default=None,
        help="workspace scope to serve (default: the active Ephe workspace)",
    )
    args = parser.parse_args(argv)

    allow_write = False if args.read_only else (True if args.allow_write else writes_allowed())
    memory = _default_memory(args.scope)
    print(
        f"ephe-memory: scope={memory.collection_name} provider={memory.provider_kind} "
        f"write={'enabled' if allow_write else 'read-only'} (stdio, one process per scope)",
        file=sys.stderr,
    )
    return serve(memory=memory, allow_write=allow_write)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
