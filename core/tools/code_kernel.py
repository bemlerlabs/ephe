"""Ephe – stateful Python kernel (execute_code).

Reference-A parity: a persistent session namespace survives individual calls, so
multi-step computations (load data → transform → output) run without repeating
the imports/variables.

Design:
- A session-keyed register (_KERNELS) carries one own namespace (dict) per
  session across calls — no context leaking between sessions.
- stdout/stderr are redirected into a string buffer per call and returned
  (no loss of print output).
- Fail-closed: an error in user code does not break the kernel — the namespace
  is kept and the traceback line is returned as the error.
- reset=True establishes an empty namespace (a new "session").
"""
from __future__ import annotations

import io
import sys
import time
import traceback
import types
from contextlib import redirect_stdout

# Session-keyed kernel register: session_id → namespace (P0-2 isolation).
_KERNELS: dict[str, dict[str, object]] = {}
_KERNEL_EXEC_COUNT = 0
_EPHE_TOOLS_STUB: types.ModuleType | None = None

_MAX_STDOUT_CHARS = 20000
#: The tail that stays free at the cap — for tracebacks and "last line = result".
_STDOUT_TAIL_CHARS = 2_000


def _auto_approved() -> tuple[str, ...]:
    """Tools that also run outside the kernel without a dialog.

    The kernel has no approval dialog — so it may only expose what the gate lets
    through anyway. Lazy lookup, because the registry (MCP) keeps filling after
    the stub load.
    """
    from core.tools.approval import classify_tool
    from core.tools.registry import TOOL_MAP

    return tuple(name for name in TOOL_MAP if classify_tool(name).auto_approve_by_default)


def _refusal(name: str):
    """A refusal that is an action: back into the tool call, not silence."""

    def refused(*_args, **_kwargs):
        return (
            f"[ephe_tools] '{name}' is not reachable from the kernel — kernel code runs "
            "without an approval gate, and this tool needs one. End this "
            f"execute_code turn and call '{name}' as a tool directly; there Ephe asks."
        )

    return refused


def _make_ephe_tools_stub() -> types.ModuleType:
    """An ``ephe_tools`` stub so kernel code can write
    ``from ephe_tools import <tool>`` directly and call the registry tools in the
    same turn — instead of one model round trip per tool.

    The stub exposes only the auto-approved registry functions; names that need a
    gate answer with a refusal (``_refusal``), because otherwise a single
    auto-run call would rewrite every gate. async tools are synchronized through a
    ``tool_call`` helper (asyncio.run).
    """

    def _sync(fn):
        # Drive an async tool to completion inside the running loop (kernel exec
        # is not an await context). Outside a loop: the classic asyncio.run.
        import asyncio
        import inspect

        def wrapper(*args, **kwargs):
            coro = fn(*args, **kwargs)
            if not inspect.iscoroutine(coro):
                return coro
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                return loop.run_until_complete(coro)
            return asyncio.run(coro)

        return wrapper

    def _resolve(name: str):
        from core.tools.registry import TOOL_MAP

        if name == "TOOL_NAMES":
            return _auto_approved()
        if name not in TOOL_MAP:
            raise AttributeError(f"module 'ephe_tools' has no tool {name!r}")
        if name not in _auto_approved():
            return _refusal(name)
        return _sync(TOOL_MAP[name])

    def tool_call(name: str, **kwargs):
        from core.tools.registry import TOOL_MAP

        if name not in TOOL_MAP:
            return f"[tool_call] unbekanntes Tool: {name!r}"
        return _resolve(name)(**kwargs)

    module = types.ModuleType("ephe_tools")
    module.tool_call = tool_call
    # PEP 562: one attribute per lookup, so the filtering stays live and
    # an unknown name remains an AttributeError instead of becoming a phantom None.
    module.__getattr__ = _resolve
    return module



def _ensure_stub() -> types.ModuleType:
    """Lazy creation of the stub (after module initialization completes), so that
    the code_kernel <-> registry circular import does not fail at load time."""
    global _EPHE_TOOLS_STUB
    if _EPHE_TOOLS_STUB is None:
        _EPHE_TOOLS_STUB = _make_ephe_tools_stub()
        sys.modules["ephe_tools"] = _EPHE_TOOLS_STUB
    return _EPHE_TOOLS_STUB


def _reset_kernel(ns: dict[str, object]) -> None:
    ns.clear()
    ns["__name__"] = "__ephe_kernel__"
    # Set the stub only if it has already been created (lazy, see _ensure_stub).
    if _EPHE_TOOLS_STUB is not None:
        ns["ephe_tools"] = _EPHE_TOOLS_STUB


def _kernel_for(session_id: str) -> dict[str, object]:
    """Fetches the session's namespace (initialized fresh when needed)."""
    ns = _KERNELS.get(session_id)
    if ns is None:
        ns = {}
        _KERNELS[session_id] = ns
        _reset_kernel(ns)
    return ns


