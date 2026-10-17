"""Ephe – auto_memory: durable facts after every turn (R19).

Behind the settings toggle (memory_enabled → EPHE_MEMORY_ENABLED) the Q/A pairs
are stored in the local store — as the TUI always did, now for the PWA as well.
Dedupe asks the store: an auto-memory that is already there is merged into its own
row instead of arriving twice. Artifact answers (FILE
markers) and micro answers are deliberately NOT stored — the library (R17) is
the place for artifacts.

One turn has two writers: this capture and the model's own `memory` tool
(`source: "agent"`). The tool stores the fact it read out of the message while
the turn runs, the capture stores the pair after it — the same fact twice. The
capture therefore looks for its twin before it writes (walkthrough 2026-10-12,
finding: "one chat turn stores the same fact twice").
"""
from __future__ import annotations

import os
import re


# DI hook for tests: None → Memory() (singleton, env-driven); tests set a
# factory with its own tmp persist_dir, because the process singleton pins the
# FIRST instance (later env changes then do not take effect).
_memory_factory = None
_MIN_QUESTION_CHARS = 8
# The threshold is the register field `memory.dedupe_score_threshold`. Its default
# was calibrated for the retired store, whose HNSW returned ~0.89 for IDENTICAL
# text; the store that replaced it ranks rather than measures, so an identical row
# scores ~0.77 there and this comparison cannot decide on its own. The verdict that
# carries is the one at the write (`mem.count()` unchanged afterwards).
# Dedupe applies across auto_memory + compaction (R25): repeated
# compactions of the same history must not register duplicates, and the model's
# own tool write (agent) is a writer of the same fact, not an outsider.
_DEDUPE_SOURCES = frozenset({"auto_memory", "compaction", "agent"})

#: The model's own write path (core/tools/state_tools.py) labels its entries
#: with this source. A row with this origin was written *during the same turn*
#: the capture below is about to store.
_AGENT_SOURCES = frozenset({"agent"})

#: How many hits the duplicate check reads. The twin is written during the turn
#: out of the same user message, so it leads the hits for that message even when
#: its wording differs from the stored Q/A pair.
_TWIN_TOPK = 8

#: A stored fact counts as this turn's twin when its words come from the same
#: message. 5 characters is the length at which a word still means something;
#: 60 % of the fact's words standing in the question is the bar.
_TWIN_TOKEN_CHARS = 5
_TWIN_TOKEN_FLOOR = 0.6

#: Explicit instructions to keep a fact. The answer floor exists to keep micro
#: acknowledgements out of the store — but "Remember this fact: X" answered with
#: a one-word confirmation is an *instruction*, and dropping it let the
#: assistant confirm a save that never happened (walkthrough 2026-10-12,
#: finding: "the capture gate is invisible and rejects short answers").
_REMEMBER_MARKERS = (
    "remember this", "remember that", "remember it", "remember my",
    "remember for later", "please remember", "memorise this", "memorize this",
    "keep this", "keep it in mind", "keep in mind", "don't forget",
    "dont forget", "note that", "make a note", "save this", "store this",
    "add this to memory", "add to memory",
)

#: Every entry the store holds carries an origin, and every origin has a label a
#: surface can print. The memory page's own label map knew only `auto_memory`
#: and `compaction`, so the tool-written rows rendered with no origin at all
#: (walkthrough 2026-10-12: 32 rows, 29 chips). The vocabulary lives here, next
#: to the writers, and travels to the surface through `GET /api/memory/stats`.
SOURCE_LABELS = {
    "auto_memory": "From chat",
    "compaction": "Compacted",
    "agent": "Agent tool",
    "user": "Added by hand",
}
#: An entry whose write path forgot the key is stored under this one instead of
#: under none: `source_of` is the single rule every write path normalises
#: through, so no stored entry can be unlabelled.
DEFAULT_SOURCE = "user"

# R33 (stress triage P1-2): importance gate + ceiling
# The 1000-message campaign stored ~956 entries (~0.9/turn, unbounded).
# Low-signal turns (greeting/emoji-only questions, refusal answers) must never
# enter long-term memory, and the auto_learned namespace gets a hard ceiling
# with oldest-lowest-priority eviction. Entries preserved by the compactor
# (source="compaction") are knowledge backups and are NEVER evicted here.
_MIN_ALNUM_RATIO = 0.65
_REFUSAL_PREFIXES = (
    "i cannot", "i can not", "i am unable", "i'm unable", "not able to",
    "i'm sorry, but", "ich kann nicht", "ich bin nicht in der lage",
    "error:", "failed:", "fehler:",
)
_DEFAULT_MAX_ENTRIES = 1000
_EVICTABLE_SOURCE = "auto_memory"
_PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}


