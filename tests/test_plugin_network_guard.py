"""GAP-06 / NET-01..04 — the outbound guard for remote MCP connectors.

The guard refuses plain HTTP, loopback, private, link-local and metadata
addresses, resolves a name once and pins the request to that checked address
while keeping the original host for the Host header and TLS SNI. Requests do not
follow redirects.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.network_guard import NetworkGuardError, prepare_http_target


def _addresses(*addresses: str):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in addresses
    ]


def test_loopback_private_link_local_and_metadata_are_refused() -> None:
    for url in (
        "https://127.0.0.1/mcp",
        "https://10.0.0.1/mcp",
        "https://192.168.1.20/mcp",
        "https://169.254.169.254/latest/meta-data",
        "https://100.100.100.200/mcp",
        "https://[::1]/mcp",
        "https://[fd00:ec2::254]/mcp",
    ):
        with pytest.raises(NetworkGuardError):
            prepare_http_target(url)


def test_plain_http_to_a_public_host_is_refused() -> None:
    with pytest.raises(NetworkGuardError) as err:
        prepare_http_target("http://example.com/mcp")
    assert "https" in str(err.value)


def test_userinfo_is_refused() -> None:
    with pytest.raises(NetworkGuardError) as err:
        prepare_http_target("https://user:secret@example.com/mcp")
    assert "credential" in str(err.value).lower()


def test_a_name_resolving_to_a_private_address_is_refused(monkeypatch) -> None:
    import core.network_guard as guard

    monkeypatch.setattr(
        guard.socket, "getaddrinfo", lambda *args, **kwargs: _addresses("127.0.0.1")
    )
    with pytest.raises(NetworkGuardError):
        prepare_http_target("https://mcp.example.com/mcp")


def test_a_public_name_is_pinned_to_the_checked_address(monkeypatch) -> None:
    import core.network_guard as guard

    monkeypatch.setattr(
        guard.socket,
        "getaddrinfo",
        lambda *args, **kwargs: _addresses("93.184.216.34"),
    )
    url, host_header, sni = prepare_http_target(
        "https://mcp.example.com/tenant/mcp?x=1"
    )
    assert url == "https://93.184.216.34/tenant/mcp?x=1"
    assert host_header == "mcp.example.com"
    assert sni == "mcp.example.com"


def test_an_ip_literal_keeps_its_own_host_and_has_no_sni() -> None:
    url, host_header, sni = prepare_http_target("https://93.184.216.34/mcp")
    assert url == "https://93.184.216.34/mcp"
    assert host_header == "93.184.216.34"
    assert sni == ""


def test_a_bare_mcp_spec_defaults_to_https() -> None:
    from core.tools.mcp_client import parse_server_spec

    spec = parse_server_spec("mcp.example.com/mcp")
    assert spec.transport == "http"
    assert spec.endpoint == "https://mcp.example.com/mcp"
