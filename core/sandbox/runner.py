"""Confined runner for a dynamic plugin tool: resolve an entry, run it in a child, answer.

Ruling A1 in code. Nothing here imports a plugin module, calls its entry or holds a
callable in the backend process. The descriptor's `module:callable` text is resolved
to a file inside the plugin directory with `core.plugin_manifest._under`, and that
file is read and imported only inside the confined child that `core.sandbox.run_worker`
starts. The backend writes one JSON request to the child's stdin and reads one JSON
response from its stdout; if the reply does not parse, the run is a protocol error.

`Never importlib, never exec, in this process` — a later edit that resolves the entry
here is the defect this docstring exists to keep out.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from core import mcp_sandbox, plugin_state
from core.dynamic_refusals import (
    PLUGIN_ENTRY_REFUSED,
    PLUGIN_STATE_FULL,
    SANDBOX_UNAVAILABLE,
)
from core.sandbox import bridge_host
from core.sandbox.restart_budget import Refusal, RestartBudget
from core.sandbox.supervisor import WorkerOutcome, run_worker
from core.sandbox.worker_spec import build_spec

#: The child-side launcher, run as `__main__` inside the confined process.
LAUNCHER = str(Path(__file__).with_name("worker_launcher.py"))

#: A death that spends the restart budget; a refusal or a good run does not.
_DEATH_STATUSES = frozenset({"timeout", "crashed", "nonzero", "oom", "protocol_error"})


@dataclass
class RunResult:
    """One confined run mapped for the transport: a status, a surface, a message."""

    status: str
    kind: str          # result, error, refusal
    text: str
    code: str = ""
    #: the slots a surface fills its own sentence from — the two numbers of a state refusal,
    #: and nothing else. A path never rides here; the trail is read by every surface.
    params: dict | None = None


def _is_json_line(text: str) -> bool:
    """The framing check #47 runs on stdout: one JSON object, nothing else."""
    try:
        return isinstance(json.loads(text), dict)
    except (ValueError, TypeError):
        return False


def _entry_parts(entry: str) -> list[str]:
    """The plugin-relative file parts a `module:callable` entry points at."""
    parts = str(entry).rpartition(":")[0].split(".")
    parts[-1] += ".py"
    return parts


def resolve_entry_file(plugin_dir: Path | str, entry: str) -> tuple[Path | None, str]:
    """Map `module:callable` to a file inside the plugin dir, or say why it cannot.

    The containment rule is `_under`, the same one the manifest applies: the dotted
    module becomes a path under the real plugin directory and a `..`, an absolute
    path or a symlink that steps out resolves outside and is refused here, before any
    process is started.
    """
    head, sep, callable_name = str(entry).rpartition(":")
    if not sep or not head or not callable_name.isidentifier():
        return None, f"entry {entry!r} is not a module:callable pair"
    parts = head.split(".")
    if not all(part.isidentifier() for part in parts):
        return None, f"entry {entry!r} names an unusable module path"
    parts[-1] += ".py"
    from core.plugin_manifest import _under

    target = _under(Path(plugin_dir), *parts)
    if target is None:
        return None, f"entry {entry!r} resolves outside the plugin directory"
    if not target.is_file():
        return None, f"entry {entry!r} is not a file inside the plugin directory"
    return target, ""


def resolve_plugin_dir(plugin_id: str) -> Path | None:
    """The manifest directory a plugin id names, from the same scan activations use."""
    from core import plugin_manifest

    try:
        scanned = plugin_manifest.scan_plugins(None)
    except Exception:  # noqa: BLE001 - a broken portfolio is not a crash here
        return None
    for record in scanned:
        manifest = record.get("manifest")
        if isinstance(manifest, dict) and str(manifest.get("name")) == plugin_id:
            return Path(record["dir"])
    return None


def _denied_line(name: str, reason_text: str) -> str:
    """A call that was refused before it ran, in the words the approval gate already uses."""
    return f"[TOOL-DENIED] plugin tool '{name}' was not run: {reason_text}"


def _state_gate(descriptor, home: Path, cap: int, used: int) -> RunResult:
    """The refusal for a bundle that has spent the ceiling it lives under."""
    used_mb = max(1, round(used / plugin_state.MB))
    cap_mb = round(cap / plugin_state.MB)
    return RunResult(
        "state_full",
        "refusal",
        _denied_line(
            descriptor.name,
            f"its stored data holds {used_mb} MB of the {cap_mb} MB this bundle may keep — "
            "open this bundle on Extensions and remove a stored file there, then run "
            "the tool again",
        ),
        code=PLUGIN_STATE_FULL,
        params={"used_mb": str(used_mb), "cap_mb": str(cap_mb)},
    )


