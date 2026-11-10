"""The plugin worker supervisor: start confined, classify, leave no orphans.

Task #9's confined runner calls `run_worker` with a `WorkerSpec`. Three rules this
file exists to keep true:

- No confinement, no execution. `confined_argv` returns None where the OS has no
  boundary (Linux without bubblewrap, macOS without sandbox-exec, any Windows —
  this tree carries no Windows rung at all), and the worker is classified
  `sandbox_unavailable` before anything spawns. The child never ran; the ordering
  of the code above is the answer, not a claim made after the fact.
- The process group dies on timeout. The child leads its own session
  (`start_new_session`), so `killpg` reaches the family it spawned — the shape
  `core/tools/_shell_proc.py` already proved for the shell tool.
- Classification is the fixed `STATUSES` vocabulary, never an exception string.
  Task #10 turns `sandbox_unavailable` into its coded refusal; nothing here
  invents a second code beside it.

The OS boundary itself comes from `core.mcp_sandbox`, reused in place: its builders
produce the profile or the mounts, and this module only appends the descriptor's declared read-roots,
where the last rule wins in Seatbelt and the bind order wins in bubblewrap.
"""
from __future__ import annotations

import contextvars
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from core import mcp_sandbox
from core.sandbox.worker_spec import MEMORY_CEILING_MARKER, WorkerSpec
from core.secret_broker import child_env


@dataclass
class BoundedBuffer:
    """A cap that preserves the tail. A tracebacks worthlessness at the head is why
    the tail is 3/4 of the budget (the pattern in `core/tools/code_kernel.py`)."""

    cap_bytes: int

    def __post_init__(self) -> None:
        self.cap_bytes = max(256, int(self.cap_bytes))
        self._head_budget = self.cap_bytes // 4
        self._tail_budget = self.cap_bytes - self._head_budget
        self._head = bytearray()
        self._tail = bytearray()
        self.total = 0

    def feed(self, chunk: bytes) -> None:
        self.total += len(chunk)
        if len(self._head) < self._head_budget:
            take = self._head_budget - len(self._head)
            self._head += chunk[:take]
            chunk = chunk[take:]
        if not chunk:
            return
        self._tail += chunk
        if len(self._tail) > self._tail_budget:
            del self._tail[: len(self._tail) - self._tail_budget]

    @property
    def dropped(self) -> int:
        return max(0, self.total - len(self._head) - len(self._tail))

    def render(self) -> str:
        if not self.dropped:
            return bytes(self._head + self._tail).decode("utf-8", "replace")
        marker = (
            f"\n...[{self.dropped} bytes not passed - cap {self.cap_bytes}, "
            "tail preserved, head kept for the first line]\n"
        )
        return bytes(self._head).decode("utf-8", "replace") + marker + bytes(self._tail).decode(
            "utf-8", "replace"
        )


