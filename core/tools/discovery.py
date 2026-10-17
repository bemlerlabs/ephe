"""Ephe – progressive tool discovery (parity harness, Wave 3).

Without a skill whitelist the registry pumps all 55 schemas (~8k tokens) into every
conversation. Most of them are specialized artifact generators that one
turn rarely needs at the same time. This module splits the landscape:

  - CORE_TOOLS: always in the API array (high-frequency, small footprint).
  - DEFERRED_TOOLS: not in the base array; the model reaches them via
    tool_search (name + short description) -> tool_call (execution).

The whitelist path (an active skill sets allowed_tool_names) keeps its declared
tools plus the meta tools plus the file primitives; deferred status does not filter
it, but search() is session-aware and reports what such a session was left without.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from contextvars import ContextVar

#: The three discovery meta tools — appended to EVERY non-empty whitelist path
#: (P0-1), so progressive disclosure also applies with an active skill.
META_TOOL_NAMES: frozenset[str] = frozenset({
    "tool_search", "tool_describe", "tool_call",
})

#: The file primitives, appended to a NON-empty whitelist for the same reason the
#: meta tools are: the skill list is the session's whole array, and a session that
#: cannot read the workspace reports its own files as absent. Measured 2026-10-10:
#: 33 of 37 endstate reps without read_file failed, 2 of 42 with it
#: (docs/ENDSTATE_DELTA_2026-10-10.md).
FILE_PRIMITIVE_TOOLS: frozenset[str] = frozenset({
    "read_file", "write_file", "edit_file", "delete_file", "list_directory", "file_search",
})

#: What every non-empty whitelist keeps: the three read primitives, all classified
#: SAFE, so no restricted mode widens through them.
READ_ONLY_FILE_TOOLS: frozenset[str] = frozenset({
    "read_file", "list_directory", "file_search",
})

#: The mutating half of the file primitives. A whitelist that declares one of these
#: is a file-working session and gets all six; one that declares none stays at the
#: read trio. The restricted mode strips these names from the whitelist before the
#: array is built, which is what this rule preserves.
FILE_MUTATING_TOOLS: frozenset[str] = frozenset({
    "write_file", "edit_file", "delete_file",
})


def file_primitives_for(allowed_tool_names: Iterable[str] | None) -> frozenset[str]:
    """The file names a whitelisted session keeps, tiered by what it declared."""
    if set(allowed_tool_names or ()) & FILE_MUTATING_TOOLS:
        return FILE_PRIMITIVE_TOOLS
    return READ_ONLY_FILE_TOOLS

#: Always in the base array: file/shell/test core, research, verification,
#: Kernel, Ledger, Process, Browser, Vision.
CORE_TOOLS: frozenset[str] = frozenset({
    "read_file", "write_file", "edit_file", "list_directory", "file_search",
    "run_shell", "run_tests", "task_output", "task_stop", "process_manage",
    # G6 (workbench): the agent reads its own run — the transcript it was shown
    # and the cell journal behind a capped result. Both in the base array so
    # transparency needs no tool_search round-trip.
    "read_transcript", "read_cell_journal",
    "web_search", "fetch_url",
    "verify_artifact", "execute_code", "todo_list", "manage_tasks", "get_datetime",
    "analyze_image", "take_screenshot",
    "browser_go", "browser_screenshot", "browser_click", "browser_type",
    "browser_press", "browser_scroll", "browser_evaluate",
    "clipboard_read", "clipboard_write", "get_display_info",
    "browser_exec",
    "vision_click", "vision_type",
    "analyze_project", "discover_projects", "load_workspace",
    # P3 stateful-agent tools (memory + skill care) — high-frequency, always included
    "memory", "skill_manage",
    # the discovery meta tools themselves
    "tool_search", "tool_describe", "tool_call",
})

#: Short descriptions for the discovery view (compact, precise).
_TOOL_HINTS: dict[str, str] = {
    "create_pdf": "PDF-Dokument aus Titel+Content (report/brief/notes).",
    "create_pptx_deck": "Echtes .pptx-Deck aus Folien-Definition.",
    "create_pitch_deck": "Pitch-Deck als 16:9-PDF mit Preview.",
    "inspect_pptx_template": "PPTX-Template-Struktur inspizieren.",
    "edit_pptx_template": "PPTX-Template-Felder fuellen.",
    "qa_pptx_deck": "PPTX-Deck-Qualitaetscheck (Rubric).",
    "create_xlsx": "Excel-Arbeitsmappe mit Tabellen/Formatierung.",
    "create_docx": "Word-Dokument aus strukturiertem Content.",
    "create_qrcode": "QR-Code als PNG.",
    "create_diagram": "Fluss-/Saeulendiagramm als SVG.",
    "create_svg": "Freies SVG aus Code.",
    "generate_chart": "Datenvisualisierung (Balken/Linie/Kreis) als PNG.",
    "generate_image": "Bildgenerierung aus Prompt.",
    "create_video": "Video aus Bildern/Audio.",
    "scaffold_project": "Lauffaehiges Projekt-Geruest erzeugen.",
    "build_document": "Report-Grade-Briefing-PDF (quellenbasiert).",
    "create_source_notebook": "NotebookLM-artiges Quellen-Notebook.",
    "query_source_notebook": "Quellen-Notebook abfragen (zitiert).",
    "export_source_brief": "Quellen-Notebook als Briefing exportieren.",
    "agent_message": "Schwarm-Agent mit neuer Nachricht fortsetzen.",
    "execute_code": "Stateful Python-Kernel — Variablen ueberleben Aufrufe (mehrfache Berechnung).",
    "todo_list": "Session-Fortschritts-Ledger (add/update/list) fuer mehrstufige Plaene.",
    "process_manage": "Hintergrund-Prozess-Kontrolle (list/poll/wait/kill) ueber Task-ID.",
    "read_transcript": "Your own model trajectory: numbered steps of a turn (tool calls, timing, tokens).",
    "read_cell_journal": "Read a byte range of this session's /work stdout/stderr journal (cell output the result block capped).",
    "browser_exec": "Python gegen den eingebauten Browser (vorimportierte Helpers, Session-isoliert).",
    "memory": "Persistente Notizen (2-Tier: user-Profil + Fakten-Collection).",
    "skill_manage": "Skill-Katalog pflegen (list/show/create/delete).",
}

#: Non-CORE tools with a schema = deferrable.
def deferred_names(all_names: set[str]) -> list[str]:
    return sorted(n for n in all_names if n not in CORE_TOOLS)


#: The array the current session was built with, recorded by the chat array builder.
#: ContextVar because several sessions interleave in one process, which is also why
#: the approval policy is carried this way. None = no array was built in this context,
#: read as an unfiltered session (every core tool active).
_SESSION_ARRAY: ContextVar[frozenset[str] | None] = ContextVar("ephe_session_tool_array", default=None)


def set_session_tool_array(names: Iterable[str] | None) -> None:
    """Record the names the session was handed; None clears the session state."""
    _SESSION_ARRAY.set(frozenset(names) if names is not None else None)


def clear_session_tool_array() -> None:
    _SESSION_ARRAY.set(None)


def omitted_core_tools() -> frozenset[str]:
    """CORE_TOOLS names this session's array left out (empty when nothing was)."""
    array = _SESSION_ARRAY.get()
    return frozenset() if array is None else CORE_TOOLS - array


