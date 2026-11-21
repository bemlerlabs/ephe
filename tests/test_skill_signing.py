"""W3-14 — Signed skill packs.

The plugin trust machinery (core/plugin_signing.py: RFC 8785 canonical JSON +
ES256) applied to a skill pack, plus the verify path.

Contract:
1. The module REUSES the plugin machinery object-for-object — same
   canonical_json / sign / verify, not a parallel copy.
2. `ephe-skill.sig.json` binds the pack identity (SKILL.md name + version) to
   the pack hash; the record itself AND the install-time provenance note
   (`.ephe-install.json`) are excluded from that hash (hash stability).
3. Drift after signing, an identity mismatch, a foreign key and a stray nested
   record all fail closed; verify NEVER throws.
4. The load path (SkillLoader.signature_status) and the route
   GET /api/skills/{name}/verify report the state without raising.
5. Install fail-closed: a pack that ships a signature record must verify
   against the trusted keys or the install is rejected (422) and nothing is
   written; unsigned packs are unaffected.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_signing, skill_signing  # noqa: E402
from core.skill_provenance import RECORD_FILE  # noqa: E402
from core.skills import SkillLoader  # noqa: E402


def _skill_md(name: str, version: str = "1.0.0", trigger: str = "/packtool") -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f'version: "{version}"\n'
        f"trigger: {trigger}\n"
        'description: "Test pack for skill signing."\n'
        "tools: []\n"
        "---\n"
        f"\n# {name}\n\n"
        f"**Trigger**: {trigger}\n"
        '**Description**: Test pack for skill signing.\n'
        "**Tools**: \n\n"
        "## System Prompt\n\n"
        "Du bist ein Test-Skill.\n"
    )


def _make_pack(base: Path, name: str, version: str = "1.0.0") -> Path:
    pack = base / name
    (pack / "references").mkdir(parents=True)
    (pack / "SKILL.md").write_text(_skill_md(name, version), encoding="utf-8")
    (pack / "references" / "notes.md").write_text("sidecar\n", encoding="utf-8")
    return pack


def _zip_tree(pack: Path) -> bytes:
    """Zip a pack directory as `<pack>/...` — the archive layout install expects."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(pack.rglob("*")):
            if f.is_file():
                zf.writestr(f"{pack.name}/{f.relative_to(pack).as_posix()}", f.read_bytes())
    return buf.getvalue()


@pytest.fixture
def keypair():
    return plugin_signing.generate_keypair()


@pytest.fixture
def trust(monkeypatch, keypair):
    """Point the shared trust-anchor seam at this test's public key."""
    monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [keypair[1]])
    return keypair


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setattr("core.skills.DISABLED_SKILLS_FILE", tmp_path / "skills_state.json")
    from server.main import create_app

    return TestClient(create_app())


def _install(client: TestClient, archive: bytes, filename: str = "pack.zip", force: bool = False):
    return client.post(
        "/api/skills/install",
        files={"file": (filename, archive, "application/zip")},
        data={"force": str(force).lower()},
    )


class TestMachineryReuse:
    def test_same_objects_as_the_plugin_layer(self):
        """Skill signing reuses the plugin layer's own function objects."""
        assert skill_signing.canonical_json is plugin_signing.canonical_json
        assert skill_signing.sign is plugin_signing.sign
        assert skill_signing.verify is plugin_signing.verify


class TestPackHash:
    def test_stable_and_content_addressed(self, tmp_path):
        pack = _make_pack(tmp_path, "h-tool")
        first = skill_signing.pack_sha256(pack)
        assert skill_signing.pack_sha256(pack) == first
        (pack / "SKILL.md").write_text(_skill_md("h-tool", "1.0.1"), encoding="utf-8")
        assert skill_signing.pack_sha256(pack) != first

    def test_signature_file_excluded_from_pack_hash(self, tmp_path):
        pack = _make_pack(tmp_path, "s-tool")
        before = skill_signing.pack_sha256(pack)
        (pack / skill_signing.SIG_FILENAME).write_text('{"signature": "whatever"}', encoding="utf-8")
        assert skill_signing.pack_sha256(pack) == before

    def test_provenance_note_excluded_from_pack_hash(self, tmp_path):
        pack = _make_pack(tmp_path, "p-tool")
        before = skill_signing.pack_sha256(pack)
        (pack / RECORD_FILE).write_text('{"schema": 1, "installed_at": "now"}', encoding="utf-8")
        assert skill_signing.pack_sha256(pack) == before


