"""Ephe – Tool registry: TOOL_MAP, execute_tool, get_tool_schemas."""

from __future__ import annotations

import inspect
import time

from core.artifact_markers import ARTIFACT_MARKER_PREFIXES
from core.reason import Reason
from core.tools.base import (
    TOOL_SCHEMA_CACHE_TTL_SECONDS,
    _TOOL_SCHEMA_CACHE,
    ShellConfirmationRequired,
)
from core.tools.approval import (
    ApprovalPolicy,
    request_approval,
)
from core.tools.task_tools import manage_tasks
from core.tools.web_search import web_search
from core.tools.fetch_tools import fetch_url
from core.tools.file_ops import (
    file_search,
    read_file,
    list_directory,
    edit_file,
    write_file,
    delete_file,
)
from core.tools.test_tools import run_tests
from core.tools.video_tools import create_video
from core.tools.source_tools import (
    create_source_notebook,
    query_source_notebook,
    export_source_brief,
)
from core.tools.system_tools import (
    discover_projects,
    analyze_project,
    get_datetime,
    load_workspace,
    analyze_image,
    take_screenshot,
    create_svg,
)
from core.tools.browser_tools import (
    _vision_click_wrapper,
    _vision_type_wrapper,
    browser_go,
    browser_screenshot,
    browser_click,
    browser_type,
    browser_press,
    browser_scroll,
    browser_evaluate,
    clipboard_read,
    clipboard_write,
    get_display_info,
    browser_exec,
)
from core.tools.chart_tools import generate_chart
from core.tools.pdf_tools import create_pdf
from core.tools.office_tools import create_docx, create_qrcode, create_xlsx
from core.tools.image_tools import generate_image
from core.tools.diagram_tools import create_diagram
from core.tools.verify_tools import verify_artifact
from core.tools.factory_tools import build_document, scaffold_project
from core.tools.deck_tools import (
    create_pitch_deck,
    create_pptx_deck,
    inspect_pptx_template,
    edit_pptx_template,
    qa_pptx_deck,
)
from core.tools.shell_tools import run_shell, task_output, task_stop
from core.tools.code_kernel import execute_code
from core.tools.todo_tools import todo_list
from core.tools.ask_gate import ASK_TOOL_SCHEMAS, ask_user
from core.tools.process_tools import process_manage
from core.tools.workbench_tools import (
    WORKBENCH_TOOL_SCHEMAS,
    read_cell_journal,
    read_transcript,
)
from core.tools.discovery import tool_search, tool_describe, tool_call
from core.tools.state_tools import memory, skill_manage
from core.tools.subagent_tool import spawn_agent, SPAWN_AGENT_SCHEMA


def _error_line(line: str, exc: BaseException) -> str:
    """An error line keeps the reason code its exception was raised with.

    The card resolves `reader.<code>`; without the code it can only show this sentence.
    """
    code = getattr(exc, "code", "")
    if not code:
        return line
    return Reason(line, code, dict(getattr(exc, "params", {}) or {}))


# J2: core LLM continuation — lazy import (core.swarm_v2 → core.chat → core.tools
# would otherwise be an initialization cycle while this module itself is loading).
async def _agent_message_impl(agent_id: str, message: str) -> str:
    from core.swarm_v2 import agent_message

    return await agent_message(agent_id, message)
from core.tools.utility_tools import (
    extract_pdf_text,
    format_code,
    run_linter,
    validate_json,
)
from core.tools.sandbox_tools import (
    SANDBOX_TOOL_SCHEMAS,
    is_available as sandbox_is_available,
    run_sandboxed_code,
)
from core.tools.mcp_client import get_mcp_tools, call_registered_mcp_tool
from core.tools._schemas import BASE_TOOL_SCHEMAS

# ── R40b (Z43): Pre/Post-tool hooks ─────────────────────────────────────────
# Module-global table: phase -> [(priority, seq, fn)]. Lower priority number
# = earlier; on a tie the registration order decides (seq).
# Pre:  fn(name, arguments) -> dict | None  (dict replaces the args chain)
# Post: fn(name, arguments, result) -> str | None  (str replaces the result)
# Every hook run is audited; a raising hook is tolerated, it must not break the call.
_TOOL_HOOKS: dict[str, list] = {"pre": [], "post": []}
_HOOK_SEQ = 0


def register_tool_hook(phase: str, fn, priority: int = 0) -> None:
    """Registers a hook ('pre' | 'post') with a priority (lower = earlier)."""
    global _HOOK_SEQ
    if phase not in _TOOL_HOOKS or not callable(fn):
        return
    _HOOK_SEQ += 1
    entries = _TOOL_HOOKS[phase]
    entries.append((int(priority), _HOOK_SEQ, fn))
    entries.sort(key=lambda t: (t[0], t[1]))


