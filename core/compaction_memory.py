"""Ephe – compaction_memory: preserving memory before it is discarded (R25 v2).

Why checkpoint-based instead of inside the engine path? ``compact_history`` runs
on every turn with a long history — a Chroma roundtrip per discarded pair would
worsen TTFT there (the R25 latency budgets). This preservation therefore runs
ONCE per turn AFTER the answer (in ``routes/chat.py``, alongside Auto-Memory)
and is **incremental**: one checkpoint per session counts which Q/A pairs are
already stored; nothing stored goes through the embedding dedupe a second
time (0 cost in the normal case).

Determinism: the history only grows (append). The pair index ``i`` in the
session history is thus stable **while that holds**. Edits or deletions of old
messages — or a foreign writer touching the checkpoint file — can shift the
assignment, and a bare count would then skip a pair that was never stored
(a decision, silently lost as "already done"). Every checkpoint therefore
stores a fingerprint over the pairs it counted; the reader trusts the count
only when that fingerprint still matches the current window, otherwise it
re-derives from the store. The content-based Chroma dedupe ("auto_memory" +
"compaction", score ≥ 0.85) absorbs the duplicates that re-derivation produces.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from core.conversation_compactor import DEFAULT_MAX_MESSAGES, MemorySink

CHECKPOINT_FILENAME = "compaction_checkpoints.json"

#: Reserved top-level key holding the per-session content fingerprint. Kept in
#: the same file (one atomic replace) instead of a sidecar so a crash can never
#: leave the counter and its proof out of sync.
_FP_KEY = "__fingerprints__"


def _prefix_fingerprint(pairs: list[tuple[str, str]], count: int) -> str:
    """A stable hash over the first ``count`` Q/A pairs.

    The checkpoint stores a *count* of already-secured pairs. A bare count is
    only trustworthy while the history is append-only: if old messages are
    edited or deleted (or a foreign writer touches the file), the same index can
    point at a different pair and a decision that was never stored would be
    skipped forever ("already done") and silently lost. The fingerprint lets the
    reader prove that indices ``[0, count)`` still describe the pairs that were
    stored; on any mismatch the run re-derives from the store instead of
    trusting the count.
    """
    digest = hashlib.sha256()
    for user_text, assistant_text in pairs[:count]:
        digest.update(user_text.encode("utf-8", "surrogatepass"))
        digest.update(b"\x1e")
        digest.update(assistant_text.encode("utf-8", "surrogatepass"))
        digest.update(b"\x1f")
    return digest.hexdigest()



def _checkpoint_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    ephe_dir = Path(os.environ.get("EPHE_DIR", str(Path.home() / ".ephe")))
    return ephe_dir / CHECKPOINT_FILENAME


def _load_checkpoints(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_checkpoints(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _pairs(messages: list[dict]) -> list[tuple[str, str]]:
    """Q/A pairs in order (a user message without a partner is dropped)."""
    out: list[tuple[str, str]] = []
    pending_user: str | None = None
    for message in messages:
        role = message.get("role")
        content = str(message.get("content", "") or "")
        if not content:
            continue
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            out.append((pending_user, content))
            pending_user = None
    return out


def preserve_compacted_pairs(
    session_id: str,
    *,
    messages: list[dict] | None = None,
    sink: MemorySink | None = None,
    path: Path | None = None,
    max_messages: int = DEFAULT_MAX_MESSAGES,
    keep_recent: int = 10,
) -> int:
    """Store Q/A pairs outside the compaction window permanently.

    Returns: the number of NEWLY stored pairs (0 = nothing to do — the normal
    case after the first run). Sink failures never break out (best effort).
    """
    if not session_id:
        return 0

    if messages is None:
        try:
            from core.multi_session import load_messages

            messages = load_messages(session_id)
        except Exception:
            return 0
    if len(messages) <= max_messages:
        return 0

    effective_sink: MemorySink | None = sink
    if effective_sink is None:
        try:
            from core.auto_memory import maybe_store_turn

            def effective_sink(user_text: str, assistant_text: str) -> Any:
                return maybe_store_turn(user_text, assistant_text, source="compaction")
        except Exception:
            return 0

    # The window sits at the END of the history; discarded = everything before
    # it. The pair index across the whole run is stable *while* the history is
    # append-only — _verified_progress proves that before trusting the count.
    discarded_count = len(messages) - keep_recent
    discarded_pairs = _pairs(messages[:discarded_count])

    cp_path = _checkpoint_path(path)
    checkpoints = _load_checkpoints(cp_path)
    already = _verified_progress(checkpoints, session_id, discarded_pairs)

    stored = 0
    for index, (user_text, assistant_text) in enumerate(discarded_pairs):
        if index < already:
            continue  # checkpoint: already stored, 0 cost
        try:
            result = effective_sink(user_text, assistant_text)
        except Exception:
            break  # frontier: do not advance the checkpoint, the next turn repeats
        if (
            isinstance(result, dict)
            and result.get("stored") is False
            and str(result.get("reason", "")).startswith("error")
        ):
            # The store did not answer — maybe_store_turn's own reason-code
            # pattern. Counting this as preserved would record an outage as
            # "nothing to do" and lose the pairs when the checkpoint advances.
            break
        stored += 1

    if stored > 0 or already > 0:
        _record_progress(checkpoints, session_id, already + stored, discarded_pairs)
        _save_checkpoints(cp_path, checkpoints)
    return stored


def _verified_progress(
    checkpoints: dict[str, Any],
    session_id: str,
    discarded_pairs: list[tuple[str, str]],
) -> int:
    """How many of the current discarded pairs are *proven* already secured.

    Returns the stored count only when the fingerprint over indices
    ``[0, count)`` still matches the current pairs — i.e. the window is a
    superset of what was stored and nothing before the frontier moved. A
    legacy counter without a fingerprint, a corrupt value, a count past the end
    of the (possibly shrunken) window, or a mutated prefix all read as 0:
    re-deriving from the store is safe (Chroma dedupe absorbs true duplicates),
    silently skipping an un-stored decision is not.
    """
    try:
        already = max(0, int(checkpoints.get(session_id, 0)))
    except (TypeError, ValueError):
        # A corrupt per-session counter (hand edit, foreign writer) reads as 0:
        # re-derived from the store, whose embedding dedupe catches the
        # duplicates. Raising here would kill preservation for the session —
        # the fire-and-forget caller swallows the exception every turn.
        return 0
    if already <= 0 or already > len(discarded_pairs):
        return 0
    fingerprints = checkpoints.get(_FP_KEY)
    saved = fingerprints.get(session_id) if isinstance(fingerprints, dict) else None
    if not isinstance(saved, str):
        return 0  # legacy / foreign record: cannot prove → re-store
    if saved != _prefix_fingerprint(discarded_pairs, already):
        return 0  # prefix changed (edit/delete/foreign write): do not skip
    return already


def _record_progress(
    checkpoints: dict[str, Any],
    session_id: str,
    count: int,
    discarded_pairs: list[tuple[str, str]],
) -> None:
    """Persist the counter together with the proof over the stored prefix."""
    checkpoints[session_id] = count
    fingerprints = checkpoints.get(_FP_KEY)
    if not isinstance(fingerprints, dict):
        fingerprints = {}
        checkpoints[_FP_KEY] = fingerprints
    fingerprints[session_id] = _prefix_fingerprint(discarded_pairs, count)



__all__ = [
    "preserve_compacted_pairs",
    "CHECKPOINT_FILENAME",
]
