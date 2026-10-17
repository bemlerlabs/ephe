"""Regression: every 0.0.0.0 bind forces auth (fail-closed).

Root cause: `ephe start --lan` spawns run_server.py with --host 0.0.0.0
BUT without --lan (ephe_cli.py:735-746). Before the fix EPHE_LAN stayed
unset -> main.py:303 lan_mode=False -> AuthMiddleware never installed
(main.py:135) -> anyone on the Wi-Fi hit POST /api/shell (auto_approve) without a token.
"""
import os
import sys
from unittest.mock import patch

import run_server


def _lan_env_for(argv):
    """Run main() with the given argv (uvicorn/boot mocked) and
    return the resulting EPHE_LAN."""
    os.environ.pop("EPHE_LAN", None)
    try:
        with patch.object(sys, "argv", argv), \
             patch("run_server._bootstrap_engine_choice"), \
             patch("uvicorn.run"):
            run_server.main()
        return os.environ.get("EPHE_LAN")
    finally:
        # W19 hygiene: the bootstrap now reads EPHE_LAN fail-closed —
        # a leak into the following tests would tip their loopback start
        # into the LAN branch. Always clean up.
        os.environ.pop("EPHE_LAN", None)


def test_public_bind_forces_lan_auth():
    # Exactly the CLI spawn path: --host 0.0.0.0, NO --lan.
    assert _lan_env_for(["run_server.py", "--host", "0.0.0.0", "--port", "8765"]) == "1"


def test_localhost_stays_authless_offline_first():
    # Default operation stays tokenless (offline-first, localhost trusted).
    assert _lan_env_for(["run_server.py", "--host", "127.0.0.1", "--port", "8765"]) is None


def test_a_specific_lan_address_forces_lan_auth_too():
    """`--host 192.168.1.20` reaches the network exactly as `0.0.0.0` does.

    Arming the token only for the wildcard left that bind serving every /api route
    without one — the same fail-open, reached by naming an address instead.
    """
    assert _lan_env_for(["run_server.py", "--host", "192.168.1.20", "--port", "8765"]) == "1"


def test_ipv6_loopback_stays_authless():
    assert _lan_env_for(["run_server.py", "--host", "::1", "--port", "8765"]) is None


def test_explicit_lan_flag_still_works():
    assert _lan_env_for(["run_server.py", "--lan", "--port", "8765"]) == "1"


def test_the_ipv6_wildcard_forces_lan_auth():
    # `--host ::` reaches the same bind as `--host 0.0.0.0`: uvicorn hands it to the
    # OS as every address, so the token has to be forced here too.
    assert _lan_env_for(["run_server.py", "--host", "::", "--port", "8765"]) == "1"


def test_an_empty_host_forces_lan_auth():
    assert _lan_env_for(["run_server.py", "--host", "", "--port", "8765"]) == "1"
