"""One leader plans, members run, one report returns.

The leader plans when the mode asks for it and always writes the final summary.
Members run through the same ``Subagent`` primitive as chat delegation, with
their own model, tool set and budget. A run is cancellable between member calls
and stops at its wall-clock or member-call budget.
"""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from core import agent_store
from core.agent_team_ledger import record_run
from core.agent_team_schema import REPORT_MAX_CHARS, RUNS_KEEP, TeamError

logger = logging.getLogger(__name__)


@dataclass
class TeamRunState:
    run_id: str
    team_id: str
    status: str = "running"
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task] = field(default_factory=list)
    result: dict[str, Any] | None = None


_RUNS: dict[str, TeamRunState] = {}


def _member_model(record: dict[str, Any], team: dict[str, Any], override: str | None) -> str | None:
    if override:
        return override
    policy = team.get("model_policy") or "inherit"
    if policy == "team":
        return (team.get("model") or {}).get("model")
    if policy == "per_member":
        return (record.get("model") or {}).get("model")
    return None


def _member_timeout(record: dict[str, Any]) -> float:
    return float(record["limits"]["timeout"])


def _member_turns(record: dict[str, Any]) -> int:
    return int(record["limits"]["max_turns"])


async def _run_one(
    *,
    record: dict[str, Any],
    task: str,
    context: str,
    model: str | None,
    run_id: str,
    index: int,
) -> dict[str, Any]:
    from core.subagent import Subagent

    started = time.perf_counter()
    helper = Subagent(
        agent_id=f"{run_id}-m{index}",
        role=str(record["name"]),
        task=task,
        model=model,
        context=context,
        instructions=str(record.get("instructions") or ""),
        allowed_tools=agent_store.effective_tools(record),
        timeout=_member_timeout(record),
        max_iterations=_member_turns(record),
    )
    result = await helper.run()
    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        agent_store.record_run(
            run_id=helper.agent_id,
            agent_id=str(record["id"]),
            agent_name=str(record["name"]),
            model=model,
            model_source="team" if model else "global",
            source="team",
            status=result.status,
            duration_ms=duration_ms,
            tool_calls=len(result.tool_calls),
            prompt_chars=len(task),
            report_chars=len(result.report),
        )
    except Exception:
        logger.exception("agent run ledger write failed")
    return {
        "agent_id": record["id"],
        "name": record["name"],
        "model": model or "",
        "model_source": "team" if model else "global",
        "status": result.status,
        "duration_ms": duration_ms,
        "report": str(result.report)[:REPORT_MAX_CHARS],
        "tool_calls": len(result.tool_calls),
    }


async def _leader_call(
    *,
    record: dict[str, Any],
    task: str,
    context: str,
    model: str | None,
    run_id: str,
    index: int = 99,
) -> dict[str, Any]:
    return await _run_one(
        record=record,
        task=task,
        context=context,
        model=model,
        run_id=run_id,
        index=index,
    )


def _member_task(task: str, prior: list[dict[str, Any]], mode: str) -> str:
    if not prior:
        return task
    seen = "\n\n".join(
        f"[{item['name']}]\n{item['report']}" for item in prior
    )
    if mode == "review":
        return f"{task}\n\nReview the work so far:\n{seen}"
    return f"{task}\n\nEarlier team results:\n{seen}"


def _context(team: dict[str, Any], task: str) -> str:
    shared = team.get("shared_context") or {}
    parts = [str(team.get("instructions") or ""), f"Team task: {task}"]
    if shared.get("workspace", True):
        parts.append("The workspace files are readable through your read-only tools.")
    if shared.get("memory", True):
        parts.append("Ephe memory tools are not part of the read-only helper set.")
    return "\n".join(part for part in parts if part)