def clear_tool_hooks(phase: str | None = None) -> None:
    """Empties the hook table (as a whole or per phase)."""
    if phase in _TOOL_HOOKS:
        _TOOL_HOOKS[phase] = []
    else:
        _TOOL_HOOKS["pre"] = []
        _TOOL_HOOKS["post"] = []


def _run_tool_hooks(phase: str, name: str, value):
    """Folds the hooks of one phase; the last non-None return value wins.

    Errors from individual hooks land in an audit line while execution continues with
    the last good value (never an abort caused by hook noise).
    """
    from core.audit_log import audit_event

    for _prio, _seq, fn in list(_TOOL_HOOKS.get(phase, ())):
        try:
            if phase == "pre":
                out = fn(name, value)
                if out is not None:
                    value = out
            else:
                arguments, result = value
                out = fn(name, arguments, result)
                if out is not None:
                    result = str(out)
                value = (arguments, result)
            audit_event("hook", tool=name, status="ok", detail=phase)
        except Exception as exc:
            audit_event("hook", tool=name, status="error", detail=f"{phase}: {str(exc)[:160]}")
    return value


# ── P0-3 (deep audit 2026-09-14): typed evidence gate ─────────────────────────
# Holds every artifact tool call to returning a *_FILE: marker + ARTIFACT_VERIFIED.
# Runs automatically as a post hook with priority 100. The marker set comes from
# the single source in core/artifact_markers; it is never re-listed here.
_ARTIFACT_MARKERS: tuple[str, ...] = ARTIFACT_MARKER_PREFIXES



# ── P1-4 (deep audit 2026-09-14): session-scoped assertion ledger ───────────
# Structured in-memory ledger: every successful tool call emits an ASSERT line; the
# conversation_compactor reads from it directly instead of hunting for it through
# word heuristics in the raw text. The ledger is process-local (a session = a
# ledger); switching sessions resets it.
_ASSERTION_LEDGER: list[dict] = []
_LEDGER_SEQ = 0
_LEDGER_MAX = 200  # capped so a very long session cannot leak memory


def get_assertions() -> list[dict]:
    """P1-4: Returns the current assertion ledger (for the compactor)."""
    return list(_ASSERTION_LEDGER)


def reset_assertion_ledger() -> None:
    """P1-4: Resets the ledger (on session reset or cache invalidation)."""
    global _ASSERTION_LEDGER, _LEDGER_SEQ
    _ASSERTION_LEDGER = []
    _LEDGER_SEQ = 0


def _assertion_post_hook(name: str, arguments: dict, result: str) -> str | None:
    """P1-4: Records structured asserts from the tool result into the ledger.

    Emits an entry for:
      - *_FILE: markers (artifact paths)
      - run_tests result (pass/fail counts)
      - ARTIFACT_VERIFIED / ARTIFACT_FAILED
    """
    global _LEDGER_SEQ
    if not isinstance(result, str):
        return None
    entry: dict = {"seq": _LEDGER_SEQ, "tool": name}
    # 1. Artifact paths
    for line in result.splitlines():
        line = line.strip()
        for marker in _ARTIFACT_MARKERS:
            if line.startswith(marker):
                entry["path"] = line[len(marker):].strip()[:200]
                break
    # 2. ARTIFACT_VERIFIED
    if "ARTIFACT_VERIFIED" in result:
        for line in result.splitlines():
            if line.strip().startswith("ARTIFACT_VERIFIED:"):
                entry["verified"] = line.split(":", 1)[1].strip()[:200]
                break
    # 3. Test result (pytest: N passed, M failed)
    import re as _re
    m = _re.search(r"(\d+)\s+passed", result)
    if m:
        entry["tests_passed"] = int(m.group(1))
        m2 = _re.search(r"(\d+)\s+failed", result)
        entry["tests_failed"] = int(m2.group(1)) if m2 else 0
    # Append the entry only when it carries real content
    if len(entry) > 2:  # seq + tool are always there
        _LEDGER_SEQ += 1
        _ASSERTION_LEDGER.append(entry)
        if len(_ASSERTION_LEDGER) > _LEDGER_MAX:
            _ASSERTION_LEDGER.pop(0)
    return None
# ── End P1-4 ──────────────────────────────────────────────────────────────────

