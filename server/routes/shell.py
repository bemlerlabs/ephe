"""server/routes/shell.py – POST /api/shell (AgentPanel full terminal).

The user is the author of the command input = the explicit approval
(equivalent to --yes in the CLI). The hard security boundary stays run_shell's
own ALLOWED_COMMANDS whitelist + BLOCKED_PATTERNS + timeout
(core/tools/shell_tools.py). This route adds NO new exec path —
it calls the same execute_tool('run_shell', ...) as the chat agent.
"""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.audit_log import audit_event
from core.pty_session import get_pty_session
from core.tools.registry import execute_tool
from core.tools.approval import ApprovalPolicy
from server.middleware import ws_client_authorized

router = APIRouter(tags=["Shell"])

#: W16: a fixed header value that tells cross-origin POSTs from simple
#: fetch/form POSTs apart (XHR paradigm). Only our own PWA sets it deliberately.
XHR_HEADER = "X-Requested-With"
XHR_VALUE = "XMLHttpRequest"


class ShellRequest(BaseModel):
    command: str
    #: The client states, per call, that the user approved this command. The CSRF header below
    #: proves the request came from a page that can set headers; this proves a client decided.
    #: A stray form POST or a script that reuses the header does neither, and the route
    #: refuses without it.
    approved: bool = False
    #: W17 P1-1: optional stdin feed for the PTY pipe ('read' scripts).
    input: str | None = None


class ShellResponse(BaseModel):
    command: str
    output: str
    ok: bool


@router.post("/shell", response_model=ShellResponse)
async def run_shell_command(
    req: ShellRequest,
    x_requested_with: str | None = Header(None, alias=XHR_HEADER),
) -> ShellResponse:
    # W16: CSRF/cross-origin guard — no run without the exact X-Requested-With
    # value. Browser forms and foreign fetch POSTs do not carry the header
    # automatically; the PWA sets it in the api.ts client.
    if (x_requested_with or "").strip() != XHR_VALUE:
        raise HTTPException(
            status_code=403,
            detail=f"missing or wrong header '{XHR_HEADER}' (expected '{XHR_VALUE}').",
        )
    command = (req.command or "").strip()
    if not req.approved:
        raise HTTPException(
            status_code=403,
            detail="This route runs a command only with an explicit approval: the terminal "
                   "that shows the user what runs sends approved=true.",
        )
    if not command:
        return ShellResponse(command="", output="(leer)", ok=False)
    # User authorization == explicit approval; the whitelist/blocked patterns
    # inside run_shell remain the hard security boundary (no RCE free space).
    policy = ApprovalPolicy(auto_approve=True, interactive=False)
    output = await execute_tool("run_shell", {"command": command}, policy)
    ok = not output.startswith("⚠") and not output.startswith("[tool-error")
    return ShellResponse(command=command, output=output, ok=ok)


@router.post("/shell/pty", response_model=ShellResponse)
async def run_shell_pty_command(
    req: ShellRequest,
    x_requested_with: str | None = Header(None, alias=XHR_HEADER),
) -> ShellResponse:
    # W17 P1-1: PTY pipe (os.openpty) — the onlcr translation stays in place,
    # stdin is written before reading (write+EOF) so that `read` terminates.
    if (x_requested_with or "").strip() != XHR_VALUE:
        raise HTTPException(
            status_code=403,
            detail=f"missing or wrong header '{XHR_HEADER}' (expected '{XHR_VALUE}').",
        )
    command = (req.command or "").strip()
    if not req.approved:
        raise HTTPException(
            status_code=403,
            detail="This route runs a command only with an explicit approval: the terminal "
                   "that shows the user what runs sends approved=true.",
        )
    if not command:
        return ShellResponse(command="", output="(leer)", ok=False)
    from core.tools.shell_tools import run_shell_pty

    output = await asyncio.to_thread(run_shell_pty, command, req.input or "")
    ok = (
        not output.startswith("⚠")
        and not output.startswith("[tool-error")
        and not output.startswith("[timeout")
    )
    return ShellResponse(command=command, output=output, ok=ok)


# P1-5: full PTY terminal (interactive, persistent)
#
# Unlike /shell/pty (one-shot, buffered) the client attaches here to
# a long-lived PTY session (core/pty_session). xterm.js sends raw
# keystrokes as {"type":"input"} — the PTY line discipline + the shell (readline)
# do echo, line editing, Ctrl-C (SIGINT to the process group) and
# full-screen apps (vim/less) natively. Tab change/reload reconnect onto the same
# session including scrollback replay (session continuity).
#
# SECURITY: BaseHTTPMiddleware does NOT cover the websocket scope — hence the
# explicit ws_client_authorized gate (loopback trusted, LAN needs ?token=).
# An interactive shell is by design RCE; it belongs to the typing user
# (IDE terminal model), not to the agent (whose run_shell stays whitelisted).


async def _pump_output(ws: WebSocket, queue: asyncio.Queue) -> None:
    """PTY reader queue → WebSocket. Ends on the exit frame or on disconnect."""
    try:
        while True:
            frame = await queue.get()
            await ws.send_json(frame)
            if frame.get("type") == "exit":
                break
    except (WebSocketDisconnect, RuntimeError):
        pass


@router.websocket("/shell/term")
async def shell_terminal(ws: WebSocket) -> None:
    origin = ws.headers.get("origin") or "none"
    host = ws.headers.get("host") or "none"
    if not ws_client_authorized(ws):
        # 1008 = policy violation; no accept() → the handshake is refused.
        from server.middleware import audit_ws_refusal

        audit_ws_refusal(ws, "interactive_pty_refused", path="/api/shell/term")
        await ws.close(code=1008)
        return
    await ws.accept()
    audit_event(
        "shell",
        tool="terminal",
        status="open",
        detail=f"interactive_pty_attached host={host} origin={origin}",
    )
    session = get_pty_session()
    back = session.scrollback()
    if back:
        await ws.send_json({"type": "output", "data": back.decode("utf-8", "replace")})
    if not session.alive:
        await ws.send_json(
            {"type": "output", "data": "\r\n[interactive PTY unavailable on this platform]\r\n"}
        )
        await ws.send_json({"type": "exit", "code": -1})
        await ws.close()
        return

    queue = session.subscribe()
    pump = asyncio.create_task(_pump_output(ws, queue))
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "input":
                session.write((msg.get("data") or "").encode("utf-8", "replace"))
            elif kind == "resize":
                session.resize(int(msg.get("cols", 80)), int(msg.get("rows", 24)))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — honest close instead of a stack trace in the log
        pass
    finally:
        session.unsubscribe(queue)
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump
