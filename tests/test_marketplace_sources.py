"""Marketplace sources: explicit, manual, and truthful about failure.

A source is a file or an HTTPS index the user added. The bundled source is
always present. A refresh keeps the last good index and records the error; no
background request is made.
"""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import marketplace_sources, path_guard, plugin_signing  # noqa: E402


def index_doc(version: str = "1.0.0") -> dict:
    return {
        "format": 2,
        "name": "test-index",
        "owner": {"name": "Test"},
        "plugins": [
            {
                "name": "alpha",
                "displayName": "Alpha",
                "description": {"en": "Alpha"},
                "publisher": {"name": "Test"},
                "trust": "local",
                "versions": [
                    {
                        "version": version,
                        "source": {
                            "type": "zip",
                            "url": f"artifacts/alpha-{version}.zip",
                            "sha256": "a" * 64,
                        },
                        "engines": {"ephe": ">=0.1.0"},
                    }
                ],
            }
        ],
    }


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    root = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    bundled = tmp_path / "marketplace" / "index.json"
    bundled.parent.mkdir(parents=True)
    bundled.write_text(json.dumps(index_doc()), encoding="utf-8")
    monkeypatch.setenv("EPHE_MARKETPLACE_INDEX", str(bundled))
    # A local source has to sit inside the owner's home folder; the test's scratch
    # directory stands in for it.
    monkeypatch.setattr(marketplace_sources, "_home_root", lambda: tmp_path)
    return root


