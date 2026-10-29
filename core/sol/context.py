"""The prompt block that carries what this workspace already knows.

Two parts, both read fresh per turn so an edit or deletion in the store takes
effect on the next call: the learning map the organizer keeps, and the rules
the consolidator wrote. The block is capped whole — a map plus twenty rules may
not crowd out the conversation it is meant to shorten.
"""
from __future__ import annotations

from pathlib import Path

from core.sol import consolidator, organizer

#: ~400 tokens for the whole block; the map alone is held to 200 by its own cap.
LEARNING_BLOCK_MAX_CHARS = 1_600

#: How many stored rules ride along. The rest stay readable in the file and in
#: the settings inspector; a prompt is not an inventory.
PROMPT_RULES = 5


def rules_block(limit: int = PROMPT_RULES, root: Path | None = None) -> str | None:
    rules = consolidator.active(limit, root)
    if not rules:
        return None
    rows = [f"- [{item.id}] {item.action} (trigger: {item.trigger}; verified {item.verified_at})" for item in rules]
    return "## Rules this project learned from earlier failures\n" + "\n".join(rows)


def learning_block(root: Path | None = None, *, max_chars: int = LEARNING_BLOCK_MAX_CHARS) -> str | None:
    """Map header plus stored rules, or None when the workspace has neither."""
    parts: list[str] = []
    try:
        header = organizer.map_header(root)
    except Exception:
        header = None
    if header:
        parts.append(header)
    try:
        rules = rules_block(root=root)
    except Exception:
        rules = None
    if rules:
        parts.append(rules)
    if not parts:
        return None
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text
