"""Ephe CPython cell boot loader — runs INSIDE the WASI cell, never in the host.

The host puts ``program.py`` (the model) and optionally ``state.pkl`` (variables
from the previous run) into the preopen ``/work``. This script rebuilds the
namespace, runs ``program.py`` and writes the namespace back — variables thus
survive individual cell runs without an interpreter process having to keep
running.

What the guest does NOT have: network, fork/exec, host files and tools with an
approval gate. ``ephe_tools`` answers with the same refusal as in the in-process
kernel and shows the way through the tool-call gate.

The host reads ``result.json`` (names, status, truncated variables) and the
stream logs ``/work/stdout.log`` / ``/work/stderr.log``.

Output is not a free pass: from ~11,000 bytes per stream the cell sink throws
``OSError: [Errno 29] I/O error`` INSIDE the guest — measured 2026-10-02. A model
that prints a large JSON therefore crashes on its own print and, on top of that,
sees half an output. So this boot tees every output completely into ``/work`` and
lets only a remainder under the sink through the real fd. (Limit: code that
writes ``os.write(1, …)`` straight into fd 1 bypasses the tee and still faults —
that is a known, documented edge.)
"""
from __future__ import annotations

import io
import json
import os
import pickle
import sys
import traceback
import types

WORK = "/work"
PROGRAM = os.path.join(WORK, "program.py")
STATE = "/work/state.pkl"
RESULT = "/work/result.json"
STDOUT_LOG = "/work/stdout.log"
STDERR_LOG = "/work/stderr.log"

#: Bytes per stream that may reach the real fd. Safely under the sink wall
#: (``SINK_CEILING_BYTES``), so normal output passes unchanged and the wall is
#: simply never hit.
FORWARD_BYTES = 2_048
#: Largest write amount of the logs — /work is under a disk quota, and a
#: runaway print must not eat the space the program itself needs.
TEE_CAP_BYTES = 512 * 1024

_REFUSAL = (
    "[ephe] '{name}' is not reachable from the cell — the guest runs without an "
    "approval gate and without host access. End this execute_code turn and "
    "call '{name}' as a tool directly; there Ephe asks."
)


def _make_ephe_tools() -> types.ModuleType:
    """An `ephe_tools` module that only refuses — and does so even via import.

    The in-process kernel hands auto-approved host tools through; inside the cell
    there is no host context left. So that `from ephe_tools import run_shell` does
    not end as ModuleNotFoundError (which would mislead the model), the module
    exists — and every answer to it is the action that leads back to the real
    gate.
    """

    def _refused(name):
        def call(*_args, **_kwargs):
            return _REFUSAL.format(name=name)

        return call

    def _getattr(item):
        if item.startswith("__"):
            raise AttributeError(item)
        return _refused(item)

    module = types.ModuleType("ephe_tools")
    module.__dict__["TOOL_NAMES"] = ()
    module.__dict__["tool_call"] = lambda name, **_kw: _REFUSAL.format(name=name)
    module.__dict__["__getattr__"] = _getattr
    return module


def _install_ephe_tools() -> types.ModuleType:
    module = _make_ephe_tools()
    sys.modules["ephe_tools"] = module  # the import path, not just the namespace
    return module


def _load_namespace() -> dict:
    ns: dict[str, object] = {"__name__": "__ephe_cell__", "ephe_tools": _install_ephe_tools()}
    if not os.path.exists(STATE):
        return ns
    try:
        with open(STATE, "rb") as fh:
            stored = pickle.load(fh)
        if isinstance(stored, dict):
            ns.update(stored)
            ns["ephe_tools"] = _install_ephe_tools()
    except Exception:  # noqa: BLE001 — a foreign/damaged state is an empty state
        traceback.print_exc(file=sys.stderr)
        print("[ephe] state.pkl unlesbar — Namespace startet leer", file=sys.stderr)
    return ns


def _store_namespace(ns: dict) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    payload: dict[str, object] = {}
    for key, value in ns.items():
        if key.startswith("__") or key == "ephe_tools":
            continue
        try:
            payload[key] = value
            pickle.dumps(value)
        except Exception:
            payload.pop(key, None)
            dropped.append(key)
            continue
        kept.append(key)
    tmp = STATE + ".tmp"
    with open(tmp, "wb") as fh:
        pickle.dump(payload, fh, protocol=4)
    os.replace(tmp, STATE)
    return sorted(kept), sorted(dropped)


def main() -> None:
    # Tees go up before the namespace: the damaged-state report is a host diagnostic
    # and must reach the journal, which exists only once the streams are redirected.
    counters = _install_tees()
    ns = _load_namespace()
    status = "ok"
    try:
        with open(PROGRAM, "r", encoding="utf-8") as fh:
            source = fh.read()
        compiled = compile(source, "<ephe-cell>", "exec")
    except SyntaxError as exc:
        line, offset = exc.lineno or 0, exc.offset or 0
        print(f"[ephe-cell] SyntaxError (Zeile {line}, Spalte {offset}): {exc.msg}", file=sys.stderr)
        _write_result("syntax-error", [], [], counters)
        return
    except OSError as exc:
        print(f"[ephe-cell] {PROGRAM} cannot be read: {exc}", file=sys.stderr)
        _write_result("io-error", [], [], counters)
        return

    sys.argv = ["<ephe-cell>", *[a for a in sys.argv[1:] if a != "--"]]
    try:
        exec(compiled, ns)  # noqa: S102 — the deliberate exec point, sealed inside the cell
    except SystemExit as exc:  # sys.exit() in the model code is not an error
        status = "ok" if not exc.code or exc.code == 0 else f"exit:{exc.code}"
    except BaseException:  # noqa: BLE001 — the traceback goes to the host as an error report
        traceback.print_exc(file=sys.stderr)
        status = "error"

    try:
        kept, dropped = _store_namespace(ns)
    except OSError as exc:  # /work full or unwritable — the variables are gone, the output is not
        print(f"[ephe-cell] state could not be written: {exc}", file=sys.stderr)
        kept, dropped = [], sorted(k for k in ns if not k.startswith("__") and k != "ephe_tools")
    _flush_tees(counters)
    _write_result(status, kept, dropped, counters)