def _evidence_gate_post_hook(name: str, arguments: dict[str, object], result: str) -> str | None:
    """P0-3: Pins the evidence chain down — every artifact tool call ends with an
    ARTIFACT_VERIFIED-/ARTIFACT_FAILED line, so the agent path does not just see a
    *_FILE: marker but a hard check.
    """
    if not isinstance(result, str) or not result:
        return None
    # Marker present?
    marker_line = None
    for line in result.splitlines():
        line = line.strip()
        for marker in _ARTIFACT_MARKERS:
            if line.startswith(marker):
                marker_line = line
                break
        if marker_line:
            break
    if marker_line:
        # Append ARTIFACT_VERIFIED only when it is not there yet
        if "ARTIFACT_VERIFIED" not in result:
            path = marker_line.split(":", 1)[-1].strip() if ":" in marker_line else marker_line
            return result + "\nARTIFACT_VERIFIED: " + str(path)[:200]
        return None
    # No marker but also no error → not an artifact tool, the hook stays inactive
    if result.startswith(("[TOOL-ERROR", "[text-search", "FILE_NOT_FOUND", "ARTIFACT_FAILED")):
        return None
    return None

# Register the hook with priority 100 (later than result-changing hooks, not as an error)
register_tool_hook("post", _evidence_gate_post_hook, priority=100)
register_tool_hook("post", _assertion_post_hook, priority=200)
# ── End P0-3 ─────────────────────────────────────────────────────────────────────

#: Deep-audit wave 2 (parity harness): schemas of the three new parity tools.
#: Kept as a module constant so get_tool_schemas() appends them statically.
_PARITY_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Runs Python in a persistent session kernel. Variables and imports survive "
                "across calls, so multi-step computation (load -> transform -> emit) needs no "
                "repetition. Use for arithmetic, data wrangling, and 3+ tool-call reductions. "
                "print(...) returns the captured stdout. reset=True starts a fresh namespace. "
                "By default the code runs inside the pinned cell (no host files, no network, "
                "fuel/memory caps) and needs no dialog. Only when no cell carries the turn "
                "(EPHE_CODE_EXEC=kernel, or a machine with no guest) does it run in-process "
                "with full host access — then it is gated like run_shell. "
                "Kernel code has no approval dialog: `ephe_tools` reaches only gate-free tools — "
                "call a gated tool (run_shell, write_file, edit_file, delete_file) as a tool "
                "call, never from inside the kernel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python source to execute."},
                    "reset": {
                        "type": "boolean",
                        "description": "Clear the kernel namespace before running (new session).",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_list",
            "description": (
                "Session todo ledger for multi-step plans (machine-readable progress). "
                "action='set' replaces the list (items = titles, newline or ';' separated); "
                "action='update' sets one entry's status by 1-based id; action='list' prints "
                "the current ledger. Statuses: pending|in_progress|completed|cancelled."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["set", "update", "list"],
                        "description": "Ledger operation.",
                    },
                    "items": {
                        "type": "string",
                        "description": "Titles for 'set' (newline or ';' separated).",
                    },
                    "id": {
                        "type": "integer",
                        "description": "1-based entry index for 'update'.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "New status for 'update'.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "process_manage",
            "description": (
                "Controls a background process started by run_shell(run_in_background=True). "
                "action='list' enumerates every registered job (id, status, age, output size, "
                "command) — use it to see what is still running and to find the id a stop "
                "needs. 'poll' returns one job's current status without blocking; 'wait' "
                "blocks up to timeout_s until done; 'kill' cancels it. task_id is the id "
                "run_shell returned (required for poll/wait/kill, not for list)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["poll", "wait", "kill", "list"],
                        "description": "Process operation.",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "The id returned by run_shell(run_in_background=True), e.g. 'bg1' (not needed for 'list').",
                    },
                    "timeout_s": {
                        "type": "number",
                        "description": "Wait budget in seconds for action='wait' (default 30).",
                    },
                },
                "required": ["action"],
            },
        },
    },
]

