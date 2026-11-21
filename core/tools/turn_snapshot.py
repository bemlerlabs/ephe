"""Task #36 — one deterministic offer array per turn (Wave 2 non-negotiable 5).

Two rules live here, both about the array the model is handed, not about which
tools exist:

1. **One stable order.** The whole array — kernel, MCP and dynamic entries — is
   sorted by tool name where it is built, so two builds of one state are
   byte-identical and a refresh that re-registers the same set cannot move a
   byte. Registration order and dict order stop being inputs to the offer.
2. **A per-turn snapshot.** The first read of a turn freezes the array under the
   turn's id; every later request of that turn — tool rounds, the retry that
   replays a captured call, the fall-over chain and the revision half that runs
   ``chat_with_tools`` again under the same id — reads the frozen one. A mid-turn
   change (an MCP tool arriving, a plugin mounted or unmounted) reaches the model
   on the NEXT turn, never to a model that was already offered this array. The
   snapshot is a view over the live registry: each turn's id is fresh and every
   rebuild reads the registry, so a frozen array cannot outlive its turn the way
   a stale cache would.

Order ties (a name the live MCP block and a same-named descriptor both carry)
keep the block order they arrived in — kernel, then MCP, then dynamic — which is
also the dispatch priority the executor resolves by.
"""
from __future__ import annotations

import threading
from typing import Any

#: How many turns keep their frozen array at most. Turn ids are single-use, so
#: an evicted id can only be reached by a turn that never ran — the entry has no
#: further reader. The cap bounds memory; it never reopens a finished turn's view.
_MAX_FROZEN_TURNS = 32

_frozen: dict[str, list[dict]] = {}
_lock = threading.Lock()


def _entry_name(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    function = entry.get("function")
    return str(function.get("name") or "") if isinstance(function, dict) else ""


def sort_tool_array(schemas: list[dict]) -> list[dict]:
    """Order one offer array by tool name, in place, where it is built.

    The sort is stable, so equal names keep their block order (kernel, MCP,
    dynamic) — the array becomes a pure function of its content.
    """
    schemas.sort(key=_entry_name)
    return schemas


def current_turn_id() -> str:
    """The turn id the running chat turn carries, or '' outside one.

    Read from the loop observer the turn already binds for its counters (the
    W1-7 pattern): the snapshot reaches the turn without a parameter through
    every signature. A caller that passes no turn id gets no freeze, and every
    read stays as live as the TTL window it has always had.
    """
    try:
        from core.loop_observability import current_observer

        observer = current_observer()
    except Exception:  # noqa: BLE001 - no observer, no freeze; the array is still built
        return ""
    return str(getattr(observer, "turn_id", "") or "") if observer is not None else ""


def frozen_tool_array() -> list[dict] | None:
    """The array the current turn froze, or None when the turn must build one."""
    turn_id = current_turn_id()
    if not turn_id:
        return None
    with _lock:
        return _frozen.get(turn_id)


def freeze_tool_array(schemas: list[dict]) -> list[dict]:
    """Bind the array to the current turn and hand it back; a helper for the reader."""
    turn_id = current_turn_id()
    if not turn_id:
        return schemas
    with _lock:
        if turn_id not in _frozen:
            while len(_frozen) >= _MAX_FROZEN_TURNS:
                _frozen.pop(next(iter(_frozen)))
            _frozen[turn_id] = schemas
        return _frozen[turn_id]


def clear_frozen_turns() -> None:
    """Drop every frozen array (the test seam; production turns age out by eviction)."""
    with _lock:
        _frozen.clear()
