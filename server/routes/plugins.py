"""
◑ Ephe – plugin store and lifecycle routes (wave 5 P3, P1 lifecycle)

GET  /api/plugins                     → aggregated view (catalog + switch state)
PUT  /api/plugins/{id}/enabled        → the lifecycle switch (scope, version, ETag)
POST /api/plugins/{id}/cancel         → cancel a pending activation
POST /api/plugins/{id}/enable         → one-release compatibility shim
POST /api/plugins/master              → legacy control; off pauses every plugin
GET  /api/plugins/events              → SSE state/pending/failed/paused events
GET  /api/plugins/commands            → commands of enabled plugins
GET  /api/plugins/icon/{id}           → plugin icon

A failed write is an HTTP error, never 200 with saved:false.

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import json
import queue

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from core import plugin_runtime, plugin_switch_policy
from core.plugin_lifecycle import (
    STATE_FILENAME,
    LifecycleError,
    PluginSnapshot,
    PluginState,
    subscribe,
    unsubscribe,
)
from core.plugin_store import config_root, plugins_view

_SCOPES = ("user", "workspace")


def _mutation_guard(request: Request) -> None:
    """Same-origin mutations carry the XHR marker the app's client always sends.

    A cross-origin page cannot add this header without a successful CORS
    preflight, so a simple form post cannot flip a plugin switch. GET stays open.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "unauthorized",
                "detail": "X-Requested-With: XMLHttpRequest required",
            },
        )


router = APIRouter(
    tags=["plugins"],
    dependencies=[Depends(_mutation_guard)],
)


def _state_payload(snapshot: PluginSnapshot) -> dict:
    return {
        "name": snapshot.name,
        "state": snapshot.state.value,
        "enabled": snapshot.enabled,
        "version": snapshot.version,
        "scope": snapshot.scope,
        "etag": snapshot.etag,
        "pause_all": snapshot.pause_all,
    }


def _lifecycle_http_error(exc: LifecycleError) -> HTTPException:
    detail: dict = {"code": exc.code, "detail": exc.detail}
    if exc.snapshot is not None:
        detail["current"] = _state_payload(exc.snapshot)
    return HTTPException(status_code=exc.status, detail=detail)


def _invalidate_caches() -> None:
    from core.skills import invalidate_skill_cache

    invalidate_skill_cache()
    plugin_runtime.invalidate_ownership_cache()


def _audit_scope(body: dict) -> str:
    scope = body.get("scope", "user")
    return str(scope) if scope in _SCOPES else ""


def _read_only_guard(action: str, plugin_id: str = "", scope: str = "") -> None:
    """The one choke point for the read-only brake on every switch mutation."""
    if not plugin_switch_policy.read_only():
        return
    plugin_switch_policy.audit_refusal(action=action, plugin=plugin_id, scope=scope)
    raise HTTPException(
        status_code=423,
        detail={"code": plugin_switch_policy.READ_ONLY_CODE},
    )


def _signature_gate(plugin_id: str) -> None:
    """E4b drift gate: an enabled plugin with a signature record is verified."""
    from core import plugin_signing

    if not plugin_signing.signature_check_enabled():
        return
    from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, SIG_FILENAME

    sig_file = next(
        (
            base / plugin_id / SIG_FILENAME
            for base in (config_root() / "plugins", BUILTIN_PLUGINS_ROOT)
            if (base / plugin_id / SIG_FILENAME).is_file()
        ),
        None,
    )
    if sig_file is None:
        return
    record = json.loads(sig_file.read_text(encoding="utf-8"))
    ok, reason = plugin_signing.verify_plugin_dir(
        sig_file.parent, record, plugin_signing.load_trusted_public_keys()
    )
    if ok:
        return
    from core.audit_log import audit_event

    audit_event(
        "plugin_gate", tool=plugin_id, decision="signature_denied", detail=reason
    )
    raise HTTPException(
        status_code=409,
        detail=f"plugin '{plugin_id}' failed signature check: {reason}",
    )


def _scope_from(body: dict) -> str:
    scope = body.get("scope", "user")
    if scope not in _SCOPES:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "field": "scope"},
        )
    return str(scope)


@router.get("/plugins")
def get_plugins() -> dict:
    """Curated list + installed registry, with the enabled toggles."""
    return plugins_view()


