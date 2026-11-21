"""W3-63: the plugin lifecycle over the shipped surfaces — install, use, remove.

One plugin travels the whole path the product puts it through:

1. install — a marketplace artifact is verified in staging (sha256, manifest,
   listing identity) and only then moved into the device plugins root, by the
   same ``core.plugin_market.install_from_marketplace`` that ``ephe plugin
   install`` and the desktop install button call.
2. use     — the fresh install lands DISABLED (``plugins.plugin_autorun``
   defaults off), so install alone changes no surface. Enabling it through the
   shipped ``POST /api/plugins/{id}/enable`` turns its bundled skill pack into a
   loadable skill (``core.skills.SkillLoader``) and its declared command into a
   slash command (``GET /api/plugins/commands``) — over the real HTTP app.
3. remove  — a plugin is a folder; deleting it (the shipped "folder presence
   suffices" contract) takes every surface back: the scan entry, the skill and
   the command are gone.

Only the marketplace fetcher is injected — it stands in for the network hop the
default fetcher would make. Hash verification, the safe unzip, the manifest
validator, the registry, the skill loader and the plugins HTTP routes are the
shipped code.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest  # noqa: E402
from core.plugin_store import load_registry, registry_path, sha256_hex  # noqa: E402

# The plugin registry and the skill-list cache are process-global, and the leg
# writes the device registry; eight workers sharing that state would clobber one
# another, so this module runs on the serial leg and stands down under xdist.
pytestmark = pytest.mark.skipif(
    bool(os.environ.get("PYTEST_XDIST_WORKER")),
    reason="serial leg only: the plugin registry and the skill cache are process-global",
)

PLUGIN_ID = "e2e-plugin-demo"
VERSION = "2.4.6"
SKILL_PACK = "e2e-demo-pack"
COMMAND = "e2e-demo-say"
COMMAND_DESC = "Say hello from the installed plugin"
COMMAND_TEMPLATE = "Say: {input}"


def _manifest() -> dict:
    """A valid ``ephe-plugin.json``: one skill pack, one slash command."""
    return {
        "manifest_version": 1,
        "name": PLUGIN_ID,
        "version": VERSION,
        "description": "End-to-end plugin lifecycle fixture",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "skills": [SKILL_PACK],
            "commands": [{"name": COMMAND, "description": COMMAND_DESC, "template": COMMAND_TEMPLATE}],
        },
    }


_SKILL_MD = (
    "---\n"
    f"name: {SKILL_PACK}\n"
    "version: 1.0.0\n"
    f"trigger: /{SKILL_PACK}\n"
    f"description: {SKILL_PACK} pack\n"
    "---\n"
    f"# {SKILL_PACK}\n\n"
    "## System Prompt\n"
    "You are a focused assistant for this bundled pack. "
    "Produce real artifact output, never simulated placeholders.\n"
)


def _artifact_bytes() -> bytes:
    """The shipping shape: a top-level dir named after the plugin."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{PLUGIN_ID}/ephe-plugin.json", json.dumps(_manifest()))
        zf.writestr(f"{PLUGIN_ID}/skills/{SKILL_PACK}/SKILL.md", _SKILL_MD)
    return buf.getvalue()


def _listing(payload: bytes) -> dict:
    return {
        "version": 1,
        "plugins": [
            {
                "name": PLUGIN_ID,
                "version": VERSION,
                "sha256": sha256_hex(payload),
                "url": f"https://market.example.invalid/{PLUGIN_ID}.zip",
                "description": "d",
                "tags": [],
            }
        ],
    }