#: Wave 3: schemas of the discovery meta tools (always active in the base array).
_DISCOVERY_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "tool_search",
            "description": (
                "Finds deferred tools by keyword. Returns matching tool names with a short "
                "description. Call this when a capability you need is not in the active tool "
                "list, then activate it with tool_call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword(s), e.g. 'pdf' or 'pptx deck'."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_describe",
            "description": "Returns the full JSON schema of one tool by exact name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Exact tool name."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_call",
            "description": (
                "Executes any registered tool (including deferred ones) by name. 'arguments' "
                "is a JSON object as a string, e.g. '{\"title\":\"Report\"}'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Exact tool name."},
                    "arguments": {"type": "string", "description": "JSON object string of arguments."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory",
            "description": (
                "Writes to persistent memory that survives across sessions. Two tiers: "
                "'user' = the user profile (name, expertise, language, style, topics, projects); "
                "'memory' = the fact collection (environment facts, conventions, lessons). "
                "Keep entries compact and high-signal. On the 'memory' tier 'replace' supersedes "
                "the identified fact instead of forgetting it (the old fact stays askable as "
                "history), and 'memory_type' classifies the fact kind."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "replace", "remove", "list"], "description": "Operation."},
                    "target": {"type": "string", "enum": ["user", "memory"], "description": "Which tier to write."},
                    "content": {"type": "string", "description": "Entry text (add/replace). For target=user use 'field=value', e.g. 'name=Test User'."},
                    "old_text": {"type": "string", "description": "Substring identifying the entry (replace/remove)."},
                    "memory_type": {"type": "string", "enum": ["semantic", "episodic", "procedural"], "description": "Fact kind for target=memory: semantic=state of things, episodic=something that happened, procedural=how to do it."},
                    "supersedes": {"type": "string", "description": "Entry id that this write corrects (target=memory, action=replace). Optional; 'old_text' identifies it otherwise."},
                },
                "required": ["action", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_manage",
            "description": (
                "Maintains the skill catalog. 'list' shows all skills, 'show' returns one skill's "
                "full content, 'create' writes a new user skill (name+trigger+description+system_prompt), "
                "'delete' removes one. Use after solving a non-trivial workflow to persist it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "show", "create", "delete"], "description": "Operation."},
                    "name": {"type": "string", "description": "Skill name (slug)."},
                    "trigger": {"type": "string", "description": "Trigger phrase for activation (create)."},
                    "description": {"type": "string", "description": "One-line description (create)."},
                    "tools": {"type": "string", "description": "Comma-separated allowed tool names (create)."},
                    "system_prompt": {"type": "string", "description": "The skill's system-prompt body (create)."},
                    "test_input": {"type": "string", "description": "Optional golden-example input (create) — adds a ## Test block."},
                    "test_expect_tool": {"type": "string", "description": "Tool the test expects to be called (create)."},
                    "test_expect_contains": {"type": "string", "description": "Substring the answer must contain (create)."},
                },
                "required": ["action"],
            },
        },
    },
]

TOOL_MAP: dict[str, object] = {
    "manage_tasks": manage_tasks,
    "web_search": web_search,
    "fetch_url": fetch_url,
    "file_search": file_search,
    "discover_projects": discover_projects,
    "analyze_project": analyze_project,
    "create_source_notebook": create_source_notebook,
    "query_source_notebook": query_source_notebook,
    "export_source_brief": export_source_brief,
    "read_file": read_file,
    "edit_file": edit_file,
    "write_file": write_file,
    "delete_file": delete_file,
    "run_tests": run_tests,
    "list_directory": list_directory,
    "get_datetime": get_datetime,
    "run_shell": run_shell,
    # gateway parity: the marker names (bash/read/edit) are the same tools
    # under the gateway's own nomenclature — identical parameter names, a direct
    # alias, no translation layer.
    "bash": run_shell,
    "read": read_file,
    "edit": edit_file,
    "task_output": task_output,
    "task_stop": task_stop,
    "agent_message": _agent_message_impl,
    "run_sandboxed_code": run_sandboxed_code,
    "load_workspace": load_workspace,
    "analyze_image": analyze_image,
    "vision_click": _vision_click_wrapper,
    "vision_type": _vision_type_wrapper,
    "take_screenshot": take_screenshot,
    "browser_go": browser_go,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_press": browser_press,
    "browser_scroll": browser_scroll,
    "browser_evaluate": browser_evaluate,
    "clipboard_read": clipboard_read,
    "clipboard_write": clipboard_write,
    "get_display_info": get_display_info,
    "browser_exec": browser_exec,
    "generate_chart": generate_chart,
    "create_pdf": create_pdf,
    "create_pitch_deck": create_pitch_deck,
    "create_pptx_deck": create_pptx_deck,
    "inspect_pptx_template": inspect_pptx_template,
    "edit_pptx_template": edit_pptx_template,
    "qa_pptx_deck": qa_pptx_deck,
    "create_svg": create_svg,
    "create_xlsx": create_xlsx,
    "create_docx": create_docx,
    "create_qrcode": create_qrcode,
    "create_diagram": create_diagram,
    "generate_image": generate_image,
    "create_video": create_video,
    "verify_artifact": verify_artifact,
    "scaffold_project": scaffold_project,
    "build_document": build_document,
    # Deep-audit wave 2 (parity harness): stateful kernel + session ledger
    # + unified process manager.
    "execute_code": execute_code,
    "todo_list": todo_list,
    "process_manage": process_manage,
    # G1: a run that can pause on a question — the human's answer arrives as the
    # result of this call, in the same tool loop.
    "ask_user": ask_user,
    # G6 (workbench): read-only readers of the agent's own run — the transcript
    # (same list the panel shows) and the cell journal behind a capped result.
    "read_transcript": read_transcript,
    "read_cell_journal": read_cell_journal,
    # Wave 3: progressive-discovery meta tools.
    "tool_search": tool_search,
    "tool_describe": tool_describe,
    "tool_call": tool_call,
    # Wave 4 (P3): stateful agent tools — memory write path + skill catalog care.
    "memory": memory,
    "skill_manage": skill_manage,
    # Wave 3: utility tools (T1-T4).
    "extract_pdf_text": extract_pdf_text,
    "format_code": format_code,
    "run_linter": run_linter,
    "validate_json": validate_json,
    # R36-S: native sub-agent delegation (the main agent decides on its own).
    "spawn_agent": spawn_agent,
}


