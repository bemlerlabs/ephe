"""Page reading for the web intake channel: robots, delay, conditional cache, text.

Every request goes through ``core.net_guard.guarded_get``; this module adds the
crawl rules on top of the reach rules. A page is revalidated with the ETag and
Last-Modified values the last read returned and kept under
``~/.ephe/web-cache/``, so a turn without a network can still answer from the
text it read before.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from core.engine_config import config_root
from core.net_guard import guarded_get
from core.web_intake import policy

CACHE_MAX_ENTRIES = 500
ROBOTS_MAX_BYTES = 200_000
_LINK = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.I)
_SCRIPT = re.compile(r"<(script|style)\b.*?</\s*\1\s*>", re.S | re.I)
_HEAD = re.compile(r"<head\b.*?</head\s*>", re.S | re.I)
_HEADING = re.compile(r"<h([1-6])[^>]*>(.*?)</h\s*\1>", re.S | re.I)
_LIST_ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n\s*\n(\s*\n)+")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)

_ROBOTS: dict[str, tuple[float, policy.RobotsRules]] = {}


def clear_robots_cache() -> None:
    _ROBOTS.clear()


def html_to_text(html: str, cap: int = policy.MAX_EXTRACT_CHARS) -> str:
    """Regex-based reduction to plain text (headings and lists markdown-like)."""
    text = _HEAD.sub(" ", html or "")
    text = _TITLE.sub(" ", text)
    text = _SCRIPT.sub(" ", text)

    def _heading(match: re.Match) -> str:
        level = min(int(match.group(1)), 6)
        return "\n" + "#" * level + " " + match.group(2).strip() + "\n"

    text = _HEADING.sub(_heading, text)
    text = _LIST_ITEM.sub(r"\n- \1", text)
    text = _TAG.sub(" ", text)
    text = _SPACES.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    if len(text) > cap:
        text = text[:cap] + f"\n\n[... truncated at {cap} chars]"
    return text.strip()


def page_title(html: str) -> str:
    match = _TITLE.search(html or "")
    if not match:
        return ""
    title = _TAG.sub(" ", match.group(1))
    return _SPACES.sub(" ", title).strip()[:200]


def extract_links(html: str, base: str) -> tuple[str, ...]:
    """Same-document links in reading order, capped, http(s) only."""
    links: list[str] = []
    seen: set[str] = set()
    for match in _LINK.finditer(html or ""):
        target = urljoin(base, match.group(1).strip())
        if urlsplit(target).scheme not in ("http", "https"):
            continue
        target = target.split("#", 1)[0]
        if target and target not in seen:
            seen.add(target)
            links.append(target)
        if len(links) >= policy.MAX_LINKS_PER_PAGE:
            break
    return tuple(links)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _age_seconds(fetched_at: str) -> float:
    try:
        stamp = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())


def _media_type(header: str) -> str:
    return (header or "").split(";", 1)[0].strip().lower()


class PageCache:
    """JSON per URL under the config root; the key is the URL hash."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root or (config_root() / "web-cache" / "pages")

    def _path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8", "replace")).hexdigest()[:32]
        return self.root / f"{key}.json"

    def get(self, url: str) -> dict | None:
        try:
            payload = json.loads(self._path(url).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def put(self, url: str, record: dict) -> None:
        path = self._path(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(f".{os.getpid()}.part")
            temp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, path)
        except OSError:
            return
        self._prune()

    def _prune(self) -> None:
        try:
            files = sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime)
        except OSError:
            return
        for stale in files[: max(0, len(files) - CACHE_MAX_ENTRIES)]:
            try:
                stale.unlink()
            except OSError:
                continue


PAGE_CACHE = PageCache()


@dataclass(frozen=True)
class CrawlPage:
    url: str
    title: str
    text: str
    content_type: str
    fetched_at: str
    links: tuple[str, ...] = ()
    from_cache: bool = False


@dataclass(frozen=True)
class CrawlGap:
    url: str
    reason: str
    code: str = ""


@dataclass
class CrawlRun:
    pages: list[CrawlPage] = field(default_factory=list)
    gaps: list[CrawlGap] = field(default_factory=list)
    considered: int = 0


def _gap(url: str, reason: str, code: str) -> CrawlGap:
    text = str(reason or "").strip()
    return CrawlGap(url=url, reason=text or "no answer", code=code or getattr(reason, "code", ""))


async def robots_for(
    url: str,
    *,
    allow_private: bool | None = None,
    timeout: float = policy.REQUEST_TIMEOUT_SECONDS,
) -> policy.RobotsRules:
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    cached = _ROBOTS.get(origin)
    now = time.monotonic()
    if cached is not None and cached[0] > now:
        return cached[1]
    response = await guarded_get(
        urljoin(url, "/robots.txt"),
        timeout=min(timeout, 5.0),
        max_bytes=ROBOTS_MAX_BYTES,
        allow_private=allow_private,
    )
    if response.status == 0:
        rules = policy.RobotsRules.blocked(
            f"robots.txt could not be read ({response.note or 'no answer'})"
        )
    elif response.status in (401, 403):
        rules = policy.RobotsRules.blocked(
            f"robots.txt answered HTTP {response.status}"
        )
    elif response.status >= 500:
        rules = policy.RobotsRules.blocked(
            f"robots.txt answered HTTP {response.status}"
        )
    elif response.status >= 400:
        rules = policy.RobotsRules.from_text("")
    else:
        rules = policy.RobotsRules.from_text(response.text)
    _ROBOTS[origin] = (now + policy.ROBOTS_CACHE_SECONDS, rules)
    return rules