async def execute_code(code: str, reset: bool = False) -> str:
    """Runs model Python — by default inside the pinned CPython cell.

    The cell is the third security layer (docs/SANDBOX_EXECUTION.md): fuel,
    memory, file and network caps around the same code that previously ran
    in-process with full host access. ``EPHE_CODE_EXEC=kernel`` is the explicit
    opt-out and names its consequence in every result; an installed but unfitting
    guest does not fall back, it refuses.

    The kernel path is not auto-run: because it executes with full host access,
    ``execute_code`` counts as MUTATING while the cell does not carry the turn, so
    the approval gate stands in front of it (decision W3-15, core.tools.approval).
    Contained runs stay auto-run: the licence is the cell itself.

    Args:
        code: The Python source to execute.
        reset: True → empty the namespace first (a new "session").

    Returns:
        Result text with the runtime receipt (runtime/status/caps) before the output.
    """
    from core import cpython_cell, ephemeral_cell
    from core.tools.session_ctx import get_current_session

    refused = cpython_cell.exec_choice_error()
    if refused:
        return f"[execute_code] {refused}"

    sid = get_current_session()
    if cpython_cell.exec_runtime() == cpython_cell.RUNTIME_CELL:
        if not (code or "").strip():
            return cpython_cell.format_report(_empty_report(cpython_cell.RUNTIME_CELL))
        report = await cpython_cell.run_python(code, sid, reset=reset)
        # WP5: without this call the cell registry stays empty in the product, and
        # the lifetime line would assert something that never ran. The number comes
        # from the guest report (elapsed_ms), not from a clock on the side.
        ephemeral_cell.record_call(
            sid, float(report.get("elapsed_ms") or 0.0),
            kind=ephemeral_cell.KIND_WASI,
        )
        return cpython_cell.format_report(report)

    if not (code or "").strip():
        return cpython_cell.format_report(_empty_report(cpython_cell.RUNTIME_KERNEL))
    started = time.monotonic()
    out = await _execute_in_kernel(code, sid, reset=reset)
    ephemeral_cell.record_call(
        sid, (time.monotonic() - started) * 1000, kind=ephemeral_cell.KIND_KERNEL
    )
    return out


def _empty_report(runtime: str) -> dict:
    return {
        "runtime": runtime,
        "status": "SKIPPED",
        "stdout": "[execute_code] leerer Code-Block",
        "stderr": "",
        "names": [],
        "dropped": [],
        "preopens": [],
    }


async def _execute_in_kernel(code: str, sid: str, *, reset: bool = False) -> str:
    """The unsandboxed path: persistent in-process namespace (opt-out)."""
    global _KERNEL_EXEC_COUNT

    ns = _kernel_for(sid)
    if reset:
        _reset_kernel(ns)
    # Activate the stub lazily (after module load, no cycle left) + provide it in
    # the namespace so `from ephe_tools import ...` works inside the kernel.
    ns["ephe_tools"] = _ensure_stub()

    _KERNEL_EXEC_COUNT += 1
    try:
        compiled = compile(code, f"<ephe-kernel-{_KERNEL_EXEC_COUNT}>", "exec")
    except SyntaxError as exc:
        line, offset = exc.lineno or 0, exc.offset or 0
        return (cpython_cell_header("SYNTAX_ERROR")
                + f"[execute_code] SyntaxError (Zeile {line}, Spalte {offset}): {exc.msg}")

    def _run_in_worker() -> tuple[str, str]:
        # Own worker thread = no running loop → the tool wrappers can drive
        # async tools to completion via asyncio.run (reference-A parity: multi tool
        # in the same turn). stdout is process-global; one kernel runs per process.
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                exec(compiled, ns)  # noqa: S102 — deliberate kernel exec
        except Exception:
            err = "".join(traceback.format_exc(limit=8)).strip()
            return buf.getvalue(), err
        return buf.getvalue(), ""

    import asyncio as _aio
    out, error = await _aio.to_thread(_run_in_worker)
    body = out
    if error:
        body = (body + "\n" if body else "") + f"[execute_code] {error}"
    if len(body) > _MAX_STDOUT_CHARS:
        # A head alone cut away the very line it was about: errors and results
        # sit at the end. The kernel buffers in memoria — there is no remainder.
        head = body[:_MAX_STDOUT_CHARS - _STDOUT_TAIL_CHARS]
        tail = body[-_STDOUT_TAIL_CHARS:]
        lost = len(body) - len(head) - len(tail)
        body = head + f"\n…[{lost} Zeichen nicht uebergeben — keine Rueckhol-Route im Kernel]\n" + tail
    if not body.strip():
        body = "[execute_code] ran (no output)"
    return cpython_cell_header("ERROR" if error else "OK") + body


def cpython_cell_header(status: str) -> str:
    """The one line the kernel puts before its result: runtime and consequence."""
    from core import cpython_cell

    return f"[execute_code] runtime={cpython_cell.RUNTIME_KERNEL} status={status} {cpython_cell.KERNEL_UNSANDBOXED_NOTE}\n"


def kernel_state(session_id: str | None = None) -> dict[str, object]:
    """Introspection: the variable names in a session's kernel (tests/diagnostics)."""
    from core.tools.session_ctx import get_current_session

    sid = session_id or get_current_session()
    ns = _KERNELS.get(sid, {})
    return {"names": sorted(k for k in ns if not k.startswith("__")),
            "exec_count": _KERNEL_EXEC_COUNT}
