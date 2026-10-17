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
from typing import Any

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

    def __init__(self, command: str, args: list[str] | None = None, timeout: float = 30.0):
        self.command = command
        self.args = list(args or [])
        self.timeout = timeout
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
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    self.command,
                    *self.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except Exception as exc:  # noqa: BLE001 — a missing binary is a refusal
                self.note_failure()
                return self._fail(body, -32005, f"stdio spawn failed: {exc}")
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
            return self._fail(body, -32006, f"stdio write failed: {exc}")
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
