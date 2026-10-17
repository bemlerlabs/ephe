"""core/pty_session.py — persistent interactive PTY session (P1-5 full terminal).

A real terminal backend core: a long-lived PTY (os.openpty + shell) fed over a
WebSocket. Unlike run_shell_pty (one-shot, buffered) the shell stays alive between
connections — a tab change or a panel reload hooks back into the same session
(session continuity), including scrollback replay.

Security model: this is an interactive shell = RCE by design. It is the same
surface as an IDE terminal (VS Code) and belongs to the user who types — not to
the agent (whose run_shell stays whitelist-gated). Access is protected at route
level by the same LAN auth trust as the rest of the API (loopback trusted,
otherwise X-Auth-Token); see ws_client_authorized in server/middleware.py. This
class itself does NO auth — it is the pure PTY mechanism.

Platforms without os.openpty (some Windows setups): start() returns False, and the
route reports "PTY unavailable" instead of half interactivity.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import struct
import subprocess
import threading
from collections import deque

try:  # TIOCSWINSZ/termios are missing on Windows without openpty — disabled there anyway.
    import fcntl
    import termios
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]

#: Scrollback cap for replay on reconnect (~256 KiB) — no unbounded growth.
SCROLLBACK_BYTES = 256 * 1024
#: Single read chunk from the master.
_READ_CHUNK = 4096


def _default_shell() -> str:
    """The user's login shell, with a POSIX-safe fallback."""
    shell = os.environ.get("SHELL") or ""
    if shell and os.path.isabs(shell) and os.path.exists(shell):
        return shell
    for candidate in ("/bin/bash", "/bin/sh"):
        if os.path.exists(candidate):
            return candidate
    return shell or "sh"


def pty_available() -> bool:
    return hasattr(os, "openpty") and fcntl is not None and termios is not None


class PtySession:
    """One long-lived PTY with a shell process and fan-out to subscribers.

    The reader thread blocks on reads from the master and distributes the bytes to
    all asyncio queues (subscribers) plus a scrollback ring buffer. Queues are
    bound per subscriber to that subscriber's event loop (subscribe() runs inside
    the async handler), so call_soon_threadsafe pushes into the right loop.
    """

    def __init__(self, shell: str | None = None, cwd: str | None = None) -> None:
        self.shell = shell or _default_shell()
        self.cwd = cwd or os.getcwd()
        self.master: int | None = None
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._loops: dict[int, asyncio.AbstractEventLoop] = {}
        self._scrollback = deque[bytes]()
        self._scrollback_size = 0
        self._lock = threading.Lock()
        self._closed = False
        self.exit_code: int | None = None

    # Lifecycle
    def start(self, cols: int = 80, rows: int = 24) -> bool:
        """Start the PTY + shell. True on success, False when the platform cannot do PTY."""
        if self.proc is not None:
            return self.alive
        if not pty_available():
            return False
        master, slave = os.openpty()
        self._set_winsize(master, cols, rows)
        env = dict(os.environ)
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLUMNS", str(cols))
        env.setdefault("LINES", str(rows))
        try:
            self.proc = subprocess.Popen(
                [self.shell, "-i"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=self.cwd,
                env=env,
                start_new_session=True,  # own process group → Ctrl-C/SIGINT isolated
                close_fds=True,
            )
        except OSError:
            os.close(master)
            os.close(slave)
            self.proc = None
            return False
        # The slave belongs to the child; the parent only holds the master.
        os.close(slave)
        self.master = master
        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return True

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def kill(self) -> None:
        self._closed = True
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), 9)
            except (ProcessLookupError, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
        if self.master is not None:
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = None

    # I/O
    def write(self, data: bytes) -> None:
        if self.master is None or not data:
            return
        try:
            os.write(self.master, data)
        except OSError:
            pass

    def resize(self, cols: int, rows: int) -> None:
        if self.master is None:
            return
        cols = max(2, min(int(cols or 80), 500))
        rows = max(2, min(int(rows or 24), 200))
        self._set_winsize(self.master, cols, rows)
        # SIGWINCH to the process group, so vim/less redraw.
        if self.proc is not None and self.proc.poll() is None:
            try:
                import signal

                os.killpg(os.getpgid(self.proc.pid), signal.SIGWINCH)
            except (ProcessLookupError, OSError, AttributeError):
                pass

    @staticmethod
    def _set_winsize(fd: int, cols: int, rows: int) -> None:
        if termios is None or fcntl is None:
            return
        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass

    def scrollback(self) -> bytes:
        with self._lock:
            return b"".join(self._scrollback)

    # Fan-out
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        self._loops[id(q)] = asyncio.get_running_loop()
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)
        self._loops.pop(id(q), None)

    def _emit(self, data: bytes) -> None:
        text = data.decode("utf-8", "replace")
        dead: list[asyncio.Queue] = []
        for q in list(self._subscribers):
            loop = self._loops.get(id(q))
            if loop is None or loop.is_closed():
                dead.append(q)
                continue
            try:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "output", "data": text})
            except RuntimeError:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)
            self._loops.pop(id(q), None)

    def _emit_exit(self, code: int) -> None:
        for q in list(self._subscribers):
            loop = self._loops.get(id(q))
            if loop is None or loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "exit", "code": code})
            except RuntimeError:
                pass

    def _read_loop(self) -> None:
        assert self.master is not None
        master = self.master
        while not self._closed:
            try:
                data = os.read(master, _READ_CHUNK)
            except OSError:
                break
            if not data:
                break
            with self._lock:
                self._scrollback.append(data)
                self._scrollback_size += len(data)
                while self._scrollback_size > SCROLLBACK_BYTES and len(self._scrollback) > 1:
                    dropped = self._scrollback.popleft()
                    self._scrollback_size -= len(dropped)
            self._emit(data)
        code = 0
        if self.proc is not None:
            try:
                code = self.proc.wait()
            except Exception:  # noqa: BLE001
                code = 0
        self.exit_code = code
        self._emit_exit(code)


# Process singleton (session continuity across WS reconnects)
_SESSION: PtySession | None = None
_SESSION_LOCK = threading.Lock()


def get_pty_session(shell: str | None = None, cwd: str | None = None) -> PtySession:
    """Returns the one long-lived session; starts it on first access."""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None or not _SESSION.alive:
            if _SESSION is not None:
                _SESSION.kill()
            sess = PtySession(shell=shell, cwd=cwd)
            sess.start()
            _SESSION = sess
        return _SESSION


def reset_pty_session() -> None:
    """Test/shutdown hook: terminate the running session and drop the singleton."""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is not None:
            _SESSION.kill()
        _SESSION = None
