"""I6-6 — the network area shows the actual state, not the documentation.

There was no answer to "what is Ephe hanging on to right now?": bind and port live
only in the process environment, and the LAN token is created anew on every start.
The endpoint therefore must not know anything it does not read — this test pins
exactly the four things a page like that lies about most easily.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from core.tools.base import _get_allowed_roots  # noqa: E402
from server.routes.network import network_status  # noqa: E402


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("EPHE_HOST", "EPHE_PORT", "EPHE_LAN", "EPHE_SETUP_MODE",
                 "EPHE_PROXY_PORTS", "EPHE_FETCH_ALLOW_PRIVATE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_ohne_LAN_start_haengt_ephe_nur_am_Geraet(clean_env) -> None:
    clean_env.setenv("EPHE_HOST", "127.0.0.1")
    clean_env.setenv("EPHE_PORT", "8765")
    status = network_status()
    assert status["bind_host"] == "127.0.0.1"
    assert status["bind_port"] == 8765
    assert status["lan"] is False
    assert status["allow_private_fetches"] is False
    assert status["proxy_extra_ports"] == []


def test_ein_0000_Start_ist_LAN_modus_auch_ohne_Schalter(clean_env) -> None:
    """The CLI spawn passes `--host 0.0.0.0` but never `--lan` — the view has to draw
    the same conclusion as the middleware, not one of its own."""
    clean_env.setenv("EPHE_HOST", "0.0.0.0")
    clean_env.setenv("EPHE_PORT", "8899")
    status = network_status()
    assert status["lan"] is True
    assert status["bind_port"] == 8899


def test_ausdruckliche_Freigaben_erscheinen_nur_wenn_gesetzt(clean_env) -> None:
    clean_env.setenv("EPHE_PROXY_PORTS", "6379, 11434 ,")
    clean_env.setenv("EPHE_FETCH_ALLOW_PRIVATE", "1")
    status = network_status()
    assert status["proxy_extra_ports"] == ["6379", "11434"]
    assert status["allow_private_fetches"] is True


def test_die_Wurzeln_sind_die_der_Datei_Route(clean_env) -> None:
    """No second list of granted folders — the view shows what the route
    actually checks."""
    status = network_status()
    assert status["file_roots"] == [str(r) for r in _get_allowed_roots()]
    assert status["file_roots"], "ohne Freigabe wäre die Zeile eine Behauptung"


def test_get_network_status_liefert_den_ist_zustand(clean_env) -> None:
    from fastapi.testclient import TestClient

    from server.main import app

    clean_env.setenv("EPHE_HOST", "127.0.0.1")
    clean_env.setenv("EPHE_PORT", "8765")
    body = TestClient(app).get("/api/network/status").json()
    assert body["bind_host"] == "127.0.0.1"
    assert set(body) == {
        "bind_host", "bind_port", "lan", "setup_mode", "token_required",
        "file_roots", "proxy_extra_ports", "allow_private_fetches",
    }
