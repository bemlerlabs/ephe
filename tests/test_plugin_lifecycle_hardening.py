"""The plugin lifecycle's hard edges: idempotency, state agreement, contested ids,
reload, uninstall, trust and two installers at once.

Every test here drove a gap that shipped: a second install replaced the directory
it had just written, a contested id was hidden but never named, an uninstall left
the tool on the rail, and two installers of one name shared one staging folder.
The contract these tests pin is the one the owner asked for: every operation ends
in one coded answer and one state every reader agrees with.
"""

from __future__ import annotations

import io
import json
import sys
import threading
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HEADERS = {"X-Requested-With": "XMLHttpRequest"}
PLUGIN = "alpha"


def manifest(
    name: str = PLUGIN,
    version: str = "1.0.0",
    *,
    tools: list[dict] | None = None,
    memory: dict | None = None,
    surface: dict | None = None,
) -> dict:
    body = {
        "manifest_version": 2,
        "name": name,
        "version": version,
        "description": f"{name} {version}",
        "publisher": {"name": "Test"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": tools or []},
    }
    if memory is not None:
        body["capabilities"] = {"memory": memory}
        body["permissions"]["tool_families"] = ["read", "network"]
    if surface is not None:
        body["components"]["ui"] = surface
    return body


def tool(name: str = "tick") -> dict:
    return {
        "name": name,
        "entry": "handlers.py:run",
        "family": "read",
        "description": f"does {name}",
        "parameters": {"type": "object", "properties": {}},
    }


def surface() -> dict:
    return {
        "type": "floating-window",
        "entry": "ui/index.html",
        "title": "Alpha board",
    }


def artifact(
    name: str = PLUGIN,
    version: str = "1.0.0",
    *,
    tools: list[dict] | None = None,
    memory: dict | None = None,
    surface_decl: dict | None = None,
    extra: dict[str, str] | None = None,
    handler: str = "def run(arguments, context=None):\n    return 'ok'\n",
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            f"{name}/ephe-plugin.json",
            json.dumps(
                manifest(
                    name, version, tools=tools, memory=memory, surface=surface_decl
                )
            ),
        )
        zf.writestr(f"{name}/handlers.py", handler)
        if surface_decl is not None:
            zf.writestr(f"{name}/ui/index.html", "<!doctype html><title>alpha</title>")
        for rel, text in (extra or {}).items():
            zf.writestr(f"{name}/{rel}", text)
    return buffer.getvalue()


def write_dir(cfg: Path, name: str, body: dict, *, files: dict[str, str] | None = None) -> Path:
    directory = cfg / "plugins" / name
    directory.mkdir(parents=True)
    (directory / "ephe-plugin.json").write_text(json.dumps(body), encoding="utf-8")
    for rel, text in (files or {}).items():
        target = directory / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return directory


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core import audit_log, plugin_activity, plugin_runtime
    from core.skills import invalidate_skill_cache

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()
    plugin_activity.clear()
    from core.tools.dynamic_registry import default_registry

    default_registry().replace_for_plugin(PLUGIN, ())
    yield config
    default_registry().replace_for_plugin(PLUGIN, ())
    plugin_activity.clear()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()


@pytest.fixture()
def client(device):
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update(HEADERS)
        yield test_client


def source(tmp_path, monkeypatch, artifacts: dict[str, bytes], *, trust: str = "local", version: str = "1.0.0", name: str = PLUGIN) -> str:
    """An owner-provisioned local index whose one artifact is `artifacts[name]`."""
    from core import marketplace_sources
    from core.plugin_store import sha256_hex

    market = tmp_path / "market"
    (market / "artifacts").mkdir(parents=True, exist_ok=True)
    payload = artifacts[name]
    (market / "artifacts" / f"{name}.zip").write_bytes(payload)
    index = {
        "format": 2,
        "name": "test-index",
        "owner": {"name": "Test"},
        "plugins": [
            {
                "name": name,
                "displayName": name,
                "description": {"en": name},
                "publisher": {"name": "Test"},
                "trust": trust,
                "categories": ["code"],
                "versions": [
                    {
                        "version": version,
                        "publishTimestamp": 1790000000,
                        "source": {
                            "type": "zip",
                            "url": f"artifacts/{name}.zip",
                            "sha256": sha256_hex(payload),
                        },
                        "engines": {"ephe": ">=0.1.0"},
                        "permissions": {"tool_families": ["read"], "data_roots": []},
                        "components": [],
                    }
                ],
            }
        ],
    }
    path = market / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(marketplace_sources, "_home_root", lambda: tmp_path)
    return marketplace_sources.add_source("local", "Test", str(path))["id"]


def sha256_of(payload: bytes) -> str:
    from core.plugin_store import sha256_hex

    return sha256_hex(payload)


def install(tmp_path, monkeypatch, payload: bytes, **kwargs):
    from core import marketplace_service

    source_id = kwargs.pop("source_id", None) or source(
        tmp_path, monkeypatch, {PLUGIN: payload}, **kwargs
    )
    plan = marketplace_service.plan(
        source_id,
        kwargs.pop("name", PLUGIN),
        kwargs.pop("version", "1.0.0"),
        allow_local_trust=True,
        approve_permissions=True,
    )
    assert plan.get("status") == "ready", plan
    return marketplace_service.install(plan)


def low_level(payload: bytes, *, name: str = PLUGIN, root: Path | None = None):
    from core.plugin_install import install_from_marketplace
    from core.plugin_store import sha256_hex

    entry = {
        "name": name,
        "version": "1.0.0",
        "url": "https://example.invalid/artifact.zip",
        "sha256": sha256_hex(payload),
        "trust": "local",
    }
    return install_from_marketplace(
        name,
        marketplace={"plugins": [entry]},
        fetcher=lambda _url: payload,
        allow_local_trust=True,
        root=root,
    )


def state_file(cfg: Path) -> dict:
    path = cfg / "plugin-state.json"
    if not path.is_file():
        return {"plugins": {}, "mounts": {}, "surfaces": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def lockfile(cfg: Path) -> dict:
    path = cfg / "plugin-lock.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def registry(cfg: Path) -> dict[str, bool]:
    path = cfg / "plugins.json"
    raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {str(item["name"]): bool(item["enabled"]) for item in raw.get("plugins", [])}


# Idempotency


def test_a_second_identical_install_is_a_coded_no_op(device) -> None:
    payload = artifact(tools=[tool()])
    first = low_level(payload)
    assert first["status"] == "extracted", first
    before = state_file(device)

    second = low_level(payload)
    assert second["status"] == "already_installed", second
    assert second["version"] == "1.0.0"
    assert (device / "plugins" / PLUGIN).is_dir()
    assert not (device / "plugins" / f".previous-{PLUGIN}").exists()
    assert state_file(device) == before


def test_a_second_disable_is_the_same_committed_answer(client, device) -> None:
    low_level(artifact())
    assert client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": True}).status_code == 200
    first = client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": False})
    second = client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": False})
    assert first.status_code == second.status_code == 200
    assert first.json()["etag"] == second.json()["etag"]
    assert state_file(device)["plugins"][PLUGIN]["user"]["committed"] == "disabled"


def test_removing_a_plugin_that_is_not_installed_is_a_coded_404(client) -> None:
    response = client.post("/api/market/remove", json={"name": "never-installed"})
    assert response.status_code == 404, response.text
    assert response.json()["error"]["detail"]["code"] == "not_installed"


def test_a_half_written_plugin_folder_can_be_removed(client, device) -> None:
    directory = device / "plugins" / "half"
    directory.mkdir(parents=True)
    (directory / "ephe-plugin.json").write_text("{not json", encoding="utf-8")

    response = client.post("/api/market/remove?force=true", json={"name": "half"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "removed"
    assert not directory.exists()


# State consistency


def test_install_agrees_across_registry_state_view_disk_and_lock(
    client, device, tmp_path, monkeypatch
) -> None:
    from core import plugin_runtime

    result = install(tmp_path, monkeypatch, artifact(tools=[tool()]))
    assert result["status"] == "extracted", result

    assert (device / "plugins" / PLUGIN).is_dir()
    # The install lands on the state `plugins.plugin_autorun` decides (E5). The registry,
    # the lock and the installed view - the three surfaces a user can see - agree on it.
    from core.settings_schema import deep_bool
    from core import plugin_runtime

    autorun = deep_bool("plugins.plugin_autorun")
    assert registry(device)[PLUGIN] is autorun
    lock = lockfile(device)
    entry = next(row for row in lock["plugins"] if row["name"] == PLUGIN)
    assert entry["version"] == "1.0.0"
    view = client.get("/api/plugins").json()
    row = next(item for item in view["installed"] if item["name"] == PLUGIN)
    # The view has to mirror the switch source the lifecycle reports, value and all; the
    # registry row is the second witness and is asserted above.
    assert row["enabled"] is plugin_runtime.lifecycle().snapshot(PLUGIN).enabled
    assert registry(device)[PLUGIN] is autorun

    enabled = client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    view = client.get("/api/plugins").json()
    row = next(item for item in view["installed"] if item["name"] == PLUGIN)
    assert row["enabled"] is True
    assert plugin_runtime.lifecycle().snapshot(PLUGIN).enabled is True


def test_removal_clears_every_record(client, device, tmp_path, monkeypatch) -> None:
    install(tmp_path, monkeypatch, artifact(tools=[tool()], surface_decl=surface()))
    from core import plugin_runtime

    client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": True})
    mounted = client.post(f"/api/plugins/{PLUGIN}/hot-mount", json={})
    assert mounted.status_code == 200, mounted.text
    from core.tools import dynamic_registry

    assert dynamic_registry.default_registry().get("tick") is not None
    assert plugin_runtime.tool_gate("tick").visible is True
    assert client.post(f"/api/plugins/{PLUGIN}/surface-token", json={}).status_code == 200
    data = device / "plugin-data" / PLUGIN
    data.mkdir(parents=True)
    (data / "kept.json").write_text("{}", encoding="utf-8")

    blocked = client.post("/api/market/remove", json={"name": PLUGIN, "delete_data": True})
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["detail"]["code"] == "still_active"

    removed = client.post(
        "/api/market/remove?force=true", json={"name": PLUGIN, "delete_data": True}
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["data_removed"] is True

    assert not (device / "plugins" / PLUGIN).exists()
    assert PLUGIN not in registry(device)
    assert not data.exists()
    remaining_lock = {row["name"] for row in lockfile(device).get("plugins", [])}
    assert PLUGIN not in remaining_lock
    # The lock describes the installed portfolio: removing one user bundle must
    # not drop the shipped plugins the default scan had written into it.
    assert "web-research" in remaining_lock
    raw = state_file(device)
    assert PLUGIN not in raw.get("plugins", {})
    assert PLUGIN not in raw.get("mounts", {})
    assert PLUGIN not in raw.get("surfaces", {})
    assert dynamic_registry.default_registry().get("tick") is None
    assert plugin_runtime.tool_gate("tick").visible is False
    from core.tools.registry import get_tool_schemas

    assert "tick" not in {item["function"]["name"] for item in get_tool_schemas()}
    assert client.post(f"/api/plugins/{PLUGIN}/surface-token", json={}).status_code == 404
    view = client.get("/api/plugins").json()
    assert all(
        item["name"] != PLUGIN for item in view["public"] + view["personal"]
    )


def test_removal_keeps_the_data_folder_by_default(client, device, tmp_path, monkeypatch) -> None:
    install(tmp_path, monkeypatch, artifact())
    data = device / "plugin-data" / PLUGIN
    data.mkdir(parents=True)
    (data / "kept.json").write_text("{}", encoding="utf-8")

    forced = client.post("/api/market/remove?force=true", json={"name": PLUGIN})
    assert forced.status_code == 200, forced.text
    assert forced.json()["data_removed"] is False
    assert (data / "kept.json").is_file()


def test_a_refused_install_leaves_no_record(client, device, tmp_path, monkeypatch) -> None:
    from core.plugin_install import install_from_marketplace

    payload = artifact()
    result = install_from_marketplace(
        PLUGIN,
        marketplace={
            "plugins": [
                {
                    "name": PLUGIN,
                    "version": "1.0.0",
                    "url": "https://example.invalid/a.zip",
                    "sha256": "00" * 32,
                    "trust": "local",
                }
            ]
        },
        fetcher=lambda _url: payload,
        allow_local_trust=True,
    )
    assert result["status"] == "hash_mismatch"
    assert not (device / "plugins" / PLUGIN).exists()
    assert not (device / "plugins" / f".staging-{PLUGIN}").exists()
    assert PLUGIN not in registry(device)
    assert all(row["name"] != PLUGIN for row in lockfile(device).get("plugins", []))
    assert PLUGIN not in state_file(device).get("plugins", {})


def test_plugin_operations_write_no_pidfile(client, device, tmp_path, monkeypatch) -> None:
    run = device / "run"
    run.mkdir(parents=True)
    install(tmp_path, monkeypatch, artifact())
    client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": True})
    client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": False})
    client.post("/api/market/remove", json={"name": PLUGIN})
    assert list(run.iterdir()) == []


# Contested ids


def test_a_contested_tool_names_both_claimants_and_serves_neither(client, device) -> None:
    from core import plugin_runtime

    write_dir(device, "alpha", manifest("alpha", tools=[tool()]))
    write_dir(device, "beta", manifest("beta", tools=[tool()]))
    plugin_runtime.invalidate_ownership_cache()

    assert plugin_runtime.tool_gate("tick").visible is False
    for name in ("alpha", "beta"):
        response = client.post(f"/api/plugins/{name}/hot-mount", json={})
        assert response.status_code == 409, response.text
        assert "tick" in response.text
        assert "alpha" in response.text and "beta" in response.text

    contested = client.get("/api/plugins").json()["contested"]
    entry = next(row for row in contested["tools"] if row["name"] == "tick")
    assert {claim["plugin"] for claim in entry["claims"]} == {"alpha", "beta"}
    assert "alpha" in entry["reason"] and "beta" in entry["reason"]


def test_two_bundles_claiming_one_memory_provider_serve_neither(client, device) -> None:
    from core import plugin_runtime
    from core.memory_provider import available_providers, plugin_provider

    memory = {
        "id": "acme-brain",
        "transport": "kepta-bridge",
        "url": "https://brain.example.invalid/mcp",
        "description": "Acme brain",
    }
    write_dir(device, "alpha", manifest("alpha", memory=memory))
    write_dir(device, "beta", manifest("beta", memory=memory))
    plugin_runtime.invalidate_ownership_cache()

    table = plugin_runtime.memory_providers()
    assert table.contested == ("acme-brain",)
    claim, why = plugin_provider("acme-brain")
    assert claim is None and "alpha" in why and "beta" in why
    assert "acme-brain" not in available_providers()
    contested = client.get("/api/plugins").json()["contested"]
    entry = next(
        row for row in contested["memory_providers"] if row["name"] == "acme-brain"
    )
    assert {claim["plugin"] for claim in entry["claims"]} == {"alpha", "beta"}


def test_a_surface_is_keyed_by_its_plugin_so_two_bundles_cannot_share_one(
    client, device
) -> None:
    from core import plugin_runtime

    one = manifest("alpha", surface=surface())
    two = manifest("beta", surface=surface())
    write_dir(device, "alpha", one, files={"ui/index.html": "<!doctype html>a"})
    write_dir(device, "beta", two, files={"ui/index.html": "<!doctype html>b"})
    plugin_runtime.invalidate_ownership_cache()
    writes = plugin_runtime.lifecycle()
    writes.remember_surface(
        "alpha",
        {"slot": "overlay", "x": 10, "y": 20, "width": 400, "height": 300,
         "open": True, "minimized": False, "placed": True},
    )
    writes.remember_surface(
        "beta",
        {"slot": "overlay", "x": 30, "y": 40, "width": 500, "height": 320,
         "open": True, "minimized": False, "placed": True},
    )
    hosts = client.get("/api/plugins/surface-hosts").json()["surfaces"]
    assert hosts["alpha"]["x"] == 10
    assert hosts["beta"]["x"] == 30


# Hot reload


def test_a_changed_handler_reloads_and_stays_active(client, device, tmp_path, monkeypatch) -> None:
    from core import plugin_hot_reload, plugin_runtime

    install(tmp_path, monkeypatch, artifact(tools=[tool()]))
    client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": True})
    assert client.post(f"/api/plugins/{PLUGIN}/hot-mount", json={}).status_code == 200
    before = plugin_runtime.lifecycle().snapshot(PLUGIN).etag

    (device / "plugins" / PLUGIN / "handlers.py").write_text(
        "def run(arguments, context=None):\n    return 'changed'\n", encoding="utf-8"
    )
    result = plugin_hot_reload.reload_bundle(PLUGIN)
    assert result.names == ("tick",)
    assert result.artifact_changed is True
    assert plugin_runtime.lifecycle().snapshot(PLUGIN).enabled is True
    assert plugin_runtime.lifecycle().snapshot(PLUGIN).etag == before


def test_a_broken_manifest_is_refused_and_the_published_tools_survive(
    client, device, tmp_path, monkeypatch
) -> None:
    from core import plugin_hot_reload
    from core.plugin_lifecycle_types import LifecycleError
    from core.tools import dynamic_registry

    install(tmp_path, monkeypatch, artifact(tools=[tool()]))
    client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": True})
    assert client.post(f"/api/plugins/{PLUGIN}/hot-mount", json={}).status_code == 200
    committed = state_file(device)["plugins"][PLUGIN]["user"]["committed"]

    (device / "plugins" / PLUGIN / "ephe-plugin.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(LifecycleError) as err:
        plugin_hot_reload.reload_bundle(PLUGIN)
    assert err.value.code == "mount_manifest_invalid"
    assert dynamic_registry.default_registry().get("tick") is not None
    assert state_file(device)["plugins"][PLUGIN]["user"]["committed"] == committed


def test_the_reload_route_answers_the_mount_refusal(client, device, tmp_path, monkeypatch) -> None:
    install(tmp_path, monkeypatch, artifact(tools=[tool()]))
    assert client.post(f"/api/plugins/{PLUGIN}/reload", json={}).status_code == 200
    (device / "plugins" / PLUGIN / "ephe-plugin.json").write_text("{broken", encoding="utf-8")
    response = client.post(f"/api/plugins/{PLUGIN}/reload", json={})
    assert response.status_code == 422
    assert response.json()["error"]["detail"]["code"] == "mount_manifest_invalid"


# Trust


def test_which_trust_classes_may_install_is_named(device) -> None:
    """A trust refusal carries the class it refused and the reason, never a bare no."""
    from core.plugin_install import install_from_marketplace

    payload = artifact()

    def run(trust: str, *, allow_local_trust: bool = False) -> dict:
        entry = {
            "name": PLUGIN,
            "version": "1.0.0",
            "url": "https://example.invalid/a.zip",
            "sha256": sha256_of(payload),
            "trust": trust,
        }
        return install_from_marketplace(
            PLUGIN,
            marketplace={"plugins": [entry]},
            fetcher=lambda _url: payload,
            allow_local_trust=allow_local_trust,
        )

    unsigned_official = run("official", allow_local_trust=True)
    assert unsigned_official["status"] == "signature_required"
    assert "signature" in unsigned_official["error"]

    unsigned_local = run("local")
    assert unsigned_local["status"] == "local_trust_required"
    assert "explicit trust" in unsigned_local["error"]

    blocked = run("blocked", allow_local_trust=True)
    assert blocked["status"] == "blocked_source"
    assert "blocked" in blocked["error"]

    unknown = run("trusted-ish", allow_local_trust=True)
    assert unknown["status"] == "invalid_trust"
    assert "unknown trust" in unknown["error"]


def test_an_unsigned_local_artifact_needs_consent_and_says_so(client, tmp_path, monkeypatch) -> None:
    from core import marketplace_service

    payload = artifact()
    source_id = source(tmp_path, monkeypatch, {PLUGIN: payload})
    plan = marketplace_service.plan(source_id, PLUGIN, "1.0.0")
    assert plan["status"] == "refused"
    assert plan["code"] == "local_trust_required"
    response = client.post("/api/market/install", json={"plan": plan})
    assert response.status_code == 428, response.text
    assert response.json()["error"]["detail"]["code"] == "local_trust_required"


def test_a_tampered_signature_names_the_drift_at_the_route(
    client, tmp_path, monkeypatch
) -> None:
    """A trust refusal must name its reason, not just 'quarantined'."""
    from core import marketplace_service, plugin_signing

    private, public = plugin_signing.generate_keypair()
    monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [public])

    payload = artifact()
    # Build the signed artifact the way an exporter does: sign the tree, then zip it.
    source_dir = tmp_path / "src" / PLUGIN
    source_dir.mkdir(parents=True)
    (source_dir / "ephe-plugin.json").write_text(json.dumps(manifest()), encoding="utf-8")
    (source_dir / "handlers.py").write_text("x = 1\n", encoding="utf-8")
    record = plugin_signing.sign_plugin_dir(source_dir, private)
    # Tamper after signing: the record no longer matches the bytes.
    (source_dir / "handlers.py").write_text("x = 2\n", encoding="utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for path in sorted(p for p in source_dir.rglob("*") if p.is_file()):
            zf.writestr(
                f"{PLUGIN}/{path.relative_to(source_dir).as_posix()}", path.read_bytes()
            )
    payload = buffer.getvalue()

    from core.plugin_store import sha256_hex

    market = tmp_path / "market"
    (market / "artifacts").mkdir(parents=True)
    (market / "artifacts" / f"{PLUGIN}.zip").write_bytes(payload)
    index = {
        "format": 2,
        "name": "signed",
        "owner": {"name": "Test"},
        "plugins": [
            {
                "name": PLUGIN,
                "displayName": PLUGIN,
                "description": {"en": PLUGIN},
                "publisher": {"name": "Test"},
                "trust": "community",
                "categories": ["code"],
                "versions": [
                    {
                        "version": "1.0.0",
                        "publishTimestamp": 1790000000,
                        "source": {
                            "type": "zip",
                            "url": f"artifacts/{PLUGIN}.zip",
                            "sha256": sha256_hex(payload),
                            "signature": record,
                        },
                        "engines": {"ephe": ">=0.1.0"},
                        "permissions": {"tool_families": ["read"], "data_roots": []},
                        "components": [],
                    }
                ],
            }
        ],
    }
    path = market / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    from core import marketplace_sources

    monkeypatch.setattr(marketplace_sources, "_home_root", lambda: tmp_path)
    source_id = marketplace_sources.add_source("local", "Signed", str(path))["id"]
    plan = marketplace_service.plan(
        source_id, PLUGIN, "1.0.0", allow_local_trust=True, approve_permissions=True
    )
    assert plan["status"] == "ready", plan
    response = client.post("/api/market/install", json={"plan": plan})
    assert response.status_code == 409, response.text
    detail = response.json()["error"]["detail"]
    assert detail["code"] == "signature_invalid", detail
    assert "drift" in detail.get("reason", "").lower(), detail


def test_a_drifted_signed_plugin_cannot_be_enabled_and_says_why(
    client, device, tmp_path, monkeypatch
) -> None:
    from core import plugin_install, plugin_signing
    from core.plugin_store import sha256_hex

    private, public = plugin_signing.generate_keypair()
    monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [public])
    source_dir = tmp_path / "src" / PLUGIN
    source_dir.mkdir(parents=True)
    (source_dir / "ephe-plugin.json").write_text(json.dumps(manifest()), encoding="utf-8")
    (source_dir / "handlers.py").write_text("x = 1\n", encoding="utf-8")
    record = plugin_signing.sign_plugin_dir(source_dir, private)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for path in sorted(p for p in source_dir.rglob("*") if p.is_file()):
            zf.writestr(
                f"{PLUGIN}/{path.relative_to(source_dir).as_posix()}", path.read_bytes()
            )
    payload = buffer.getvalue()
    installed = plugin_install.install_from_marketplace(
        PLUGIN,
        marketplace={
            "plugins": [
                {
                    "name": PLUGIN,
                    "version": "1.0.0",
                    "url": "https://example.invalid/a.zip",
                    "sha256": sha256_hex(payload),
                    "trust": "community",
                    "signature": record,
                }
            ]
        },
        fetcher=lambda _url: payload,
        allow_local_trust=False,
    )
    assert installed["status"] == "extracted", installed
    (device / "plugins" / PLUGIN / "handlers.py").write_text("x = 2\n", encoding="utf-8")

    response = client.put(f"/api/plugins/{PLUGIN}/enabled", json={"enabled": True})
    assert response.status_code == 409, response.text
    detail = response.json()["error"]["detail"]
    assert detail["code"] == "signature_denied"
    assert "drift" in detail["detail"].lower()


# Two installers at once


def test_two_installers_of_one_name_leave_one_intact_directory(device) -> None:
    from core.plugin_store import sha256_hex

    payload = artifact(tools=[tool()], extra={f"data/{i}.txt": "x" * 50 for i in range(20)})
    digest = sha256_hex(payload)
    from core.plugin_install import install_from_marketplace

    entry = {
        "name": PLUGIN,
        "version": "1.0.0",
        "url": "https://example.invalid/a.zip",
        "sha256": digest,
        "trust": "local",
    }
    results: list[dict] = []
    raised: list[BaseException] = []

    def work() -> None:
        try:
            results.append(
                install_from_marketplace(
                    PLUGIN,
                    marketplace={"plugins": [entry]},
                    fetcher=lambda _url: payload,
                    allow_local_trust=True,
                )
            )
        except BaseException as exc:  # noqa: BLE001 - the gap was an exception escaping
            raised.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert raised == []
    statuses = sorted(result["status"] for result in results)
    assert statuses[0] in {"already_installed", "extracted"}
    assert "extracted" in statuses
    final = device / "plugins" / PLUGIN
    assert final.is_dir()
    assert (final / "ephe-plugin.json").is_file()
    assert len([p for p in final.rglob("*") if p.is_file()]) == len(
        [p for p in zipfile.ZipFile(io.BytesIO(payload)).namelist() if not p.endswith("/")]
    )
    leftovers = [
        p.name for p in (device / "plugins").iterdir() if p.name.startswith(".staging-")
    ]
    assert leftovers == []
    assert registry(device)[PLUGIN] is False


def test_a_stale_staging_directory_is_swept(device) -> None:
    stale = device / "plugins" / f".staging-{PLUGIN}-dead"
    stale.mkdir(parents=True)
    (stale / "payload").mkdir()
    (stale / "payload" / "junk.txt").write_text("half written", encoding="utf-8")

    result = low_level(artifact())
    assert result["status"] == "extracted", result
    assert not stale.exists()
    assert (device / "plugins" / PLUGIN / "ephe-plugin.json").is_file()
