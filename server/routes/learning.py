"""server/routes/learning.py – learning-loop proposals (R31).

GET  /api/learning/proposals               pending candidates
POST /api/learning/proposals/{id}/dismiss  drop one
POST /api/learning/proposals/{id}/accept   build + install via skill_builder
                                           (structural quality gate inside;
                                           422 keeps the proposal retryable)

Finding #18 status (2026-10-08): all three have a live surface — the chat slash
commands /proposals, /accept <id> and /dismiss <id> in
app/src/components/dashboard/chat/model.ts:780, :801 and :815 (wrappers in
app/src/lib/api/endpoints.ts:263-279). None is dead, none is removed. Pinned by
tests/test_learning_loop.py::TestLearningRoutes, including the two answers the
commands depend on: every listed item carries the ``id`` that /accept and
/dismiss feed back, and a skill refused by the gate stays pending so the user can
retry with another model.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.skill_builder import build_skill

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Learning"])


class AcceptRequest(BaseModel):
    model: str


@router.get("/learning/proposals")
async def list_proposals() -> dict:
    from core.learning_loop import ProposalStore

    return {"proposals": ProposalStore().pending()}


def _require_pending(pid: str):
    from core.learning_loop import ProposalStore

    item = ProposalStore().get(pid)
    if item is None or item.get("status") != "pending":
        raise HTTPException(status_code=404, detail="unknown or already handled proposal")
    return item


@router.post("/learning/proposals/{pid}/dismiss")
async def dismiss_proposal(pid: str) -> dict:
    from core.learning_loop import ProposalStore

    _require_pending(pid)
    ProposalStore().dismiss(pid)
    return {"status": "dismissed"}


@router.post("/learning/proposals/{pid}/accept")
async def accept_proposal(pid: str, request: AcceptRequest) -> dict:
    from core.learning_loop import ProposalStore
    from core.skills import SkillLoadError

    item = _require_pending(pid)
    topic = (
        f"{item.get('kind', 'pattern')}: {item.get('topic', '')}\n\n"
        f"Learned from real exchanges with the user (evidence):\n{item.get('evidence', '')}"
    )
    try:
        skill = await build_skill(topic=topic, model=request.model)
    except SkillLoadError as exc:
        # quality gate: a structurally invalid skill is refused, proposal stays retryable
        logger.warning("learning loop: proposal %s failed the skill gate: %s", pid, exc)
        raise HTTPException(status_code=422, detail=f"skill gate: {exc}")
    ProposalStore().accept(pid)
    logger.info("learning loop: installed skill '%s' from proposal %s", skill.name, pid)
    return {"installed": skill.name, "status": "accepted"}