# Repair taxonomy: a malformed call is refused with a named class and the repair
# it wants. W7-9's poka-yoke routes that refusal through _validate_tool_arguments,
# so the words around the class token are presentation and a reader matches the
# token.
#
# The table lives in core.provider_errors (W7-3), the one error taxonomy serve,
# chat and the CLI import. Reading it from there keeps the class set single; the
# names stay importable here for the tool loop and the tests that read them from
# this module.
from core.provider_errors import (
    REPAIR_CLASS_TOKEN as _REPAIR_CLASS_TOKEN,  # noqa: F401 — re-exported for the tool loop and tests
    REPAIR_CLASSES as _REPAIR_CLASSES,  # noqa: F401 — re-exported for the tool loop and tests
    REPAIR_TAXONOMY as _REPAIR_TAXONOMY,  # noqa: F401 — re-exported for the tool loop and tests
    RepairClass as _RepairClass,  # noqa: F401 — re-exported for the tool loop and tests
    refuse as _refuse,
    repair_class_of as _repair_class_of,
)


def _handler_accepts(name: str, key: str) -> bool:
    """True when the handler would take ``key`` as a keyword argument.

    A key it would not accept reaches ``func(**arguments)`` as a bare TypeError —
    an unnamed crash (the observed ``execute_code() got an unexpected keyword
    argument '_raw'``). Naming that case is the poka-yoke: it becomes an
    unknown-param refusal with a repair instead. Any handler we cannot introspect
    or that takes ``**kwargs`` is left tolerant, so a working call is never
    refused.
    """
    func = TOOL_MAP.get(name)
    if func is None:
        return True  # not ours to judge (MCP, unknown): stay tolerant
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return True  # not introspectable: stay tolerant
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return True
    param = parameters.get(key)
    return param is not None and param.kind is not inspect.Parameter.POSITIONAL_ONLY


def _validate_tool_arguments(name: str, arguments: dict) -> str | None:
    """P1-9 + W7-9: validates tool args against the declared JSON schema.

    Returns None when valid, otherwise a NAMED [TOOL-ERROR] refusal (see
    _refuse): the class comes from _REPAIR_TAXONOMY, the detail names the
    offending parameters. Best effort: hard required errors, undeclared
    parameters (a schema that closes its object, or a handler that would reject
    the keyword) and enum mismatches are reported; type tolerance wherever the
    schema allows it.
    """
    schema_entry = None
    for entry in get_tool_schemas():
        if entry.get("function", {}).get("name") == name:
            schema_entry = entry
            break
    if schema_entry is None:
        return None
    params = schema_entry.get("function", {}).get("parameters") or {}
    if not params:
        return None

    required = params.get("required") or []
    properties = params.get("properties") or {}
    missing = [key for key in required if key not in arguments]
    if missing:
        names = ", ".join(missing)
        return _refuse(name, "missing-param", f"required parameter(s) not set: {names}", names=names)

    closed = bool(properties) and params.get("additionalProperties") is False
    unknown = [
        key for key in arguments
        if key not in properties and (closed or not _handler_accepts(name, key))
    ]
    if unknown:
        names = ", ".join(unknown)
        return _refuse(name, "unknown-param", f"undeclared parameter(s): {names}", names=names)

    # Enum check (the most frequent small-model error source, cheap and hard).
    for key, value in arguments.items():
        spec = properties.get(key)
        if not spec:
            continue
        enum = spec.get("enum")
        if enum and value not in enum:
            return _refuse(
                name,
                "enum-mismatch",
                f"parameter {key!r}={value!r} is not one of {enum}",
                key=key,
                values=enum,
            )
    return None


def _classify_tool_error(error_str: str) -> str | None:
    """P1-2 + W7-9: the repair class a refusal names.

    Reads the class token first — that is the mechanism, and it comes from
    core.provider_errors so the token and the class set are one table. A string
    written before the token existed (an in-flight payload, an older audit line)
    is still classified from its wording, so nothing silently stops being
    repairable.
    """
    token_class = _repair_class_of(error_str)
    if token_class:
        return token_class
    if "fehlende Pflicht-Parameter" in error_str:
        return "missing-param"
    if "nicht in [" in error_str or "nicht in (" in error_str:
        return "enum-mismatch"
    if "unbekannte Parameter" in error_str:
        return "unknown-param"
    return None


def _tool_parameters(name: str) -> dict | None:
    """The parameter object a schema declares, or None when the tool is unknown."""
    for entry in get_tool_schemas():
        fn = entry.get("function") or {}
        if fn.get("name") == name:
            return fn.get("parameters") or {}
    return None


