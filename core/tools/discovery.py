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

#: Names every turn that offers tools keeps, whitelist or not. The ask gate is why the
#: set exists: a turn that holds no way to ask can only write the question into the
#: answer, where the reader meets a payload and not a card.
ALWAYS_OFFERED_TOOLS: frozenset[str] = frozenset({"ask_user"})

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
    # G1 (ask gate): the question a run has to ask before it can go on. Without the
    # tool in this array the model has no way to pause, so it writes the question into
    # the answer and the reader meets a payload where a card belongs.
    *ALWAYS_OFFERED_TOOLS,
    # P3 stateful-agent tools (memory + skill care) — high-frequency, always included
    "memory", "skill_manage",
    # the discovery meta tools themselves
    "tool_search", "tool_describe", "tool_call",
})

#: Families of CORE tools a turn carries only when the message asks for them.
#: A chat turn and a browser turn share almost no vocabulary, and these three
#: families are 7.6 KB of the 27.8 KB base array (measured 2026-11-12). Leaving
#: one out does not remove its tools: tool_search names them as "not in this
#: session's array, reachable through tool_call", and a direct call still
#: dispatches through the registry.
REQUESTED_ONLY_FAMILIES: dict[str, frozenset[str]] = {
    "browser": frozenset({
        "browser_go", "browser_screenshot", "browser_click", "browser_type",
        "browser_press", "browser_scroll", "browser_evaluate", "browser_exec",
    }),
    "vision": frozenset({
        "analyze_image", "take_screenshot", "vision_click", "vision_type",
        "get_display_info",
    }),
    "clipboard": frozenset({"clipboard_read", "clipboard_write"}),
}

#: Vocabulary that asks for a family. Single tokens match on word boundaries
#: (``tab`` does not fire on ``table``); a phrase with a space matches as text.
#: German words are here because the user's own message is not the product
#: surface, and a German-language turn has to reach the same tools.
_FAMILY_SIGNALS: dict[str, tuple[str, ...]] = {
    "browser": (
        "browser", "browsers", "browse", "webpage", "web page", "website",
        "web site", "url", "http", "https", "navigate", "click", "clicking",
        "scroll", "tab", "webseite", "seite", "klicke", "scrolle", "navigiere",
        "link", "button", "form", "login", "log in", "sign in", "anmelden",
    ),
    "vision": (
        "screenshot", "screenshots", "screen", "screengrab", "display",
        "monitor", "vision", "desktop", "bildschirm", "anzeige",
    ),
    "clipboard": (
        "clipboard", "copy", "paste", "zwischenablage", "kopiere", "kopieren",
        "einfuegen", "einfügen",
    ),
}

#: The family scan reads the tail of the conversation: a follow-up turn ("now log
#: in") inherits the browser family from the turn before it, and a family used
#: long ago does not linger as a standing cost.
_FAMILY_SCAN_MESSAGES = 8
_FAMILY_SCAN_CHARS = 20_000


def _message_text(message: object) -> str:
    """Content plus the names of the tool calls in one history entry."""
    if isinstance(message, dict):
        parts = [str(message.get("content") or "")]
        calls = message.get("tool_calls") or []
    else:
        parts = [str(getattr(message, "content", "") or "")]
        calls = getattr(message, "tool_calls", None) or []
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
        name = (
            function.get("name")
            if isinstance(function, dict)
            else getattr(function, "name", "")
        )
        if name:
            parts.append(str(name))
    return " ".join(part for part in parts if part)


def requested_tool_families(messages: list) -> frozenset[str]:
    """The request-gated families the recent conversation asks for."""
    recent = list(messages or [])[-_FAMILY_SCAN_MESSAGES:]
    chunks: list[str] = []
    used = 0
    for message in recent:
        text = _message_text(message)
        if not text:
            continue
        chunks.append(text)
        used += len(text)
        if used >= _FAMILY_SCAN_CHARS:
            break
    text = "\n".join(chunks).lower()[:_FAMILY_SCAN_CHARS]
    families = {
        family
        for family, signals in _FAMILY_SIGNALS.items()
        if any(
            (signal in text) if " " in signal
            else re.search(rf"(?<![a-z0-9]){re.escape(signal)}(?![a-z0-9])", text) is not None
            for signal in signals
        )
    }
    if any(
        getattr(message, "images", None)
        or (isinstance(message, dict) and message.get("images"))
        for message in recent
    ):
        families.add("vision")
    return frozenset(families)


