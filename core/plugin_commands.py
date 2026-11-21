"""Server-side expansion of plugin slash commands (CAP-04, CAP-05).

The client sends the command intent; the server replaces `{input}` in the
manifest's template. A command whose name belongs to one of the five
command/skill pairs is left untouched: the skill keeps the native name and the
deterministic collision rule decides, not the order in which a client listed
them.
"""
from __future__ import annotations

from pathlib import Path

from core import plugin_manifest
from core.plugin_registry import DUPLICATE_COMMANDS


def expand_plugin_command(text: str, root: Path | None = None) -> str:
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return text
    parts = raw.split(maxsplit=1)
    command = parts[0][1:].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""
    if not command:
        return text
    for entry in plugin_manifest.manifest_commands(root):
        name = str(entry.get("name") or "").lstrip("/").lower()
        if name != command:
            continue
        plugin = str(entry.get("plugin") or "")
        if (plugin, command) in DUPLICATE_COMMANDS:
            return text
        template = str(entry.get("template") or "")
        if not template:
            return text
        if "{input}" in template:
            if not argument:
                return f"[{parts[0]}] Usage: {parts[0]} <text>"
            return template.replace("{input}", argument)
        return template + (" " + argument if argument else "")
    return text
