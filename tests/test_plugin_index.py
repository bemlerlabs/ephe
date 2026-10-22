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


def _signed_at(root: Path, version: str) -> tuple[bytes, dict, bytes]:
    private, public = plugin_signing.generate_keypair()
    source = root / "src" / "my-tool"
    source.mkdir(parents=True)
    manifest = _manifest()
    manifest["version"] = version
    (source / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "README.md").write_text("signed content\n", encoding="utf-8")
    record = plugin_signing.sign_plugin_dir(source, private)
    return _zip_tree(source), record, public


def _entry_at(payload: bytes, version: str, signature: dict) -> dict:
    entry = _entry(payload, "official", signature)
    entry["version"] = version
    return entry


def test_anti_rollback_floor(device, tmp_path) -> None:
    """GIVEN a signed 2.0.0 is installed
    WHEN a signed 1.0.0 from a trusted key is offered
    THEN the install is refused and the newer version stays on disk.

    T-03: an old artifact served by a listing, or signed by a key that was
    trusted once, must not downgrade an install. The signature proves who made
    the artifact, not that it is the newest one the user should run.
    """
    newest, newest_record, newest_key = _signed_at(tmp_path / "v2", "2.0.0")
    installed = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry_at(newest, "2.0.0", newest_record)]},
        fetcher=lambda url: newest,
        trusted_public_keys=[newest_key],
    )
    assert installed["status"] == "extracted"

    older, older_record, older_key = _signed_at(tmp_path / "v1", "1.0.0")
    refused = plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [_entry_at(older, "1.0.0", older_record)]},
        fetcher=lambda url: older,
        trusted_public_keys=[newest_key, older_key],
    )
    assert refused["status"] == "downgrade_refused"
    assert "2.0.0" in refused["error"] and "1.0.0" in refused["error"]

    on_disk = json.loads(
        (device / "plugins" / "my-tool" / "ephe-plugin.json").read_text(encoding="utf-8")
    )
    assert on_disk["version"] == "2.0.0"


def test_reinstalling_the_same_version_is_not_a_downgrade(device, tmp_path) -> None:
    """GIVEN 2.0.0 is installed
    WHEN the same 2.0.0 is installed again
    THEN it replaces cleanly, so a repair is possible and only a lower version
    is refused."""
    payload, record, public = _signed_at(tmp_path / "v2", "2.0.0")
    for _ in range(2):
        status = plugin_market.install_from_marketplace(
            "my-tool",
            marketplace={"plugins": [_entry_at(payload, "2.0.0", record)]},
            fetcher=lambda url: payload,
            trusted_public_keys=[public],
        )
        assert status["status"] == "extracted"
