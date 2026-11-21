"""Agent Teams — team profiles, templates and local runs.

GET    /api/agent-teams                    → current and archived teams
GET    /api/agent-teams/templates          → template catalog
POST   /api/agent-teams                    → create (optionally from a template)
GET    /api/agent-teams/{id}
PUT    /api/agent-teams/{id}               → update with If-Match
POST   /api/agent-teams/{id}/archive
POST   /api/agent-teams/{id}/run           → one local run
GET    /api/agent-teams/{id}/runs
GET    /api/agent-teams/runs/{run_id}      → status or finished result
POST   /api/agent-teams/runs/{run_id}/cancel
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from core import agent_teams
from core.agent_teams import TeamError

_TASK_MAX = 8000


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
    tags=["agent-teams"],
    dependencies=[Depends(_mutation_guard)],
)


def _http_error(exc: TeamError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "detail": exc.detail},
    )


class ArchiveRequest(BaseModel):
    archived: bool


class TeamRunRequest(BaseModel):
    task: str
    model: str | None = None
    run_id: str | None = None


@router.get("/agent-teams")
async def list_teams() -> dict:
    return agent_teams.list_teams()


@router.get("/agent-teams/templates")
async def list_templates() -> dict:
    return {"templates": agent_teams.template_names()}


@router.post("/agent-teams", status_code=201)
async def create_team(payload: dict) -> dict:
    try:
        return agent_teams.create_team(payload)
    except TeamError as exc:
        raise _http_error(exc) from exc


@router.get("/agent-teams/{team_id}")
async def get_team(team_id: str) -> dict:
    team = agent_teams.get_team(team_id)
    if team is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_team", "detail": f"unknown team: {team_id}"},
        )
    return team


@router.put("/agent-teams/{team_id}")
async def update_team(
    team_id: str,
    payload: dict,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict:
    try:
        return agent_teams.update_team(team_id, payload, etag=if_match or "")
    except TeamError as exc:
        raise _http_error(exc) from exc


@router.post("/agent-teams/{team_id}/archive")
async def archive_team(team_id: str, body: ArchiveRequest) -> dict:
    try:
        return agent_teams.set_archived(team_id, body.archived)
    except TeamError as exc:
        raise _http_error(exc) from exc


@router.post("/agent-teams/{team_id}/run")
async def run_team(team_id: str, body: TeamRunRequest) -> dict:
    team = agent_teams.get_team(team_id)
    if team is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_team", "detail": f"unknown team: {team_id}"},
        )
    if team.get("archived"):
        raise HTTPException(
            status_code=409,
            detail={"code": "team_archived", "detail": "restore the team before a run"},
        )
    task = (body.task or "").strip()
    if not task:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_task", "detail": "a team run needs a task"},
        )
    if len(task) > _TASK_MAX:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "task_too_long",
                "detail": f"team tasks are capped at {_TASK_MAX} characters",
            },
        )
    return await agent_teams.run_team(team, task, model=body.model, run_id=body.run_id)


@router.get("/agent-teams/{team_id}/runs")
async def team_runs(team_id: str, limit: int = 20) -> dict:
    if agent_teams.get_team(team_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_team", "detail": f"unknown team: {team_id}"},
        )
    return {"runs": agent_teams.list_runs(team_id, limit=limit)}


@router.get("/agent-teams/runs/{run_id}")
async def team_run_state(run_id: str) -> dict:
    state = agent_teams.run_state(run_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_run", "detail": f"unknown run: {run_id}"},
        )
    return state


@router.post("/agent-teams/runs/{run_id}/cancel")
async def cancel_team_run(run_id: str) -> dict:
    state = agent_teams.cancel_run(run_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_run", "detail": f"unknown run: {run_id}"},
        )
    return state
