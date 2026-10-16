"""R75 — the plugin provenance chain, link by link (Plugin Platform).

Every test here pins one sentence that the product says about installing a
third-party plugin. Where the sentence was not held, the code now holds it:

1. VERIFY BEFORE WRITE — the signature is checked against the staged copy.
   A refused package never reaches a loadable path, and a refused *update*
   leaves the installed plugin on disk.
2. IDENTITY — three witnesses must agree: the marketplace listing, the
   manifest inside the artifact, and the signed record. The market path
   refuses when the listing promised a version the artifact does not carry,
   even when a trusted key signed that artifact.
3. COVERAGE — `dir_sha256` excludes the signature file NAME at any depth, so a
   second record hidden in a subdirectory would sit outside the signature.
   Such a package is refused, both to sign and to verify.
4. ZIP SLIP — the guard compares resolved paths, not string prefixes. Measured
   honestly: the old prefix test accepted a member resolving to a SIBLING of
   the staging directory, and it was `zipfile.extractall`'s own name
   sanitization that kept the bytes inside the destination. The guard is the
   documented contract, so it is fixed at the guard.
5. PERMISSIONS — declared `permissions` are a declaration. Nothing in the
   install path consults them, and this file pins that so a future
   "permissions are enforced" claim earns its place only in changed behaviour.

No network: every artifact is a zip built in the test, every key ephemeral.
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

from core import plugin_market, plugin_signing  # noqa: E402
from core.plugin_store import sha256_hex  # noqa: E402

MANIFEST = {
    "manifest_version": 1,
    "name": "my-tool",
    "version": "1.2.3",
    "description": "A bundled tool",
    "permissions": {"tool_families": ["read"], "data_roots": []},
    "components": {"skills": [], "commands": []},
}


def _zip(files: dict[str, str]) -> bytes:
    """Build an artifact locally. Keys are member paths inside the zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for member, content in files.items():
            zf.writestr(member, content)
    return buf.getvalue()


def _artifact(manifest: dict | None = None, extra: dict[str, str] | None = None) -> bytes:
    man = manifest or MANIFEST
    files = {f"{man['name']}/ephe-plugin.json": json.dumps(man)}
    for name, body in (extra or {}).items():
        files[f"{man['name']}/{name}"] = body
    return _zip(files)


def _sign_dir(tmp_path: Path, manifest: dict, private_pem: bytes, extra: dict[str, str] | None = None) -> dict:
    """Sign a directory built exactly like the artifact will unpack."""
    staged = tmp_path / "stage" / manifest["name"]
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, body in (extra or {}).items():
        (staged / name).write_text(body, encoding="utf-8")
    return plugin_signing.sign_plugin_dir(staged, private_pem)


def _entry(name: str, version: str, payload: bytes, signature: dict | None = None) -> dict:
    entry = {"name": name, "version": version, "url": "https://artifact.invalid/x.zip",
             "sha256": sha256_hex(payload)}
    if signature is not None:
        entry["signature"] = signature
    return entry


