"""Ephe — the `Content-Security-Policy` a plugin surface response carries.

server/plugin_surface_policy.py

`server/plugin_surface.py` holds the serving policy behind a mount, and this is
the half of it that answers a header: the closed baseline, the widening a
capability in `core/plugin_ui_capabilities.py` paid for, the `sandbox` directive
that decides whose authority the document holds, and the `frame-ancestors`
allow-set the app shell needs in order to frame the mount at all.
`server/routes/plugin_ui.py` asks for one string per response and edits nothing
in it, so the wording of a surface's permissions is decided in exactly one place.

The desktop shell's own policy comes from `app/src-tauri/tauri.conf.json` and
applies per document, so a plugin document gets its policy from here. The
baseline is closed and a directive opens only where a capability earned it; the
comment beside each widening names the capability, because a reader checking what
a mount may reach should not have to reconstruct the grant from the header.

Two directives work as a pair and belong to different layers. `'self'` in the
baseline is the whole app origin, so this policy confines what a document may
*load*; the plugin's own files are confined by the containment and the media-type
whitelist in `server/plugin_surface.py`. What takes the *authority* of that origin
away is the sandbox directive below, and a sandboxed document's requests stop
being same-origin — the observation `tests/test_plugin_surface_isolation_browser.py`
makes on a real engine, per engine, and records as unmeasured on one it cannot
drive.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import re
from typing import Iterable

#: The baseline, in the order the response header prints it. `'self'` here is the
#: whole app origin, so the policy confines what the document may *load*; the
#: plugin's own files stay confined by the containment and the MIME whitelist
#: around the route, and `default-src 'self'` on its own still lets a document on
#: the app origin read every `/api/*` response. What takes the *authority* of that
#: origin away is the sandbox directive `_ISOLATION_DIRECTIVE` adds, and the two
#: work as a pair: load scope across the mount, opaque origin inside it.
_BASELINE_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
)

#: The document's own isolation. Scripts run — `allow-scripts` is why a surface
#: exists — beside the `allow-popups` the global framed-document policy in
#: `server/middleware.py` already grants framed files, and `allow-same-origin`
#: is deliberately absent: that is the token that makes the document's origin
#: opaque, and every authority test in the browser suite leans on it. Sub-resource
#: responses (`.js`, `.css`, fonts, images) carry no sandbox; nested HTML
#: documents re-add it, because a sandbox applies to documents and the asset
#: route can serve one.
_ISOLATION_DIRECTIVE = "sandbox allow-scripts allow-popups"

#: A plugin SVG is script-capable as a document. Served as an image it runs nothing;
#: opened as a document it gets the same isolation the icon route already imposes
#: (`server/routes/plugins.py`), with `frame-ancestors 'none'` so no page can frame
#: it either. Declaring frame-ancestors here is also what keeps
#: `SecurityHeadersMiddleware` from appending its own policy to this one.
SVG_DOCUMENT_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox; base-uri 'none'; frame-ancestors 'none'"

#: An origin this server may name in `frame-ancestors`: a scheme, an authority and an
#: optional port. A wildcard or a bare fragment never survives the filter.
_ANCESTOR_RE = re.compile(
    r"^(?:https?|tauri)://[A-Za-z0-9][A-Za-z0-9.\-_]*(?::\d{1,5})?$"
)


def frame_ancestors(origins: Iterable[str]) -> list[str]:
    """`'self'` plus every origin this app serves, with anything unshaped dropped.

    The plugin document is framed by the app shell, which is same-origin in the
    browser and `tauri://localhost` in the desktop shell. A wildcard would let any
    page frame a plugin surface, so an entry that is not a plain scheme and
    authority never reaches the header. The input includes the operator's
    `EPHE_DEV_ORIGINS` list read through `server/middleware._app_origins`, which
    is exactly why the shape filter is a unit-tested function: an operator can
    widen the allow-set, and a stray `*` or half-written origin still must not.
    """
    kept = sorted({origin.strip() for origin in origins if _ANCESTOR_RE.match((origin or "").strip())})
    return ["'self'", *kept]


def surface_content_security_policy(
    capabilities: Iterable[str], ancestors: Iterable[str], isolate: bool = True
) -> str:
    """The policy one surface response gets, assembled from its own declaration.

    `capabilities` is `ui_descriptor()["capabilities"]`: a name the manifest paid
    for. Nothing here opens a directive on a guess about what a plugin needs.
    `isolate` adds the sandbox directive, and the route sets it for documents —
    the entry and every nested HTML — keeping it off the script and style
    responses a browser loads *inside* the mount.
    """
    declared = set(capabilities or ())
    directives = list(_BASELINE_DIRECTIVES)

    # Capability `wasm`: WebAssembly compiles bytes into code, which a closed
    # `script-src` refuses. Only a manifest that names `wasm` gets the evaluator,
    # and the comment in core/plugin_ui_capabilities.py records that the native
    # feature policy is the layer that decides whether the window runs wasm at all.
    if "wasm" in declared:
        directives[directives.index("script-src 'self'")] = (
            "script-src 'self' 'wasm-unsafe-eval'"
        )

    # Capability `workers`: `worker-src 'self' blob:` — and `'self'` here is the
    # app origin, because a per-plugin origin does not exist to bind a worker to
    # yet. The confining layer for this mount is the per-document sandbox above
    # and the asset containment below it; the capability record in
    # core/plugin_ui_capabilities.py states the same reading, and a name whose
    # layer admits it is not per-plugin stays unenforced. A module worker built
    # from a Blob needs `blob:` beside the origin. With no declaration the
    # directive stays absent, which leaves `worker-src` on `default-src 'self'`.
    if "workers" in declared:
        directives.append("worker-src 'self' blob:")

    # Capability `network` earns nothing here, and that is the honest reading:
    # `components.ui.capabilities` carries names, and the contract
    # (core/plugin_ui_capabilities.py, UI_FIELDS) has no field where a plugin could
    # state the hosts it reaches. Widening `connect-src` to a guessed list would
    # have this surface claim a reach the grant never named, so `connect-src` stays
    # on `default-src 'self'` until the manifest can say which hosts it means.

    if isolate:
        directives.append(_ISOLATION_DIRECTIVE)
    directives.append("frame-ancestors " + " ".join(frame_ancestors(ancestors)))
    return "; ".join(directives)
