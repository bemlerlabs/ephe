"""Ephe – web_search tool."""

from __future__ import annotations

import asyncio
import re

from ddgs import DDGS

from core.net_guard import reach_by_name
from core.tools.base import WebSearchError


# W19 bench finding: DDGS rotates across backends (primp) and occasionally hangs
# endlessly in one backend retry — without a timeout asyncio.to_thread waits forever
# and the whole agent loop stands still (observed in the bench: runs with 700s+
# of silence in the middle of the search flow). A hard budget for the whole search call.
WEB_SEARCH_TIMEOUT_SECONDS = 30.0

#: Tried one at a time so the result can name the backend that answered.
SEARCH_BACKENDS: tuple[str, ...] = (
    "startpage",
    "brave",
    "google",
    "duckduckgo",
    "mojeek",
    "yahoo",
)

#: Per-backend timeout; WEB_SEARCH_TIMEOUT_SECONDS caps the whole call.
BACKEND_TIMEOUT_SECONDS = 8.0

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

_HTTP_CODE = re.compile(r"\b(4\d\d|5\d\d)\b")


def _status_token(exc: BaseException) -> str:
    """The short word a status line can carry: the HTTP code, else `error`."""
    match = _HTTP_CODE.search(str(exc))
    if match:
        return match.group(1)
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    return "error"


def _one_backend(query: str, max_results: int, backend: str) -> list[dict]:
    with DDGS() as ddgs:
        try:
            raw = ddgs.text(query, max_results=max_results, backend=backend)
        except TypeError:
            # A ddgs build without the per-backend switch: the call still works,
            # the status line then names the rotation it actually got.
            raw = ddgs.text(query, max_results=max_results)
    return raw or []


async def _ask_backend(query: str, max_results: int, backend: str) -> list[dict]:
    """One backend, one retry, both inside the per-backend timeout."""
    last: BaseException | None = None
    for _attempt in range(2):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_one_backend, query, max_results, backend),
                timeout=BACKEND_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - the call reports, it does not decide
            last = exc
            if _HTTP_CODE.search(str(exc)):
                # A 403/429 is not retried.
                break
    assert last is not None
    raise last


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

    loop = asyncio.get_running_loop()
    deadline = loop.time() + WEB_SEARCH_TIMEOUT_SECONDS
    statuses: list[str] = []
    raw: list[dict] = []
    for backend in SEARCH_BACKENDS:
        remaining = deadline - loop.time()
        if remaining <= 0:
            statuses.append("deadline")
            break
        try:
            raw = await asyncio.wait_for(
                _ask_backend(query, max_results, backend), timeout=remaining
            )
        except asyncio.TimeoutError:
            statuses.append(f"{backend} timeout")
            continue
        except Exception as exc:  # noqa: BLE001 - one backend falling over is data
            statuses.append(f"{backend} {_status_token(exc)}")
            continue
        if raw:
            statuses.append(f"{backend} 200")
            break
        statuses.append(f"{backend} 204")
    status_line = "Providers: " + (", ".join(statuses) or "none tried")

    if not raw:
        if statuses and all(line.endswith(("timeout", "error", "deadline")) for line in statuses):
            raise WebSearchError(status_line)
        return f"No results found. {status_line}"

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

    formatted_parts = [status_line]
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
        reach_line = "" if reachable else f"\n    Reach: {reason} — fetch_url does not open this target."
        formatted_parts.append(
            f"[{i}] {title}\n"
            f"    URL: {url}\n"
            f"    Source quality: {quality}{reach_line}\n"
            f"    {body}"
        )
    return "\n\n".join(formatted_parts)
