"""
◑ Ephe – The product words a surface prints itself.
ui/surface_words.py

The words live in the surface bundles (`app/src/locales/<language>.json`) under `chat.`,
which is where the PWA reads them. The wheel ships that directory beside this package
(`app/src/**` in the hatch include list), so a source tree and an installed wheel name the
same file. The tree root is found by the rule `core/marketplace_sources.py` uses for the
`marketplace/` directory it reads from the tree it runs in.

The English here is the fallback a surface prints when a bundle cannot answer: no file, an
unreadable file, broken JSON, or a leaf the bundle does not carry. Each of those prints the
English sentence and keeps the card working, so an installation without a bundle reads one
language rather than none.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TREE_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_DIR = TREE_ROOT / "app" / "src" / "locales"

#: The leaves of the thinking state, named the way the bundles name them.
THINKING_LEAVES = ("thinkingNow", "thoughtBriefly", "thoughtForSeconds")

#: What a surface prints when the bundle is silent. Same sentences the English bundle carries.
ENGLISH: dict[str, str] = {
    "thinkingNow": "ephe is flying",
    "thoughtBriefly": "Thought briefly",
    "thoughtForSeconds": "Thought for {{duration}}",
}


def _bundle(language: str) -> dict[str, Any]:
    """One language's catalog, empty when it cannot answer."""
    try:
        parsed = json.loads((BUNDLE_DIR / f"{language}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def thinking_words(language: str) -> dict[str, str]:
    """The thinking titles in the language the surface shows its own text in."""
    section = _bundle(language).get("chat")
    section = section if isinstance(section, dict) else {}
    words: dict[str, str] = {}
    for leaf in THINKING_LEAVES:
        text = section.get(leaf)
        words[leaf] = text if isinstance(text, str) and text.strip() else ENGLISH[leaf]
    return words


def fill(template: str, **parts: str) -> str:
    """A leaf with its `{{name}}` placeholders filled; an unfilled one stays visible."""
    for name, value in parts.items():
        template = template.replace("{{" + name + "}}", value)
    return template