def drop_unrequested_families(tools: list[dict], messages: list) -> list[dict]:
    """Remove the request-gated families this turn did not ask for.

    Only the base (no-whitelist) array goes through here; an active skill named
    its tools, so its whitelist is not second-guessed.
    """
    wanted = requested_tool_families(messages)
    drop: set[str] = set()
    for family, names in REQUESTED_ONLY_FAMILIES.items():
        if family not in wanted:
            drop |= names
    if not drop:
        return tools
    return [tool for tool in tools if tool.get("function", {}).get("name") not in drop]


#: The verbs that make media — a card, an effect, a music bed, a spoken line and the
#: cut that carries them. They sit outside ``CORE_TOOLS`` on purpose: all seven
#: schemas are 7 341 characters (measured 2026-11-18, ``film_clip`` alone 2 333 of
#: them) and a chat turn has no use for a cutter. What they were not supposed to cost
#: is what they cost: a turn asking for a clip with music and a voice spent five
#: ``tool_search`` calls and two ``tool_describe`` calls of a fourteen-round budget
#: reaching exactly these seven (measured on the device, 2026-11-18).
REQUESTED_EXTRA_FAMILIES: dict[str, frozenset[str]] = {
    "studio": frozenset({
        "film_card", "film_sound", "film_music", "film_clip", "film_job",
        "film_status", "synthesize",
    }),
}

#: The making verbs. A cut you cannot watch is half a cut, so when the message asks
#: for one of these, the two verbs that report on the work join unconditionally —
#: ``film_job`` (1 322 characters together with ``film_status``) is a dependency of
#: the render, not a wish.
_STUDIO_MAKING = frozenset({
    "film_card", "film_sound", "film_music", "film_clip", "synthesize",
})
_STUDIO_COMPANIONS = frozenset({"film_job", "film_status"})


def _query_terms(text: str) -> tuple[list[str], list[str]]:
    """The terms of one question and those of them that carry meaning.

    Shared with :func:`search` so that the ask which opens a tool's door is the same
    ask that would have found it by search: one vocabulary, two uses.
    """
    lowered = (text or "").lower()
    terms = [t for t in lowered.split() if len(t) >= 3]
    return terms, [t for t in terms if t not in _COMMON_TERMS]


def admit_requested_tools(
    tools: list[dict], messages: list, catalog: list[dict]
) -> list[dict]:
    """Add the media verbs this turn's own message asks for.

    Three things keep this narrow. Only the base array reaches it — a skill named its
    tools and is not second-guessed, same rule as :func:`drop_unrequested_families`.
    Only the name-and-keyword tier decides (tier 0): the description tier is a fair way
    to answer a search and a poor way to spend 2 333 characters. And a session whose
    mode refuses the writing verbs does not get offered one — the gate at
    ``chat_gate`` would refuse the call anyway, and an offer the mode answers with a
    refusal is a round the model spends learning the mode.
    """
    from core.tools.chat_gate import READ_ONLY_MODE_TOOLS
    from core.tools.session_ctx import get_current_mode

    wanted: set[str] = set()
    for names in REQUESTED_EXTRA_FAMILIES.values():
        wanted |= set(names)
    if not wanted:
        return tools
    present = {tool.get("function", {}).get("name") for tool in tools}
    missing = wanted - present
    if not missing:
        return tools

    recent = list(messages or [])[-_FAMILY_SCAN_MESSAGES:]
    chunks: list[str] = []
    used = 0
    for message in recent:
        text = _message_text(message)
        if not text:
            continue
        chunks.append(text)
        used += len(text)
        if used >= _FAMILY_SCAN_CHARS:
            break
    if not chunks:
        return tools
    terms, signal = _query_terms("\n".join(chunks)[:_FAMILY_SCAN_CHARS])
    if not terms:
        return tools

    schemas: dict[str, str] = {}
    entries: dict[str, dict] = {}
    for entry in catalog:
        function = entry.get("function", {})
        name = function.get("name")
        if name and str(name) in missing:
            schemas[str(name)] = str(function.get("description", ""))
            entries[str(name)] = entry
    # A verb the offer does not carry cannot be admitted, however well the message
    # asks for it: the array is what the model may call, and an entry invented here
    # would be a schema the registry never published.
    missing &= set(entries)

    mode = get_current_mode()
    allowed_missing = missing
    if mode in ("plan", "architect"):
        allowed_missing = missing & set(READ_ONLY_MODE_TOOLS)

    hits = {
        name
        for name in allowed_missing
        if _matched(terms, signal, name, schemas.get(name, ""), 0)
    }
    if hits & _STUDIO_MAKING:
        hits |= allowed_missing & _STUDIO_COMPANIONS
    if not hits:
        return tools
    return tools + [entries[name] for name in sorted(hits)]


