"""Ephe — the plugin artifact routes: generated static files under an opaque origin.

GET /api/plugin-artifacts/{plugin_id}/{nonce}/{artifact_id}/{path}
    → one generated file of a plugin (site preview, rendered frame), served under
      a closed CSP with a mount credential the iframe or native webview cannot
      send in a header.

The route reuses the plugin surface's nonce verification, containment walk
(`O_NOFOLLOW`, symlink refusal), media whitelist and CSP assembly. A request that
walks out of the plugin directory, names an unlisted suffix, offers a nonce minted
for another plugin, or asks for a file the surface may not load is refused before
a byte is read; the response names only the mount's opaque origin.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Request
from fastapi.responses import Response

from core import path_guard, plugin_runtime
from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, plugins_root, load_manifest
from core.plugin_store import PLUGIN_NAME_RE
from core.plugin_ui_capabilities import ui_descriptor
from server import (
    middleware,
    plugin_surface,
    plugin_surface_nonce,
    plugin_surface_policy,
)
from server.refusals import Refused

router = APIRouter(tags=["plugin-artifacts"])


def _plugin_dir(plugin_id: str) -> Path | None:
    """The installed directory behind one slug, the user root overriding builtin."""

    for root in (plugins_root(), BUILTIN_PLUGINS_ROOT):
        candidate = path_guard.child(root, plugin_id, pattern=PLUGIN_NAME_RE)
        if candidate is not None and candidate.is_dir():
            return candidate
    return None


def _declared_bundle(plugin_id: str) -> tuple[Path, dict]:
    """The installed directory and its UI descriptor, or a coded refusal."""

    plugin_dir = _plugin_dir(plugin_id)
    if plugin_dir is None:
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason="no plugin is installed under that id",
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


def _policy(descriptor: dict, isolate: bool) -> str:
    return plugin_surface_policy.surface_content_security_policy(
        descriptor.get("capabilities") or (), middleware._app_origins(), isolate
    )


def _opaque_origin_cors_headers(request: Request) -> dict[str, str]:
    """The two headers a module fetch needs when the document's origin is `null`."""

    if request.headers.get("origin") == "null":
        return {"Access-Control-Allow-Origin": "null", "Vary": "Origin"}
    return {}


def _served(body: bytes, media_type: str, policy: str, extra_headers: dict | None = None) -> Response:
    """One response, with the three headers a surface may never be without."""

    headers = {
        "Content-Security-Policy": policy,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    if extra_headers:
        headers.update(extra_headers)
    return Response(content=body, media_type=media_type, headers=headers)


def _read(plugin_dir: Path, relative: str, plugin_id: str, refusal: str) -> bytes:
    """The bytes of a file the walk proved contained, refusing a link at every step."""

    data, reason = plugin_surface.read_surface_bytes(plugin_dir, relative)
    if data is None:
        raise Refused(refusal, plugin=plugin_id, reason=reason)
    return data


@router.get(
    "/plugin-artifacts/{plugin_id}/{nonce}/{artifact_id}/{path:path}",
    name="plugin-artifact-file",
)
def get_plugin_artifact(plugin_id: str, nonce: str, artifact_id: str, path: str, request: Request) -> Response:
    """A generated file of a plugin, sealed to the mount that owns its nonce.

    The artifact is resolved inside the plugin directory, so a path that walks
    out of it, a suffix the surface will not serve, or a nonce minted for
    another plugin is refused before the file is opened. The document carries a
    closed policy and never hands a second origin the app's authority.
    """
    plugin_dir, descriptor = _declared_bundle(plugin_id)
    if not plugin_runtime.is_plugin_active(plugin_id):
        raise Refused(
            "plugin_ui_unavailable",
            plugin=plugin_id,
            reason="the plugin is switched off",
        )
    if not plugin_surface_nonce.verify_surface_nonce(plugin_id, nonce):
        middleware._audit_token_refusal(request, "surface_nonce_refused")
        raise Refused("plugin_ui_unauthorized", plugin=plugin_id)

    relative = f"{artifact_id}/{path}" if path else artifact_id
    target, reason = plugin_surface.resolve_surface_file(plugin_dir, relative)
    if target is None:
        raise Refused(
            "plugin_ui_asset_refused",
            plugin=plugin_id,
            reason=reason,
        )
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
    body = _read(plugin_dir, relative, plugin_id, "plugin_ui_asset_refused")
    return _served(
        body,
        media_type,
        policy,
        _opaque_origin_cors_headers(request),
    )