def _drain(stream, buffer: BoundedBuffer) -> None:
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            buffer.feed(chunk)
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _drain_with_bridge(stream, buffer: BoundedBuffer, proc, dispatch, stdin_lock) -> None:
    """Read the worker's stdout line by line, answering bridge requests as they appear.

    Two kinds of line come out of a bridged run and only one of them is the worker's answer.
    A bridge request is dispatched here and its reply goes back on stdin; everything else is
    fed to the bounded buffer, so what `run_plugin_tool` classifies is still one result line
    and #47's caps keep their exact meaning.

    Line-based rather than chunk-based, because a request has to be answered before the child
    continues: the child writes one line and blocks on its reply, and a chunk reader would be
    sitting on the answer it is meant to send.

    The read is bounded by the bridge's own byte ceiling. A tool's answer is bounded by
    `output_cap_bytes` through the buffer, but a request line never reaches the buffer, and
    an unbounded `readline()` would let a plugin make this thread hold as much as it could
    write. Past the ceiling the child is refused with a code and its bytes go to the buffer,
    where the classifier turns them into a protocol error.
    """
    from core.sandbox import bridge

    ceiling = bridge.MAX_BRIDGE_BYTES
    answered = False
    try:
        while True:
            line = stream.readline(ceiling + 1)
            if not line:
                break
            if len(line) > ceiling and not line.endswith(b"\n"):
                _send(proc, stdin_lock, bridge.encode_refusal(
                    0, bridge.PAYLOAD_TOO_LARGE, f"a request is capped at {ceiling} bytes"
                ))
                buffer.feed(line)
                continue
            text = line.decode("utf-8", "replace")
            if not bridge.is_bridge_line(text):
                buffer.feed(line)
                if not answered:
                    # The answer is the last line the launcher writes. Closing stdin here
                    # restores the EOF the plain path always promised, because once the
                    # answer has arrived the bridge has nothing more to send.
                    answered = True
                    _close_stdin(proc, stdin_lock)
                continue
            reply = _bridge_reply(bridge.parse_request(text), dispatch)
            if not _send(proc, stdin_lock, reply):
                # The child is gone. Its answer never arrives, and the outcome the parent
                # reports is the one the exit status gives.
                break
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _send(proc, stdin_lock, line: str) -> bool:
    """One reply onto the child's stdin; whether the pipe is still there."""
    try:
        with stdin_lock:
            proc.stdin.write(line.encode("utf-8", "replace"))
            proc.stdin.flush()
        return True
    except (OSError, ValueError):
        return False


def _close_stdin(proc, stdin_lock) -> None:
    try:
        with stdin_lock:
            proc.stdin.close()
    except (OSError, ValueError):
        pass


def _bridge_reply(request, dispatch) -> str:
    """One reply line. A request the parser rejected is answered, never ignored.

    Silence here would leave the child blocked on a read that only ends when the process is
    killed at the wall clock, and a timeout is the worst possible report for a malformed
    line: it says the tool was slow when it said the plugin sent something unreadable.
    """
    from core.sandbox import bridge

    if request is None:
        return bridge.encode_refusal(0, bridge.ARGS_INVALID, "the request was not an envelope")
    try:
        answer = dispatch(request)
    except Exception as exc:  # noqa: BLE001 — the drain must answer whatever happens
        return bridge.encode_refusal(
            request["id"], bridge.INTERNAL, f"{type(exc).__name__}"
        )
    if answer.get("ok"):
        return bridge.encode_reply(request["id"], answer.get("result"))
    return bridge.encode_refusal(
        request["id"], str(answer.get("code") or bridge.INTERNAL), str(answer.get("detail") or "")
    )


def _write_stdin_open(proc, payload: str, lock) -> None:
    """Write the request and leave stdin open: the bridge answers on it.

    The plain path closes stdin so a reading worker sees EOF. A bridged worker reads again
    later, for its reply, and an EOF there is a dead pipe rather than an answer.

    The lock is shared with the drain. Two threads write one pipe here — this thread the
    request, the drain the replies — and a large argument payload can leave part of itself
    in the kernel buffer while the other thread starts writing. A child reading that stream
    gets one line with the other's bytes in the middle of it, which reads as a broken tool.
    """
    try:
        with lock:
            proc.stdin.write(payload.encode("utf-8", "replace"))
            proc.stdin.flush()
    except (OSError, ValueError):
        pass


def _write_stdin(proc, payload: str) -> None:
    """Hand the worker its request, then close stdin so a reading worker sees EOF.

    A worker that never reads is not this caller's problem: the write is bounded by
    the payload size and a broken pipe is swallowed, matching the drain's restraint.
    """
    try:
        proc.stdin.write(payload.encode("utf-8", "replace"))
    except (OSError, ValueError):
        pass
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass


def confined_argv(
    command: str, args: list[str], home: str, extra_read_roots: list[str] | None = None
) -> list[str] | None:
    """The child argv under the platform boundary — or None, which means do not spawn.

    On macOS: `sandbox-exec` with `mcp_sandbox.build_profile` (whole-home deny,
    child-home writes, measured runtime prefixes) plus one appended read-only
    allow per declared root; Seatbelt's last-rule-wins makes the append exact, and
    an undeclared path still sits behind the deny. On Linux: the same bubblewrap
    mounts with each declared root bound read-only. Anywhere else: None.
    """
    boundary = mcp_sandbox.platform_boundary()
    if boundary == "seatbelt":
        # Plugin workers ask for the network deny. The connector rail keeps its
        # sockets. This child reaches the host through the bridge.
        profile = mcp_sandbox.build_profile(home, command, deny_network=True)
        profile += "".join(
            f'(allow file-read* (subpath "{os.path.realpath(root)}"))\n'
            for root in extra_read_roots or []
        )
        return ["sandbox-exec", "-p", profile, command, *args]
    if boundary == "bubblewrap":
        argv = list(mcp_sandbox.build_bwrap(home, command, deny_network=True))
        for root in extra_read_roots or []:
            real = os.path.realpath(root)
            argv += ["--ro-bind", real, real]
        return [*argv, "--chdir", os.path.realpath(home), command, *args]
    return None


def _kill_group(pgid: int) -> None:
    """SIGTERM the family, then SIGKILL.

    Measured on this macOS: a signal to a process group whose only remaining
    members are unreaped zombies is refused with EPERM (where POSIX would say
    ESRCH). A TERM that already emptied the group of live processes therefore
    makes the follow-up KILL raise; the rejection reads as nothing live left to
    signal. `_group_gone` after the reap is the proof step, never this loop.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.05)


def _group_gone(pgid: int, window_s: float = 2.0) -> bool:
    """True once `killpg(pgid, 0)` reports no such group: every member dead and reaped.

    The bounded wait is the proof window; past it the answer is False and the
    caller says so rather than guessing. EPERM here is a leftover zombie —
    poll through it; ProcessLookupError is the group's death certificate.
    """
    deadline = time.monotonic() + window_s
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


@dataclass
class WorkerOutcome:
    """One classified run. `status` is always a member of `STATUSES`."""

    status: str
    exit_code: int | None = None
    signal_number: int | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_dropped: int = 0
    stderr_dropped: int = 0
    output_cap_bytes: int = 0
    timed_out: bool = False
    group_gone: bool = True
    duration_seconds: float = 0.0
    boundary: str = ""
    pgid: int | None = None
    note: str = ""
    #: `applied`, `refused`, `unknown` when the spec declared a ceiling, and empty when it
    #: declared none. The child is the one that asked the OS, so the child is what answers.
    memory_ceiling: str = ""


def _memory_ceiling(stderr: str, declared_mb: int) -> str:
    """The verdict the child's bootstrap reported about the ceiling it was handed."""
    if not declared_mb:
        return ""
    marker = f"{MEMORY_CEILING_MARKER} "
    for line in stderr.splitlines():
        if line.startswith(marker):
            return line[len(marker):].split(" ", 1)[0] or "unknown"
    return "unknown"