# I6-7: the thresholds are controls
#
# They used to stand here as constants while the entries page of Settings showed
# a text field with no control behind it. The same bar as in the rest of the
# register: a field only when this file (or core/memory.py) reads the value
# through the accessor line under its full key.


def capture_enabled() -> bool:
    """Auto-memory on or off — `memory.capture_enabled`.

    The environment variable wins when it says no: `EPHE_MEMORY_ENABLED=0` is the
    kill switch that startup scripts and tests set, and a file in the device
    folder may not override it. Only the chat path stops: retrieval and
    injection keep running, the `memory` tool keeps writing."""
    if (os.environ.get("EPHE_MEMORY_ENABLED") or "").strip() == "0":
        return False
    from core.settings_schema import deep_bool

    return deep_bool("memory.capture_enabled")


def min_answer_chars() -> int:
    """From how many characters an answer counts as worth knowing."""
    from core.settings_schema import deep_number

    return int(deep_number("memory.capture_min_answer_chars"))


def dup_score_threshold() -> float:
    """From which similarity value a hit counts as a duplicate."""
    from core.settings_schema import deep_number

    return float(deep_number("memory.dedupe_score_threshold"))


def _count_or_none(mem) -> int | None:
    """The store's entry count, or None when it cannot answer.

    None is the honest third answer: `test_the_ceiling_step_is_best_effort` pins that
    a count failure must not turn a fact that landed into an error verdict, and a
    stand-in store without the method must not be read as "nothing changed".
    """
    try:
        return int(mem.count())
    except Exception:
        return None


def _signal_score(question: str) -> float:
    """Share of alphanumeric characters among the non-space question chars.

    Emoji, punctuation and whitespace push the ratio down — greetings and
    sticker replies land far below the floor, real questions near 1.0.
    """
    chars = [c for c in question if not c.isspace()]
    if not chars:
        return 0.0
    good = sum(1 for c in chars if c.isalnum())
    return good / len(chars)


def source_of(metadata: dict | None) -> str:
    """The origin every stored entry carries — the one rule all write paths use.

    The store must never hold an entry without one: a row without a source
    renders with no origin at all in the memory page (walkthrough 2026-10-12:
    the tool-written twin showed no label). A missing, blank or non-string value
    therefore becomes the explicit default instead of an empty field.
    """
    raw = (metadata or {}).get("source")
    return (raw.strip() if isinstance(raw, str) else "") or DEFAULT_SOURCE


def source_labels() -> dict[str, str]:
    """The origin vocabulary of the store: every source value a write path can
    leave behind, with the label a surface prints for it."""
    return dict(SOURCE_LABELS)


def _significant_tokens(text) -> set[str]:
    """The words of `text` that still carry meaning (from 5 characters on).

    Non-strings are read as empty: a corrupt row in a search result may cost one
    duplicate check, never the fact (same rule as the guards below).
    """
    if not isinstance(text, str):
        return set()
    return {
        token
        for token in re.findall(r"[^\W_]+", text.casefold())
        if len(token) >= _TWIN_TOKEN_CHARS
    }


def _fact_comes_from(text, question: str) -> bool:
    """True when the words of `text` mostly stand in `question`.

    Both writers of a turn draw on the same user message: the `memory` tool
    stores the fact it read out of it, this capture stores the pair. A stored
    fact whose vocabulary is the question's vocabulary is that twin.
    """
    fact = _significant_tokens(text)
    if not fact:
        return False
    shared = fact & _significant_tokens(question)
    if len(fact) == 1:
        # A lone word is evidence only when the word is a fact in itself (a
        # marker, an id); one shared common word is none.
        only = next(iter(fact))
        return only in shared and len(only) >= 10
    return len(shared) / len(fact) >= _TWIN_TOKEN_FLOOR


def _asks_to_keep(question: str) -> bool:
    """True when the user's own message asks for the fact to be kept."""
    text = " ".join((question or "").casefold().split())
    return any(marker in text for marker in _REMEMBER_MARKERS)


def _is_low_value(question: str, answer: str) -> bool:
    """Deterministic importance gate (no model call): rejects symbol-salad
    questions and pure refusal/error answers before they pollute retrieval."""
    if _signal_score(question) < _MIN_ALNUM_RATIO:
        return True
    head = answer.strip()[:40].casefold()
    return any(head.startswith(prefix) for prefix in _REFUSAL_PREFIXES)


