"""PE2E — a click in the surface is the consent the chat gate asks for.

The measured defect: ``POST /api/plugins/{id}/client/tool`` reached the chat
approval gate with no policy in scope, so ``confirm_for_chat`` answered
``no_approval_channel`` and *every* tool a surface owns was unusable although the
reader had just clicked in that surface. The proof that the call comes from that
surface already exists — the mount credential
``POST /api/plugins/{id}/surface-token`` mints — so the route accepts it and the
call runs as user-confirmed, with the same mode, path and plugin rules in force.

The boundary is pinned from both sides. With a live credential for *this* bundle
the tool runs and leaves a ``surface-consent`` line; without one the answer is
exactly today's denial. A credential minted for another bundle, an expired one, a
tool of another bundle, a switched-off bundle, a protected root and a
credential-shaped file are all still refused, and a mode that blocks the tool
blocks it here too.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tools.chat_gate import DENIAL_PREFIX, confirm_for_surface  # noqa: E402

PLUGIN_ID = "acme-ticker"
#: A second installed bundle. A credential is minted for it, never used by it, so the
#: plugin binding — not the value — is what the refusal is measured against.
PEER_ID = "acme-peers"
READ_TOOL = "tick"
WRITE_TOOL = "pulse"
SURFACE_HEADER = "X-Surface-Token"

def _manifest(name: str, *, tools: bool) -> dict:
    manifest = {
        "manifest_version": 2,
        "name": name,
        "version": "1.0.0",
        "description": f"The {name} bundle.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "permissions": {"tool_families": ["read", "write"], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [],
            "tools": [],
            "ui": {
                "type": "floating-window",
                "entry": "ui/index.html",
                "title": "Ticker",
                "capabilities": [],
            },
        },
    }
    if tools:
        manifest["components"]["tools"] = [
            {
                "name": READ_TOOL,
                "entry": "handlers.py:read",
                "family": "read",
                "description": "Reads the count.",
            },
            {
                "name": WRITE_TOOL,
                "entry": "handlers.py:write",
                "family": "write",
                "description": "Sets the count.",
            },
        ]
    return manifest

def _home(tmp_path: Path, monkeypatch) -> Path:
    """Two installed bundles: the one whose tool runs, and a peer for a foreign mint."""
    config = tmp_path / "ephe-home"
    for name, tools in ((PLUGIN_ID, True), (PEER_ID, False)):
        plugin = config / "plugins" / name
        (plugin / "ui").mkdir(parents=True)
        (plugin / "ui" / "index.html").write_text(
            "<!doctype html><title>ticker</title>", encoding="utf-8"
        )
        (plugin / "handlers.py").write_text(
            "def read(arguments, state_dir):\n"
            "    return 'ok'\n"
            "def write(arguments, state_dir):\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        (plugin / "ephe-plugin.json").write_text(
            json.dumps(_manifest(name, tools=tools)), encoding="utf-8"
        )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    return config

@pytest.fixture()
def client(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()

@pytest.fixture()
def audit_rows(tmp_path, monkeypatch):
    """The stored audit lines, read the way the product's own reader reads them."""
    from core import audit_log

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")

    def rows(kind: str = "approval") -> list[dict]:
        return audit_log.tail(100, kind=kind)

    return rows

@pytest.fixture()
def ran(monkeypatch):
    """The executor as a recorder: the tool's own body has no part in this decision."""
    calls: list[tuple] = []

    async def _execute(name, arguments, policy=None):
        calls.append((name, dict(arguments), policy))
        return "ran-marker"

    monkeypatch.setattr("core.tools.registry.execute_tool", _execute)
    return calls

def _mint(client, plugin_id: str = PLUGIN_ID) -> str:
    minted = client.post(f"/api/plugins/{plugin_id}/surface-token", json={})
    assert minted.status_code == 200, minted.text
    return minted.json()["surface"]

def _call_tool(
    client, name: str, arguments: dict | None = None, *, token: str = "", in_body: bool = False
):
    headers = {SURFACE_HEADER: token} if token and not in_body else {}
    body: dict = {"name": name, "arguments": arguments or {}}
    if token and in_body:
        body["surface"] = token
    return client.post(f"/api/plugins/{PLUGIN_ID}/client/tool", json=body, headers=headers)

def _run(coro):
    return asyncio.run(coro)

def _code(denial) -> str:
    return str(getattr(denial, "code", ""))

def test_without_a_credential_the_tool_is_denied_as_before(client, ran):
    """The defect is not fixed by widening the route for everybody who asks."""
    response = _call_tool(client, READ_TOOL, {"unit": "s"})

    assert response.status_code == 200, response.text
    assert ran == []
    body = response.json()["result"]
    assert body.startswith(DENIAL_PREFIX)
    assert READ_TOOL in body
    assert "no approval channel is active" in body

