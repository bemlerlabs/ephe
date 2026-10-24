"""Chat-side approval gate — one choke point for model dispatch and the meta router.

Two paths execute tools: ``core/chat.py`` calls the tool the model
chose, and ``core/tools/discovery.tool_call`` delegates a deferred tool
once more inwards. Both have to pass the same gate. Whoever has the gate at only
one end leaves the other open: ``tool_call`` is chat-auto-run and forwards the
active approval policy — which is ``None`` on the PWA path, and
``execute_tool`` skips its gate without a policy. One single meta-router call
therefore bypassed every confirmation dialog (Wave G1, audit 2026-10-02).

Approval comes from the request context (``core.vision._sandbox_cb_var``),
the same callback the SSE handler sets via ``set_sandbox_confirm_cb``.
No channel reachable ⇒ no execution; that is conservative, not convenient.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

#: Leaf module (contextvars only) — no import cycle with the registry that calls us.
from core.tools.session_ctx import get_current_mode

#: The dialog callback: ``async def cb(name, args) -> bool`` (sync is tolerated).
ConfirmCallback = Callable[[str, dict], Any]

DENIAL_PREFIX = "[TOOL-DENIED]"


def _approval_callback(on_confirm: Optional[ConfirmCallback]) -> Optional[ConfirmCallback]:
    """An explicit callback has priority, otherwise the request-scoped SSE callback."""
    if on_confirm is not None:
        return on_confirm
    from core.vision import _sandbox_cb_var

    return _sandbox_cb_var.get()


async def _resolve(value: Any) -> bool:
    return bool(await value) if hasattr(value, "__await__") else bool(value)


#: The gate's outcomes, in the language the engine is instructed with. A surface that
#: localises reads `Denied.code` beside the text, the way `tool_done` already carries
#: `reason_code` (f5d88653); `not_approved` is the short form for a caller with no detail.
DENIAL_REASONS = {
    "no_approval_channel": "no approval channel is active (nobody is asking the user)",
    "not_approved_by_user": "the user did not approve the run",
    "approval_channel_failed": "the approval channel failed ({error})",
    "not_approved": "",
    # W10: the mode's own promise, refused where the call would run.
    "mode_read_only": "this mode is read-only (Plan) and that tool writes — leave Plan mode to run it",
    "mode_no_tools": "this mode (Ask) runs without tools",
    # SEC-1: a path under a protected root is refused before a dialog; a
    # credential-shaped file needs the dialog even when the tool only reads.
    "secret_path_denied": "the path is inside a protected root ({path})",
}

#: The move a denied run leaves open. Every denial carries it — a bare "was not executed"
#: tells the model what did not happen and stops, which is half a refusal. Appended to the
#: short `not_approved` form as well as the detailed ones, so no branch is a dead end.
NEXT_STEP = "Ask, or choose a read-only path."


#: The tool names a read-only mode (Plan) still executes. The offer filter in
#: ``server/routes/chat.py`` is the subset the model is shown; this set is what the
#: execution gate admits, and it is deliberately wider in exactly two ways:
#:   - ``tool_search``/``tool_describe`` only read the tool index;
#:   - ``tool_call`` is the deferred forwarder — it executes nothing itself, and the
#:     name it forwards is re-checked by this same gate one frame deeper. Judging the
#:     forwarder instead of the forwarded call would refuse a read-only lookup while
#:     looking like it closed the write.
#:   - ``ask_user`` (G1) writes nothing at all: it pauses the run and asks. A read-only
#:     mode is exactly where a run should be allowed to ask before it writes.
READ_ONLY_MODE_TOOLS: frozenset[str] = frozenset({
    "read_file", "file_search", "list_directory", "web_search",
    "tool_search", "tool_describe", "tool_call", "ask_user",
})


def mode_denial(name: str) -> Optional[Denied]:
    """The mode's promise, enforced where the call is executed — None when it holds.

    The offer filter hides tools from the model; it cannot bind a call that arrives
    by name through the deferred bridge (``tool_search`` discovers a tool,
    ``tool_call`` dispatches it). A run with the chip reading ``Plan`` therefore wrote
    a real file that way (walkthrough 2026-10-12). This is the one place both paths
    (model dispatch and the meta router) pass through, so the refusal happens at the
    point where the write would have happened, whatever route the model took to ask.
    """
    mode = get_current_mode()
    if mode == "ask":
        return denial_message(name, "mode_no_tools")
    if mode == "plan" and name not in READ_ONLY_MODE_TOOLS:
        return denial_message(name, "mode_read_only")
    return None


class Denied(str):
    """A refusal sentence the model reads, with the code a surface translates.

    Subclass of `str` because the result object goes to the tool message, the tool card
    and the audit row as one string; `code` and `params` ride along for the card alone.
    """

    __slots__ = ("code", "params")

    code: str
    params: dict

    def __new__(cls, text: str, code: str, params: Optional[dict] = None):
        obj = super().__new__(cls, text)
        obj.code = code
        obj.params = dict(params or {})
        return obj


def denial_message(name: str, reason: str = "not_approved", **params) -> Denied:
    """Build the one denial string both sinks consume.

    `reason` is the gate's code, so no caller has to know the wording. A code that needs a
    slot and is called without it raises rather than sending `{error}` to the model. Every
    branch ends on the next step, the short `not_approved` form included.
    """
    text = DENIAL_REASONS.get(reason, reason).format(**params)
    detail = f": {text}" if text else ""
    body = f"{DENIAL_PREFIX} {name} was not executed{detail}. {NEXT_STEP}"
    return Denied(body, reason, params)


async def confirm_for_chat(
    name: str,
    args: dict,
    *,
    on_confirm: Optional[ConfirmCallback] = None,
    audit: bool = True,
) -> tuple[bool, str]:
    """(approved, denial) — the denial is empty when the tool runs.

    Read-only/compute tools (``chat_tool_requires_confirm`` == False) run without
    asking; everything else needs a yes. A throwing callback counts
    as a no — a broken dialog is not an approval. The denial is built here so the
    exception name reaches the engine instead of dying in this function.
    """
    from core.tools.approval import chat_tool_requires_confirm
    from core.path_guard import deny_paths, secret_paths, verifiable_artifact

    denied_hits = deny_paths(args)
    if denied_hits and name in {"verify_artifact", "qa_pptx_deck", "inspect_pptx_template"}:
        denied_hits = [value for value in denied_hits if not verifiable_artifact(value)]
    if denied_hits:
        if audit:
            from core.audit_log import audit_event

            audit_event("security", tool=name, args=args, decision="denied", status="protected-root")
        return False, denial_message(name, "secret_path_denied", path=denied_hits[0])

    # A read-only tool stays read-only; a credential-shaped file is the one exception,
    # because its content is the secret whatever the tool intends to do with it.
    if not chat_tool_requires_confirm(name) and not secret_paths(args):
        return True, ""

    cb = _approval_callback(on_confirm)
    params: dict[str, str] = {}
    if cb is None:
        reason = "no_approval_channel"
    else:
        try:
            if await _resolve(cb(name, args or {})):
                return True, ""
        except Exception as exc:  # noqa: BLE001 — refusal, not an aborted turn
            reason = "approval_channel_failed"
            params = {"error": type(exc).__name__}
        else:
            reason = "not_approved_by_user"

    if audit:
        from core.audit_log import audit_event

        audit_event("approval", tool=name, args=args, decision="denied", status="chat-gate")
    return False, denial_message(name, reason, **params)


#: The three answers a delegated call can get. The first is the design's own
#: exemption (a helper's whitelist stays read-only); the other two are a human's
#: decision. Naming all three is the point: whichever way the call falls, it is
#: one of these lines laid down somewhere.
DELEGATE_EXEMPT = "exempt"
DELEGATE_APPROVED = "approved"
DELEGATE_DENIED = "denied"
DELEGATE_STATUS = "delegate-gate"


def _delegate_row(name: str, args: dict, decision: str, who: str, detail: str = "") -> None:
    """One append-only row per delegated gate decision — the durable half of the record."""
    try:
        from core.audit_log import audit_event

        audit_event(
            "approval",
            tool=name,
            args=args,
            decision=decision,
            status=DELEGATE_STATUS,
            detail=f"{who} {detail}".strip(),
        )
    except Exception:  # noqa: BLE001 — the log never blocks the call it records
        pass


async def gate_delegated_tool(name: str, args: dict, *, who: str = "delegate") -> tuple[bool, str, str]:
    """(allowed, denial, record) for one tool call a delegated agent asked for.

    ``core.subagent`` and the two swarm loops run tools of their own, inside a turn
    the user started and is watching at the level of a report. Those loops reached
    ``execute_tool`` with no policy, and ``execute_tool`` skips its gate without
    one. An agent profile may name a mutating tool, so a helper wrote to the host
    with nobody asked and no line left behind — the one outcome the standing rule
    refuses (AGENTS.md, no silent default).

    The answer is the record. A read-only call runs *exempt*, and it says so;
    everything else goes to the dialog the main turn uses, where a missing channel
    counts as a no. ``record`` is a sentence for the caller to keep, so the line
    lands wherever the run is read back.
    """
    from core.tools.approval import chat_tool_requires_confirm
    from core.path_guard import secret_paths

    if not chat_tool_requires_confirm(name) and not secret_paths(args):
        record = f"[gate] {who}: {name} ran exempt from the approval gate (read-only tool)."
        _delegate_row(name, args, DELEGATE_EXEMPT, who)
        return True, "", record

    approved, denial = await confirm_for_chat(name, args, audit=False)
    if approved:
        record = f"[gate] {who}: {name} was approved by the user before it ran."
        _delegate_row(name, args, DELEGATE_APPROVED, who)
        return True, "", record

    reason = str(getattr(denial, "code", "")) or DELEGATE_DENIED
    text = DENIAL_REASONS.get(reason, reason)
    record = f"[gate] {who}: {name} was denied ({text or reason})."
    _delegate_row(name, args, DELEGATE_DENIED, who, f"({reason})")
    return False, str(denial), record


__all__ = [
    "confirm_for_chat",
    "denial_message",
    "mode_denial",
    "gate_delegated_tool",
    "DELEGATE_EXEMPT",
    "DELEGATE_APPROVED",
    "DELEGATE_DENIED",
    "DELEGATE_STATUS",
    "READ_ONLY_MODE_TOOLS",
    "DENIAL_PREFIX",
    "DENIAL_REASONS",
    "NEXT_STEP",
    "Denied",
]
