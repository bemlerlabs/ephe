"""The search provider a user configures, and the refusal when none is.

The endpoint is one JSON API the operator points Ephe at: a URL, a key that
travels in a header, and a response whose rows carry a URL, a title and a
snippet. Common key names are accepted so a small adapter is a JSON file, not a
code change. Without URL and key the provider is absent, and the tool refuses
with the setting to add instead of searching and failing quietly.

The request leaves through ``core.net_guard.guarded_get``: the same address
check, pin and byte cap as ``fetch_url``, and the key header is never sent to a
redirect target.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.engine_config import config_root
from core.net_guard import guarded_get
from core.web_intake import policy

CONFIG_FILENAME = "web-search.json"
ENV_CONFIG = "EPHE_SEARCH_CONFIG"
ENV_URL = "EPHE_SEARCH_API_URL"
ENV_KEY = "EPHE_SEARCH_API_KEY"
ENV_PROVIDER = "EPHE_SEARCH_PROVIDER"
ENV_KEY_HEADER = "EPHE_SEARCH_KEY_HEADER"
ENV_KEY_PREFIX = "EPHE_SEARCH_KEY_PREFIX"
ENV_QUERY_PARAM = "EPHE_SEARCH_QUERY_PARAM"
ENV_COUNT_PARAM = "EPHE_SEARCH_COUNT_PARAM"
ENV_TIMEOUT = "EPHE_SEARCH_TIMEOUT"

NEXT_STEP = (
    "set EPHE_SEARCH_API_URL and EPHE_SEARCH_API_KEY, or write both into "
    "~/.ephe/web-search.json, then call web_research again"
)


class SearchNotConfigured(RuntimeError):
    """No endpoint or no key: nothing was requested."""

    code = "web_search_not_configured"

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or "No search provider is configured.")
        self.detail = detail or str(self)


class SearchUnavailable(RuntimeError):
    """The provider was asked and did not deliver a list."""

    code = "web_search_failed"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class SearchConfig:
    url: str = ""
    key: str = ""
    provider: str = "configured"
    key_header: str = "Authorization"
    key_prefix: str = "Bearer "
    query_param: str = "q"
    count_param: str = "count"
    timeout: float = policy.REQUEST_TIMEOUT_SECONDS

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def headers(self) -> dict[str, str]:
        if not self.key_header:
            return {}
        return {self.key_header: f"{self.key_prefix}{self.key}"}

    @classmethod
    def from_environment(cls) -> "SearchConfig":
        stored = _stored_values()

        def pick(name: str, field: str, default: str = "") -> str:
            return (
                (os.environ.get(name) or "").strip()
                or str(stored.get(field) or "").strip()
                or default
            )

        timeout = pick(ENV_TIMEOUT, "timeout")
        try:
            timeout_seconds = float(timeout) if timeout else policy.REQUEST_TIMEOUT_SECONDS
        except ValueError:
            timeout_seconds = policy.REQUEST_TIMEOUT_SECONDS
        return cls(
            url=pick(ENV_URL, "url"),
            key=pick(ENV_KEY, "key"),
            provider=pick(ENV_PROVIDER, "provider", "configured"),
            key_header=pick(ENV_KEY_HEADER, "key_header", "Authorization"),
            key_prefix=pick(ENV_KEY_PREFIX, "key_prefix", "Bearer "),
            query_param=pick(ENV_QUERY_PARAM, "query_param", "q"),
            count_param=pick(ENV_COUNT_PARAM, "count_param", "count"),
            timeout=max(1.0, min(timeout_seconds, 60.0)),
        )


def config_path() -> str:
    return (os.environ.get(ENV_CONFIG) or "").strip() or str(config_root() / CONFIG_FILENAME)


def _stored_values() -> dict:
    try:
        payload = json.loads(Path(config_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


def _field(row: dict, names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "items", "data", "web", "hits"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = value.get("results") or value.get("items")
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
    return []


def _endpoint(url: str, params: list[tuple[str, str]]) -> str:
    parts = urlsplit((url or "").strip())
    query = parse_qsl(parts.query, keep_blank_values=True) + params
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def hits_from_payload(payload: object, limit: int) -> list[SearchHit]:
    """Normalize the documented shape and the usual aliases into one row type."""
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for row in _rows(payload):
        url = _field(row, ("url", "link", "href", "source_url"))
        if not url or url in seen:
            continue
        seen.add(url)
        title = _field(row, ("title", "name", "heading")) or url
        snippet = _field(row, ("snippet", "description", "content", "body", "text"))
        hits.append(SearchHit(title=title[:300], url=url, snippet=snippet[:600]))
        if len(hits) >= limit:
            break
    return hits


async def search(
    config: SearchConfig,
    query: str,
    *,
    limit: int,
    freshness: str = "",
) -> list[SearchHit]:
    if not config.configured:
        raise SearchNotConfigured()
    params = [(config.query_param, query), (config.count_param, str(limit))]
    if freshness:
        params.append(("freshness", freshness))
    response = await guarded_get(
        _endpoint(config.url, params),
        headers=config.headers(),
        timeout=config.timeout,
        max_bytes=policy.MAX_PAGE_BYTES,
    )
    if response.status == 0:
        raise SearchUnavailable(
            f"the search endpoint could not be reached ({response.note or 'no answer'})"
        )
    if response.status in (401, 403):
        raise SearchUnavailable(
            f"the search endpoint refused the key (HTTP {response.status})"
        )
    if response.status >= 400:
        raise SearchUnavailable(
            f"the search endpoint answered HTTP {response.status}"
        )
    try:
        payload = json.loads(response.text)
    except ValueError as exc:
        raise SearchUnavailable("the search endpoint answered non-JSON text") from exc
    return hits_from_payload(payload, limit)
