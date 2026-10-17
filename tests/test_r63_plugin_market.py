"""R63 — Plugin marketplace + CLI (Extensions wave E4a).

Resolution + installation contract:
1. `plugin-marketplace.json` (repo root) lists installable entries
   {name, version, sha256, url, description, tags}; parsing is fail-soft.
2. `install_from_marketplace(name)`: resolve → fetch (injectable fetcher) →
   sha256 verify → safe unzip (zip-slip guard) → manifest validation.
   - hash mismatch: REJECTED, nothing extracted.
   - invalid manifest: quarantined (directory removed), honest status.
3. `ephe plugin list|enable|disable|install` drives the same core functions.
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

from core import plugin_market, plugin_manifest  # noqa: E402
from core.plugin_store import sha256_hex  # noqa: E402


def _zip_bytes(dirname: str, manifest: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{dirname}/ephe-plugin.json", json.dumps(manifest))
    return buf.getvalue()


VALID = {
    "manifest_version": 1,
    "name": "my-tool",
    "version": "1.2.3",
    "description": "A bundled tool",
    "permissions": {"tool_families": ["read"], "data_roots": []},
    "components": {"skills": [], "commands": []},
}

MARKET = {
    "version": 1,
    "plugins": [
        {"name": "my-tool", "version": "1.2.3", "sha256": "deadbeef", "url": "https://example.invalid/my-tool.zip", "description": "d", "tags": []},
    ],
}


class TestMarketplace:

    def test_marketplace_file_ships_and_parses(self):
        """G: repo marketplace file W: load T: valid structure."""
        data = plugin_market.load_marketplace()
        assert data["version"] == 1
        assert isinstance(data["plugins"], list)

    def test_resolve_entry(self, tmp_path, monkeypatch):
        mp = tmp_path / "market.json"
        mp.write_text(json.dumps(MARKET))
        entry = plugin_market.resolve_entry("my-tool", path=mp)
        assert entry and entry["version"] == "1.2.3"
        assert plugin_market.resolve_entry("nope", path=mp) is None


class TestInstall:

    def test_hash_mismatch_rejects_without_extract(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        payload = _zip_bytes("my-tool", VALID)
        entry = {**MARKET["plugins"][0], "sha256": "00" * 32}
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [entry]}, fetcher=lambda url: payload
        )
        assert status["status"] == "hash_mismatch"
        assert not (tmp_path / "cfg" / "plugins" / "my-tool").exists()

    def test_install_ok_registers_plugin(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        payload = _zip_bytes("my-tool", VALID)
        entry = {**MARKET["plugins"][0], "sha256": sha256_hex(payload)}
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [entry]}, fetcher=lambda url: payload
        )
        assert status["status"] == "extracted"
        pdir = tmp_path / "cfg" / "plugins" / "my-tool"
        manifest, err = plugin_manifest.load_manifest(pdir)
        assert err is None and manifest["version"] == "1.2.3"

    def test_invalid_manifest_quarantined(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        bad = {**VALID, "version": "not-semver"}
        payload = _zip_bytes("my-tool", bad)
        entry = {**MARKET["plugins"][0], "sha256": sha256_hex(payload)}
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [entry]}, fetcher=lambda url: payload
        )
        assert status["status"] == "quarantined" and status["error"]
        assert not (tmp_path / "cfg" / "plugins" / "my-tool").exists()

    def test_zip_slip_member_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("my-tool/ephe-plugin.json", json.dumps(VALID))
            zf.writestr("my-tool/../../escape.sh", "rm -rf /")
        payload = buf.getvalue()
        entry = {**MARKET["plugins"][0], "sha256": sha256_hex(payload)}
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [entry]}, fetcher=lambda url: payload
        )
        assert status["status"] == "unsafe_archive"
        assert not (tmp_path / "escape.sh").exists()

    def test_unknown_name_fails_honest(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        status = plugin_market.install_from_marketplace(
            "ghost", marketplace={"plugins": []}, fetcher=lambda url: b""
        )
        assert status["status"] == "unknown_plugin"

    def test_missing_url_fails_honest(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [{**MARKET["plugins"][0], "url": ""}]},
            fetcher=lambda url: b"",
        )
        assert status["status"] == "no_url"


class TestCli:

    def test_parser_knows_plugin_group(self):
        from ephe_cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["plugin", "list"])
        assert args.command == "plugin" and args.action == "list"
        args = parser.parse_args(["plugin", "enable", "my-tool"])
        assert args.action == "enable" and args.plugin_id == "my-tool"
        args = parser.parse_args(["plugin", "install", "my-tool"])
        assert args.action == "install"

    def test_plugin_list_runs(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        from ephe_cli import cmd_plugin

        rc = cmd_plugin(type("A", (), {"action": "list"})())
        assert rc == 0
        out = capsys.readouterr().out
        assert "web-research" in out