def run_worker(
    spec: WorkerSpec,
    *,
    protocol_check: Callable[[str], bool] | None = None,
    stdin_payload: str | None = None,
    bridge_dispatch: Callable[[dict], dict] | None = None,
) -> WorkerOutcome:
    """Run one confined worker and classify it. Never leaves the boundary question open.

    `stdin_payload` is the request handed to the worker on stdin; None (the #47 shape)
    closes stdin, so a worker that reads nothing sees EOF immediately.

    `bridge_dispatch` turns the #23 path on: with it, stdin stays open for replies and
    stdout is read line by line so a request can be answered while the tool still runs.
    Without it nothing about this function's behaviour changes, which is the reason the
    flag is an argument and not a new function.
    """
    started = time.monotonic()
    boundary = mcp_sandbox.platform_boundary()
    home = mcp_sandbox.home_for(f"plugin_{spec.plugin_id}")
    child = spec.child_argv()
    argv = confined_argv(child[0], child[1:], str(home), spec.read_roots())
    if argv is None:
        # The ordering is the guarantee: this returns before any Popen exists.
        return WorkerOutcome(
            status="sandbox_unavailable",
            boundary=boundary,
            output_cap_bytes=spec.output_cap_bytes,
            note="no OS boundary on this platform — the worker was not spawned "
            "(fail-closed; the refusal code is registered by task #10)",
        )

    env = child_env(home=home)
    env["PYTHONIOENCODING"] = "utf-8"
    out_buf = BoundedBuffer(spec.output_cap_bytes)
    err_buf = BoundedBuffer(spec.output_cap_bytes)
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(home),
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        return WorkerOutcome(
            status="protocol_error",
            boundary=boundary,
            output_cap_bytes=spec.output_cap_bytes,
            note=f"spawn failed: {exc}",
        )

    stdin_lock = threading.Lock()
    if stdin_payload is not None:
        threading.Thread(
            target=_write_stdin_open if bridge_dispatch else _write_stdin,
            args=(
                (proc, stdin_payload, stdin_lock)
                if bridge_dispatch
                else (proc, stdin_payload)
            ),
            daemon=True,
        ).start()
    stdout_reader = (
        _drain_with_bridge if bridge_dispatch else _drain
    )
    stdout_args = (
        (proc.stdout, out_buf, proc, bridge_dispatch, stdin_lock)
        if bridge_dispatch
        else (proc.stdout, out_buf)
    )
    # The stdout drain answers a bridge call. A desktop method reads the loop
    # the caller published, and this thread keeps that context from here.
    stdout_ctx = contextvars.copy_context()
    readers = [
        threading.Thread(
            target=stdout_ctx.run, args=(stdout_reader, *stdout_args), daemon=True
        ),
        threading.Thread(target=_drain, args=(proc.stderr, err_buf), daemon=True),
    ]
    for thread in readers:
        thread.start()

    timed_out = False
    group_gone = True
    try:
        proc.wait(timeout=spec.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc.pid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        group_gone = _group_gone(proc.pid)
    finally:
        for thread in readers:
            thread.join(timeout=2.0)
        if bridge_dispatch is not None:
            # Closed only now when the drain did not already see the answer: a pipe left open
            # past the wait is a leak the next run inherits.
            _close_stdin(proc, stdin_lock)

    rc = proc.returncode
    signal_number = -rc if (rc is not None and rc < 0) else None
    note = ""
    if timed_out:
        status = "timeout"
        note = f"killed at {spec.timeout_seconds}s wall-clock; process group gone: {group_gone}"
    else:
        if rc is None:
            status = "crashed"
        elif signal_number == int(signal.SIGKILL):
            # The exit-status path: an unasked-for SIGKILL is the kernel
            # out-of-memory killer's signature on Linux. On macOS the kernel
            # does not send one — a memory overrun shows up inside the child
            # (RLIMIT_AS raises) or as a nonzero/crashed exit. The exit status
            # carries the classification; no kernel kill was observed here.
            status = "oom"
            signal_number = int(signal.SIGKILL)
            note = (
                "classified from the exit status (unasked SIGKILL); the kernel's own "
                "out-of-memory kill is unmeasured on this platform"
            )
        elif signal_number is not None:
            status = "crashed"
            note = f"terminated by signal {signal_number}"
        elif rc > 0:
            status = "nonzero"
        else:
            status = "ok"
    if status == "ok" and protocol_check is not None and not protocol_check(out_buf.render()):
        status = "protocol_error"
        note = "worker exited 0 but its stdout failed the transport's framing check"

    return WorkerOutcome(
        status=status,
        exit_code=rc,
        signal_number=signal_number,
        stdout=out_buf.render(),
        stderr=err_buf.render(),
        stdout_dropped=out_buf.dropped,
        stderr_dropped=err_buf.dropped,
        output_cap_bytes=spec.output_cap_bytes,
        timed_out=timed_out,
        group_gone=group_gone,
        duration_seconds=round(time.monotonic() - started, 3),
        boundary=boundary,
        pgid=proc.pid,
        note=note,
        memory_ceiling=_memory_ceiling(err_buf.render(), spec.memory_cap_mb),
    )
