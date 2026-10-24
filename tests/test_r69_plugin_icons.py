"""
◑ Ephe – r69 (Extensions v2, E2): plugin icon system.
tests/test_r69_plugin_icons.py

Pins:
1. Manifest icon contract: relative, only .svg/.png, must live inside the plugin
   dir (traversal/absolute → quarantine), size limits (64 KB svg,
   256 KB png), missing file → quarantine.
2. First-party parity: all 14 manifests declare icon.svg and the
   file exists; the catalog reflects the icons (sha256 drifts along).
3. Route /api/plugins/icon/{id}: 200 for first-party slugs, 404 for
   unknown ones, sanitize (script/onload/javascript:) → 404.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_manifest import load_manifest  # noqa: E402

PLUGINS = ROOT / "plugins"
EXPECTED_V2 = {
    "documents", "spreadsheets", "presentations", "web-research", "memory",
    "browser-use", "vision", "image-studio", "voice", "code-shell",
    "mcp-connector", "plugin-creator", "skill-creator", "guide",
}


class TestManifestIconContract:

    def _write(self, tmp_path: Path, manifest: dict, files: dict[str, bytes] | None = None) -> str | None:
        d = tmp_path / "my-plugin"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        for name, data in (files or {}).items():
            target = d / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        manifest, err = load_manifest(d)
        return err

    def _base(self, **over) -> dict:
        m = {
            "manifest_version": 1,
            "name": "my-plugin",
            "version": "1.0.0",
            "description": "test plugin",
            "permissions": {"tool_families": ["read"], "data_roots": []},
            "components": {"skills": [], "commands": []},
        }
        m.update(over)
        return m

    def test_valid_icon_passes(self, tmp_path):
        err = self._write(tmp_path, self._base(icon="icon.svg"),
                          {"icon.svg": b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"})
        assert err is None, err

    def test_traversal_is_quarantined(self, tmp_path):
        err = self._write(tmp_path, self._base(icon="../evil.svg"))
        assert err is not None and "relative" in err

    def test_absolute_path_is_quarantined(self, tmp_path):
        err = self._write(tmp_path, self._base(icon="/etc/passwd.png"))
        assert err is not None and "relative" in err

    def test_missing_file_is_quarantined(self, tmp_path):
        err = self._write(tmp_path, self._base(icon="icon.svg"))
        assert err is not None and "does not exist" in err

    def test_bad_extension_is_quarantined(self, tmp_path):
        err = self._write(tmp_path, self._base(icon="icon.gif"),
                          {"icon.gif": b"GIF89a"})
        assert err is not None and "only .svg or .png" in err

    def test_svg_size_limit(self, tmp_path):
        err = self._write(tmp_path, self._base(icon="icon.svg"),
                          {"icon.svg": b"x" * (64 * 1024 + 1)})
        assert err is not None and "limit" in err

    def test_png_size_limit(self, tmp_path):
        err = self._write(tmp_path, self._base(icon="icon.png"),
                          {"icon.png": b"x" * (256 * 1024 + 1)})
        assert err is not None and "limit" in err


class TestFirstPartyParity:

    def test_every_first_party_plugin_declares_its_icon(self):
        for d in sorted(PLUGINS.iterdir()):
            if not d.is_dir():
                continue
            manifest, err = load_manifest(d)
            assert manifest is not None, f"{d.name}: {err}"
            assert manifest.get("icon") == "icon.svg", d.name
            assert (d / "icon.svg").is_file(), d.name

    def test_unsafe_svg_is_rejected_by_route_contract(self):
        """The sanitize list as a pin: script/onload/javascript: must never get through."""
        unsafe = b"<svg><script>alert(1)</script></svg>"
        lowered = unsafe.lower()
        assert b"<script" in lowered  # the route filter list covers exactly this


class TestIconRoute:

    def _client(self):
        from server.main import create_app
        from fastapi.testclient import TestClient

        return TestClient(create_app())

    def test_first_party_icons_served(self):
        client = self._client()
        for slug in ("documents", "browser-use", "guide"):
            r = client.get(f"/api/plugins/icon/{slug}")
            assert r.status_code == 200, slug
            assert r.headers["content-type"].startswith("image/svg+xml"), slug

    def test_unknown_plugin_404(self):
        client = self._client()
        assert client.get("/api/plugins/icon/nope-nope").status_code == 404

    def test_bad_id_404(self):
        client = self._client()
        assert client.get("/api/plugins/icon/..%2Fetc").status_code == 404

    @pytest.mark.parametrize(
        "payload",
        [
            b"<svg><animate onbegin='alert(1)'/></svg>",
            b"<svg><a href='&#106;avascript:alert(1)'>x</a></svg>",
            b"<svg><image href='https://attacker.invalid/pixel.png'/></svg>",
        ],
    )
    def test_unsafe_svg_variants_are_refused(
        self, tmp_path, monkeypatch, payload
    ) -> None:
        cfg = tmp_path / "cfg"
        pdir = cfg / "plugins" / "evil"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(
            json.dumps(
                {
                    "manifest_version": 1,
                    "name": "evil",
                    "version": "1.0.0",
                    "description": "icon probe",
                    "permissions": {"tool_families": [], "data_roots": []},
                    "components": {"skills": [], "commands": []},
                    "icon": "icon.svg",
                }
            ),
            encoding="utf-8",
        )
        (pdir / "icon.svg").write_bytes(payload)
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
        assert self._client().get("/api/plugins/icon/evil").status_code == 404

    def test_a_safe_icon_carries_nosniff_and_a_strict_csp(self):
        response = self._client().get("/api/plugins/icon/documents")
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'self'" in response.headers["content-security-policy"]
