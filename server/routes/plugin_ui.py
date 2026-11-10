"""Ephe — the plugin surface routes: one document, its assets, its credential.

server/routes/plugin_ui.py

GET  /api/plugins/ui/{plugin_id}                 → 307 to the directory shape below
GET  /api/plugins/ui/{plugin_id}/{nonce}/        → the declared entry document
GET  /api/plugins/ui/{plugin_id}/{nonce}/{rel}   → one file beside the entry
POST /api/plugins/{plugin_id}/surface-token      → mint, or renew a live credential

`{nonce}` is the mount credential minted by `server/plugin_surface_nonce.py`,
on loopback and off it. A mount URL without a live nonce returns no bytes.
The app's own fetches outside this family stay token-free on loopback.

The policy behind these routes — the media types, the containment, the descriptor
reads — lives in `server/plugin_surface.py`, and the header wording a response
carries lives in `server/plugin_surface_policy.py`, so this file is the HTTP shape
only. Three rules decide everything here.

A surface authenticates with a per-mount nonce carried *inside the path*, which
is the one URL location an `<iframe>` and a native webview can both present on
every request they derive: a document at the directory shape hands its path prefix
to each sub-resource, and a query string would belong to the document's URL alone
while the LAN token itself stays out of URLs entirely (R21 — logs, history and
screenshots all keep a query). The old bare-document URL redirects to the
directory shape, and the old query-string credential now arrives as a request
with no credential and is refused.

The document arrives with its own `Content-Security-Policy`, including the
`sandbox` directive that gives an attacker-authored page an opaque origin: the
policy assembled from `components.ui.capabilities` says what the mount may load,
and the sandbox says whose authority the mount holds. Loosening the shell's
policy in `app/src-tauri/tauri.conf.json` for the whole app to fit plugin code
would be a product-wide downgrade, so both answers ride this route's header.

Page storage is the one authority the sandbox takes away that a surface still
needs, and it is restored without giving the origin back. The route serves
`sdk/ephe-storage.js` under a reserved name and places it, with a snapshot of
this bundle's own page store, at the top of every HTML document it delivers; the
shim answers synchronous reads from that snapshot and sends writes over the
existing `ephe.sdk` bridge to the bundle's state root
(`server/plugin_surface_storage.py`). The policy below is unchanged: `sandbox
allow-scripts allow-popups`, and never `allow-same-origin`.

Nothing is read from disk before the credential and the path have been decided,
and a refusal is a coded `Refused`, so the reader gets the envelope every other
route in this app gives.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from core import path_guard, plugin_runtime
from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, load_manifest, plugins_root
from core.plugin_state import client_snapshot
from core.plugin_store import PLUGIN_NAME_RE
from core.plugin_ui_capabilities import UI_ENTRY_SUFFIX, ui_descriptor
from server import (
    middleware,
    plugin_surface,
    plugin_surface_nonce,
    plugin_surface_policy,
    plugin_surface_storage,
)
from server.refusals import Refused
from server.routes.plugins import _mutation_guard

router = APIRouter(
    tags=["plugin-ui"],
    dependencies=[Depends(_mutation_guard)],
)


def _plugin_dir(plugin_id: str) -> Path | None:
    """The installed directory behind one slug, the user root overriding builtin.

    `path_guard.child` refuses a name that is not a slug before a path is built, so
    the id in a URL cannot reach the filesystem as `..`, as an absolute path or as
    a symlink out of the plugin root.
    """
    for root in (plugins_root(), BUILTIN_PLUGINS_ROOT):
        candidate = path_guard.child(root, plugin_id, pattern=PLUGIN_NAME_RE)
        if candidate is not None and candidate.is_dir():
            return candidate
    return None


def _declared_surface(plugin_id: str) -> tuple[Path, dict]:
    """`(plugin_dir, descriptor)` for a mountable surface, or a coded 404.

    Every question below is a filesystem read, and a plugin directory the owner
    closed answers one of them with an `OSError` that `pathlib` lets travel: the
    runtime scan, the manifest validator and the slug check all `stat` inside the
    directory. A route that served that would answer 500 with the absolute path in
    the body, so the whole preparation is read behind one guard and a closed
    directory arrives as the refusal this route already speaks.
    """
    try:
        return _surface_behind_the_read(plugin_id)
    except OSError:
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason=plugin_surface.REFUSED_SHAPES["unreadable"],
        ) from None


def _surface_behind_the_read(plugin_id: str) -> tuple[Path, dict]:
    """The four questions a mount asks, in the order a reader would ask them.

    Is a plugin installed under this id, is it switched on, does its manifest still
    pass the contract, does it declare a surface at all. A manifest that fails
    validation arrives here as `(None, error)` from `load_manifest`, and its error
    text rides in the `{reason}` slot — the quarantined plugin keeps its own words.
    """
    plugin_dir = _plugin_dir(plugin_id)
    if plugin_dir is None:
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason="no plugin is installed under that id",
        )
    if not plugin_runtime.is_plugin_active(plugin_id):
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason="the plugin is switched off",
        )
    manifest, error = load_manifest(plugin_dir)
    if manifest is None:
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason=f"its manifest is quarantined: {error}",
        )
    descriptor = ui_descriptor(manifest)
    if not descriptor or not descriptor.get("entry"):
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason="the manifest declares no components.ui surface",
        )
    return plugin_dir, descriptor


def _consume_credential(
    request: Request, plugin_id: str, asset_path: str
) -> tuple[str, str | None]:
    """Split the credential segment off the remainder, before any disk is read.

    The first segment after the plugin id has to be a live nonce for exactly
    this plugin, on loopback and off it. Anything else is a coded 401: a stale
    mount, a value minted for another plugin, or the old shape with no segment
    in the path. A refused segment leaves the same throttled audit line a
    guessed LAN token leaves, so a guessing run is visible in the log. A nonce
    with no slash behind it answers the directory shape, because that trailing
    slash is where the browser starts resolving the document's own assets.

    Returns `(relative_path, redirect_url)`; exactly one half is meaningful.
    """
    nonce, slash, remainder = asset_path.partition("/")
    live = bool(nonce) and plugin_surface_nonce.verify_surface_nonce(plugin_id, nonce)
    if not live:
        if nonce:
            middleware._audit_token_refusal(request, "surface_nonce_refused")
        raise Refused("plugin_ui_unauthorized", plugin=plugin_id)
    if not slash:
        return "", f"{request.url.path}/"
    return remainder, None


def _policy(descriptor: dict, isolate: bool) -> str:
    return plugin_surface_policy.surface_content_security_policy(
        descriptor.get("capabilities") or (), middleware._app_origins(), isolate
    )


def _opaque_origin_cors_headers(request: Request) -> dict[str, str]:
    """The two headers a module fetch needs when the document's origin is `null`.

    A sandboxed document's origin is opaque, which the browser presents as the
    literal string `null`. An ES module is fetched in CORS mode, so the response
    must name that origin or the engine withholds the bytes. Naming an origin is
    not the same as lending a credential: this server sets no cookie and gives
    the mount no token, so the bytes arrive with a name on them and nothing else.
    """
    if request.headers.get("origin") == "null":
        return {"Access-Control-Allow-Origin": "null", "Vary": "Origin"}
    return {}


def _served(body: bytes, media_type: str, policy: str, extra_headers: dict | None = None) -> Response:
    """One response, with the three headers a surface may never be without.

    `no-store` because the mount URL carries its credential in a path segment: a
    cached asset would sit behind a value that has since died.
    """
    headers = {
        "Content-Security-Policy": policy,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    if extra_headers:
        headers.update(extra_headers)
    return Response(
        content=body,
        media_type=media_type,
        headers=headers,
    )


def _read(plugin_dir: Path, relative: str, plugin_id: str, refusal: str) -> bytes:
    """The bytes of a file that was proven contained a moment ago.

    Between the containment check and the read the plugin author can change the
    directory under the request — a hot edit, a swapped symlink at any component of
    the path, a file that is gone — and a read by path after the proof follows the
    swap out of the directory. The bytes come from
    `plugin_surface.read_surface_bytes`, which walks the remainder one component at a
    time on directory descriptors, refuses a link at each step, and re-proves the
    opened descriptor; a crash there is the coded refusal the route already speaks,
    and never a 500 with a filesystem path in the body. The remainder the containment
    check was given is the one the walk opens.
    """
    data, reason = plugin_surface.read_surface_bytes(plugin_dir, relative)
    if data is None:
        raise Refused(refusal, plugin=plugin_id, reason=reason)
    return data


def _beside_entry(descriptor: dict, relative: str) -> str:
    """The plugin-dir path of a URL remainder: relative to the entry's directory.

    A browser resolves `app.js` against the directory of the document URL, and
    the mount's directory shape is exactly that directory, so a remainder rides
    from the entry's parent. One root, chosen so the URL a browser derives is the
    URL that loads; a remainder that walks is refused by `resolve_surface_file`
    before it can leave the entry's directory.
    """
    entry_dir = PurePosixPath(descriptor["entry"]).parent.as_posix()
    if entry_dir in (".", ""):
        return relative
    return f"{entry_dir}/{relative}"


def _served_document(plugin_dir: Path, descriptor: dict, plugin_id: str) -> Response:
    """The declared entry as a document: whitelist, HTML, and the isolated policy.

    The entry is resolved through the same containment the asset branch uses. The
    manifest contract already refused an entry that leaves the directory, and a
    route that serves attacker-influenced paths checks for itself. The page-storage
    shim and this bundle's own store snapshot ride at the top of the document, so a
    bundle written against `localStorage` finds an area before its first script runs
    while the policy keeps the opaque origin the sandbox gives it.
    """
    document, reason = plugin_surface.resolve_surface_file(plugin_dir, descriptor["entry"])
    if document is None:
        raise Refused("plugin_ui_unavailable", plugin=plugin_id, reason=reason)
    media_type = plugin_surface.surface_media_type(document)
    if media_type != "text/html" or document.suffix.lower() != UI_ENTRY_SUFFIX:
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason="the declared entry is not an HTML document this route may serve",
        )
    body = _read(plugin_dir, descriptor["entry"], plugin_id, "plugin_ui_unavailable")
    body = plugin_surface_storage.install_shim(body, client_snapshot(plugin_id))
    return _served(body, media_type, _policy(descriptor, isolate=True))


_SDK_FILE = Path(__file__).resolve().parents[2] / "sdk" / "ephe.js"
_STORAGE_SHIM_FILE = Path(__file__).resolve().parents[2] / "sdk" / "ephe-storage.js"


def _served_sdk(descriptor: dict, plugin_id: str, request: Request) -> Response:
    """The build's page sdk. A file of the same name inside the bundle is ignored."""
    try:
        body = _SDK_FILE.read_bytes()
    except OSError:
        raise Refused(
            "plugin_ui_asset_refused",
            plugin=plugin_id,
            reason="the page sdk is not in this build",
        ) from None
    return _served(
        body, "application/javascript", _policy(descriptor, isolate=False),
        _opaque_origin_cors_headers(request),
    )


