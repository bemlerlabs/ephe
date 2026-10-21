"""Ephe – MCP transport: the JSON-RPC client that speaks to one MCP server.

Split out of ``core.tools.mcp_client`` (W7b-2). The wire side lives here: the
JSON-RPC 2.0 payload builders and response parsers, the paginated
``tools/list`` catalogue walk, and the per-server client that drives both. The
sibling module ``core.tools.mcp_client`` keeps the server-spec registry, the
sync orchestration and the catalogue-freshness policy, and re-exports every
public name from here, so callers keep importing from ``mcp_client``.

Transports:
- http  : POST JSON-RPC to an HTTP endpoint (streamable HTTP / SSE)
- stdio : starts a local MCP server as a subprocess, JSON-RPC over stdin/stdout

The client is deliberately minimal and fault-tolerant: on network/timeout errors
it returns a readable error string instead of an abort, so the agent can keep
working. The process side (spawn, exit, backoff) lives in
``core.tools.mcp_process.StdioLink``; a JSON-RPC error is an error, not an empty
success.
"""
from __future__ import annotations

from typing import Any

from core.tools.mcp_process import StdioLink, error_envelope

# httpx is imported lazily (only in the http path) — no import error when it is missing.
try:
    import httpx
except Exception:  # pragma: no cover - optional dependency
    httpx = None  # type: ignore[assignment]

_MCP_PROTOCOL_VERSION = "2024-11-05"
#: Hard ceiling on ``tools/list`` pages. The MCP standard paginates the tool
#: catalogue via ``nextCursor``; a server that never stops handing out a fresh
#: cursor (or repeats one) must not spin discovery without an end.
MAX_TOOL_PAGES = 50
_MCP_COUNTER: dict[str, int] = {}


def _mcp_id() -> int:
    _MCP_COUNTER["n"] = _MCP_COUNTER.get("n", 0) + 1
    return _MCP_COUNTER["n"]