def _get_tool_property(name: str, key: str) -> dict | None:
    """P1-2: Fetches the property schema for a single parameter."""
    params = _tool_parameters(name) or {}
    return (params.get("properties") or {}).get(key)


def _typed_repair(name: str, arguments: dict, error_str: str) -> dict | None:
    """P1-2 + W7-9: Deterministic parameter repair for one refusal.

    The class comes from the refusal; the parameters to fix are re-derived from
    the tool's schema and the arguments, never parsed out of the message — so the
    repair holds whatever wording or language the refusal happens to use.

    Returns the repaired arguments dict, or None when no repair is possible.
    """
    error_class = _classify_tool_error(error_str)
    if error_class is None:
        return None
    params = _tool_parameters(name)
    if params is None:
        return None
    properties = params.get("properties") or {}
    required = params.get("required") or []
    repaired = dict(arguments)

    if error_class == "missing-param":
        # An argument set holding a key the tool never declared is a payload that
        # failed to parse (core.model_provider parks it under one key). Filling
        # the required parameters beside it runs a call the model never made: an
        # empty write_file, an empty program. No repair in that case.
        if any(key not in properties for key in repaired):
            return None
        for key in required:
            if key in repaired:
                continue
            spec = properties.get(key) or {}
            if "default" in spec:
                repaired[key] = spec["default"]
            elif spec.get("type") == "boolean":
                repaired[key] = False
            elif spec.get("type") in ("number", "integer"):
                repaired[key] = 0
            elif spec.get("type") == "array":
                repaired[key] = []
            else:
                repaired[key] = ""
        return repaired if repaired != arguments else None

    if error_class == "enum-mismatch":
        for key, value in repaired.items():
            enum = (properties.get(key) or {}).get("enum")
            if enum and value not in enum:
                repaired[key] = enum[0]
                return repaired if repaired != arguments else None
        return None

    if error_class == "unknown-param":
        dropped = [key for key in repaired if key not in properties]
        if not dropped:
            return None
        for key in dropped:
            repaired.pop(key, None)
        return repaired

    return None
# ── end of P1-2 / W7-9 ───────────────────────────────────────────────────────

async def execute_tool(name: str, arguments: dict, policy: ApprovalPolicy | None = None) -> str:
    """Execute a tool by name (E5 wrapper: plugin gate + user hooks + core).

    Order: plugin gate (fail-closed) → user pre_tool hooks (transform or
    block) → the tool core (approval, internal hooks, execution) → user
    post_tool transform.
    """
    # ── E1 plugin runtime gate (fail-closed) ────────────────────────────────
    # A plugin that was explicitly disabled takes its tool out of execution —
    # even if a model still guesses the name. Visibility fails open, execution
    # fails closed: both honest (denial + audit line).
    try:
        from core import plugin_runtime

        gate = plugin_runtime.tool_gate(name)
        if not gate.visible:
            from core.audit_log import audit_event

            audit_event("plugin_gate", tool=name, decision="denied", detail=f"plugin={gate.plugin}")
            return f"[Tool '{name}' is disabled (plugin '{gate.plugin}' is off — enable it in Settings → Plugins)]"
    except Exception:
        pass

    # W10 mode contract (Plan read-only / Ask no-tools), fail-closed: the offer
    # filter hides tools from the model, yet the deferred bridge resolves a name at
    # execution time and never sees that list. Model dispatch and the meta router
    # both land here, so the mode is enforced at the call that would write.
    from core.tools.chat_gate import mode_denial

    mode_refusal = mode_denial(name)
    if mode_refusal is not None:
        try:
            from core.audit_log import audit_event

            audit_event("mode_gate", tool=name, decision="denied", status=mode_refusal.code)
        except Exception:
            pass
        return mode_refusal

    # ── E5 User pre_tool hooks (transform or block) ─────────────────────────
    effective_args = arguments
    try:
        from core import user_hooks

        effective_args, block_reason = user_hooks.pre_tool_gate(name, arguments)
        if block_reason:
            return f"[Tool '{name}' blocked by hook: {block_reason}]"
    except Exception:
        pass

    # SEC-1 backstop: the chat gate runs one frame above for the model's own calls,
    # but a delegated agent, a channel or a plugin can reach this dispatch directly.
    # A protected root is refused here as well, and the refusal is a line.
    from core.path_guard import deny_paths

    blocked = deny_paths(effective_args)
    if blocked:
        try:
            from core.audit_log import audit_event

            audit_event(
                "security", tool=name, args=effective_args, decision="denied", status="protected-root"
            )
        except Exception:
            pass
        return (
            f"[Tool '{name}' refused: {blocked[0]} is inside a protected root "
            "(~/.ephe, ~/.ssh, ~/.aws, ~/.gnupg or a peer); no approval can open it.]"
        )

    result = await _execute_tool_core(name, effective_args, policy)

    # Sky 3: one track point per tool call — the ephemeris only sees THAT a tool
    # ran, never with which arguments (d/h/k/n, fail-soft).
    try:
        from core import ephemeris as _em

        _em.record("tool")
    except Exception:
        pass

    try:
        from core import user_hooks

        result = user_hooks.post_tool_transform(name, effective_args, result)
    except Exception:
        pass
    return result


