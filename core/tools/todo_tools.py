"""Ephe – todo_list (session ledger for multi-step plans).

Parity harness: a lean in-memory task list per session that the agent
uses as a structured progress ledger (not to be confused with the
persistent manage_tasks/user todo). The ledger lives in the process and counts
status per step; it is the machine-readable anchor for ephe-agent/coding-agent.

Status: pending | in_progress | completed | cancelled
"""
from __future__ import annotations

from core.reason import reason

# Session ledger: session_id → list (P0-2 isolation, no context leaking).
_LEDGERS: dict[str, list[dict[str, str]]] = {}


def _ledger_for(session_id: str) -> list[dict[str, str]]:
    from core.tools.session_ctx import get_current_session

    sid = session_id or get_current_session()
    return _LEDGERS.setdefault(sid, [])


async def todo_list(
    action: str,
    items: str = "",
    id: int | None = None,
    status: str = "",
) -> str:
    """Manages the session todo ledger.

    Args:
        action: 'set' (replace the list), 'update' (status of one entry),
                'list' (print the current state).
        items:  for 'set' — entry titles, separated by newline or ';'.
        id:     1-based index of the entry for 'update'.
        status: new status for 'update' (pending|in_progress|completed|cancelled).

    Returns:
        Confirmation or the formatted list.
    """
    from core.tools.session_ctx import get_current_session

    sid = get_current_session()
    ledger = _ledger_for(sid)
    action = (action or "").strip().lower()

    if action == "set":
        parsed = [t.strip() for t in (items or "").replace(";", "\n").splitlines() if t.strip()]
        if not parsed:
            return reason("todo_set_needs_items", "[todo_list] 'set' needs 'items' (1 title min.)")
        _LEDGERS[sid] = [{"id": i + 1, "title": t, "status": "pending"} for i, t in enumerate(parsed)]
        return _render(_LEDGERS[sid])

    if action == "update":
        if id is None or not (1 <= int(id) <= len(ledger)):
            return reason("todo_id_out_of_range",
                          f"[todo_list] update: id outside 1..{len(ledger)}",
                          limit=str(len(ledger)))
        allowed = {"pending", "in_progress", "completed", "cancelled"}
        if status not in allowed:
            return reason("todo_status_unknown",
                          f"[todo_list] invalid status '{status}' "
                          f"(allowed: {', '.join(sorted(allowed))})",
                          status=status,
                          allowed=", ".join(sorted(allowed)))
        ledger[int(id) - 1]["status"] = status
        return _render(ledger)

    if action == "list":
        return _render(ledger)

    return reason("todo_action_unknown", f"[todo_list] unknown action '{action}' (set|update|list)",
                  action=action)


def _render(ledger: list[dict[str, str]]) -> str:
    if not ledger:
        return reason("todo_list_empty", "Todo list: empty.")
    from core.ephe_plan import PLAN_HEADING

    done = sum(1 for t in ledger if t["status"] == "completed")
    lines = [f"{PLAN_HEADING} · {done}/{len(ledger)}"]
    mark_of = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]", "cancelled": "[-]"}
    for t in ledger:
        # The id stays in the line: it is the handle `action='update'` takes. The plan
        # parser strips it back off, so the reader never sees a doubled number.
        lines.append(f"- {mark_of.get(t['status'], '[ ]')} {t['id']}. {t['title']}")
    return "\n".join(lines)


def reset_todo(session_id: str = "") -> None:
    """Introspection/test: empty the ledger of a session (empty → active session)."""
    from core.tools.session_ctx import get_current_session

    sid = session_id or get_current_session()
    _LEDGERS[sid] = []


def get_todo(session_id: str = "") -> list[dict[str, str]]:
    from core.tools.session_ctx import get_current_session

    sid = session_id or get_current_session()
    return list(_LEDGERS.get(sid, []))
