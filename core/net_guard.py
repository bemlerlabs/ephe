"""core/net_guard.py — the reach of the fetch_url channel (pure, no httpx in the decision tree).

``fetch_url`` is the only tool that gets a URL straight from the model.
Until now the rules were: ``follow_redirects=True``, no address check, no size
cap. "fetch_url('http://169.254.169.254/latest/meta-data/')" was a cloud
metadata reader, a redirect to ``127.0.0.1:8765/api/file?path=.ssh/id_rsa`` was
a file reader through Ephe's own server, and an arbitrarily large document was
a memory DoS in the process running on the user's machine.

The same rule wave G2 set for the headless browser: bound the cluster by its
reach, not by a guess. The check is a function of (URL, resolution) — so it
runs without a network, without httpx, and it is testable.

Deliberate decisions:
- Link-local/unspecified/metadata hosts are ALWAYS blocked. A user who sets
  ``EPHE_FETCH_ALLOW_PRIVATE=1`` wants to reach their dev servers, not the
  environment's instance credentials.
- Loopback/RFC1918/IPv6-local are opt-in through exactly that variable. The
  desktop case ("read me the docs from my local server") is more legitimate
  than the attack, and a default that blocks it is more honest than a default
  that hands it through.
- DNS binding (TOCTOU) is closed for this channel, not merely documented:
  ``guarded_fetch`` connects to the address that was checked (the URL host is
  set to the resolved IP) and passes TLS the original host as
  ``sni_hostname``. Certificate validation stays against the hostname — a
  nameserver that moves between check and connection then connects into
  nothing, not into the metadata network. A channel that resolves on its own
  (the headless browser) is not covered here.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

from core.reason import reason

#: Upper bound for one document text. The fetch channel feeds prompts, not
#: disks — 2 MB is far above any sensible page source.
MAX_DOWNLOAD_BYTES = 2_000_000
MAX_REDIRECT_HOPS = 5
FETCH_TIMEOUT_SECONDS = 15.0

#: Hostnames that point at the metadata endpoint (GCP and the standard shorthand).
METADATA_HOSTS = frozenset({"metadata.google.internal", "metadata.goog"})


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def allow_private_by_default() -> bool:
    """``EPHE_FETCH_ALLOW_PRIVATE=1`` — only then are internal networks reachable."""
    return _env_flag("EPHE_FETCH_ALLOW_PRIVATE")


def classify_address(ip: str) -> str:
    """Sort an address into its reach class; 'public' is the only free case.

    The order is the result, not a detail: ``is_private`` covers loopback AND
    link-local, and the metadata address must not get lost as a generic
    link-local case, because that would make the hint interchangeable.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "invalid"
    if addr in ipaddress.ip_network("169.254.169.254/32") or addr in ipaddress.ip_network(
        "fd00:ec2::254/128"
    ):
        return "metadata"
    if addr.is_unspecified or addr in ipaddress.ip_network("0.0.0.0/8"):
        return "unspecified"
    if addr.is_link_local:
        return "link_local"
    if addr.is_loopback:
        return "loopback"
    if addr.is_private or addr.is_reserved or addr.is_multicast:
        return "private"
    return "public"


#: Classes that stay blocked even with ``EPHE_FETCH_ALLOW_PRIVATE=1``.
ALWAYS_BLOCKED_KINDS = frozenset({"metadata", "unspecified", "link_local", "invalid"})


def address_is_public(ip: str) -> str | None:
    """``None`` for publicly reachable, otherwise the reason (class + address)."""
    kind = classify_address(ip)
    if kind == "public":
        return None
    return f"{ip} is {kind}"


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    return sorted({info[4][0] for info in infos})


def check_url(
    url: str,
    *,
    allow_private: bool | None = None,
    resolver=None,
) -> tuple[bool, str]:
    """(allowed, note or reason) — the channel's public statement of reach."""
    allowed, note, _addresses = _evaluate(url, allow_private=allow_private, resolver=resolver)
    return allowed, note


