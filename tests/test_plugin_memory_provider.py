"""MEM-P1 — a memory provider a plugin declares (`capabilities.memory`).

The seam this file pins: a version 2 manifest names one memory provider, the plugin
runtime registers it from the same scan the tool gate reads, and the provider is only
reachable while its plugin is active. The kernel keeps the two built-ins
(`core/memory_provider.VALID_PROVIDERS`); a bundle adds one over the wire protocol the
Kepta bridge already speaks, and that is why nothing here imports plugin code
(ruling A1, `core/sandbox/runner.py`).

`tests/fixtures/plugins/team-memory/` is the declared provider used throughout; the
tests copy it into a root they own, so a scan never reads a folder this file does not
own.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "plugins"



def _valid(**memory: object) -> dict:
    """A v2 manifest that declares the fixture's provider; `memory` replaces the section."""
    descriptor: dict = {
        "id": "team-memory",
        "transport": "kepta-bridge",
        "url": "http://127.0.0.1:3010",
        "scope": "team",
        "description": "Shared notes for the team.",
    }
    descriptor.update(memory)
    descriptor = {key: value for key, value in descriptor.items() if value is not None}
    return {
        "manifest_version": 2,
        "name": "acme-memory",
        "version": "1.0.0",
        "description": "A declared memory provider.",
        "publisher": {"name": "Acme"},
        "license": "MIT",
        "engines": {"ephe": ">=0.6.0"},
        "permissions": {"tool_families": ["network"], "data_roots": []},
        "capabilities": {"memory": descriptor},
    }


