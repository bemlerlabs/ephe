"""Marketplace service: one plan, one verified install, one rollback path.

The plan is what the user approves: exact version, hash, trust and permission
delta. The install re-reads the source, refuses a changed index and passes an
inspect hook into staging so the bytes must match the plan before they replace
the running version.
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

from core import marketplace_service, marketplace_sources, plugin_store  # noqa: E402
from core.plugin_store import sha256_hex  # noqa: E402


def make_artifact(
    directory: Path,
    name: str,
    version: str,
    *,
    families: tuple[str, ...] = ("read",),
    dependencies: list[str] | None = None,
    engine: str = ">=0.1.0",
) -> tuple[Path, str]:
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "description": f"{name} {version}",
        "permissions": {"tool_families": list(families), "data_roots": []},
        "components": {"skills": [], "commands": []},
        "engines": {"ephe": engine},
    }
    if dependencies:
        manifest["dependencies"] = dependencies
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr(f"{name}/ephe-plugin.json", json.dumps(manifest))
    path = directory / f"{name}-{version}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.getvalue())
    return path, sha256_hex(payload.getvalue())


def version_entry(
    version: str,
    artifact: Path,
    digest: str,
    *,
    families: tuple[str, ...] = ("read",),
    engine: str = ">=0.1.0",
) -> dict:
    return {
        "version": version,
        "publishTimestamp": 1790000000,
        "source": {
            "type": "zip",
            "url": f"artifacts/{artifact.name}",
            "sha256": digest,
        },
        "engines": {"ephe": engine},
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
                "description": {"en": "Alpha plugin"},
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
def market(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    root = tmp_path / "market"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    v1, sha1 = make_artifact(artifacts, "alpha", "1.0.0")
    v2, sha2 = make_artifact(artifacts, "alpha", "2.0.0")
    index = write_index(
        root,
        [
            version_entry("1.0.0", v1, sha1),
            version_entry("2.0.0", v2, sha2),
        ],
    )
    source = marketplace_sources.add_source("local", "Test source", str(index))
    return {
        "cfg": cfg,
        "root": root,
        "artifacts": artifacts,
        "index": index,
        "source": source,
        "v1": (v1, sha1),
        "v2": (v2, sha2),
    }


def installed_version() -> str:
    from core import plugin_manifest

    directory = plugin_manifest.plugins_root() / "alpha"
    manifest, _ = plugin_manifest.load_manifest(directory)
    return str(manifest.get("version")) if manifest else ""


class TestInstall:

    def test_a_first_install_commits_the_artifact_and_the_lockfile(self, market):
        plan = marketplace_service.plan(
            market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        assert plan["status"] == "ready", plan
        result = marketplace_service.install(plan)
        assert result["status"] == "extracted", result
        assert result.get("enabled") is True, result
        assert installed_version() == "1.0.0"
        from core import plugin_runtime

        assert plugin_runtime.lifecycle().snapshot("alpha").enabled is True
        lock = json.loads((market["cfg"] / "plugin-lock.json").read_text())
        assert lock["plugins"][0]["version"] == "1.0.0"

    def test_an_update_keeps_the_switch_state(self, market):
        first = marketplace_service.plan(
            market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        marketplace_service.install(first)
        from core import plugin_runtime

        plugin_runtime.lifecycle().set_enabled("alpha", True, actor="test")

        second = marketplace_service.plan(
            market["source"]["id"], "alpha", "2.0.0", allow_local_trust=True
        )
        assert second["status"] == "ready", second
        assert marketplace_service.install(second)["status"] == "extracted"
        assert installed_version() == "2.0.0"
        assert plugin_runtime.lifecycle().snapshot("alpha").enabled is True
        assert (market["cfg"] / "plugins" / ".previous-alpha").is_dir()

    def test_rollback_restores_the_previous_version(self, market):
        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        )
        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "2.0.0", allow_local_trust=True
            )
        )
        result = marketplace_service.rollback("alpha")
        assert result["status"] == "rolled_back"
        assert installed_version() == "1.0.0"

    def test_remove_keeps_data_unless_asked(self, market):
        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        )
        data = market["cfg"] / "plugin-data" / "alpha"
        data.mkdir(parents=True)
        (data / "x.json").write_text("{}")

        result = marketplace_service.remove("alpha")
        assert result["status"] == "removed"
        assert data.is_dir()

        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        )
        marketplace_service.remove("alpha", delete_data=True)
        assert not data.exists()


class TestPermissions:

    def test_a_permission_adding_update_needs_review(self, market):
        v3, sha3 = make_artifact(market["artifacts"], "alpha", "3.0.0", families=("read", "network"))
        write_index(
            market["root"],
            [
                version_entry("1.0.0", *market["v1"]),
                version_entry("3.0.0", v3, sha3, families=("read", "network")),
            ],
        )
        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        )
        review = marketplace_service.plan(
            market["source"]["id"], "alpha", "3.0.0", allow_local_trust=True
        )
        assert review["status"] == "permission_review"
        assert review["delta"]["tool_families_added"] == ["network"]
        assert review["delta"]["digest"]

        approved = marketplace_service.plan(
            market["source"]["id"],
            "alpha",
            "3.0.0",
            allow_local_trust=True,
            approve_permissions=True,
        )
        assert approved["status"] == "ready"
        assert marketplace_service.install(approved)["status"] == "extracted"

    def test_a_lying_index_cannot_smuggle_a_permission(self, market):
        # The index declares only read, the artifact adds shell.
        v2, sha2 = make_artifact(market["artifacts"], "alpha", "2.0.0", families=("read", "shell"))
        write_index(
            market["root"],
            [
                version_entry("1.0.0", *market["v1"]),
                version_entry("2.0.0", v2, sha2, families=("read",)),
            ],
        )
        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        )
        plan = marketplace_service.plan(
            market["source"]["id"], "alpha", "2.0.0", allow_local_trust=True
        )
        assert plan["status"] == "ready"
        result = marketplace_service.install(plan)
        assert result["status"] == "refused"
        assert result["code"] == "permission_delta"
        assert result["delta"]["tool_families_added"] == ["shell"]
        assert installed_version() == "1.0.0"

    def test_a_missing_dependency_refuses_the_commit(self, market):
        v2, sha2 = make_artifact(
            market["artifacts"], "alpha", "2.0.0", dependencies=["base"]
        )
        write_index(
            market["root"],
            [
                version_entry("1.0.0", *market["v1"]),
                version_entry("2.0.0", v2, sha2),
            ],
        )
        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        )
        result = marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "2.0.0", allow_local_trust=True
            )
        )
        assert result["status"] == "refused"
        assert "dependency_missing" in result["error"]
        assert installed_version() == "1.0.0"


class TestRefusals:

    def test_an_incompatible_engine_is_refused_before_download(self, market):
        v2, sha2 = make_artifact(
            market["artifacts"], "alpha", "2.0.0", engine=">=9.0.0"
        )
        write_index(
            market["root"],
            [version_entry("2.0.0", v2, sha2, engine=">=9.0.0")],
        )
        plan = marketplace_service.plan(
            market["source"]["id"], "alpha", "2.0.0", allow_local_trust=True
        )
        assert plan["status"] == "refused"
        assert plan["code"] == "incompatible"

    def test_a_revoked_version_is_refused(self, market):
        (market["root"] / "revocations.json").write_text(
            json.dumps(
                {"format": 1, "revoked": [{"name": "alpha", "version": "2.0.0", "reason": "x"}]}
            )
        )
        plan = marketplace_service.plan(
            market["source"]["id"], "alpha", "2.0.0", allow_local_trust=True
        )
        assert plan["status"] == "refused"
        assert plan["code"] == "revoked"

    def test_updates_lists_a_newer_version(self, market):
        marketplace_service.install(
            marketplace_service.plan(
                market["source"]["id"], "alpha", "1.0.0", allow_local_trust=True, approve_permissions=True)
        )
        updates = marketplace_service.updates()
        assert updates["updates"][0]["name"] == "alpha"
        assert updates["updates"][0]["version"] == "2.0.0"
