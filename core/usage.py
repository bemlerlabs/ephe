"""Ephe – core/usage: honest token accounting (R33, stress triage P2).

The OpenAI-compatible surface used to ship hardcoded ``0`` usage values,
which is worse than no data: dashboards and agent CLIs trusted the zeros.
Single source of truth now:

  * provider-measured counts (Ollama's final stream chunk, OpenAI usage
    frames) are passed through untouched, flagged ``usage_estimated: False``;
  * when the provider reports nothing, a documented character-based
    estimate is returned and openly flagged ``usage_estimated: True`` —
    never a silent zero.

The ratio is a deliberate offline heuristic: mixed EN/DE prose and code
averages ~4.2 characters per subword token for the Gemma/Qwen vocabularies
this product ships with. It is an estimate, and the flag says so.

The counter behind that estimate is a named choice. ``estimate_tokens`` used to
prefer tiktoken whenever it happened to be importable, so the same fixture
priced at 2407 tokens through the heuristic and 33 through BPE — enough to move
every window-fitting boundary. The choice has a name (``EPHE_TOKEN_COUNTER``)
and the name that ran is written back: ``tokenizer_backend()`` reports it
wherever the budget is shown, and a usage block names the counter whenever one
priced a side.
"""
from __future__ import annotations

import math
import os

CHARS_PER_TOKEN = 4.2

#: CJK syllables sit near 1:1 in the tokenizer — the Latin ratio 4.2 would
#: undercount them by a factor of ~4 (400 Chinese characters would be "100 tokens").
CJK_TOKENS_PER_CHAR = 1.0

#: W16: backend names as the SSOT for the budget endpoint, the status-bar chip
#: and the usage_estimated derivation — exact for tiktoken-BPE, otherwise calibrated.
BPE_BACKEND = "tiktoken-bpe"
CALIBRATED_BACKEND = "calibrated-4.2"

#: The counter as an explicit setting. ``auto`` keeps the historical preference
#: (tiktoken when importable, else the heuristic); the two backend names pin one
#: counter on every machine, so a ceiling priced against it does not drift.
COUNTER_ENV = "EPHE_TOKEN_COUNTER"
COUNTER_AUTO = "auto"

_TIKTOKEN_ENCODING: object | None = None
_TIKTOKEN_RESOLVED = False


def counter_setting() -> str:
    """The counter requested through ``EPHE_TOKEN_COUNTER`` (``auto`` when unset).

    An unrecognised value resolves to ``auto`` so a stray setting cannot fail a turn.
    """
    raw = os.environ.get(COUNTER_ENV, "").strip().lower()
    if raw in ("tiktoken", BPE_BACKEND):
        return BPE_BACKEND
    if raw in ("calibrated", CALIBRATED_BACKEND):
        return CALIBRATED_BACKEND
    return COUNTER_AUTO


def _get_tiktoken_encoding():
    """BPE subword counter (cl100k_base), or None when it is not the active choice.

    An explicit ``calibrated`` never loads tiktoken; an explicit ``tiktoken`` that
    cannot be imported leaves the heuristic in place.
    Resolved once; reset_tokenizer_cache() forces a re-resolution
    (test harnesses set sys.modules['tiktoken'] before the next call)."""
    global _TIKTOKEN_ENCODING, _TIKTOKEN_RESOLVED
    if _TIKTOKEN_RESOLVED:
        return _TIKTOKEN_ENCODING
    if counter_setting() == CALIBRATED_BACKEND:
        _TIKTOKEN_ENCODING = None
    else:
        try:
            import tiktoken
            _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _TIKTOKEN_ENCODING = None
    _TIKTOKEN_RESOLVED = True
    return _TIKTOKEN_ENCODING


def reset_tokenizer_cache() -> None:
    """Forces re-resolution of the BPE backend (after an env-/sys.modules change)."""
    global _TIKTOKEN_ENCODING, _TIKTOKEN_RESOLVED
    _TIKTOKEN_ENCODING = None
    _TIKTOKEN_RESOLVED = False