def _error_line(name: str, reason_text: str, detail: str) -> str:
    tail = f"\n{detail}" if detail else ""
    return f"[TOOL-ERROR] plugin tool '{name}' {reason_text}.{tail}".rstrip()


def _reason_from_envelope(result: dict):
    """The sentence plus the code a kernel tool put on it, restored as one value.

    A worker that returns any other object keeps that object as JSON. This
    envelope is the page tool's refusal: the model reads the sentence, and the
    code stays on it for the refusal channel and the audit decision.
    """
    if not isinstance(result, dict):
        return None
    if "text" not in result or "code" not in result:
        return None
    if not set(result) <= {"text", "code", "params", "happened"}:
        return None
    code = str(result.get("code") or "")
    if not code:
        return None
    params = result.get("params")
    clean = (
        {str(key): str(value) for key, value in params.items()}
        if isinstance(params, dict)
        else {}
    )
    from core.reason import Reason

    return Reason(
        str(result.get("text") or ""), code, clean, happened=bool(result.get("happened")),
    )


def _classify(name: str, outcome: WorkerOutcome, spec_timeout: float) -> RunResult:
    """Map a supervisor status to a model-facing result, with no traceback or host path."""
    if outcome.status == SANDBOX_UNAVAILABLE:
        return RunResult(
            status=outcome.status,
            kind="refusal",
            code=SANDBOX_UNAVAILABLE,
            text=(
                "[TOOL-DENIED] this plugin tool was not spawned: no OS boundary is "
                "available on this machine, and confinement is required to run it"
            ),
        )
    if outcome.status == "timeout":
        return RunResult("timeout", "error", _error_line(
            name, f"timed out after {spec_timeout:g}s and its process group was killed", ""
        ))
    if outcome.status == "protocol_error":
        return RunResult("protocol_error", "error", _error_line(
            name, "returned a reply that could not be read", ""
        ))
    if outcome.status == "crashed":
        return RunResult("crashed", "error", _error_line(
            name, f"was terminated by signal {outcome.signal_number}", outcome.stderr
        ))
    if outcome.status == "oom":
        return RunResult("oom", "error", _error_line(
            name, "ran out of the memory it was given", outcome.stderr
        ))
    if outcome.status == "nonzero":
        refused = mcp_sandbox.start_refusal(outcome.stderr)
        if refused is not None:
            # The boundary refused the child's own exec: the worker never ran. The raw
            # line names `execvp` and a host path, so the sandbox module turns it into a
            # code, a reason and the move; the stderr itself stays out of the answer.
            return RunResult(
                "start_refused",
                "refusal",
                f"[TOOL-DENIED] plugin tool '{name}' was not started: {refused.sentence()}",
                code=refused.code,
            )
        return RunResult("nonzero", "error", _error_line(
            name, f"exited with code {outcome.exit_code}", outcome.stderr
        ))
    # status == "ok": the single stdout line is the worker's own verdict.
    try:
        response = json.loads(outcome.stdout)
    except (ValueError, TypeError):
        return RunResult("protocol_error", "error", _error_line(
            name, "returned a reply that could not be read", ""
        ))
    if not response.get("ok"):
        return RunResult("tool_error", "error", _error_line(
            name, f"reported an error ({response.get('error')})", outcome.stderr
        ))
    result = response.get("result")
    if isinstance(result, dict):
        restored = _reason_from_envelope(result)
        text = restored if restored is not None else json.dumps(result, default=str)
    elif isinstance(result, str):
        text = result
    else:
        text = json.dumps(result, default=str)
    return RunResult("ok", "result", text)


_BUDGETS: dict[str, RestartBudget] = {}
_BUDGET_LOCK = threading.Lock()


