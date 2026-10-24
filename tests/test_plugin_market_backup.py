"""An install keeps the old version until the new one is committed.

The staging checks were already tested. These cover the two states around the
commit: the one-slot backup that makes a rollback possible, and the inspect hook
that can refuse a staged candidate without touching the installed version.
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

from core import plugin_market  # noqa: E402
from core.plugin_store import sha256_hex  # noqa: E402


def manifest(version: str) -> dict:
    return {
        "manifest_version": 1,
        "name": "alpha",
        "version": version,
        "description": f"alpha {version}",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {"skills": [], "commands": []},
    }


def artifact(version: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("alpha/ephe-plugin.json", json.dumps(manifest(version)))
    return buf.getvalue()


def entry(version: str, payload: bytes) -> dict:
    return {
        "name": "alpha",
        "version": version,
        "url": "https://artifact.invalid/alpha.zip",
        "sha256": sha256_hex(payload),
    }


def install(root: Path, version: str, *, inspect=None) -> dict:
    payload = artifact(version)
    return plugin_market.install_from_marketplace(
        "alpha",
        marketplace={"plugins": [entry(version, payload)]},
        fetcher=lambda url: payload,
        root=root,
        allow_local_trust=True,
        inspect=inspect,
    )


@pytest.fixture
def plugins(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    root = tmp_path / "cfg" / "plugins"
    root.mkdir(parents=True)
    return root


def installed(root: Path) -> str:
    data = json.loads((root / "alpha" / "ephe-plugin.json").read_text(encoding="utf-8"))
    return data["version"]


class TestBackup:

    def test_a_replacement_keeps_the_old_version_as_backup(self, plugins):
        assert install(plugins, "1.0.0")["status"] == "extracted"
        assert install(plugins, "2.0.0")["status"] == "extracted"

        assert installed(plugins) == "2.0.0"
        backup = plugins / ".previous-alpha"
        assert backup.is_dir()
        assert json.loads((backup / "ephe-plugin.json").read_text())["version"] == "1.0.0"

    def test_inspect_refusal_leaves_the_installed_version_untouched(self, plugins):
        assert install(plugins, "1.0.0")["status"] == "extracted"

        refused = install(plugins, "2.0.0", inspect=lambda _dir, _manifest: "permission missing")

        assert refused["status"] == "refused"
        assert "permission missing" in refused["error"]
        assert installed(plugins) == "1.0.0"
        assert not (plugins / ".previous-alpha").exists()
        assert not (plugins / ".staging-alpha").exists()

    def test_a_failed_commit_restores_the_old_version(self, plugins, monkeypatch):
        assert install(plugins, "1.0.0")["status"] == "extracted"
        original = Path.rename

        def fail_candidate(self, target):
            if self.parent.name == "payload" and Path(target).name == "alpha":
                raise OSError("disk full")
            return original(self, target)

        monkeypatch.setattr(Path, "rename", fail_candidate)
        result = install(plugins, "2.0.0")

        assert result["status"] == "commit_failed"
        assert installed(plugins) == "1.0.0"
        assert not (plugins / ".previous-alpha").exists()
        assert not (plugins / ".staging-alpha").exists()
