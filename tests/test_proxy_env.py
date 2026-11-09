"""A bracketed IPv6 bypass must not stop a client from being built.

Measured on the installed 0.28.1 wheel: ``NO_PROXY`` is split on commas, and
``[::1]`` becomes a mount key whose port reads as ``:1]``. The rewrite runs
inside both client constructors. This file sets that exact list and requires
the guarded fetch to finish.
"""
from __future__ import annotations

import os
import subprocess
import sys

import httpx
import pytest

from core.net_guard import guarded_fetch
from core.proxy_env import normalize_proxy_environment
from tests.subprocess_env import hermetic_env

_NO_PROXY = "localhost,.localhost,127.0.0.1,127.0.0.0/8,[::1],::1"


def _resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def test_a_bracketed_entry_becomes_a_bare_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_PROXY", _NO_PROXY)
    monkeypatch.setenv("no_proxy", _NO_PROXY)

    normalize_proxy_environment()

    assert os.environ["NO_PROXY"] == "localhost,.localhost,127.0.0.1,127.0.0.0/8,::1,::1"
    assert os.environ["no_proxy"] == os.environ["NO_PROXY"]


def test_a_sync_client_builds_under_the_bracketed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_PROXY", _NO_PROXY)

    with httpx.Client() as client:
        assert client.trust_env is True

    assert "[::1]" not in os.environ["NO_PROXY"]


@pytest.mark.asyncio
async def test_guarded_fetch_finishes_under_the_bracketed_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_PROXY", _NO_PROXY)
    monkeypatch.setenv("no_proxy", _NO_PROXY)

    async def _send(self, request, stream=True):  # noqa: ARG001
        class _Response:
            status_code = 200
            headers: dict[str, str] = {}

            async def aiter_bytes(self):
                yield b"ok"

            async def aclose(self) -> None:
                return None

        return _Response()

    monkeypatch.setattr(httpx.AsyncClient, "send", _send)
    status, text, note = await guarded_fetch("https://example.com/ok", resolver=_resolver)

    assert status == 200
    assert text == "ok"
    assert note == ""


def test_core_loads_no_client_and_still_catches_a_list_set_afterwards() -> None:
    """GIVEN a fresh interpreter WHEN core loads THEN no HTTP client and no renderer load with it.

    The CLI startup budget counts both as heavy, and the client's own package
    imports the renderer. The rewrite still has to reach a client built later,
    so the constructor patch may not depend on the client being loaded first.
    """
    code = (
        "import os, sys\n"
        "import core\n"
        "assert 'httpx' not in sys.modules, 'core loaded the client'\n"
        "assert 'rich' not in sys.modules, 'core loaded the renderer'\n"
        "os.environ['NO_PROXY'] = 'localhost,[::1],::1'\n"
        "import httpx\n"
        "with httpx.Client() as client:\n"
        "    assert client.trust_env is True\n"
        "assert '[::1]' not in os.environ['NO_PROXY'], os.environ['NO_PROXY']\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=hermetic_env(PYTHONPATH=""),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