async def _execute_tool_core(name: str, arguments: dict, policy: ApprovalPolicy | None = None) -> str:
    """Tool core: approval gate, internal pre/post hooks, MCP dispatch,
    validation and execution (everything that existed before the E5 wrapper)."""
    # ── P0-1 E1: Approval-Gate ──────────────────────────────────────────────
    if policy is not None:
        from core.tools.session_ctx import set_current_policy
        set_current_policy(policy)
        decision = await request_approval(name, arguments, policy)
        if not decision.approved:
            from core.audit_log import audit_event

            audit_event("approval", tool=name, args=arguments, decision="denied", status="cli-policy")
            return decision.report

    # R40b (Z43): pre hooks transform the args chain before execution.
    arguments = _run_tool_hooks("pre", name, arguments)

    # MCP remote tools (namespace 'mcp_') are dispatched separately.
    mcp_tools = get_mcp_tools()
    if name in mcp_tools:
        try:
            text, is_error = await call_registered_mcp_tool(name, arguments)
            prefix = "[MCP-tool-error] " if is_error else ""
            result = f"{prefix}{text}"
        except Exception as exc:
            result = _error_line(f"[MCP-tool-error '{name}': {exc}]", exc)
        return _run_tool_hooks("post", name, (arguments, result))[1]

    func = TOOL_MAP.get(name)
    if func is None:
        return _run_tool_hooks("post", name, (arguments, f"[Tool '{name}' not found]"))[1]

    # P1-9 (deep audit 2026-09-13): structured parameter validation against the
    # declared JSON schema, BEFORE func(**arguments) runs. An unknown or missing
    # required argument thus becomes a readable [TOOL-ERROR] instead of a bare
    # TypeError string. Best effort: schema gaps in existing tools must not block
    # a valid call (only hard required/additionalProperties errors).
    validation_error = _validate_tool_arguments(name, arguments)
    if validation_error is not None:
        # P1-2: deterministic repair for a classifiable error,
        # then ONE retry with the repaired args (no LLM roundtrip).
        repaired = _typed_repair(name, arguments, validation_error)
        if repaired is not None:
            retry_error = _validate_tool_arguments(name, repaired)
            if retry_error is None:
                arguments = repaired  # reparierte Args verwenden
            else:
                return _run_tool_hooks("post", name, (arguments, validation_error))[1]
        else:
            return _run_tool_hooks("post", name, (arguments, validation_error))[1]

    # R23: audit around EVERY execution (duration + status; payload redacted).
    import time as _time

    from core.audit_log import audit_event

    _started = _time.monotonic()
    try:
        result = await func(**arguments)
        if isinstance(result, list):
            result = "\n".join(str(r) for r in result)
        # A str subclass is kept as it is: core.reason.Reason IS its sentence and
        # carries the reason code beside it. Flattening it here is where that code
        # used to be lost on its way to the tool_done frame.
        if not isinstance(result, str):
            result = str(result)
        # P0-3 (deep audit 2026-09-13): audit status against the normalized
        # prefix table (core.quality.is_error_result) instead of only the lowercase
        # `[tool-error` check — otherwise `[TOOL-ERROR]`/`ARTIFACT_FAILED` from the
        # chat layer would show up as `ok` in the audit.
        from core.quality import is_error_result, result_decision

        audit_event(
            "tool_exec", tool=name, args=arguments,
            status="error" if is_error_result(result) else "ok",
            decision=result_decision(result),
            duration_ms=int((_time.monotonic() - _started) * 1000),
            detail=result[:300],
        )
        return _run_tool_hooks("post", name, (arguments, result))[1]
    except ShellConfirmationRequired:
        raise
    except Exception as exc:
        if exc.__class__.__name__ == "SandboxConfirmationRequired":
            raise
        audit_event(
            "tool_exec", tool=name, args=arguments, status="error",
            duration_ms=int((_time.monotonic() - _started) * 1000),
            detail=str(exc)[:300],
        )
        return _run_tool_hooks(
            "post", name, (arguments, _error_line(f"[tool-error '{name}': {exc}]", exc))
        )[1]


def invalidate_tool_schema_cache() -> None:
    """Drops the get_tool_schemas cache (e.g. when MCP tools get registered)."""
    global _TOOL_SCHEMA_CACHE
    _TOOL_SCHEMA_CACHE = None


