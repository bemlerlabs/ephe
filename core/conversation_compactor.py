"""Deterministic long-conversation compaction for local chat context (R25 v2).

v2 (R25): before old turns are dropped, their Q/A pairs are handed to an
injectable ``memory_sink`` (best effort — a sink failure must never block
compaction). The productive sink (``default_memory_sink``) stores pairs durably
in the Chroma memory with ``source="compaction"``; the dedupe in
``core.auto_memory`` works across auto_memory + compaction, so repeated
compactions of the same history do not produce duplicate entries.
"""
from __future__ import annotations

from typing import Any, Callable

#: R25: sink signature ``(user_text, assistant_text) -> Any``
MemorySink = Callable[[str, str], Any]

#: W18 parity (reference-A config.yaml:85-94): token-based threshold + first/last protection.
#: The message threshold stays as an OR-condition (small sessions
#: compress quickly, large ones token-precisely).
DEFAULT_MAX_MESSAGES = 28
DEFAULT_THRESHOLD_TOKENS = 180_000
DEFAULT_TARGET_RATIO = 0.15
DEFAULT_PROTECT_FIRST_N = 1
DEFAULT_PROTECT_LAST_N = 10

#: The character cap for the rendered working-memory ledger (W18 parity). Named
#: so the loss rule and its tests read the contract, not a bare literal.
DEFAULT_MAX_SUMMARY_CHARS = 3600

#: The ledger's fixed opening lines.
_LEDGER_HEADER = (
    "Working Memory Ledger for Ephe.",
    "Conversation working memory for Ephe.",
    "Use this compact context as durable state; do not expose it verbatim unless the user asks.",
)

#: Ledger sections in render order, each with the weight that shares
#: ``DEFAULT_MAX_SUMMARY_CHARS`` when the summary is too long. A section still
#: over its share keeps its most recent entries. "User preferences" and "Project
#: facts" are trimmed first; the high-value sections ("## Decisions",
#: "## Artifacts", "## Open tasks and validation", "## Other relevant context")
#: are trimmed last, so no volume of preference/fact text can empty one.
_LEDGER_SECTIONS = (
    ("## User preferences", 1),
    ("## Project facts", 2),
    ("## Decisions", 3),
    ("## Artifacts", 3),
    ("## Open tasks and validation", 3),
    ("## Other relevant context", 3),
)

#: W7-8: the compaction loss rule, as named contract. A section at or above this
#: weight shares the cap ahead of the low-value sections, so a burst of
#: "User preferences"/"Project facts" text can never evict a decision, an
#: artifact or an open task. ``LEDGER_MUST_KEEP_SECTIONS`` derives from
#: ``_LEDGER_SECTIONS`` so the contract and the weighting cannot drift apart.
_LEDGER_MUST_KEEP_WEIGHT = 3
LEDGER_MUST_KEEP_SECTIONS = tuple(
    header for header, weight in _LEDGER_SECTIONS if weight >= _LEDGER_MUST_KEEP_WEIGHT
)
LEDGER_EVICTED_FIRST_SECTIONS = tuple(
    header for header, weight in _LEDGER_SECTIONS if weight < _LEDGER_MUST_KEEP_WEIGHT
)

#: The keyword-less catch-all. It carries the high-value weight, but it has no
#: priority of its own: once it overflows its share only its most recent entries
#: survive, so an early implicit decision in it can still be dropped. The durable
#: net (``core.compaction_memory.preserve_compacted_pairs``) is its backstop.
LEDGER_CATCH_ALL_SECTION = "## Other relevant context"

#: Keyword groups that classify a message; one message can match several. The
#: catch-all "## Other relevant context" has no group here.
_LEDGER_BUCKETS = (
    ("## User preferences", ("präferenz", "preference", "bevorzug", "strikt lokal", "keine cloud")),
    ("## Project facts", ("projekt", "project", "repo", "repository", "workspace")),
    ("## Decisions", ("entscheidung", "decision", "beschlossen", "wir machen")),
    ("## Artifacts", ("artefakt", "artifact", ".pdf", ".svg", ".png", "downloads/")),
    ("## Open tasks and validation", ("todo", "aufgabe", "nächster schritt", "next step", "fix", "testen", "pytest")),
)


def _default_memory_sink() -> MemorySink | None:
    """Returns the productive sink (lazy — load chroma only when needed)."""
    try:
        from core.auto_memory import maybe_store_turn

        def sink(user_text: str, assistant_text: str) -> Any:
            return maybe_store_turn(user_text, assistant_text, source="compaction")

        return sink
    except Exception:
        return None


