"""The bundled marketplace index is generated, reproducible and hash-true.

The builder packages every first-party plugin into an immutable ZIP, writes the
v2 index and optionally signs both with a supplied key. A symlink never enters
an artifact.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import marketplace_index, plugin_signing  # noqa: E402
from core.plugin_store import sha256_hex  # noqa: E402

SCRIPT = ROOT / "scripts" / "build_marketplace.py"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def built(tmp_path):
    out = tmp_path / "marketplace"
    result = run("--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return out, index


def _generator():
    spec = importlib.util.spec_from_file_location(
        "generate_marketplace_under_test", ROOT / "scripts" / "generate_marketplace.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_marketplace_metadata_matches_the_generator():
    generated = _generator().generate(ROOT)
    current = json.loads((ROOT / "ephe-marketplace.json").read_text(encoding="utf-8"))
    assert generated == current


def test_a_rebuild_without_the_previous_output_keeps_the_labels(tmp_path):
    (tmp_path / "plugins").symlink_to(ROOT / "plugins", target_is_directory=True)
    (tmp_path / "marketplace").mkdir()
    shutil.copyfile(
        ROOT / "marketplace" / "first-party.json",
        tmp_path / "marketplace" / "first-party.json",
    )
    (tmp_path / "marketplace" / "third-party.json").write_text(
        '{"format": 1, "plugins": []}\n', encoding="utf-8"
    )
    generated = _generator().generate(tmp_path)
    by_name = {entry["name"]: entry for entry in generated["plugins"]}
    assert len(by_name) == 16
    presets = [name for name, entry in by_name.items() if entry.get("quality_label") == "capability-preset"]
    assert len(presets) == 7
    assert by_name["documents"]["measurement"]["pass3"]
    source = json.loads(
        (ROOT / "marketplace" / "first-party.json").read_text(encoding="utf-8")
    )
    source_by_name = {entry["name"]: entry for entry in source["plugins"]}
    assert (
        by_name["local-document-factory"]["description"]
        == source_by_name["local-document-factory"]["description"]
    )


class TestBuild:

    def test_every_entry_has_one_valid_version(self, built):
        out, index = built
        parsed = marketplace_index.validate_index(index, source_kind="bundled")
        plugins = [entry for entry in parsed["plugins"] if entry["kind"] == "plugin"]
        packs = [entry for entry in parsed["plugins"] if entry["kind"] == "skill-pack"]
        # 16 first-party plugins; five first-party packs and the adapted
        # Superpowers pack, which is bundled third-party content.
        assert len(plugins) == 16
        assert len(packs) == 6
        for entry in parsed["plugins"]:
            assert len(entry["versions"]) == 1
            version = entry["versions"][0]
            archive = out / version["source"]["url"]
            assert archive.is_file()
            assert sha256_hex(archive.read_bytes()) == version["source"]["sha256"]
            assert "latest" not in version["source"]["url"]

    def test_the_archive_unpacks_to_the_named_plugin(self, built):
        out, index = built
        plugin = next(entry for entry in index["plugins"] if entry.get("kind", "plugin") == "plugin")
        version = plugin["versions"][0]
        with zipfile.ZipFile(out / version["source"]["url"]) as zf:
            names = zf.namelist()
        assert all(not name.startswith("/") for name in names)
        assert any(name.endswith("/ephe-plugin.json") for name in names)
        assert all(not name.startswith("../") for name in names)

    def test_the_index_separates_first_party_from_third_party(self, built):
        _, index = built
        by_name = {entry["name"]: entry for entry in index["plugins"]}
        assert by_name["superpowers"]["publisher"]["verified"] is False
        assert by_name["superpowers"]["provenance"] == "third-party"
        assert by_name["superpowers"]["kind"] == "skill-pack"
        assert by_name["superpowers"]["quality_label"] == "bundled"
        first_party = [e for n, e in by_name.items() if n != "superpowers"]
        assert {entry["publisher"]["name"] for entry in first_party} == {"Ephe"}
        assert all(entry["publisher"]["verified"] for entry in first_party)
        assert {entry.get("kind", "plugin") for entry in index["plugins"]} == {"plugin", "skill-pack"}

    def test_skill_packs_are_bundled_and_cover_51_skills(self, built):
        out, index = built
        packs = [
            entry
            for entry in index["plugins"]
            if entry.get("kind") == "skill-pack"
            and entry.get("provenance") == "first-party"
        ]
        assert len(packs) == 5
        plugin_names = {entry["name"] for entry in index["plugins"] if entry.get("kind", "plugin") == "plugin"}
        assert not {pack["name"] for pack in packs} & plugin_names
        covered: set[str] = set()
        for pack in packs:
            archive = out / pack["versions"][0]["source"]["url"]
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                manifest = json.loads(zf.read(f"{pack['name']}/pack.json"))
            assert manifest["license"] == "LicenseRef-Ephe"
            assert all(name.startswith(f"{pack['name']}/") for name in names)
            skills = {
                name.split("/skills/", 1)[1].split("/", 1)[0]
                for name in names if "/skills/" in name
            }
            assert sorted(skills) == sorted(manifest["skills"])
            assert all(f"{pack['name']}/skills/{skill}/SKILL.md" in names for skill in skills)
            covered |= skills
        assert len(covered) == 51

    def test_two_runs_are_byte_identical(self, tmp_path):
        first = tmp_path / "a"
        second = tmp_path / "b"
        assert run("--out", str(first)).returncode == 0
        assert run("--out", str(second)).returncode == 0
        assert (first / "index.json").read_bytes() == (second / "index.json").read_bytes()
        archives = sorted((first / "artifacts").glob("*.zip"))
        assert archives
        for archive in archives:
            assert archive.read_bytes() == (second / "artifacts" / archive.name).read_bytes()

    def test_a_symlink_in_a_plugin_is_refused(self, tmp_path):
        plugins = tmp_path / "plugins"
        plugin = plugins / "alpha"
        plugin.mkdir(parents=True)
        (plugin / "ephe-plugin.json").write_text(
            json.dumps(
                {
                    "manifest_version": 1,
                    "name": "alpha",
                    "version": "1.0.0",
                    "description": "alpha",
                }
            )
        )
        (plugin / "link").symlink_to("/etc/hosts")
        result = run("--plugins", str(plugins), "--out", str(tmp_path / "out"))
        assert result.returncode != 0
        assert "symlink" in (result.stdout + result.stderr)


class TestSigning:

    def test_a_signed_index_and_artifact_verify(self, tmp_path):
        private = ec.generate_private_key(ec.SECP256R1())
        private_pem = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public_pem = private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key = tmp_path / "key.pem"
        key.write_bytes(private_pem)
        out = tmp_path / "marketplace"
        result = run("--out", str(out), "--sign-key", str(key), "--kid", "test")
        assert result.returncode == 0, result.stdout + result.stderr

        index = json.loads((out / "index.json").read_text(encoding="utf-8"))
        assert index["signature"]["alg"] == "ES256"
        body = {k: v for k, v in index.items() if k != "signature"}
        assert plugin_signing.verify(body, index["signature"]["signature"], public_pem)

        entry = next(entry for entry in index["plugins"] if entry.get("kind", "plugin") == "plugin")
        version = entry["versions"][0]
        assert isinstance(version["source"].get("signature"), dict)
        target = tmp_path / "unpacked"
        with zipfile.ZipFile(out / version["source"]["url"]) as zf:
            zf.extractall(target)
        plugin_dir = target / entry["name"]
        ok, reason = plugin_signing.verify_plugin_dir(
            plugin_dir, version["source"]["signature"], [public_pem]
        )
        assert ok, reason
