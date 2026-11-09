"""
◑ Ephe – plugin store and lifecycle routes (wave 5 P3, P1 lifecycle)

GET  /api/plugins                     → aggregated view (catalog + switch state)
GET  /api/plugins/{id}/state          → bytes kept against the bundle ceiling, and the file list
POST /api/plugins/{id}/state/remove   → delete one stored file inside that folder
GET  /api/plugins/{id}/client/storage → one page-sdk value, by key
PUT  /api/plugins/{id}/client/storage → write or clear that key
POST /api/plugins/{id}/client/tool    → run one tool this bundle owns
PUT  /api/plugins/{id}/enabled        → the lifecycle switch (scope, version, ETag)
POST /api/plugins/{id}/cancel         → cancel a pending activation
POST /api/plugins/{id}/enable         → one-release compatibility shim
POST /api/plugins/master              → legacy control; off pauses every plugin
GET  /api/plugins/events              → SSE state/pending/failed/paused events
GET  /api/plugins/commands            → commands of enabled plugins
GET  /api/plugins/icon/{id}           → plugin icon
GET  /api/plugins/surface-hosts       → host placement for open surfaces
PUT  /api/plugins/{id}/surface-host   → record that placement

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
from server.refusals import Refused

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
    """E4b drift gate: the same check the lifecycle runs on the CLI path."""
    from core import plugin_signing

    ok, reason = plugin_signing.verify_enable(plugin_id)
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


@router.get("/plugins/surface-hosts")
def get_plugin_surface_hosts() -> dict:
    """Host placement for every plugin surface. No page state, no mount URL."""
    from core import plugin_runtime

    return {"surfaces": plugin_runtime.lifecycle().surface_hosts()}


@router.put("/plugins/{plugin_id}/surface-host")
def put_plugin_surface_host(plugin_id: str, body: dict) -> dict:
    """Record where the shell put this surface. The page's own state stays out."""
    from core.plugin_surface_host import parse_host_record

    _known_bundle(plugin_id)
    if not isinstance(body, dict):
        raise Refused("invalid_request")
    try:
        record = parse_host_record(body)
    except ValueError:
        raise Refused("invalid_request") from None
    stored = plugin_runtime.lifecycle().remember_surface(plugin_id, record)
    return {"plugin": plugin_id, "surface": stored}


def _unknown_bundle(plugin_id: str) -> None:
    from core.plugin_state import is_addressable

    if is_addressable(plugin_id):
        return
    raise HTTPException(status_code=404, detail={"code": "plugin_unknown"})


@router.get("/plugins/{plugin_id}/state")
def get_plugin_state(plugin_id: str) -> dict:
    """Bytes kept, bytes allowed, and the stored-file names. No host path."""
    from core.plugin_state import report

    _unknown_bundle(plugin_id)
    return report(plugin_id)


@router.post("/plugins/{plugin_id}/state/remove")
def post_plugin_state_remove(plugin_id: str, body: dict) -> dict:
    """Delete one stored file the reader named, then return the report."""
    from core.plugin_state import remove_stored_file
    from server.refusals import Refused

    _read_only_guard("remove", plugin_id, _audit_scope(body))
    _unknown_bundle(plugin_id)
    name = body.get("name") if isinstance(body, dict) else None
    try:
        return remove_stored_file(plugin_id, name)
    except ValueError:
        raise Refused("plugin_state_name") from None


def _known_bundle(plugin_id: str) -> None:
    from core.plugin_state import is_addressable

    if not is_addressable(plugin_id):
        raise Refused("plugin_unknown")


@router.get("/plugins/{plugin_id}/client/storage")
def get_plugin_client_storage(plugin_id: str, key: str = "") -> dict:
    """One stored page value. A missing key is present=false and creates nothing."""
    from core.plugin_state import client_get

    _known_bundle(plugin_id)
    try:
        value, present = client_get(plugin_id, key)
    except ValueError:
        raise Refused("invalid_request") from None
    return {"value": value, "present": present}


