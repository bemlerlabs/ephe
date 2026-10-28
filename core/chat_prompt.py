"""System-prompt assembly and model-trait helpers.

Extracted from core/chat.py (2026-10-11). Owns the persona/tool-guideline
prompt build, the native-thinking model tables, detect-timeout classification
and the open-plan nudge settings; core/chat.py re-exports the public names.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.chat_context import _active_context_window, _fit_messages_to_window
from core.corrections import CorrectionJournal
from core.feedback import FeedbackStore
from core.memory import Memory
from core.profile import load_profile

# Native Ollama thinking is model-specific. Ephe keeps reasoning hidden by
# default for Gemma 4 12B; otherwise short answers can spend the entire token
# budget in Ollama's `thinking` field and return empty visible content.
NATIVE_THINKING_MODELS = (
    "deepseek-r1",
    "gpt-oss",
)


DISABLE_NATIVE_THINKING_MODELS = (
    "gemma4:12b",
)


TOOL_DETECT_TIMEOUT_DEFAULT = float(os.environ.get("EPHE_TOOL_DETECT_TIMEOUT", "45"))


TOOL_DETECT_TIMEOUT_SMALL_MODEL = float(os.environ.get("EPHE_SMALL_MODEL_TIMEOUT", "25"))


# Large reasoning models (27B+) need markedly longer for the
# tool detection: a long reasoning phase before the tool call + long
# system prompts. 120s budget instead of 25s (the timeout
# budget follows the model class (never the name).
TOOL_DETECT_TIMEOUT_LARGE_REASONING = float(os.environ.get("EPHE_LARGE_REASONING_TIMEOUT", "120"))


# R28: the hardcoded EPHE_SYSTEM_PROMPT is gone. Identity now comes from
# core/persona.py — a generated identity block + the user-editable
# persona.md + dynamic tool guidelines (see assemble_system_prompt below).



# Thinking Mode (tag parser plus native support for selected models)
THINK_OPEN  = "<|think|>"
THINK_CLOSE = "<|/think|>"


# Thinking Mode (tag parser plus native support for selected models)
THINK_OPEN  = "<|think|>"


# Wave 7: the knowledge-gap protocol — always active, so the model marks gaps
# in the answer text with [[GAP: topic]] (parser: core.knowledge_gap).
#: Wave 2 (B1): the cap the custom-instruction layer is read under. The editor in
#: the behaviour settings stops here; the prompt marks a truncation if a stored
#: value ever arrives longer (a hand-edited settings.json, a lowered cap).
CUSTOM_INSTRUCTIONS_MAX = 4000


def custom_instructions_block() -> str | None:
    """The user's own instruction layer, provenance-marked, capped; None when empty.

    Read through the settings accessor so the register proof finds a real consumer.
    The marker names the source: the model has to be able to tell the user's words
    from the system's own voice.
    """
    from core.settings_schema import deep_value

    try:
        raw = str(deep_value("chat.custom_instructions") or "").strip()
    except Exception:
        return None
    if not raw:
        return None
    if len(raw) > CUSTOM_INSTRUCTIONS_MAX:
        raw = (
            raw[:CUSTOM_INSTRUCTIONS_MAX].rstrip()
            + f"\n… truncated ({CUSTOM_INSTRUCTIONS_MAX} of {len(raw)} chars shown)."
        )
    return (
        "## Custom instructions (from this device's settings — the user's own words, "
        "standing for every turn)\n\n" + raw
    )


# W3-38: a module constant (never built inline) so its bytes are provably the
# same every turn — it is part of the cacheable prefix.
KNOWLEDGE_GAP_PROTOCOL = (
    "Knowledge-gap protocol: when the answer needs knowledge you cannot "
    "confidently derive from the context, mark the gap in the answer text "
    "exactly as [[GAP: topic]] (once per gap). The system then researches "
    "automatically and appends the sources."
)


def _workspace_anchor() -> str | None:
    """The active project, named with its absolute path (QD-015 Z3).

    Every turn used to learn the workspace only from the tool schema or from
    listing directories, so it began by looking for the tree it was meant to
    work in. One stable block names it up front; it changes per workspace, not
    per turn, so it sits with the other rarely-changing context.
    """
    try:
        from core.workspace_rules import resolve_workspace_dir

        raw = str(resolve_workspace_dir() or "").strip()
        if not raw:
            return None
        root = Path(raw).expanduser().resolve()
    except Exception:
        return None
    return (
        "## Active workspace\n"
        f"Name: {root.name or root}\n"
        f"Path: {root}\n"
        "Relative paths in this conversation resolve against this root."
    )


def assemble_system_prompt(
    *,
    model: str,
    incoming_system: str | None = None,
    extra_system_prompt: str | None = None,
    custom_instructions_ctx: str | None = None,
    workspace_rules_ctx: str | None = None,
    workspace_ctx: str | None = None,
    profile_ctx: str | None = None,
    memory_ctx: str | None = None,
    corrections_ctx: str | None = None,
    feedback_ctx: str | None = None,
    allowed_tool_names: list[str] | None = None,
) -> str:
    """R28: compose the system prompt in a FIXED, testable order.

    W3-38 (byte-stable prefixes, Manus' law): the blocks are ordered
    MOST-stable → LEAST-stable so the longest possible byte-prefix is identical
    between two turns and the engine's prefix cache can reuse it. The static
    core and the constant protocol are byte-identical turn over turn; the
    per-turn memory injection and the once-a-day date block sit at the tail,
    where their churn cannot invalidate the blocks in front of them.

    1. generated identity block (factual: name, model disclosure, local) — static
    2. user persona (persona.md / SOUL.md — personality, tone, boundaries)
    3. dynamic tool guidelines (from the registry, never a static list)
    4. skill system prompt arriving as messages[0] (skill packs inject here)
    5. extra directive (e.g. the R22 coding-agent brief)
    6. constant knowledge-gap protocol (KNOWLEDGE_GAP_PROTOCOL)
    7. custom instructions (this device's standing words, provenance-marked)
    8. active workspace (name + absolute path) and its project rules
       (AGENTS.md and .ephe/rules/*, provenance-marked)
    9. user profile → 10. corrections → 11. feedback   (rarely change)
    12. memory (per-turn volatile) → 13. current date block (per-day, last)

    The user's global instructions sit ahead of the project's own files because
    the more specific voice speaks last.
    """
    from core.persona import (
        build_date_block,
        build_identity_block,
        build_tool_guidelines,
        create_default_persona_if_missing,
        load_persona,
    )

    # First use: materialize the editable default so the user can customize it.
    create_default_persona_if_missing()

    parts: list[str] = [
        build_identity_block(model),
        load_persona(),
        build_tool_guidelines(allowed_tool_names),
    ]
    if incoming_system:
        parts.append(incoming_system)
    if extra_system_prompt:
        parts.append(extra_system_prompt)
    # The constant protocol sits at the end of the static core — in front of
    # every block that can change, so it always lies inside the cached prefix.
    parts.append(KNOWLEDGE_GAP_PROTOCOL)
    for ctx in (
        custom_instructions_ctx,
        workspace_ctx,
        workspace_rules_ctx,
        profile_ctx,
        corrections_ctx,
        feedback_ctx,
    ):
        if ctx:
            parts.append(ctx)
    # Per-turn volatile last (before the daily date): a memory change breaks the
    # prefix only at the tail, never over the stable core or the conversation.
    if memory_ctx:
        parts.append(memory_ctx)
    parts.append(build_date_block())
    return "\n\n".join(part for part in parts if part)


def supports_native_thinking(model: str) -> bool:
    normalized = (model or "").lower()
    return any(normalized.startswith(prefix) for prefix in NATIVE_THINKING_MODELS)


def _native_thinking_kwargs(model: str) -> dict[str, bool]:
    normalized = (model or "").lower()
    if any(normalized.startswith(prefix) for prefix in DISABLE_NATIVE_THINKING_MODELS):
        return {"think": False}
    return {"think": True} if supports_native_thinking(model) else {}


def _model_param_billions(model: str) -> float | None:
    r"""Extract the parameter size (in B) from the model name.

    'qwen3:4b' → 4.0, 'qwen3.8-27b' → 27.0, 'gemma4:12b' → 12.0,
    'custom-anything' → None. Matches the last '<number>b' token (the
    parameter figure), never version digits as in '3.8'.

    Walked by hand instead of by a regular expression: a run of digits and dots
    that only has to *end* at a 'b' is a polynomial match for a backtracking
    engine, and one forward scan is both linear and clearer about the rule it
    implements (``(?<![\d.])(\d[\d.]*)\s*b\b``) — py/polynomial-redos.
    """
    text = (model or "").lower()
    digits = "0123456789"
    cursor = 0
    while True:
        pos = text.find("b", cursor)
        if pos < 0:
            return None
        cursor = pos + 1
        # \b after the 'b': the letter has to end a token, not sit inside a word.
        if pos + 1 < len(text) and (text[pos + 1].isalnum() or text[pos + 1] == "_"):
            continue
        head = pos
        while head > 0 and text[head - 1].isspace():
            head -= 1
        start = head
        while start > 0 and (text[start - 1] in digits or text[start - 1] == "."):
            start -= 1
        number = text[start:head]
        if not number or number[0] not in digits:
            continue
        # The lookbehind: no digit and no dot directly before the number.
        if start > 0 and (text[start - 1] in digits or text[start - 1] == "."):
            continue
        try:
            return float(number)
        except ValueError:
            return None


def _tool_detection_timeout(model: str) -> float:
    # Large reasoning models (≥14B) need a large budget:
    # a long reasoning phase + long system prompts → 120s instead of 25s.
    param_b = _model_param_billions(model)
    if param_b is not None and param_b >= 14:
        return TOOL_DETECT_TIMEOUT_LARGE_REASONING
    normalized = (model or "").lower()
    if normalized.startswith("qwen3:"):
        return TOOL_DETECT_TIMEOUT_SMALL_MODEL
    return TOOL_DETECT_TIMEOUT_DEFAULT


def _assemble_system_prompt_into(
    messages: list,
    model: str,
    extra_system_prompt: str | None,
    allowed_tool_names: list[str] | None,
    *,
    session_id: str = "",
    turn_id: str = "",
) -> None:
    """R28: identity → persona → dynamic tools → skill → extra directive →
    constant protocol → workspace → profile → corrections → feedback → memory
    → current date. Stable blocks first, volatile last (W3-38). Mutates
    ``messages`` in-place (system prompt at index 0, then capped against the
    active window).

    G7: the memory injection carries a query and a result set that name their
    source. When ``session_id`` names a live turn, the facts the block was built
    from are recorded on that run (``core.trajectory.record_memories``) so a
    reader can open the turn later and see — and correct — what the agent knew.
    """
    incoming_system: str | None = None
    if messages and messages[0].get("role") == "system":
        incoming_system = str(messages.pop(0).get("content", ""))

    try:
        profile_ctx: str | None = load_profile().to_context_string()
    except Exception:
        profile_ctx = None

    try:
        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break
        # RAM: build the store only when data actually exists (idle fix)
        memory_ctx: str | None = None
        if user_query and Memory.has_persisted_memory():
            injection = Memory().get_injection(user_query)
            memory_ctx = injection.block or None
            # G7: the run keeps the facts its prompt was built from. Same query,
            # same rows — so /api/trajectory can show a past turn's facts and the
            # reader can correct the entry that shaped it. Best effort: a caller
            # without a session records nothing rather than inventing an owner,
            # and a recording failure must never cost the turn its context.
            if injection.entries and session_id:
                try:
                    from core import trajectory

                    trajectory.record_memories(session_id, injection.entries)
                except Exception:
                    pass
    except Exception:
        memory_ctx = None

    try:
        corrections_ctx: str | None = CorrectionJournal().to_context_string()
    except Exception:
        corrections_ctx = None

    try:
        feedback_ctx: str | None = FeedbackStore().to_few_shot_string()
    except Exception:
        feedback_ctx = None

    try:
        # R29: operative project rules from the workspace's own instruction
        # file (provenance-marked, capped) — never crashes a turn.
        from core.workspace_rules import load_workspace_rules

        workspace_rules_ctx: str | None = load_workspace_rules()
    except Exception:
        workspace_rules_ctx = None

    workspace_ctx = _workspace_anchor()

    full_system_prompt = assemble_system_prompt(
        model=model,
        incoming_system=incoming_system,
        extra_system_prompt=extra_system_prompt,
        custom_instructions_ctx=custom_instructions_block(),
        workspace_rules_ctx=workspace_rules_ctx,
        workspace_ctx=workspace_ctx,
        profile_ctx=profile_ctx,
        memory_ctx=memory_ctx,
        corrections_ctx=corrections_ctx,
        feedback_ctx=feedback_ctx,
        allowed_tool_names=allowed_tool_names,
    )
    messages.insert(0, {"role": "system", "content": full_system_prompt})
    # P0-2: cap the assembled length against the active window (precedence:
    # EPHE_CONTEXT_WINDOW > engine probe > tier table > legacy 8192).
    _fit_messages_to_window(messages, _active_context_window(model))


_OPEN_PLAN_NUDGE = (
    "Continue the announced steps directly: call the still-outstanding "
    "tools (write_file/delete_file) now, until the end state is reached. "
    "No interim-status explanation, no table up front."
)


def _continue_attempts() -> int:
    """I6-3: how often an aborted plan is nudged on — control
    `chat.continue_attempts` in the register. 0 = never: the run ends with the
    declaring answer, the user sees the abort instead of a second
    model round."""
    from core.settings_schema import deep_number

    return int(deep_number("chat.continue_attempts"))


def _looks_like_open_plan(text: str) -> bool:
    """True when the answer is a plan broken off mid-way: a step
    is declared, but the FINAL close is missing. Heuristic for the nudge."""
    if not text:
        return False
    stripped = text.strip()
    if "FINAL" in stripped:
        return False
    if "Schritt" not in stripped and "Step" not in stripped:
        return False
    return stripped.endswith((".", ":", "`"))
