"""Classification, containment and confidence rules behind the approval gate.

The static half of the gate: which tools are safe (``SAFE_TOOLS`` and the name
sets), when a name's class depends on the runtime (``_runs_uncontained``), and
the opt-in confidence floor (``low_confidence_escalation``). Every public name
here is re-exported by ``core.tools.approval``, which runs the gate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

# Classification

#: Read-only / non-mutating tools. These never need an approval gate.
#: (Deliberately conservative: anything else counts as mutating.)
SAFE_TOOLS: frozenset[str] = frozenset({
    "read_file",
    "list_directory",
    "file_search",
    "get_datetime",
    "query_source_notebook",
    "browser_screenshot",
    "verify_artifact",
    "task_output",
    "fetch_url",
    "clipboard_read",
    "get_display_info",
    # Deep-audit wave 2 (parity harness): the compute kernel, the in-memory ledger and
    # the bg register (the task_output counterpart) are read-only/compute — CLI auto-run.
    # W3-15: `execute_code` keeps this listing but its auto-run licence is conditional —
    # it is only SAFE while the pinned cell carries the run; uncontained it is gated
    # (see `_runs_uncontained`).
    "execute_code",
    "todo_list",
    "process_manage",
    # G6 (workbench): the agent's own readers are read-only — a transcript of a
    # past turn and a byte range of the cell journal. Nothing here mutates.
    "read_transcript",
    "read_cell_journal",
    # Wave 3: discovery index lookups (read-only) are SAFE; tool_call delegates
    # and carries the inner gate — deliberately kept outside (MUTATING/dialog).
    "tool_search",
    "tool_describe",
    # R36-S: sub-agent delegation is compute (no host mutation) and SHOULD run in the
    # SAFE parallel batch — several spawn_agent calls of one round are then executed
    # concurrently; the helpers themselves stay read-only whitelisted
    # (core.subagent.SUBAGENT_TOOL_WHITELIST).
    "spawn_agent",
})

#: Chat path (PWA ``/chat/stream``): tools that run WITHOUT a confirmation dialog —
#: read-only, compute, or purely app-internal state changes (tasks). These deliberately
#: do NOT extend ``SAFE_TOOLS`` (CLI auto-approve semantics) and change nothing in the
#: channel/policy gates. Unknown ⇒ dialog (conservative).
CHAT_AUTO_RUN_TOOLS: frozenset[str] = frozenset({
    "analyze_image",
    "analyze_project",
    "discover_projects",
    "file_search",
    "get_datetime",
    "inspect_pptx_template",
    "list_directory",
    "load_workspace",
    "manage_tasks",
    "qa_pptx_deck",
    "query_source_notebook",
    "read_file",
    "verify_artifact",
    "web_search",
    # J2: internal task-register control + LLM continuation (compute)
    "task_stop",
    "agent_message",
    # Wave 3: tool_call is a meta router — auto-run on the chat path (carries the
    # inner gate via execute_tool(policy=...)); on the CLI side conservatively MUTATING.
    "tool_call",
    # J5: browser channel extensions (manager-internal, no second dialog needed)
    "browser_scroll",
    "browser_evaluate",
    "clipboard_write",
    # Deep-audit wave 2 (parity harness): compute kernel, session ledger and
    # background-process control are app-internal/auto-run (no host mutation
    # outside the shell register that is already approved anyway).
    "execute_code",
    "todo_list",
    "process_manage",
    # G1: the ask gate asks the human and awaits the answer — the dialog is what
    # this tool IS, so a confirmation gate in front of it would ask nothing.
    "ask_user",
    # G6 (workbench): reading your own transcript or the cell journal changes
    # nothing outside the app's own files — chat auto-run.
    "read_transcript",
    "read_cell_journal",
    # Wave 4 (P3): memory/skill upkeep writes only into the app's own files
    # (~/.ephe), no host mutation outside — chat auto-run.
    "memory",
    "skill_manage",
    # R36-S: sub-agent delegation — the helpers run read-only whitelisted on the
    # active engine; the delegation tool itself mutates nothing (auto-run).
    "spawn_agent",
})

#: Cluster that does NOT gate itself through the chat gate. Vision/desktop control
#: calls ``core.vision.check_sandbox`` itself (request-scoped callback); the browser
#: cluster has no dialog — it is bounded by its reach
#: (core.browser_url.url_policy: no file: outside the artifact folders).
SELF_GATED_TOOLS: frozenset[str] = frozenset({
    "vision_click",
    "vision_type",
    "take_screenshot",
    "browser_go",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_screenshot",
})

#: Tools that need the network (P1-8): they perform outbound DNS/HTTP roundtrips —
#: an informational category next to SAFE/MUTATING; the approval semantics stay
#: coupled to `SAFE_TOOLS`/`_CHAT_NO_CONFIRM` (no behavior drift).
NETWORK_TOOLS: frozenset[str] = frozenset({
    "web_search",
    "fetch_url",
    "browser_go",
})

#: Hard category (P1-9 context): write/process tools with a direct effect.
DANGEROUS_TOOLS: frozenset[str] = frozenset({
    "run_shell",
    "edit_file",
    "write_file",
})

#: Names that may run on the chat path without asking.
_CHAT_NO_CONFIRM: frozenset[str] = SAFE_TOOLS | CHAT_AUTO_RUN_TOOLS | SELF_GATED_TOOLS


#: Tools whose auto-run licence depends on WHERE the code runs, not on the name.
#: ``execute_code`` is contained by the pinned cell when the guest carries the turn
#: (auto-run, no dialog), and runs in-process with full host access otherwise — there
#: it must pass the same gate as ``run_shell``. The licence is the cell whichever tool
#: carries the code (docs/SANDBOX_EXECUTION.md, decision W3-15). Every other tool is classified
#: by name alone.
_RUNTIME_CONTAINMENT_GATED: frozenset[str] = frozenset({"execute_code"})


def _runs_uncontained(name: str) -> bool:
    """True when *name* would execute outside the cell (full host access) — fail-closed.

    Anything that keeps us from reading the runtime counts as uncontained, i.e. as
    needing the gate — the same direction as every other default in this module
    (unknown ⇒ ask). A contained run needs no dialog because the cell caps it
    (fuel, memory, files, network, no host files).
    """
    if name not in _RUNTIME_CONTAINMENT_GATED:
        return False
    try:
        from core.cpython_cell import code_runs_uncontained

        return code_runs_uncontained()
    except Exception:  # noqa: BLE001 — an unreadable runtime is not an approval
        return True


def chat_tool_requires_confirm(
    name: str,
    *,
    policy: Optional["ApprovalPolicy"] = None,
    confidence: object = None,
) -> bool:
    """True when the chat path has to ask the user before executing.

    Conservative default: unknown names and the MCP namespace count as mutating
    and are asked about. ``run_shell`` is handled through ``on_shell_confirm``
    before this gate and never reaches it. ``execute_code`` is asked about only
    when it would run uncontained (no cell carries the turn) — inside the cell it
    stays auto-run.

    The opt-in confidence floor applies here too: with a policy that turns it on, an
    auto-run tool the model is unsure about is asked about after all. Without a
    policy the result is exactly the old one.
    """
    if _runs_uncontained(name):
        return True
    if name not in _CHAT_NO_CONFIRM:
        return True
    if policy is not None and low_confidence_escalation(
        policy, confidence, mutating=classify_tool(name).is_mutating
    ):
        return True
    return False


@dataclass(frozen=True)
class ToolClassification:
    """Risk classification of a tool (E1).

    ``category`` is the 4-class identifier from P0-1/layer 2:
    ``SAFE`` | ``NETWORK`` | ``MUTATING`` | ``DANGEROUS``.

    A name alone is not enough for ``execute_code``: its class depends on the
    effective runtime (contained cell ⇒ SAFE, host kernel ⇒ MUTATING). Every other
    tool's class is fixed by name.
    """

    name: str
    is_mutating: bool
    auto_approve_by_default: bool
    category: str = "MUTATING"


def classify_tool(name: str) -> ToolClassification:
    """Classifies a tool by mutation potential and category (P1-8).

    Conservative defaults: unknown / not in ``SAFE_TOOLS`` counts as mutating and
    must not be auto-approved. The category separates the four classes —
    ``web_search`` is e.g. ``NETWORK``: an external roundtrip.

    Not purely static: ``execute_code`` is auto-approved only while the pinned cell
    really carries the run. Without the cell it executes on the host, so it is
    classified MUTATING and gated (``_runs_uncontained``).
    """
    safe = name in SAFE_TOOLS and not _runs_uncontained(name)
    if name in DANGEROUS_TOOLS:
        category = "DANGEROUS"
    elif name in NETWORK_TOOLS:
        category = "NETWORK"
    elif safe:
        category = "SAFE"
    elif name.startswith("mcp_"):
        # P0-4 (deep audit 2026-09-14): MCP remote tools are network-mediated
        # (HTTP/stdio to an external server); no local mutation.
        category = "NETWORK"
    else:
        category = "MUTATING"
    return ToolClassification(
        name=name,
        is_mutating=not safe,
        auto_approve_by_default=safe,
        category=category,
    )


# Policy and the confidence floor

#: Approval below this confidence is escalated once the opt-in is on. It is a floor
#: for asking a human, never a quality score: the escalation only ever adds a
#: confirmation and never grants one.
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.6

#: Callback signature: ``async def on_confirm(tool_name, arguments) -> bool``
OnConfirm = Callable[[str, dict], Awaitable[bool]]


@dataclass
class ApprovalPolicy:
    """Runtime approval configuration per execution context.

    The defaults are conservative (E1): no auto-approval, no dry run.
    """

    auto_approve: bool = False
    dry_run: bool = False
    #: ``True`` → explicit refusal (``--no``): mutating tools are not executed.
    declined: bool = False
    #: ``None`` → no explicit callback → fall back to the TTY prompt.
    on_confirm: Optional[OnConfirm] = None
    #: Is the caller interactive (TTY)? ``False`` → no prompt possible.
    interactive: bool = True
    #: Opt-in confidence floor (off by default, so no behavior drift). With it on, a
    #: mutating call whose ``confidence`` sits below ``confidence_threshold`` is
    #: confirmed by a human instead of auto-approved — ``--yes`` included.
    escalate_on_low_confidence: bool = False
    #: The requesting call's confidence in [0, 1], or ``None`` when no signal exists.
    confidence: Optional[float] = None
    #: Below this value the opt-in escalation asks a human.
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD


def _confidence_value(raw: object) -> Optional[float]:
    """The number a confidence signal carries.

    A plain float passes through; an object with a numeric ``confidence`` field
    (``core.decisions.Decision`` carries one) is read through that field. ``None``
    stays ``None`` — no signal — while a declared-but-unreadable signal returns NaN
    so the caller escalates instead of reading it as confident.
    """
    if raw is None:
        return None
    value = getattr(raw, "confidence", raw)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def low_confidence_escalation(
    policy: ApprovalPolicy,
    confidence: object = None,
    *,
    mutating: bool = True,
) -> bool:
    """True when the opt-in confidence floor turns this call into a human decision.

    Off by default: without ``policy.escalate_on_low_confidence`` this is always
    ``False`` and the gate is exactly the one that ran before. Only a mutating call
    can escalate — a read-only tool acts on nothing, so there is nothing to defer.
    The floor is monotonic: it can ask a human, it can never approve, so a
    probabilistic signal never decides a mutating tool (see
    docs/EPHE_DECISION_LAYER_2026-10-10.md on why the deterministic classification
    stays in charge).

    ``confidence`` is a number, or an object that carries one — a
    ``core.decisions.Decision`` from the Ephe Decision layer is accepted as-is. A
    call with no signal (``None``) is not escalated; a signal that is present but
    unusable (NaN, non-numeric) counts as low, so a broken producer cannot make the
    gate look more confident than it is.
    """
    if not mutating or not policy.escalate_on_low_confidence:
        return False
    raw = policy.confidence if confidence is None else confidence
    value = _confidence_value(raw)
    if value is None:
        return False
    if math.isnan(value):
        return True
    return value < policy.confidence_threshold


__all__ = [
    "CHAT_AUTO_RUN_TOOLS",
    "DANGEROUS_TOOLS",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "NETWORK_TOOLS",
    "SAFE_TOOLS",
    "SELF_GATED_TOOLS",
    "ApprovalPolicy",
    "OnConfirm",
    "ToolClassification",
    "chat_tool_requires_confirm",
    "classify_tool",
    "low_confidence_escalation",
]
