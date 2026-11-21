"""The shell routes run a command only when the call says a person approved it.

The header guard next door proves the request came from a page that can set headers, which a
cross-origin form POST cannot. It does not prove anyone decided: a script that reuses our own
client, or a page whose origin we granted, sends the same header. `approved=true` is the
statement that a person pressed Run on this command, and the empty case comes first here
because a refused request must not reach the whitelist, the PTY, or the tool at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.main import create_app  # noqa: E402

XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client():
    return TestClient(create_app())


def test_a_command_without_the_explicit_approval_is_refused(client):
    r = client.post("/api/shell", json={"command": "echo should-not-run"}, headers=XHR_HEADERS)
    assert r.status_code == 403
    assert "approved" in r.json()["error"]["message"]


def test_the_refusal_runs_nothing_even_for_a_whitelisted_command(client, tmp_path):
    """`echo` is whitelisted, so the refusal has to come from the approval and not from the
    whitelist: the file the command would create is the proof that nothing ran."""
    witness = tmp_path / "witness.txt"
    r = client.post(
        "/api/shell",
        json={"command": f"touch {witness}"},
        headers=XHR_HEADERS,
    )
    assert r.status_code == 403
    assert not witness.exists()


def test_the_pty_route_asks_for_the_same_approval(client):
    r = client.post(
        "/api/shell/pty",
        json={"command": "echo should-not-run", "input": ""},
        headers=XHR_HEADERS,
    )
    assert r.status_code == 403
    assert "approved" in r.json()["error"]["message"]


def test_an_approved_command_still_runs(client):
    r = client.post(
        "/api/shell",
        json={"command": "echo approved-and-run", "approved": True},
        headers=XHR_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "approved-and-run" in r.json()["output"]
