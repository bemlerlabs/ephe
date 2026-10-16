"""Ephe – TUI context meter (P2-9).

The status bar reads its fill from the same budget the PWA shows: a per-message
character estimate (``core.usage.estimate_tokens``, the tokenizer single source of
truth) sized against the window of the active engine. ``resolve_window`` reuses
``core.model_config.resolve_context_window`` — env override, engine probe, tier
table, then the documented legacy 8192 — which is the offline twin of
``GET /api/context/budget`` (``server/routes/context.py:_resolve_window``). Percent
and the 75 % warning line match ``app/src/lib/contextMeter.ts``.

Compose the two pieces: ``resolve_window(model)`` then
``estimate_context_usage(session, window)``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.model_config import resolve_context_window
from core.usage import estimate_tokens

#: from this fill on the meter warns (same figure as app/src/lib/contextMeter.ts)
WARN_THRESHOLD = 0.75


@dataclass(frozen=True)
class ContextUsage:
    """Fill of one session against one window; percent/remaining/warn are derived."""

    system: int = 0
    user: int = 0
    assistant: int = 0
    window: int = 0

    @property
    def total(self) -> int:
        return self.system + self.user + self.assistant

    @property
    def percent(self) -> int:
        # A window of 0 means "the engine names none yet" → full, never NaN.
        if self.window <= 0:
            return 100
        return min(100, round(self.total / self.window * 100))

    @property
    def remaining(self) -> int:
        return max(0, self.window - self.total)

    @property
    def warn(self) -> bool:
        return self.window > 0 and self.total / self.window >= WARN_THRESHOLD


def estimate_context_usage(
    messages: Iterable[Mapping] | None,
    window: int,
) -> ContextUsage:
    """Sum the per-role token estimate over a session's messages.

    A message whose role is neither system nor assistant counts as user — the same
    safe default the TypeScript meter takes for an unknown role.
    """
    system = user = assistant = 0
    for msg in messages or ():
        content = msg.get("content") if isinstance(msg, Mapping) else None
        tokens = estimate_tokens(content if isinstance(content, str) else "")
        role = msg.get("role") if isinstance(msg, Mapping) else ""
        if role == "system":
            system += tokens
        elif role == "assistant":
            assistant += tokens
        else:
            user += tokens
    return ContextUsage(system=system, user=user, assistant=assistant, window=window)


def resolve_window(model: str = "") -> tuple[int, str]:
    """Window for the active engine plus the source it came from.

    The source is one of ``env``/``engine``/``tier``/``legacy`` — kept so a caller
    can label the number instead of asserting one.
    """
    return resolve_context_window(model)


def _compact(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


def meter_text(usage: ContextUsage) -> str:
    """One-line chip for the status bar, e.g. ``ctx 12% · 1.0k/131k tok``."""
    return f"ctx {usage.percent}% · {_compact(usage.total)}/{_compact(usage.window)} tok"
