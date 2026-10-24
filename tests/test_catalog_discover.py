"""The catalogue discovery probes sources without publishing or extracting them."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "catalog_discover.py"


def _load():
    spec = importlib.util.spec_from_file_location("catalog_discover_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


discover = _load()


def _archive(manifest: dict) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        bundle.writestr(".qoder-plugin/plugin.json", json.dumps(manifest))
        bundle.writestr("skills/demo/SKILL.md", "# demo\n")
    return payload.getvalue()


def _qoder_index(url: str, digest: str) -> dict:
    return {
        "plugins": [
            {
                "name": "alpha",
                "version": "1.0.0",
                "author": {"name": "Alpha"},
                "source": {"source": "archive", "url": url, "sha256": digest},
            }
        ]
    }


def _ephe_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    plugin = root / "plugins" / "alpha" / "ephe-plugin.json"
    plugin.parent.mkdir(parents=True)
    plugin.write_text(json.dumps({
        "manifest_version": 1,
        "name": "alpha",
        "version": "1.0.0",
        "description": "Alpha",
        "components": {"skills": [{"name": "demo", "path": "demo/SKILL.md"}]},
    }), encoding="utf-8")
    skill = root / "skills" / "coding-agent"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# coding-agent\n", encoding="utf-8")
    (root / "skills" / "pack-index.json").write_text(json.dumps({"packs": [
        {"id": "dev-pack", "title": "Development", "skills": ["coding-agent"]}
    ]}), encoding="utf-8")
    return root


def test_ephe_lists_first_party_plugins_and_skill_packs(tmp_path):
    rows = discover.discover_ephe(_ephe_root(tmp_path))
    plugins = [row for row in rows if row["kind"] == "plugin"]
    packs = [row for row in rows if row["kind"] == "skill-pack"]
    assert plugins[0]["name"] == "alpha" and plugins[0]["status"] == "published"
    assert packs[0]["name"] == "dev-pack"
    assert packs[0]["skills"] == ["coding-agent"]
    assert packs[0]["license"] == "project"


def test_qoder_archive_is_hashed_and_licensed():
    manifest = {"name": "alpha", "license": "MIT", "repository": "https://example.test/alpha", "skills": "./skills/"}
    data = _archive(manifest)
    rows, errors = discover.discover_qoder(
        _qoder_index("https://example.test/alpha.zip", hashlib.sha256(data).hexdigest()),
        fetch_bytes=lambda _url: data,
    )
    assert errors == []
    row = rows[0]
    assert row["archive_sha256_ok"] is True
    assert row["license"] == "MIT"
    assert row["status"] == "discovered"
    assert row["components"] == ["skills"]


def test_a_qoder_hash_mismatch_is_refused():
    data = _archive({"name": "alpha", "license": "MIT", "skills": "./skills/"})
    rows, _ = discover.discover_qoder(
        _qoder_index("https://example.test/alpha.zip", "0" * 64),
        fetch_bytes=lambda _url: data,
    )
    assert rows[0]["status"] == "refused_hash"
    assert rows[0]["archive_sha256_ok"] is False


def test_a_qoder_pack_without_a_licence_is_refused():
    data = _archive({"name": "alpha", "skills": "./skills/"})
    rows, _ = discover.discover_qoder(
        _qoder_index("https://example.test/alpha.zip", hashlib.sha256(data).hexdigest()),
        fetch_bytes=lambda _url: data,
    )
    assert rows[0]["status"] == "refused_license"


def test_a_qoder_native_pack_is_incompatible():
    data = _archive({"name": "alpha", "license": "MIT", "skills": "./skills/", "canvas": {"viewers": []}})
    rows, _ = discover.discover_qoder(
        _qoder_index("https://example.test/alpha.zip", hashlib.sha256(data).hexdigest()),
        fetch_bytes=lambda _url: data,
    )
    assert rows[0]["compatibility"] == "qoder-native"
    assert rows[0]["status"] == "incompatible"


def test_an_interface_alone_is_not_native():
    data = _archive({"name": "alpha", "license": "MIT", "skills": "./skills/", "interface": {"displayName": "Alpha"}})
    rows, _ = discover.discover_qoder(
        _qoder_index("https://example.test/alpha.zip", hashlib.sha256(data).hexdigest()),
        fetch_bytes=lambda _url: data,
    )
    assert rows[0]["compatibility"] == "skills-only"


def test_an_archive_url_with_a_space_is_quoted():
    sys.path.insert(0, str(SCRIPT.parent))
    import catalog_fetch

    quoted = catalog_fetch.ascii_url("https://example.test/a b.zip")
    assert quoted.endswith("a%20b.zip")


def _mcp_payload() -> dict:
    meta = {"io.modelcontextprotocol.registry/official": {"isLatest": True}}
    return {"servers": [
        {
            "server": {
                "name": "io.test/remote",
                "version": "1.0.0",
                "title": "Remote",
                "remotes": [{"type": "streamable-http", "url": "https://mcp.example.test"}],
                "repository": {"url": "https://example.test/remote"},
            },
            "_meta": meta,
        },
        {
            "server": {
                "name": "io.test/local",
                "version": "1.0.0",
                "packages": [{
                    "registryType": "npm",
                    "identifier": "local-mcp",
                    "runtimeHint": "npx",
                    "transport": {"type": "stdio"},
                    "environmentVariables": [{"name": "TOKEN", "isSecret": True}],
                }],
            },
            "_meta": meta,
        },
    ]}


def test_mcp_registry_maps_remote_and_package_entries():
    rows = discover.discover_mcp([_mcp_payload()])
    by_name = {row["name"]: row for row in rows}
    assert by_name["io.test/remote"]["transport"] == "streamable-http"
    assert by_name["io.test/remote"]["endpoint"] == "https://mcp.example.test"
    assert by_name["io.test/local"]["transport"] == "stdio"
    assert by_name["io.test/local"]["env"][0]["name"] == "TOKEN"
    assert all(row["kind"] == "connector" for row in rows)


def test_claude_without_a_licence_is_refused():
    index = {"owner": {"name": "Anthropic"}, "plugins": [
        {"name": "demo", "version": "1.0.0", "source": "./plugins/demo"}
    ]}
    rows, _ = discover.discover_claude(
        index, fetch_bytes=lambda _url: json.dumps({"name": "demo"}).encode()
    )
    assert rows[0]["status"] == "refused_license"
    assert "no licence" in rows[0]["reason"]


def test_claude_with_a_permissive_licence_is_discovered():
    index = {"owner": {"name": "Anthropic"}, "plugins": [
        {"name": "demo", "version": "1.0.0", "source": "./plugins/demo"}
    ]}
    rows, _ = discover.discover_claude(
        index,
        fetch_bytes=lambda _url: json.dumps({"name": "demo", "license": "MIT", "skills": "./skills/"}).encode(),
    )
    assert rows[0]["status"] == "discovered"
    assert rows[0]["license"] == "MIT"


def test_cli_writes_only_the_report(tmp_path):
    root = _ephe_root(tmp_path)
    before = {path for path in root.rglob("*")}
    out = tmp_path / "run" / "candidates.json"
    assert discover.main(["--sources", "ephe", "--root", str(root), "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["counts"]["total"] == 2
    assert set(report["sources"]) == {"ephe"}
    assert out.is_file()
    assert {path for path in root.rglob("*")} == before


def test_the_curated_pack_index_has_five_packs_and_covers_51_skills():
    root = Path(__file__).resolve().parents[1]
    packs = json.loads((root / "skills" / "pack-index.json").read_text(encoding="utf-8"))["packs"]
    assert len(packs) == 5
    ids = [pack["id"] for pack in packs]
    assert len(set(ids)) == 5
    for pack in packs:
        assert len(pack["skills"]) == len(set(pack["skills"]))
    skills = {skill for pack in packs for skill in pack["skills"]}
    skill_dirs = {
        path.name for path in (root / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    assert len(skills) == 51
    assert skills == skill_dirs
    plugin_names = {path.parent.name for path in (root / "plugins").glob("*/ephe-plugin.json")}
    assert not set(ids) & plugin_names


def test_http_is_refused_before_network():
    sys.path.insert(0, str(SCRIPT.parent))
    import catalog_fetch

    with pytest.raises(ValueError):
        catalog_fetch.fetch("http://example.test/index.json")


def test_a_redirect_is_refused():
    sys.path.insert(0, str(SCRIPT.parent))
    import catalog_fetch

    handler = catalog_fetch._NoRedirect()
    request = urllib.request.Request("https://example.test/index.json")
    with pytest.raises(urllib.error.HTTPError) as error:
        handler.redirect_request(request, None, 302, "Found", {}, "https://evil.test/")
    assert error.value.code == 302


def test_the_size_cap_is_enforced(monkeypatch):
    sys.path.insert(0, str(SCRIPT.parent))
    import catalog_fetch

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size):
            return b"x" * size

    monkeypatch.setattr(catalog_fetch, "_OPENER", SimpleNamespace(open=lambda *_a, **_k: Response()))
    with pytest.raises(ValueError):
        catalog_fetch.fetch("https://example.test/index.json", max_bytes=4)