def _rpc(method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _result_text(content: list[dict]) -> str:
    return "\n".join(str(c.get("text", "")) for c in content if c.get("type") == "text")


def _jsonrpc_error_text(resp: dict) -> str:
    """The text of a JSON-RPC error — readable, with code, without stack trace."""
    err = resp.get("error")
    if not isinstance(err, dict):
        return f"mcp jsonrpc error: {err!r}"
    message = str(err.get("message") or err)
    code = err.get("code")
    return f"mcp error {code}: {message}" if code is not None else f"mcp error: {message}"


class MCPClient:
    """A single MCP server: list_tools() → tools, call_tool() → result."""

    def __init__(self, endpoint: str, transport: str = "http", label: str = "", timeout: float = 30.0, args: list[str] | None = None, auth_token: str = ""):
        self.endpoint = endpoint
        self.transport = transport
        self.label = label or endpoint
        self.timeout = timeout
        self.args = list(args or [])
        self.auth_token = auth_token
        self.session_id: str | None = None
        # Restart policy (I1-8): failures count, the backoff window applies —
        # both sit with the process, because only the process restarts.
        self.last_error: str = ""
        self._link: StdioLink | None = None
        if transport == "stdio":
            self._link = StdioLink(endpoint, self.args, timeout)

    # --- JSON-RPC payload builders (pure, testable) ---
    def _build_initialize(self) -> dict:
        return _rpc("initialize", {"protocolVersion": _MCP_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "ephe", "version": "2.0.0"}}, _mcp_id())

    def _build_tools_list(self, request_id: int, cursor: str | None = None) -> dict:
        """`tools/list`, optionally continuing from a page cursor.

        The MCP standard paginates the tool catalogue: a reply may carry a
        ``nextCursor``, and the following page is a second ``tools/list`` that
        passes that cursor back in the params. Without the cursor a server with
        more tools than one page answers with its first page only, and every
        tool behind the cursor is never discovered.
        """
        params: dict[str, Any] = {"cursor": cursor} if cursor else {}
        return _rpc("tools/list", params, request_id)

    def _build_tools_call(self, name: str, arguments: dict, request_id: int) -> dict:
        return _rpc("tools/call", {"name": name, "arguments": arguments}, request_id)

    # --- response parsers (pure, testable) ---
    def _parse_tools_response(self, resp: dict) -> list[dict]:
        if "error" in resp:
            self.last_error = _jsonrpc_error_text(resp)
            return []
        return resp.get("result", {}).get("tools", []) or []

    def _parse_tools_cursor(self, resp: dict) -> str | None:
        """The ``nextCursor`` of a ``tools/list`` reply, or None on the last page."""
        cursor = resp.get("result", {}).get("nextCursor")
        return cursor if isinstance(cursor, str) and cursor else None

    def _extract_tool_result(self, resp: dict) -> tuple[str, bool]:
        # Without this branch a JSON-RPC error was reported as an empty success:
        # the client answered with ("", False) and the agent took the failure
        # for a tool that had returned nothing.
        if "error" in resp:
            self.last_error = _jsonrpc_error_text(resp)
            return self.last_error, True
        result = resp.get("result", {})
        is_error = bool(result.get("isError"))
        text = _result_text(result.get("content", []))
        if is_error:
            self.last_error = text
        else:
            self._on_success()
        return text, is_error

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": _MCP_PROTOCOL_VERSION,
            "MCP-Session-Id": self.session_id or "",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    # --- Transport ---
    async def _post(self, endpoint: str, headers: dict, body: dict) -> dict:
        """HTTP POST with JSON-RPC. Overridable for tests."""
        if httpx is None:  # pragma: no cover
            return error_envelope(body, -32000, "httpx not installed")
        from core.network_guard import NetworkGuardError, prepare_http_target

        try:
            target, host_header, sni = prepare_http_target(endpoint)
        except NetworkGuardError as exc:
            return error_envelope(body, -32010, f"mcp network guard: {exc}")
        request_headers = dict(headers)
        request_headers["Host"] = host_header
        extensions = {"sni_hostname": sni} if sni else None
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=False, trust_env=False
        ) as client:
            resp = await client.post(
                target,
                headers=request_headers,
                json=body,
                extensions=extensions,
            )
            if 300 <= resp.status_code < 400:
                return error_envelope(body, -32011, "mcp redirect refused")
            try:
                return resp.json()
            except Exception:
                return error_envelope(body, -32003, f"non-JSON reply ({resp.status_code})")

    async def _send(self, body: dict) -> dict:
        if self.transport != "stdio":
            return await self._post(self.endpoint, self._headers(), body)
        link = self._link
        if link is None:
            link = self._link = StdioLink(self.endpoint, self.args, self.timeout)
        resp = await link.send(body)
        error = resp.get("error")
        if isinstance(error, dict):
            # The process refused — this text is the reason the agent sees.
            self.last_error = str(error.get("message") or error)
        else:
            self._on_success()
        return resp

    def _on_success(self) -> None:
        self.last_error = ""
        if self._link is not None:
            self._link.note_success()

    # --- Public API ---
    async def list_tools(self) -> list[dict]:
        """Lists remote tools, following the catalogue across its pages.

        The MCP standard paginates ``tools/list``: a reply may carry a
        ``nextCursor`` and the next page is another ``tools/list`` with that
        cursor. A single request therefore discovers only the first page — a
        server with more tools than one page silently hides the rest. This
        follows the cursor, dedupes by tool name, and stops at
        ``MAX_TOOL_PAGES`` or as soon as a cursor repeats, so a server that never
        ends its pagination cannot spin the loop.

        Fault-tolerant: a failure *before* any tool is found → ``[{"error": …}]``;
        a failure *after* some pages → the tools found so far (``last_error``
        set), because dropping the pages already read is worse than a short list.
        The session is not initialized (many servers answer tools/list without
        initialize); on demand via ``initialize()``.
        """
        tools: list[dict] = []
        seen_names: set[str] = set()
        seen_cursors: set[str] = set()
        cursor: str | None = None
        for _ in range(MAX_TOOL_PAGES):
            try:
                resp = await self._send(self._build_tools_list(_mcp_id(), cursor))
            except Exception as exc:
                self.last_error = f"mcp list failed: {exc!r}"
                return tools or [{"error": self.last_error}]
            if "error" in resp:
                # The reason is known — swallowing it leaves the health page guessing.
                self.last_error = _jsonrpc_error_text(resp)
                return tools or [{"error": self.last_error}]
            for tool in self._parse_tools_response(resp):
                name = tool.get("name") if isinstance(tool, dict) else None
                if name and name in seen_names:
                    continue
                if name:
                    seen_names.add(name)
                tools.append(tool)
            next_cursor = self._parse_tools_cursor(resp)
            if not next_cursor or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return tools

    async def initialize(self) -> dict:
        return await self._send(self._build_initialize())

    async def call_tool(self, name: str, arguments: dict | None = None) -> tuple[str, bool]:
        """Calls a remote tool. Returns (text, is_error), never an abort."""
        arguments = arguments or {}
        try:
            resp = await self._send(self._build_tools_call(name, arguments, _mcp_id()))
        except Exception as exc:
            self.last_error = f"mcp call failed: {exc!r}"
            return self.last_error, True
        return self._extract_tool_result(resp)

    async def close(self) -> None:
        """Reaps the child process; the session falls with it — a new server
        does not know the old ``MCP-Session-Id``."""
        if self._link is not None:
            await self._link.close()
        self.session_id = None
