"""P1 — the lifecycle HTTP contract.

One PUT commits both directions, a stale ETag or version returns 409 with the
current state, a failed write is an error, the legacy POST delegates, and the
legacy master control maps onto pause all without rewriting per-plugin states.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core import audit_log, plugin_runtime
    from core.skills import invalidate_skill_cache

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()
    yield config, log
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()


@pytest.fixture()
def client(device):
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client


def _toggle(client, enabled: bool, **extra) -> dict:
    return client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": enabled, **extra},
    )


def test_put_disable_commits_and_returns_the_state(client) -> None:
    response = _toggle(client, False)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "disabled"
    assert body["enabled"] is False
    assert body["scope"] == "user"
    assert body["version"] == "1.1.0"
    assert response.headers["etag"] == body["etag"]

    view = client.get("/api/plugins").json()
    entry = next(item for item in view["public"] if item["name"] == "web-research")
    assert entry["enabled"] is False


def test_put_enables_again(client) -> None:
    assert _toggle(client, False).status_code == 200
    response = _toggle(client, True)
    assert response.status_code == 200
    assert response.json()["state"] == "enabled"
    assert response.json()["enabled"] is True


def test_an_idempotency_key_has_one_effect_and_one_audit_entry(client, device) -> None:
    first = client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": False},
        headers={"Idempotency-Key": "toggle-1"},
    )
    second = client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": False},
        headers={"Idempotency-Key": "toggle-1"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["etag"] == second.json()["etag"]
    log = device[1].read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in log if line.strip()]
    assert (
        len([entry for entry in entries if entry.get("kind") == "plugin_lifecycle"])
        == 1
    )


def test_a_stale_etag_is_a_conflict_with_the_current_state(client) -> None:
    stale = _toggle(client, False).json()["etag"]
    assert _toggle(client, True).status_code == 200
    response = client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": True},
        headers={"If-Match": stale},
    )
    assert response.status_code == 409
    detail = response.json()["error"]["detail"]
    assert detail["code"] == "stale_state"
    assert detail["current"]["enabled"] is True


def test_a_stale_expected_version_is_a_conflict(client) -> None:
    response = client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": False, "expected_version": "9.9.9"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["detail"]["code"] == "stale_state"


def test_an_unknown_plugin_is_a_404(client) -> None:
    response = client.put("/api/plugins/not-installed/enabled", json={"enabled": False})
    assert response.status_code == 404
    assert response.json()["error"]["detail"]["code"] == "unknown_plugin"


def test_invalid_bodies_are_400(client) -> None:
    assert client.put("/api/plugins/web-research/enabled", json={}).status_code == 400
    assert (
        client.put(
            "/api/plugins/web-research/enabled", json={"enabled": "yes"}
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/api/plugins/web-research/enabled",
            json={"enabled": False, "scope": "machine"},
        ).status_code
        == 400
    )


def test_cancel_without_a_pending_activation_returns_the_state(client) -> None:
    assert _toggle(client, False).status_code == 200
    response = client.post("/api/plugins/web-research/cancel", json={})
    assert response.status_code == 200
    assert response.json()["state"] == "disabled"


def test_the_legacy_post_delegates_and_refuses_an_implicit_enable(client) -> None:
    assert client.post("/api/plugins/web-research/enable", json={}).status_code == 400
    response = client.post("/api/plugins/web-research/enable", json={"enabled": False})
    assert response.status_code == 200
    assert response.json() == {
        "id": "web-research",
        "enabled": False,
        "saved": True,
    }


def test_master_off_pauses_every_plugin_and_preserves_its_state(client, device) -> None:
    from core import plugin_runtime

    assert _toggle(client, False).status_code == 200
    assert (
        client.post("/api/plugins/master", json={"enabled": False}).status_code == 200
    )
    assert client.get("/api/plugins").json()["master_enabled"] is False
    assert plugin_runtime.is_tool_visible("web_search") is False
    assert plugin_runtime.is_tool_visible("read_file") is False
    assert plugin_runtime.is_tool_visible("ask_user") is True

    assert client.post("/api/plugins/master", json={"enabled": True}).status_code == 200
    view = client.get("/api/plugins").json()
    assert view["master_enabled"] is True
    entry = next(item for item in view["public"] if item["name"] == "web-research")
    assert entry["enabled"] is False


def test_a_get_does_not_rewrite_the_committed_state(client, device) -> None:
    assert _toggle(client, False).status_code == 200
    state_file = device[0] / "plugin-state.json"
    before = state_file.read_bytes()
    assert client.get("/api/plugins").status_code == 200
    assert state_file.read_bytes() == before


def test_the_audit_line_carries_the_transition(client, device) -> None:
    assert _toggle(client, False).status_code == 200
    log = device[1].read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in log if line.strip()]
    line = next(entry for entry in entries if entry.get("kind") == "plugin_lifecycle")
    assert line["tool"] == "web-research"
    assert line["decision"] == "disable"
    assert line["status"] == "committed"
    assert "scope=user" in line["detail"]
    assert "previous=enabled" in line["detail"]
    assert "requested=disabled" in line["detail"]
