"""Agent Center — local agent profiles and their run records.

GET    /api/agents                     → default, local and plugin agents
POST   /api/agents                     → create a local agent
GET    /api/agents/{id}                → one agent
PUT    /api/agents/{id}                → update with If-Match
POST   /api/agents/{id}/duplicate      → copy to a local agent
POST   /api/agents/{id}/archive        → archive or restore
POST   /api/agents/{id}/test           → one test prompt through the Subagent path
GET    /api/agents/{id}/runs           → recent content-free run records

A failed write is an HTTP error with a coded body; the editor never reads
"saved" from a 200 alone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from core import agent_store
from core.agent_store import AgentError

_PROMPT_MAX = 4000


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
    tags=["agents"],
    dependencies=[Depends(_mutation_guard)],
)


def _http_error(exc: AgentError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "detail": exc.detail},
    )


class AgentTestRequest(BaseModel):
    prompt: str


class ArchiveRequest(BaseModel):
    archived: bool


@router.get("/agents")
async def list_agents() -> dict:
    return agent_store.list_agents()


@router.get("/agents/tools")
async def list_agent_tools() -> dict:
    """The read-only tools an agent may be granted, with their kernel family."""
    from core.capability_policy import TOOL_FAMILIES
    from core.subagent import SUBAGENT_TOOL_WHITELIST
    from core.tools.registry import TOOL_MAP

    rows = [
        {
            "name": name,
            "families": sorted(TOOL_FAMILIES.get(name, frozenset())),
        }
        for name in sorted(SUBAGENT_TOOL_WHITELIST)
        if name in TOOL_MAP
    ]
    return {"tools": rows}


@router.post("/agents", status_code=201)
async def create_agent(payload: dict) -> dict:
    try:
        return agent_store.create_agent(payload)
    except AgentError as exc:
        raise _http_error(exc) from exc


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    record = agent_store.get_agent(agent_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_agent", "detail": f"unknown agent: {agent_id}"},
        )
    return record


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    payload: dict,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict:
    try:
        return agent_store.update_agent(agent_id, payload, etag=if_match or "")
    except AgentError as exc:
        raise _http_error(exc) from exc


@router.post("/agents/{agent_id}/duplicate", status_code=201)
async def duplicate_agent(agent_id: str) -> dict:
    try:
        return agent_store.duplicate_agent(agent_id)
    except AgentError as exc:
        raise _http_error(exc) from exc


@router.post("/agents/{agent_id}/archive")
async def archive_agent(agent_id: str, body: ArchiveRequest) -> dict:
    try:
        return agent_store.set_archived(agent_id, body.archived)
    except AgentError as exc:
        raise _http_error(exc) from exc


@router.post("/agents/{agent_id}/test")
async def test_agent(agent_id: str, body: AgentTestRequest) -> dict:
    record = agent_store.get_agent(agent_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_agent", "detail": f"unknown agent: {agent_id}"},
        )
    if record.get("read_only") and record.get("origin") != "ephe":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "read_only",
                "detail": "duplicate this plugin agent before testing changes",
            },
        )
    if record.get("archived"):
        raise HTTPException(
            status_code=409,
            detail={"code": "agent_archived", "detail": "restore the agent before a run"},
        )
    if not record.get("enabled", True):
        raise HTTPException(
            status_code=409,
            detail={"code": "agent_disabled", "detail": "enable the agent before a run"},
        )
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_prompt", "detail": "a test prompt is required"},
        )
    if len(prompt) > _PROMPT_MAX:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "prompt_too_long",
                "detail": f"test prompts are capped at {_PROMPT_MAX} characters",
            },
        )
    return await agent_store.run_agent(record, prompt)


@router.get("/agents/{agent_id}/runs")
async def agent_runs(agent_id: str, limit: int = 20) -> dict:
    if agent_store.get_agent(agent_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_agent", "detail": f"unknown agent: {agent_id}"},
        )
    return {"runs": agent_store.list_runs(agent_id, limit=limit)}