def _max_entries() -> int:
    """Ceiling: settings control > env > default. I3-8 — before, only the env was read.

    The memory_max_entries control lived in engine.json but was never read: the
    card showed a value that the entry count ignored.
    """
    from core.engine_config import read_generation_explicit

    explicit = read_generation_explicit().get("memory_max_entries")
    if explicit is not None and int(explicit) > 0:
        return int(explicit)
    raw = os.environ.get("EPHE_MEMORY_MAX_ENTRIES", "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_MAX_ENTRIES
    except ValueError:
        value = _DEFAULT_MAX_ENTRIES
    return value if value > 0 else _DEFAULT_MAX_ENTRIES


def _enforce_ceiling(mem) -> int:
    """Trim the store back to the ceiling by evicting the least valuable
    auto_learned entries first (low priority, then oldest). Best effort."""
    try:
        total = mem.count()
        cap = _max_entries()
        if total <= cap:
            return 0
        entries = mem.list_all(limit=max(total, 50))
        victims = [
            e for e in entries
            if (e.get("metadata") or {}).get("source") == _EVICTABLE_SOURCE
        ]
        victims.sort(key=lambda e: (
            _PRIORITY_RANK.get((e.get("metadata") or {}).get("priority") or "medium", 1),
            (e.get("metadata") or {}).get("timestamp", 0),
        ))
        removed = 0
        for entry in victims[: min(total - cap, 50)]:
            try:
                mem.delete(entry["id"])
                removed += 1
            except Exception:
                pass
        return removed
    except Exception:
        return 0


def maybe_store_turn(user_message: str, answer: str, source: str = "auto_memory") -> dict:
    """Stores Q/A durably — or explains honestly why it did not.

    ``source``: ``"auto_memory"`` (chat turns) or ``"compaction"`` (R25: old
    turns secured before they are discarded). Never raises: the chat stream must
    not die on auto-memory.

    Two writers meet on one turn: the model's own `memory` tool stores the fact
    it read out of the message while the turn runs (source ``"agent"``), and
    this capture stores the pair afterwards. Storing both puts one fact in the
    store twice, so the capture refuses when the twin is already there.

    The answer floor keeps micro acknowledgements out of the store, with one
    exception: when the user's message itself asks for the fact to be kept, the
    one-word answer acknowledges the instruction it fulfils and is kept.
    Dropping it would let the assistant confirm a save that never happened.
    """
    try:
        if not capture_enabled():
            return {"stored": False, "reason": "disabled"}
        user_message = (user_message or "").strip()
        answer = (answer or "").strip()
        requested = _asks_to_keep(user_message)
        if len(user_message) < _MIN_QUESTION_CHARS:
            return {"stored": False, "reason": "too-short"}
        if len(answer) < min_answer_chars() and not requested:
            return {"stored": False, "reason": "too-short"}
        if "_FILE:" in answer:
            return {"stored": False, "reason": "artifact"}
        if _is_low_value(user_message, answer):
            return {"stored": False, "reason": "low-value"}

        from core.memory import Memory

        mem = _memory_factory() if _memory_factory else Memory()
        try:
            hits = mem.search(user_message[:200], top_k=_TWIN_TOPK)
        except Exception:
            hits = []
        for hit in hits or []:
            # A corrupt row (not a dict, null/non-numeric score, non-dict
            # metadata) must not decide the verdict: before, one such row made
            # every later store answer `error:` and the fact was dropped.
            if not isinstance(hit, dict):
                continue
            metadata = hit.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            try:
                score = float(hit.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0  # an unreadable similarity cannot claim "duplicate"
            origin = str(metadata.get("source") or "")
            # The second writer of this turn has already stored this fact.
            # Its similarity to the Q/A pair can sit below the dedupe threshold
            # (the wording differs), so the words the fact came from decide.
            if origin in _AGENT_SOURCES and _fact_comes_from(hit.get("text"), user_message):
                return {"stored": False, "reason": "duplicate"}
            if score >= dup_score_threshold() and origin in _DEDUPE_SOURCES:
                return {"stored": False, "reason": "duplicate"}

        before = _count_or_none(mem)
        mem.store(
            f"Q: {user_message[:500]}\nA: {answer[:600]}",
            metadata={"source": source if source in ("auto_memory", "compaction") else "auto_memory"},
        )
        after = _count_or_none(mem)
        if before is not None and after is not None and after == before:
            # The store merged this into the row that was already there, so the same
            # fact did not arrive twice. This is the provider-independent form of the
            # score test further up: a rank score carries no similarity of its own —
            # one row in the store is rank 1 for every query — so what decides is the
            # store's own verdict on the write it was just handed. A store that
            # cannot count answers nothing, and the fact is stored: the ceiling step
            # must never un-store a fact that landed.
            return {"stored": False, "reason": "duplicate"}
        evicted = _enforce_ceiling(mem)
        return {"stored": True, "evicted": evicted}
    except Exception as exc:  # absolute fire protection
        return {"stored": False, "reason": f"error: {exc}"}
