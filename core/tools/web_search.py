"""Ephe – web_search tool."""

from __future__ import annotations

import asyncio

from ddgs import DDGS

from core.net_guard import reach_by_name
from core.tools.base import WebSearchError


# W19 bench finding: DDGS rotates across backends (primp) and occasionally hangs
# endlessly in one backend retry — without a timeout asyncio.to_thread waits forever
# and the whole agent loop stands still (observed in the bench: runs with 700s+
# of silence in the middle of the search flow). A hard budget for the whole search call.
WEB_SEARCH_TIMEOUT_SECONDS = 30.0

OFFICIAL_SOURCE_DOMAINS = (
    "ai.google.dev",
    "developers.googleblog.com",
    "blog.google",
    "deepmind.google",
    "openai.com",
    "anthropic.com",
    "docs.github.com",
    "github.com",
    "ollama.com",
    "python.org",
)


async def web_search(query: str, max_results: int = 5) -> str:
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    # The JSON schema declares 'integer', but some models
    # loosely deliver "5" as a string. ddgs internally divides the value -> 'str'/'int'
    # errors. Normalize at the entry (as discover_projects does).
    try:
        max_results = max(1, min(int(max_results), 10))
    except (TypeError, ValueError):
        max_results = 5

    def _search() -> list[dict]:
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=max_results)
        return raw or []

    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_search), timeout=WEB_SEARCH_TIMEOUT_SECONDS
        )
        if not raw:
            return "No results found."

        def _source_quality(url: str) -> tuple[int, str]:
            lowered = (url or "").lower()
            if any(domain in lowered for domain in OFFICIAL_SOURCE_DOMAINS):
                return (0, "official")
            if any(domain in lowered for domain in ("wikipedia.org", "arxiv.org", "huggingface.co")):
                return (1, "reference")
            return (2, "general")

        raw = sorted(
            raw,
            key=lambda result: _source_quality(str(result.get("href", "")))[0],
        )

        formatted_parts = []
        for i, r in enumerate(raw, 1):
            title = r.get("title", "")
            url = r.get("href", "")
            body = r.get("body", "")
            _, quality = _source_quality(url)
            # A result is only worth as much as the target behind it. fetch_url
            # is walled (core/net_guard); a hit from an internal
            # namespace is worthless as a link and effective as bait, so the
            # line says that, instead of letting the model run into a blockade.
            reachable, reason = reach_by_name(url)
            reach_line = "" if reachable else f"\n    Reichweite: {reason} — fetch_url oeffnet dieses Ziel nicht."
            formatted_parts.append(
                f"[{i}] {title}\n"
                f"    URL: {url}\n"
                f"    Source quality: {quality}{reach_line}\n"
                f"    {body}"
            )
        return "\n\n".join(formatted_parts)

    except Exception as exc:
        raise WebSearchError(str(exc)) from exc