def worker_data_roots(plugin_id: str) -> tuple[str, ...]:
    """The declared data roots the boundary can actually bind, and how many it could not.

    The declaration used to reach one rail: a plugin that asked a kernel tool to read a
    declared root got it, while a v2 tool of the same bundle, running confined, saw nothing of
    the line its own manifest wrote. Both rails read it through
    `capability_policy.resolved_data_roots` now, so one declaration means one set of paths.

    Validation refuses a declaration that is not a folder when the manifest loads, so this
    filter is the window between that read and the spawn: a root the disk gave up in between
    is left out of the profile, which binds nothing new, and the tool still runs. The
    turn hooks (`core/plugin_turn_hooks.py`) read this same function, so one declaration
    binds the same paths on both rails.
    """
    from core import engine_config
    from core.capability_policy import resolved_data_roots

    try:
        workspace = engine_config.validate_workspace_dir(engine_config.get_workspace_dir())
    except (OSError, ValueError):
        workspace = ""
    root = Path(workspace).resolve() if workspace else None
    return tuple(str(path) for path in resolved_data_roots(plugin_id, root) if path.is_dir())


def _state_extra(used: int, files: int, roots: int, cap: int) -> str:
    """The measurement the completion row carries: sizes, never paths."""
    return (
        f"state_bytes={used} state_files={files} state_roots={roots} state_cap_bytes={cap}"
    )


def _budget_for(plugin_id: str) -> RestartBudget:
    with _BUDGET_LOCK:
        return _BUDGETS.setdefault(plugin_id, RestartBudget())


def run_plugin_tool(
    descriptor, arguments: dict, plugin_dir: Path | str, *,
    timeout_seconds: float = 20.0, memory_cap_mb: int = 0,
    output_cap_bytes: int = 64 * 1024, budget: RestartBudget | None = None,
) -> RunResult:
    """Resolve the descriptor entry, run one confined worker, map its status to a result."""
    entry_file, error = resolve_entry_file(plugin_dir, descriptor.entry)
    if entry_file is None:
        return RunResult("refused", "refusal", _error_line(
            descriptor.name, "entry was refused before any worker started", ""
        ), code=PLUGIN_ENTRY_REFUSED)
    rel = "/".join(_entry_parts(descriptor.entry))
    home = mcp_sandbox.home_for(f"plugin_{descriptor.plugin_id}")
    host_roots = worker_data_roots(descriptor.plugin_id)
    spec, build_error = build_spec(
        plugin_id=descriptor.plugin_id, plugin_dir=plugin_dir, entry=rel,
        launcher=LAUNCHER, timeout_seconds=timeout_seconds, memory_cap_mb=memory_cap_mb,
        output_cap_bytes=output_cap_bytes, host_roots=host_roots,
    )
    if spec is None:
        return RunResult("refused", "refusal", _error_line(
            descriptor.name, "entry was refused before any worker started", ""
        ), code=PLUGIN_ENTRY_REFUSED)

    cap = plugin_state.cap_bytes(descriptor.plugin_id)
    used, files = plugin_state.usage(home)
    extra = _state_extra(used, files, len(host_roots), cap)
    if plugin_state.over(cap, used):
        # The gate stands before the worker: a run that could only add to a folder already at
        # its ceiling would be a promise that the ceiling means something.
        _audit("tool_start", descriptor, arguments)
        refused = _state_gate(descriptor, home, cap, used)
        _audit_run(descriptor, arguments, refused, extra)
        return refused

    request = json.dumps({
        "tool": descriptor.name, "arguments": arguments, "state_dir": str(home),
        "entry_file": str(spec.entry_path()), "callable": descriptor.entry.rpartition(":")[2],
    })
    _audit("tool_start", descriptor, arguments)
    identity = bridge_host.BridgeIdentity(
        plugin_id=descriptor.plugin_id,
        tool=descriptor.name,
        family=descriptor.tool_family,
        families=descriptor.families,
        fingerprint=descriptor.fingerprint,
    )
    state = bridge_host.RunState()
    outcome = run_worker(
        spec,
        protocol_check=_is_json_line,
        stdin_payload=request + "\n",
        bridge_dispatch=lambda line: bridge_host.dispatch(line, identity, state),
    )
    pending = state.take_confirmation()
    if pending is not None:
        # The kernel asked and nobody was there to answer. The turn sees that
        # raise. The child's error line is the same fact in another shape.
        raise pending
    result = _classify(descriptor.name, outcome, timeout_seconds)
    used, files = plugin_state.usage(home)
    extra = _state_extra(used, files, len(host_roots), cap)
    if budget is not None:
        verdict = _record(budget, result)
        if isinstance(verdict, Refusal):
            result = RunResult(
                "restart_exhausted", "refusal",
                _error_line(descriptor.name, verdict.message, ""), code=verdict.code,
            )
    _audit_run(descriptor, arguments, result, extra)
    return result


