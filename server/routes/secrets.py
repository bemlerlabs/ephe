"""The secret vault surface: presence, never values.

A page may learn whether a name is set and which store holds it. It may write a
value in. Nothing here returns a value, echoes one in an error, or logs one.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from core import secret_store


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


router = APIRouter(tags=["secrets"], dependencies=[Depends(_mutation_guard)])


@router.get("/secrets/status")
async def secrets_status(names: str = "") -> dict:
    """Presence and storage mode per requested name."""
    wanted = [part.strip() for part in names.split(",") if part.strip()]
    return {"names": secret_store.status(wanted[:64])}


@router.post("/secrets")
async def put_secret(request: Request, body: dict) -> dict:
    name = str(body.get("name") or "")
    value = str(body.get("value") or "")
    try:
        held = secret_store.put(name, value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"code": "secret_refused", "detail": str(exc)}
        ) from exc
    return {"name": name, "present": True, "mode": held}


@router.post("/secrets/remove")
async def remove_secret(request: Request, body: dict) -> dict:
    name = str(body.get("name") or "")
    secret_store.delete(name)
    return {"name": name, "present": False, "mode": ""}

