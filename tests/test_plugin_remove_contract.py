"""PE2E finding 8d — removing a bundle has one semantic, and the answer is coded.

`core/marketplace_service.remove` switched an active bundle off and deleted it in one
200. The lower path (`plugin_versions.remove_plugin`) refuses an enabled bundle with
`plugin_enabled`, so the product spoke two semantics for one gesture and the surface
could not tell the reader that a switch had been flipped. The route now answers
`still_active` with the state, and `?force=true` is the explicit permission that
deactivates first. The answer names what left the disk and what stayed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.plugin_bundle import mark_installed, write_bundle
import json


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core import audit_log, plugin_runtime
    from core.skills import invalidate_skill_cache

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()


@pytest.fixture()
def client(device):
    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client


def _install(device: Path, name: str = "alpha", *, enabled: bool = False) -> Path:
    bundle = write_bundle(device / "plugins", name)
    mark_installed(name, enabled=enabled)
    return bundle


def _state_row(device: Path, name: str) -> dict:
    import json

    document = json.loads((device / "plugin-state.json").read_text(encoding="utf-8"))
    return document["plugins"][name]["user"]


def test_removing_an_enabled_bundle_is_refused_with_its_state(client, device) -> None:
    bundle = _install(device, enabled=True)

    response = client.post("/api/market/remove", json={"name": "alpha"})

    assert response.status_code == 409, response.text
    detail = response.json()["error"]["detail"]
    assert detail["code"] == "still_active"
    assert detail["state"] == "enabled"
    assert detail["version"] == "0.1.0"
    assert bundle.is_dir()
    assert _state_row(device, "alpha")["committed"] == "enabled"
    view = client.get("/api/plugins").json()
    row = next(item for item in view["installed"] if item["name"] == "alpha")
    assert row["state"] == "enabled"


def test_force_is_the_explicit_permission_that_deactivates_first(client, device) -> None:
    from core import plugin_state

    _install(device, enabled=True)
    state_home = plugin_state.state_home("alpha")
    state_home.mkdir(parents=True, exist_ok=True)
    (state_home / "client-store.json").write_text("{}", encoding="utf-8")

    response = client.post("/api/market/remove?force=true", json={"name": "alpha"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "removed"
    assert body["state"] == "enabled"
    assert body["deactivated"] is True
    assert body["removed"]["bundle"] is True
    # The marketplace path writes a registry row for the bundle, so the answer names it.
    assert body["removed"]["registry"] is True
    assert body["removed"]["mount"] is False
    # The lifecycle row goes with the bundle (removal clears every record); the answer
    # reports the state after it, so this is false and the file carries no row for it.
    assert body["remains"]["state_record"] is False
    assert body["remains"]["data"] is True
    assert body["data_removed"] is False
    assert not (device / "plugins" / "alpha").exists()
    raw = json.loads((device / "plugin-state.json").read_text(encoding="utf-8"))
    assert "alpha" not in raw.get("plugins", {})
    view = client.get("/api/plugins").json()
    assert "alpha" not in [row["name"] for row in view["installed"]]


def test_a_disabled_bundle_removes_without_a_second_permission(client, device) -> None:
    _install(device, enabled=False)

    body = client.post("/api/market/remove", json={"name": "alpha"}).json()

    assert body["status"] == "removed"
    assert body["deactivated"] is False
    # The lifecycle row goes with the bundle (removal clears every record); the answer
    # reports the state after it, so this is false and the file carries no row for it.
    assert body["remains"]["state_record"] is False


def test_the_mount_record_leaves_with_the_bundle(client, device) -> None:
    _install(device, enabled=True)
    from core import plugin_runtime

    plugin_runtime.lifecycle().mount("alpha", actor="test", reason="fixture")
    assert "alpha" in plugin_runtime.lifecycle().mount_records()

    body = client.post("/api/market/remove?force=true", json={"name": "alpha"}).json()

    assert body["removed"]["mount"] is True
    assert "alpha" not in plugin_runtime.lifecycle().mount_records()


def test_keep_data_is_the_default_and_delete_data_removes_both_folders(
    client, device
) -> None:
    from core import plugin_state

    _install(device, enabled=False)
    legacy = device / "plugin-data" / "alpha"
    legacy.mkdir(parents=True)
    (legacy / "x.json").write_text("{}", encoding="utf-8")
    state_home = plugin_state.state_home("alpha")
    state_home.mkdir(parents=True, exist_ok=True)
    (state_home / "client-store.json").write_text("{}", encoding="utf-8")

    kept = client.post("/api/market/remove", json={"name": "alpha"}).json()

    assert kept["data_removed"] is False
    assert kept["remains"]["data"] is True
    assert legacy.is_dir()
    assert state_home.is_dir()

    _install(device, enabled=False)
    (state_home / "client-store.json").write_text("{}", encoding="utf-8")
    deleted = client.post(
        "/api/market/remove", json={"name": "alpha", "delete_data": True}
    ).json()

    assert deleted["data_removed"] is True
    assert deleted["removed"]["data"] is True
    assert deleted["remains"]["data"] is False
    assert not legacy.exists()
    assert not state_home.exists()


def test_the_creator_draft_is_named_as_remaining(client, device) -> None:
    _install(device, enabled=False)
    write_bundle(device / "creator" / "plugins", "alpha")

    body = client.post("/api/market/remove", json={"name": "alpha"}).json()

    assert body["remains"]["creator_draft"] is True
    assert (device / "creator" / "plugins" / "alpha").is_dir()


def test_an_unknown_name_is_not_installed(client, device) -> None:
    response = client.post("/api/market/remove", json={"name": "ghost"})

    assert response.status_code == 404
    assert response.json()["error"]["detail"]["code"] == "not_installed"


def test_a_bundled_plugin_is_not_removable(client, device) -> None:
    response = client.post("/api/market/remove", json={"name": "countdown"})

    assert response.status_code == 409
    assert response.json()["error"]["detail"]["code"] == "bundled_not_removable"
    assert (Path(__file__).resolve().parents[1] / "plugins" / "countdown").is_dir()