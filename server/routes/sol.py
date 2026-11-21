"""server/routes/sol.py — the workspace's learned rules, readable and editable.

GET    /api/sol/heuristics          the active rules, the map and the switch
PATCH  /api/sol/heuristics/{id}     edit the trigger or the action of one rule
DELETE /api/sol/heuristics/{id}     remove one rule for good

The store is `.ephe/learning/heuristics.md` inside the active workspace; these
routes are a view on that file, not a second copy of it. Delete is the same
delete a hand edit performs, so the settings inspector and the file cannot
disagree.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.sol import consolidator, organizer, session

router = APIRouter(tags=["Learning"])

#: Rule ids are the consolidator's own `H<n>` form. Anything else never reaches
#: the store, so a request cannot name an arbitrary string.
_RULE_ID = re.compile(r"^H\d{1,4}$")

MAX_FIELD_CHARS = 400


class RuleEdit(BaseModel):
    trigger: str | None = None
    action: str | None = None


def _require(rule_id: str) -> str:
    if not _RULE_ID.match(rule_id or ""):
        raise HTTPException(status_code=404, detail="unknown rule")
    return rule_id


@router.get("/sol/heuristics")
async def list_heuristics() -> dict:
    root = organizer.workspace_root()
    rules = [item.as_dict() for item in consolidator.load(root)]
    try:
        learning_map = organizer.ensure_map(root)
    except Exception:
        learning_map = None
    return {
        "workspace": str(root),
        "enabled": session.enabled(),
        "max_active": consolidator.max_active(),
        "heuristics": rules,
        "map": learning_map,
    }


@router.patch("/sol/heuristics/{rule_id}")
async def edit_heuristic(rule_id: str, request: RuleEdit) -> dict:
    _require(rule_id)
    root = organizer.workspace_root()
    trigger = request.trigger.strip()[:MAX_FIELD_CHARS] if request.trigger is not None else None
    action = request.action.strip()[:MAX_FIELD_CHARS] if request.action is not None else None
    if trigger is None and action is None:
        raise HTTPException(status_code=422, detail="nothing to change")
    updated = consolidator.update(rule_id, trigger=trigger, action=action, root=root)
    if updated is None:
        raise HTTPException(status_code=404, detail="unknown rule")
    return {"heuristic": updated.as_dict()}


@router.delete("/sol/heuristics/{rule_id}")
async def delete_heuristic(rule_id: str) -> dict:
    _require(rule_id)
    if not consolidator.delete(rule_id, root=organizer.workspace_root()):
        raise HTTPException(status_code=404, detail="unknown rule")
    return {"status": "deleted", "id": rule_id}