def test_the_denial_of_a_call_without_a_credential_is_still_the_chat_gate(audit_rows):
    approved, denial = _run(confirm_for_surface(READ_TOOL, {"unit": "s"}, plugin=PLUGIN_ID))

    assert approved is False
    assert _code(denial) == "no_approval_channel"
    row = audit_rows()[0]
    assert row["status"] == "chat-gate" and row["decision"] == "denied"

def test_a_live_credential_runs_the_tool_and_records_surface_consent(client, ran, audit_rows):
    token = _mint(client)

    response = _call_tool(client, READ_TOOL, {"unit": "s"}, token=token)

    assert response.status_code == 200, response.text
    assert response.json() == {"result": "ran-marker"}
    assert ran == [(READ_TOOL, {"unit": "s"}, None)]
    row = audit_rows()[0]
    assert row["tool"] == READ_TOOL
    assert row["decision"] == "approved"
    assert row["status"] == "surface-consent"
    assert PLUGIN_ID in row["detail"]

def test_the_credential_may_ride_the_body_field_the_mint_route_reads(client, ran):
    """`POST .../surface-token` renews from a body field; the same shape works here."""
    token = _mint(client)

    response = _call_tool(client, READ_TOOL, {"unit": "s"}, token=token, in_body=True)

    assert response.status_code == 200, response.text
    assert response.json() == {"result": "ran-marker"}
    assert ran

def test_a_credential_with_no_bundle_named_is_not_a_consent(audit_rows):
    from server import plugin_surface_nonce

    token = plugin_surface_nonce.mint_surface_nonce(PLUGIN_ID).nonce

    approved, denial = _run(confirm_for_surface(READ_TOOL, {}, plugin="", surface=token))

    assert approved is False
    assert _code(denial) == "surface_token_refused"

def test_a_credential_minted_for_another_bundle_is_refused(client, ran):
    from server import plugin_surface_nonce

    foreign = plugin_surface_nonce.mint_surface_nonce(PEER_ID).nonce

    response = _call_tool(client, READ_TOOL, {"unit": "s"}, token=foreign)

    assert response.status_code == 200, response.text
    assert ran == []
    assert response.json()["result"].startswith(DENIAL_PREFIX)

def test_a_credential_for_another_bundle_is_not_a_consent_at_the_gate(audit_rows):
    from server import plugin_surface_nonce

    foreign = plugin_surface_nonce.mint_surface_nonce(PEER_ID).nonce

    approved, denial = _run(confirm_for_surface(READ_TOOL, {}, plugin=PLUGIN_ID, surface=foreign))

    assert approved is False
    assert _code(denial) == "surface_token_refused"

def test_an_expired_credential_is_refused(client, ran, monkeypatch):
    from server import plugin_surface_nonce

    token = _mint(client)
    started = plugin_surface_nonce.surface_clock()
    monkeypatch.setattr(
        plugin_surface_nonce,
        "surface_clock",
        lambda: started + plugin_surface_nonce.SURFACE_NONCE_TTL_SECONDS + 1,
    )

    response = _call_tool(client, READ_TOOL, {"unit": "s"}, token=token)

    assert response.status_code == 200, response.text
    assert ran == []
    assert response.json()["result"].startswith(DENIAL_PREFIX)

def test_an_unknown_credential_is_refused(client, ran):
    response = _call_tool(client, READ_TOOL, {"unit": "s"}, token="not-a-live-nonce")

    assert response.status_code == 200, response.text
    assert ran == []
    assert response.json()["result"].startswith(DENIAL_PREFIX)

def test_a_tool_of_another_bundle_is_refused_with_a_live_credential(client, ran):
    token = _mint(client)

    response = _call_tool(client, "run_shell", {"command": "pwd"}, token=token)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "tool_not_available"
    assert ran == []

def test_a_switched_off_bundle_refuses_even_with_a_live_credential(client, ran, tmp_path):
    from core import plugin_runtime

    token = _mint(client)
    (tmp_path / "ephe-home" / "plugin-state.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "pause_all": False,
                "plugins": {PLUGIN_ID: {"user": {"committed": "disabled"}}},
            }
        ),
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()

    response = _call_tool(client, READ_TOOL, {"unit": "s"}, token=token)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "tool_not_available"
    assert ran == []

def test_the_plugin_read_only_brake_stops_the_call_before_any_credential(client, ran, monkeypatch):
    from core import plugin_switch_policy

    monkeypatch.setattr(plugin_switch_policy, "read_only", lambda: True)

    response = _call_tool(client, READ_TOOL, {"unit": "s"}, token=_mint(client))

    assert response.status_code == 423, response.text
    assert ran == []

