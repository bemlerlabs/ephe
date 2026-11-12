"""The bounds of the web intake channel, in one place.

The crawler reads what a search provider hands it and nothing else: public
addresses only, robots.txt first, one request per host per delay, a byte cap per
page and a whitelist of content types. Crawler, tool and tests read these
constants instead of carrying copies.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from core.net_guard import reach_by_name

DEFAULT_PAGES = 4
MAX_PAGES = 8
DEFAULT_DEPTH = 1
MAX_DEPTH = 2

#: One page feeds a prompt, not a disk. Above this the crawler keeps the head and says so.
MAX_PAGE_BYTES = 1_000_000
MAX_EXTRACT_CHARS = 12_000
MAX_LINKS_PER_PAGE = 20
REQUEST_TIMEOUT_SECONDS = 12.0

CRAWL_DELAY_SECONDS = 1.0
#: A site asking for a longer pause than this would stall a whole turn.
MAX_CRAWL_DELAY_SECONDS = 5.0
ROBOTS_CACHE_SECONDS = 3_600.0

USER_AGENT = "Ephe-WebIntake/1.0 (local research tool)"

CONTENT_TYPE_ALLOWLIST = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
)

#: A freshness word becomes a cache window. ``""`` means revalidate every time.
FRESHNESS_WINDOWS = {
    "": 0,
    "day": 86_400,
    "week": 604_800,
    "month": 2_592_000,
    "year": 31_536_000,
}


def normalize_freshness(value: object) -> str:
    """One of the window keys, or ``ValueError`` for a word the crawler cannot honour."""
    text = str(value or "").strip().lower()
    if text in ("", "any", "none"):
        return ""
    if text in FRESHNESS_WINDOWS:
        return text
    raise ValueError("freshness must be any, day, week, month or year")


def cache_window_seconds(freshness: str) -> float:
    return float(FRESHNESS_WINDOWS.get(freshness, 0))


def normalize_limits(max_pages: object, depth: object) -> tuple[int, int]:
    """Clamp the two inputs a model sends loosely (``"3"``, 0, 99)."""
    try:
        pages = int(max_pages)
    except (TypeError, ValueError):
        pages = DEFAULT_PAGES
    try:
        levels = int(depth)
    except (TypeError, ValueError):
        levels = DEFAULT_DEPTH
    return (
        max(1, min(pages, MAX_PAGES)),
        max(1, min(levels, MAX_DEPTH)),
    )


def content_type_allowed(value: str) -> bool:
    """The media type before ``;`` against the whitelist."""
    media = (value or "").split(";", 1)[0].strip().lower()
    return media in CONTENT_TYPE_ALLOWLIST


def site_host(value: str) -> str:
    """The host a site restriction names; a bare name and a full URL both work."""
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    return (urlsplit(raw).hostname or "").strip().rstrip(".")


def in_site(url: str, site: str) -> bool:
    """True while the host is the named one or a subdomain of it.

    A URL the parser cannot read is outside every site: the restriction is a
    boundary, so an unparsable link fails closed instead of raising mid-crawl.
    """
    if not site:
        return True
    try:
        parts = urlsplit(url)
        parts.port
        host = (parts.hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return False
    return host == site or host.endswith(f".{site}")


def link_reach(url: str) -> tuple[bool, str]:
    """Name-based reach for a search hit or a discovered link (no request)."""
    return reach_by_name(url)


@dataclass(frozen=True)
class RobotsRules:
    """What one host allows, from its robots.txt or from a fetch that failed."""

    parser: RobotFileParser | None = None
    reason: str = ""
    crawl_delay: float = 0.0

    @classmethod
    def from_text(cls, text: str) -> "RobotsRules":
        parser = RobotFileParser()
        parser.parse((text or "").splitlines())
        delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 0.0
        return cls(parser=parser, crawl_delay=min(float(delay), MAX_CRAWL_DELAY_SECONDS))

    @classmethod
    def blocked(cls, reason: str) -> "RobotsRules":
        # RFC 9309: a robots.txt that cannot be read (5xx, timeout) forbids the site.
        return cls(parser=None, reason=reason)

    def allows(self, url: str) -> tuple[bool, str]:
        if self.parser is None:
            return False, self.reason or "robots.txt keeps the crawler out"
        if self.parser.can_fetch(USER_AGENT, url):
            return True, ""
        return False, "robots.txt disallows this path"


class RateLimiter:
    """One request per host per delay, measured against an injectable clock.

    The clock and the sleep are parameters so a test asserts the wait without
    spending it.
    """

    def __init__(self, *, delay: float = CRAWL_DELAY_SECONDS, clock=None, sleep=None):
        self._delay = delay
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._last: dict[str, float] = {}

    async def wait(self, host: str, delay: float | None = None) -> None:
        pause = self._delay if delay is None else max(self._delay, delay)
        now = self._clock()
        last = self._last.get(host)
        if last is not None:
            remaining = pause - (now - last)
            if remaining > 0:
                await self._sleep(remaining)
                now = last + pause
        self._last[host] = now