def _evaluate(
    url: str,
    *,
    allow_private: bool | None = None,
    resolver=None,
) -> tuple[bool, str, tuple[str, ...]]:
    """Like ``check_url``, but also with the resolved addresses to pin to.

    The addresses are only usable in the allow case; in a refusal they are empty.
    """
    raw = (url or "").strip()
    if not raw:
        return False, reason("url_empty", "Empty URL — fetch_url reaches nothing."), ()
    if "/" in raw and "://" not in raw and not raw.startswith("//"):
        return False, reason(
            "url_without_scheme",
            "URL without a scheme — put https:// (or http://) in front of it.",
        ), ()
    candidate = raw if "://" in raw else f"https://{raw}"
    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        # The sentence keeps its own word for a missing scheme; the param is what a
        # locale entry interpolates, so it has to read in both languages.
        return False, reason(
            "scheme_blocked",
            f"{scheme or 'none'}: is blocked for fetch_url — the tool reads web "
            "documents over http/https, not files on the host.",
            scheme=scheme or "none",
        ), ()
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        return False, reason("no_host", f"{candidate} has no host.", url=candidate), ()
    if host in METADATA_HOSTS:
        return False, reason(
            "metadata_host",
            f"{host} is the environment's metadata endpoint — blocked always.",
            host=host,
        ), ()

    gate = allow_private if allow_private is not None else allow_private_by_default()
    resolve = resolver or _resolve
    try:
        addresses = [host] if _is_ip_literal(host) else list(resolve(host))
    except socket.gaierror:
        # gaierror is not a system failure but the answer "this host does not
        # exist" — the same statement the empty-resolution-result path makes.
        return False, reason(
            "not_resolvable",
            f"{host} does not resolve — there is no target.",
            host=host,
        ), ()
    except Exception as exc:  # noqa: BLE001 — a broken resolver is a refusal
        return False, reason(
            "dns_failed",
            f"DNS for {host} failed ({type(exc).__name__}).",
            host=host,
            error_type=type(exc).__name__,
        ), ()
    if not addresses:
        return False, reason(
            "not_resolvable",
            f"{host} does not resolve — there is no target.",
            host=host,
        ), ()

    seen_kinds: list[str] = []
    for address in addresses:
        kind = classify_address(address)
        if kind == "public":
            continue
        if kind in ALWAYS_BLOCKED_KINDS:
            return False, reason(
                "always_blocked_class",
                f"{host} stands on {address} ({kind}) — metadata and link-local targets "
                "are blocked always.",
                host=host,
                address=address,
                kind=kind,
            ), ()
        if not gate:
            return False, reason(
                "private_blocked_default",
                f"{host} stands on {address} ({kind}) — internal networks are blocked by "
                "default. For the local dev server: EPHE_FETCH_ALLOW_PRIVATE=1.",
                host=host,
                address=address,
                kind=kind,
            ), ()
        seen_kinds.append(kind)
    note = f"{host} → {', '.join(addresses)}"
    if seen_kinds:
        note += f" (internal: {', '.join(sorted(set(seen_kinds)))}, allowed on purpose)"
    return True, note, tuple(addresses)



#: Suffixes that only resolve inside an internal network — a search result with
#: such a name leads the model into a target it must not reach.
INTERNAL_NAME_SUFFIXES = (".localhost", ".local", ".internal", ".svc", ".cluster.local")
INTERNAL_NAME_HOSTS = frozenset({"localhost", "metadata", "gdcl"})


def reach_by_name(url: str, *, allow_private: bool | None = None) -> tuple[bool, str]:
    """(reachable, reason) from the name alone — no DNS, no connection.

    For search results: a hit that ``fetch_url`` may never open is worthless as
    a link and effective as bait (a poisoned index can hand back a metadata
    address as a result). The check is deliberately name-based: it gives the
    same answer offline as online and does not turn a list of results into a
    list of requests.
    """
    raw = (url or "").strip()
    parts = urlsplit(raw if "://" in raw else f"//{raw}", scheme="https")
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return False, reason(
            "scheme_outside_channel",
            f"{scheme or 'no scheme'}: is outside the fetch channel.",
            scheme=scheme or "none",
        )
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        return False, reason("no_host_in_url", "No host in the URL.")
    if host in METADATA_HOSTS or host in INTERNAL_NAME_HOSTS:
        return False, reason(
            "internal_target_name",
            f"{host} is an internal target name (metadata or loopback name).",
            host=host,
        )
    if any(host.endswith(suffix) for suffix in INTERNAL_NAME_SUFFIXES):
        return False, reason(
            "internal_name_suffix",
            f"{host} ends in an internal namespace.",
            host=host,
        )
    if _is_ip_literal(host):
        kind = classify_address(host)
        if kind in ALWAYS_BLOCKED_KINDS:
            return False, reason(
                "always_blocked_class_name",
                f"{host} is {kind} — always out of reach.",
                host=host,
                kind=kind,
            )
        gate = allow_private if allow_private is not None else allow_private_by_default()
        if not gate and kind != "public":
            return False, reason(
                "private_blocked_default_name",
                f"{host} is {kind} — internal networks are blocked by default.",
                host=host,
                kind=kind,
            )
    return True, ""


