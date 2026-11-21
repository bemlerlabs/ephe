"""QA residue 5 — the memory settings route accepts the provider ids this install declares.

`PUT /api/memory/provider` validated a two-name `Literal` (`kepta`, `kepta-bridge`), so a
provider an active plugin declares (MEM-P1, `capabilities.memory`) was answered with 422
even though `Memory(...)`, `EPHE_MEMORY_PROVIDER` and the decision record all accept it.

The route now asks `core.memory_provider.available_providers()` — the kernel's two ids
first, then the ids the active bundles declare — and refuses anything else with 422 naming
the ids that were allowed. The kernel's ids stay reserved by construction: the manifest
contract refuses a bundle that claims `kepta` or `kepta-bridge`
(`core/plugin_memory_contract.BUILTIN_PROVIDER_IDS`), so a plugin can only add a name.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "plugins"


@pytest.fixture()
def declared(tmp_path, monkeypatch):
    """A plugin root holding the fixture provider, and a hermetic config root."""
    from core import plugin_manifest, plugin_runtime
    from core.memory import Memory
    from server.routes.memory import _get_memory

    plugins = tmp_path / "plugins"
    plugins.mkdir()
    shutil.copytree(FIXTURES / "team-memory", plugins / "team-memory")
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", plugins)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    monkeypatch.delenv("EPHE_MEMORY_PROVIDER", raising=False)
    monkeypatch.delenv("EPHE_MEMORY_DIR", raising=False)
    plugin_runtime.invalidate_ownership_cache()
    _get_memory.cache_clear()
    Memory.reset_scoped_instances()
    yield plugins
    plugin_runtime.invalidate_ownership_cache()
    _get_memory.cache_clear()
    Memory.reset_scoped_instances()


@pytest.fixture()
def client(declared):
    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_the_route_accepts_a_provider_an_active_plugin_declares(client) -> None:
    response = client.put("/api/memory/provider", json={"provider": "team-memory"})
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "team-memory"


def test_the_declared_choice_is_written_as_the_record(client) -> None:
    from core.memory_provider import provider_record_path

    client.put("/api/memory/provider", json={"provider": "team-memory"})
    record = json.loads(provider_record_path().read_text(encoding="utf-8"))
    assert record["provider"] == "team-memory"
    assert record["reason"] == "settings"


def test_the_kernel_ids_are_accepted_and_listed_first(client, monkeypatch) -> None:
    from core.memory_provider import VALID_PROVIDERS, available_providers

    # The bridge is a provider without a default endpoint: selecting it needs its
    # instance named, exactly like the env path does (W18, no silent endpoint).
    monkeypatch.setenv("EPHE_MEMORY_KEPTA_URL", "http://127.0.0.1:3010")
    assert available_providers()[: len(VALID_PROVIDERS)] == VALID_PROVIDERS
    for kernel in VALID_PROVIDERS:
        response = client.put("/api/memory/provider", json={"provider": kernel})
        assert response.status_code == 200, response.text
        assert response.json()["provider"] == kernel


def test_an_unknown_id_is_refused_and_the_allowed_ids_are_named(client) -> None:
    response = client.put("/api/memory/provider", json={"provider": "postgres"})
    assert response.status_code == 422
    message = str(response.json()["error"]["message"])
    assert "postgres" in message
    assert "team-memory" in message, message


def test_a_retired_name_stays_refused(client) -> None:
    assert client.put("/api/memory/provider", json={"provider": "chroma"}).status_code == 422
