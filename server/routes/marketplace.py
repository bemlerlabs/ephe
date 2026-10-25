"""Marketplace API: curated catalog, plan, install, update, rollback and remove.

The user surface is curated: there is no route to add, refresh or remove a
source, and the catalog and update views expose only the bundled source. The
source engine stays available for owner-provisioned sources (P4 enterprise).

Every mutation carries the XHR marker. A permission review is a 428 with the
delta, a revoked or incompatible version is a 409, and a failed install never
answers 200.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from core import marketplace_service, marketplace_sources, path_guard
from core.marketplace_planner import ServiceError
from core.marketplace_sources import REPO_ROOT

_ICON_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
#: The fixed sentence a refusal carries beside its code. The client renders the
#: localized sentence from the code; server text never includes an exception,
#: a path or a value from the request.
_REFUSED = "the marketplace refused the request"
#: Plan fields the permission review needs; every other refusal field is dropped,
#: so no exception text can ride a structured payload to the client.
_REVIEW_FIELDS = (
    "delta",
    "permissions",
    "trust",
    "components",
    "local_trust_required",
    "approved_delta",
)


def _compact(body: dict) -> dict:
    return {key: value for key, value in body.items() if value is not None and value != ""}


def _public_plan(plan: dict) -> dict:
    """A plan success payload, field by field. `error` is never read: the service
    dictionaries use it for diagnostics that can name a path or an exception."""
    return _compact(
        {
            "status": plan.get("status"),
            "name": plan.get("name"),
            "version": plan.get("version"),
            "installed_version": plan.get("installed_version"),
            "sha256": plan.get("sha256"),
            "url": plan.get("url"),
            "trust": plan.get("trust"),
            "signature": plan.get("signature"),
            "permissions": plan.get("permissions"),
            "components": plan.get("components"),
            "delta": plan.get("delta"),
            "approved_delta": plan.get("approved_delta"),
            "allow_local_trust": plan.get("allow_local_trust"),
            "source_id": plan.get("source_id"),
            "source_title": plan.get("source_title"),
            "stale": plan.get("stale"),
            "displayName": plan.get("displayName"),
            "description": plan.get("description"),
            "publisher": plan.get("publisher"),
            "categories": plan.get("categories"),
            "icon": plan.get("icon"),
        }
    )


def _public_result(result: dict) -> dict:
    return _compact(
        {
            "status": result.get("status"),
            "name": result.get("name"),
            "version": result.get("version"),
            "trust": result.get("trust"),
            "warning": result.get("warning"),
            "permissions": result.get("permissions"),
            "enabled": result.get("enabled"),
            "activation_error": result.get("activation_error"),
            "lockfile_error": result.get("lockfile_error"),
            "data_removed": result.get("data_removed"),
            "dependents": result.get("dependents"),
            "code": result.get("code"),
        }
    )

_ERROR_STATUS = {
    "unknown_source": 404,
    "unknown_plugin": 404,
    "unknown_version": 404,
    "revoked": 409,
    "incompatible": 409,
    "no_compatible_version": 409,
    "downgrade": 409,
    "source_unavailable": 503,
    "bundled_not_installable": 409,
    "local_trust_required": 428,
    "permission_review": 428,
    "permission_delta": 428,
}


def _mutation_guard(request: Request) -> None:
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
    tags=["marketplace"],
    dependencies=[Depends(_mutation_guard)],
)


def _refusal(status: str, body: dict) -> dict:
    code = str(body.get("code") or status)
    http_status = _ERROR_STATUS.get(code, 409)
    detail = {"code": code, "detail": _REFUSED}
    for key in _REVIEW_FIELDS:
        if key in body:
            detail[key] = body[key]
    raise HTTPException(status_code=http_status, detail=detail)


def _bundled_only(mapping: dict) -> dict:
    return {
        key: value
        for key, value in mapping.items()
        if key == marketplace_sources.BUNDLED_ID
    }


@router.get("/market")
async def market_home() -> dict:
    data = marketplace_sources.load_sources()
    return {
        "sources": [s for s in data["sources"] if s["id"] == marketplace_sources.BUNDLED_ID],
        "last_read": _bundled_only(data["last_read"]),
        "last_error": _bundled_only(data["last_error"]),
    }


@router.get("/market/icon/{name}")
async def market_icon(name: str) -> Response:
    if not _ICON_NAME.match(name):
        raise HTTPException(status_code=404, detail="unknown icon")
    base = Path(REPO_ROOT) / "marketplace" / "icons"
    for suffix, media in ((".svg", "image/svg+xml"), (".png", "image/png"), (".webp", "image/webp")):
        path = path_guard.child(base, name, pattern=_ICON_NAME, suffix=suffix)
        if path is None or not path.is_file():
            continue
        data = path.read_bytes()
        if suffix == ".svg":
            import html

            text = html.unescape(data[:64_000].decode("utf-8", "replace")).lower()
            if any(bad in text for bad in ("<script", "foreignobject", "javascript:")):
                raise HTTPException(status_code=404, detail="unsafe icon")
            if re.search(r"\bon[a-z]+\s*=", text):
                raise HTTPException(status_code=404, detail="unsafe icon")
            if re.search(r"""(?:href|src|xlink:href)\s*=\s*['"]\s*(?:https?:|data:|javascript:)""", text):
                raise HTTPException(status_code=404, detail="unsafe icon")
        return Response(
            content=data,
            media_type=media,
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            },
        )
    raise HTTPException(status_code=404, detail="unknown icon")