def pinned_request(
    url: str, addresses: tuple[str, ...]
) -> tuple[str, str, str]:
    """(URL with the pinned address, TLS server name, Host header).

    The TCP peer becomes the address that was checked, not a second resolution.
    For ``https`` the original host stays the TLS server name, so certificate
    validation still checks against the hostname and not against an IP. An
    IP-literal URL has nothing to pin and no SNI.
    """
    # the same scheme inference as _evaluate: without a scheme, https is the target.
    raw = (url or "").strip()
    parts = urlsplit(raw if "://" in raw else f"https://{raw}")
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").strip().rstrip(".").lower()
    default_port = 443 if scheme == "https" else 80
    port = parts.port or default_port
    target = addresses[0] if addresses else host
    literal = f"[{target}]" if ":" in target else target
    netloc = literal if port == default_port else f"{literal}:{port}"
    if "@" in parts.netloc:
        # basic auth in the URL stays; only the host becomes the resolved address.
        netloc = parts.netloc.rsplit("@", 1)[0] + "@" + netloc
    pinned = urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))
    # an IPv6 host name needs brackets, otherwise the Host header is ambiguous
    header_host = f"[{host}]" if ":" in host else host
    sni = header_host if scheme == "https" and not _is_ip_literal(host) else ""
    host_header = header_host if port == default_port else f"{header_host}:{port}"
    return pinned, sni, host_header


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


async def guarded_fetch(
    url: str,
    *,
    resolver=None,
    allow_private: bool | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    transport=None,
) -> tuple[int, str, str]:
    """Fetches (status, text, note) over checked hops — every redirect on its own.

    ``follow_redirects=True`` would be the bug itself here: a 302 onto loopback
    is exactly the attack the entry check has nothing against. So redirects are
    followed by hand, each hop re-checked, and the count is capped.

    ``transport`` is only the test hook for the request path without a network;
    in production httpx decides.
    """
    import httpx

    current = (url or "").strip()
    target = ""
    for _hop in range(MAX_REDIRECT_HOPS + 1):
        allowed, decision, addresses = _evaluate(
            current, allow_private=allow_private, resolver=resolver
        )
        if not allowed:
            return 0, f"[refused] {decision}", decision
        target = decision
        pinned_url, sni, host_header = pinned_request(current, addresses)
        collected = bytearray()
        truncated = False
        try:
            client_kwargs = {"timeout": timeout, "follow_redirects": False}
            if transport is not None:
                client_kwargs["transport"] = transport
            async with httpx.AsyncClient(**client_kwargs) as client:
                request = client.build_request("GET", pinned_url, headers={"Host": host_header})
                if sni:
                    # TLS validates against the host name, TCP goes to the checked address.
                    request.extensions["sni_hostname"] = sni
                response = await client.send(request, stream=True)
                try:
                    status = int(response.status_code)
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("location") or ""
                        if not location:
                            return status, "", "Redirect carried no target."
                        current = urljoin(current, location)
                        continue
                    async for chunk in response.aiter_bytes():
                        collected += chunk
                        if len(collected) >= max_bytes:
                            truncated = True
                            break
                finally:
                    await response.aclose()
        except Exception as exc:  # noqa: BLE001 — the channel returns lines, not stack traces
            return 0, f"[error] {type(exc).__name__}: {exc}", f"{target}: {type(exc).__name__}"
        text = bytes(collected).decode("utf-8", errors="replace")
        # The note is for things that stand out, not for every healthy request:
        # a success stays an empty line, otherwise the caller reads warnings everywhere.
        if truncated:
            return status, text[:max_bytes], f"{target}: answer capped at {max_bytes} bytes."
        return status, text, ""
    return 0, "[error] too many redirects.", (
        f"{MAX_REDIRECT_HOPS} redirects exceeded — last hop {current}"
    )