@router.put("/plugins/{plugin_id}/enabled")
def put_plugin_enabled(
    plugin_id: str,
    body: dict,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """One endpoint for both directions; commits only after the registry confirms."""
    _read_only_guard("set", plugin_id, _audit_scope(body))
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "field": "enabled"},
        )
    expected_version = body.get("expected_version")
    if expected_version is not None and not isinstance(expected_version, str):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "field": "expected_version"},
        )
    scope = _scope_from(body)
    if enabled:
        _signature_gate(plugin_id)
    try:
        snapshot = plugin_runtime.lifecycle().set_enabled(
            plugin_id,
            enabled,
            scope=scope,
            expected_version=expected_version,
            expected_etag=if_match,
            idempotency_key=idempotency_key,
            actor="user",
            reason=str(body.get("reason") or ""),
        )
    except LifecycleError as exc:
        raise _lifecycle_http_error(exc) from exc
    _invalidate_caches()
    response.headers["ETag"] = snapshot.etag
    if snapshot.state in (PluginState.ENABLING, PluginState.DISABLING):
        response.status_code = 202
        return {
            "state": snapshot.state.value,
            "token": snapshot.etag,
            "poll": "/api/plugins/events",
        }
    return _state_payload(snapshot)


@router.post("/plugins/{plugin_id}/cancel")
def post_plugin_cancel(plugin_id: str, body: dict, response: Response) -> dict:
    """Cancels a pending activation; the plugin stays off with no staged capability."""
    _read_only_guard("cancel", plugin_id, _audit_scope(body))
    scope = _scope_from(body)
    try:
        snapshot = plugin_runtime.lifecycle().cancel(plugin_id, scope=scope)
    except LifecycleError as exc:
        raise _lifecycle_http_error(exc) from exc
    _invalidate_caches()
    response.headers["ETag"] = snapshot.etag
    return _state_payload(snapshot)


@router.get("/plugins/events")
def get_plugin_events() -> StreamingResponse:
    """SSE stream for every open window; a reconnect reads /api/plugins first."""
    state_path = config_root() / STATE_FILENAME

    def events():
        subscriber = subscribe(state_path)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                data = json.dumps(event["data"], ensure_ascii=False)
                yield f"id: {event['id']}\nevent: {event['event']}\ndata: {data}\n\n"
        finally:
            unsubscribe(subscriber)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/plugins/{plugin_id}/enable")
def post_plugin_enable(
    plugin_id: str,
    body: dict,
    if_match: str | None = Header(default=None, alias="If-Match"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """One-release shim: delegates to the lifecycle, never reports a failed write as 200."""
    _read_only_guard("legacy_enable", plugin_id, _audit_scope(body))
    if "enabled" not in body:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "field": "enabled"},
        )
    enabled = body["enabled"]
    if not isinstance(enabled, bool):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "field": "enabled"},
        )
    scope = _scope_from(body)
    if enabled:
        _signature_gate(plugin_id)
    try:
        snapshot = plugin_runtime.lifecycle().set_enabled(
            plugin_id,
            enabled,
            scope=scope,
            expected_version=body.get("expected_version"),
            expected_etag=if_match,
            idempotency_key=idempotency_key,
            actor="user",
            reason=str(body.get("reason") or "legacy enable route"),
        )
    except LifecycleError as exc:
        raise _lifecycle_http_error(exc) from exc
    _invalidate_caches()
    return {"id": plugin_id, "enabled": snapshot.enabled, "saved": True}


@router.post("/plugins/master")
def post_plugin_master(body: dict) -> dict:
    """Legacy control: off pauses every plugin, on restores the per-plugin states."""
    _read_only_guard("master")
    if "enabled" not in body or not isinstance(body["enabled"], bool):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "field": "enabled"},
        )
    enabled = body["enabled"]
    try:
        plugin_runtime.lifecycle().set_pause_all(
            not enabled,
            actor="user",
            reason="legacy master route",
        )
    except LifecycleError as exc:
        raise _lifecycle_http_error(exc) from exc
    from core.skills import invalidate_skill_cache

    invalidate_skill_cache()
    return {"master_enabled": enabled, "saved": True}


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
        for bad in (
            b"<script",
            b"foreignobject",
            b"onload",
            b"onerror",
            b"javascript:",
        ):
            if bad in lowered:
                raise HTTPException(status_code=404, detail="unsafe icon")
        return Response(
            content=data,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    media = "image/png"
    return Response(
        content=data,
        media_type=media,
        headers={"Cache-Control": "public, max-age=3600"},
    )