#: Short descriptions for the discovery view (compact, precise).
_TOOL_HINTS: dict[str, str] = {
    "create_pdf": "PDF document from title and content (report/brief/notes).",
    "create_pptx_deck": "Real .pptx deck from a slide definition.",
    "create_pitch_deck": "Pitch deck as a 16:9 PDF with preview.",
    "inspect_pptx_template": "Inspect a PPTX template's structure.",
    "edit_pptx_template": "Fill PPTX template fields.",
    "qa_pptx_deck": "PPTX deck quality check against the rubric.",
    "create_xlsx": "Excel workbook with tables and formatting.",
    "create_docx": "Word document from structured content.",
    "create_qrcode": "QR code as PNG.",
    "create_diagram": "Diagram (mind map, timeline, flow) as SVG.",
    "create_svg": "Free-form SVG from code.",
    "generate_chart": "Data visualization (bar/line/pie) as SVG, light or dark.",
    "generate_image": "Image generation from a prompt.",
    "create_video": "Video from images or audio.",
    "film_status": "What this machine can render now (ffmpeg, voice, Pillow, SFX folder).",
    "film_card": "Typographic still as PNG (title/card/quote/stat).",
    "film_sound": "One sound effect as WAV from the built-in synth.",
    "film_music": "Music bed as WAV (calm/driving/playful/tense/corporate) at a bpm.",
    "film_clip": "Cut stills into an mp4 (captions, voice, music) with ffmpeg.",
    "film_job": "Status or cancel of a running film_clip render by job id.",
    "synthesize": "Speak a line as WAV with the local voice (read aloud, voice-over).",
    "scaffold_project": "Create a runnable project scaffold.",
    "build_document": "Report-grade briefing PDF, source-grounded.",
    "create_source_notebook": "NotebookLM-style source notebook.",
    "query_source_notebook": "Query a source notebook with citations.",
    "export_source_brief": "Export a source notebook as a briefing.",
    "agent_message": "Continue a swarm agent with a new message.",
    "execute_code": "Stateful Python kernel - variables survive calls (multi-step computation).",
    "todo_list": "Session progress ledger (add/update/list) for multi-step plans.",
    "process_manage": "Background process control (list/poll/wait/kill) by task id.",
    "read_transcript": "Your own model trajectory: numbered steps of a turn (tool calls, timing, tokens).",
    "read_cell_journal": "Read a byte range of this session's /work stdout/stderr journal (cell output the result block capped).",
    "browser_exec": "Python against the built-in browser (preimported helpers, session-isolated).",
    "memory": "Persistent notes (2 tiers: user profile + fact collection).",
    "skill_manage": "Maintain the skill catalog (list/show/create/delete).",
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
NO_MATCH_CORE_ACTIVE = "No matching deferred tools. Core tools are already active."
NO_MATCH_WHITELISTED = (
    "No tool matched. {count} core tool(s) are not in this session's array ({names}); "
    "they are callable through tool_call."
)


def _index_line(name: str, description: str, parameters: dict | None = None,
                with_args: bool = True) -> str:
    """One index line: the curated hint, else the tool's own declared description.

    The argument names ride along because a hit the model cannot call is a hit that
    costs another round: `tool_describe` answers one tool's full schema — 2 333
    characters for ``film_clip`` — and a five-verb turn pays it five times over
    (measured 2026-11-18). Required arguments carry a ``*``, optional ones are
    listed by name only and capped, and the whole line stays under a budget. On a
    listing of the whole index nobody has asked for, the names are left off: the
    budget that made this line affordable is the same one that drops them there."""
    hint = _TOOL_HINTS.get(name)
    if hint is None:
        first = (description or "").split(". ")[0].rstrip(".")
        if len(first) > 140:
            first = first[:140].rstrip() + "..."
        hint = first
    args = _args_excerpt(parameters or {}) if with_args else ""
    return f"- {name}: {hint}{args}"


#: Optional arguments named on an index line before the list truncates. Enough for a
#: model to call the verb it found without a describe round, small enough that a
#: seven-hit search still costs less than one schema.
_INDEX_OPTIONAL_ARGS = 6
_INDEX_ARG_BUDGET = 96


def _args_excerpt(parameters: dict) -> str:
    """``— args: shots*, out, fps +7 more`` from a tool's own JSON schema."""
    props = parameters.get("properties") or {}
    if not props:
        return ""
    required = [n for n in (parameters.get("required") or []) if n in props]
    optional = [n for n in props if n not in required]
    shown = [f"{n}*" for n in required] + optional[:_INDEX_OPTIONAL_ARGS]
    tail = f" +{len(optional) - _INDEX_OPTIONAL_ARGS} more" if len(optional) > _INDEX_OPTIONAL_ARGS else ""
    text = ", ".join(shown) + tail
    if len(text) > _INDEX_ARG_BUDGET:
        text = text[:_INDEX_ARG_BUDGET].rsplit(",", 1)[0].rstrip() + "…"
    return f" — args: {text}"


#: Function words carry no signal in a schema description ("the" appears in most of
#: them), so they are dropped before the description tier runs. The name tier keeps
#: them, because that index behaved that way before and matches a name literally.
_COMMON_TERMS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "then", "there", "here",
    "are", "was", "were", "you", "your", "all", "not", "its", "can", "into", "also",
    "will", "what", "when", "them", "they", "each", "some", "other", "must", "have",
})


