"""SOL phase 3 — the rules a project learned, kept where the user can read them.

One Markdown file per workspace, `.ephe/learning/heuristics.md`, plain enough to
edit in any editor and structured enough to parse back:

    [HEURISTIC-H1] Node binaries live in the Homebrew prefix
    Kind: command-not-found
    Trigger: A shell call fails with "command not found" in this project
    Insight: node, npm and pnpm are installed under /opt/homebrew/bin
    Action: Call them by absolute path or prepend /opt/homebrew/bin to PATH
    Verified: 2026-10-29T14:05:00Z

The field names are English because the block enters the prompt: the engine is
instructed in one language end to end. The store itself stays a plain text file
the user owns.

Only a rule that ended a failure gets written: the turn saw the class, the
turn's later rounds did not repeat it and the turn finished. The cap keeps the
newest rules active; the rest move to `heuristics-archive.md` instead of being
deleted, so nothing the user could have read disappears silently.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, replace

from core.sol import organizer

HEURISTICS_NAME = "heuristics.md"
ARCHIVE_NAME = "heuristics-archive.md"
MAX_ACTIVE = 15

_ID_RE = re.compile(r"^\[HEURISTIC-(?P<id>[A-Za-z0-9]{1,8})\]\s*(?P<title>.*)$")
#: The English names are the format; the German ones a hand-edited file may carry
#: are read as aliases so an older block keeps working.
_FIELD_RE = re.compile(
    r"^(Kind|Trigger|Insight|Erkenntnis|Action|Aktion|Verified|Geprüft am):\s*(.*)$"
)
_FIELD_ALIAS = {
    "Erkenntnis": "Insight",
    "Aktion": "Action",
    "Geprüft am": "Verified",
}
_HEADER = (
    "# Project heuristics\n\n"
    "Rules this workspace learned from failed tool calls. Ephe reads them into the\n"
    "prompt, applies them to the failure classes they name, and stops using one the\n"
    "moment it leaves this file. Edit or delete any block; the next turn rereads it.\n"
)


@dataclass(frozen=True)
class Heuristic:
    id: str
    title: str
    kind: str = ""
    trigger: str = ""
    insight: str = ""
    action: str = ""
    verified_at: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def max_active() -> int:
    """The `sol.max_active_rules` ceiling, with the register's default as fallback."""
    try:
        from core.settings_schema import deep_number

        return max(1, int(deep_number("sol.max_active_rules")))
    except Exception:
        return MAX_ACTIVE


def heuristics_path(root=None):
    return organizer.learning_dir(root) / HEURISTICS_NAME


def archive_path(root=None):
    return organizer.learning_dir(root) / ARCHIVE_NAME


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _blocks(text: str) -> list[list[str]]:
    out: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if current:
                out.append(current)
                current = []
            continue
        current.append(line)
    if current:
        out.append(current)
    return out


def parse(text: str) -> list[Heuristic]:
    """Every well-formed block in `text`; malformed blocks are skipped, not fatal."""
    out: list[Heuristic] = []
    for block in _blocks(text or ""):
        head = _ID_RE.match(block[0])
        if not head:
            continue
        fields: dict[str, str] = {}
        for line in block[1:]:
            match = _FIELD_RE.match(line)
            if match:
                name = _FIELD_ALIAS.get(match.group(1), match.group(1))
                fields[name] = match.group(2).strip()
        out.append(
            Heuristic(
                id=head.group("id"),
                title=head.group("title").strip(),
                kind=fields.get("Kind", ""),
                trigger=fields.get("Trigger", ""),
                insight=fields.get("Insight", ""),
                action=fields.get("Action", ""),
                verified_at=fields.get("Verified", ""),
            )
        )
    return out


def render_blocks(heuristics: list[Heuristic]) -> str:
    return "\n\n".join(
        "\n".join(
            [
                f"[HEURISTIC-{item.id}] {item.title}",
                f"Kind: {item.kind}",
                f"Trigger: {item.trigger}",
                f"Insight: {item.insight}",
                f"Action: {item.action}",
                f"Verified: {item.verified_at}",
            ]
        )
        for item in heuristics
    )


def render(heuristics: list[Heuristic]) -> str:
    if not heuristics:
        return _HEADER
    return _HEADER + "\n" + render_blocks(heuristics) + "\n"


def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.part")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _read(path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load(root=None) -> list[Heuristic]:
    return parse(_read(heuristics_path(root)))


def active(limit: int = 5, root=None) -> list[Heuristic]:
    """The newest rules, for the prompt header and the reflection lookup."""
    return load(root)[:limit]


def _next_id(existing: list[Heuristic]) -> str:
    numbers = [int(item.id[1:]) for item in existing if item.id[:1] == "H" and item.id[1:].isdigit()]
    return f"H{max(numbers, default=0) + 1}"


def save(heuristics: list[Heuristic], root=None) -> list[Heuristic]:
    """Write the list; everything past the active ceiling moves to the archive."""
    ceiling = max_active()
    kept = heuristics[:ceiling]
    overflow = heuristics[ceiling:]
    try:
        _write(heuristics_path(root), render(kept))
        if overflow:
            older = parse(_read(archive_path(root)))
            merged = overflow + older
            _write(
                archive_path(root),
                "# Archived project heuristics\n\n"
                "Rules that left the active set when newer ones arrived. Move a block back\n"
                f"into {HEURISTICS_NAME} to use it again.\n\n" + render_blocks(merged) + "\n",
            )
    except OSError:
        # A read-only workspace keeps the turn working; the rule is simply not stored.
        return kept
    return kept


def record(*, kind: str, title: str, trigger: str, insight: str, action: str, root=None) -> Heuristic | None:
    """Add one rule, deduplicated by failure class. A known class updates the
    existing block (fresh verification, current wording) and keeps its id."""
    if not kind or not action:
        return None
    existing = load(root)
    for item in existing:
        if item.kind == kind:
            updated = replace(
                item,
                title=title or item.title,
                trigger=trigger or item.trigger,
                insight=insight or item.insight,
                action=action,
                verified_at=_now(),
            )
            rest = [updated] + [other for other in existing if other.id != item.id]
            save(rest, root)
            return updated
    fresh = Heuristic(
        id=_next_id(existing),
        title=title or action[:80],
        kind=kind,
        trigger=trigger,
        insight=insight,
        action=action,
        verified_at=_now(),
    )
    save([fresh] + existing, root)
    return fresh


def update(rule_id: str, *, trigger: str | None = None, action: str | None = None, root=None) -> Heuristic | None:
    items = load(root)
    for index, item in enumerate(items):
        if item.id != rule_id:
            continue
        changed = replace(
            item,
            trigger=item.trigger if trigger is None else trigger,
            action=item.action if action is None else action,
            verified_at=_now(),
        )
        items[index] = changed
        save(items, root)
        return changed
    return None


def delete(rule_id: str, root=None) -> bool:
    items = load(root)
    remaining = [item for item in items if item.id != rule_id]
    if len(remaining) == len(items):
        return False
    save(remaining, root)
    return True