class TestSignVerify:
    def test_sign_writes_record_and_verifies(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool", "1.2.3")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        assert (pack / skill_signing.SIG_FILENAME).is_file()
        assert record["name"] == "my-tool" and record["version"] == "1.2.3"
        assert record["alg"] == "ES256"
        ok, reason = skill_signing.verify_skill_pack(pack, record, [keypair[1]])
        assert ok is True and reason == ""

    def test_roundtrip_after_provenance_note_written(self, tmp_path, keypair):
        """The note is written AFTER install; it must not invalidate the signature."""
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        (pack / RECORD_FILE).write_text('{"schema": 1, "content_hash": "sha256:x"}', encoding="utf-8")
        ok, reason = skill_signing.verify_skill_pack(pack, record, [keypair[1]])
        assert ok is True, reason

    def test_drift_detected(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        (pack / "references" / "notes.md").write_text("TAMPERED\n", encoding="utf-8")
        ok, reason = skill_signing.verify_skill_pack(pack, record, [keypair[1]])
        assert ok is False and "drift" in reason.lower()

    def test_identity_mismatch_detected(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        forged = {**record, "version": "9.9.9"}
        ok, _ = skill_signing.verify_skill_pack(pack, forged, [keypair[1]])
        assert ok is False

    def test_foreign_key_fails(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        _, other_pub = plugin_signing.generate_keypair()
        ok, reason = skill_signing.verify_skill_pack(pack, record, [other_pub])
        assert ok is False and "trusted key" in reason.lower()

    def test_no_trusted_key(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        ok, reason = skill_signing.verify_skill_pack(pack, record, [])
        assert ok is False and reason == "no_trusted_key"

    def test_unsupported_algorithm(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        ok, reason = skill_signing.verify_skill_pack(pack, {**record, "alg": "RS256"}, [keypair[1]])
        assert ok is False and reason == "unsupported algorithm"

    def test_stray_nested_record_refused(self, tmp_path, keypair):
        """A record the hash does not cover (nested) makes the pack untrusted."""
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        (pack / "references" / skill_signing.SIG_FILENAME).write_text(json.dumps(record), encoding="utf-8")
        ok, reason = skill_signing.verify_skill_pack(pack, record, [keypair[1]])
        assert ok is False and "stray" in reason.lower()

    def test_sign_refuses_nested_record(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        (pack / "references" / skill_signing.SIG_FILENAME).write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="nested"):
            skill_signing.sign_skill_pack(pack, keypair[0])

    def test_verify_never_throws(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        for bad in ({}, {"signature": "not-base64"}, {"signature": "AAAA", "alg": "ES256"}):
            ok, reason = skill_signing.verify_skill_pack(pack, bad, [keypair[1]])
            assert ok is False and isinstance(reason, str)

    def test_tampered_signature_string_fails(self, tmp_path, keypair):
        pack = _make_pack(tmp_path, "my-tool")
        record = skill_signing.sign_skill_pack(pack, keypair[0])
        flipped = "A" if record["signature"][0] != "A" else "B"
        ok, _ = skill_signing.verify_skill_pack(pack, {**record, "signature": flipped + record["signature"][1:]}, [keypair[1]])
        assert ok is False

    def test_verify_installed_unsigned(self, tmp_path):
        pack = _make_pack(tmp_path, "my-tool")
        ok, reason = skill_signing.verify_installed(pack, [])
        assert ok is False and reason == "no signature record"


class TestLoadPathStatus:
    def test_signed_pack_reports_verified(self, tmp_path, trust):
        packs = tmp_path / "skills"
        pack = _make_pack(packs, "signed-tool")
        skill_signing.sign_skill_pack(pack, trust[0])
        status = SkillLoader(skills_dir=packs).signature_status("signed-tool")
        assert status["signed"] is True and status["verified"] is True

    def test_unsigned_pack_reports_unsigned(self, tmp_path):
        packs = tmp_path / "skills"
        _make_pack(packs, "plain-tool")
        status = SkillLoader(skills_dir=packs).signature_status("plain-tool")
        assert status["signed"] is False and status["verified"] is None

    def test_flat_skill_is_not_a_pack(self, tmp_path):
        packs = tmp_path / "skills"
        packs.mkdir(parents=True)
        (packs / "flat-tool.md").write_text(_skill_md("flat-tool"), encoding="utf-8")
        status = SkillLoader(skills_dir=packs).signature_status("flat-tool")
        assert status["signed"] is False and "not a pack" in str(status["reason"])

    def test_drift_reported_on_load_path(self, tmp_path, trust):
        packs = tmp_path / "skills"
        pack = _make_pack(packs, "drift-tool")
        skill_signing.sign_skill_pack(pack, trust[0])
        # Content change that leaves the identity (name + version) intact.
        (pack / "references" / "notes.md").write_text("TAMPERED\n", encoding="utf-8")
        status = SkillLoader(skills_dir=packs).signature_status("drift-tool")
        assert status["signed"] is True and status["verified"] is False
        assert "drift" in str(status["reason"]).lower()


class TestInstallGate:
    def test_signed_pack_installs_and_verifies(self, client, tmp_path, trust):
        pack = _make_pack(tmp_path / "src", "my-tool", "1.0.0")
        skill_signing.sign_skill_pack(pack, trust[0])
        r = _install(client, _zip_tree(pack))
        assert r.status_code == 200, r.text
        assert r.json()["installed"][0]["name"] == "my-tool"
        # The provenance note written at install must not break the signature,
        # and the load path must still report a verified pack.
        v = client.get("/api/skills/my-tool/verify").json()
        assert v["signed"] is True and v["verified"] is True, v
        listed = next(s for s in client.get("/api/skills").json()["skills"] if s["name"] == "my-tool")
        assert listed["signature"] and listed["signature"]["verified"] is True

    def test_forged_signature_rejected_and_nothing_written(self, client, tmp_path, trust, monkeypatch):
        pack = _make_pack(tmp_path / "src", "victim", "1.0.0")
        skill_signing.sign_skill_pack(pack, trust[0])
        # A different trust anchor — the record is genuine but not ours.
        _, other_pub = plugin_signing.generate_keypair()
        monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [other_pub])
        r = _install(client, _zip_tree(pack))
        assert r.status_code == 422, r.text
        assert not (tmp_path / "skills" / "victim").exists()

    def test_unsigned_pack_still_installs(self, client, tmp_path):
        pack = _make_pack(tmp_path / "src", "plain-tool", "1.0.0")
        r = _install(client, _zip_tree(pack))
        assert r.status_code == 200, r.text
        assert client.get("/api/skills/plain-tool/verify").json()["signed"] is False


class TestVerifyRoute:
    def test_404_for_unknown_skill(self, client):
        assert client.get("/api/skills/does-not-exist/verify").status_code == 404

    def test_reports_drift(self, client, tmp_path, trust):
        pack = _make_pack(tmp_path / "src", "drift-tool", "1.0.0")
        skill_signing.sign_skill_pack(pack, trust[0])
        assert _install(client, _zip_tree(pack)).status_code == 200
        installed = tmp_path / "skills" / "drift-tool" / "references" / "notes.md"
        installed.write_text("TAMPERED\n", encoding="utf-8")
        v = client.get("/api/skills/drift-tool/verify").json()
        assert v["signed"] is True and v["verified"] is False and "drift" in v["reason"].lower()
