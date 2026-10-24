"""A guarded HTTPS GET for indexes and artifacts.

The address is resolved once, pinned for the request, and checked against the
public-address policy; redirects and proxy environment settings are refused.
A response is read with a byte cap, so a hostile server cannot exhaust memory
before the caller sees the size.
"""
from __future__ import annotations

import httpx

from core.network_guard import NetworkGuardError, prepare_http_target

MAX_DEFAULT_BYTES = 2 * 1024 * 1024


class GuardedFetchError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def fetch_https(
    url: str,
    *,
    max_bytes: int = MAX_DEFAULT_BYTES,
    timeout: float = 10.0,
    accept: str = "application/json",
) -> bytes:
    try:
        target, host_header, sni = prepare_http_target(url)
    except NetworkGuardError as exc:
        raise GuardedFetchError("untrusted_target", str(exc)) from exc
    headers = {"Host": host_header, "Accept": accept}
    extensions = {"sni_hostname": sni} if sni else None
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=False, trust_env=False
        ) as client, client.stream(
            "GET", target, headers=headers, extensions=extensions
        ) as response:
            if 300 <= response.status_code < 400:
                raise GuardedFetchError("redirect_refused", "a redirect is not followed")
            if response.status_code >= 400:
                raise GuardedFetchError(
                    "http_status", f"the server answered {response.status_code}"
                )
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise GuardedFetchError("too_large", "the declared size exceeds the cap")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise GuardedFetchError("too_large", "the response exceeds the cap")
                chunks.append(chunk)
            return b"".join(chunks)
    except GuardedFetchError:
        raise
    except httpx.HTTPError as exc:
        raise GuardedFetchError("fetch_failed", str(exc)[:200]) from exc
