"""What a reader's client can actually resolve: the boot bundle plus the register copy.

The app loads two files, not one. `app/src/locales/<lang>.json` arrives with the start bundle,
`app/src/lib/settingsCopy.<lang>.json` is loaded when the register opens and merged into the same
namespace by `i18n.addResourceBundle` (`app/src/lib/settingsCopy.ts`). A row asks i18next for one
dotted leaf and does not care which of the two files carried it, so a test that reads one file
alone measures a state the product never has: half the register's sentences look missing.

Reading locales is the allowed exception in tests/AGENTS.md — a locale is data the product loads,
the way the plist and the shipped bundle are read elsewhere. This module is where the three tests
that resolve a sentence agree on how the two files are put together, so none of them can quietly
drift into demanding the copy back in the boot bundle.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "app" / "src" / "locales"
REGISTER_COPY = ROOT / "app" / "src" / "lib"


def boot(language: str) -> dict:
    """The catalog the start bundle carries."""
    return json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))


def register_leaves(language: str) -> dict:
    """The register's copy, keyed by the dotted path a row asks i18next for."""
    module = json.loads((REGISTER_COPY / f"settingsCopy.{language}.json").read_text(encoding="utf-8"))
    return {f"{group}.{leaf}": text for group, leaves in module.items() for leaf, text in leaves.items()}


def shipped(language: str) -> dict:
    """The namespace as the client holds it: boot catalog with the register copy merged in.

    The merge is `addResourceBundle`'s own — same namespace, deeper objects joined — and it refuses
    to hide a leaf standing in both files, because that would let the boot bundle ship register copy
    again while the split still looked intact.
    """
    catalog = boot(language)
    merged = {key: dict(value) if isinstance(value, dict) else value for key, value in catalog.items()}
    for dotted, text in register_leaves(language).items():
        group, _, leaf = dotted.partition(".")
        if group in catalog and not isinstance(catalog[group], dict):
            raise AssertionError(f"{language}: {group} is no object in the boot bundle")
        node = merged.setdefault(group, {})
        if leaf in node:
            raise AssertionError(f"{language}: {dotted} stands in the boot bundle and in the register copy")
        node[leaf] = text
    return merged


def resolve(language: str, dotted: str) -> str:
    """The page's own lookup over both files: a dotted key walks the namespace, an unknown key raises."""
    node: object = shipped(language)
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    assert isinstance(node, str), f"{dotted} is no string"
    return node