@router.get("/market/index")
async def market_index() -> dict:
    entry = marketplace_sources.bundled_source()
    result = marketplace_sources.read_source(entry)
    return {
        "status": result["status"],
        "source": result["source"],
        "index": result.get("index"),
        "error": result.get("error") or "",
    }


@router.get("/market/installed")
async def market_installed() -> dict:
    return marketplace_service.installed()


@router.get("/market/updates")
async def market_updates() -> dict:
    data = marketplace_service.updates()
    bundled = marketplace_sources.BUNDLED_ID
    return {
        "updates": [row for row in data["updates"] if row.get("source_id") == bundled],
        "errors": [row for row in data["errors"] if row.get("source") == bundled],
    }


@router.post("/market/plan")
async def plan_install(body: dict) -> dict:
    try:
        plan = marketplace_service.plan(
            str(body.get("source_id") or ""),
            str(body.get("name") or ""),
            str(body.get("version") or ""),
            approve_permissions=bool(body.get("approve_permissions")),
            allow_local_trust=bool(body.get("allow_local_trust")),
        )
    except ServiceError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"code": exc.code, "detail": _REFUSED},
        ) from exc
    if plan.get("status") == "refused" or plan.get("status") == "permission_review":
        _refusal(str(plan.get("status")), plan)
    return _public_plan(plan)


class MarketSwitchRequest(BaseModel):
    name: str
    enabled: bool
    source_id: str = marketplace_sources.BUNDLED_ID
    version: str = ""
    approve_permissions: bool = False
    allow_local_trust: bool = False


@router.post("/market/switch")
async def market_switch(body: MarketSwitchRequest) -> dict:
    """The one gesture the card offers: on installs-if-needed and activates."""
    result = marketplace_service.switch(
        body.name,
        enabled=body.enabled,
        source_id=body.source_id,
        version=body.version,
        approve_permissions=body.approve_permissions,
        allow_local_trust=body.allow_local_trust,
    )
    status = str(result.get("status") or "")
    if status in {"refused", "permission_review", "permission_delta"}:
        _refusal(status, result)
    if status == "not_installed":
        raise HTTPException(
            status_code=404,
            detail={"code": "not_installed", "detail": _REFUSED},
        )
    if status in {"unknown_plugin", "unknown_source", "unknown_version"}:
        _refusal(status, result)
    out = _public_result(result)
    out["status"] = status
    out["enabled"] = bool(result.get("enabled"))
    if result.get("phase"):
        out["phase"] = result["phase"]
    return out


@router.post("/market/install")
async def install_plan(body: dict) -> dict:
    plan = body.get("plan")
    if not isinstance(plan, dict):
        raise HTTPException(
            status_code=422,
            detail={"code": "plan_required", "detail": "a plan object is required"},
        )
    try:
        result = marketplace_service.install(plan)
    except ServiceError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"code": exc.code, "detail": _REFUSED},
        ) from exc
    if result.get("status") == "refused":
        _refusal("refused", result)
    if result.get("status") != "extracted":
        _refusal(str(result.get("code") or result.get("status") or "install_failed"), result)
    return _public_result(result)


@router.post("/market/rollback")
async def rollback(body: dict) -> dict:
    name = str(body.get("name") or "")
    result = marketplace_service.rollback(name)
    status = result.get("status")
    if status == "no_previous":
        raise HTTPException(
            status_code=404,
            detail={"code": "no_previous", "detail": _REFUSED},
        )
    if status in {"invalid_backup", "rollback_failed"}:
        raise HTTPException(
            status_code=409,
            detail={"code": status, "detail": _REFUSED},
        )
    return _public_result(result)


@router.post("/market/remove")
async def remove_plugin(body: dict) -> dict:
    name = str(body.get("name") or "")
    result = marketplace_service.remove(
        name, delete_data=bool(body.get("delete_data"))
    )
    status = result.get("status")
    if status == "not_installed":
        raise HTTPException(
            status_code=404,
            detail={"code": "not_installed", "detail": _REFUSED},
        )
    if status in {"plugin_enabled", "dependents_enabled"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": status,
                "detail": _REFUSED,
                **{
                    k: v
                    for k, v in result.items()
                    if k in {"dependents"}
                },
            },
        )
    return _public_result(result)
