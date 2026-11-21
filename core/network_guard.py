"""Outbound guard for remote MCP connectors (GAP-06).

Remote endpoints are HTTPS only. The host is resolved once, every address must
be public, and the request is pinned to the checked address while the original
host stays in the Host header and the TLS SNI. That removes the DNS-rebinding
window between a check and a later connection. Redirects are not followed, so an
Authorization header cannot travel to a second host.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

#: Networks that are never a remote MCP endpoint, including cloud metadata.
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "169.254.0.0/16",
        "100.64.0.0/10",
        "192.0.0.0/24",
        "198.18.0.0/15",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "fd00:ec2::254/128",
    )
)


class NetworkGuardError(ValueError):
    """The URL or one of its resolved addresses is not a permitted target."""


def _is_public(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    if not parsed.is_global:
        return False
    return not any(parsed in network for network in _BLOCKED_NETWORKS)


def prepare_http_target(url: str) -> tuple[str, str, str]:
    """Returns (pinned request URL, Host header, TLS SNI).

    The caller sends to the pinned address and keeps the original host in the
    header and SNI. An IP literal has no SNI.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise NetworkGuardError("remote MCP endpoints require https")
    if parts.username or parts.password:
        raise NetworkGuardError("the URL must not carry credentials")
    host = parts.hostname
    if not host:
        raise NetworkGuardError("the URL has no host")
    try:
        port = parts.port or 443
    except ValueError as exc:
        raise NetworkGuardError("the URL has an invalid port") from exc

    literal = ""
    try:
        literal = str(ipaddress.ip_address(host))
    except ValueError:
        literal = ""
    if literal:
        addresses = [literal]
    else:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise NetworkGuardError(f"cannot resolve {host}") from exc
        addresses = sorted({str(info[4][0]) for info in infos})
        if not addresses:
            raise NetworkGuardError(f"cannot resolve {host}")

    for address in addresses:
        if not _is_public(address):
            raise NetworkGuardError(f"address {address} is not public")

    pinned = addresses[0]
    netloc = f"[{pinned}]" if ":" in pinned else pinned
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    request_url = urlunsplit(
        ("https", netloc, parts.path or "/", parts.query, "")
    )
    return request_url, parts.netloc, "" if literal else host