def _leftovers(plugins: Path) -> list[str]:
    """Anything the installer left behind — a missing root counts as nothing left."""
    if not plugins.is_dir():
        return []
    return [p.name for p in plugins.iterdir() if p.name.startswith(".staging-")]


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """An isolated config root; returns (config_dir, plugins_dir)."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "cfg", tmp_path / "cfg" / "plugins"


@pytest.fixture
def keypair():
    return plugin_signing.generate_keypair()


class TestVerifyBeforeWrite:

    def test_signature_is_checked_before_the_bytes_reach_a_loadable_path(self, cfg, keypair):
        """G: a signed artifact W: install T: verify runs while the final path is empty."""
        cfg_dir, plugins = cfg
        priv, pub = keypair
        payload = _artifact()
        record = _sign_dir(cfg_dir.parent, MANIFEST, priv)
        seen: dict[str, object] = {}
        real = plugin_signing.verify_plugin_dir

        def spy(plugin_dir, rec, pems):
            # Observed, and not assumed: where the check ran, and whether the
            # loadable path already held the unverified package.
            seen["checked_dir"] = Path(plugin_dir).name
            seen["checked_inside_staging"] = ".staging-my-tool" in str(plugin_dir)
            seen["final_path_existed"] = (plugins / "my-tool").exists()
            return real(plugin_dir, rec, pems)

        plugin_signing.verify_plugin_dir = spy
        try:
            status = plugin_market.install_from_marketplace(
                "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload, record)]},
                fetcher=lambda url: payload, trusted_public_keys=[pub],
            )
        finally:
            plugin_signing.verify_plugin_dir = real

        assert status["status"] == "extracted", status
        assert seen["final_path_existed"] is False
        assert seen["checked_inside_staging"] is True
        assert seen["checked_dir"] == "my-tool"

    def test_refused_signature_leaves_nothing_at_the_loadable_path(self, cfg, keypair):
        """G: a record whose hash does not match W: install T: no directory, no registry entry."""
        cfg_dir, plugins = cfg
        _, pub = keypair
        payload = _artifact()
        forged = {"alg": "ES256", "kid": "first-party", "name": "my-tool", "version": "1.2.3",
                  "sha256": "0" * 64, "signature": "not-a-real-signature"}
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload, forged)]},
            fetcher=lambda url: payload, trusted_public_keys=[pub],
        )
        assert status["status"] == "quarantined"
        assert "signature_invalid" in status["error"]
        assert not (plugins / "my-tool").exists()
        assert _leftovers(plugins) == []

    def test_refused_update_keeps_the_installed_plugin(self, cfg, keypair):
        """G: a good install W: an update with a forged signature T: the old copy survives intact."""
        cfg_dir, plugins = cfg
        priv, pub = keypair
        payload = _artifact(extra={"tool.py": "print('the version the user trusts')"})
        record = _sign_dir(cfg_dir.parent, MANIFEST, priv, extra={"tool.py": "print('the version the user trusts')"})
        first = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload, record)]},
            fetcher=lambda url: payload, trusted_public_keys=[pub],
        )
        assert first["status"] == "extracted", first
        trusted_code = (plugins / "my-tool" / "tool.py").read_text()

        bad_payload = _artifact(extra={"tool.py": "import os; os.system('rm -rf ~')"})
        bad_record = {**record, "sha256": "f" * 64}
        second = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", bad_payload, bad_record)]},
            fetcher=lambda url: bad_payload, trusted_public_keys=[pub],
        )
        assert second["status"] == "quarantined"
        assert (plugins / "my-tool" / "tool.py").read_text() == trusted_code
        assert "rm -rf" not in (plugins / "my-tool" / "tool.py").read_text()

    def test_verified_record_stays_with_the_installed_plugin(self, cfg, keypair):
        """G: a signed install T: the record is on disk for the enable-time drift gate."""
        cfg_dir, plugins = cfg
        priv, pub = keypair
        payload = _artifact()
        record = _sign_dir(cfg_dir.parent, MANIFEST, priv)
        plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload, record)]},
            fetcher=lambda url: payload, trusted_public_keys=[pub],
        )
        written = json.loads((plugins / "my-tool" / "ephe-plugin.sig.json").read_text())
        assert written["signature"] == record["signature"]
        ok, reason = plugin_signing.verify_plugin_dir(plugins / "my-tool", written, [pub])
        assert ok is True, reason


class TestIdentity:

    def test_listing_version_must_match_the_delivered_artifact(self, cfg, keypair):
        """G: listing promises 1.2.3, artifact carries 9.9.9 T: refused, nothing installed."""
        cfg_dir, plugins = cfg
        payload = _artifact(manifest={**MANIFEST, "version": "9.9.9"})
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload)]},
            fetcher=lambda url: payload, trusted_public_keys=[keypair[1]],
        )
        assert status["status"] == "identity_mismatch"
        assert "1.2.3" in status["error"] and "9.9.9" in status["error"]
        assert not (plugins / "my-tool").exists()

    def test_a_trusted_signature_does_not_excuse_a_wrong_listing_version(self, cfg, keypair):
        """G: 9.9.9 signed correctly by a trusted key T: the listing mismatch still refuses it."""
        cfg_dir, plugins = cfg
        priv, pub = keypair
        swapped = {**MANIFEST, "version": "9.9.9"}
        payload = _artifact(manifest=swapped)
        record = _sign_dir(cfg_dir.parent, swapped, priv)
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload, record)]},
            fetcher=lambda url: payload, trusted_public_keys=[pub],
        )
        assert status["status"] == "identity_mismatch"
        assert not (plugins / "my-tool").exists()

    def test_a_record_signed_for_another_plugin_is_refused(self, cfg, keypair):
        """G: manifest and record disagree on the name T: quarantined before the move."""
        cfg_dir, plugins = cfg
        priv, pub = keypair
        payload = _artifact()
        record = _sign_dir(cfg_dir.parent, MANIFEST, priv)
        other = {**record, "name": "innocent-tool"}
        # Re-sign under the wrong name: the identity fails while the crypto still verifies.
        other["signature"] = plugin_signing.sign(
            {k: other[k] for k in ("alg", "kid", "name", "version", "sha256")}, priv
        )
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload, other)]},
            fetcher=lambda url: payload, trusted_public_keys=[pub],
        )
        assert status["status"] == "quarantined"
        assert "identity mismatch" in status["error"]
        assert not (plugins / "my-tool").exists()

    def test_an_entry_that_declares_no_version_installs_what_it_points_at(self, cfg):
        """G: listing carries no version claim T: nothing to bind, install proceeds (documented limit)."""
        cfg_dir, plugins = cfg
        payload = _artifact()
        entry = {"name": "my-tool", "url": "https://artifact.invalid/x.zip", "sha256": sha256_hex(payload)}
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [entry]}, fetcher=lambda url: payload,
            trusted_public_keys=[],
        )
        assert status["status"] == "extracted", status
        assert status["version"] == "1.2.3"


class TestSignatureCoverage:

    def test_nested_signature_record_is_not_covered_and_is_refused(self, cfg, keypair):
        """G: signed package + a second record hidden in a subdirectory T: verify refuses."""
        cfg_dir, plugins = cfg
        priv, pub = keypair
        payload = _artifact()
        record = _sign_dir(cfg_dir.parent, MANIFEST, priv)
        smuggled = _artifact(extra={"skills/inner/ephe-plugin.sig.json": '{"signature":"attacker owns this"}'})
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", smuggled, record)]},
            fetcher=lambda url: smuggled, trusted_public_keys=[pub],
        )
        assert status["status"] == "quarantined", status
        assert "not covered by the hash" in status["error"]
        assert not (plugins / "my-tool").exists()

    def test_a_package_hiding_a_nested_record_cannot_be_signed(self, tmp_path, keypair):
        """G: directory with skills/inner/ephe-plugin.sig.json W: sign T: refuses, writes nothing."""
        pdir = tmp_path / "plugins" / "my-tool"
        (pdir / "skills" / "inner").mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        (pdir / "skills" / "inner" / "ephe-plugin.sig.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="nested"):
            plugin_signing.sign_plugin_dir(pdir, keypair[0])
        assert not (pdir / "ephe-plugin.sig.json").exists()

    def test_root_record_alone_still_verifies(self, tmp_path, keypair):
        """G: an ordinary signed plugin T: the exclusion of the root record is unchanged."""
        pdir = tmp_path / "plugins" / "my-tool"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        record = plugin_signing.sign_plugin_dir(pdir, keypair[0])
        ok, reason = plugin_signing.verify_plugin_dir(pdir, record, [keypair[1]])
        assert ok is True, reason


class TestZipSlip:

    def test_guard_refuses_a_sibling_sharing_the_destination_name_prefix(self, tmp_path):
        """G: member resolving to `<dest>-shadow/x` W: _safe_extract T: refused.

        The old guard tested `str(target).startswith(str(dest))`, and a sibling
        whose name merely begins with the destination's name passed it. Note
        what this does NOT claim: `zipfile.extractall` sanitizes member names on
        its own, so the unsound guard never wrote outside the destination in
        practice. The guard is the documented contract, so it is fixed here."""
        dest = tmp_path / ".staging-my-tool" / "payload"
        dest.mkdir(parents=True)
        (tmp_path / ".staging-my-tool" / "payload-shadow").mkdir()
        payload = _zip({"../payload-shadow/escaped.txt": "ESCAPED"})
        err = plugin_market._safe_extract(payload, dest)
        assert err == "unsafe_archive: path traversal member"

    def test_guard_still_refuses_an_absolute_member(self, tmp_path):
        """G: member with an absolute path W: _safe_extract T: refused."""
        dest = tmp_path / "payload"
        dest.mkdir(parents=True)
        err = plugin_market._safe_extract(_zip({"/etc/ephe-evil.txt": "nope"}), dest)
        assert err == "unsafe_archive: path traversal member"

    def test_guard_accepts_an_ordinary_archive(self, tmp_path):
        """G: well-behaved zip W: _safe_extract T: no error, files inside dest."""
        dest = tmp_path / "payload"
        dest.mkdir(parents=True)
        assert plugin_market._safe_extract(_zip({"my-tool/ephe-plugin.json": "{}"}), dest) is None
        assert (dest / "my-tool" / "ephe-plugin.json").is_file()

    def test_install_still_refuses_the_classic_escape(self, cfg):
        """G: member escaping above the staging tree W: install T: unsafe_archive, nothing installed."""
        cfg_dir, plugins = cfg
        payload = _zip({
            "my-tool/ephe-plugin.json": json.dumps(MANIFEST),
            "my-tool/../../../../escape.sh": "rm -rf /",
        })
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload)]},
            fetcher=lambda url: payload, trusted_public_keys=[],
        )
        assert status["status"] == "unsafe_archive", status
        assert not (plugins / "my-tool").exists()
        assert _leftovers(plugins) == []


class TestFlatArtifactShape:

    def test_artifact_with_the_manifest_at_its_root_installs(self, cfg):
        """G: zip without a top-level plugin directory W: install T: extracted under that name.

        The marketplace docstring always promised both shapes; the root-shape
        branch could never succeed because the staging directory name
        (`.staging-<name>`) is not a valid plugin slug."""
        cfg_dir, plugins = cfg
        payload = _zip({"ephe-plugin.json": json.dumps(MANIFEST), "tool.py": "print('flat')"})
        status = plugin_market.install_from_marketplace(
            "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload)]},
            fetcher=lambda url: payload, trusted_public_keys=[],
        )
        assert status["status"] == "extracted", status
        assert (plugins / "my-tool" / "tool.py").read_text() == "print('flat')"
        assert _leftovers(plugins) == []


class TestDeclaredPermissionsAreNotEnforced:

    def test_install_never_consults_the_declared_permission_families(self, cfg):
        """G: manifest declares shell + network + data_roots "/" W: install T: succeeds unasked.

        Pins the gap the settings surface leans on: the chips under a plugin's
        details show what the manifest DECLARES. No code in this path reads
        `permissions`, so the declaration is neither granted nor refused. If
        enforcement ever lands, this test is where the claim changes."""
        cfg_dir, plugins = cfg
        loud = {**MANIFEST, "permissions": {"tool_families": ["shell", "network", "memory"],
                                            "data_roots": ["/"]}}
        payload = _artifact(manifest=loud)
        seen: list[object] = []
        real_load = plugin_market.plugin_manifest.load_manifest

        def spy(plugin_dir):
            manifest, err = real_load(plugin_dir)
            if manifest:
                seen.append(manifest["permissions"])
            return manifest, err

        plugin_market.plugin_manifest.load_manifest = spy
        try:
            status = plugin_market.install_from_marketplace(
                "my-tool", marketplace={"plugins": [_entry("my-tool", "1.2.3", payload)]},
                fetcher=lambda url: payload, trusted_public_keys=[],
            )
        finally:
            plugin_market.plugin_manifest.load_manifest = real_load

        assert status["status"] == "extracted", status
        assert seen, "the manifest was never read — the spy is wrong, not the product"
        assert "permissions" not in status
        assert not (plugins / "my-tool" / "ephe-plugin.sig.json").exists()
