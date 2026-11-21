"""Ephe — the webview feature policy a plugin surface is served under.

server/plugin_surface_features.py

`server/plugin_surface_policy.py` answers the header a mount carries; this is
the half that answers the document. Three capabilities — `webgl`, `wasm` and
`audio-out` — are confined by the surface feature policy: the route writes the
declared set into the document as a JSON block, and `sdk/ephe-feature-policy.js`
turns a missing name into an absent API before the document's own first script
runs. The native window applies the same script as its initialization script
(`app/src-tauri/src/plugin_window.rs`), so both halves of a surface answer to one
policy and one file.

The block is `type="application/json"`, which is data rather than code: the
closed `script-src 'self'` of the surface policy carries it without an inline
grant, the same way the page-storage snapshot rides ahead of its shim. The
script itself is served from the build under a reserved name, so a bundle cannot
shadow the policy with a file of its own.

A name this module does not list earns nothing here. The vocabulary is
`core/plugin_ui_capabilities.py`, and the three names are the enforced subset
that module records.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable

#: The capabilities this layer confines, in the order the policy object prints.
#: A name that leaves the enforced subset of `core/plugin_ui_capabilities.py`
#: leaves this tuple in the same change.
FEATURE_CAPABILITIES: tuple[str, ...] = ("audio-out", "wasm", "webgl")

#: The name the mount serves the policy script under. Reserved like the page
#: storage shim: a bundle that ships a file of this name does not replace it.
POLICY_SCRIPT_NAME = "ephe-feature-policy.js"

#: The element the policy reads its declared set from when the shell has not
#: already written it into the webview.
POLICY_ELEMENT_ID = "ephe-feature-policy"

#: A document that opens with a doctype keeps it first: inserting ahead of it
#: would put the engine into quirks mode. A leading BOM is stepped over so it
#: stays the encoding signature rather than becoming a stray character.
_LEADING_BOM = b"\xef\xbb\xbf"
_LEADING_DOCTYPE = re.compile(rb"\s*<!doctype\b[^>]*>", re.IGNORECASE)


def feature_policy(capabilities: Iterable[str]) -> dict[str, bool]:
    """The declared set as the script reads it: three names, never a guess."""
    declared = set(capabilities or ())
    return {name: name in declared for name in FEATURE_CAPABILITIES}


def policy_markup(capabilities: Iterable[str]) -> bytes:
    """The data block and the script tag that applies it, as ASCII bytes.

    The order matters: the block is data the script reads at execution time, so
    it is emitted first and the script that consumes it second.
    """
    text = json.dumps(
        feature_policy(capabilities), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return (
        f'<script type="application/json" id="{POLICY_ELEMENT_ID}">{text}</script>'
        f'<script src="{POLICY_SCRIPT_NAME}"></script>'
    ).encode("ascii")


def install_policy(document: bytes, capabilities: Iterable[str]) -> bytes:
    """The document with the policy placed before its own content.

    A script immediately after the doctype parses into the implied `<head>`, so
    it blocks the parser and runs before the entry document's first script. The
    original bytes are otherwise untouched, which matters because the entry is
    the plugin's own file and this route is not a rewriter.
    """
    tag = policy_markup(capabilities)
    start = len(_LEADING_BOM) if document.startswith(_LEADING_BOM) else 0
    doctype = _LEADING_DOCTYPE.match(document, start)
    offset = doctype.end() if doctype else start
    return document[:offset] + tag + document[offset:]
