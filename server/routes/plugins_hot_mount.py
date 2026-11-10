"""
◑ Ephe – the hot-mount routes: put a bundle's tools on the rail, take them off

POST   /api/plugins/{id}/hot-mount   → mount the tools one bundle declares
DELETE /api/plugins/{id}/hot-mount   → remove exactly that bundle's names

Both verbs drive the one transition #15 built, so nothing here decides what a mount
means. The route answers three questions and delegates the rest.

`expected_version` and `If-Match` are the same guard on this resource: the bundle version
is the whole identity of what would be published, and the transition compares it against
the manifest it read, under the lifecycle lock, before anything is written. Two writers
that both believe they are mounting 0.1.0 get one mount and one `stale_state`.

A mount publishes code the model can call, so it passes the signature gate that switching
a plugin on passes. The atomic 0600 writes and the audit rows are the transition's, and
the notification a surface waits for is the one the mount already pushes over
`GET /api/plugins/events` — this file adds no second stream and no second record.

The alarm a changed contract raises travels as data: a 409 from the pin check
carries `diff`, one entry per served name with both fingerprints and the fields that
moved, because a reader who has to approve a change is shown the change itself.

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from core import plugin_runtime
from core.plugin_lifecycle import LifecycleError

from server.routes.plugins import (
    _invalidate_caches,
    _lifecycle_http_error,
    _mutation_guard,
    _read_only_guard,
    _signature_gate,
)

router = APIRouter(
    tags=["plugins"],
    dependencies=[Depends(_mutation_guard)],
)


def _mount_http_error(exc: LifecycleError) -> HTTPException:
    """The lifecycle's own answer, plus the structured diff a card has to render."""
    error = _lifecycle_http_error(exc)
    if isinstance(error.detail, dict) and exc.data:
        error.detail.update(exc.data)
    return error


def _body_text(body: dict, field: str) -> str:
    value = body.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise HTTPException(
            status_code=400, detail={"code": "invalid_request", "field": field}
        )
    return value


def _acknowledge(body: dict) -> list[str]:
    """The names whose changed contract the caller has already seen and accepted."""
    value = body.get("acknowledge", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(
            status_code=400, detail={"code": "invalid_request", "field": "acknowledge"}
        )
    return [str(item) for item in value]


@router.post("/plugins/{plugin_id}/hot-mount")
def post_plugin_hot_mount(
    plugin_id: str,
    body: dict,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict:
    """Mount one bundle's declared tools, or refuse with the reason the transition found."""
    _read_only_guard("mount", plugin_id)
    _signature_gate(plugin_id)
    expected_version = _body_text(body, "expected_version") or None
    accepted_change = body.get("acknowledge_artifact", False)
    if not isinstance(accepted_change, bool):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "field": "acknowledge_artifact"},
        )
    try:
        result = plugin_runtime.lifecycle().mount(
            plugin_id,
            acknowledge=_acknowledge(body),
            acknowledge_artifact=accepted_change,
            expected_version=expected_version,
            expected_etag=if_match,
            actor="user",
            reason=_body_text(body, "reason"),
        )
    except LifecycleError as exc:
        raise _mount_http_error(exc) from exc
    _invalidate_caches()
    if result.version:
        response.headers["ETag"] = result.version
    return result.as_dict()


@router.post("/plugins/{plugin_id}/reload")
def post_plugin_reload(plugin_id: str, body: dict | None = None) -> dict:
    """Re-enter the mount after the bundle's file changed.

    The same transition a user-facing mount runs, with nothing acknowledged on the
    caller's behalf: a moved tool contract is the pin refusal, an unreadable
    manifest is the manifest refusal, and in both cases the descriptors the last
    accepted mount published stay served. This is the one caller of
    `core.plugin_hot_reload.reload_bundle`, which the Creator loop and the reload
    gesture in the shell both intend.
    """
    from core.plugin_hot_reload import reload_bundle

    _read_only_guard("reload", plugin_id)
    _signature_gate(plugin_id)
    try:
        result = reload_bundle(plugin_id)
    except LifecycleError as exc:
        raise _mount_http_error(exc) from exc
    _invalidate_caches()
    return result.as_dict()


@router.delete("/plugins/{plugin_id}/hot-mount")
def delete_plugin_hot_mount(plugin_id: str, reason: str = "") -> dict:
    """Remove exactly this bundle's names; a call for one that just left is a coded refusal."""
    _read_only_guard("unmount", plugin_id)
    try:
        result = plugin_runtime.lifecycle().unmount(
            plugin_id, actor="user", reason=reason
        )
    except LifecycleError as exc:
        raise _mount_http_error(exc) from exc
    _invalidate_caches()
    return result.as_dict()
