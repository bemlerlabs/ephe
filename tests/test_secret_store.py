"""Y5 — the vault: values stay in, presence and mode travel out."""
from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import secret_store  # noqa: E402


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(secret_store, "_store_keyring", lambda name, value: False)
    monkeypatch.setattr(secret_store, "_load_keyring", lambda name: None)
    monkeypatch.setattr(secret_store, "_delete_keyring", lambda name: None)
    return tmp_path


class TestStore:
    def test_a_value_roundtrips_and_the_file_is_owner_only(self, vault):
        held = secret_store.put("WEB_SEARCH_KEY", "sk-test")
        assert held == secret_store.MODE_FILE
        assert secret_store.get("WEB_SEARCH_KEY") == "sk-test"
        path = secret_store.secrets_dir() / "WEB_SEARCH_KEY"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_status_names_presence_and_mode_and_nothing_else(self, vault):
        secret_store.put("TOKEN_A", "value-a")
        rows = secret_store.status(["TOKEN_A", "TOKEN_B"])
        assert rows == [
            {"name": "TOKEN_A", "present": True, "mode": secret_store.MODE_FILE},
            {"name": "TOKEN_B", "present": False, "mode": ""},
        ]
        assert "value-a" not in repr(rows)

    def test_a_name_that_is_not_a_variable_name_is_refused(self, vault):
        for bad in ("../escape", "lower", "1ABC", ""):
            with pytest.raises(ValueError):
                secret_store.put(bad, "x")
        assert secret_store.get("../escape") is None
        assert secret_store.status(["../escape"]) == []

    def test_delete_removes_the_value(self, vault):
        secret_store.put("TOKEN_A", "value-a")
        secret_store.delete("TOKEN_A")
        assert secret_store.get("TOKEN_A") is None
        assert secret_store.mode("TOKEN_A") == ""

    def test_env_for_returns_only_the_names_asked_for(self, vault):
        secret_store.put("A_KEY", "one")
        secret_store.put("B_KEY", "two")
        assert secret_store.env_for(["A_KEY"]) == {"A_KEY": "one"}


class TestRoute:
    def _client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
        monkeypatch.setattr(secret_store, "_store_keyring", lambda name, value: False)
        monkeypatch.setattr(secret_store, "_load_keyring", lambda name: None)
        from fastapi.testclient import TestClient

        from server.main import create_app

        return TestClient(create_app())

    def test_a_write_without_the_marker_is_refused(self, tmp_path, monkeypatch):
        with self._client(tmp_path, monkeypatch) as client:
            r = client.post("/api/secrets", json={"name": "A_KEY", "value": "x"})
        assert r.status_code == 403

    def test_a_write_answers_presence_and_mode_only(self, tmp_path, monkeypatch):
        with self._client(tmp_path, monkeypatch) as client:
            r = client.post(
                "/api/secrets",
                json={"name": "A_KEY", "value": "secret-value"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            status = client.get("/api/secrets/status", params={"names": "A_KEY"})
        assert r.status_code == 200, r.text
        assert r.json() == {"name": "A_KEY", "present": True, "mode": "file_0600"}
        assert "secret-value" not in r.text
        assert status.json()["names"][0]["present"] is True

    def test_an_empty_value_is_refused(self, tmp_path, monkeypatch):
        with self._client(tmp_path, monkeypatch) as client:
            r = client.post(
                "/api/secrets",
                json={"name": "A_KEY", "value": "  "},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert r.status_code == 400
        assert r.json()["error"]["detail"]["code"] == "secret_refused"

    def test_the_declaration_names_the_connector_and_its_variables(self, tmp_path, monkeypatch):
        spec = "stdio:npx -y web-search"
        with self._client(tmp_path, monkeypatch) as client:
            refused = client.post("/api/mcp/env", json={"spec": spec, "names": ["A_KEY"]})
            bad = client.post(
                "/api/mcp/env",
                json={"spec": spec, "names": ["not-a-name"]},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            ok = client.post(
                "/api/mcp/env",
                json={"spec": spec, "names": ["A_KEY"]},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            listed = client.get("/api/mcp/env")
        assert refused.status_code == 403
        assert bad.status_code == 400
        assert ok.status_code == 200, ok.text
        assert listed.json()["servers"] == {spec: ["A_KEY"]}


class TestChild:
    def test_the_child_receives_only_the_declared_names(self, vault, monkeypatch):
        secret_store.put("A_KEY", "one")
        secret_store.put("B_KEY", "two")
        from core.tools import mcp_process

        link = mcp_process.StdioLink("echo", [], env_names=["A_KEY"])
        env = link._child_env(None)
        assert env["A_KEY"] == "one"
        assert "B_KEY" not in env

    def test_a_link_without_names_gets_no_vault_values(self, vault):
        secret_store.put("A_KEY", "one")
        from core.tools import mcp_process

        link = mcp_process.StdioLink("echo", [])
        assert "A_KEY" not in link._child_env(None)
