"""Reading the v1 marketplace listing.

The file is a resolution input, not an authority: install verifies the
artifact against the listing and the signature against a trusted key. A
missing or broken listing is an empty catalog, never a crash.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MARKETPLACE_FILENAME = "plugin-marketplace.json"
MARKETPLACE_VERSION = 1

def marketplace_path() -> Path:
    return Path(__file__).resolve().parent.parent / MARKETPLACE_FILENAME


def load_marketplace(path: Path | None = None) -> dict[str, Any]:
    """Fail-soft marketplace read: missing/broken → empty listing."""
    target = Path(path) if path is not None else marketplace_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": MARKETPLACE_VERSION, "plugins": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("plugins"), list):
        return {"version": MARKETPLACE_VERSION, "plugins": []}
    entries = [e for e in raw["plugins"] if isinstance(e, dict) and e.get("name")]
    return {"version": raw.get("version", MARKETPLACE_VERSION), "plugins": entries}


def resolve_entry(name: str, path: Path | None = None) -> dict[str, Any] | None:
    for entry in load_marketplace(path)["plugins"]:
        if str(entry.get("name")) == name:
            return entry
    return None