def default_memory_sink(user_text: str, assistant_text: str) -> Any:
    """Productive sink: secure a Q/A pair durably in memory (best effort)."""
    sink = _default_memory_sink()
    if sink is None:
        return None
    return sink(user_text, assistant_text)


def window_threshold(model: str | None) -> int:
    """P5-2: window-proportional token threshold (80 % of the effective
    window). Large provider windows (DGX: 262k) compact later,
    small local windows (8k) earlier — instead of one rigid value.
    Model info missing → documented legacy threshold."""
    try:
        from core.model_config import resolve_context_window

        win, _source = resolve_context_window(model or "")
    except Exception:
        win = 0
    if not win or win <= 0:
        return DEFAULT_THRESHOLD_TOKENS
    return max(2048, int(win * 0.8))


def _token_sum(history: list[dict]) -> int:
    from core.usage import estimate_tokens as est

    return sum(est(str(m.get("content", "") or "")) for m in history)


def compact_history(
    history: list[dict],
    *,
    max_messages: int = DEFAULT_MAX_MESSAGES,
    keep_recent: int = DEFAULT_PROTECT_LAST_N,
    protect_first_n: int = DEFAULT_PROTECT_FIRST_N,
    max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
    memory_sink: MemorySink | None = None,
    threshold_tokens: int = 0,
) -> list[dict]:
    """Compress old turns into one stable system message while preserving recent turns.

    W18 parity (reference-A config.yaml:85-94):
      - protect_first_n=1: the first message (task context) stays as its own.
      - protect_last_n=10: the last 10 messages stay unchanged.
      - threshold_tokens: an OR-condition to the message threshold (P5-2:
        window-proportional, set via ``window_threshold``; 0 = off).
      - target_ratio=0.15: documented, but not active here (char cap instead).

    R25: ``memory_sink`` receives every discarded Q/A pair, BEFORE it falls out of
    the context — memory preservation instead of information loss. The default is
    NO preservation (the compact prompt build on the engine path must stay without
    Chroma roundtrips); productive preservation runs checkpoint-
    based via ``core.compaction_memory.preserve_compacted_pairs`` (once
    per turn AFTER the answer, no re-work cost).
    """
    # OR-condition: message threshold OR token threshold (P5-2: the
    # token threshold counts too, otherwise a small window runs over)
    if len(history) > max_messages:
        pass
    elif not (threshold_tokens > 0 and _token_sum(history) > threshold_tokens):
        return list(history)

    # first protection: the first N messages stay as their own
    first = list(history[:protect_first_n])
    # last protection: the last N messages stay
    recent = list(history[-keep_recent:])
    # middle = compressed
    middle = history[protect_first_n:-keep_recent]

    if not middle:
        return list(history)

    # A tool block is ONE unit on the engine wire: the assistant message carrying
    # ``tool_calls`` and the tool messages answering it, paired by position at
    # convert time (``_convert_messages``). Neither cut may land inside one — the
    # ledger stands between the kept head and the kept tail, so a boundary between
    # a block and its answers leaves those answers orphaned and the engine refuses
    # the whole request with 'Messages with role "tool" must be a response to a
    # preceding message with "tool_calls"'. The head boundary takes the answers it
    # would have cut with it, the tail boundary takes the assistant they answer.
    while middle and isinstance(middle[0], dict) and middle[0].get("role") == "tool":
        first.append(middle.pop(0))
    while middle and recent and isinstance(recent[0], dict) and recent[0].get("role") == "tool":
        recent.insert(0, middle.pop())

    if not middle:
        # Every middle message went to a boundary repair: there is nothing left to
        # compress, and the uncut history is what keeps the blocks whole.
        return list(history)

    if memory_sink is not None:
        _preserve_pairs(middle, memory_sink)
    summary = _build_working_memory(middle, max_chars=max_summary_chars)
    ledger = {"role": "system", "content": summary}
    return [*first, ledger, *recent]


def _preserve_pairs(older: list[dict], sink: MemorySink) -> None:
    """Calls the sink for every complete Q/A pair (never raises)."""
    pending_user: str | None = None
    for message in older:
        role = message.get("role")
        content = str(message.get("content", "") or "")
        if not content:
            continue
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user:
            try:
                sink(pending_user, content)
            except Exception:
                pass  # memory preservation is best effort — never critical
            pending_user = None