@router.put("/plugins/{plugin_id}/client/storage")
def put_plugin_client_storage(plugin_id: str, body: dict) -> dict:
    """Write one JSON value, or drop the key when value is null."""
    from core.plugin_state import client_set, report

    _read_only_guard("client_store", plugin_id)
    _known_bundle(plugin_id)
    if not isinstance(body, dict) or "key" not in body:
        raise Refused("invalid_request")
    try:
        present = client_set(plugin_id, body.get("key"), body.get("value"))
    except ValueError as exc:
        if str(exc) == "cap":
            usage = report(plugin_id)
            raise Refused(
                "plugin_state_full",
                plugin=plugin_id,
                used_mb=usage["used_mb"],
                cap_mb=usage["cap_mb"],
            ) from None
        raise Refused("invalid_request") from None
    return {"present": present}


@router.post("/plugins/{plugin_id}/client/tool")
async def post_plugin_client_tool(plugin_id: str, body: dict) -> dict:
    """Run one tool this bundle owns. The chat approval gate still applies."""
    from core.plugin_runtime import tool_gate
    from core.tools.chat_gate import confirm_for_chat
    from core.tools.registry import execute_tool
    from core.tools.session_ctx import get_current_policy

    _read_only_guard("client_tool", plugin_id)
    _known_bundle(plugin_id)
    if not isinstance(body, dict):
        raise Refused("invalid_request")
    name = body.get("name")
    arguments = body.get("arguments", {})
    if not isinstance(name, str) or not name or not isinstance(arguments, dict):
        raise Refused("invalid_request")
    gate = tool_gate(name)
    if gate.plugin != plugin_id or not gate.visible:
        raise Refused("tool_not_available", plugin=plugin_id, transport="plugin")
    policy = get_current_policy()
    if policy is None:
        approved, denial = await confirm_for_chat(name, arguments)
        if not approved:
            return {"result": denial}
    result = await execute_tool(name, arguments, policy=policy)
    return {"result": result}


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
    from core import path_guard
    from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, load_manifest
    from core.plugin_store import PLUGIN_NAME_RE

    base = config_root() / "plugins"
    plugin_dir = next(
        (
            cand
            for cand in (
                path_guard.child(base, plugin_id, pattern=PLUGIN_NAME_RE),
                path_guard.child(BUILTIN_PLUGINS_ROOT, plugin_id, pattern=PLUGIN_NAME_RE),
            )
            if cand is not None and cand.is_dir()
        ),
        None,
    )
    if plugin_dir is None:
        raise HTTPException(status_code=404, detail="unknown plugin")
    manifest, _err = load_manifest(plugin_dir)
    icon_rel = (manifest or {}).get("icon")
    if not isinstance(icon_rel, str) or not icon_rel:
        raise HTTPException(status_code=404, detail="plugin has no icon")
    icon_path = path_guard.confine(plugin_dir / icon_rel, plugin_dir)
    if icon_path is None:
        raise HTTPException(status_code=404, detail="bad icon path")
    if not icon_path.is_file():
        raise HTTPException(status_code=404, detail="icon missing")
    data = icon_path.read_bytes()
    icon_headers = {
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        ),
    }
    if icon_path.suffix.lower() == ".svg":
        import html

        text = html.unescape(data[:64_000].decode("utf-8", "replace")).lower()
        for bad in ("<script", "foreignobject", "javascript:"):
            if bad in text:
                raise HTTPException(status_code=404, detail="unsafe icon")
        if _re.search(r"\bon[a-z]+\s*=", text):
            raise HTTPException(status_code=404, detail="unsafe icon")
        if _re.search(
            r"""(?:href|src|xlink:href)\s*=\s*['"]\s*(?:https?:|data:|javascript:)""",
            text,
        ):
            raise HTTPException(status_code=404, detail="unsafe icon")
        if _re.search(r"""url\(\s*['"]?\s*(?:https?:|data:|javascript:)""", text):
            raise HTTPException(status_code=404, detail="unsafe icon")
        return Response(
            content=data,
            media_type="image/svg+xml",
            headers=icon_headers,
        )
    return Response(
        content=data,
        media_type="image/png",
        headers=icon_headers,
    )
