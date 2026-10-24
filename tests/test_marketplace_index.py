"""Marketplace index v2: schema, resolution, compatibility and revocation.

The index is the document a user reads before an install. It is validated as a
whole and resolved to one immutable version; a malformed or mutable entry never
reaches the installer.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import marketplace_index, plugin_signing  # noqa: E402


def version(number: str, *, engine: str = ">=0.1.0", signed: bool = False) -> dict:
    data = {
        "version": number,
        "publishTimestamp": 1790000000,
        "source": {
            "type": "zip",
            "url": f"artifacts/alpha-{number}.zip",
            "sha256": "a" * 64,
        },
        "engines": {"ephe": engine},
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": ["skills"],
    }
    if signed:
        data["source"]["signature"] = {
            "alg": "ES256",
            "kid": "test",
            "signature": "AAAA",
        }
    return data


def index(*versions: dict, trust: str = "local") -> dict:
    return {
        "format": 2,
        "name": "test-index",
        "owner": {"name": "Test"},
        "metadata": {"categories": {"code": {"title": {"en": "Code"}}}},
        "plugins": [
            {
                "name": "alpha",
                "displayName": "Alpha",
                "description": {"en": "Alpha plugin"},
                "publisher": {"name": "Test", "verified": True},
                "trust": trust,
                "categories": ["code"],
                "versions": list(versions) or [version("1.0.0")],
            }
        ],
    }


class TestValidation:

    def test_a_valid_index_normalizes(self):
        parsed = marketplace_index.validate_index(index(version("1.0.0")))
        assert parsed["plugins"][0]["versions"][0]["version"] == "1.0.0"

    def test_wrong_format_is_refused_with_a_path(self):
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.validate_index({"format": 1, "plugins": []})
        assert exc.value.code == "format"
        assert exc.value.path == "format"

    def test_a_latest_url_is_mutable_and_refused(self):
        bad = index(version("1.0.0"))
        bad["plugins"][0]["versions"][0]["source"]["url"] = "https://x/latest.zip"
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.validate_index(bad)
        assert exc.value.code == "mutable_url"

    def test_a_missing_hash_is_refused(self):
        bad = index(version("1.0.0"))
        bad["plugins"][0]["versions"][0]["source"]["sha256"] = ""
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.validate_index(bad)
        assert exc.value.code == "missing_hash"

    def test_duplicate_versions_are_refused(self):
        bad = index(version("1.0.0"), version("1.0.0"))
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.validate_index(bad)
        assert exc.value.code == "duplicate_version"

    def test_a_non_semver_version_is_refused(self):
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.validate_index(index(version("1.0")))
        assert exc.value.code == "bad_version"

    def test_a_remote_official_entry_needs_a_signature(self):
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.validate_index(
                index(version("1.0.0"), trust="official"), source_kind="remote"
            )
        assert exc.value.code == "signature_required"


class TestCompatibility:

    @pytest.mark.parametrize(
        "spec,version,expected",
        [
            ("*", "0.1.3", True),
            (">=0.1.0", "0.1.3", True),
            (">=0.2.0", "0.1.3", False),
            (">0.1.3", "0.1.3", False),
            ("<=0.2.0", "0.1.3", True),
            ("<0.1.0", "0.1.3", False),
            ("^0.1.0", "0.1.9", True),
            ("^0.1.0", "0.2.0", False),
            ("~0.1.0", "0.1.9", True),
            ("~0.1.0", "0.2.0", False),
            (">=0.1.0 <1.0.0", "0.9.0", True),
            (">=0.1.0 <1.0.0", "1.0.0", False),
            ("0.1.3", "0.1.3", True),
            ("nonsense", "0.1.3", False),
        ],
    )
    def test_ranges(self, spec, version, expected):
        assert marketplace_index.compatible(spec, version) is expected

    def test_highest_compatible_version_wins(self):
        parsed = marketplace_index.validate_index(
            index(
                version("1.0.0"),
                version("2.0.0"),
                version("3.0.0", engine=">=9.0.0"),
            )
        )
        found = marketplace_index.resolve_version(parsed, "alpha", ephe_version="0.1.3")
        assert found["version"] == "2.0.0"

    def test_exact_version_is_returned(self):
        parsed = marketplace_index.validate_index(index(version("1.0.0"), version("2.0.0")))
        found = marketplace_index.resolve_version(
            parsed, "alpha", version="1.0.0", ephe_version="0.1.3"
        )
        assert found["version"] == "1.0.0"

    def test_an_incompatible_exact_version_is_refused(self):
        parsed = marketplace_index.validate_index(
            index(version("2.0.0", engine=">=9.0.0"))
        )
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.resolve_version(
                parsed, "alpha", version="2.0.0", ephe_version="0.1.3"
            )
        assert exc.value.code == "incompatible"


class TestRevocations:

    def test_revocation_wins_over_an_old_index(self):
        parsed = marketplace_index.validate_index(index(version("1.0.0"), version("2.0.0")))
        revoked = [{"name": "alpha", "version": "2.0.0", "reason": "security"}]
        marketplace_index.apply_revocations(parsed, revoked)
        found = marketplace_index.resolve_version(parsed, "alpha", ephe_version="0.1.3")
        assert found["version"] == "1.0.0"
        assert marketplace_index.is_revoked("alpha", "2.0.0", revoked)

    def test_all_versions_revoked_yields_no_candidate(self):
        parsed = marketplace_index.validate_index(index(version("1.0.0")))
        marketplace_index.apply_revocations(
            parsed, [{"name": "alpha", "version": "1.0.0", "reason": "security"}]
        )
        with pytest.raises(marketplace_index.IndexError) as exc:
            marketplace_index.resolve_version(parsed, "alpha", ephe_version="0.1.3")
        assert exc.value.code == "revoked"


class TestIndexSignature:

    def _keypair(self):
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
        return private_pem, public_pem

    def test_a_signed_index_verifies_and_a_tampered_one_fails(self):
        private, public = self._keypair()
        raw = index(version("1.0.0"))
        body = copy.deepcopy(raw)
        signature = plugin_signing.sign(body, private)
        raw["signature"] = {"alg": "ES256", "kid": "test", "signature": signature}
        ok, reason = marketplace_index.verify_index_signature(raw, [public])
        assert ok, reason

        raw["plugins"][0]["versions"][0]["source"]["sha256"] = "b" * 64
        ok, reason = marketplace_index.verify_index_signature(raw, [public])
        assert not ok and reason
