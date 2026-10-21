"""MAN-01..04 — manifest v2, the v1 adapter and quarantine.

v1 stays loadable. v2 adds the identity fields the marketplace needs. Unknown
top-level fields and unknown component keys fail closed; an install with an
invalid manifest is quarantined and a hash mismatch never extracts.
"""
from __future__ import annotations

import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_market
from core.plugin_manifest import MANIFEST_FILENAME, load_manifest
from core.plugin_registry import (
    CapabilityKind,
    ManifestV1Adapter,
    PluginDescriptor,
)
from core.plugin_store import sha256_hex


def _v1() -> dict:
    return {
        "manifest_version": 1,
        "name": "acme-research",
        "version": "1.4.0",
        "description": "Acme research",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [
                {
                    "name": "acme",
                    "description": "Run acme research",
                    "template": "Research {input}",
                }
            ],
            "tools": ["read_file"],
        },
    }


def _v2(**over: object) -> dict:
    manifest = {
        "manifest_version": 2,
        "name": "acme-research",
        "version": "2.0.0",
        "description": "Acme research",
        "publisher": {"name": "Acme", "verified": "acme.example"},
        "license": "MIT",
        "engines": {"ephe": ">=0.1.0"},
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [],
            "tools": ["read_file"],
            "agents": [{"name": "acme-scout", "description": "Scout"}],
        },
    }
    manifest.update(over)
    return manifest


def _write(root: Path, manifest: dict) -> Path:
    plugin = root / str(manifest["name"])
    plugin.mkdir(parents=True)
    (plugin / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    return plugin


def test_v2_required_fields(tmp_path) -> None:
    plugin = _write(tmp_path, _v2())
    manifest, error = load_manifest(plugin)
    assert error is None and manifest is not None
    assert manifest["manifest_version"] == 2

    missing_publisher = _v2()
    missing_publisher.pop("publisher")
    manifest, error = load_manifest(_write(tmp_path / "a", missing_publisher))
    assert manifest is None and error is not None and "publisher" in error

    missing_license = _v2()
    missing_license.pop("license")
    manifest, error = load_manifest(_write(tmp_path / "b", missing_license))
    assert manifest is None and error is not None and "license" in error


def test_unknown_component_refused(tmp_path) -> None:
    manifest = _v2(
        components={
            "skills": [],
            "commands": [],
            "frobnicate": {"wat": True},
        }
    )
    manifest, error = load_manifest(_write(tmp_path / "bad", manifest))
    assert manifest is None
    assert error is not None and "frobnicate" in error


def test_unknown_top_level_field_refused(tmp_path) -> None:
    manifest = _v2(trust_me=True)
    manifest, error = load_manifest(_write(tmp_path / "bad", manifest))
    assert manifest is None
    assert error is not None and "trust_me" in error


def test_v1_adapter(tmp_path) -> None:
    plugin_dir = _write(tmp_path, _v1())
    manifest, error = load_manifest(plugin_dir)
    assert error is None and manifest is not None
    descriptor = PluginDescriptor(
        id=manifest["name"],
        version=manifest["version"],
        manifest=manifest,
        source=str(plugin_dir),
    )
    capabilities = ManifestV1Adapter(descriptor).capabilities()
    assert [cap.kind for cap in capabilities] == [CapabilityKind.COMMAND]
    assert capabilities[0].id == "acme-research.acme"
    assert capabilities[0].template == "Research {input}"


def _zip(manifest: dict) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            f"{manifest['name']}/{MANIFEST_FILENAME}", json.dumps(manifest)
        )
    return buf.getvalue()


def test_quarantine(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    broken = _v2()
    broken.pop("publisher")
    payload = _zip(broken)
    entry = {
        "name": "acme-research",
        "version": "2.0.0",
        "sha256": sha256_hex(payload),
        "url": "https://artifact.invalid/acme.zip",
        "trust": "local",
    }
    status = plugin_market.install_from_marketplace(
        "acme-research",
        marketplace={"plugins": [entry]},
        fetcher=lambda url: payload,
        allow_local_trust=True,
    )
    assert status["status"] == "quarantined", status
    assert "publisher" in status["error"]

    mismatched = {**entry, "sha256": "00" * 32}
    status = plugin_market.install_from_marketplace(
        "acme-research",
        marketplace={"plugins": [mismatched]},
        fetcher=lambda url: payload,
        allow_local_trust=True,
    )
    assert status["status"] == "hash_mismatch"
