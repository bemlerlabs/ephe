"""
◑ Ephe – Vision Memory System (HITL)
core/vision_memory.py

Stores and loads visual button states (crops) in the local store, so the Llama
Vision agent receives reference material on the next call.

What stood here before: a persistent vector-store client on
`~/.ephe/memory/chroma_db`, one `vision_rules` collection shared by every
workspace, queried with an L2 radius of 1.2. The caller sees the same two
functions. The radius travels as the cosine floor it was always equal to —
unit-norm vectors make an L2 distance `sqrt(2 - 2*cos)`, so 1.2 is 0.28 — and
the migration writes that floor into the store, where this reader finds it.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Shared by every workspace, the way the single collection always was.
VISION_SCOPE = "vision_rules"

#: Where the migration records the boundary it converted, next to the data.
GATE_KEY = "chroma_import"  # gate:legacy

#: The radius the retired client queried with, and the floor it is equal to.
LEGACY_L2_RADIUS = 1.2
COSINE_FLOOR = round(1.0 - LEGACY_L2_RADIUS ** 2 / 2.0, 6)


def _document(target_description: str) -> str:
    return f"Appearance and position of {target_description} in the current context."


def _provider() -> Any:
    from core.memory_provider import KEPTA, open_provider

    return open_provider(KEPTA, scope=VISION_SCOPE, embedder="auto")


def _cosine_floor(provider: Any) -> float:
    """The floor this store carries, or the derived one when it carries none."""
    carried = provider.meta_value(GATE_KEY)
    target = carried.get("target") if isinstance(carried, dict) else None
    if isinstance(target, dict) and isinstance(target.get("threshold"), (int, float)):
        return float(target["threshold"])
    return COSINE_FLOOR


def _exact_target(provider: Any, target_description: str) -> dict[str, Any] | None:
    """The row whose `raw_target` is the query itself, vector leg or not."""
    for found in provider.list_all(limit=1000):
        meta = found.get("metadata") or {}
        if meta.get("raw_target") == target_description:
            return dict(meta)
    return None


def save_vision_rule(target_description: str, base64_crop: str, x: int, y: int) -> None:
    """Stores a learned UI rule in the local store."""
    provider = _provider()
    try:
        provider.store(
            _document(target_description),
            {
                "base64_crop": base64_crop,
                "last_known_x": x,
                "last_known_y": y,
                "raw_target": target_description,
            },
        )
    finally:
        provider.close()


def find_vision_rule(target_description: str) -> dict[str, Any] | None:
    """The learned crop for `target_description`, or None when none is close enough.

    The floor rejects a *near* row that is not near enough, which is what the
    radius was for. A row carrying the query as its own `raw_target` is returned
    either way: that is the answer the radius would have accepted, and it keeps
    a store without a vector leg (no ONNX artifact, embeddings switched off)
    answering instead of silently forgetting what it learned.
    """
    try:
        provider = _provider()
    except Exception as exc:
        logger.error("vision memory unavailable: %s", exc)
        return None
    try:
        found: dict[str, Any] | None = None
        try:
            matches = provider.cosine_matches(_document(target_description), limit=1)
        except Exception as exc:  # no vector leg → the exact target below still answers
            logger.debug("vision memory vector leg unavailable: %s", exc)
            matches = []
        if matches and matches[0][1] >= _cosine_floor(provider):
            found = dict(matches[0][0].get("metadata") or {})
        if found is None:
            found = _exact_target(provider, target_description)
        return found
    except Exception as exc:
        logger.error("vision memory query failed: %s", exc)
        return None
    finally:
        provider.close()
