"""GAP-02 — install-time signatures and local trust.

Official, verified and community entries need a valid artifact signature even
when the enable-time drift gate is off. A local unsigned artifact installs only
with explicit trust and lands disabled. Tampering after signing is quarantined.
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

from core import plugin_market, plugin_signing
from core.plugin_store import sha256_hex


def _manifest(name: str = "my-tool") -> dict:
    return {
        "manifest_version": 1,
        "name": name,
        "version": "1.2.3",
        "description": "indexed plugin",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": []},
    }


def _zip_tree(source: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent))
    return buf.getvalue()


def _signed(tmp_path: Path) -> tuple[bytes, dict, bytes]:
    private, public = plugin_signing.generate_keypair()
    source = tmp_path / "src" / "my-tool"
    source.mkdir(parents=True)
    (source / "ephe-plugin.json").write_text(
        json.dumps(_manifest()), encoding="utf-8"
    )
    (source / "README.md").write_text("signed content\n", encoding="utf-8")
    record = plugin_signing.sign_plugin_dir(source, private)
    return _zip_tree(source), record, public


def _entry(payload: bytes, trust: str, signature: dict | None = None) -> dict:
    entry = {
        "name": "my-tool",
        "version": "1.2.3",
        "sha256": sha256_hex(payload),
        "url": "https://market.example.invalid/my-tool.zip",
        "description": "indexed plugin",
        "tags": [],
        "trust": trust,
    }
    if signature is not None:
        entry["signature"] = signature
    return entry


@pytest.fixture()
def device(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    from core import audit_log, plugin_runtime

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    plugin_runtime.invalidate_ownership_cache()
    yield tmp_path / "cfg"
    plugin_runtime.invalidate_ownership_cache()


def test_tampered_artifact_is_quarantined(device, tmp_path) -> None:
    payload, record, public = _signed(tmp_path)
    source = tmp_path / "src" / "my-tool"
    (source / "tampered.txt").write_text("added after signing\n", encoding="utf-8")
    tampered = _zip_tree(source)
    status = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry(tampered, "official", record)]},
        fetcher=lambda url: tampered,
        trusted_public_keys=[public],
    )
    assert status["status"] == "quarantined"
    assert "signature_invalid" in status["error"]
    assert not (device / "plugins" / "my-tool").exists()


def test_missing_signature_is_refused_for_official_and_community(
    device, tmp_path, monkeypatch
) -> None:
    payload, _record, _public = _signed(tmp_path)
    monkeypatch.setattr(plugin_signing, "signature_check_enabled", lambda: False)
    for trust in ("official", "verified", "community"):
        status = plugin_market.install_from_marketplace(
            "my-tool",
            marketplace={"plugins": [_entry(payload, trust)]},
            fetcher=lambda url: payload,
        )
        assert status["status"] == "signature_required", trust
        assert status["trust"] == trust
    assert not (device / "plugins" / "my-tool").exists()


def test_a_valid_signature_installs_for_official(device, tmp_path) -> None:
    payload, record, public = _signed(tmp_path)
    status = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry(payload, "official", record)]},
        fetcher=lambda url: payload,
        trusted_public_keys=[public],
    )
    assert status["status"] == "extracted"
    assert status["trust"] == "official"
    assert (device / "plugins" / "my-tool" / "ephe-plugin.json").is_file()


def test_local_unsigned_needs_explicit_trust(device, tmp_path) -> None:
    payload, _record, _public = _signed(tmp_path)
    refused = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry(payload, "local")]},
        fetcher=lambda url: payload,
    )
    assert refused["status"] == "local_trust_required"
    assert not (device / "plugins" / "my-tool").exists()

    accepted = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry(payload, "local")]},
        fetcher=lambda url: payload,
        allow_local_trust=True,
    )
    assert accepted["status"] == "extracted"
    assert accepted["trust"] == "local"
    assert accepted["warning"] == "local_trust"

    from core import plugin_runtime

    snapshot = plugin_runtime.lifecycle().snapshot("my-tool")
    assert snapshot.enabled is False


def test_blocked_and_unknown_trust_are_refused(device, tmp_path) -> None:
    payload, _record, _public = _signed(tmp_path)
    blocked = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry(payload, "blocked")]},
        fetcher=lambda url: payload,
    )
    assert blocked["status"] == "blocked_source"
    unknown = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry(payload, "trusted-ish")]},
        fetcher=lambda url: payload,
    )
    assert unknown["status"] == "invalid_trust"


def test_cli_install_accepts_explicit_local_trust() -> None:
    from ephe_cli import build_parser

    args = build_parser().parse_args(["plugin", "install", "my-tool", "--trust-local"])
    assert args.trust_local is True


def test_cli_plugin_toggle_uses_the_lifecycle(device) -> None:
    from argparse import Namespace

    from core import plugin_runtime
    from ephe_cli import cmd_plugin

    assert cmd_plugin(Namespace(action="disable", plugin_id="web-research")) == 0
    assert plugin_runtime.lifecycle().snapshot("web-research").enabled is False
    assert cmd_plugin(Namespace(action="enable", plugin_id="web-research")) == 0
    assert plugin_runtime.lifecycle().snapshot("web-research").enabled is True
