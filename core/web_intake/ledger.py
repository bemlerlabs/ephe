"""The research runs this process still holds, so a surface can read them.

A run's evidence used to end with the tool call: the text carried the sources
and no second reader could ask for them. This keeps the last runs in memory,
bounded and newest first, and the route in ``server/routes/research.py`` reads
that list. No file is written: a restart forgets the runs, which is the honest
lifespan of evidence gathered for one turn.

Two ids tie an answer to its evidence. ``run_id`` names the run; ``source_id``
names one page and is already stable across re-reads of the same text.
"""
from __future__ import annotations

import hashlib
import threading
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from core.web_intake.evidence import EvidenceSource, EvidenceStore
from core.web_intake.verify import Verification
from core.web_intake.workspace_scope import WorkspaceHit

MAX_RUNS = 32
MAX_SOURCES = 400
MAX_EXCERPT_CHARS = 500

_CURRENT_TURN: ContextVar[str] = ContextVar("ephe_research_turn", default="")


def bind_turn(turn_id: str) -> Token:
    return _CURRENT_TURN.set(str(turn_id or "").strip())


def current_turn() -> str:
    return _CURRENT_TURN.get()


def reset_turn(token: Token) -> None:
    _CURRENT_TURN.reset(token)


@dataclass(frozen=True)
class ResearchClaim:
    """One answer line: copied text plus the address it was copied from."""

    text: str
    source_id: str = ""
    reference: str = ""

    @property
    def kind(self) -> str:
        return "workspace" if self.reference else "web"

    def as_dict(self) -> dict:
        return {"text": self.text, "source_id": self.source_id,
                "reference": self.reference, "kind": self.kind}


@dataclass
class ResearchRun:
    run_id: str
    query: str
    site: str
    started_at: str
    provider: str
    depth: int
    freshness: str
    pages: int
    considered: int
    sources: tuple[EvidenceSource, ...] = ()
    workspace: tuple[WorkspaceHit, ...] = ()
    claims: tuple[ResearchClaim, ...] = ()
    answer: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    verification: Verification = field(default_factory=Verification)
    store: EvidenceStore = field(default_factory=EvidenceStore)
    turn_id: str = ""
    session_id: str = ""

    def view(self) -> dict:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "site": self.site,
            "started_at": self.started_at,
            "provider": self.provider,
            "depth": self.depth,
            "freshness": self.freshness,
            "pages": self.pages,
            "considered": self.considered,
            "sources": len(self.sources),
            "workspace": len(self.workspace),
            "workspace_hits": [hit.as_dict() for hit in self.workspace],
            "claims": [claim.as_dict() for claim in self.claims],
            "answer": list(self.answer),
            "gaps": list(self.gaps),
            "verification": {
                "checked": self.verification.checked,
                "verified": self.verification.verified,
                "issues": list(self.verification.issues),
            },
            "turn_id": self.turn_id,
        }


def new_run_id(query: str) -> str:
    seed = f"{query}\n{time.time_ns()}"
    return "r_" + hashlib.sha256(seed.encode("utf-8", "replace")).hexdigest()[:12]


class EvidenceLedger:
    """Newest runs first; the oldest run leaves once the caps are reached."""

    def __init__(self, max_runs: int = MAX_RUNS, max_sources: int = MAX_SOURCES):
        self._runs: list[ResearchRun] = []
        self._max_runs = max(1, int(max_runs))
        self._max_sources = max(1, int(max_sources))
        self._lock = threading.Lock()

    def record(
        self,
        *,
        query: str,
        site: str = "",
        provider: str = "",
        depth: int = 1,
        freshness: str = "",
        pages: int = 0,
        considered: int = 0,
        sources: list[EvidenceSource] | None = None,
        workspace: list[WorkspaceHit] | None = None,
        claims: list[ResearchClaim] | None = None,
        answer: list[str] | None = None,
        gaps: list[str] | None = None,
        verification: Verification | None = None,
        store: EvidenceStore | None = None,
        turn_id: str = "",
        session_id: str = "",
    ) -> ResearchRun:
        run = ResearchRun(
            run_id=new_run_id(query),
            query=str(query or ""),
            site=str(site or ""),
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            provider=str(provider or ""),
            depth=max(1, int(depth)),
            freshness=str(freshness or ""),
            pages=max(0, int(pages)),
            considered=max(0, int(considered)),
            sources=tuple(sources or ()),
            workspace=tuple(workspace or ()),
            claims=tuple(claims or ()),
            answer=tuple(answer or ()),
            gaps=tuple(gaps or ()),
            verification=verification or Verification(),
            store=store or EvidenceStore(),
            turn_id=str(turn_id or ""),
            session_id=str(session_id or ""),
        )
        with self._lock:
            self._runs.insert(0, run)
            self._trim()
        return run

    def _trim(self) -> None:
        del self._runs[self._max_runs:]
        while len(self._runs) > 1 and sum(
            len(one.sources) for one in self._runs
        ) > self._max_sources:
            self._runs.pop()

    def runs(self) -> list[ResearchRun]:
        with self._lock:
            return list(self._runs)

    def latest_for_turn(self, turn_id: str) -> ResearchRun | None:
        wanted = str(turn_id or "").strip()
        if not wanted:
            return None
        with self._lock:
            for run in self._runs:
                if run.turn_id == wanted:
                    return run
        return None

    def sources(
        self, *, query: str = "", run_id: str = "", limit: int = 40
    ) -> list[tuple[ResearchRun, EvidenceSource]]:
        needle = (query or "").strip().casefold()
        out: list[tuple[ResearchRun, EvidenceSource]] = []
        for run in self.runs():
            if run_id and run.run_id != run_id:
                continue
            if needle and needle not in run.query.casefold():
                continue
            for source in run.sources:
                out.append((run, source))
                if len(out) >= max(1, min(limit, self._max_sources)):
                    return out
        return out

    def workspace_hits(
        self, *, query: str = "", run_id: str = "", limit: int = 40
    ) -> list[tuple[ResearchRun, WorkspaceHit]]:
        needle = (query or "").strip().casefold()
        out: list[tuple[ResearchRun, WorkspaceHit]] = []
        for run in self.runs():
            if run_id and run.run_id != run_id:
                continue
            if needle and needle not in run.query.casefold():
                continue
            for hit in run.workspace:
                out.append((run, hit))
                if len(out) >= max(1, min(limit, self._max_sources)):
                    return out
        return out

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


_LEDGER = EvidenceLedger()


def default_ledger() -> EvidenceLedger:
    return _LEDGER


def note_run(**kwargs) -> ResearchRun:
    """The one call the tool makes; the contextvars decide which turn owns it."""
    from core.tools.session_ctx import get_current_session

    kwargs.setdefault("turn_id", current_turn())
    kwargs.setdefault("session_id", get_current_session())
    return _LEDGER.record(**kwargs)


def source_view(source: EvidenceSource, query: str, run_id: str) -> dict:
    excerpt = " ".join((source.extract or "").split())
    if len(excerpt) > MAX_EXCERPT_CHARS:
        excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + " [...]"
    return {
        "source_id": source.source_id,
        "url": source.url,
        "title": source.title,
        "fetched_at": source.fetched_at,
        "sha256": source.sha256,
        "excerpt": excerpt,
        "query": query,
        "run_id": run_id,
    }


def workspace_view(hit: WorkspaceHit, query: str, run_id: str) -> dict:
    return {
        "path": hit.path,
        "line": hit.line,
        "reference": hit.reference,
        "text": hit.text,
        "query": query,
        "run_id": run_id,
    }
