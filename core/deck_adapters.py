"""Optional Deck Engine v2 adapter discovery.

The local renderer remains the default. External/open-source presentation
engines can be enabled later without becoming hard runtime dependencies.

Each opt-in is read ONCE and normalised there. Reading `get(X) or get(X, ...)` looks
like a two-stage fallback, but here the two operands disagree, so the value the user
typed lost whenever it was truthy: a whitespace-only `EPHE_PRESENTON_URL` reported an
available adapter, and `EPHE_ENABLE_PPTXGENJS=false` — a non-empty string, therefore
truthy — ENABLED the adapter its own name was disabling.
"""
from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)

#: The two words an opt-in understands. Anything outside them means OFF: guessing "on"
#: for a typo would hand an external engine (network, cost, a node subprocess) to
#: somebody who never asked for it.
_FLAG_ON = frozenset({"1", "true", "yes", "on"})
_FLAG_OFF = frozenset({"0", "false", "no", "off"})


def _env_flag(name: str) -> bool:
    """Explicit truthiness for an opt-in env var — `bool("false")` is the defect this replaces."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if lowered in _FLAG_ON:
        return True
    if lowered not in _FLAG_OFF:
        # Silent for a recognised "no"; loud for an input nobody can read as either.
        logger.warning(
            "%s=%r is neither on (%s) nor off (%s) — adapter stays disabled",
            name,
            raw[:40],
            "/".join(sorted(_FLAG_ON)),
            "/".join(sorted(_FLAG_OFF)),
        )
    return False


def optional_adapter_status() -> dict:
    presenton_url = os.environ.get("EPHE_PRESENTON_URL", "").strip()
    pptxgenjs_enabled = _env_flag("EPHE_ENABLE_PPTXGENJS")
    return {
        "active": "local_engine_v2",
        "hard_dependency": False,
        "adapters": {
            "presenton": {
                "available": bool(presenton_url),
                "configured_by": "EPHE_PRESENTON_URL" if presenton_url else "",
                "hard_dependency": False,
            },
            "pptxgenjs": {
                "available": bool(pptxgenjs_enabled and shutil.which("node")),
                "configured_by": "EPHE_ENABLE_PPTXGENJS" if pptxgenjs_enabled else "",
                "hard_dependency": False,
            },
        },
    }
