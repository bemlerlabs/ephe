"""fetch_url — pull one URL, reduce the page to text, hand the text back.

The tool makes no model call. A second call inside a tool is a hidden engine
choice: the old prompt path went to a local client no matter which provider was
active, so with a hosted engine it failed behind a card that said Completed.
The model that asked for the page answers from the text this returns.

Every failure is a ``Reason``: a marker the model and the audit can read, a code
the surface translates, and the params that sentence interpolates.
"""
from __future__ import annotations

import re
import time

from core.reason import Reason
from core.tool_markers import FETCH_FAILED_MARKER, FETCH_REFUSED_MARKER

_FETCH_TTL_SECONDS = 900.0          # 15 minutes, like the reference
_FETCH_CACHE_MAX = 50
_FETCH_HTML_CAP = 12_000

#: key = URL, value = (timestamp, extracted document text)
_FETCH_CACHE: dict[str, tuple[float, str]] = {}

#: The tool's own vocabulary for the outcomes it names. A refusal the guard
#: already coded keeps that code: the reader translates it with the sentence it
#: actually has (`metadata_host`, `private_blocked_default`, …), and collapsing
#: that into a generic refusal would replace a precise sentence with a vaguer one.
_GUARD_CODES = {
    "url_empty": "fetch_empty_url",
    "url_without_scheme": "fetch_scheme_blocked",
    "scheme_blocked": "fetch_scheme_blocked",
    "scheme_outside_channel": "fetch_scheme_blocked",
    "url_not_http": "fetch_scheme_blocked",
}


def _now() -> float:
    return time.monotonic()


def _html_to_text(html: str) -> str:
    """Regex-based reduction to plain text (headings/lists markdown-like)."""
    text = html
    text = re.sub(r"<(script|style)\b.*?</\s*\1\s*>", " ", text, flags=re.S | re.I)

    def _heading(match: re.Match) -> str:
        level = min(int(match.group(1)), 6)
        return "\n" + "#" * level + " " + match.group(2).strip() + "\n"

    text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\s*\1>", _heading, text, flags=re.S | re.I)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n(\s*\n)+", "\n\n", text)
    if len(text) > _FETCH_HTML_CAP:
        text = text[:_FETCH_HTML_CAP] + f"\n\n[... truncated at {_FETCH_HTML_CAP} chars]"
    return text.strip()


class FetchRefused(RuntimeError):
    """The scope guard refused the target — one line, no stack trace."""


class FetchTransport(RuntimeError):
    """The request failed before a document arrived (timeout, reset, DNS)."""


def _failure(code: str, detail: str, **params: str) -> Reason:
    return Reason(f"{FETCH_FAILED_MARKER} {detail}", code, params)


def _refusal(note) -> Reason:
    original = str(getattr(note, "code", "") or "")
    params = dict(getattr(note, "params", {}) or {})
    mapped = _GUARD_CODES.get(original)
    if mapped is None and not original:
        return Reason(
            f"{FETCH_REFUSED_MARKER} {note}",
            "fetch_refused",
            {"detail": str(note)},
        )
    return Reason(f"{FETCH_REFUSED_MARKER} {note}", mapped or original, params)


def _transport_failure(detail: str) -> Reason:
    lowered = detail.lower()
    if "timeout" in lowered or "timed out" in lowered:
        return _failure("fetch_timeout", "The fetch ran into a timeout.")
    return _failure("fetch_unreachable", "The host could not be reached.")


async def _http_get(url: str) -> tuple[int, str]:
    """G4: the only way out leads through core.net_guard.

    http/https, the target address of EVERY hop (a 302 onto loopback is the
    attack itself) and the data volume are checked there. A refused target
    raises FetchRefused with the reason; a broken request raises FetchTransport,
    so the caller can name the outcome instead of guessing.
    """
    from core.net_guard import guarded_fetch

    status, text, note = await guarded_fetch(url)
    if status == 0:
        if str(text).startswith("[refused]"):
            raise FetchRefused(note or text)
        raise FetchTransport(str(note or text))
    if note:
        text = f"{text}\n\n[{note}]"
    return status, text


async def fetch_url(url: str, prompt: str = "") -> str:
    """Fetches a URL and returns the extracted text.

    ``prompt`` stays in the signature for callers that still send it and is not
    answered here: the asking model answers from the text, which is what the
    tool description now tells it to do.
    """
    url = (url or "").strip()
    if not url:
        return _failure("fetch_empty_url", "The URL is empty.")

    cached = _FETCH_CACHE.get(url)
    if cached is not None and (_now() - cached[0]) < _FETCH_TTL_SECONDS:
        doc = cached[1]
    else:
        try:
            status, html = await _http_get(url)
        except FetchRefused as refused:
            return _refusal(refused.args[0] if refused.args else refused)
        except FetchTransport as transport:
            return _transport_failure(str(transport))
        except Exception as exc:  # noqa: BLE001 — the channel returns lines, not stack traces
            return _transport_failure(str(exc))
        if status >= 400:
            return _failure(
                "fetch_http_error",
                f"{url} answered HTTP {status}.",
                status=str(status),
                url=url,
            )
        doc = _html_to_text(html)
        _FETCH_CACHE[url] = (_now(), doc)
        while len(_FETCH_CACHE) > _FETCH_CACHE_MAX:
            _FETCH_CACHE.pop(next(iter(_FETCH_CACHE)), None)

    return doc or "(empty document)"
