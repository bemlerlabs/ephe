"""The two SOL settings and their English fallback text, beside the German locale leaf.

A field in the register needs a reader and a text in the same slice; the readers
are `core/sol/session.py` (the switch) and `core/sol/consolidator.py` (the cap on
active rules). The file sits beside the engine it explains so the register keeps
its own size. The German half of each text is a leaf in app/src/locales/de.json
under `core.settings_hints.hint_key`, which the settings surface resolves with t().
"""
from __future__ import annotations

from typing import Final

SOL_HINTS: Final[dict[str, str]] = {
    "sol.enabled":
        "After a failed round Ephe names the class, the broken assumption and the correction "
        "for the next request. A correction that ended the run becomes a readable rule under "
        ".ephe/learning/; this switch turns both off.",
    "sol.max_active_rules":
        "How many learned project rules ride along in the prompt (5-50). Older rules move to "
        "heuristics-archive.md; none is deleted, and the file stays editable by hand.",
}
