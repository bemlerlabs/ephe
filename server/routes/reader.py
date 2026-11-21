"""
◑ Ephe – Reader view (W1-b)
server/routes/reader.py

GET /api/reader?url=… → {ok, title, text, chars, truncated, target,
                         reason, reason_code, reason_params}

The browser pane draws a web page inside an iframe; pages that forbid embedding
(X-Frame-Options, frame-ancestors) leave an empty box. This route returns the
same material as text — fetched through exactly the reach guard the agent tools
use (core.net_guard via core.tools.fetch_tools._http_get). The surface therefore
gets no second, unchecked network window; what the agent may not reach, the
reader does not reach either.

The path is deliberately narrow: one title, one text, one reason when there is
no text. No Markdown, no images, no CSS.

A refused fetch is answered with the guard's own verdict on the address the caller
named, taken again as data (`_verdict_on`), so no line of an exception reaches a pane.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Query

from core.net_guard import check_url

router = APIRouter(tags=["reader"])

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_OG_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I
)
_OG_ALT_RE = re.compile(
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:title[\"']", re.I
)
# The reader wants the article, not the page frame. Two attempts, then
# the whole document — a page without <article>/<main> is not an error,
# it is the normal case.
_LANDMARK_RE = re.compile(
    r"<(article|main)\b[^>]*>(.*?)</\s*\1\s*>", re.S | re.I
)
_TRUNCATED_MARK = re.compile(r"\n\n\[\.\.\. truncated at \d+ chars\]\s*$")


def _title_of(html: str, url: str) -> str:
    for pattern in (_TITLE_RE, _OG_RE, _OG_ALT_RE):
        match = pattern.search(html)
        if match:
            raw = re.sub(r"<[^>]+>", " ", match.group(1))
            raw = re.sub(r"\s+", " ", raw).strip()
            if raw:
                return raw[:160]
    host = urlparse(url).netloc
    return host or url


def _body_of(html: str) -> str:
    # An <article>/<main> is the author's statement of where the content lives —
    # it holds as long as it is not empty. The rest is frame.
    match = _LANDMARK_RE.search(html)
    if match and len(match.group(2).strip()) > 40:
        return match.group(2)
    body = re.search(r"<body\b[^>]*>(.*?)</\s*body\s*>", html, re.S | re.I)
    return body.group(1) if body else html


def _refused(
    target: str,
    reason: str,
    code: str | None = None,
    params: dict[str, object] | None = None,
) -> dict:
    """The pane's one failure shape.

    `reason` stays the sentence this route has always sent — old clients and the
    log lines read it. `reason_code` names the same statement for a client that
    translates, and is null wherever nothing names it, which tells the pane to
    show `reason`.
    """
    return {
        "ok": False,
        "reason": reason,
        "reason_code": code,
        "reason_params": dict(params or {}),
        "title": "",
        "text": "",
        "chars": 0,
        "truncated": False,
        "target": target,
    }


#: The one sentence for a fetch this route could not complete for a reason the guard
#: does not name — a connection that failed, a redirect onto a blocked address, a
#: decoder that tripped. The class name and the message of such an error are the leak,
#: and they stay in the log.
_UNREADABLE = "The page could not be read."


def _verdict_on(target: str) -> tuple[str, str | None, dict | None]:
    """The guard's own reading of the address the caller named, as (sentence, code, params).

    A refusal arrives as an exception, and a pane must not read one: the line of a
    fetch fault names its class, and the guard's sentence for a blocked hop belongs to
    the hop rather than to the address in the query. So the route asks the guard again
    about that address and hands the verdict over as data. Where the guard now allows
    the target, the answer is this route's own sentence with no code.
    """
    try:
        allowed, note = check_url(target)
    except Exception:  # a verdict that cannot be taken is no reason to serve a line
        logger.warning("reader: no verdict for %s", target, exc_info=True)
        return _UNREADABLE, None, None
    if allowed:
        return _UNREADABLE, None, None
    return str(note), getattr(note, "code", "") or None, getattr(note, "params", None) or {}


@router.get("/reader")
async def read_url(url: str = Query(default="")) -> dict:
    """Text of a web page for the panel's reader view."""
    target = (url or "").strip()
    if not re.match(r"^https?://", target, re.I):
        return _refused(target, "Only http(s) addresses can be read.", "url_not_http")

    from core.tools.fetch_tools import FetchRefused, _html_to_text, _http_get

    try:
        status, html = await _http_get(target)
    except FetchRefused as exc:
        # The guard refused the target or the fetch failed below it. Its line is one
        # designed sentence, pinned by tests/test_reader_reason_codes.py, and its Reason
        # carries the code beside it — the pane gets the guard's reading of the address
        # it asked for, never a string lifted off an exception.
        logger.info("reader refused %s: %s", target, exc)
        return _refused(target, *_verdict_on(target))
    except Exception:  # network, time, decoder — all one thing: no text.
        # The exception is for the log below. The pane gets a fixed sentence: the
        # class name and the message of a network, time or decoder error are the leak.
        logger.warning("reader: fetch failed for %s", target, exc_info=True)
        return _refused(target, _UNREADABLE)

    if status >= 400:
        return _refused(
            target,
            f"The page answers with {status}.",
            "http_status_error",
            {"status": status},
        )

    text = _html_to_text(_body_of(html))
    truncated = bool(_TRUNCATED_MARK.search(text))
    if truncated:
        text = _TRUNCATED_MARK.sub("", text)
    return {
        "ok": bool(text),
        "reason": "" if text else "This page carries no readable text.",
        "reason_code": None if text else "no_readable_text",
        "reason_params": {},
        "title": _title_of(html, target),
        "text": text,
        "chars": len(text),
        "truncated": truncated,
        "target": target,
    }
