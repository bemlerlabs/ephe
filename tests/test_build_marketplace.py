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


def test_the_committed_bundled_index_is_what_the_builder_generates():
    result = run("--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fresh" in result.stdout, result.stdout


def test_a_stale_index_row_is_named(tmp_path):
    shelf = tmp_path / "marketplace"
    shutil.copytree(ROOT / "marketplace", shelf)
    index_path = shelf / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    countdown = next(entry for entry in index["plugins"] if entry["name"] == "countdown")
    countdown["categories"] = ["meta"]
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = run("--check", "--out", str(shelf))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "plugins.countdown.categories[0]" in result.stdout, result.stdout
    assert "'meta' != 'widgets'" in result.stdout, result.stdout


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
    assert len(by_name) == 19
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
        # 19 first-party plugins; five first-party packs and the adapted
        # Superpowers pack, which is bundled third-party content.
        assert len(plugins) == 19
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


def _keypair(tmp_path: Path, name: str) -> tuple[Path, bytes]:
    """(key file, public PEM) for one ephemeral signing key."""
    private = ec.generate_private_key(ec.SECP256R1())
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key = tmp_path / name
    key.write_bytes(private_pem)
    return key, public_pem


@pytest.fixture(scope="module")
def signed_shelf(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("signed-shelf")
    key, public_pem = _keypair(tmp, "key.pem")
    out = tmp / "marketplace"
    result = run("--out", str(out), "--sign-key", str(key))
    assert result.returncode == 0, result.stdout + result.stderr
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return out, index, public_pem


def _repack(archive: Path, replacements: dict[str, bytes]) -> None:
    """Rewrite an archive with named members replaced, so a test can tamper one byte."""
    with zipfile.ZipFile(archive) as zf:
        members = [(info.filename, replacements.get(info.filename, zf.read(info.filename))) for info in zf.infolist()]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)


def test_two_signed_runs_are_byte_identical(tmp_path):
    key, _ = _keypair(tmp_path, "key.pem")
    first, second = tmp_path / "a", tmp_path / "b"
    assert run("--out", str(first), "--sign-key", str(key)).returncode == 0
    assert run("--out", str(second), "--sign-key", str(key)).returncode == 0
    assert (first / "index.json").read_bytes() == (second / "index.json").read_bytes()
    archives = sorted((first / "artifacts").glob("*.zip"))
    assert archives, "the signed build produced no archives"
    for archive in archives:
        assert archive.read_bytes() == (second / "artifacts" / archive.name).read_bytes(), archive.name


def test_a_flipped_byte_in_the_record_is_refused(signed_shelf):
    out, index, public_pem = signed_shelf
    entry = next(e for e in index["plugins"] if isinstance(e["versions"][0]["source"].get("signature"), dict))
    record = entry["versions"][0]["source"]["signature"]
    target = out / f"unpack-{entry['name']}"
    with zipfile.ZipFile(out / entry["versions"][0]["source"]["url"]) as zf:
        zf.extractall(target)
    plugin_dir = target / entry["name"]
    flipped_signature = {**record, "signature": record["signature"][:-4] + ("AAAA" if not record["signature"].endswith("AAAA") else "BBBB")}
    ok, reason = plugin_signing.verify_plugin_dir(plugin_dir, flipped_signature, [public_pem])
    assert not ok and reason, reason
    flipped_sha = {**record, "sha256": record["sha256"][:-1] + ("0" if record["sha256"][-1] != "0" else "1")}
    ok, reason = plugin_signing.verify_plugin_dir(plugin_dir, flipped_sha, [public_pem])
    assert not ok and "drift" in reason, reason


def test_a_record_from_another_bundle_is_refused(signed_shelf):
    out, index, public_pem = signed_shelf
    signed = [e for e in index["plugins"] if isinstance(e["versions"][0]["source"].get("signature"), dict)]
    assert len(signed) >= 2
    a, b = signed[0], signed[1]
    dirs = []
    for entry in (a, b):
        target = out / f"swap-{entry['name']}"
        with zipfile.ZipFile(out / entry["versions"][0]["source"]["url"]) as zf:
            zf.extractall(target)
        dirs.append(target / entry["name"])
    ok, reason = plugin_signing.verify_plugin_dir(
        dirs[0], b["versions"][0]["source"]["signature"], [public_pem]
    )
    assert not ok and "identity" in reason, reason


def test_a_record_from_another_key_is_refused(signed_shelf, tmp_path):
    out, index, _ = signed_shelf
    _, other_public = _keypair(tmp_path, "other.pem")
    entry = next(e for e in index["plugins"] if isinstance(e["versions"][0]["source"].get("signature"), dict))
    target = out / f"otherkey-{entry['name']}"
    with zipfile.ZipFile(out / entry["versions"][0]["source"]["url"]) as zf:
        zf.extractall(target)
    ok, reason = plugin_signing.verify_plugin_dir(
        target / entry["name"], entry["versions"][0]["source"]["signature"], [other_public]
    )
    assert not ok and "trusted key" in reason, reason


def test_verification_refuses_a_garbage_record_without_raising(signed_shelf):
    out, index, public_pem = signed_shelf
    entry = next(e for e in index["plugins"] if isinstance(e["versions"][0]["source"].get("signature"), dict))
    target = out / f"garbage-{entry['name']}"
    with zipfile.ZipFile(out / entry["versions"][0]["source"]["url"]) as zf:
        zf.extractall(target)
    ok, reason = plugin_signing.verify_plugin_dir(target / entry["name"], {}, [public_pem])
    assert ok is False and reason == "no signature record"


def test_the_shipped_shelf_rows_match_the_disk():
    """Index, disk and bytes agree pairwise, for every archive: no dead URL, no orphan,
    no artifact row whose claim the file beside it does not measure up to."""
    index = json.loads((ROOT / "marketplace" / "index.json").read_text(encoding="utf-8"))
    shipped = {p.name for p in (ROOT / "marketplace" / "artifacts").glob("*.zip")}
    named: set[str] = set()
    for entry in index["plugins"]:
        for version in entry["versions"]:
            url = str(version["source"]["url"])
            name = Path(url).name
            named.add(name)
            archive = ROOT / "marketplace" / "artifacts" / name
            assert archive.is_file(), f"{url}: named in the index, missing from disk"
            artifact = version.get("artifact") or {}
            assert artifact.get("file") == url, f"{name}: artifact row names {artifact.get('file')!r}"
            assert artifact.get("sha256") == sha256_hex(archive.read_bytes()), f"{name}: artifact sha256 lies"
            assert artifact.get("sizeBytes") == archive.stat().st_size, f"{name}: artifact size lies"
            assert version["source"]["sha256"] == artifact["sha256"], f"{name}: source and artifact hash differ"
    assert named == shipped, f"dead rows: {named - shipped}; orphans: {shipped - named}"
    assert len(shipped) >= 25
    for required in ("ephe-motion-studio", "ephe-template-library"):
        entry = next((e for e in index["plugins"] if e["name"] == required), None)
        assert entry is not None, f"{required}: not in the index"
        assert isinstance(entry["versions"][0]["source"].get("signature"), dict), f"{required}: unsigned"


def test_a_flipped_archive_byte_fails_the_check(tmp_path):
    shelf = tmp_path / "marketplace"
    shutil.copytree(ROOT / "marketplace", shelf)
    archive = shelf / "artifacts" / "countdown-0.1.0.zip"
    with zipfile.ZipFile(archive) as zf:
        victim = next(i.filename for i in zf.infolist() if not i.is_dir() and zf.read(i.filename))
        payload = zf.read(victim)
    _repack(archive, {victim: payload[:-1] + bytes([payload[-1] ^ 0xFF])})
    result = run("--check", "--out", str(shelf))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "artifact_sha256_mismatch" in result.stdout, result.stdout


def test_a_tampered_embedded_signature_fails_the_check(tmp_path):
    shelf = tmp_path / "marketplace"
    shutil.copytree(ROOT / "marketplace", shelf)
    archive = shelf / "artifacts" / "countdown-0.1.0.zip"
    sig_member = "countdown/ephe-plugin.sig.json"
    with zipfile.ZipFile(archive) as zf:
        record = json.loads(zf.read(sig_member))
    record["signature"] = "MEUCIQ" + record["signature"][6:]
    _repack(archive, {sig_member: (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")})
    result = run("--check", "--out", str(shelf))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "signature_refused" in result.stdout, result.stdout


def test_the_private_key_is_ignored_and_the_public_half_is_not():
    """The accidental commit of the signing half is blocked by rule, checked with
    `git check-ignore` rather than assumed; the verifier half stays tracked."""
    probe = ROOT / "first-party.private.pem"
    assert not probe.exists(), "a private key sits in the tree"
    probe.write_text("probe, not key material\n", encoding="utf-8")
    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(probe)], cwd=ROOT, capture_output=True
        )
        assert ignored.returncode == 0, "*.private.pem is not ignored by .gitignore"
    finally:
        probe.unlink()
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "plugins/first-party.pub.pem"],
        cwd=ROOT, capture_output=True,
    )
    assert tracked.returncode == 0, "the public verifier is not tracked"
    not_ignored = subprocess.run(
        ["git", "check-ignore", "-q", "plugins/first-party.pub.pem"], cwd=ROOT, capture_output=True
    )
    assert not_ignored.returncode != 0, "the public verifier is ignored by .gitignore"