#: Words a user's own message carries that no English hint contains. A German turn
#: asks in German, and matching only the English index answered
#: ``search("musik effekt")`` with "No matching deferred tools" on a machine holding
#: ``film_music`` and ``film_sound`` (measured 2026-11-18). The index lines stay
#: English; this table is only read when deciding whether a tool matched.
_TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "film_card": ("karte", "titel", "titelkarte", "poster", "standbild", "textbild"),
    "film_sound": ("effekt", "soundeffekt", "geraeusch", "geräusch", "sfx", "klang", "ton"),
    "film_music": ("musik", "musikk", "song", "lied", "beat", "hintergrundmusik", "bett"),
    "film_clip": ("video", "clip", "film", "schnitt", "aufnahme", "mp4", "trailer", "sequenz"),
    "film_job": ("render", "renderjob", "fortschritt", "warteschlange", "abbruch"),
    "film_status": ("ausstattung", "ausruestung", "ausrüstung", "faehigkeiten", "voraussetzungen"),
    "synthesize": ("stimme", "sprechen", "sprachausgabe", "vorlesen", "vo", "text-to-speech",
                   "voice", "voiceover", "speech", "speak", "speaks", "tts"),
    "create_video": ("video", "film", "aufnehmen"),
    "generate_image": ("bild", "illustration", "zeichnung", "foto"),
    "create_pdf": ("dokument", "bericht", "pdf", "ausarbeitung"),
    "create_docx": ("dokument", "wort", "textdatei", "brief"),
    "create_qrcode": ("qrcode", "qr-code", "barcode"),
    "generate_chart": ("diagramm", "grafik", "chart", "kurve", "säulen"),
    "create_diagram": ("diagramm", "flussdiagramm", "mindmap", "zeitstrahl"),
    "extract_pdf_text": ("text", "lesen", "extrahieren"),
}