#: A search that hits nothing. The second answer is the one a whitelisted session
#: needs: the first claims the core tools are active, which is false right after a
#: skill whitelist removed them from the array.
NO_MATCH_CORE_ACTIVE = "Keine passende Deferred-Tools. Kern-Tools sind bereits aktiv."
NO_MATCH_WHITELISTED = (
    "No tool matched. {count} core tool(s) are not in this session's array ({names}); "
    "they are callable through tool_call."
)


def _index_line(name: str, description: str) -> str:
    """One index line: the curated hint, else the tool's own declared description."""
    hint = _TOOL_HINTS.get(name)
    if hint:
        return f"- {name}: {hint}"
    first = (description or "").split(". ")[0].rstrip(".")
    if len(first) > 140:
        first = first[:140].rstrip() + "..."
    return f"- {name}: {first}"


#: Function words carry no signal in a schema description ("the" appears in most of
#: them), so they are dropped before the description tier runs. The name tier keeps
#: them, because that index behaved that way before and matches a name literally.
_COMMON_TERMS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "then", "there", "here",
    "are", "was", "were", "you", "your", "all", "not", "its", "can", "into", "also",
    "will", "what", "when", "them", "they", "each", "some", "other", "must", "have",
})


def _matched(terms: list[str], signal: list[str], name: str, description: str, tier: int) -> bool:
    """Name + curated hint first; the schema description only when that found nothing."""
    if not terms:
        return True
    if any(t in f"{name} {_TOOL_HINTS.get(name, '')}".lower() for t in terms):
        return True
    if tier == 0:
        return False
    lowered = description.lower()
    return any(re.search(rf"\b{re.escape(t)}\b", lowered) for t in signal)


