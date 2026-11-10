"""The host half of a plugin surface, kept beside the mount record.

The mount record says which tools a bundle published. This record says where
the shell put the window: which slot, the box, and whether that window is
open. The page inside the frame keeps its own scroll and form values on the
client storage route. A field from that page is refused here, so a restart
can put the window back without replaying the page.
"""

from __future__ import annotations

from typing import Any

SURFACES_FIELD = "surfaces"

SLOTS = frozenset({"overlay", "native"})

FIELDS = (
    "slot",
    "x",
    "y",
    "width",
    "height",
    "open",
    "minimized",
    "placed",
)

_X_LIMIT = 16_384
_SIZE_LIMIT = 8_192


def _whole(value: object, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("bounds")
    if value < low or value > high:
        raise ValueError("bounds")
    return value


def parse_host_record(body: object) -> dict[str, Any]:
    """The host record, or ValueError when the body carries anything else.

    `placed` is false when the shell has not reported a position yet. A
    restore then keeps the shell's own placement and still keeps the size.
    """
    if not isinstance(body, dict) or set(body) != set(FIELDS):
        raise ValueError("shape")
    slot = body.get("slot")
    if slot not in SLOTS:
        raise ValueError("slot")
    if not isinstance(body.get("open"), bool):
        raise ValueError("open")
    if not isinstance(body.get("minimized"), bool):
        raise ValueError("minimized")
    if not isinstance(body.get("placed"), bool):
        raise ValueError("placed")
    return {
        "slot": slot,
        "x": _whole(body.get("x"), -_X_LIMIT, _X_LIMIT),
        "y": _whole(body.get("y"), -_X_LIMIT, _X_LIMIT),
        "width": _whole(body.get("width"), 1, _SIZE_LIMIT),
        "height": _whole(body.get("height"), 1, _SIZE_LIMIT),
        "open": body["open"],
        "minimized": body["minimized"],
        "placed": body["placed"],
    }


def load_surfaces(raw: dict[str, Any], data: dict[str, Any]) -> None:
    """Reads host records. A damaged section is dropped.

    Switch truth stays where it was. A geometry section the reader cannot
    trust is empty, and the plugins stay on the states the file committed.
    """
    data[SURFACES_FIELD] = {}
    section = raw.get(SURFACES_FIELD)
    if not isinstance(section, dict):
        return
    kept: dict[str, dict[str, Any]] = {}
    for plugin_id, record in section.items():
        if not isinstance(plugin_id, str) or not isinstance(record, dict):
            continue
        try:
            kept[plugin_id] = parse_host_record(record)
        except ValueError:
            continue
    data[SURFACES_FIELD] = kept


def merge_surfaces(
    merged: dict[str, Any],
    local: dict[str, Any] | None,
    loaded: dict[str, Any] | None,
) -> None:
    """Writes the host records this process changed and leaves the rest."""
    records = merged.get(SURFACES_FIELD)
    if not isinstance(records, dict):
        records = {}
        merged[SURFACES_FIELD] = records
    previous = loaded or {}
    for plugin_id, record in (local or {}).items():
        if previous.get(plugin_id) != record:
            records[str(plugin_id)] = dict(record)
    # A `forget` or a cleared placement deletes this instance's record; a key
    # another process wrote after this instance loaded stays.
    for plugin_id in list(records):
        if plugin_id in previous and plugin_id not in (local or {}):
            records.pop(plugin_id, None)
