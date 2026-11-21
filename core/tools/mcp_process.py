"""Ephe – the child process behind a stdio MCP server.

A stdio MCP server is not an endpoint but a child process, and a
child process that dies dies permanently. This module holds the line exactly there:
``MCPClient`` speaks JSON-RPC, ``StdioLink`` keeps the window to the
process open and cleans it up.

Three duties that were previously written down nowhere:
- **Wait for exit** (`reap`): a terminated but unreaped server
  stays a zombie in the process table — one per health probe and per
  restart.
- **Recognize death** (`proc.returncode`): a dead process hangs on closed
  pipes; whoever keeps writing to it waits for an answer that never comes.
- **Throttle restarts** (exponential backoff, 0.5–30 s): a server without
  a binary, with wrong args or in a crash loop must not restart per tool
  call. Only failed *attempts* are counted — dying between two
  calls is not yet a crash loop, the first restart stays free.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from core import mcp_sandbox
from core.secret_broker import child_env

logger = logging.getLogger(__name__)

#: Backoff for restarting a dead server: 0.5 s, doubled,
#: finished at 30 s.
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 30.0
#: Time a terminated child process gets for its exit before it is killed.
EXIT_GRACE_SECONDS = 2.0


def error_envelope(body: dict, code: int, message: str) -> dict:
    """A JSON-RPC error dressed up as the requested message."""
    return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": code, "message": message}}


class StdioLink:
    """Spawn, one JSON line, wait for exit — the process side of a stdio server."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        timeout: float = 30.0,
        trusted: bool = False,
        env_names: list[str] | None = None,
    ):
        self.command = command
        self.args = list(args or [])
        self.trusted = trusted
        self.timeout = timeout
        #: The names this connector declared; the values stay in the vault and are
        #: read once at spawn, so the child holds them and this object does not.
        self.env_names = list(env_names or [])
        self.proc: Any | None = None
        self.last_error: str = ""
        self.failures: int = 0
        self._retry_after: float = 0.0

    @property
    def alive(self) -> bool:
        return self.proc is not None

    def _fail(self, body: dict, code: int, message: str) -> dict:
        self.last_error = message
        return error_envelope(body, code, message)

    def _audit_child(
        self, boundary: str, home: str, *, decision: str = ""
    ) -> None:
        try:
            from core.audit_log import audit_event

            verdict = decision or (
                "unsandboxed" if boundary == "unavailable" else "sandboxed"
            )
            audit_event(
                "mcp_child",
                tool=self.command,
                decision=verdict,
                detail=f"home={home} os_boundary={boundary}",
            )
        except Exception:  # noqa: BLE001 — an audit failure must not block the spawn
            logger.debug("mcp child audit skipped", exc_info=True)

    def _child_env(self, home: str | None) -> dict[str, str]:
        env = child_env(home=home)
        if not self.env_names:
            return env
        from core import secret_store

        env.update(secret_store.env_for(self.env_names))
        return env

    def note_failure(self) -> None:
        self.failures += 1
        delay = min(
            BACKOFF_BASE_SECONDS * float(2 ** (self.failures - 1)),
            BACKOFF_MAX_SECONDS,
        )
        self._retry_after = asyncio.get_running_loop().time() + delay

    def note_success(self) -> None:
        self.failures = 0
        self._retry_after = 0.0
        self.last_error = ""

    def backoff_seconds(self) -> float:
        if not self._retry_after:
            return 0.0
        return max(0.0, self._retry_after - asyncio.get_running_loop().time())

    async def reap(self) -> None:
        """Reaps the child process: terminate, wait for exit, kill if necessary.

        If the process is already reaped (`returncode` set), there is nothing
        to terminate — only the reference has to go.
        """
        proc, self.proc = self.proc, None
        if proc is None:
            return
        for step in (getattr(proc, "terminate", None), getattr(proc, "kill", None)):
            if proc.returncode is not None:
                return
            if step is None:
                return
            try:
                step()
                await asyncio.wait_for(proc.wait(), timeout=EXIT_GRACE_SECONDS)
                return
            except Exception:  # noqa: BLE001 — cleanup never throws the call
                continue

    async def send(self, body: dict) -> dict:
        """Starts the server lazily and writes/reads one JSON line over stdio.

        A dead process is recognized at ``returncode``, reaped, and restarted
        only outside the backoff window.
        """
        if self.proc is not None and self.proc.returncode is not None:
            await self.reap()
        if self.proc is None:
            if not self.command:
                return self._fail(body, -32000, "stdio server not configured")
            waiting = self.backoff_seconds()
            if waiting:
                return self._fail(
                    body,
                    -32004,
                    f"stdio restart deferred {waiting:.1f}s after {self.failures} "
                    f"failures (last: {self.last_error or 'unknown'})",
                )
            home = None
            argv = [self.command, *self.args]
            boundary = "trusted"
            if not self.trusted:
                home = str(mcp_sandbox.home_for(self.command))
                boundary = mcp_sandbox.platform_boundary()
                if boundary == "unavailable":
                    # No boundary, no child: a model-chosen server next to the
                    # user's key material is the one spawn this product refuses
                    # to make. No raw argv fallback exists here.
                    self._audit_child("unavailable", home, decision="refused")
                    self.note_failure()
                    if sys.platform.startswith("win"):
                        detail = (
                            "MCP server needs a filesystem boundary; Windows "
                            "provides none in this build, so the child is not started"
                        )
                    else:
                        detail = (
                            "MCP server needs a filesystem boundary "
                            "(install bubblewrap and enable user namespaces, or use a "
                            "platform that provides Seatbelt); no boundary, no start"
                        )
                    return self._fail(body, -32006, detail)
                wrapped = mcp_sandbox.wrap(self.command, self.args, home)
                if wrapped is None:  # the boundary claimed to work and did not
                    self._audit_child(boundary, home, decision="refused")
                    self.note_failure()
                    return self._fail(
                        body,
                        -32006,
                        "MCP server needs a filesystem boundary; the wrapper "
                        "refused to build one",
                    )
                argv = wrapped
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self._child_env(home),
                    # The bwrap path already chdirs; Seatbelt needs the same
                    # start directory, or `python -c` reads the denied home as
                    # its cwd and dies before the first message.
                    cwd=home,
                )
            except Exception as exc:  # noqa: BLE001 — a missing binary is a refusal
                self._audit_child(boundary, home or "", decision="spawn_failed")
                self.note_failure()
                return self._fail(body, -32005, f"stdio spawn failed: {exc}")
            # The sandboxed line is written only once the child exists under it.
            if self.trusted:
                self._audit_child("trusted", "", decision="trusted")
            else:
                self._audit_child(boundary, home or "")
        proc = self.proc
        if proc.stdin is None or proc.stdout is None:
            await self.reap()
            self.note_failure()
            return self._fail(body, -32000, "stdio pipe closed")
        try:
            proc.stdin.write((json.dumps(body) + "\n").encode())
            await proc.stdin.drain()
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=self.timeout)
        except asyncio.TimeoutError:
            # The server hangs; only a restart can reach it, so get rid of it.
            await self.reap()
            self.note_failure()
            return self._fail(body, -32002, "stdio timeout")
        except Exception as exc:  # noqa: BLE001 — a broken pipe is a refusal
            await self.reap()
            self.note_failure()
            return self._fail(body, -32007, f"stdio write failed: {exc}")
        if not line:
            await self.reap()
            self.note_failure()
            return self._fail(body, -32001, "stdio server closed")
        try:
            resp = json.loads(line.decode().strip())
        except Exception:
            self.note_failure()
            return self._fail(body, -32003, "non-JSON stdio reply")
        self.note_success()
        return resp

    async def close(self) -> None:
        await self.reap()