def tokenizer_backend() -> str:
    """Active counter backend name (exact for tiktoken, otherwise calibrated)."""
    return BPE_BACKEND if _get_tiktoken_encoding() is not None else CALIBRATED_BACKEND


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3000 <= code <= 0x30FF       # CJK Symbols + Punctuation
        or 0x3400 <= code <= 0x4DBF    # Ext A
        or 0x4E00 <= code <= 0x9FFF    # Unified Ideographs
        or 0xF900 <= code <= 0xFAFF    # Compatibility Ideographs
        or 0xFF00 <= code <= 0xFFEF    # Half/Full-Width Forms
        or 0x31F0 <= code <= 0x31FF    # Bopomofo
    )


def estimate_tokens(text: str) -> int:
    """Token count — BPE-exact when that is the active counter, else the heuristic.

    Two-bucket heuristic (calibrated counter): CJK counts ~1 token per character,
    Latin ~4.2 characters per token. Pure Latin fixtures stay numerically identical
    to the old ratio — only mixed/CJK text is calibrated (P0-3).
    """
    if not text:
        return 0
    encoding = _get_tiktoken_encoding()
    if encoding is not None:
        try:
            return len(encoding.encode(text))
        except Exception:
            pass  # defensive: a broken encoding -> the heuristic takes over
    cjk = sum(1 for ch in text if _is_cjk(ch))
    latin = len(text) - cjk
    return math.ceil(cjk * CJK_TOKENS_PER_CHAR + latin / CHARS_PER_TOKEN)


def serialize_prompt(messages: list[dict]) -> str:
    """Flatten chat messages into the text the model effectively sees."""
    parts: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, list):  # multimodal parts → text parts only
            content = " ".join(
                str(p.get("text", "")) for p in content if isinstance(p, dict)
            )
        parts.append(f"{msg.get('role', 'user')}: {content if content is not None else ''}")
    return "\n".join(parts)


def build_usage(
    prompt_text: str,
    completion_text: str,
    *,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cached_tokens: int | None = None,
) -> dict:
    """Build the OpenAI-shaped usage block, measured-first, estimated-fallback.

    Either side may be measured independently; every estimated side flips the
    block-wide ``usage_estimated`` flag so consumers can tell real accounting
    from a documented guess.

    ``cached_tokens`` (wave 3: prompt-cache chip) is passed through ONLY
    when the provider has reported it — estimated cache numbers would be
    a lie. The shape follows OpenAI: ``prompt_tokens_details.cached_tokens``.

    ``tokenizer`` names the counter that priced the block, so a run's usage
    records the choice and a reader need not guess the environment. A block
    whose both sides the provider measured names none: no counter ran.
    """
    p = prompt_tokens if prompt_tokens is not None else estimate_tokens(prompt_text)
    c = completion_tokens if completion_tokens is not None else estimate_tokens(completion_text)
    # W16: with the BPE backend even the independently counted side is exact —
    # usage_estimated now only marks the calibrated heuristic as an estimate.
    missing = prompt_tokens is None or completion_tokens is None
    estimated = missing and tokenizer_backend() != BPE_BACKEND
    block = {
        "prompt_tokens": int(p),
        "completion_tokens": int(c),
        "total_tokens": int(p) + int(c),
        "usage_estimated": bool(estimated),
    }
    if missing:
        block["tokenizer"] = tokenizer_backend()
    if cached_tokens is not None and cached_tokens > 0:
        block["prompt_tokens_details"] = {"cached_tokens": int(cached_tokens)}
    return block


def extract_measured_counts(chunk: dict) -> tuple[int, int] | None:
    """Pull provider-reported counts out of a raw stream chunk, if present.

    Understands Ollama's native metrics (``prompt_eval_count``/``eval_count``
    in the final chunk) and OpenAI-compatible usage frames.
    """
    if not isinstance(chunk, dict):
        return None
    p, c = chunk.get("prompt_eval_count"), chunk.get("eval_count")
    if p is not None and c is not None:
        return int(p), int(c)
    usage = chunk.get("usage")
    if isinstance(usage, dict):
        p = usage.get("prompt_tokens", usage.get("prompt_eval_count"))
        c = usage.get("completion_tokens", usage.get("eval_count"))
        if p is not None and c is not None:
            return int(p), int(c)
    return None