#: Word-boundary test for one term. ``tab`` must not fire on ``table`` and ``ton``
#: (German for sound) must not fire on ``tonne``; the description tier has matched
#: this way since the index was written, the name tier matched by substring and
#: answered a two-word English question with ten unrelated tools.
def _has_word(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _matched(terms: list[str], signal: list[str], name: str, description: str, tier: int) -> bool:
    """Name + curated hint + keyword table first; the schema description only after.

    Function words are dropped before either tier: ``with`` is a term in "make a video
    with music", and as a substring it matched every hint that happened to contain the
    word — the ten-line answer to a four-word question this index exists to avoid.
    A query made of nothing but function words still has to answer something, so the
    literal terms are the fallback then.
    """
    if not terms:
        return True
    probes = signal or terms
    keys = f"{name} {_TOOL_HINTS.get(name, '')} {' '.join(_TOOL_KEYWORDS.get(name, ()))}".lower()
    if any(_has_word(keys, t) for t in probes):
        return True
    if tier == 0:
        return False
    lowered = description.lower()
    return any(_has_word(lowered, t) for t in probes)


#: Hits on one index line before the argument names are left off. A query that names
#: this many tools did not find a verb, it asked for the shelf; the per-line budget
#: only pays for itself where one verb was found.
_INDEX_ARG_MAX_HITS = 15


def _index_block(header: str, names: list[str], schemas: dict[str, str],
                 params: dict[str, dict]) -> str:
    with_args = len(names) <= _INDEX_ARG_MAX_HITS
    lines = [_index_line(n, schemas[n], params[n], with_args) for n in names]
    if with_args:
        header += " (call with tool_call; * = required argument)"
    return header + ":\n" + "\n".join(lines)


#: What a turn may ask the index before the memo stops growing.
_SEARCH_MEMO_MAX = 32

#: Queries this run already asked, with the names the index answered. A model that
#: searches the same words twice was not searching, it had lost the first answer — and
#: the round it spends re-asking is a round taken off a budget of 14 (measured
#: 2026-11-18: five searches and two describes for a five-verb task). The repeat
#: answer still names the tools, so a legitimate second ask in a later turn loses
#: nothing but the re-listing.
_SEARCH_MEMO: ContextVar[dict[str, tuple[str, ...]] | None] = ContextVar(
    "ephe_tool_search_memo", default=None)


def clear_search_memo() -> None:
    """Forget what this context searched. The turn that starts a fresh array starts
    with a fresh index question."""
    _SEARCH_MEMO.set(None)


def _repeat_answer(query: str, names: tuple[str, ...]) -> str | None:
    """The short answer when this exact query was already asked, None the first time."""
    memo = _SEARCH_MEMO.get()
    if memo is None:
        memo = {}
        _SEARCH_MEMO.set(memo)
    key = " ".join((query or "").lower().split())
    seen = memo.get(key)
    if seen is not None and seen == names:
        if not names:
            return (f"Same as your earlier search for \"{key}\": nothing matched. "
                    "Call tool_search with an empty query to read the whole index.")
        return (f"Same as your earlier search for \"{key}\" — the same {len(names)} tool(s): "
                + ", ".join(names)
                + ". Call one with tool_call; its arguments were in that first answer.")
    if len(memo) < _SEARCH_MEMO_MAX:
        memo[key] = names
    return None


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
    params: dict[str, dict] = {}
    for entry in get_tool_schemas():
        function = entry.get("function", {})
        name = function.get("name")
        if name:
            schemas[str(name)] = str(function.get("description", ""))
            declared = function.get("parameters")
            params[str(name)] = declared if isinstance(declared, dict) else {}
    deferred = deferred_names(set(schemas))
    omitted = sorted(omitted_core_tools() & set(schemas))

    def collect(names: list[str], tier: int) -> list[str]:
        return [name for name in names if _matched(terms, signal, name, schemas[name], tier)]

    # An empty query keeps the footprint it always had: the omitted names are indexed
    # only for a question that asked for something.
    parts: list[str] = []
    listed: list[str] = []
    for tier in (0, 1):
        deferred_hits = collect(deferred, tier)
        omitted_hits = collect(omitted, tier) if terms else []
        if deferred_hits:
            parts.append(_index_block(
                "Available deferred tools", deferred_hits, schemas, params))
        if omitted_hits:
            parts.append(_index_block(
                "Not in this session's array, reachable through tool_call",
                omitted_hits, schemas, params))
        listed = deferred_hits + omitted_hits
        if parts:
            break
    repeated = _repeat_answer(query, tuple(listed))
    if repeated is not None:
        return repeated
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
    return f"[tool_describe] no tool named '{name}'"


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
            return f"[tool_call] invalid JSON in 'arguments': {exc}"
    if not isinstance(args, dict):
        return "[tool_call] 'arguments' must be a JSON object"
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