def test_a_mode_that_blocks_the_tool_blocks_it_with_a_credential(audit_rows):
    """Architect (plan) is read-only; a write-family tool is refused before it runs."""
    from core.tools.session_ctx import reset_current_mode, set_current_mode
    from server import plugin_surface_nonce

    token = plugin_surface_nonce.mint_surface_nonce(PLUGIN_ID).nonce
    held = set_current_mode("architect")
    try:
        approved, denial = _run(
            confirm_for_surface(WRITE_TOOL, {}, plugin=PLUGIN_ID, surface=token)
        )
    finally:
        reset_current_mode(held)

    assert approved is False
    assert _code(denial) == "mode_read_only"

def test_a_protected_root_is_refused_even_with_a_live_credential(client, ran):
    token = _mint(client)

    response = _call_tool(client, READ_TOOL, {"path": "~/.ssh/id_rsa"}, token=token)

    assert response.status_code == 200, response.text
    assert ran == []
    assert "protected root" in response.json()["result"]

def test_a_credential_shaped_file_keeps_the_dialog_a_surface_cannot_open(audit_rows):
    """The click is not a dialog about a path the page chose — that one stays refused."""
    from server import plugin_surface_nonce

    token = plugin_surface_nonce.mint_surface_nonce(PLUGIN_ID).nonce

    approved, denial = _run(
        confirm_for_surface(READ_TOOL, {"path": "/tmp/workspace/.env"}, plugin=PLUGIN_ID, surface=token)
    )

    assert approved is False
    assert _code(denial) == "no_approval_channel"

def test_a_tool_that_never_asked_still_runs_without_a_credential(audit_rows):
    """No regression for the read-only half: it never needed the dialog."""
    approved, denial = _run(confirm_for_surface("read_file", {"path": "README.md"}, plugin=PLUGIN_ID))

    assert approved is True
    assert denial == ""

def test_a_stale_credential_does_not_refuse_a_tool_that_never_asked(audit_rows):
    """A page holding a dead credential must not lose the read-only half it always had."""
    approved, denial = _run(
        confirm_for_surface("read_file", {"path": "README.md"}, plugin=PLUGIN_ID, surface="stale")
    )

    assert approved is True
    assert denial == ""


def test_a_failing_tool_does_not_name_its_exception(client, monkeypatch) -> None:
    """CodeQL py/stack-trace-exposure: the page gets a code, the log gets the class."""
    async def boom(*_a, **_k):
        raise KeyError("secret-internals")

    from types import SimpleNamespace

    monkeypatch.setattr("core.tools.registry.execute_tool", boom, raising=True)
    monkeypatch.setattr(
        "core.plugin_runtime.tool_gate",
        lambda name: SimpleNamespace(plugin=PLUGIN_ID, visible=True),
        raising=True,
    )
    monkeypatch.setattr(
        "core.tools.session_ctx.get_current_policy", lambda *a, **k: object(), raising=True
    )
    answer = client.post(
        f"/api/plugins/{PLUGIN_ID}/client/tool",
        json={"name": "read", "arguments": {"path": "notes.txt"}},
    )
    assert answer.status_code >= 400, answer.text
    body = answer.text
    assert "KeyError" not in body
    assert "secret-internals" not in body


def test_a_failing_tool_never_leaks_its_class_path_or_message(client, monkeypatch) -> None:
    """CWE-209/CWE-497: the answer is the route's own code, the log keeps the rest."""
    async def boom(*_a, **_k):
        raise FileNotFoundError("/Users/someone/.ephe/secret/engine.key missing")

    from types import SimpleNamespace

    monkeypatch.setattr("core.tools.registry.execute_tool", boom, raising=True)
    monkeypatch.setattr(
        "core.plugin_runtime.tool_gate",
        lambda name: SimpleNamespace(plugin=PLUGIN_ID, visible=True),
        raising=True,
    )
    monkeypatch.setattr(
        "core.tools.session_ctx.get_current_policy", lambda *a, **k: object(), raising=True
    )
    answer = client.post(
        f"/api/plugins/{PLUGIN_ID}/client/tool",
        json={"name": "read", "arguments": {"path": "notes.txt"}},
    )
    body = answer.text
    assert answer.status_code in (409, 500), answer.text
    assert "FileNotFoundError" not in body
    assert "/Users/someone" not in body
    assert "engine.key" not in body
    assert "tool_failed" in body
    assert answer.json()["error"]["reason_params"] == {"plugin": PLUGIN_ID}
