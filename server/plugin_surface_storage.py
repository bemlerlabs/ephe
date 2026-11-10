"""Ephe — the page storage a sandboxed plugin surface is given.

server/plugin_surface_storage.py

A surface document is served with `sandbox allow-scripts allow-popups`
(`server/plugin_surface_policy.py`), so its origin is opaque and the engine's
`localStorage` and `sessionStorage` throw a `SecurityError`. The sandbox is not
negotiable — `allow-same-origin` would hand an attacker-authored page the app's
origin and its tokens — so the storage API arrives as a shim instead.

The mount owns two halves of that shim. It serves `sdk/ephe-storage.js` under a
reserved name, exactly the way it already serves `sdk/ephe.js`, and it writes one
snapshot of the bundle's own page store into the document *ahead of* that script.
The snapshot is what makes a synchronous `getItem` honest: the shim never has to
wait for a message round-trip to answer a read. Writes still travel over the
existing `ephe.sdk` bridge to the shell, which routes them to the bundle's own
state root (`core/plugin_state.py`). One state root per plugin is therefore the
same boundary the SDK already had; the shim adds an API, not a new reach.

Only the bundle's own store is embedded, and only into its own document: the
snapshot is read by the plugin id the nonce in the path was minted for. A bundle
that shares a mount origin with no one cannot see a sibling's keys, and the
injection is the same for the entry document and for a nested HTML document the
surface loads beside it.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping

#: The name the mount serves the shim under. It is reserved like `ephe.js`: a
#: bundle that ships a file of the same name does not replace the build's copy.
SHIM_NAME = "ephe-storage.js"

#: The element the shim reads its starting view from. A `type="application/json"`
#: script block is data: the closed `script-src 'self'` carries it as it stands, so the
#: snapshot needs neither a wider policy nor a nonce.
SNAPSHOT_ELEMENT_ID = "ephe-storage-snapshot"

#: A document that opens with a doctype keeps it first: inserting ahead of it
#: would put the engine into quirks mode. `\s*` covers the whitespace some
#: generators leave before the doctype; a leading BOM is stepped over so it stays
#: the encoding signature rather than becoming a stray character in the body.
_LEADING_BOM = b"\xef\xbb\xbf"
_LEADING_DOCTYPE = re.compile(rb"\s*<!doctype\b[^>]*>", re.IGNORECASE)

#: The characters that could end the JSON data block or start an HTML token. A
#: store value is attacker-authored (the bundle wrote it), so the text is escaped
#: as JSON escape sequences — `\u003c` cannot close a `</script>` — and never by
#: trusting the value to be free of them. `ensure_ascii` keeps the block readable
#: whatever charset the plugin's own `<meta>` declares.
_ESCAPES = (
    ("<", "\\u003c"),
    (">", "\\u003e"),
    ("&", "\\u0026"),
    ("\u2028", "\\u2028"),
    ("\u2029", "\\u2029"),
)


def snapshot_markup(values: Mapping[str, object]) -> bytes:
    """The data block and the script tag that starts the shim, as ASCII bytes.

    The order matters: the shim parses its snapshot at execution time, so the data
    block is emitted before the script that reads it. Both sit at the top of the
    document's head, which is what makes every later script see the shim's area.
    """
    text = json.dumps(dict(values), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    for raw, escaped in _ESCAPES:
        text = text.replace(raw, escaped)
    return (
        f'<script type="application/json" id="{SNAPSHOT_ELEMENT_ID}">{text}</script>'
        f'<script src="{SHIM_NAME}"></script>'
    ).encode("ascii")


def install_shim(document: bytes, values: Mapping[str, object]) -> bytes:
    """The document with the shim and its snapshot placed before its own content.

    A script immediately after the doctype parses into the implied `<head>`, so it
    blocks the parser and runs before the entry document's first script: no bundle
    can reach `localStorage` before the shim has replaced it. The original bytes
    are otherwise untouched, which matters because the entry is the plugin's own
    file and this route is not a rewriter.
    """
    tag = snapshot_markup(values)
    start = len(_LEADING_BOM) if document.startswith(_LEADING_BOM) else 0
    doctype = _LEADING_DOCTYPE.match(document, start)
    offset = doctype.end() if doctype else start
    return document[:offset] + tag + document[offset:]
