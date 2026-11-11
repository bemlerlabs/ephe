"""
◑ Ephe – plugin store and lifecycle routes (wave 5 P3, P1 lifecycle)

GET  /api/plugins                     → aggregated view (catalog + switch state)
GET  /api/plugins/{id}/state          → bytes kept against the bundle ceiling, and the file list
POST /api/plugins/{id}/state/remove   → delete one stored file inside that folder
GET  /api/plugins/{id}/client/storage → one page-sdk value, by key
PUT  /api/plugins/{id}/client/storage → write or clear that key
POST /api/plugins/{id}/client/tool    → run one tool this bundle owns
PUT  /api/plugins/{id}/enabled        → the lifecycle switch, and the mount it owes
POST /api/plugins/{id}/cancel         → cancel a pending activation
POST /api/plugins/{id}/enable         → one-release compatibility shim (same two movements)
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

from core import plugin_lifecycle_types, plugin_runtime, plugin_switch_policy
from core.plugin_lifecycle import (
    STATE_FILENAME,
    LifecycleError,
    PluginLifecycle,
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
                "next": (
                    "Send this request from the Ephe app, or repeat it with the header "
                    "X-Requested-With: XMLHttpRequest."
                ),
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
    """The code, the detail and the move: a switch that refuses still leaves a next call."""
    detail: dict = {
        "code": exc.code,
        "detail": exc.detail,
        "next": plugin_lifecycle_types.next_step_for(exc.code),
    }
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
        detail={
            "code": plugin_switch_policy.READ_ONLY_CODE,
            "detail": "the plugin switch surface is read-only",
            "next": (
                "Turn plugins.plugin_lifecycle_read_only off, then retry the switch."
            ),
        },
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
    # A coded refusal, not a sentence only: the switch surface has to name the
    # reason (drift, a missing record, an untrusted key) in the reader's language.
    raise HTTPException(
        status_code=409,
        detail={
            "code": "signature_denied",
            "detail": f"plugin '{plugin_id}' failed signature check: {reason}",
            "next": plugin_lifecycle_types.next_step_for("signature_denied"),
        },
    )


def _scope_from(body: dict) -> str:
    scope = body.get("scope", "user")
    if scope not in _SCOPES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_request",
                "detail": "scope has to be 'user' or 'workspace'",
                "field": "scope",
                "next": "Send scope as 'user' or 'workspace', then retry the call.",
            },
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
    # The code alone used to be the message; the registry has the sentence and the move.
    raise Refused("plugin_unknown")


@router.get("/plugins/{plugin_id}/state")
def get_plugin_state(plugin_id: str) -> dict:
    """Bytes kept, bytes allowed, and the stored-file names. No host path."""
    from core.plugin_state import report
    from server.refusals import Refused

    _unknown_bundle(plugin_id)
    try:
        return report(plugin_id)
    except ValueError:
        # The bundle is installed but its state folder is not the folder the module
        # proved (a link out of the homes root, `core/plugin_state.py` `state_home`).
        # Nothing about it is addressable, so the answer is the one a name this install
        # does not know already gets.
        raise Refused("plugin_unknown") from None


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
    except ValueError as exc:
        if str(exc) == "plugin":
            raise Refused("plugin_unknown") from None
        raise Refused("plugin_state_name") from None


def _known_bundle(plugin_id: str) -> None:
    from core.plugin_state import is_addressable

    if not is_addressable(plugin_id):
        raise Refused("plugin_unknown")


#: The header a surface call carries its mount credential in. A surface POST has no
#: path segment to borrow the way the mount URL does, so the value travels beside
#: the arguments it is the consent for.
SURFACE_TOKEN_HEADER = "X-Surface-Token"


def _surface_token(request: Request, body: dict) -> str:
    """The mount credential a surface call offers, from the header or the body.

    The body field is the one `POST .../surface-token` reads when it renews, so a
    caller that already holds the value has one shape to build either way. The
    value is only *read* here; `confirm_for_surface` decides whether it is live.
    """
    offered = request.headers.get(SURFACE_TOKEN_HEADER) or ""
    if offered:
        return offered
    value = body.get("surface")
    return value if isinstance(value, str) else ""


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
async def post_plugin_client_tool(plugin_id: str, body: dict, request: Request) -> dict:
    """Run one tool this bundle owns, for a click in that bundle's own surface.

    A surface call has no chat turn behind it, so the gate it meets is the one that
    takes the mount credential as the consent (``confirm_for_surface``). Without a
    live credential for this bundle the answer stays the one this route gave before:
    the call meets the chat gate and is refused where no dialog can open (PE2E).
    """
    from core.plugin_runtime import tool_gate
    from core.tools.chat_gate import confirm_for_surface
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
        approved, denial = await confirm_for_surface(
            name, arguments, plugin=plugin_id, surface=_surface_token(request, body)
        )
        if not approved:
            return {"result": denial}
    try:
        result = await execute_tool(name, arguments, policy=policy)
    except Exception as exc:  # noqa: BLE001 - the boundary answers a code, never the text
        # A traceback names files and internals the page has no use for, so the
        # plugin client receives the coded refusal the rest of this router uses.
        raise Refused("tool_failed", plugin=plugin_id, kind=type(exc).__name__) from None
    return {"result": result}


def _mount_facts(plugin_id: str) -> dict:
    """What the rail holds for this bundle, read from the lifecycle's own record.

    The record is the snapshot a restart replays (`core/plugin_mount_replay.py`), so an
    answer built from it says what survived rather than what one call attempted. A
    bundle that declares no tool has no record: nothing is on the rail, and `names` is
    empty instead of a claim.
    """
    record = plugin_runtime.lifecycle().mount_records().get(plugin_id) or {}
    names = [str(name) for name in record.get("names") or []]
    return {"mounted": bool(names), "names": names}


def _mount_after_enable(
    lifecycle: PluginLifecycle,
    plugin_id: str,
    *,
    before: PluginSnapshot,
    scope: str,
    reason: str,
) -> None:
    """Mount what the switch just promised, and take the switch back if it refuses."""
    try:
        lifecycle.mount(plugin_id, actor="user", reason=reason or "enable mounts")
    except LifecycleError as exc:
        rolled_back = _roll_back_enable(
            lifecycle, plugin_id, before=before, scope=scope, cause=exc
        )
        raise _mount_failed(lifecycle, plugin_id, exc, rolled_back=rolled_back) from exc


def _roll_back_enable(
    lifecycle: PluginLifecycle,
    plugin_id: str,
    *,
    before: PluginSnapshot,
    scope: str,
    cause: LifecycleError,
) -> bool:
    """Return the switch to the position this call found, if this call moved it.

    An enable of a bundle that was already on owns no switch movement, so there is
    nothing to take back: the mount's own rollback restored the descriptor set the last
    accepted mount published, and that set stays served.
    """
    if before.enabled:
        return False
    try:
        lifecycle.set_enabled(
            plugin_id,
            False,
            scope=scope,
            actor="user",
            reason=f"enable rolled back: the mount refused ({cause.code})",
        )
    except LifecycleError:
        return False
    return True


def _mount_failed(
    lifecycle: PluginLifecycle,
    plugin_id: str,
    exc: LifecycleError,
    *,
    rolled_back: bool,
) -> HTTPException:
    """The one answer for "the switch and the mount disagreed", with the mount's reason.

    The status is the mount's own (a moved contract is a 409, a broken manifest a 422),
    because that is the condition the reader has to resolve; `cause` carries the mount's
    code so a card can render the diff or the entry the detail names.
    """
    current = lifecycle.effective(plugin_id)
    if rolled_back:
        because = "the switch was taken back to off; nothing of this bundle is served."
    else:
        because = "the switch was already on; the last accepted tool set stays served."
    detail: dict = {
        "code": "mount_failed",
        "detail": (
            f"the tools of '{plugin_id}' could not be mounted "
            f"({exc.code}: {exc.detail}) — {because}"
        ),
        "next": plugin_lifecycle_types.next_step_for(exc.code),
        "cause": exc.code,
        "rolled_back": rolled_back,
        "current": _state_payload(current),
    }
    # The mount's structured alarm rides beside the code, as it does on the mount route:
    # a moved contract is shown as the fields that moved.
    for name, value in exc.data.items():
        detail.setdefault(str(name), value)
    return HTTPException(status_code=exc.status, detail=detail)


def _unmount_after_disable(
    lifecycle: PluginLifecycle, plugin_id: str, *, reason: str
) -> None:
    """Take the names back with the switch; a cleanup that fails is a coded error.

    The switch is already committed off, so nothing is offered either way — the gate
    withholds every tool of a disabled bundle and the surface answers 404. What failed
    is the record: the mount's own rollback put the descriptor set back, so a retry of
    the same call finishes the cleanup instead of finding a half-removed bundle.
    """
    try:
        lifecycle.unmount(plugin_id, actor="user", reason=reason or "disable unmounts")
    except LifecycleError as exc:
        error = _lifecycle_http_error(exc)
        if isinstance(error.detail, dict):
            error.detail["current"] = _state_payload(lifecycle.effective(plugin_id))
        raise error from exc


def _set_enabled_with_rescan(
    lifecycle,
    plugin_id: str,
    enabled: bool,
    *,
    scope: str,
    expected_version: str | None,
    expected_etag: str | None,
    idempotency_key: str | None,
    reason: str,
):
    """One switch movement, and one rebuild if the manifest view predates the bundle.

    `ephe plugin install` in a terminal while the app is running installs into the same
    folder the server scans, but the process keeps its version map until something
    invalidates it. The answer used to be "not installed" for a bundle the installed list
    was already showing; a bundle whose folder exists is worth one rescan before that is
    said.
    """
    try:
        return lifecycle.set_enabled(
            plugin_id,
            enabled,
            scope=scope,
            expected_version=expected_version,
            expected_etag=expected_etag,
            idempotency_key=idempotency_key,
            actor="user",
            reason=reason,
        )
    except LifecycleError as exc:
        if exc.code != "unknown_plugin":
            raise
        plugin_runtime.invalidate_ownership_cache()
        rebuilt = plugin_runtime.lifecycle()
        return rebuilt.set_enabled(
            plugin_id,
            enabled,
            scope=scope,
            expected_version=expected_version,
            expected_etag=expected_etag,
            idempotency_key=idempotency_key,
            actor="user",
            reason=reason,
        )


def _apply_switch(
    plugin_id: str,
    enabled: bool,
    *,
    scope: str,
    expected_version: str | None,
    expected_etag: str | None,
    idempotency_key: str | None,
    reason: str,
) -> PluginSnapshot:
    """One switch movement and the mount it owes, behind the guards the caller passed.

    A 0.6.4 owner test read `PUT .../enabled {"enabled": true}` as "it works" and got a
    200 with the tool missing from the offer: the switch alone published nothing. So an
    enable mounts and a disable unmounts, in this one call.

    The mount runs after the switch committed, so a refused mount could leave the switch
    on with nothing served. It does not: the mount's own rollback restores every
    artifact it wrote, and `_roll_back_enable` takes the switch back when this call was
    the one that moved it. The 202 path is untouched — an activation that has not
    settled is answered by the event stream, and the mount belongs to the answer that
    settles it.
    """
    lifecycle = plugin_runtime.lifecycle()
    try:
        before = lifecycle.effective(plugin_id)
        snapshot = _set_enabled_with_rescan(
            lifecycle,
            plugin_id,
            enabled,
            scope=scope,
            expected_version=expected_version,
            expected_etag=expected_etag,
            idempotency_key=idempotency_key,
            reason=reason,
        )
    except LifecycleError as exc:
        raise _lifecycle_http_error(exc) from exc
    if snapshot.state in (PluginState.ENABLING, PluginState.DISABLING):
        return snapshot
    if enabled:
        _mount_after_enable(
            lifecycle, plugin_id, before=before, scope=scope, reason=reason
        )
    else:
        _unmount_after_disable(lifecycle, plugin_id, reason=reason)
    return snapshot


@router.put("/plugins/{plugin_id}/enabled")
def put_plugin_enabled(
    plugin_id: str,
    body: dict,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """One endpoint for both directions, and the mount each direction owes."""
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
    snapshot = _apply_switch(
        plugin_id,
        enabled,
        scope=scope,
        expected_version=expected_version,
        expected_etag=if_match,
        idempotency_key=idempotency_key,
        reason=str(body.get("reason") or ""),
    )
    _invalidate_caches()
    response.headers["ETag"] = snapshot.etag
    if snapshot.state in (PluginState.ENABLING, PluginState.DISABLING):
        response.status_code = 202
        return {
            "state": snapshot.state.value,
            "token": snapshot.etag,
            "poll": "/api/plugins/events",
        }
    payload = _state_payload(snapshot)
    payload.update(_mount_facts(plugin_id))
    return payload


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
    """One-release shim: same two movements as `PUT .../enabled`, its own old payload.

    A caller on the old route asked for the same thing the new one did, so it gets the
    same mount (or unmount). Only the answer stays the one the release before this one
    promised: `id`, `enabled`, `saved`.
    """
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
    snapshot = _apply_switch(
        plugin_id,
        enabled,
        scope=scope,
        expected_version=body.get("expected_version"),
        expected_etag=if_match,
        idempotency_key=idempotency_key,
        reason=str(body.get("reason") or "legacy enable route"),
    )
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