class _BoundedTee(io.RawIOBase):
    """Full byte count, completeness on file, the rest under the sink.

    ``write`` always answers with the full length — the writer must not believe it
    was dropped. Whatever is lost is lost to the channel, not to the session.

    The log is a **journal across all runs of one session**: each run notes its own
    byte range instead of deleting the file. Otherwise "fetch the rest" would be an
    empty promise — the next run would already have torn up the previous one's
    paper.
    """

    def __init__(self, inner, log_path: str, forward_limit: int, start: int) -> None:
        self._inner = inner
        self._log_path = log_path
        self._limit = forward_limit
        self._log_fh = None
        self.start = start
        self.total_bytes = 0
        self.forwarded_bytes = 0
        self.log_bytes = 0
        self.log_path = log_path

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        payload = bytes(data)
        self.total_bytes += len(payload)
        if self.forwarded_bytes < self._limit and payload:
            room = self._limit - self.forwarded_bytes
            try:
                self._inner.write(payload[:room])
                self.forwarded_bytes += room if len(payload) >= room else len(payload)
            except OSError:
                self._limit = self.forwarded_bytes
        self._log(payload)
        return len(payload)

    def _log(self, payload: bytes) -> None:
        room = TEE_CAP_BYTES - self.log_bytes
        if room <= 0 or not payload:
            return
        if self._log_fh is None:
            try:
                # appending, unbuffered: a trap in the guest must not bury a
                # partial buffer in an already closed process
                self._log_fh = open(self._log_path, "ab", buffering=0)
            except OSError:
                return
        try:
            written = self._log_fh.write(payload[:room]) or 0
            self.log_bytes += written
        except OSError:
            self._log_fh = None

    def flush(self) -> None:
        try:
            self._inner.flush()
        except OSError:
            pass

    def write_through(self, text: str) -> None:
        """One line past the byte count and past the forward cap — the channel
        itself, not what the program wrote."""
        try:
            self._inner.write(text.encode("utf-8"))
        except OSError:
            pass

    def close(self) -> None:
        if self._log_fh is not None:
            try:
                self._log_fh.close()
            except OSError:
                pass
            self._log_fh = None
        super().close()


def _journal_start(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _wrap_stream(name: str, log_path: str):
    stream = getattr(sys, name)
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return None
    tee = _BoundedTee(buffer, log_path, FORWARD_BYTES, _journal_start(log_path))
    setattr(sys, name, io.TextIOWrapper(
        io.BufferedWriter(tee), encoding="utf-8", errors="replace",
        newline="\n", line_buffering=True,
    ))
    return tee


def _install_tees() -> dict[str, object]:
    """Redirect both streams; a guest without .buffer keeps the old behaviour."""
    tees = {}
    for name, log in (("stdout", STDOUT_LOG), ("stderr", STDERR_LOG)):
        tee = _wrap_stream(name, log)
        if tee is not None:
            tees[name] = tee
    return {"tees": tees}


def _flush_tees(counters: dict[str, object]) -> None:
    for name in ("stdout", "stderr"):
        stream = sys.stdout if name == "stdout" else sys.stderr
        try:
            stream.flush()
        except Exception:  # noqa: BLE001 — a broken channel must not tip the report
            pass
    tees = counters.get("tees") or {}
    stdout_tee = tees.get("stdout")
    if stdout_tee is None or stdout_tee.total_bytes <= stdout_tee.forwarded_bytes:
        return
    if stdout_tee.log_bytes >= stdout_tee.total_bytes:
        rest = f"vollstaendig {stdout_tee.log_path}"
    else:
        rest = f"{stdout_tee.log_bytes} von {stdout_tee.total_bytes} Byte gesichert"
    stdout_tee.write_through(f"\n[ephe-cell] stdout {stdout_tee.total_bytes} Byte, "
                             f"{stdout_tee.forwarded_bytes} uebergeben — {rest}\n")


def _stream_counts(counters: dict[str, object]) -> dict[str, object]:
    tees = counters.get("tees") or {}
    out: dict[str, object] = {}
    for name, tee in tees.items():
        out[f"{name}_bytes"] = tee.total_bytes
        out[f"{name}_forwarded_bytes"] = tee.forwarded_bytes
        out[f"{name}_log"] = tee.log_path
        out[f"{name}_log_start"] = tee.start
        out[f"{name}_log_bytes"] = tee.log_bytes
    return out


def _write_result(status: str, kept: list[str], dropped: list[str],
                  counters: dict[str, object] | None = None) -> None:
    try:
        payload = {"status": status, "names": kept, "dropped": dropped}
        payload.update(_stream_counts(counters or {}))
        with open(RESULT, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except OSError:
        pass


if __name__ == "__main__":
    # No SystemExit with a status: that lives in result.json. A non-zero exit
    # would make Ephemora report ERROR with a host traceback and bury the model's
    # stdout in noise.
    main()
