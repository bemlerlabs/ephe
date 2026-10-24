"""Plugin version history: backup, rollback, remove.

The installer already verifies an artifact before it reaches a loadable path.
This layer owns what happens to the version that was there: it stays available
until the new one commits, a rollback puts it back with its switch state, and a
remove refuses to break an enabled dependent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_signing, plugin_versions  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    root = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    return root


def plugin(root: Path, name: str, version: str, *, dependencies: list[str] | None = None) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "description": f"{name} {version}",
    }
    if dependencies:
        manifest["dependencies"] = dependencies
    (directory / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def registry(root: Path, entries: list[dict]) -> None:
    (root.parent / "plugins.json").write_text(json.dumps({"plugins": entries}), encoding="utf-8")


def read_registry(root: Path) -> list[dict]:
    return json.loads((root.parent / "plugins.json").read_text(encoding="utf-8"))["plugins"]


def installed_version(directory: Path) -> str:
    manifest = json.loads((directory / "ephe-plugin.json").read_text(encoding="utf-8"))
    return manifest["version"]


class TestRollback:

    def test_rollback_restores_the_previous_version_and_switch(self, cfg):
        plugins = cfg / "plugins"
        plugin(plugins, "alpha", "1.0.0")
        registry(plugins, [{"name": "alpha", "enabled": True}])
        backup = plugin_versions.backup_current(plugins / "alpha")
        assert backup is not None and backup.is_dir()
        # The installer writes the new version into the same final path.
        plugin(plugins, "alpha", "2.0.0")

        result = plugin_versions.rollback_plugin("alpha", root=plugins)

        assert result["status"] == "rolled_back"
        assert result["version"] == "1.0.0"
        assert installed_version(plugins / "alpha") == "1.0.0"
        assert read_registry(plugins) == [{"name": "alpha", "enabled": True}]
        assert not (plugins / ".previous-alpha").exists()

    def test_rollback_restores_the_switch_state_of_the_backup(self, cfg):
        plugins = cfg / "plugins"
        plugin(plugins, "alpha", "1.0.0")
        registry(plugins, [{"name": "alpha", "enabled": False}])
        plugin_versions.backup_current(plugins / "alpha")
        plugin(plugins, "alpha", "2.0.0")
        registry(plugins, [{"name": "alpha", "enabled": True}])

        plugin_versions.rollback_plugin("alpha", root=plugins)

        assert read_registry(plugins) == [{"name": "alpha", "enabled": False}]

    def test_rollback_without_a_backup_is_refused(self, cfg):
        plugins = cfg / "plugins"
        plugin(plugins, "alpha", "1.0.0")
        result = plugin_versions.rollback_plugin("alpha", root=plugins)
        assert result["status"] == "no_previous"
        assert installed_version(plugins / "alpha") == "1.0.0"


class TestRollbackTrustClass:
    """TS-09 at rollback: the backup is verified against the class it was
    installed under, and a sidecar from before the field is migrated."""

    def _bind(self, monkeypatch, *pairs):
        monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: list(pairs))

    def _signed(self, plugins: Path, version: str, private_pem: bytes) -> Path:
        directory = plugin(plugins, "alpha", version)
        plugin_signing.sign_plugin_dir(directory, private_pem)
        return directory

    def test_a_backup_recorded_as_first_party_refuses_a_user_signature(
        self, cfg, monkeypatch
    ):
        user = plugin_signing.generate_keypair()
        first = plugin_signing.generate_keypair()
        self._bind(
            monkeypatch,
            (first[1], plugin_signing.FIRST_PARTY),
            (user[1], plugin_signing.USER),
        )
        plugins = cfg / "plugins"
        self._signed(plugins, "1.0.0", user[0])
        plugin_versions.backup_current(plugins / "alpha", trust_class=plugin_signing.FIRST_PARTY)
        plugin(plugins, "alpha", "2.0.0")

        result = plugin_versions.rollback_plugin("alpha", root=plugins)

        assert result["status"] == "invalid_backup"
        assert result["error"] == "signature not from a trusted key"
        assert installed_version(plugins / "alpha") == "2.0.0"

    def test_a_backup_of_the_recorded_class_rolls_back(self, cfg, monkeypatch):
        user = plugin_signing.generate_keypair()
        self._bind(monkeypatch, (user[1], plugin_signing.USER))
        plugins = cfg / "plugins"
        self._signed(plugins, "1.0.0", user[0])
        plugin_versions.backup_current(plugins / "alpha")
        plugin(plugins, "alpha", "2.0.0")

        result = plugin_versions.rollback_plugin("alpha", root=plugins)

        assert result["status"] == "rolled_back"
        assert result["version"] == "1.0.0"
        assert plugin_signing.load_pin("alpha")["trust_class"] == plugin_signing.USER

    def test_the_sidecar_survives_a_committed_install(self, cfg, monkeypatch):
        plugins = cfg / "plugins"
        plugin(plugins, "alpha", "1.0.0")
        plugin_versions.backup_current(plugins / "alpha")
        plugin(plugins, "alpha", "2.0.0")
        plugin_versions.commit_backup(plugins / "alpha")

        assert (plugins / ".previous-alpha.json").is_file()

    def test_a_real_install_then_rollback_verifies_the_old_class(
        self, cfg, monkeypatch, tmp_path
    ):
        """The production sequence: v1 installed under the user class, v2 under
        first-party, then a rollback. The sidecar must still say user."""
        import io
        import zipfile

        from core import plugin_market
        from core.plugin_store import sha256_hex

        user = plugin_signing.generate_keypair()
        first = plugin_signing.generate_keypair()
        self._bind(
            monkeypatch,
            (first[1], plugin_signing.FIRST_PARTY),
            (user[1], plugin_signing.USER),
        )

        def artifact(version: str) -> tuple[bytes, dict]:
            source = tmp_path / f"src-{version}" / "alpha"
            source.mkdir(parents=True)
            manifest = {
                "manifest_version": 1,
                "name": "alpha",
                "version": version,
                "description": f"alpha {version}",
                "permissions": {"tool_families": [], "data_roots": []},
                "components": {"skills": [], "commands": []},
            }
            (source / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
            record = plugin_signing.sign_plugin_dir(source, self._keys[version])
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        zf.write(path, path.relative_to(source.parent))
            return buf.getvalue(), record

        self._keys = {"1.0.0": user[0], "2.0.0": first[0]}
        plugins = cfg / "plugins"
        for version, trust in (("1.0.0", "community"), ("2.0.0", "official")):
            payload, record = artifact(version)
            result = plugin_market.install_from_marketplace(
                "alpha",
                marketplace={"plugins": [{
                    "name": "alpha",
                    "version": version,
                    "url": f"https://artifact.invalid/{version}.zip",
                    "sha256": sha256_hex(payload),
                    "trust": trust,
                    "signature": record,
                }]},
                fetcher=lambda url, p=payload: p,
                root=plugins,
            )
            assert result["status"] == "extracted", result

        assert json.loads((plugins / ".previous-alpha.json").read_text())["trust_class"] == plugin_signing.USER
        result = plugin_versions.rollback_plugin("alpha", root=plugins)

        assert result["status"] == "rolled_back", result
        assert installed_version(plugins / "alpha") == "1.0.0"

    def test_an_old_sidecar_is_migrated_to_the_pinned_class(self, cfg, monkeypatch):
        """A sidecar written before TS-09 has no class. The pin remembers it, so
        the migration verifies with the class the install used — and the
        rewritten lock names the class for the next rollback."""
        from core.plugin_lockfile import read_lockfile

        user = plugin_signing.generate_keypair()
        first = plugin_signing.generate_keypair()
        self._bind(
            monkeypatch,
            (first[1], plugin_signing.FIRST_PARTY),
            (user[1], plugin_signing.USER),
        )
        plugins = cfg / "plugins"
        self._signed(plugins, "1.0.0", user[0])
        backup = plugin_versions.backup_current(plugins / "alpha")
        assert backup is not None
        sidecar = plugins / ".previous-alpha.json"
        legacy = json.loads(sidecar.read_text(encoding="utf-8"))
        legacy.pop("trust_class", None)
        sidecar.write_text(json.dumps(legacy), encoding="utf-8")
        plugin_signing.record_pin(
            "alpha", {"name": "alpha", "version": "1.0.0", "sha256": "a" * 64},
            trust_class=plugin_signing.USER,
        )
        plugin(plugins, "alpha", "2.0.0")

        result = plugin_versions.rollback_plugin("alpha", root=plugins)

        assert result["status"] == "rolled_back", result
        lock = read_lockfile(cfg / "plugin-lock.json")
        assert [entry["trust_class"] for entry in lock["plugins"]] == [
            plugin_signing.USER
        ]


class TestRemove:

    def test_remove_refuses_an_enabled_dependent(self, cfg):
        plugins = cfg / "plugins"
        plugin(plugins, "base", "1.0.0")
        plugin(plugins, "dependent", "1.0.0", dependencies=["base"])
        registry(
            plugins,
            [
                {"name": "base", "enabled": True},
                {"name": "dependent", "enabled": True},
            ],
        )

        result = plugin_versions.remove_plugin("base", root=plugins)

        assert result["status"] == "dependents_enabled"
        assert result["dependents"] == ["dependent"]
        assert (plugins / "base").is_dir()

    def test_remove_refuses_an_enabled_plugin_until_it_is_off(self, cfg):
        plugins = cfg / "plugins"
        plugin(plugins, "alpha", "1.0.0")
        registry(plugins, [{"name": "alpha", "enabled": True}])

        refused = plugin_versions.remove_plugin("alpha", root=plugins)
        assert refused["status"] == "plugin_enabled"
        assert (plugins / "alpha").is_dir()

        from core import plugin_runtime

        plugin_runtime.lifecycle().set_enabled("alpha", False, actor="test")
        removed = plugin_versions.remove_plugin("alpha", root=plugins)
        assert removed["status"] == "removed"
        assert not (plugins / "alpha").exists()

    def test_remove_clears_the_backup_and_pin_but_keeps_data(self, cfg):
        plugins = cfg / "plugins"
        plugin(plugins, "alpha", "1.0.0")
        registry(plugins, [{"name": "alpha", "enabled": False}])
        plugin_versions.backup_current(plugins / "alpha")
        plugin(plugins, "alpha", "2.0.0")
        plugin_signing.record_pin(
            "alpha",
            {"name": "alpha", "version": "2.0.0", "sha256": "a" * 64},
        )
        data = cfg / "plugin-data" / "alpha"
        data.mkdir(parents=True)
        (data / "store.json").write_text("{}", encoding="utf-8")

        result = plugin_versions.remove_plugin("alpha", root=plugins)

        assert result["status"] == "removed"
        assert not (plugins / "alpha").exists()
        assert not (plugins / ".previous-alpha").exists()
        assert plugin_signing.load_pin("alpha") is None
        assert data.is_dir()
        assert read_registry(plugins) == []

    def test_remove_can_delete_data_on_request(self, cfg):
        plugins = cfg / "plugins"
        plugin(plugins, "alpha", "1.0.0")
        registry(plugins, [{"name": "alpha", "enabled": False}])
        data = cfg / "plugin-data" / "alpha"
        data.mkdir(parents=True)
        (data / "store.json").write_text("{}", encoding="utf-8")

        result = plugin_versions.remove_plugin("alpha", root=plugins, delete_data=True)

        assert result["status"] == "removed"
        assert not data.exists()