def _served_storage_shim(descriptor: dict, plugin_id: str, request: Request) -> Response:
    """The build's page-storage shim, under the same reserved-name rule as the sdk.

    A bundle that ships `ephe-storage.js` of its own does not replace this copy:
    the mount is the one that decides what a sandboxed document's `localStorage`
    is, so a bundle-authored replacement would only let a plugin lie to itself
    about where its state goes.
    """
    try:
        body = _STORAGE_SHIM_FILE.read_bytes()
    except OSError:
        raise Refused(
            "plugin_ui_asset_refused",
            plugin=plugin_id,
            reason="the page-storage shim is not in this build",
        ) from None
    return _served(
        body, "application/javascript", _policy(descriptor, isolate=False),
        _opaque_origin_cors_headers(request),
    )


def _served_asset(
    plugin_dir: Path, descriptor: dict, plugin_id: str, relative: str, request: Request
) -> Response:
    """One file beside the entry, from the whitelist and nothing else.

    A suffix outside `ASSET_MEDIA_TYPES` is refused and a directory is refused
    (there is no listing here). An HTML remainder is a nested document and gets
    the sandbox back; a plugin SVG arrives with the isolated document policy the
    icon route already imposes, because an SVG opened as a document can script;
    a script or style arrives un-sandboxed, because the sandbox applies to
    documents and the mount has to be able to load its own files.
    """
    within = _beside_entry(descriptor, relative)
    target, reason = plugin_surface.resolve_surface_file(plugin_dir, within)
    if target is None:
        raise Refused("plugin_ui_asset_refused", plugin=plugin_id, reason=reason)
    media_type = plugin_surface.surface_media_type(target)
    if media_type is None:
        raise Refused(
            "plugin_ui_asset_refused",
            plugin=plugin_id,
            reason=plugin_surface.REFUSED_SHAPES["media"],
        )
    needed = plugin_surface.ASSET_REQUIRED_CAPABILITIES.get(media_type)
    if needed is not None and needed not in (descriptor.get("capabilities") or ()):
        raise Refused(
            "plugin_ui_asset_refused",
            plugin=plugin_id,
            reason=plugin_surface.REFUSED_SHAPES["capability"],
        )
    if media_type == "image/svg+xml":
        policy = plugin_surface_policy.SVG_DOCUMENT_CSP
    else:
        policy = _policy(descriptor, isolate=media_type == "text/html")
    body = _read(plugin_dir, within, plugin_id, "plugin_ui_asset_refused")
    if media_type == "text/html":
        # A nested document is a document of its own, sandboxed like the entry, so
        # it gets the same shim and the same bundle's snapshot. A non-HTML asset is
        # never rewritten: this route delivers bytes, it does not author them.
        body = plugin_surface_storage.install_shim(body, client_snapshot(plugin_id))
    return _served(
        body,
        media_type,
        policy,
        _opaque_origin_cors_headers(request),
    )