def search(query: str) -> str:
    """Compact index hit: name + short description of the tools reachable from here.

    A schema description is consulted only after the name-and-hint index came up
    empty: delete_file's rename behaviour lives there and nowhere else a search can
    read, while ~50 loose English descriptions turn any two-word question into a
    40-line answer (measured 2026-10-10) — the footprint this index exists to avoid.
    """
    from core.tools.registry import get_tool_schemas

    q = (query or "").lower()
    terms = [t for t in q.split() if len(t) >= 3]
    signal = [t for t in terms if t not in _COMMON_TERMS]
    schemas: dict[str, str] = {}
    for entry in get_tool_schemas():
        function = entry.get("function", {})
        name = function.get("name")
        if name:
            schemas[str(name)] = str(function.get("description", ""))
    deferred = deferred_names(set(schemas))
    omitted = sorted(omitted_core_tools() & set(schemas))

    def collect(names: list[str], tier: int) -> list[str]:
        return [name for name in names if _matched(terms, signal, name, schemas[name], tier)]

    # An empty query keeps the footprint it always had: the omitted names are indexed
    # only for a question that asked for something.
    parts: list[str] = []
    for tier in (0, 1):
        deferred_hits = collect(deferred, tier)
        omitted_hits = collect(omitted, tier) if terms else []
        if deferred_hits:
            parts.append(
                "Verfuegbare Deferred-Tools:\n"
                + "\n".join(_index_line(name, schemas[name]) for name in deferred_hits)
            )
        if omitted_hits:
            parts.append(
                "Not in this session's array, reachable through tool_call:\n"
                + "\n".join(_index_line(name, schemas[name]) for name in omitted_hits)
            )
        if parts:
            break
    if parts:
        return "\n".join(parts)
    if omitted:
        sample = ", ".join(omitted[:8])
        if len(omitted) > 8:
            sample += f", {len(omitted) - 8} more"
        return NO_MATCH_WHITELISTED.format(count=len(omitted), names=sample)
    return NO_MATCH_CORE_ACTIVE


def describe(name: str) -> str:
    """Full JSON schema of a tool (for the model context when needed)."""
    from core.tools.registry import get_tool_schemas

    for entry in get_tool_schemas():
        if entry.get("function", {}).get("name") == name:
            return json.dumps(entry, ensure_ascii=False)
    return f"[tool_describe] kein Tool '{name}' gefunden"


async def tool_search(query: str = "") -> str:
    """Searches the deferred index by tool name/short description."""
    return search(query)


async def tool_describe(name: str) -> str:
    """Returns the full JSON schema of a tool (on-demand activation)."""
    return describe(name)


async def tool_call(name: str, arguments: str = "{}") -> str:
    """Executes an (also deferred) tool through the normal registry.

    `arguments` is a JSON object as a string, so small models hit
    it as one single string argument; a dict is tolerated.
    """
    from core.tools.registry import execute_tool

    if isinstance(arguments, dict):
        args = arguments
    else:
        try:
            args = json.loads(arguments) if (arguments or "").strip() else {}
        except json.JSONDecodeError as exc:
            return f"[tool_call] ungueltiges JSON in 'arguments': {exc}"
    if not isinstance(args, dict):
        return "[tool_call] 'arguments' muss ein JSON-Objekt sein"
    # P1a: forward the active approval policy so the inner tool goes
    # through the same approval gate as a directly called one (no gate bypass).
    from core.tools.session_ctx import get_current_policy
    from core.tools.chat_gate import confirm_for_chat

    policy = get_current_policy()
    if policy is None:
        # Without a policy execute_tool does not gate — then the gate is HERE. Otherwise
        # the meta router would be an auto-run window onto every mutating tool.
        approved, denial = await confirm_for_chat(name, args)
        if not approved:
            return denial
    return await execute_tool(name, args, policy=policy)