async def _run_members(
    team: dict[str, Any],
    agents: dict[str, dict[str, Any]],
    task: str,
    state: TeamRunState,
    *,
    model_override: str | None,
    plan: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    mode = str(team.get("orchestration") or "parallel")
    rounds = int(team["budget"]["max_rounds"])
    members = [agents[agent_id] for agent_id in team["member_ids"]]
    context = _context(team, task)
    if plan:
        context = f"{context}\n\nLeader plan:\n{plan}"
    results: list[dict[str, Any]] = []
    budget_hit = False

    for index, record in enumerate(members):
        if state.cancel.is_set():
            break
        if index >= rounds:
            budget_hit = True
            break
        model = _member_model(record, team, model_override)
        if mode in ("sequential", "review"):
            result = await _run_one(
                record=record,
                task=_member_task(task, results, mode),
                context=context,
                model=model,
                run_id=state.run_id,
                index=index,
            )
            results.append(result)
    if mode in ("parallel", "leader"):
        allowed = min(len(members), rounds)
        budget_hit = allowed < len(members)
        if state.cancel.is_set():
            return results, budget_hit
        tasks = []
        for index, record in enumerate(members[:allowed]):
            model = _member_model(record, team, model_override)
            tasks.append(
                asyncio.create_task(
                    _run_one(
                        record=record,
                        task=task,
                        context=context,
                        model=model,
                        run_id=state.run_id,
                        index=index,
                    )
                )
            )
        state.tasks.extend(tasks)
        try:
            results = list(await asyncio.gather(*tasks))
        except asyncio.CancelledError:
            for item in tasks:
                item.cancel()
            raise
    return results, budget_hit


def _summary_task(team: dict[str, Any], task: str, results: list[dict[str, Any]]) -> str:
    body = "\n\n".join(
        f"[{item['name']}] status={item['status']}\n{item['report']}" for item in results
    )
    return (
        f"{task}\n\nTeam results:\n{body}\n\n"
        "Write the final answer. Name the members you are relying on and any "
        "member that failed. Do not repeat raw member reports."
    )


async def run_team(
    team: dict[str, Any],
    task: str,
    *,
    model: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    if run_id is None:
        run_id = f"team-{secrets.token_hex(4)}"
    elif not re.match(r"^team-[A-Za-z0-9-]{4,48}$", run_id) or run_id in _RUNS:
        raise TeamError("invalid_run_id", "a run id must be team- followed by 4-48 safe characters", 400)
    state = TeamRunState(run_id=run_id, team_id=str(team["id"]))
    _RUNS[run_id] = state
    while len(_RUNS) > RUNS_KEEP:
        _RUNS.pop(next(iter(_RUNS)))
    started = time.perf_counter()
    leader = agent_store.get_agent(str(team["leader_id"]))
    agents: dict[str, dict[str, Any]] = {}
    for agent_id in [team["leader_id"], *team["member_ids"]]:
        record = agent_store.get_agent(str(agent_id))
        if record is None:
            state.status = "error"
            return {
                "run_id": run_id,
                "team_id": team["id"],
                "status": "error",
                "report": f"[team error: unknown agent {agent_id}]",
                "members": [],
                "budget_hit": False,
                "duration_ms": 0,
            }
        if record.get("archived") or not record.get("enabled", True):
            state.status = "error"
            return {
                "run_id": run_id,
                "team_id": team["id"],
                "status": "error",
                "report": f"[team error: agent '{record['name']}' is not available]",
                "members": [],
                "budget_hit": False,
                "duration_ms": 0,
            }
        agents[str(agent_id)] = record
    wall = int(team["budget"]["wall_timeout"])
    leader_model = _member_model(leader, team, model)
    context = _context(team, task)
    budget_hit = False
    results: list[dict[str, Any]] = []
    report = ""
    status = "ok"
    plan = ""
    try:
        async def _execute() -> str:
            nonlocal budget_hit, results, plan
            plan = ""
            if team.get("orchestration") == "leader" and not state.cancel.is_set():
                planned = await _leader_call(
                    record=leader,
                    task=(
                        f"{task}\n\nPlan the team's work in at most 120 words. "
                        "Name what each member should contribute, then stop. "
                        "Do not answer the task yet."
                    ),
                    context=context,
                    model=leader_model,
                    run_id=run_id,
                    index=98,
                )
                plan = str(planned["report"])
            results, budget_hit = await _run_members(
                team, agents, task, state, model_override=model, plan=plan
            )
            if state.cancel.is_set():
                return "[team cancelled before the summary]"
            summary = await _leader_call(
                record=leader,
                task=_summary_task(team, task, results),
                context=context,
                model=leader_model,
                run_id=run_id,
            )
            results = [*results, summary]
            for item in results[:-1]:
                item["role"] = "member"
            summary["role"] = "leader"
            return str(summary["report"])

        report = await asyncio.wait_for(_execute(), timeout=wall)
        if state.cancel.is_set():
            status = "cancelled"
        elif budget_hit:
            status = "budget"
    except TimeoutError:
        status = "budget"
        report = f"[team stopped at its {wall}s wall-clock budget]"
        budget_hit = True
    except asyncio.CancelledError:
        status = "cancelled"
        report = "[team cancelled]"
    except Exception as exc:  # noqa: BLE001 — the run record reports the failure
        status = "error"
        report = f"[team error: {exc}]"
    duration_ms = int((time.perf_counter() - started) * 1000)
    state.status = status
    result = {
        "run_id": run_id,
        "team_id": team["id"],
        "status": status,
        "report": report,
        "members": results,
        "budget_hit": budget_hit,
        "duration_ms": duration_ms,
        "orchestration": team.get("orchestration"),
        "model_policy": team.get("model_policy"),
        "plan": plan,
    }
    state.result = result
    record_run(result)
    try:
        from core.audit_log import audit_event

        audit_event(
            "agent_team",
            tool=str(team["id"]),
            decision="run",
            detail=f"run={run_id} status={status} members={len(results)}",
        )
    except Exception:
        logger.exception("agent team audit write failed")
    return result


def run_state(run_id: str) -> dict[str, Any] | None:
    state = _RUNS.get(run_id)
    if state is None:
        return None
    return state.result or {
        "run_id": state.run_id,
        "team_id": state.team_id,
        "status": state.status,
        "report": "",
        "members": [],
    }


def cancel_run(run_id: str) -> dict[str, Any] | None:
    state = _RUNS.get(run_id)
    if state is None:
        return None
    if state.status != "running":
        return state.result
    state.cancel.set()
    for task in state.tasks:
        if not task.done():
            task.cancel()
    return {"run_id": run_id, "team_id": state.team_id, "status": "cancelling"}
