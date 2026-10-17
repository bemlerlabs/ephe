"""Context window, result capping and tool-schema plumbing for the chat path.

Split out of core/chat.py (2026-10-11): window fitting, per-tool result caps,
tool-schema caching and the budget helpers the tool loop reads. core/chat.py
re-exports every name here.
"""

from __future__ import annotations

import json
import time
from contextvars import ContextVar

from core.model_config import resolve_context_window
from core.tools import get_tool_schemas
from core.usage import estimate_tokens, serialize_prompt

TOOL_SCHEMA_CACHE_TTL_SECONDS = 60.0


_TOOL_SCHEMA_CACHE: tuple[float, list[dict]] | None = None


#: Estimated tokens of the visible tool array of the current context. The provider
#: window is shared by messages and tools, so the fit must not spend the array's
#: share on history. Recorded by _tools_for_messages (ContextVar: several sessions
#: interleave in one process, same reason the session array is carried this way).
#: None = no array was built here, read as "nothing to reserve".
_TOOL_SCHEMA_TOKENS: ContextVar[int | None] = ContextVar("ephe_tool_schema_tokens", default=None)


def _tool_schema_tokens(tools: list[dict]) -> int:
    """Token estimate of a tool array as the provider receives it (its JSON form)."""
    if not tools:
        return 0
    try:
        payload = json.dumps(tools, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        payload = str(tools)
    return estimate_tokens(payload)


def _fit_text(messages: list) -> str:
    """Prompt text for the window estimate, counting provider message objects too.

    History holds dicts, but the tool loop appends ``response.message`` (assistant
    content plus tool_call arguments) as an object. serialize_prompt skips non-dicts,
    so those turns priced at 0 tokens and the cap leaked. Normalizing objects to the
    dict shape keeps serialize_prompt the single text format.
    """
    normalized: list[dict] = []
    for msg in messages:
        if isinstance(msg, dict):
            normalized.append(msg)
            continue
        content = getattr(msg, "content", None)
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            args = json.dumps(tool_calls, ensure_ascii=False, default=str)
            content = f"{content or ''} {args}".strip()
        normalized.append({"role": getattr(msg, "role", "assistant"), "content": content})
    return serialize_prompt(normalized)


def _active_context_window(model: str) -> int:
    """Context window of this request: a set control first, otherwise the
    resolved model table.

    I3-8: 'not set' is only distinguishable with read_generation_explicit —
    a filled-in register default would be an invented window size that cuts the
    history shorter than the engine can.
    """
    from core.engine_config import read_generation_explicit

    explicit = read_generation_explicit().get("context_window")
    if explicit is not None:
        return int(explicit)
    return resolve_context_window(model)[0]


def _budget_exhausted_note(cap: int) -> str:
    """R37: cap end as an honest status — number + 'unfinished', never pseudo-complete."""
    return (
        f"[Ephe] Tool budget exhausted after {cap} tool rounds — "
        "task unfinished (no final answer). Narrow the task or send the next step to continue."
    )


#: P1-9: cap per tool result before it enters the message array.
#: Prevents the memory explosion of long tool chains (25+ calls) without
#: trimming the relevant heads — the shell caps on its own at 10.000.
#: I6-3: the value is a control (`chat.tool_result_chars` in the register,
#: core/settings_schema.py). The register carries default and bounds; this
#: file holds no second number, because a change to one of the two would
#: otherwise leave a lie behind.
def _tool_result_cap() -> int:
    from core.settings_schema import deep_number

    return int(deep_number("chat.tool_result_chars"))


def _cap_tool_result(result: str) -> str:
    """P1-9: cap the result to `chat.tool_result_chars` (marker appended).

    P2-13 (deep audit 2026-09-13): the ARTIFACT_VERIFIED/FAILED evidence line
    stands at the end of the string and fell victim to the end cap — so exactly
    the verification proof was lost on long results. The evidence is therefore
    extracted before the cap and kept (as a prefix).
    """
    cap = _tool_result_cap()
    if len(result) <= cap:
        return result
    evidence = ""
    for line in result.splitlines():
        if line.startswith("ARTIFACT_VERIFIED") or line.startswith("ARTIFACT_FAILED"):
            evidence = line
            break
    capped = result[:cap] + f" …[truncated at {cap} chars]"
    if evidence:
        return f"{evidence}\n{capped}"
    return capped


def _tool_call_ids(msg: object) -> list[str]:
    """Tool-call ids of an assistant message; [] for every other shape.

    Both shapes reach the assemblers: the tool loop appends ``response.message``
    (a ProviderMessage), while a replayed history (REST caller, /v1 client,
    resumed session) carries the wire shape as a dict.
    """
    calls = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
    ids: list[str] = []
    for call in calls or []:
        if isinstance(call, dict):
            ids.append(str(call.get("id") or ""))
        else:
            ids.append(str(getattr(call, "id", "") or ""))
    return ids


def _front_unit_end(messages: list) -> int:
    """Exclusive end of the smallest run at the front that may leave as one unit.

    The engine pairs a ``role: "tool"`` message with the assistant ``tool_calls``
    block in front of it, and the ids of the tool messages are assigned
    positionally at convert time (``_convert_messages``) — so an assistant block
    and the tool messages answering it are one unit on the wire, never two:

      - cutting the assistant alone leaves an orphan tool message, and the
        engine refuses the whole request with 'Messages with role "tool" must be
        a response to a preceding message with "tool_calls"' (the failure this
        exists for);
      - cutting the answers alone leaves an unanswered block, refused with
        'An assistant message with "tool_calls" must be followed by tool
        messages responding to each "tool_call_id"'.

    So the unit is the assistant plus its N answers (N = the calls it declares),
    evidence messages in between included, ending at the last answer found. A
    block that was never answered — a broken input, the assemblers cannot build
    one — leaves only the assistant, and a tool message with no block in front of
    it is a unit of one: it never had an owner and is unusable either way.
    """
    ids = _tool_call_ids(messages[1])
    if not ids:
        return 2
    remaining = len(ids)
    end = 2
    last_answer = 1
    while end < len(messages) and remaining > 0:
        msg = messages[end]
        if isinstance(msg, dict) and msg.get("role") == "tool":
            remaining -= 1
            last_answer = end
        elif _tool_call_ids(msg):
            break  # a new block starts: this one was never answered
        end += 1
    cut = last_answer + 1 if remaining else end
    # A history that arrives already orphaned (no owner anywhere in front) would
    # hand the orphan straight to the front of the list; it answers nothing, so it
    # leaves with the cut.
    while cut < len(messages) and isinstance(messages[cut], dict) and messages[cut].get("role") == "tool":
        cut += 1
    return cut


def _fit_messages_to_window(messages: list, window: int, *, tools: list[dict] | None = None) -> int:
    """P0-2: hard server-side cap onto the active context window.

    Kept are the system block (index 0) and the most recent messages; trimmed from
    the front (after the system block) until the estimated prompt fits. Provider
    message objects price in like dicts (_fit_text), and the visible tool array,
    which ships with every call, has its estimated cost reserved from the window up
    front — pass ``tools`` to size a specific array, otherwise the array recorded
    for this context holds. The compactor (compact_history) stays the qualitative
    pre-stage — this cap is the hard ceiling. Below three messages there is nothing
    to trim and the floor stands (system block + newest).

    What leaves, leaves as a whole tool block (_front_unit_end): the loop stays
    open for 25+ rounds and this cap runs before every follow-up call, so a cut
    between an assistant ``tool_calls`` message and its results is exactly the
    request the engine 400s on. A unit the floor would not leave standing is not
    cut at all — the block only exists together, so there is nothing left to
    trade and the honest end is to send what fits.
    """
    if window <= 0:
        return 0
    if tools is not None:
        reserve = _tool_schema_tokens(tools)
    else:
        reserve = _TOOL_SCHEMA_TOKENS.get() or 0
    budget = window - reserve
    trimmed = 0
    while estimate_tokens(_fit_text(messages)) > budget and len(messages) > 2:
        end = _front_unit_end(messages)
        if len(messages) - (end - 1) < 2:
            break
        del messages[1:end]
        trimmed += end - 1
    return trimmed


def _has_uploaded_images(messages: list) -> bool:
    return any(bool(getattr(msg, "images", None) or (isinstance(msg, dict) and msg.get("images"))) for msg in messages)


def _tools_for_messages(messages: list, allowed_tool_names: list[str] | None = None) -> list[dict]:
    tools = _cached_tool_schemas()
    if allowed_tool_names is not None:
        # Whitelist path (active skill): the skill declares its tools.
        # P0-1: a NON-empty whitelist additionally gets the three
        # discovery meta tools, so that the model can reach rare artifact
        # generators on demand (progressive disclosure stays in effect).
        # R38 follow-up (owner decision 2026-10-10): it also keeps the file
        # primitives, for the same reason — this list becomes the session's whole
        # array, and a session that cannot read the workspace tells the model its
        # files do not exist. The mutating three join only a whitelist that already
        # declares one of them; the tools were already reachable through tool_call
        # before the union (probe p1 in docs/ENDSTATE_DELTA_2026-10-10.md).
        # An EMPTY whitelist (ask_mode) stays empty — deliberately no tool dialog.
        if allowed_tool_names:
            from core.tools.discovery import META_TOOL_NAMES, file_primitives_for
            allowed = set(allowed_tool_names) | META_TOOL_NAMES | file_primitives_for(allowed_tool_names)
        else:
            allowed = set(allowed_tool_names)
        tools = [
            tool for tool in tools
            if tool.get("function", {}).get("name") in allowed
        ]
    else:
        # Wave 3: progressive tool discovery. Without a skill whitelist the
        # landscape is reduced to the CORE kernel + the discovery meta tools;
        # rare artifact generators are reached on demand via
        # tool_search/tool_describe/tool_call. That halves the base array.
        from core.tools.discovery import CORE_TOOLS

        visible = set(CORE_TOOLS)
        tools = [
            tool for tool in tools
            if tool.get("function", {}).get("name") in visible
        ]
    # Recorded for tool_search: it must not claim that omitted core tools are active.
    # The image filter below stays outside the record on purpose — it removes a tool
    # for one message (a turn without images), while the session keeps its landscape.
    from core.tools.discovery import set_session_tool_array

    set_session_tool_array({tool.get("function", {}).get("name") for tool in tools})
    if not _has_uploaded_images(messages):
        shipped = tools
    else:
        shipped = [
            tool for tool in tools
            if tool.get("function", {}).get("name") != "analyze_image"
        ]
    # The shipped array (after the image filter) reserves its window share here, so
    # the fit prices the request the provider actually receives.
    _TOOL_SCHEMA_TOKENS.set(_tool_schema_tokens(shipped))
    return shipped


def _cached_tool_schemas() -> list[dict]:
    global _TOOL_SCHEMA_CACHE
    now = time.monotonic()
    if _TOOL_SCHEMA_CACHE and now - _TOOL_SCHEMA_CACHE[0] < TOOL_SCHEMA_CACHE_TTL_SECONDS:
        return _TOOL_SCHEMA_CACHE[1]
    schemas = get_tool_schemas()
    _TOOL_SCHEMA_CACHE = (now, schemas)
    return schemas
