"""What this server process knows about a model's tool support.

Two facts, one register. An endpoint may state ``supported_parameters`` without
``tools`` — the probe reads it into ``supports_tools: false`` — and an engine may
refuse a turn that carries a tool array, which is only seen when a real request
hits it. Both mean the same thing for the next turn: this ``(endpoint, model)``
answers, and it does not take tools.

Process-lifetime only, never persisted. A restart loses the memory and the next
turn discovers the fact again — the alternative is a stale "no" that outlives an
engine update, and a wrong "no" costs the agent its tools.

Unknown is not false: a model nobody has refused keeps exactly today's behaviour,
with the full array. Nothing here infers a capability from a name.
"""
from __future__ import annotations

# Scrubbed of credentials and of a trailing slash: the same engine asked at
# `http://h:8000/v1/` and `http://h:8000/v1` is one entry.
_answer_only: set[tuple[str, str]] = set()

# What the engine families say when a request carries `tools` and the model cannot
# take them. Matched lower-case on the refusal body the provider raises with
# (`core/model_provider.py::_status_error` keeps the first 500 characters).
_TOOL_WORDS = ("tool", "function_call", "function call", "tool_choice")
_REFUSAL_WORDS = (
    "does not support",
    "do not support",
    "not supported",
    "not support",
    "unsupported",
    "not permitted",
    "additional properties",
    # OpenRouter refuses with "No endpoints found that support tool use" and a 404 —
    # found live on 2026-10-19 against a free model; the body names no unsupported
    # parameter, so without this token the turn died on a 500 instead of answering.
    "no endpoints",
)


#: The line a surface gets when the turn was rebuilt without its array. Machine-facing
#: prose; the user's own words are the locale entry the model row shows.
ANSWER_ONLY_PHASE = "Engine refused the tool array; this turn answers without tools"


def _key(endpoint: str | None, model: str | None) -> tuple[str, str]:
    return ((endpoint or "").strip().rstrip("/"), (model or "").strip())


def note_rejection(endpoint: str | None, model: str | None) -> None:
    """Remember the first refusal of this (endpoint, model) for this process."""
    key = _key(endpoint, model)
    if key[1]:
        _answer_only.add(key)


def is_answer_only(endpoint: str | None, model: str | None) -> bool:
    return _key(endpoint, model) in _answer_only


def looks_like_tool_rejection(text: str | None) -> bool:
    """True when a refusal body says the tool array, not the request, was the problem.

    Deliberately narrow: a body that only says "bad request" is not a capability
    statement, and remembering that would take a working engine's tools away. Both
    halves have to speak — the object of the refusal and the refusal itself.
    """
    low = (text or "").lower()
    if not low:
        return False
    return any(word in low for word in _TOOL_WORDS) and any(
        word in low for word in _REFUSAL_WORDS
    )


def note_metadata(endpoint: str | None, entries: list[dict] | None) -> None:
    """Record what an endpoint said about its own models.

    Called from the probe, so a stated ``supports_tools: false`` reaches the same
    register as a refused turn — the two are one fact seen at two moments. A null
    is not a no: nothing is recorded for a model the endpoint did not describe.
    """
    for item in entries or []:
        if isinstance(item, dict) and item.get("supports_tools") is False:
            note_rejection(endpoint, str(item.get("id") or ""))


def reset() -> None:
    """Test seam only — production never clears the register mid-process."""
    _answer_only.clear()


def entries() -> tuple[tuple[str, str], ...]:
    """What is remembered, for a surface that has to say it (sorted for tests)."""
    return tuple(sorted(_answer_only))