async def fetch_page(
    url: str,
    *,
    limiter: policy.RateLimiter,
    allow_private: bool | None = None,
    timeout: float = policy.REQUEST_TIMEOUT_SECONDS,
    cache_window: float = 0.0,
) -> CrawlPage | CrawlGap:
    cached = PAGE_CACHE.get(url)
    if cached and cache_window > 0 and _age_seconds(cached.get("fetched_at", "")) < cache_window:
        return _page_from_record(cached, from_cache=True)

    rules = await robots_for(url, allow_private=allow_private, timeout=timeout)
    allowed, why = rules.allows(url)
    if not allowed:
        return _gap(url, why, "robots_disallowed")

    host = (urlsplit(url).hostname or "").lower()
    await limiter.wait(host, rules.crawl_delay)

    headers: dict[str, str] = {}
    if cached:
        if cached.get("etag"):
            headers["If-None-Match"] = str(cached["etag"])
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = str(cached["last_modified"])
    response = await guarded_get(
        url,
        headers=headers or None,
        timeout=timeout,
        max_bytes=policy.MAX_PAGE_BYTES,
        allow_private=allow_private,
    )
    if response.status == 0:
        return _gap(url, response.note, "")
    if response.status == 304 and cached:
        fetched_at = now_iso()
        cached["fetched_at"] = fetched_at
        PAGE_CACHE.put(url, cached)
        return _page_from_record(cached, from_cache=True, fetched_at=fetched_at)
    if response.status >= 400:
        return _gap(url, f"the page answered HTTP {response.status}", "http_status")
    if response.note and "capped" in response.note:
        return _gap(url, "the page is larger than the crawler's byte cap", "too_large")

    media = _media_type(response.headers.get("content-type", ""))
    if not policy.content_type_allowed(media):
        return _gap(
            url,
            f"content-type '{media or 'none'}' is outside the crawler whitelist",
            "content_type",
        )
    html = response.text
    page_url = response.url or url
    if media in ("text/html", "application/xhtml+xml"):
        text = html_to_text(html)
        links = extract_links(html, page_url)
        title = page_title(html)
    else:
        text = html[: policy.MAX_EXTRACT_CHARS]
        links = ()
        title = ""
    record = {
        "url": page_url,
        "title": title or page_url,
        "text": text,
        "content_type": media,
        "fetched_at": now_iso(),
        "etag": response.headers.get("etag", ""),
        "last_modified": response.headers.get("last-modified", ""),
        "links": list(links),
    }
    PAGE_CACHE.put(url, record)
    return CrawlPage(
        url=page_url,
        title=record["title"],
        text=text,
        content_type=media,
        fetched_at=record["fetched_at"],
        links=links,
    )


def _page_from_record(
    record: dict,
    *,
    from_cache: bool,
    fetched_at: str | None = None,
) -> CrawlPage:
    return CrawlPage(
        url=str(record.get("url", "")),
        title=str(record.get("title", "")),
        text=str(record.get("text", "")),
        content_type=str(record.get("content_type", "")),
        fetched_at=str(fetched_at or record.get("fetched_at", "")),
        links=tuple(str(link) for link in record.get("links") or ()),
        from_cache=from_cache,
    )


async def crawl(
    seeds: list[str],
    *,
    max_pages: int,
    depth: int,
    freshness: str = "",
    site: str = "",
    allow_private: bool | None = None,
    limiter: policy.RateLimiter | None = None,
    timeout: float = policy.REQUEST_TIMEOUT_SECONDS,
) -> CrawlRun:
    """Read the seeds, then same-host links from them while ``depth`` allows."""
    limiter = limiter or policy.RateLimiter()
    window = policy.cache_window_seconds(freshness)
    run = CrawlRun()
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(url, 0) for url in seeds]

    while queue and len(run.pages) < max_pages:
        url, level = queue.pop(0)
        url = (url or "").strip().split("#", 1)[0]
        if not url or url in seen:
            continue
        seen.add(url)
        run.considered += 1
        if not policy.in_site(url, site):
            run.gaps.append(_gap(url, "outside the site restriction", "site_scope"))
            continue
        result = await fetch_page(
            url,
            limiter=limiter,
            allow_private=allow_private,
            timeout=timeout,
            cache_window=window,
        )
        if isinstance(result, CrawlGap):
            run.gaps.append(result)
            continue
        run.pages.append(result)
        if level + 1 >= depth:
            continue
        scope = site or (urlsplit(result.url).hostname or "")
        for link in result.links:
            if link not in seen and policy.in_site(link, scope):
                queue.append((link, level + 1))
    return run
