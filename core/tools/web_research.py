"""web_research — one question, several pages, an answer that carries its sources.

The tool makes no model call. Its answer is extractive: every sentence is copied
from the page or the workspace line it names, and ``core.web_intake.verify``
checks the copy against the stored text before the result is returned. A model
paraphrases from the evidence afterwards; the compiled answer is the part it can
cite without inventing a source.

``workspace_scope`` mixes local evidence into the same answer. A file line keeps
its ``path:line`` address, a page keeps its ``s_…`` id, and one citation check
covers both.

The first cut is a tool, not a surface. It is off until the user configures a
search provider, and it answers with the settings to add rather than searching
and failing quietly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.reason import Reason, reason
from core.tool_markers import RESEARCH_FAILED_MARKER, RESEARCH_REFUSED_MARKER
from core.web_intake import ledger as research_ledger
from core.web_intake import policy
from core.web_intake.crawl import CrawlPage, crawl
from core.web_intake.evidence import EvidenceSource, EvidenceStore
from core.web_intake.search import (
    NEXT_STEP,
    SearchConfig,
    SearchNotConfigured,
    SearchUnavailable,
    search,
)
from core.web_intake.verify import (
    Verification,
    sentences,
    verify_claims,
)
from core.web_intake.workspace_scope import (
    MAX_CLAIM_CHARS,
    WorkspaceHit,
    search_workspace,
)

WEB_RESEARCH_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_research",
            "description": (
                "Researches one question on the open web with several pages and "
                "returns an extractive answer whose every sentence names the source "
                "id it was copied from, followed by the evidence and the pages that "
                "were refused. Needs a configured search provider; without one it "
                "answers with a coded refusal naming the settings to add. With "
                "'workspace_scope' the answer also carries lines from this workspace, "
                "each under its path:line address."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or topic to research.",
                    },
                    "site": {
                        "type": "string",
                        "description": (
                            "Restrict every page to this host and its subdomains, "
                            "e.g. 'docs.python.org'."
                        ),
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "Maximum pages to read (1-8, default 4).",
                    },
                    "depth": {
                        "type": "integer",
                        "description": (
                            "1 reads the search hits only; 2 also follows same-site "
                            "links found on them (1-2, default 1)."
                        ),
                    },
                    "freshness": {
                        "type": "string",
                        "enum": ["any", "day", "week", "month", "year"],
                        "description": (
                            "How recent the search should be; also the window in "
                            "which a cached page is reused without a request."
                        ),
                    },
                    "workspace_scope": {
                        "type": "string",
                        "description": (
                            "Optional workspace subtree or symbol to mix into the "
                            "answer. A path prefix keeps files below it; a bare word "
                            "keeps lines carrying it. Each local claim names path:line."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
]

_MAX_CLAIMS = 5
_EXCERPT_CHARS = 500
_MAX_GAPS_SHOWN = 8
_STOP_TERMS = frozenset(
    "about after also been does from have into just like more most only other over "
    "same some such than that their them then there these they this those very was "
    "were what when where which while will with would your".split()
)
_FAKE_CITATION = re.compile(r"\[s_[0-9a-f]{12}\]")
#: Page text cannot mint a workspace reference either; the pattern is the one
#: `verify.WORKSPACE_CITATION` resolves, stripped before the real one is appended.
_FAKE_WORKSPACE = re.compile(
    r"\[[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|ts|tsx|js|jsx|md|json|toml|css|html|yml|yaml):\d+\]"
)


@dataclass
class ResearchResult:
    """The tool's text plus the run a surface can read as data.

    ``run`` is None for a refusal, a failed provider and a run that read nothing:
    there is no evidence to publish, so no entry enters the ledger.
    """

    text: str
    run: research_ledger.ResearchRun | None = None
    verification: Verification = field(default_factory=Verification)


def _refusal(code: str, detail: str, next_step: str, **params: str) -> Reason:
    return reason(
        code,
        f"{RESEARCH_REFUSED_MARKER} {detail} Next: {next_step}.",
        next=next_step,
        **params,
    )


def _failed(code: str, detail: str, **params: str) -> Reason:
    return Reason(f"{RESEARCH_FAILED_MARKER} {detail}", code, params)


def _terms(query: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]{3,}", query.casefold())
        if word not in _STOP_TERMS
    ]


def _clean(sentence: str) -> str:
    """Page text cannot mint a source: both citation shapes are removed first."""
    return _FAKE_WORKSPACE.sub("", _FAKE_CITATION.sub("", sentence)).strip()


def _select_claims(
    pages: list[CrawlPage],
    terms: list[str],
    sources: dict[str, EvidenceSource],
    limit: int = _MAX_CLAIMS,
) -> tuple[list[tuple[str, EvidenceSource]], bool]:
    """Sentences that carry the most query terms, copied verbatim, one per page first."""
    scored: list[tuple[int, int, str, EvidenceSource]] = []
    seen: set[str] = set()
    for page in pages:
        source = sources.get(page.url)
        if source is None:
            continue
        page_hits = 0
        for sentence in sentences(page.text):
            sentence = _clean(sentence)
            if not 30 <= len(sentence) <= 400:
                continue
            key = sentence.casefold()
            if key in seen:
                continue
            seen.add(key)
            score = sum(1 for term in terms if term in sentence.casefold())
            scored.append((score, -page_hits, sentence, source))
            if score:
                page_hits += 1
    matched = [item for item in scored if item[0] > 0]
    ranked = sorted(matched or scored, key=lambda item: (item[1], item[0]), reverse=True)
    claims: list[tuple[str, EvidenceSource]] = []
    for score, _spread, sentence, source in ranked:
        if len(claims) >= limit:
            break
        if not score and matched:
            continue
        if any(sentence == chosen for chosen, _source in claims):
            continue
        claims.append((sentence, source))
    return claims, bool(matched)


def _workspace_claims(hits: list[WorkspaceHit], limit: int) -> list[WorkspaceHit]:
    claims: list[WorkspaceHit] = []
    seen: set[str] = set()
    for hit in hits:
        text = _clean(hit.text)
        if not 30 <= len(text) <= MAX_CLAIM_CHARS:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        claims.append(WorkspaceHit(path=hit.path, line=hit.line, text=text))
        if len(claims) >= limit:
            break
    return claims


def _format_source(source: EvidenceSource) -> str:
    excerpt = _clean(re.sub(r"\s+", " ", source.extract))
    if len(excerpt) > _EXCERPT_CHARS:
        excerpt = excerpt[:_EXCERPT_CHARS].rstrip() + " [...]"
    return (
        f"[{source.source_id}] {source.title}\n"
        f"    URL: {source.url}\n"
        f"    Fetched: {source.fetched_at} · sha256: {source.short_sha} · "
        f"{source.content_type or 'unknown type'}\n"
        f"    Excerpt: {excerpt}"
    )


def _format_workspace(hit: WorkspaceHit) -> str:
    return f"[{hit.reference}] {hit.text}"


def _gaps_text(gaps: list[str]) -> str:
    if not gaps:
        return ""
    lines = gaps[:_MAX_GAPS_SHOWN]
    if len(gaps) > _MAX_GAPS_SHOWN:
        lines.append(f"… and {len(gaps) - _MAX_GAPS_SHOWN} more")
    return "Gaps\n" + "\n".join(f"- {line}" for line in lines)


def _merge(report: Verification, part: Verification) -> None:
    report.checked += part.checked
    report.verified += part.verified
    report.issues.extend(part.issues)
    report.rejected.extend(part.rejected)


async def run_research(
    query: str = "",
    site: str = "",
    max_pages: int = policy.DEFAULT_PAGES,
    depth: int = policy.DEFAULT_DEPTH,
    freshness: str = "any",
    workspace_scope: str = "",
    workspace_root: str | Path | None = None,
) -> ResearchResult:
    """One research run as text plus data; ``web_research`` returns the text only."""
    query = (query or "").strip()
    if not query:
        return ResearchResult(
            text=_refusal(
                "web_query_empty",
                "The query is empty, so no page was requested.",
                "pass the question in 'query'",
            )
        )
    try:
        window = policy.normalize_freshness(freshness)
    except ValueError:
        return ResearchResult(
            text=_refusal(
                "web_freshness_unknown",
                f"'{freshness}' is not a freshness the crawler knows.",
                "use any, day, week, month or year",
            )
        )
    pages_limit, levels = policy.normalize_limits(max_pages, depth)

    config = SearchConfig.from_environment()
    if not config.configured:
        return ResearchResult(
            text=_refusal(
                "web_search_not_configured",
                "No search provider is configured, so no page was requested.",
                NEXT_STEP,
            )
        )

    site_host = policy.site_host(site)
    if site_host:
        reachable, why = policy.link_reach(f"https://{site_host}")
        if not reachable:
            return ResearchResult(
                text=_refusal(
                    "web_site_outside_reach",
                    f"The site restriction '{site_host}' is out of reach: {why}.",
                    "name a public host, or drop 'site'",
                    site=site_host,
                )
            )

    try:
        hits = await search(
            config,
            query,
            limit=min(20, max(5, pages_limit * 4)),
            freshness=window,
        )
    except SearchNotConfigured:
        return ResearchResult(
            text=_refusal(
                "web_search_not_configured",
                "No search provider is configured, so no page was requested.",
                NEXT_STEP,
            )
        )
    except SearchUnavailable as exc:
        return ResearchResult(
            text=_failed("web_search_failed", f"Search failed: {exc.detail}.")
        )

    seeds: list[str] = []
    gaps: list[str] = []
    if not hits:
        gaps.append(
            "the provider answered with no results; rephrase the query or name a site"
        )

    for hit in hits:
        if site_host and not policy.in_site(hit.url, site_host):
            gaps.append(f"{hit.url}: outside the site restriction")
            continue
        reachable, why = policy.link_reach(hit.url)
        if not reachable:
            gaps.append(f"{hit.url}: {why}")
            continue
        if hit.url not in seeds:
            seeds.append(hit.url)

    run = await crawl(
        seeds,
        max_pages=pages_limit,
        depth=levels,
        freshness=window,
        site=site_host,
        timeout=policy.REQUEST_TIMEOUT_SECONDS,
    )
    gaps.extend(f"{gap.url}: {gap.reason}" for gap in run.gaps)

    store = EvidenceStore()
    by_url: dict[str, EvidenceSource] = {}
    for page in run.pages:
        source = store.add(
            url=page.url,
            title=page.title,
            fetched_at=page.fetched_at,
            content_type=page.content_type,
            extract=page.text,
        )
        by_url[page.url] = source

    scope = (workspace_scope or "").strip()
    workspace_hits: list[WorkspaceHit] = []
    if scope:
        root = Path(workspace_root).expanduser() if workspace_root is not None else None
        workspace_hits = search_workspace(query, root=root, scope=scope)
        if not workspace_hits:
            gaps.append(f"workspace scope {scope!r}: no line carried the query terms")

    header = (
        f"[web_research] query={query!r} provider={config.provider} "
        f"pages={len(run.pages)}/{run.considered} gaps={len(gaps)} depth={levels} "
        f"freshness={window or 'any'}"
        + (f" workspace={len(workspace_hits)}" if scope else "")
    )
    if not run.pages and not workspace_hits:
        body = (
            "No page or workspace line could be read, so no answer is given."
            if scope else "No page could be read, so no answer is given."
        )
        return ResearchResult(
            text="\n\n".join(
                part for part in (
                    header,
                    body,
                    _gaps_text(gaps),
                    "Next: loosen the site restriction or check the provider's results.",
                ) if part
            )
        )

    web_claims, matched = _select_claims(run.pages, _terms(query), by_url)
    local_claims = _workspace_claims(workspace_hits, limit=2) if workspace_hits else []
    if local_claims:
        web_claims = web_claims[: max(0, _MAX_CLAIMS - len(local_claims))]
    workspace_map = {hit.reference: hit for hit in workspace_hits}

    answer_lines: list[str] = []
    report = Verification()
    rejected = 0
    for sentence, source in web_claims:
        line = f"{sentence} [{source.source_id}]"
        part = verify_claims([line], store)
        _merge(report, part)
        if part.verified == 1:
            answer_lines.append(f"- {sentence} [{source.source_id}]")
        else:
            rejected += 1
    for hit in local_claims:
        line = f"{hit.text} [{hit.reference}]"
        part = verify_claims([line], store, workspace_map)
        _merge(report, part)
        if part.verified == 1:
            answer_lines.append(f"- {hit.text} [{hit.reference}]")
        else:
            rejected += 1
    if rejected:
        gaps.append(f"{rejected} sentence(s) did not survive the source-text check")

    if answer_lines:
        if local_claims:
            heading = (
                "Answer (extractive; each sentence names the page or the file line "
                "it was copied from)"
            )
            check = (
                f"Citation check: {len(answer_lines)} of {len(web_claims) + len(local_claims)} "
                "claim(s) verified against the stored page text and file lines."
            )
        else:
            heading = "Answer (extractive; each sentence names the page it was copied from)"
            check = (
                f"Citation check: {len(answer_lines)} of {len(web_claims)} sentence(s) verified "
                "against the stored page text."
            )
        if not matched and not local_claims:
            check += " No sentence carried a query term; the first passages are shown."
        answer = heading + "\n" + "\n".join(answer_lines)
    else:
        answer = (
            "No sentence of the read pages or workspace lines answered the query."
            if scope else "No sentence of the read pages answered the query."
        )
        check = ""

    evidence_parts = []
    if store.sources():
        evidence_parts.append("Sources\n" + "\n\n".join(
            _format_source(source) for source in store.sources()
        ))
    if local_claims:
        evidence_parts.append("Workspace sources\n" + "\n".join(
            _format_workspace(hit) for hit in local_claims
        ))

    text = "\n\n".join(
        part for part in (header, answer, check, *evidence_parts, _gaps_text(gaps)) if part
    )

    recorded = research_ledger.note_run(
        query=query,
        site=site_host,
        provider=config.provider,
        depth=levels,
        freshness=window,
        pages=len(run.pages),
        considered=run.considered,
        sources=list(store.sources()),
        workspace=list(local_claims),
        claims=[
            research_ledger.ResearchClaim(
                text=line.text, source_id=line.source_id, reference=line.reference
            )
            for line in _claims_of(web_claims, local_claims)
        ],
        answer=answer_lines,
        gaps=gaps,
        verification=report,
        store=store,
    )
    return ResearchResult(text=text, run=recorded, verification=report)


def _claims_of(
    web_claims: list[tuple[str, EvidenceSource]],
    local_claims: list[WorkspaceHit],
) -> list[research_ledger.ResearchClaim]:
    claims = [
        research_ledger.ResearchClaim(text=sentence, source_id=source.source_id)
        for sentence, source in web_claims
    ]
    claims.extend(
        research_ledger.ResearchClaim(text=hit.text, reference=hit.reference)
        for hit in local_claims
    )
    return claims


async def web_research(
    query: str = "",
    site: str = "",
    max_pages: int = policy.DEFAULT_PAGES,
    depth: int = policy.DEFAULT_DEPTH,
    freshness: str = "any",
    workspace_scope: str = "",
) -> str:
    return (await run_research(
        query=query,
        site=site,
        max_pages=max_pages,
        depth=depth,
        freshness=freshness,
        workspace_scope=workspace_scope,
    )).text