class TestStore:

    def test_the_bundled_source_is_always_present(self, cfg):
        data = marketplace_sources.load_sources()
        assert data["sources"][0]["kind"] == "bundled"
        assert data["sources"][0]["removable"] is False

    def test_add_local_and_remove(self, cfg, tmp_path):
        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        added = marketplace_sources.add_source("local", "My index", str(local))
        listed = marketplace_sources.load_sources()["sources"]
        assert any(source["id"] == added["id"] for source in listed)
        assert marketplace_sources.remove_source(added["id"]) is True
        assert all(source["id"] != added["id"] for source in marketplace_sources.load_sources()["sources"])

    def test_bundled_cannot_be_removed(self, cfg):
        assert marketplace_sources.remove_source("bundled") is False

    def test_http_and_credentials_are_refused(self, cfg, tmp_path):
        with pytest.raises(marketplace_sources.SourceError):
            marketplace_sources.add_source("https", "bad", "http://example.com/index.json")
        with pytest.raises(marketplace_sources.SourceError):
            marketplace_sources.add_source(
                "https", "bad", "https://user:pass@example.com/index.json"
            )

    def test_sources_file_is_owner_only(self, cfg, tmp_path):
        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        marketplace_sources.add_source("local", "Mine", str(local))
        path = marketplace_sources.sources_path()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_a_local_source_must_be_a_json_index(self, cfg, tmp_path):
        plain = tmp_path / "index.txt"
        plain.write_text("{}", encoding="utf-8")
        with pytest.raises(marketplace_sources.SourceError) as exc:
            marketplace_sources.add_source("local", "Mine", str(plain))
        assert exc.value.code == "invalid_url"

    def test_a_local_source_cannot_come_from_a_credential_folder(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr(path_guard, "DENY_ROOTS", (str(tmp_path),))
        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        with pytest.raises(marketplace_sources.SourceError) as exc:
            marketplace_sources.add_source("local", "Mine", str(local))
        assert exc.value.code == "refused_path"

    def test_a_local_source_outside_the_home_folder_is_refused(self, cfg, tmp_path):
        outside = tmp_path.parent / "elsewhere.json"
        outside.write_text(json.dumps(index_doc()), encoding="utf-8")
        with pytest.raises(marketplace_sources.SourceError) as exc:
            marketplace_sources.add_source("local", "Mine", str(outside))
        assert exc.value.code == "outside_home"

    def test_a_cache_name_cannot_leave_its_folder(self, cfg):
        with pytest.raises(marketplace_sources.SourceError):
            marketplace_sources.cache_path("../../etc/passwd")


class TestRead:

    def test_a_local_index_reads_and_caches(self, cfg, tmp_path):
        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        source = marketplace_sources.add_source("local", "Mine", str(local))

        result = marketplace_sources.read_source(source)

        assert result["status"] == "ok"
        assert result["index"]["plugins"][0]["name"] == "alpha"
        cache = marketplace_sources.cache_path(source["id"])
        assert cache.is_file()
        assert stat.S_IMODE(cache.stat().st_mode) == 0o600

    def test_the_read_seals_the_catalog_it_returned(self, cfg, tmp_path):
        import hashlib

        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        source = marketplace_sources.add_source("local", "Mine", str(local))

        result = marketplace_sources.read_source(source)

        canonical = json.dumps(
            result["index"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        assert result["digest"] == hashlib.sha256(canonical).hexdigest()

    def test_a_failed_read_carries_no_seal(self, cfg, tmp_path):
        local = tmp_path / "index.json"
        local.write_text("{broken", encoding="utf-8")
        source = marketplace_sources.add_source("local", "Mine", str(local))

        result = marketplace_sources.read_source(source)

        assert result["status"] == "error"
        assert "digest" not in result

    def test_a_broken_refresh_keeps_the_last_good_index(self, cfg, tmp_path):
        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        source = marketplace_sources.add_source("local", "Mine", str(local))
        marketplace_sources.read_source(source)
        local.write_text("{broken", encoding="utf-8")

        result = marketplace_sources.read_source(source)

        assert result["status"] == "error"
        assert result["error"]
        assert result["index"]["plugins"][0]["name"] == "alpha"
        stored = marketplace_sources.load_sources()
        assert stored["last_error"][source["id"]]

    def test_a_local_index_with_a_revocation_marks_the_version(self, cfg, tmp_path):
        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        (tmp_path / "revocations.json").write_text(
            json.dumps({"format": 1, "revoked": [{"name": "alpha", "version": "1.0.0", "reason": "x"}]}),
            encoding="utf-8",
        )
        source = marketplace_sources.add_source("local", "Mine", str(local))

        result = marketplace_sources.read_source(source)

        assert result["index"]["plugins"][0]["versions"][0]["revoked"] is True

    def test_an_unsigned_https_index_is_untrusted(self, cfg, tmp_path):
        source = marketplace_sources.add_source(
            "https", "Remote", "https://example.com/index.json"
        )
        result = marketplace_sources.read_source(
            source, fetcher=lambda _url: json.dumps(index_doc()).encode()
        )
        assert result["status"] == "error"
        assert "untrusted" in result["error"]

    def test_a_signed_https_index_verifies_with_a_trusted_key(self, cfg, tmp_path, monkeypatch):
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
        doc = index_doc()
        doc["signature"] = {
            "alg": "ES256",
            "kid": "test",
            "signature": plugin_signing.sign(doc, private_pem),
        }
        # A remote index is a user-class artifact; the class-scoped lookup is
        # what read_source asks, so the seam is the key loader with its class.
        monkeypatch.setattr(
            plugin_signing,
            "TRUSTED_KEYS_LOADER",
            lambda: [(public_pem, plugin_signing.USER)],
        )
        source = marketplace_sources.add_source(
            "https", "Remote", "https://example.com/index.json"
        )
        result = marketplace_sources.read_source(
            source, fetcher=lambda _url: json.dumps(doc).encode()
        )
        assert result["status"] == "ok", result

    def test_a_download_over_the_cap_is_refused(self, cfg, monkeypatch):
        source = marketplace_sources.add_source(
            "https", "Remote", "https://example.com/index.json"
        )
        monkeypatch.setattr(marketplace_sources, "MAX_INDEX_BYTES", 16)
        result = marketplace_sources.read_source(
            source, fetcher=lambda _url: b"x" * 100
        )
        assert result["status"] == "error"
        assert "too_large" in result["error"]

    def test_the_bundled_index_carries_the_listing_translations(self, cfg, tmp_path, monkeypatch):
        metadata = tmp_path / "metadata.json"
        metadata.write_text(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": "alpha",
                            "description_i18n": {"en": "Alpha", "de": "Alpha DE"},
                        }
                    ]
                }
            )
        )
        monkeypatch.setenv("EPHE_MARKETPLACE_METADATA", str(metadata))
        result = marketplace_sources.read_source(marketplace_sources.bundled_source())
        assert result["status"] == "ok", result
        plugin = next(item for item in result["index"]["plugins"] if item["name"] == "alpha")
        assert plugin["description"].get("de") == "Alpha DE"

    def test_refresh_reads_every_source(self, cfg, tmp_path):
        local = tmp_path / "index.json"
        local.write_text(json.dumps(index_doc()), encoding="utf-8")
        marketplace_sources.add_source("local", "Mine", str(local))
        results = marketplace_sources.refresh_all()
        assert results[0]["source"]["id"] == "bundled"
        assert any(item["source"]["title"] == "Mine" for item in results)

    def test_a_source_failure_is_a_code_and_names_no_path(self, cfg, tmp_path):
        bundled = tmp_path / "marketplace" / "index.json"
        bundled.unlink()
        result = marketplace_sources.read_source(marketplace_sources.bundled_source())
        assert result["status"] == "error"
        assert result["error"] == "not_found"
        assert str(tmp_path) not in result["error"]