# Wave 3: utility tool schemas (T1-T4)
_UTILITY_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "extract_pdf_text",
            "description": (
                "Extrahiert den Volltext aus einer lokalen PDF-Datei. "
                "Gibt den seitenweisen Text zurueck (Page-Marker inklusive). "
                "Nur bei vorhandenem PDF-Dateipfad verwenden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~-relative path to the PDF file.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximale Zeichenanzahl (Default 8000).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "format_code",
            "description": (
                "Formats a Python file with ruff format (Black-compatible). "
                "check_only=True inspects without writing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~-relative path to the Python file (.py).",
                    },
                    "check_only": {
                        "type": "boolean",
                        "description": "True = inspect only, do not write.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_linter",
            "description": (
                "Fuehrt ruff check (statische Code-Analyse) auf einer Datei oder "
                "einem Verzeichnis aus. fix=True wendet automatische Korrekturen an."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~-relative path to the file or directory.",
                    },
                    "fix": {
                        "type": "boolean",
                        "description": "True = --fix (automatische Korrekturen).",
                    },
                    "max_issues": {
                        "type": "integer",
                        "description": "Maximale Anzahl angezeigter Issues (Default 50).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_json",
            "description": (
                "Validates a JSON string against a JSON schema (Draft 2020-12). "
                "Returns OK for a valid document or a list of errors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "The JSON string to validate (the instance).",
                    },
                    "schema": {
                        "type": "string",
                        "description": "The JSON schema as a string (Draft 2020-12).",
                    },
                },
                "required": ["data", "schema"],
            },
        },
    },
]

def _apply_plugin_filter(schemas: list[dict]) -> list[dict]:
    """E1 plugin runtime: the gate is a post filter OUTSIDE the cache.

    Runs on the cache-hit path too, so a disabled plugin's tools cannot come
    back on the second call of a TTL window; a registry flip still takes
    effect on the next call without invalidation plumbing.
    """
    try:
        from core import plugin_runtime

        return plugin_runtime.filter_schemas(schemas)
    except Exception:
        return schemas  # fail-open for visibility (execution gates strictly by itself)


def get_tool_schemas() -> list[dict]:
    global _TOOL_SCHEMA_CACHE
    now = time.monotonic()
    if _TOOL_SCHEMA_CACHE and now - _TOOL_SCHEMA_CACHE[0] < TOOL_SCHEMA_CACHE_TTL_SECONDS:
        return _apply_plugin_filter(_TOOL_SCHEMA_CACHE[1])

    schemas = list(BASE_TOOL_SCHEMAS)
    # Deep-audit wave 2 (parity harness): stateful kernel + session ledger +
    # process manager. Schemas static (no env opt-in needed).
    schemas.extend(_PARITY_TOOL_SCHEMAS)
    # G6 (workbench): the agent's own readers — its transcript and the cell
    # journal behind a capped result. Always visible, no opt-in.
    schemas.extend(WORKBENCH_TOOL_SCHEMAS)
    # Wave 3: progressive-discovery meta tools (active only on the unfiltered path;
    # their schemas are small and always included so the model hits them).
    schemas.extend(_DISCOVERY_TOOL_SCHEMAS)
    # Opt-in sandbox tool: schema only when Ephemora Cell is installed
    # (conservative: no tool schema for an execution environment that is not there).
    if sandbox_is_available():
        schemas.extend(SANDBOX_TOOL_SCHEMAS)
    schemas.extend(_UTILITY_TOOL_SCHEMAS)
    # G1: the ask gate — a tool the model calls to pause the run on a question.
    schemas.extend(ASK_TOOL_SCHEMAS)
    # R36-S: sub-agent delegation — one schema, the main agent decides on its own.
    schemas.append(SPAWN_AGENT_SCHEMA)
    # Append MCP remote tools dynamically (namespace 'mcp_')
    for mcp_name, mcp_entry in get_mcp_tools().items():
        schemas.append({
            "type": "function",
            "function": mcp_entry.get("schema", {"name": mcp_name, "description": "", "inputSchema": {"type": "object"}}),
        })

    _TOOL_SCHEMA_CACHE = (now, schemas)
    return _apply_plugin_filter(schemas)


def get_filtered_tool_schemas(whitelist: list[str]) -> list[dict]:
    """Filtered tool schemas for an active skill.

    P0-1 (deep audit 2026-09-14): META_TOOL_NAMES + memory + skill_manage are
    injected in addition to the skill whitelist, so progressive disclosure and
    persistence are available on the filtered path too.
    """
    from core.tools.discovery import META_TOOL_NAMES

    effective = set(whitelist) | set(META_TOOL_NAMES) | {"memory", "skill_manage"}
    all_tools = get_tool_schemas()
    return [
        t for t in all_tools
        if t.get("function", {}).get("name") in effective
    ]
