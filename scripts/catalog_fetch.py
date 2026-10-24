"""HTTP boundary for catalogue discovery: https only, capped, one retry."""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 8_000_000
TIMEOUT_S = 20


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect())


def ascii_url(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?&=%#[]@!$'()*+,;~-._")


def fetch(url: str, *, max_bytes: int = MAX_BYTES) -> bytes:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError(f"https expected: {url}")
    request = urllib.request.Request(
        ascii_url(url), headers={"User-Agent": "ephe-catalog-discover/0.1"}
    )
    for attempt in range(2):
        try:
            with _OPENER.open(request, timeout=TIMEOUT_S) as response:
                data = response.read(max_bytes + 1)
            break
        except (TimeoutError, urllib.error.URLError):
            if attempt == 1:
                raise
    if len(data) > max_bytes:
        raise ValueError(f"response above {max_bytes} bytes")
    return data
