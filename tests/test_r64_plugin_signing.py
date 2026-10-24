"""R64 — Plugin signing (Extensions wave E4b).

Signature contract (ES256 over a canonical-JSON payload):

1. canonical_json: RFC 8785 subset for manifest payloads (sorted keys,
   no whitespace, UTF-8) — deterministic across runs.
2. sign/verify roundtrip with SECP256R1 (ES256); tampered payloads and
   foreign keys fail closed (verify NEVER throws).
3. sign_plugin_dir writes `ephe-plugin.sig.json` INSIDE the plugin dir; the
   signature file is EXCLUDED from dir_sha256 (hash stability).
4. verify_plugin_dir detects DRIFT: any file change after signing fails.
5. install_from_marketplace with a `signature` entry: bad signature →
   quarantined (directory removed).
6. Enable-time drift check: with the deep setting `plugins.plugin_signature_check`
   (default on) and a signature file present, a drifted plugin cannot be
   re-enabled (409); with the setting off, enable passes (kill-switch parity).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_signing  # noqa: E402
from core.plugin_store import sha256_hex  # noqa: E402

MANIFEST = {
    "manifest_version": 1,
    "name": "my-tool",
    "version": "1.2.3",
    "description": "A bundled tool",
    "permissions": {"tool_families": ["read"], "data_roots": []},
    "components": {"skills": [], "commands": []},
}


@pytest.fixture
def keypair():
    return plugin_signing.generate_keypair()


@pytest.fixture
def signed_dir(tmp_path, keypair):
    pdir = tmp_path / "plugins" / "my-tool"
    pdir.mkdir(parents=True)
    (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (pdir / "extra.txt").write_text("payload file", encoding="utf-8")
    record = plugin_signing.sign_plugin_dir(pdir, keypair[0])
    return pdir, record


class TestCanonicalJson:

    def test_sorted_keys_no_whitespace(self):
        out = plugin_signing.canonical_json({"b": 1, "a": "x"})
        assert out == b'{"a":"x","b":1}'

    def test_nested_and_unicode_stable(self):
        a = plugin_signing.canonical_json({"z": {"m": "ü", "a": [1, "two"]}, "k": None})
        b = plugin_signing.canonical_json({"k": None, "z": {"a": [1, "two"], "m": "ü"}})
        assert a == b
        assert "ü".encode("utf-8") in a


class TestSignVerify:

    def test_roundtrip(self, keypair):
        priv, pub = keypair
        payload = {"name": "my-tool", "version": "1.2.3"}
        sig = plugin_signing.sign(payload, priv)
        assert plugin_signing.verify(payload, sig, pub) is True

    def test_tampered_payload_fails(self, keypair):
        priv, pub = keypair
        sig = plugin_signing.sign({"name": "my-tool"}, priv)
        assert plugin_signing.verify({"name": "other"}, sig, pub) is False

    def test_foreign_key_fails_never_throws(self, keypair):
        priv, _ = keypair
        _, other_pub = plugin_signing.generate_keypair()
        sig = plugin_signing.sign({"name": "x"}, priv)
        assert plugin_signing.verify({"name": "x"}, sig, other_pub) is False
        assert plugin_signing.verify({"name": "x"}, "not-a-sig", other_pub) is False


class TestPluginDirSigning:

    def test_sign_writes_record_and_verifies(self, signed_dir, keypair):
        pdir, record = signed_dir
        ok, reason = plugin_signing.verify_plugin_dir(pdir, record, [keypair[1]])
        assert ok is True and reason == ""
        assert (pdir / "ephe-plugin.sig.json").is_file()

    def test_sig_file_excluded_from_dir_hash(self, tmp_path):
        from core.plugin_manifest import dir_sha256

        pdir = tmp_path / "p"
        pdir.mkdir()
        (pdir / "ephe-plugin.json").write_text("{}")
        h_before = dir_sha256(pdir)
        (pdir / "ephe-plugin.sig.json").write_text('{"signature": "whatever"}')
        h_after = dir_sha256(pdir)
        assert h_before == h_after

    def test_drift_detected(self, signed_dir, keypair):
        pdir, record = signed_dir
        (pdir / "extra.txt").write_text("TAMPERED", encoding="utf-8")
        ok, reason = plugin_signing.verify_plugin_dir(pdir, record, [keypair[1]])
        assert ok is False and "drift" in reason.lower()

    def test_identity_mismatch_detected(self, signed_dir, keypair):
        pdir, record = signed_dir
        forged = {**record, "name": "other"}
        ok, _ = plugin_signing.verify_plugin_dir(pdir, forged, [keypair[1]])
        assert ok is False


class TestMarketplaceInstallSignature:

    def test_signed_artifact_installs(self, tmp_path, monkeypatch, keypair):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        priv, pub = keypair
        import io, zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("my-tool/ephe-plugin.json", json.dumps(MANIFEST))
            zf.writestr("my-tool/extra.txt", "payload")
        payload = buf.getvalue()
        # Sign the artifact directory as it will exist on disk.
        staged = tmp_path / "stage" / "my-tool"
        staged.mkdir(parents=True)
        (staged / "ephe-plugin.json").write_text(json.dumps(MANIFEST))
        (staged / "extra.txt").write_text("payload")
        record = plugin_signing.sign_plugin_dir(staged, priv)

        from core.plugin_market import install_from_marketplace

        entry = {
            "name": "my-tool", "version": "1.2.3", "url": "https://x/y.zip",
            "sha256": sha256_hex(payload), "signature": record,
        }
        status = install_from_marketplace(
            "my-tool", marketplace={"plugins": [entry]}, fetcher=lambda url: payload,
            trusted_public_keys=[pub],
        )
        assert status["status"] == "extracted", status

    def test_forged_signature_quarantined(self, tmp_path, monkeypatch, keypair):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        _, pub = keypair
        import io, zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("my-tool/ephe-plugin.json", json.dumps(MANIFEST))
        payload = buf.getvalue()
        from core.plugin_market import install_from_marketplace

        entry = {
            "name": "my-tool", "version": "1.2.3", "url": "https://x/y.zip",
            "sha256": sha256_hex(payload),
            "signature": {"alg": "ES256", "name": "my-tool", "version": "1.2.3", "sha256": "0" * 64, "kid": "x", "signature": "bogus"},
        }
        status = install_from_marketplace(
            "my-tool", marketplace={"plugins": [entry]}, fetcher=lambda url: payload,
            trusted_public_keys=[pub],
        )
        assert status["status"] == "quarantined"


class TestEnableDriftGate:

    def _app(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        (tmp_path / "cfg" / "plugins").mkdir(parents=True, exist_ok=True)
        from server.main import create_app

        client = TestClient(create_app())
        client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        return client, tmp_path / "cfg"

    def test_drifted_plugin_cannot_reenable(self, tmp_path, monkeypatch, keypair):
        client, cfg = self._app(tmp_path, monkeypatch)
        priv, pub = keypair
        # Install a plugin dir with a valid signature record.
        pdir = cfg / "plugins" / "my-tool"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST))
        record = plugin_signing.sign_plugin_dir(pdir, priv)
        monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [pub])
        # Drift AFTER the record exists.
        (pdir / "extra.txt").write_text("payload")
        r = client.post("/api/plugins/my-tool/enable", json={"enabled": True})
        assert r.status_code == 409
        assert "drift" in r.text.lower()

    def test_deleting_the_record_does_not_bypass_the_enable_gate(
        self, tmp_path, monkeypatch, keypair
    ):
        client, cfg = self._app(tmp_path, monkeypatch)
        priv, pub = keypair
        pdir = cfg / "plugins" / "my-tool"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST))
        (pdir / "extra.txt").write_text("payload")
        plugin_signing.sign_plugin_dir(pdir, priv)
        monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [pub])
        from core import plugin_runtime

        plugin_runtime.invalidate_ownership_cache()

        first = client.post("/api/plugins/my-tool/enable", json={"enabled": True})
        assert first.status_code == 200, first.text

        (pdir / "extra.txt").write_text("TAMPERED")
        (pdir / "ephe-plugin.sig.json").unlink()
        second = client.post("/api/plugins/my-tool/enable", json={"enabled": True})
        assert second.status_code == 409
        assert "signature_record_missing" in second.text

    def test_the_lifecycle_gate_covers_the_cli_path(
        self, tmp_path, monkeypatch, keypair
    ):
        from core.plugin_lifecycle import LifecycleError, PluginLifecycle

        cfg = tmp_path / "cfg"
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
        pdir = cfg / "plugins" / "my-tool"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST))
        (pdir / "extra.txt").write_text("payload")
        priv, pub = keypair
        plugin_signing.sign_plugin_dir(pdir, priv)
        monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [pub])
        (pdir / "extra.txt").write_text("TAMPERED")

        lifecycle = PluginLifecycle(
            None,
            versions={"my-tool": "1.2.3"},
            audit_sink=lambda entry: None,
        )
        with pytest.raises(LifecycleError) as err:
            lifecycle.set_enabled("my-tool", True)
        assert err.value.code == "signature_denied"
        assert "drift" in err.value.detail

    def test_a_malformed_record_is_a_coded_refusal(
        self, tmp_path, monkeypatch, keypair
    ):
        client, cfg = self._app(tmp_path, monkeypatch)
        priv, pub = keypair
        pdir = cfg / "plugins" / "my-tool"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST))
        plugin_signing.sign_plugin_dir(pdir, priv)
        monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [pub])
        (pdir / "ephe-plugin.sig.json").write_text("{broken", encoding="utf-8")

        response = client.post("/api/plugins/my-tool/enable", json={"enabled": True})
        assert response.status_code == 409
        assert "signature_invalid" in response.text

    def test_signature_check_off_disables_gate(self, tmp_path, monkeypatch, keypair):
        client, cfg = self._app(tmp_path, monkeypatch)
        priv, pub = keypair
        pdir = cfg / "plugins" / "my-tool"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST))
        plugin_signing.sign_plugin_dir(pdir, priv)
        (pdir / "extra.txt").write_text("payload")  # drift present
        monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [pub])
        # Deep setting off → gate inactive (stock parity).
        from core import settings_schema as ss

        monkeypatch.setattr(
            ss, "load_deep_settings",
            lambda: {"plugins": {"plugins.plugin_signature_check": False}},
        )
        r = client.post("/api/plugins/my-tool/enable", json={"enabled": True})
        assert r.status_code == 200


class TestTrustClass:
    """TS-09: a key is bound to its class; a signature cannot pick its own."""

    def _pdir(self, tmp_path):
        pdir = tmp_path / "my-tool"
        pdir.mkdir()
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        return pdir

    def _bind(self, monkeypatch, first_pem, user_pem):
        monkeypatch.setattr(
            plugin_signing, "TRUSTED_KEYS_LOADER",
            lambda: [(first_pem, plugin_signing.FIRST_PARTY), (user_pem, plugin_signing.USER)],
        )

    def test_a_user_key_cannot_sign_a_first_party_artifact(self, tmp_path, monkeypatch):
        first = plugin_signing.generate_keypair()
        user = plugin_signing.generate_keypair()
        self._bind(monkeypatch, first[1], user[1])
        pdir = self._pdir(tmp_path)
        record = plugin_signing.sign_plugin_dir(pdir, user[0])
        ok, reason = plugin_signing.verify_plugin_dir(
            pdir, record, None, trust_class=plugin_signing.FIRST_PARTY
        )
        assert ok is False
        assert reason == "signature not from a trusted key"

    def test_the_matching_class_accepts(self, tmp_path, monkeypatch):
        first = plugin_signing.generate_keypair()
        user = plugin_signing.generate_keypair()
        self._bind(monkeypatch, first[1], user[1])
        pdir = self._pdir(tmp_path)
        record = plugin_signing.sign_plugin_dir(pdir, user[0])
        ok, reason = plugin_signing.verify_plugin_dir(
            pdir, record, None, trust_class=plugin_signing.USER
        )
        assert ok, reason

    def test_the_enable_gate_reads_the_pinned_class(self, tmp_path, monkeypatch):
        """The enable gate is the other verification call site: a user-key record
        must not enable a plugin whose pin says first-party."""
        first = plugin_signing.generate_keypair()
        user = plugin_signing.generate_keypair()
        self._bind(monkeypatch, first[1], user[1])
        cfg = tmp_path / "cfg"
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
        pdir = cfg / "plugins" / "my-tool"
        pdir.mkdir(parents=True)
        (pdir / "ephe-plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        record = plugin_signing.sign_plugin_dir(pdir, user[0])
        plugin_signing.record_pin("my-tool", record, trust_class=plugin_signing.FIRST_PARTY)

        ok, reason = plugin_signing.verify_enable("my-tool")

        assert ok is False
        assert reason == "signature not from a trusted key"

    def test_a_pin_without_a_class_does_not_keep_the_previous_one(
        self, tmp_path, monkeypatch
    ):
        """An explicit caller-supplied key has no class; the pin must not claim
        the class of the artifact that happened to be there before."""
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        record = {"name": "my-tool", "version": "1.0.0", "sha256": "a" * 64}
        plugin_signing.record_pin("my-tool", record, trust_class=plugin_signing.FIRST_PARTY)
        plugin_signing.record_pin("my-tool", record)

        assert "trust_class" not in plugin_signing.load_pin("my-tool")

    def test_the_enable_gate_keeps_the_directory_name_rule(self, tmp_path, monkeypatch):
        user = plugin_signing.generate_keypair()
        monkeypatch.setattr(
            plugin_signing, "TRUSTED_KEYS_LOADER",
            lambda: [(user[1], plugin_signing.USER)],
        )
        cfg = tmp_path / "cfg"
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
        source = cfg / "src" / "other"
        source.mkdir(parents=True)
        manifest = dict(MANIFEST, name="other")
        (source / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        plugin_signing.sign_plugin_dir(source, user[0])
        target = cfg / "plugins" / "my-tool"
        target.parent.mkdir(parents=True)
        source.rename(target)

        ok, reason = plugin_signing.verify_enable("my-tool")

        assert ok is False
        assert "does not match directory" in reason

    def test_a_class_without_keys_refuses_instead_of_trying_every_key(self, tmp_path, monkeypatch):
        """A named class with no key is not a wildcard. Falling back to the full
        trusted set would accept a user-signed artifact as first-party."""
        user = plugin_signing.generate_keypair()
        monkeypatch.setattr(
            plugin_signing, "TRUSTED_KEYS_LOADER",
            lambda: [(user[1], plugin_signing.USER)],
        )
        pdir = self._pdir(tmp_path)
        record = plugin_signing.sign_plugin_dir(pdir, user[0])

        assert plugin_signing.trusted_pems_for_class(plugin_signing.FIRST_PARTY) == []
        ok, reason = plugin_signing.verify_plugin_dir(
            pdir, record, None, trust_class=plugin_signing.FIRST_PARTY
        )
        assert ok is False
        assert reason == "no_trusted_key for class first-party"