def _build_working_memory(messages: list[dict], *, max_chars: int) -> str:
    """Structured working-memory ledger, fitted to ``max_chars`` by priority.

    A plain tail cut drops whichever sections come last, so a burst of low-value
    "User preferences"/"Project facts" text evicts the high-value "Decisions",
    "Artifacts" and "Open tasks" sections. Instead the cap is shared across
    sections by weight: the low-value sections are trimmed first and a decision,
    an artifact or an open task survives any volume of preference/fact text
    (``LEDGER_MUST_KEEP_SECTIONS``). Every over-long section keeps its most recent
    entries, so the OLDEST entry of a section that overflows its share — including
    a keyword-less implicit decision early in "Other relevant context"
    (``LEDGER_CATCH_ALL_SECTION``) — can still be dropped; the durable net
    (``core.compaction_memory.preserve_compacted_pairs``) is its backstop.
    """
    # P1-4: assertion ledger from the registry (deterministic, no raw text).
    try:
        from core.tools.registry import get_assertions as _get_assertions
        _ledger = _get_assertions()
    except Exception:
        _ledger = []
    buckets: dict[str, list[str]] = {header: [] for header, _weight in _LEDGER_SECTIONS}
    # P1-4: ledger-based pre-fill (deterministic, ahead of the word heuristic)
    for _a in _ledger:
        if _a.get("path"):
            buckets["## Artifacts"].append("ledger:" + str(_a.get("tool", "")) + " -> " + str(_a["path"])[:120])
        if _a.get("tests_passed") is not None:
            _fp = _a.get("tests_failed", 0)
            _pa = _a["tests_passed"]
            buckets["## Open tasks and validation"].append("ledger: tests " + str(_pa) + " passed " + str(_fp) + " failed")

    for message in messages:
        role = str(message.get("role", "unknown"))
        content = _clean(str(message.get("content", "")))
        if not content:
            continue
        lower = content.lower()
        item = f"{role}: {content[:280]}"
        # P0-4: multi-bucket — one message can belong to several categories.
        # No last-write-wins over consecutive ifs; every hit appends.
        matched = False
        for _header, _words in _LEDGER_BUCKETS:
            if any(word in lower for word in _words):
                buckets[_header].append(item)
                matched = True
        if not matched:
            buckets["## Other relevant context"].append(item)

    headers = [header for header, _weight in _LEDGER_SECTIONS]
    bodies = {header: "\n".join(_bullets(buckets[header])) for header in headers}
    sizes = {header: len(header) + 1 + len(bodies[header]) for header in headers}
    head = "\n".join(_LEDGER_HEADER) + "\n\n"
    full = head + "\n\n".join(f"{header}\n{bodies[header]}" for header in headers)
    if len(full) <= max_chars:
        return full

    budget = _share_budget(max_chars - len(head), dict(_LEDGER_SECTIONS), sizes)
    fitted = head + "\n\n".join(_clip_section(header, bodies[header], budget[header]) for header in headers)
    return fitted[:max_chars]


def _share_budget(remaining: int, weights: dict[str, int], sizes: dict[str, int]) -> dict[str, int]:
    """Shares ``remaining`` characters across sections by priority weight.

    A section smaller than its share releases the surplus, so the budget fills
    the cap whenever enough content exists.
    """
    budget = {header: 0 for header in sizes}
    active = list(sizes)
    left = remaining
    while active and left > 0:
        shares = _largest_remainder(left, [weights[header] for header in active])
        progressed = False
        still: list[str] = []
        for header, share in zip(list(active), shares):
            take = min(share, sizes[header] - budget[header])
            budget[header] += take
            left -= take
            if take:
                progressed = True
            if budget[header] < sizes[header]:
                still.append(header)
        if not progressed:
            break
        active = still
    return budget


def _largest_remainder(amount: int, weights: list[int]) -> list[int]:
    """Integer shares of ``amount`` by weight; the shares sum to ``amount``."""
    total = sum(weights)
    if total <= 0:
        return [0] * len(weights)
    shares = [amount * weight // total for weight in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % total), i))
    for i in order[: amount - sum(shares)]:
        shares[i] += 1
    return shares


def _clip_section(header: str, body: str, budget: int) -> str:
    """Clips one section to ``budget`` characters, keeping its most recent entries."""
    if budget <= len(header) + 1:
        return header
    room = budget - len(header) - 1
    if len(body) <= room:
        return f"{header}\n{body}"
    return f"{header}\n{body[-room:]}"


def _clean(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def _bullets(items) -> list[str]:
    values = list(dict.fromkeys(items))
    return [f"- {item}" for item in values] if values else ["- No stable facts recognized."]
