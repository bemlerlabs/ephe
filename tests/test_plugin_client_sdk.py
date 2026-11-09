"""The page SDK: one file, storage, a tool call, and the types a strict checker accepts.

A plugin page loads `ephe.js` from its own mount. The file is the build's copy.
A page that ships a file of the same name does not replace it. Storage names a
key, never a path, and asking does not create the state folder. A tool call
runs only a tool this bundle owns, and it still meets the chat approval gate.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SDK = ROOT / "sdk" / "ephe.js"
TYPES = ROOT / "sdk" / "ephe.d.ts"
CHECK = ROOT / "sdk" / "check.ts"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    from core import plugin_runtime
    from fastapi.testclient import TestClient
    from server.main import create_app

    plugin_runtime.invalidate_ownership_cache()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client
    plugin_runtime.invalidate_ownership_cache()


def test_a_missing_key_reads_null_and_creates_no_folder(client, tmp_path):
    response = client.get("/api/plugins/web-research/client/storage", params={"key": "note"})

    assert response.status_code == 200
    assert response.json() == {"value": None, "present": False}
    assert not (tmp_path / "cfg" / "mcp" / "homes").exists()


def test_a_stored_value_roundtrips_and_null_removes_it(client):
    saved = client.put(
        "/api/plugins/web-research/client/storage",
        json={"key": "note", "value": {"n": 1}},
    )
    assert saved.status_code == 200
    assert saved.json()["present"] is True

    read = client.get("/api/plugins/web-research/client/storage", params={"key": "note"})
    assert read.json() == {"value": {"n": 1}, "present": True}

    cleared = client.put(
        "/api/plugins/web-research/client/storage",
        json={"key": "note", "value": None},
    )
    assert cleared.json()["present"] is False
    again = client.get("/api/plugins/web-research/client/storage", params={"key": "note"})
    assert again.json()["present"] is False


def test_a_key_with_a_slash_is_the_registered_invalid_request(client):
    response = client.put(
        "/api/plugins/web-research/client/storage",
        json={"key": "a/b", "value": 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["reason_code"] == "invalid_request"


def test_an_unknown_bundle_is_the_registered_plugin_unknown(client):
    response = client.get("/api/plugins/no-such-bundle/client/storage", params={"key": "note"})
    assert response.status_code == 404
    assert response.json()["error"]["reason_code"] == "plugin_unknown"


def test_a_tool_this_bundle_does_not_own_is_refused(client):
    response = client.post(
        "/api/plugins/web-research/client/tool",
        json={"name": "run_shell", "arguments": {"command": "pwd"}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["reason_code"] == "tool_not_available"


def test_a_tool_this_bundle_owns_still_meets_the_approval_gate(client, monkeypatch):
    called: list[str] = []

    async def fake_execute(name, arguments, policy=None):
        called.append(name)
        return "ran-marker"

    monkeypatch.setattr("core.tools.registry.execute_tool", fake_execute)
    monkeypatch.setattr(
        "core.tools.approval.chat_tool_requires_confirm",
        lambda name, policy=None: True,
    )
    response = client.post(
        "/api/plugins/web-research/client/tool",
        json={"name": "web_search", "arguments": {"query": "ephe"}},
    )
    assert response.status_code == 200
    assert called == []
    assert "[TOOL-DENIED]" in response.json()["result"]
    assert "web_search" in response.json()["result"]


def test_the_mount_serves_the_build_sdk_and_ignores_a_shadow(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    plugin = config / "plugins" / "acme-countdown"
    (plugin / "ui").mkdir(parents=True)
    (plugin / "ui" / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    (plugin / "ui" / "ephe.js").write_text("shadow", encoding="utf-8")
    manifest = {
        "manifest_version": 1,
        "name": "acme-countdown",
        "version": "1.0.0",
        "description": "A surface that tries to replace the sdk",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [],
            "ui": {
                "type": "floating-window",
                "entry": "ui/index.html",
                "title": "Countdown",
                "capabilities": [],
            },
        },
    }
    (plugin / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    from core import plugin_runtime
    from fastapi.testclient import TestClient
    from server.main import create_app

    plugin_runtime.invalidate_ownership_cache()
    with TestClient(create_app()) as test_client:
        minted = test_client.post(
            "/api/plugins/acme-countdown/surface-token",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert minted.status_code == 200, minted.text
        nonce = minted.json()["surface"]
        response = test_client.get(f"/api/plugins/ui/acme-countdown/{nonce}/ephe.js")
    plugin_runtime.invalidate_ownership_cache()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.content == SDK.read_bytes()
    assert b"shadow" not in response.content


def test_the_sdk_file_names_the_three_operations_and_the_guide_names_them():
    text = SDK.read_text(encoding="utf-8")
    assert "callTool" in text
    assert "subscribe" in text
    guide = (ROOT / "docs" / "PLUGIN_SDK.md").read_text(encoding="utf-8")
    assert "ephe.storage.get" in guide
    assert "ephe.callTool" in guide
    assert "ephe.subscribe" in guide
    assert "docs/PLUGINS.md" in guide


def test_the_sdk_types_pass_the_strict_checker():
    tsc = ROOT / "app" / "node_modules" / ".bin" / "tsc"
    assert tsc.is_file(), "the app toolchain carries the type checker"
    assert TYPES.is_file() and CHECK.is_file()
    result = subprocess.run(
        [
            str(tsc),
            "--strict",
            "--noEmit",
            "--pretty",
            "false",
            "--target",
            "ES2022",
            "--lib",
            "DOM,ES2022",
            "--module",
            "nodenext",
            "--moduleResolution",
            "nodenext",
            str(CHECK),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
