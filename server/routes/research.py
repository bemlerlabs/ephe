"""Research evidence as data: the list a source card reads, and one explicit run.

``GET /api/research/evidence`` returns what this process still holds for the runs
``web_research`` recorded: source id, URL, title, fetch time, sha256, an excerpt
and the query that produced it, plus workspace lines with their ``path:line``
address. ``POST /api/research/run`` runs the same code path on an explicit call.

The POST is not an auto-run licence. ``web_research`` keeps its NETWORK approval
class and its creator privilege; this route is what a surface or a script calls
when the user asked for the research, and it still goes through ``core.net_guard``
for every hop.

A refusal and a provider failure answer 200 with ``ok: false`` and the tool's own
reason code, because that answer is the tool's result and not a transport error:
the request was understood, the provider or the settings were not there. Both
shapes stay documented in ``docs/WEB_INTAKE.md``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.reason import Reason
from core.tool_markers import RESEARCH_FAILED_MARKER
from core.tools.web_research import run_research
from core.web_intake import policy
from core.web_intake.ledger import (
    default_ledger,
    source_view,
    workspace_view,
)

MAX_QUERY_CHARS = 500
MAX_SCOPE_CHARS = 300


def _mutation_guard(request: Request) -> None:
    """Same-origin mutations carry the XHR marker the app's client always sends."""
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


router = APIRouter(tags=["research"], dependencies=[Depends(_mutation_guard)])


class ResearchRunRequest(BaseModel):
    """The inputs ``web_research`` accepts, plus the optional local scope."""

    query: str = Field(default="", max_length=MAX_QUERY_CHARS)
    site: str = Field(default="", max_length=253)
    max_pages: int = Field(default=policy.DEFAULT_PAGES, ge=1, le=policy.MAX_PAGES)
    depth: int = Field(default=policy.DEFAULT_DEPTH, ge=1, le=policy.MAX_DEPTH)
    freshness: str = Field(default="any", max_length=16)
    workspace_scope: str = Field(default="", max_length=MAX_SCOPE_CHARS)


@router.get("/research/evidence")
async def research_evidence(
    query: str = Query(default="", max_length=MAX_QUERY_CHARS),
    run_id: str = Query(default="", max_length=32),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """The evidence of the runs this process holds, newest run first.

    ``query`` filters on the run's query (a substring, case-insensitive) and
    ``run_id`` names one run. Nothing is read from disk: a restarted server has
    no runs to show, which is the lifespan the ledger states.
    """
    ledger = default_ledger()
    sources = [
        source_view(source, run.query, run.run_id)
        for run, source in ledger.sources(query=query, run_id=run_id, limit=limit)
    ]
    workspace = [
        workspace_view(hit, run.query, run.run_id)
        for run, hit in ledger.workspace_hits(query=query, run_id=run_id, limit=limit)
    ]
    needle = (query or "").strip().casefold()
    runs = [
        run.view()
        for run in ledger.runs()
        if (not run_id or run.run_id == run_id)
        and (not needle or needle in run.query.casefold())
    ]
    return {
        "ok": True,
        "runs": runs,
        "sources": sources,
        "workspace": workspace,
        "total": len(sources) + len(workspace),
    }


@router.post("/research/run")
async def research_run(request: ResearchRunRequest) -> dict:
    """One research run, on the caller's explicit request.

    Every input goes through the tool's own normalization; the answer carries
    ``text`` (the tool's result, formatted the same way) and ``run`` (the same
    evidence as data). A coded refusal keeps its sentence and its next step so a
    client can show the move without parsing the text.
    """
    result = await run_research(
        query=request.query,
        site=request.site,
        max_pages=request.max_pages,
        depth=request.depth,
        freshness=request.freshness,
        workspace_scope=request.workspace_scope,
    )
    refusal = result.text if isinstance(result.text, Reason) else None
    status = "ok"
    if refusal is not None:
        status = (
            "failed" if str(result.text).startswith(RESEARCH_FAILED_MARKER) else "refused"
        )
    return {
        "ok": refusal is None,
        "status": status,
        "reason_code": refusal.code if refusal is not None else "",
        "reason": str(result.text) if refusal is not None else "",
        "next": (refusal.params.get("next", "") if refusal is not None else ""),
        "text": str(result.text),
        "run": result.run.view() if result.run is not None else None,
        "verification": {
            "checked": result.verification.checked,
            "verified": result.verification.verified,
            "issues": list(result.verification.issues),
        },
    }
