"""Ephe — Agent Identity Core (R28).

The agent's identity is user-editable markdown that survives every engine
switch — the pattern proven by reference A (`SOUL.md` + `/personality`) and
reference B (workspace persona files). Ephe reads `~/.ephe/persona.md`
(accepting a reference-B-style `SOUL.md` as fallback) and composes the system
prompt from:

    1. generated identity block  (factual, not editable — name/model/local)
    2. persona.md                (personality, values, tone — user editable)
    3. dynamic tool guidelines   (generated from the tool registry)
    4. skill prompt / extra directive / profile / memory / corrections / feedback

Design rules carried over from earlier rounds:
- Paths are resolved LAZILY from env (`EPHE_PERSONA_DIR`) so tests can
  redirect them after import (the import-time-binding lesson).
- A broken/oversized persona file degrades honestly to the default — a bad
  file must never kill a chat turn.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime as _dt_now
from pathlib import Path

logger = logging.getLogger(__name__)

PERSONA_FILENAME = "persona.md"
SOUL_FILENAME = "SOUL.md"
PERSONA_MAX_CHARS = 8_000

DEFAULT_PERSONA = """## Personality
- You are warm, natural and intuitive — like a brilliant friend who happens to know everything.
- You match the user's energy: casual messages get casual replies, serious questions get thorough answers.
- Keep responses proportional to the question. "Hi" → "Hey! 👋" (one line). Complex technical question → detailed explanation with formatting.
- Never over-explain simple things. Never give a 5-paragraph answer to a greeting.
- Use Markdown formatting (lists, code blocks, bold) only when it actually helps readability.
- When a request is vague or ambiguous, ask a short clarifying question first instead of guessing. Good assistants listen before they answer.
- Be honest about your limits. If you can't do something, say so clearly and suggest an alternative.

## Memory & Context
- When relevant context from memory is provided, proactively mention it: "You previously noted…". This makes you feel alive, not passive.
- Reference the user's known projects, preferences and goals when relevant. Never invent memories — only use what is explicitly provided in the context block.

## Language
- ALWAYS respond in the same language the user writes in. German → German. English → English. Japanese → Japanese. Non-negotiable.