@pytest.fixture()
def config_dir(tmp_path, monkeypatch):
    """A throwaway device folder; the plugins root lives under it."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    _invalidate()
    yield tmp_path / "config"
    _invalidate()


@pytest.fixture()
def client(config_dir):
    """The real FastAPI app. No engine is touched on the plugin surface."""
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as c:
        c.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield c


def _invalidate() -> None:
    """Plugin state flips must act on the next lookup, not after the TTL."""
    from core.skills import invalidate_skill_cache

    invalidate_skill_cache()


def _plugin_dir(config_dir: Path) -> Path:
    return config_dir / "plugins" / PLUGIN_ID


def _install() -> dict:
    """Run the shipped marketplace install with an injected (offline) fetcher."""
    from core import plugin_market

    payload = _artifact_bytes()
    return plugin_market.install_from_marketplace(
        PLUGIN_ID,
        marketplace=_listing(payload),
        fetcher=lambda url: payload,
        allow_local_trust=True,
    )


def _drop_registry_entry() -> None:
    """What the store does when a plugin is gone: forget the entry."""
    remaining = [p for p in load_registry() if p.get("name") != PLUGIN_ID]
    registry_path().write_text(
        json.dumps({"plugins": remaining}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _has_pack() -> bool:
    return any(p.name == SKILL_PACK for p in plugin_manifest.active_skill_roots())


def _command_plugins() -> list[str]:
    return [c["plugin"] for c in plugin_manifest.manifest_commands()]


def _http_command_plugins(client) -> list[str]:
    return [c["plugin"] for c in client.get("/api/plugins/commands").json()["commands"]]


def _skill_names(client) -> set[str]:
    return {s["name"] for s in client.get("/api/skills").json()["skills"]}


def test_plugin_install_use_remove(client, config_dir):
    """The whole spine: install, enable (use), remove."""
    status = _install()
    assert status["status"] == "extracted", status
    assert status["version"] == VERSION

    pdir = _plugin_dir(config_dir)
    assert (pdir / "ephe-plugin.json").is_file()
    manifest, err = plugin_manifest.load_manifest(pdir)
    assert err is None and manifest["components"]["skills"] == [SKILL_PACK]

    registry = {p["name"]: bool(p.get("enabled")) for p in load_registry()}
    assert registry.get(PLUGIN_ID) is False, f"a fresh install must land disabled: {registry}"

    # Install alone changes no surface — no silent enable.
    _invalidate()
    assert not _has_pack()
    assert PLUGIN_ID not in _command_plugins()
    assert SKILL_PACK not in _skill_names(client)
    assert PLUGIN_ID not in _http_command_plugins(client)

    enabled = client.post(f"/api/plugins/{PLUGIN_ID}/enable", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json() == {"id": PLUGIN_ID, "enabled": True, "saved": True}

    assert pdir / "skills" / SKILL_PACK in plugin_manifest.active_skill_roots()

    from core.skills import SkillLoader

    assert SkillLoader().resolve_trigger(f"/{SKILL_PACK}") is not None

    assert PLUGIN_ID in _command_plugins()
    cmd = next(c for c in plugin_manifest.manifest_commands() if c["plugin"] == PLUGIN_ID)
    assert cmd == {
        "name": f"/{COMMAND}",
        "description": COMMAND_DESC,
        "template": COMMAND_TEMPLATE,
        "plugin": PLUGIN_ID,
    }

    assert PLUGIN_ID in _http_command_plugins(client)
    assert SKILL_PACK in _skill_names(client)

    shutil.rmtree(pdir)
    _drop_registry_entry()
    _invalidate()

    assert not pdir.exists()
    scanned = {e["dir"].name for e in plugin_manifest.scan_plugins()}
    assert PLUGIN_ID not in scanned
    assert not _has_pack()
    assert PLUGIN_ID not in _command_plugins()
    assert SkillLoader().resolve_trigger(f"/{SKILL_PACK}") is None
    assert PLUGIN_ID not in _http_command_plugins(client)
    assert SKILL_PACK not in _skill_names(client)


def test_install_leaves_the_plugin_disabled(client, config_dir):
    """Stage 1 alone: the artifact is on disk, the plugin is off by default."""
    assert _install()["status"] == "extracted"
    assert _plugin_dir(config_dir).is_dir()

    _invalidate()
    assert not _has_pack()
    assert SKILL_PACK not in _skill_names(client)


def test_disable_after_enable_takes_the_plugin_back_out(client, config_dir):
    """The toggle is the switch: enabling surfaces the pack, disabling hides it."""
    assert _install()["status"] == "extracted"
    assert client.post(f"/api/plugins/{PLUGIN_ID}/enable", json={"enabled": True}).json()["saved"]
    assert _has_pack()
    assert SKILL_PACK in _skill_names(client)

    off = client.post(f"/api/plugins/{PLUGIN_ID}/enable", json={"enabled": False})
    assert off.status_code == 200 and off.json() == {"id": PLUGIN_ID, "enabled": False, "saved": True}

    assert not _has_pack()
    assert SKILL_PACK not in _skill_names(client)
    assert _plugin_dir(config_dir).is_dir(), "disable is not remove: the folder stays"