@router.get("/plugins/ui/{plugin_id}")
def get_surface_mount_redirect(plugin_id: str, request: Request) -> Response:
    """Send the bare mount URL to the directory shape that carries its assets.

    A document served at a path without the trailing slash resolves
    `<script src="app.js">` beside the plugin id instead of beside the entry, so
    the old shape is dead on both counts: it cannot derive its own assets, and
    off loopback it never carries the credential segment. The redirect hands
    every caller the URL a browser can use, and a caller that kept the old
    query-string credential arrives at the directory with no credential.
    """
    return RedirectResponse(url=f"{request.url.path}/", status_code=307)


@router.get("/plugins/ui/{plugin_id}/{asset_path:path}")
def get_surface_file(plugin_id: str, request: Request, asset_path: str) -> Response:
    """The document at the mount's directory shape, or one file beside its entry.

    An empty remainder is the declared entry under the document policy with its
    sandbox; any other remainder is one file under the entry's own directory.
    Nothing here consults the query string for a credential — the path segment
    consumed above is the only form this route answers.
    """
    relative, redirect = _consume_credential(request, plugin_id, asset_path)
    if redirect is not None:
        return RedirectResponse(url=redirect, status_code=307)
    plugin_dir, descriptor = _declared_surface(plugin_id)
    if not relative:
        return _served_document(plugin_dir, descriptor, plugin_id)
    if relative == "ephe.js":
        return _served_sdk(descriptor, plugin_id, request)
    # The shim rides a *relative* `src` in every document the route injects it
    # into, so a nested document in a subdirectory asks for `sub/ephe-storage.js`
    # rather than the mount root. The name is reserved at every depth for that
    # reason; a bundle cannot shadow it anywhere.
    if PurePosixPath(relative).name == plugin_surface_storage.SHIM_NAME:
        return _served_storage_shim(descriptor, plugin_id, request)
    return _served_asset(plugin_dir, descriptor, plugin_id, relative, request)


