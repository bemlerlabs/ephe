"""P0-1 / threat model E1: approval gates, diff preview and ``--dry-run``.

Conservative defaults (release bar from AGENTS.md):

- Destructive / mutating tools need **explicit** approval *before* execution.
- Without a policy and without interactivity, a MUTATING run is rejected
  (``--yes`` required) instead of being executed silently.
- ``--dry-run`` shows the diff but writes **nothing**.

The gate stays isolated in ``core.tools.approval`` so the registry
(``core.tools.registry.execute_tool``) and the CLI subcommand (``ephe tool <name>``)
use the same code. The classification and confidence rules it runs live in
``core.tools.approval_rules`` and are re-exported here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.tools.approval_rules import (
    CHAT_AUTO_RUN_TOOLS,
    DANGEROUS_TOOLS,
    DEFAULT_CONFIDENCE_THRESHOLD,
    NETWORK_TOOLS,
    SAFE_TOOLS,
    SELF_GATED_TOOLS,
    ApprovalPolicy,
    OnConfirm,
    ToolClassification,
    _confidence_value,
    _runs_uncontained,  # noqa: F401  (core.cpython_guest cites this path in prose)
    chat_tool_requires_confirm,
    classify_tool,
    low_confidence_escalation,
)

# Approval decision

@dataclass
class ApprovalDecision:
    """Result of the approval gate.

    ``report`` is human-readable and passed on by the CLI / the registry to the
    user as the result string.
    """

    approved: bool
    dry_run: bool
    report: str
    diff: str = ""
    extra: dict = field(default_factory=dict)


# Diff preview

def _truncate(text: str, limit: int = 400) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f" … (+{len(text) - limit} characters)"


def format_diff(tool_name: str, arguments: dict) -> str:
    """Human-readable preview of what would be executed.

    Shown to the user in the approval prompt; with ``--dry-run`` it is the only
    visible effect.
    """
    args = dict(arguments or {})

    if tool_name == "create_svg":
        svg = str(args.get("svg_code", ""))
        filename = str(args.get("filename", ""))
        lines = [
            f"Create SVG → {filename or '(default name)'}",
            "Preview:",
            _truncate(svg, 600),
        ]
        return "\n".join(lines)

    if tool_name == "run_shell":
        cmd = str(args.get("command", ""))
        return f"Shell command:\n    {cmd}"

    if tool_name == "edit_file":
        path = str(args.get("path", ""))
        old = _truncate(str(args.get("old_string", "")), 200)
        new = _truncate(str(args.get("new_string", "")), 200)
        return f"Edit file → {path}\n  - {old}\n  + {new}"

    if tool_name == "write_file":
        path = str(args.get("path", ""))
        content = str(args.get("content", ""))
        lines = content.splitlines()
        preview = "\n".join(lines[:12])
        more = f"\n… (+{len(lines) - 12} rows)" if len(lines) > 12 else ""
        return f"Write file → {path} ({len(content)} characters)\n{preview}{more}"

    if tool_name == "run_tests":
        cmd = str(args.get("command", ""))
        return f"Run tests:\n    {cmd}"

    if tool_name == "manage_tasks":
        action = str(args.get("action", ""))
        title = str(args.get("title", ""))
        return f"Tasks: action={action!r} title={title!r}"

    # Fallback: all arguments as key/value
    parts = [f"{k} = {_truncate(str(v), 200)}" for k, v in sorted(args.items())]
    body = "\n".join(f"    {p}" for p in parts) or "    (no arguments)"
    return f"Tool: {tool_name}\n{body}"


# Approval request

async def _escalated_approval(
    tool_name: str,
    arguments: dict,
    policy: ApprovalPolicy,
    diff: str,
    confidence: float,
) -> ApprovalDecision:
    """The opt-in confidence floor's decision path: callback, TTY, then fail closed.

    ``--yes`` never reaches here — the floor sits ahead of it on purpose, since a
    blanket yes is not a yes to an action the model could not rate.
    """
    note = (
        f"escalated: confidence {float(confidence):.2f} "
        f"< threshold {policy.confidence_threshold:.2f}"
    )
    extra = {
        "escalated": True,
        "confidence": float(confidence),
        "threshold": policy.confidence_threshold,
    }

    if policy.on_confirm is not None:
        granted = await policy.on_confirm(tool_name, arguments)
        report = (
            f"[approved] {tool_name} approved via callback ({note})."
            if granted
            else f"[Denied] {tool_name} denied via callback ({note}). Execution stopped."
        )
        return ApprovalDecision(approved=granted, dry_run=False, report=report,
                                diff=diff, extra=extra)

    if policy.interactive:
        try:
            answer = input(
                f"\n[Approval] {tool_name} ({note})\n{diff}\n\nExecute? [y/N] "
            )
        except EOFError:
            answer = "n"
        granted = answer.strip().lower() in ("y", "yes")
        report = (
            f"[approved] {tool_name} confirmed interactively ({note})."
            if granted
            else f"[Denied] {tool_name} denied interactively ({note}). Execution stopped."
        )
        return ApprovalDecision(approved=granted, dry_run=False, report=report,
                                diff=diff, extra=extra)

    return ApprovalDecision(
        approved=False, dry_run=False,
        report=(
            f"[Denied] {tool_name} {note}, and no interactive confirmation is "
            f"available. Approve it interactively, or adjust the escalation policy."
        ),
        diff=diff, extra=extra,
    )


async def request_approval(
    tool_name: str,
    arguments: dict,
    policy: ApprovalPolicy,
    confidence: object = None,
) -> ApprovalDecision:
    """Runs the approval gate.

    Order (conservative — a no-execute lever outranks an execute lever):

    1. SAFE tool → auto-approved (no prompt, no dry-run effect).
    2. ``policy.declined`` (``--no``) → **not executed**.
    3. ``policy.dry_run`` → **not executed**, dry-run report. It stays a
       no-touch promise even when ``auto_approve`` is set beside it.
    4. Opt-in confidence floor → a low-confidence mutating call is confirmed by a
       human instead of auto-approved (``--yes`` included).
    5. ``policy.auto_approve`` (e.g. ``--yes``) → auto-approved.
    6. Callback available → the callback decides.
    7. Interactive → TTY prompt (``input()``).
    8. Otherwise (non-interactive, no flag) → **deny** with a hint at
       ``--yes`` (exit 1 in the CLI).

    ``confidence`` is the per-call signal: a number, or a ``core.decisions.Decision``
    whose own ``confidence`` field is read. When it is ``None`` the policy's
    ``confidence`` is used, so a caller that keeps the signal on the policy needs no
    change at the call site.
    """
    cls = classify_tool(tool_name)
    diff = format_diff(tool_name, arguments)
    effective_confidence = _confidence_value(
        policy.confidence if confidence is None else confidence
    )
    escalated = low_confidence_escalation(
        policy, effective_confidence, mutating=cls.is_mutating
    )

    if cls.auto_approve_by_default:
        return ApprovalDecision(
            approved=True, dry_run=False,
            report=f"[auto] {tool_name} is read-only — no approval needed.",
            diff=diff,
        )

    # Explicit refusal (--no): mutating tools are not executed.
    if policy.declined:
        return ApprovalDecision(
            approved=False, dry_run=False,
            report=f"[Denied] {tool_name} explicitly denied (--no). Execution stopped.",
            diff=diff,
        )

    # The no-touch promise: `--dry-run` must survive a `--yes` beside it.
    if policy.dry_run:
        return ApprovalDecision(
            approved=False, dry_run=True,
            report=(
                f"[DRY-RUN] {tool_name} was NOT executed.\nPreview:\n{diff}"
            ),
            diff=diff,
        )

    # Opt-in confidence floor: a low-confidence mutating call goes to a human even
    # when `--yes` would blanket-approve it. The floor withholds that blanket yes
    # from a call the model could not rate; the human still decides, and the floor
    # itself never approves.
    if escalated:
        return await _escalated_approval(
            tool_name, arguments, policy, diff, effective_confidence
        )

    if policy.auto_approve:
        return ApprovalDecision(
            approved=True, dry_run=False,
            report=f"[--yes] {tool_name} explicitly approved.",
            diff=diff,
        )

    if policy.on_confirm is not None:
        granted = await policy.on_confirm(tool_name, arguments)
        if granted:
            return ApprovalDecision(
                approved=True, dry_run=False,
                report=f"[approved] {tool_name} approved via callback.",
                diff=diff,
            )
        return ApprovalDecision(
            approved=False, dry_run=False,
            report=f"[Denied] {tool_name} denied via callback. Execution stopped.",
            diff=diff,
        )

    if policy.interactive:
        try:
            answer = input(
                f"\n[Approval] {tool_name}\n{diff}\n\nExecute? [y/N] "
            )
        except EOFError:
            answer = "n"
        if answer.strip().lower() in ("y", "yes"):
            return ApprovalDecision(
                approved=True, dry_run=False,
                report=f"[approved] {tool_name} confirmed interactively.",
                diff=diff,
            )
        return ApprovalDecision(
            approved=False, dry_run=False,
            report=f"[Denied] {tool_name} denied interactively. Execution stopped.",
            diff=diff,
        )

    # Non-interactive, no flag, no callback → conservatively: deny.
    return ApprovalDecision(
        approved=False, dry_run=False,
        report=(
            f"[Denied] {tool_name} is mutating and this call is non-interactive. Use --yes (explicit approval) or --dry-run (preview without execution)."
        ),
        diff=diff,
    )


__all__ = [
    "SAFE_TOOLS",
    "NETWORK_TOOLS",
    "DANGEROUS_TOOLS",
    "CHAT_AUTO_RUN_TOOLS",
    "SELF_GATED_TOOLS",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "chat_tool_requires_confirm",
    "ToolClassification",
    "classify_tool",
    "low_confidence_escalation",
    "ApprovalPolicy",
    "ApprovalDecision",
    "OnConfirm",
    "format_diff",
    "request_approval",
]
