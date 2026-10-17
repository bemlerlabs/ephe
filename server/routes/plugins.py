"""
◑ Ephe – plugin store routes (wave 5 P3, E1 master switch)
server/routes/plugins.py

GET  /api/plugins              → aggregated view (catalog + registry + master)
POST /api/plugins/{id}/enable  → enabled toggle (body: {"enabled": bool})
POST /api/plugins/master       → kill switch (body: {"enabled": bool});
                                 False = stock Ephe, every toggle inactive.

Fail-soft: a damaged JSON file is an empty store, never a 500.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from core import plugin_runtime
from core.plugin_store import config_root, plugins_view, set_enabled

router = APIRouter(tags=["plugins"])


@router.get("/plugins")
def get_plugins() -> dict:
    """Curated list + installed registry, with the enabled toggles."""
    return plugins_view()


@router.post("/plugins/{plugin_id}/enable")
def post_plugin_enable(plugin_id: str, body: dict) -> dict:
    """Set the enabled state of a plugin (best effort, always able to answer 200)."""
    enabled = bool(body.get("enabled", True))
    # E4b: drift gate — a plugin carrying a signature record is verified against
    # its current content when it is ENABLED (deep setting
    # plugins.plugin_signature_check, default on). Drift = 409, never silent.
    if enabled:
        from core import plugin_signing

        if plugin_signing.signature_check_enabled():
            from core.plugin_manifest import SIG_FILENAME, BUILTIN_PLUGINS_ROOT

            sig_file = next(
                (base / plugin_id / SIG_FILENAME for base in (config_root() / "plugins", BUILTIN_PLUGINS_ROOT)
                 if (base / plugin_id / SIG_FILENAME).is_file()),
                None,
            )
            if sig_file is not None:
                pdir = sig_file.parent
                record = json.loads(sig_file.read_text(encoding="utf-8"))
                ok, reason = plugin_signing.verify_plugin_dir(pdir, record, plugin_signing.load_trusted_public_keys())
                if not ok:
                    from core.audit_log import audit_event

                    audit_event("plugin_gate", tool=plugin_id, decision="signature_denied", detail=reason)
                    raise HTTPException(status_code=409, detail=f"plugin '{plugin_id}' failed signature check: {reason}")
    ok = set_enabled(plugin_id, enabled)
    if ok:
        # E2: the toggle takes effect on the next lookup — do not let the skill
        # list stay stale until the TTL expires.
        from core.skills import invalidate_skill_cache

        invalidate_skill_cache()
    return {"id": plugin_id, "enabled": enabled, "saved": ok}


@router.post("/plugins/master")
def post_plugin_master(body: dict) -> dict:
    """Master kill switch (E1): False = stock Ephe without any plugin gating."""
    enabled = bool(body.get("enabled", True))
    ok = plugin_runtime.set_master_enabled(enabled)
    if ok:
        from core.skills import invalidate_skill_cache

        invalidate_skill_cache()
    return {"master_enabled": enabled, "saved": ok}


@router.get("/plugins/commands")
def get_plugin_commands() -> dict:
    """Slash commands declared in the manifests of ENABLED plugins (E2)."""
    from core import plugin_manifest

    return {"commands": plugin_manifest.manifest_commands()}


@router.get("/plugins/icon/{plugin_id}")
def get_plugin_icon(plugin_id: str):
    """Deliver a plugin icon (Extensions v2, E2).

    Source: the builtin repo root or the installed plugin dir (the user wins).
    The path comes from the manifest (validated: relative, .svg/.png, limits);
    here it is hardened further: traversal rejection + SVG sanitizing (no
    script/foreignObject/on* attribute). 404 → the frontend uses a lettermark.
    """
    import re as _re
    from fastapi import Response
    from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, load_manifest

    if not _re.fullmatch(r"[a-z0-9][a-z0-9-]*", plugin_id or ""):
        raise HTTPException(status_code=404, detail="unknown plugin")
    base = config_root() / "plugins"
    plugin_dir = next(
        (
            cand
            for cand in (base / plugin_id, BUILTIN_PLUGINS_ROOT / plugin_id)
            if cand.is_dir()
        ),
        None,
    )
    if plugin_dir is None:
        raise HTTPException(status_code=404, detail="unknown plugin")
    manifest, _err = load_manifest(plugin_dir)
    icon_rel = (manifest or {}).get("icon")
    if not isinstance(icon_rel, str) or not icon_rel:
        raise HTTPException(status_code=404, detail="plugin has no icon")
    icon_path = (plugin_dir / icon_rel).resolve()
    try:
        icon_path.relative_to(plugin_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="bad icon path")
    if not icon_path.is_file():
        raise HTTPException(status_code=404, detail="icon missing")
    data = icon_path.read_bytes()
    if icon_path.suffix.lower() == ".svg":
        lowered = data[:64_000].lower()
        for bad in (b"<script", b"foreignobject", b"onload", b"onerror", b"javascript:"):
            if bad in lowered:
                raise HTTPException(status_code=404, detail="unsafe icon")
        return Response(
            content=data, media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    media = "image/png"
    return Response(
        content=data, media_type=media,
        headers={"Cache-Control": "public, max-age=3600"},
    )