async def _offered_surface(request: Request) -> str:
    """The credential a renewal names, or "" when the body asks for a fresh mint."""
    raw = await request.body()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    offered = payload.get("surface")
    if not isinstance(offered, str) or not offered:
        return ""
    return offered


@router.post("/plugins/{plugin_id}/surface-token")
async def post_surface_token(plugin_id: str, request: Request) -> dict:
    """Mint one mount credential, or keep a live one on the same value.

    The route is reachable only where the caller already passed the LAN check, and
    the mutation guard the plugin routes use still requires the same-origin XHR
    marker, so the nonce is issued to the app's own authenticated fetch. The value
    is returned to that caller and held in this process; it is never written down,
    and it belongs in the *path* of the mount URL the caller builds.

    A body that names `surface` asks to keep that credential. The value in the
    answer is the same one, with its window measured again from now, so the frame
    already on screen keeps its URL. A dead value, or a value minted for another
    plugin, is a 401: bringing it back would make a URL copied into history live
    again. A body with no `surface` still mints a fresh credential.
    """
    _declared_surface(plugin_id)
    offered = await _offered_surface(request)
    if offered:
        renewed = plugin_surface_nonce.renew_surface_nonce(plugin_id, offered)
        if renewed is None:
            raise Refused("plugin_ui_unauthorized", plugin=plugin_id)
        return {
            "plugin": plugin_id,
            "surface": renewed.nonce,
            "expires_in": int(renewed.ttl_seconds),
        }
    record = plugin_surface_nonce.mint_surface_nonce(plugin_id)
    return {
        "plugin": plugin_id,
        "surface": record.nonce,
        "expires_in": int(record.ttl_seconds),
    }