## Working style
- Don't apologize, just fix things.
- Be helpful, be concise, be human.
"""


# W19 (live audit P0): Ask mode deliberately has NO tools. Without this guard
# models hallucinated executed tools / created files ("hello.txt ✅"),
# that never existed (evidence: disk check 2026-09-11). Strict, no softening.
ASK_MODE_GUARD = (
    "ASK-MODE GUARD (strict, non-negotiable): The user selected Ask mode — you have NO tool access "
    "in this mode. NEVER claim to have executed a tool, run a command, created, modified, or deleted "
    "a file, or fetched live web data. Never present computed output, file paths, or file contents as "
    "results of actions you performed. Answer conversationally from the conversation only; if the "
    "request needs an action, say which mode (e.g. 'Edit auto') enables it and what you would run."
)


# P4 (2026-09-15): Plan mode — read-only inspection + a plan, no mutations.
# #92: the guard names the one text shape core/ephe_plan.py writes and
# app/src/lib/planCardModel.ts reads. It also closes the question loop: an answer that ends in a
# question carries no plan, and the user gets neither.
PLAN_MODE_GUARD = (
    "PLAN-MODE GUARD (non-negotiable): The user selected Plan mode. Only read-only inspection is "
    "available — use read/list/search tools to gather facts, do NOT create, modify or delete files "
    "and do NOT run mutating commands.\n"
    "Every answer ends with a plan block in exactly this shape, written in the user's language "
    "below the fixed heading:\n"
    "## Plan\n"
    "- [ ] Read the three route files the request names\n"
    "- [ ] Add the failing case to the existing test family\n"
    "- [ ] Change the handler and keep the response shape\n"
    "- [ ] Run that family and report the count\n"
    "Rules for the block: 4 to 8 steps; one step per line, starting '- [ ]'; each step one verb on "
    "one concrete target, named from what you actually read; no numbered lists, no prose steps, "
    "and no step shorter than 12 characters — a fragment like 'Fix it' names nothing to do.\n"
    "If a decision is missing, choose the most probable option, write it as a step marked "
    "'(assumed: …)' and print the block anyway. Never end the turn on a question without a plan "
    "block — the user asked what will happen, and a question answers nothing."
)


# W19-Bench (G2/G4 finding): on arithmetic over file contents models compute in
# their head and return consistently wrong sums (51 instead of 101, 0/3 reps).
# The guard forces the calculation into a real tool — the answer must be based
# on printed tool output, not on mental math.
COMPUTE_GUARD = (
    "DATA-COMPUTATION GUARD: For ANY arithmetic over file or data contents — sums, totals, "
    "averages, differences, max/min, counts — you MUST run a real computation with the run_shell "
    "tool (a python3 or awk one-liner) and base your final numbers strictly on the printed output. "
    "Never compute totals in your head and never present mental arithmetic as file-derived results. "
    "If a computation fails, say so plainly instead of estimating."
)


def needs_compute_guard(text: str) -> bool:
    """True → the request contains arithmetic over file/data contents."""
    import re

    return bool(
        re.search(
            r"\b(?:sum|total|aggregate|average|mean|count|max|maximum|minimum|combine|"
            r"reconcile|auswerten|summe|gesamt)\b[^.?!]{0,80}?"
            r"\b(?:csv|json|files?|files'?|columns?|rows?|data|numbers?|values?|"
            r"dateien?|spalten|zeilen|zahlen|werte)\b",
            (text or ""),
            re.IGNORECASE,
        )
    )


# #92 (output half): a generated web page had no rule at all, so the engine shipped a
# browser-default document. Each line below is countable on the rendered page, and
# docs/PLAN_SURFACE_2026-10-11.md section 5 holds the same list as the bar.
PAGE_OUTPUT_GUARD = (
    "PAGE GUARD (a generated web page): the deliverable is a designed document. One HTML file, "
    "meeting every line:\n"
    "- exactly one <h1>, at least three heading levels, at least four top-level sections, each "
    "section with its own heading and its own content;\n"
    "- a type scale of at least four sizes, each step at least 1.25 times the one below it, body "
    "copy at 16px or larger and a display size at least twice body;\n"
    "- spacing drawn from one repeating scale of at least four values, with a section gap of at "
    "least 64px on desktop; no one-off pixel literal for a gap;\n"
    "- text at 4.5:1 against the background it actually sits on, large text at 3:1; state the two "
    "colours you picked and check the pair;\n"
    "- a hero carrying one sentence about this product and one primary action, then the sections; "
    "a centered stack of unstyled paragraphs fails this line;\n"
    "- no emoji in a heading, no remote stock image, a font stack that renders offline;\n"
    "- no horizontal scroll at 390px and at 1280px, with the media queries for both written out;\n"
    "- copy written for the named product in the user's language. Lorem ipsum, 'Your product here' "
    "and an empty section are failures of this guard."
)


def needs_page_guard(text: str) -> bool:
    """True → the request asks for a web page to be built. Two parts, like
    needs_compute_guard: a making verb near a page noun. Bare 'Seite' would match
    'on the left side', so it only counts as part of a compound page noun."""
    import re

    return bool(
        re.search(
            r"\b(?:build|builds|created?|creating|make|makes|made|design|designs|generate|"
            r"generates|write|writes|need|needs|want|wants|plan|plans|give|baue|bauen|bau|"
            r"erstelle|erstellen|gestalte|gestalten|generiere|brauche|brauchen|brauchst|"
            r"mache|machen|will|möchte|moechte|mochte|entwerfe|entwerfen)\b"
            r"[^.?!]{0,40}?"
            r"\b(?:landing[\s-]?page|landingpage|web[\s-]?page|webpage|web[\s-]?site|website|"
            r"homepage|webseite|internetseite|webpräsenz|webpraesenz|one[\s-]?pager|site)\b",
            (text or ""),
            re.IGNORECASE,
        )
    )


def _persona_dir() -> Path:
    """Persona storage dir, resolved lazily so tests can redirect via env."""
    return Path(os.environ.get("EPHE_PERSONA_DIR", str(Path.home() / ".ephe")))


def persona_path() -> Path:
    return _persona_dir() / PERSONA_FILENAME


_MARKER = "[persona]"


def _strip_marker(text: str) -> str:
    """The load-time marker must never accumulate inside the stored file.

    The Settings editor shows what load_persona() returned (marker included);
    saving that back verbatim used to nest one marker per save cycle.
    """
    stripped = text.strip("\n")
    while stripped.startswith(_MARKER):
        stripped = stripped[len(_MARKER):].strip("\n")
    return stripped


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def load_persona() -> str:
    """Load the user persona with honest degradation.

    Order: persona.md → SOUL.md (reference-B compatibility) → default.
    The result is capped to PERSONA_MAX_CHARS.
    """
    text = _read_text(persona_path())
    if text is None or not text.strip():
        text = _read_text(_persona_dir() / SOUL_FILENAME)
    if text is None or not text.strip():
        text = DEFAULT_PERSONA
    return _MARKER + "\n" + _strip_marker(text)[:PERSONA_MAX_CHARS]


def load_persona_for_editor() -> str:
    """The text the settings screen edits — without the assembly prefix.

    The prompt needs [persona] as a section marker; an editor that shows it
    must not demand it from the user as the first line."""
    return _strip_marker(load_persona())


def persona_source() -> str:
    """Which file the persona currently comes from (for the settings UI)."""
    if _read_text(persona_path()) and (persona_path().read_text(encoding="utf-8").strip()):
        return str(persona_path())
    soul = _persona_dir() / SOUL_FILENAME
    if _read_text(soul) and soul.read_text(encoding="utf-8").strip():
        return str(soul)
    return "default"


def write_persona(text: str) -> None:
    """Persist the user persona (atomic, 0600 — same convention as engine.json)."""
    text = _strip_marker(text)
    if len(text) > PERSONA_MAX_CHARS:
        raise ValueError(f"persona too large ({len(text)} > {PERSONA_MAX_CHARS} chars)")
    path = persona_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def create_default_persona_if_missing() -> bool:
    """Write the default persona file on first use. Idempotent, never
    overwrites an existing persona.md or SOUL.md. Returns True if written."""
    path = persona_path()
    soul = _persona_dir() / SOUL_FILENAME
    if (path.exists() and _read_text(path)) or (soul.exists() and _read_text(soul)):
        return False
    try:
        write_persona(DEFAULT_PERSONA)
        logger.info("Default persona written to %s", path)
        return True
    except OSError as exc:
        logger.warning("Could not write default persona: %s", exc)
        return False


def build_identity_block(model: str) -> str:
    """Factual identity — generated, never user-editable, never faked.

    The agent's NAME belongs to the harness (like reference A/B); the
    underlying model is disclosed honestly but never becomes the identity.

    W3-38 (byte-stable prefix): this block carries NO time-varying text. The
    current date moved into its own block (``build_date_block``) that the
    assembly appends LAST, so the identity bytes — the very front of every
    request — are identical turn over turn and the engine's prefix cache holds.
    """
    from core import __edition__, __version__

    return (
        "IDENTITY:\n"
        f"- You are Ephe — the user's local AI agent, running 100% locally on their device. No cloud, no tracking.\n"
        f"- You are currently powered by the model \"{model}\". Disclose this honestly if asked — "
        "but your name is Ephe regardless of the underlying model; never claim to be a different assistant.\n"
        f"- Edition: {__edition__} {__version__}."
    )


def build_date_block(now=None) -> str:
    """The single per-day block, kept OUT of the identity prefix (W3-38).

    Its only job is to tell the model today's date. Because it rotates once a
    day it must not sit in front of otherwise byte-stable content; the assembly
    appends it after the per-turn volatile context, so its daily rotation
    cannot cut the cacheable prefix short.
    """
    today = (now or _dt_now.now()).strftime("%Y-%m-%d")
    return f"Current date: {today}."


def build_tool_guidelines(allowed_tool_names: list[str] | None = None) -> str:
    """Dynamic tool guidelines generated from the registry.

    The API already delivers full tool schemas to the model — duplicating
    descriptions here would be redundant. This section groups tool NAMES by
    our security classification (read-only vs. approval-gated) and states the
    behavioral rules.

    P1-5 (deep audit 2026-09-13): when the active skill sets a tool whitelist
    (allowed_tool_names), the name list mentioned in the system text is filtered
    to exactly that subset. Otherwise the text names all 52 tools while the
    API array only delivers the whitelist — small models (gemma4:12b,
    qwen3:4b) then hallucinate calls to tools that do not exist.
    """
    from core.tools.approval import SAFE_TOOLS
    from core.tools.registry import get_tool_schemas

    schemas = get_tool_schemas()
    names = [
        entry.get("function", {}).get("name", "")
        for entry in schemas
        if entry.get("function", {}).get("name")
    ]
    if allowed_tool_names:
        allowed = set(allowed_tool_names)
        names = [n for n in names if n in allowed]
    safe = sorted(n for n in names if n in SAFE_TOOLS)
    action = sorted(n for n in names if n not in SAFE_TOOLS)
    lines = [
        "Tools & Capabilities:",
        f"- Read-only tools (always allowed): {', '.join(safe)}." if safe else "- No read-only tools registered.",
        (
            f"- Action tools (some require explicit user approval before they run): {', '.join(action)}."
            if action
            else "- No action tools registered."
        ),
        "- Use tools when the question demands it — not for simple conversation.",
        "- Use 'web_search' for internet research. Cite sources with URLs under '📎 Sources:'.",
        "- You can create real local artifacts (PDFs, decks, charts, SVGs, notebooks) when the matching tool exists — never claim you can only provide an outline.",
        "- Never say \"As an AI I cannot...\" — check the tool list above and act.",
        "- Action tools run behind an approval gate when they change your system; that is by design — proceed, the user decides.",
        "- AskUserQuestion convention: when offering the user a choice, append a fenced json block "
        "{\"question\": str, \"options\": [{\"label\": str, \"description\": str}], "
        "\"recommendation\": \"<label or 1-based number>\", \"multiSelect\": bool}; "
        "the UI renders it as a tappable options card.",
        "- To ask inside the run: call 'ask_user' when the turn cannot honestly go on without the "
        "user's answer. The run pauses, the question appears while the turn is still open, and the "
        "answer comes back as that tool's result — the same turn continues with it in context. "
        "Pass 'default' with the question: when nobody answers within the timeout the run continues "
        "on that value and says so, so a pause never turns into a silent hang.",
    ]
    return "\n".join(lines)
