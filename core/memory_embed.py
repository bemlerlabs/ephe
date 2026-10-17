"""
◑ Ephe – Embedding access for the memory provider
core/memory_embed.py

Two vectorizers behind one factory: `embeddinggemma-2` (768 dimensions narrowed
to 256) is the default, `all-MiniLM-L6-v2` (384 dimensions) is the fallback for a
machine that has not fetched the larger graph or has declared itself offline. Both
run offline as ONNX and both L2-normalise. The Kepta port needs exactly that, and
each model file plus its arithmetic lives in its own module
(`core/memory_embed_gemma.py`, `core/memory_embed_onnx.py`) — this module owns
*which* one loads, the kill switch for the case where neither is there, and the
label the store filters on. When nothing loads, the lexical leg and the entity leg
remain and Ephe says so (`stats.vector_leg = false`).

The label is the boundary between the two vector spaces. It goes into
`chunks.embedding_model` on the write and the ranking legs filter on the same
string, so a 384-wide MiniLM chunk is never scored against a 256-wide
EmbeddingGemma query: a machine that switches models keeps the old vectors
readable without ever mixing the axes.

Why this is its own module: the expensive part is the *import*. The retired store
used to supply that embedder, and importing it cost 642 ms more per process than
reading the file directly (measured 2026-10-14); a fresh Ephe with Kepta memory
must not pay that while nobody needs an embedding. So this exposes only a factory
call, which the provider materialises when needed.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from core.memory_embed_gemma import MODEL_LABEL as GEMMA_LABEL
from core.memory_embed_onnx import MODEL_NAME

logger = logging.getLogger(__name__)

ENV_DISABLE = "EPHE_MEMORY_EMBEDDER"

_DISABLED_VALUES = {"none", "off", "0", "false", "lexical"}

_CACHE: dict[str, Callable[[list[str]], list[list[float]]] | None] = {}


def is_disabled() -> bool:
    """The user (or a test) has explicitly disabled the vector leg."""
    return os.environ.get(ENV_DISABLE, "").strip().lower() in _DISABLED_VALUES


def selected_model() -> str:
    """The model family the settings ask for; its identifier is also its label."""
    from core.settings_schema import deep_select

    return deep_select("memory.embedder")


def effective_label() -> str:
    """The label this process writes and filters on, decided without loading a graph.

    EmbeddingGemma needs 540 MB on disk before it can load, so the fallback covers
    a machine that has not allowed that fetch. The returned string is one label, so
    a caller that writes it into `chunks.embedding_model` cannot widen a filter or
    mix the two spaces.
    """
    if is_disabled():
        return ""
    if selected_model() != GEMMA_LABEL:
        return MODEL_NAME
    from core.memory_embed_gemma import download_consent, model_present, offline

    if model_present() or (download_consent() and not offline()):
        return GEMMA_LABEL
    return MODEL_NAME


def _build_gemma() -> Callable[[list[str]], list[list[float]]]:
    from core.memory_embed_gemma import EmbeddingGemmaEmbedder

    return EmbeddingGemmaEmbedder()


def _build_minilm() -> Callable[[list[str]], list[list[float]]]:
    from core.memory_embed_onnx import MiniLmEmbedder, model_problem

    problem = model_problem()
    if problem:
        raise RuntimeError(problem)
    return MiniLmEmbedder()


def get_embedder() -> Callable[[list[str]], list[list[float]]] | None:
    """Lazy, process-unique: None when disabled, or when nothing loads."""
    if is_disabled():
        return None
    if "embedder" in _CACHE:
        return _CACHE["embedder"]
    label = effective_label()
    embedder: Callable[[list[str]], list[list[float]]] | None = None
    try:  # the artifact is on disk; a machine without it keeps the two other legs
        embedder = _build_gemma() if label == GEMMA_LABEL else _build_minilm()
    except Exception as exc:  # no model loaded → retrieval keeps going on two legs
        logger.warning(
            "memory: embedding model unavailable (%s) — lexical + entity legs only",
            exc,
        )
        embedder = None
    _CACHE["embedder"] = embedder
    return embedder


def model_name() -> str:
    return "" if is_disabled() else effective_label()


def reset_cache() -> None:
    """Test hook: module loading is per process, the env decision is not."""
    _CACHE.clear()