def _record(budget: RestartBudget, result: RunResult) -> object:
    if result.status == "ok":
        budget.record_success()
        return None
    if result.status in _DEATH_STATUSES:
        return budget.record_failure()
    return None


def execute(descriptor, arguments: dict) -> str | None:
    """Run a plugin-transport descriptor, or return None when its directory is not found.

    None is the "not ready yet" answer the transport keeps as `tool_not_available`;
    a resolved directory runs the confined worker and returns a model-facing string.
    """
    plugin_dir = resolve_plugin_dir(descriptor.plugin_id)
    if plugin_dir is None:
        return None
    timeout = 20.0
    if descriptor.name in {"vision_click", "vision_type"}:
        timeout = bridge_host.VISION_CALL_TIMEOUT_SECONDS
    elif descriptor.name == "analyze_image":
        # The kernel client has no clock of its own. This is the register's
        # non-streaming bound, plus time for the reply to be written.
        timeout = bridge_host.image_call_timeout_seconds()
    elif descriptor.name == "generate_image":
        # The generation client waits 120 seconds and a download waits 60.
        timeout = bridge_host.picture_call_timeout_seconds()
    elif descriptor.name in {"synthesize", "transcribe"}:
        timeout = bridge_host.voice_call_timeout_seconds()
    elif descriptor.name == "run_tests":
        timeout = bridge_host.test_call_timeout_seconds()
    elif descriptor.name == "build_document":
        timeout = bridge_host.brief_call_timeout_seconds()
    elif descriptor.name in {
        "create_pdf", "create_docx", "create_qrcode", "extract_pdf_text",
        "export_source_brief", "create_source_notebook", "query_source_notebook",
        "verify_artifact",
        "create_pptx_deck", "create_pitch_deck", "inspect_pptx_template",
        "edit_pptx_template", "qa_pptx_deck", "create_diagram", "create_svg",
    }:
        timeout = bridge_host.doc_call_timeout_seconds()
    elif descriptor.name in {"create_xlsx", "generate_chart"}:
        timeout = bridge_host.doc_call_timeout_seconds()
    elif descriptor.name in {
        "run_shell", "format_code", "run_linter",
        "file_search", "analyze_project", "load_workspace",
    }:
        timeout = bridge_host.shell_call_timeout_seconds()
    result = run_plugin_tool(
        descriptor, arguments, plugin_dir,
        timeout_seconds=timeout,
        budget=_budget_for(descriptor.plugin_id),
    )
    if result.kind == "refusal" and result.code:
        from core.reason import reason

        params = {"plugin": descriptor.plugin_id, **(result.params or {})}
        return reason(result.code, result.text, **params)
    return result.text


def _audit(
    kind: str, descriptor, arguments: dict, *, decision: str = "", status: str = "",
    extra: str = "",
) -> None:
    """One line in the existing trail: the call, and the identity of what owns it.

    `core.dynamic_refusals.rail_fields` writes the plugin id, the declared family, the
    transport and the short fingerprint. Nothing else from the descriptor crosses into
    the log — no entry text, no plugin directory, no source — because the trail is
    readable by every surface and a plugin's bytes are not a fact about a call.
    """
    try:
        from core.audit_log import audit_event
        from core.dynamic_refusals import rail_fields

        audit_event(
            kind,
            tool=descriptor.name,
            args=arguments,
            decision=decision,
            status=status,
            detail=f"{rail_fields(descriptor)} {extra}".strip(),
        )
    except Exception:  # noqa: BLE001 - the audit path must never break a run
        pass


def _audit_run(descriptor, arguments: dict, result: RunResult, extra: str = "") -> None:
    """The one completion row of a run: `tool_exec`, or `tool_refused` with its code.

    `extra` carries the run's own measurements — the bytes and files the bundle's state
    directory holds — because a number the surface cannot show is a number nobody acts on.
    """
    if result.kind == "refusal":
        _audit(
            "tool_refused", descriptor, arguments,
            decision=result.code or "refused", status="error",
        )
    elif result.kind == "error":
        _audit(
            "tool_exec", descriptor, arguments,
            decision="error", status="error", extra=extra,
        )
    else:
        from core.quality import is_error_result, result_decision

        # Empty unless the result names a blockade. Status already records the run.
        pronounced = result_decision(result.text)
        _audit(
            "tool_exec", descriptor, arguments,
            decision=pronounced,
            status="error" if is_error_result(result.text) else "ok",
            extra=extra,
        )
