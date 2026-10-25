"""Marketplace API: sources, plan, install, rollback and remove.

Mutating calls require the XHR marker, a permission review answers 428 with
the delta, and a refusal is a coded error envelope rather than a 200.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import marketplace_sources  # noqa: E402
from core.plugin_store import sha256_hex  # noqa: E402

HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def artifact(root: Path, version: str, families: tuple[str, ...] = ("read",)) -> tuple[str, str]:
    manifest = {
        "manifest_version": 1,
        "name": "alpha",
        "version": version,
        "description": f"alpha {version}",
        "permissions": {"tool_families": list(families), "data_roots": []},
        "components": {"skills": [], "commands": []},
    }
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("alpha/ephe-plugin.json", json.dumps(manifest))
    data = payload.getvalue()
    path = root / "artifacts" / f"alpha-{version}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"artifacts/{path.name}", sha256_hex(data)


def entry(version: str, url: str, digest: str, families: tuple[str, ...] = ("read",)) -> dict:
    return {
        "version": version,
        "publishTimestamp": 1790000000,
        "source": {"type": "zip", "url": url, "sha256": digest},
        "engines": {"ephe": ">=0.1.0"},
        "permissions": {"tool_families": list(families), "data_roots": []},
        "components": ["skills"],
    }


def write_index(root: Path, versions: list[dict]) -> Path:
    index = {
        "format": 2,
        "name": "test-index",
        "owner": {"name": "Test"},
        "plugins": [
            {
                "name": "alpha",
                "displayName": "Alpha",
                "description": {"en": "Alpha"}, 
                "publisher": {"name": "Test"},
                "trust": "local",
                "categories": ["code"],
                "versions": versions,
            }
        ],
    }
    path = root / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    return path


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    market = tmp_path / "market"
    market.mkdir()
    v1 = artifact(market, "1.0.0")
    v2 = artifact(market, "2.0.0")
    index = write_index(
        market,
        [entry("1.0.0", *v1), entry("2.0.0", *v2)],
    )
    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as c:
        c.index_path = index  # type: ignore[attr-defined]
        yield c


def provision_source(client) -> str:
    """Owner-provisioned source, written through the store (no user API).

    The extension center is curated: the public routes must not create a source.
    The engine keeps the capability so a future enterprise build can provision
    one through policy, and these tests exercise that path directly.
    """
    source = marketplace_sources.add_source("local", "Test", str(client.index_path))
    return source["id"]


class TestSources:

    def test_the_bundled_source_is_listed(self, client):
        body = client.get("/api/market").json()
        assert [source["id"] for source in body["sources"]] == ["bundled"]

    def test_source_writes_are_not_exposed(self, client):
        """No self-service: adding, refreshing or removing a source is not a
        user action, so the routes are absent rather than hidden in the UI."""
        for response in (
            client.post("/api/market/sources", json={}, headers=HEADERS),
            client.delete("/api/market/sources/x", headers=HEADERS),
            client.post("/api/market/refresh", headers=HEADERS),
        ):
            assert response.status_code in {404, 405}, response.text

    def test_an_owner_provisioned_source_stays_out_of_the_curated_home(self, client):
        provision_source(client)
        body = client.get("/api/market").json()
        assert [source["id"] for source in body["sources"]] == ["bundled"]
        assert "last_read" in body and "last_error" in body

    def test_a_mutation_without_the_marker_is_refused(self, client):
        response = client.post(
            "/api/market/plan",
            json={"source_id": "bundled", "name": "alpha"},
        )
        assert response.status_code == 403

    def test_the_bundled_index_carries_five_first_party_skill_packs(self, client):
        body = client.get("/api/market/index").json()
        packs = [
            entry
            for entry in body["index"]["plugins"]
            if entry.get("kind") == "skill-pack"
            and entry.get("provenance") == "first-party"
        ]
        assert len(packs) == 5
        assert {pack["name"] for pack in packs} == {
            "business-pack", "dev-pack", "office-pack", "research-pack", "writing-pack",
        }

    def test_a_bundled_skill_pack_is_not_installable(self, client):
        response = client.post(
            "/api/market/plan",
            json={"source_id": "bundled", "name": "dev-pack"},
            headers=HEADERS,
        )
        assert response.status_code == 409
        assert response.json()["error"]["detail"]["code"] == "bundled_not_installable"


class TestIcons:

    def test_the_bundled_icon_is_served(self, client):
        response = client.get("/api/market/icon/browser-use")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert response.headers["x-content-type-options"] == "nosniff"

    def test_an_unknown_icon_is_404(self, client):
        assert client.get("/api/market/icon/nope").status_code == 404


class TestInstallFlow:

    def test_plan_install_update_and_rollback(self, client):
        source_id = provision_source(client)
        plan = client.post(
            "/api/market/plan",
            json={
                "source_id": source_id,
                "name": "alpha",
                "version": "1.0.0",
                "allow_local_trust": True,
                "approve_permissions": True,
            },
            headers=HEADERS,
        )
        assert plan.status_code == 200, plan.text
        installed = client.post(
            "/api/market/install", json={"plan": plan.json()}, headers=HEADERS
        )
        assert installed.status_code == 200, installed.text
        assert installed.json()["status"] == "extracted"

        update = client.post(
            "/api/market/plan",
            json={"source_id": source_id, "name": "alpha", "version": "2.0.0", "allow_local_trust": True},
            headers=HEADERS,
        )
        assert update.status_code == 200, update.text
        client.post("/api/market/install", json={"plan": update.json()}, headers=HEADERS)

        rollback = client.post("/api/market/rollback", json={"name": "alpha"}, headers=HEADERS)
        assert rollback.status_code == 200, rollback.text
        assert rollback.json()["version"] == "1.0.0"

        installed_view = client.get("/api/market/installed").json()
        alpha = next(row for row in installed_view["plugins"] if row["name"] == "alpha")
        assert alpha["version"] == "1.0.0"

    def test_a_permission_adding_update_answers_428(self, client, tmp_path):
        source_id = provision_source(client)
        first = client.post(
            "/api/market/plan",
            json={"source_id": source_id, "name": "alpha", "version": "1.0.0", "allow_local_trust": True, "approve_permissions": True},
            headers=HEADERS,
        ).json()
        client.post("/api/market/install", json={"plan": first}, headers=HEADERS)

        v3 = artifact(client.index_path.parent, "3.0.0", families=("read", "network"))
        write_index(
            client.index_path.parent,
            [
                entry("1.0.0", *artifact(client.index_path.parent, "1.0.0")),
                entry("3.0.0", *v3, families=("read", "network")),
            ],
        )
        review = client.post(
            "/api/market/plan",
            json={"source_id": source_id, "name": "alpha", "version": "3.0.0", "allow_local_trust": True},
            headers=HEADERS,
        )
        assert review.status_code == 428, review.text
        body = review.json()["error"]["detail"]
        assert body["code"] == "permission_review"
        assert body["delta"]["tool_families_added"] == ["network"]

        approved = client.post(
            "/api/market/plan",
            json={
                "source_id": source_id,
                "name": "alpha",
                "version": "3.0.0",
                "allow_local_trust": True,
                "approve_permissions": True,
            },
            headers=HEADERS,
        )
        assert approved.status_code == 200, approved.text
        installed = client.post(
            "/api/market/install", json={"plan": approved.json()}, headers=HEADERS
        )
        assert installed.status_code == 200, installed.text

    def test_an_unknown_source_is_404(self, client):
        response = client.post(
            "/api/market/plan",
            json={"source_id": "src-nope", "name": "alpha"},
            headers=HEADERS,
        )
        assert response.status_code == 404

    def test_switch_installs_then_toggles_off_and_on_idempotently(self, client):
        source_id = provision_source(client)
        body = {
            "source_id": source_id,
            "name": "alpha",
            "version": "1.0.0",
            "enabled": True,
            "approve_permissions": True,
            "allow_local_trust": True,
        }
        on = client.post("/api/market/switch", json=body, headers=HEADERS)
        assert on.status_code == 200, on.text
        assert on.json()["status"] == "enabled"
        assert on.json()["enabled"] is True

        off = client.post(
            "/api/market/switch", json={**body, "enabled": False}, headers=HEADERS
        )
        assert off.status_code == 200, off.text
        assert off.json()["status"] == "disabled"
        assert off.json()["enabled"] is False

        off_again = client.post(
            "/api/market/switch", json={**body, "enabled": False}, headers=HEADERS
        )
        assert off_again.status_code == 200
        assert off_again.json()["enabled"] is False

        on_again = client.post("/api/market/switch", json=body, headers=HEADERS)
        assert on_again.status_code == 200, on_again.text
        assert on_again.json()["enabled"] is True

    def test_switch_without_consent_answers_428_with_the_delta(self, client):
        source_id = provision_source(client)
        review = client.post(
            "/api/market/switch",
            json={"source_id": source_id, "name": "alpha", "version": "1.0.0", "enabled": True},
            headers=HEADERS,
        )
        assert review.status_code == 428, review.text
        detail = review.json()["error"]["detail"]
        assert detail["code"] in {"permission_review", "local_trust_required"}

    def test_switch_off_for_a_plugin_that_is_not_installed_is_404(self, client):
        response = client.post(
            "/api/market/switch",
            json={"name": "never-installed", "enabled": False},
            headers=HEADERS,
        )
        assert response.status_code == 404