def _write(root: Path, manifest: dict) -> Path:
    directory = root / str(manifest["name"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return directory


@pytest.fixture()
def contract_root(tmp_path):
    """A folder per test for the manifests that have to be refused."""
    root = tmp_path / "contract"
    root.mkdir()
    return root


def _error(root: Path, manifest: dict) -> str | None:
    from core.plugin_manifest import load_manifest

    _manifest, error = load_manifest(_write(root, manifest))
    return error


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    """A plugin root the test owns, holding the fixture provider."""
    from core import plugin_manifest, plugin_runtime

    plugins = tmp_path / "plugins"
    plugins.mkdir()
    shutil.copytree(FIXTURES / "team-memory", plugins / "team-memory")
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", plugins)
    plugin_runtime.invalidate_ownership_cache()
    yield plugins
    plugin_runtime.invalidate_ownership_cache()


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    """Hermetic config root; no embedder, no provider env — the record decides."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("EPHE_MEMORY_PROVIDER", raising=False)
    monkeypatch.delenv("EPHE_MEMORY_KEPTA_URL", raising=False)
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    from core.memory import Memory

    Memory.reset_scoped_instances()
    yield tmp_path / "config"
    Memory.reset_scoped_instances()



class TestContract:
    def test_the_fixture_manifest_validates_and_carries_the_provider(self) -> None:
        from core.plugin_manifest import load_manifest
        from core.plugin_memory_contract import memory_claim

        manifest, error = load_manifest(FIXTURES / "team-memory")
        assert error is None
        claim = memory_claim(manifest)
        assert claim is not None
        assert (claim.plugin_id, claim.provider_id) == ("team-memory", "team-memory")
        assert claim.transport == "kepta-bridge"
        assert claim.url == "http://127.0.0.1:3010"
        assert claim.scope == "team"

    def test_a_version_1_manifest_cannot_declare_capabilities(self, contract_root) -> None:
        manifest = _valid()
        manifest["manifest_version"] = 1
        assert _error(contract_root, manifest) == "capabilities: manifest_version 2 required"

    def test_an_unknown_capability_section_is_refused(self, contract_root) -> None:
        manifest = _valid()
        manifest["capabilities"]["vector"] = {}
        assert _error(contract_root, manifest) == "capabilities: unknown section(s): vector"

    def test_capabilities_must_be_an_object(self, contract_root) -> None:
        manifest = _valid()
        manifest["capabilities"] = []
        assert _error(contract_root, manifest) == "capabilities: object expected"

    def test_an_unknown_memory_field_is_refused(self, contract_root) -> None:
        manifest = _valid(token="s3cret")
        assert _error(contract_root, manifest) == "capabilities.memory: unknown field(s): token"

    def test_a_missing_provider_id_is_refused(self, contract_root) -> None:
        manifest = _valid(id=None)
        assert _error(contract_root, manifest) == "capabilities.memory.id: lowercase slug expected (a-z0-9-)"

    def test_a_kernel_provider_id_cannot_be_taken(self, contract_root) -> None:
        manifest = _valid(id="kepta")
        assert _error(contract_root, manifest) == "capabilities.memory.id: 'kepta' is a kernel provider id"

    def test_a_provider_id_has_a_length_ceiling(self, contract_root) -> None:
        manifest = _valid(id="m" * 41)
        assert _error(contract_root, manifest) == "capabilities.memory.id: at most 40 characters expected"

    def test_an_unknown_transport_is_refused(self, contract_root) -> None:
        manifest = _valid(transport="grpc")
        assert (
            _error(contract_root, manifest)
            == "capabilities.memory.transport: 'grpc' is not a transport this kernel speaks (kepta-bridge)"
        )

    def test_the_url_has_to_be_http(self, contract_root) -> None:
        manifest = _valid(url="file:///etc/passwd")
        assert _error(contract_root, manifest) == "capabilities.memory.url: an http(s) URL expected"

    def test_a_url_with_credentials_is_refused(self, contract_root) -> None:
        manifest = _valid(url="http://user:pass@memory.example")
        assert _error(contract_root, manifest) == "capabilities.memory.url: credentials in the URL are refused"

    def test_a_url_fragment_is_refused(self, contract_root) -> None:
        manifest = _valid(url="http://memory.example/#frag")
        assert _error(contract_root, manifest) == "capabilities.memory.url: a fragment is refused"

    def test_the_scope_is_a_slug(self, contract_root) -> None:
        manifest = _valid(scope="Team Notes")
        assert (
            _error(contract_root, manifest)
            == "capabilities.memory.scope: a slug of lowercase letters, digits, dash, dot, underscore expected"
        )

    def test_a_description_is_not_allowed_to_be_blank(self, contract_root) -> None:
        manifest = _valid(description="  ")
        assert _error(contract_root, manifest) == "capabilities.memory.description: non-empty string expected"

    def test_a_provider_needs_the_network_family(self, contract_root) -> None:
        manifest = _valid()
        manifest["permissions"]["tool_families"] = ["read"]
        assert _error(contract_root, manifest) == "capabilities.memory: permissions.tool_families must include 'network'"

    def test_an_absent_capabilities_section_is_fine(self, contract_root) -> None:
        manifest = _valid()
        del manifest["capabilities"]
        assert _error(contract_root, manifest) is None

    def test_the_builtin_ids_agree_with_the_provider_seam(self) -> None:
        """The reserved ids are one question with one answer, pinned across the two files."""
        from core.memory_provider import VALID_PROVIDERS
        from core.plugin_memory_contract import BUILTIN_PROVIDER_IDS

        assert BUILTIN_PROVIDER_IDS == frozenset(VALID_PROVIDERS)



class TestRegistration:
    def test_the_runtime_registers_the_declared_provider(self, roots) -> None:
        from core import plugin_runtime

        table = plugin_runtime.memory_providers()
        claim = table.get("team-memory")
        assert claim is not None
        assert claim.plugin_id == "team-memory"
        assert claim.url == "http://127.0.0.1:3010"
        assert plugin_runtime.memory_provider_claim("team-memory") == claim

    def test_an_unknown_provider_id_is_not_registered(self, roots) -> None:
        from core import plugin_runtime

        assert plugin_runtime.memory_provider_claim("nobody") is None
        assert plugin_runtime.memory_providers().get("nobody") is None

    def test_two_plugins_claiming_one_id_make_it_contested(self, roots) -> None:
        from core import plugin_manifest, plugin_runtime

        twin = _valid()
        twin["name"] = "twin-memory"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, twin)
        plugin_runtime.invalidate_ownership_cache()

        table = plugin_runtime.memory_providers()
        assert table.get("team-memory") is None
        assert "team-memory" in table.contested
        assert "'twin-memory'" in table.conflict_reason("team-memory")

    def test_the_cache_drops_after_a_rescan(self, roots) -> None:
        from core import plugin_manifest, plugin_runtime

        assert plugin_runtime.memory_provider_claim("team-memory") is not None
        shutil.rmtree(plugin_manifest.PLUGINS_ROOT_OVERRIDE / "team-memory")
        plugin_runtime.invalidate_ownership_cache()
        assert plugin_runtime.memory_provider_claim("team-memory") is None



def _disable(plugin_id: str) -> None:
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    plugin_runtime.lifecycle().set_enabled(plugin_id, False)


def _enable(plugin_id: str) -> None:
    from core import plugin_runtime

    plugin_runtime.lifecycle().set_enabled(plugin_id, True)


class TestResolution:
    def test_an_active_plugin_provider_resolves_by_name(self, cfg, roots) -> None:
        from core.memory_provider import resolve_provider

        provider, reason = resolve_provider(explicit="team-memory")
        assert provider == "team-memory"
        assert "Plugin 'team-memory'" in reason

    def test_the_provider_id_lists_with_the_builtins_while_active(self, cfg, roots) -> None:
        from core.memory_provider import available_providers

        assert available_providers() == ("kepta", "kepta-bridge", "team-memory")

    def test_an_inactive_plugin_provider_is_refused_by_name(self, cfg, roots) -> None:
        from core.memory_provider import resolve_provider

        _disable("team-memory")
        with pytest.raises(ValueError) as excinfo:
            resolve_provider(explicit="team-memory")
        assert "team-memory" in str(excinfo.value)
        assert "switched off" in str(excinfo.value)

    def test_an_inactive_provider_is_gone_from_the_list(self, cfg, roots) -> None:
        from core.memory_provider import available_providers

        _disable("team-memory")
        assert available_providers() == ("kepta", "kepta-bridge")

    def test_the_env_seam_accepts_an_active_plugin_provider(self, cfg, roots, monkeypatch) -> None:
        from core.memory_provider import resolve_provider

        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "team-memory")
        provider, reason = resolve_provider()
        assert provider == "team-memory"
        assert "EPHE_MEMORY_PROVIDER" in reason

    def test_the_env_seam_ignores_an_inactive_plugin_provider(
        self, cfg, roots, monkeypatch, caplog
    ) -> None:
        from core.memory_provider import resolve_provider

        _disable("team-memory")
        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "team-memory")
        provider, reason = resolve_provider()
        assert provider == "kepta"
        assert "team-memory" not in reason
        assert any("team-memory" in record.message for record in caplog.records)

    def test_open_provider_wires_the_declared_endpoint(self, cfg, roots) -> None:
        from core.memory_provider import open_provider

        seen: list[tuple[str, str, dict | None]] = []

        def transport(method, path, body=None, params=None):
            seen.append((method, path, body))
            return {"count": 3} if path == "/api/storage-info" else None

        provider = open_provider("team-memory", transport=transport)
        assert provider._url == "http://127.0.0.1:3010"
        assert provider.count() == 3
        assert seen and seen[0][:2] == ("GET", "/api/storage-info")

    def test_the_declared_scope_reaches_the_write(self, cfg, roots) -> None:
        from core.memory_provider import open_provider

        bodies: list[dict] = []

        def transport(method, path, body=None, params=None):
            if body is not None:
                bodies.append(body)
            return {"memory": {"id": "m1"}}

        provider = open_provider("team-memory", transport=transport)
        assert provider.store("a fact") == "m1"
        assert bodies[0]["scope"] == "team"

    def test_without_a_declared_scope_the_workspace_names_it(self, cfg, roots) -> None:
        from core import plugin_manifest, plugin_runtime
        from core.engine_config import workspace_hash
        from core.memory_provider import open_provider

        manifest = _valid(id="no-scope-memory", scope=None)
        manifest["name"] = "no-scope-memory"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, manifest)
        plugin_runtime.invalidate_ownership_cache()
        provider = open_provider("no-scope-memory", transport=lambda *a, **k: {})
        assert provider._scope == workspace_hash()

    def test_a_contested_provider_is_refused(self, cfg, roots) -> None:
        from core import plugin_manifest
        from core.memory_provider import resolve_provider

        twin = _valid()
        twin["name"] = "twin-memory"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, twin)
        from core import plugin_runtime

        plugin_runtime.invalidate_ownership_cache()
        with pytest.raises(ValueError) as excinfo:
            resolve_provider(explicit="team-memory")
        assert "claimed by" in str(excinfo.value)

    def test_an_unknown_explicit_provider_still_raises(self, cfg, roots) -> None:
        from core.memory_provider import resolve_provider

        with pytest.raises(ValueError, match="Unknown memory provider"):
            resolve_provider(explicit="postgres")

    def test_open_provider_refuses_an_inactive_plugin_provider(self, cfg, roots) -> None:
        from core.memory_provider import open_provider

        _disable("team-memory")
        with pytest.raises(ValueError, match="switched off"):
            open_provider("team-memory")


class TestRecord:
    def test_a_choice_survives_while_the_plugin_is_active(self, cfg, roots) -> None:
        from core.memory_provider import (
            read_provider_record,
            resolve_provider,
            write_provider_record,
        )

        write_provider_record("team-memory", reason="settings")
        assert read_provider_record()["provider"] == "team-memory"
        assert resolve_provider()[0] == "team-memory"

    def test_a_choice_naming_an_inactive_plugin_is_kept_but_not_used(self, cfg, roots) -> None:
        """The record is the user's intent: it is not overwritten while it cannot apply."""
        from core.memory_provider import (
            read_provider_record,
            resolve_provider,
            write_provider_record,
        )

        write_provider_record("team-memory", reason="settings")
        _disable("team-memory")
        provider, reason = resolve_provider()
        assert provider == "kepta"
        assert "team-memory" in reason
        assert read_provider_record() is None
        assert json.loads(
            (cfg / "memory" / "provider.json").read_text(encoding="utf-8")
        )["provider"] == "team-memory"

    def test_the_choice_applies_again_when_the_plugin_returns(self, cfg, roots) -> None:
        from core.memory_provider import resolve_provider, write_provider_record

        write_provider_record("team-memory", reason="settings")
        _disable("team-memory")
        assert resolve_provider()[0] == "kepta"
        _enable("team-memory")
        assert resolve_provider()[0] == "team-memory"

    def test_writing_an_unknown_provider_is_refused(self, cfg, roots) -> None:
        from core.memory_provider import write_provider_record

        with pytest.raises(ValueError, match="Unknown memory provider"):
            write_provider_record("postgres", reason="settings")



class TestPrecedenceIsUnchanged:
    """The four steps `resolve_provider` took before this seam existed, one by one."""

    def test_a_named_store_beats_everything(self, cfg, roots, monkeypatch) -> None:
        from core.memory_provider import resolve_provider

        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "team-memory")
        assert resolve_provider(persist_dir="/tmp/store")[0] == "kepta"

    def test_the_explicit_argument_beats_the_environment(self, cfg, roots, monkeypatch) -> None:
        from core.memory_provider import resolve_provider

        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta-bridge")
        assert resolve_provider(explicit="kepta")[0] == "kepta"

    def test_the_record_wins_over_a_fresh_install(self, cfg, roots) -> None:
        from core.memory_provider import resolve_provider, write_provider_record

        write_provider_record("kepta-bridge", reason="settings")
        assert resolve_provider()[0] == "kepta-bridge"

    def test_a_fresh_workspace_becomes_kepta_and_says_why(self, cfg, roots) -> None:
        from core.memory_provider import resolve_provider

        provider, reason = resolve_provider()
        assert provider == "kepta"
        assert "frischer Workspace" in reason
