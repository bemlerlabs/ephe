"""tests/test_skill_pack_install.py — R16 skill-pack management (install/disable/delete)

Release bar: conservative guards. An installation archive is not trusted: path
traversal, absolute paths, symlinks, unknown extensions and size explosions are
rejected; built-ins are never overwritable.

Given/When/Then — TestClient against create_app(), hermetic (tmp user-skills).
"""
from __future__ import annotations

import gzip
import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

VALID_SKILL_BODY = """\
# pack-tool

**Trigger**: /packtool
**Description**: Test-Skill aus einem installierten Pack.
**Tools**:

## System Prompt

Du bist ein Test-Skill fuer die Pack-Installation.
"""


def _skill_md(name: str, version: str, trigger: str = "/packtool") -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f'version: "{version}"\n'
        f"trigger: {trigger}\n"
        'description: "Test-Skill aus einem installierten Pack."\n'
        "tools: []\n"
        "quality_profile: standard\n"
        "allowed_tools: []\n"
        "---\n"
        f"\n# {name}\n\n"
        f"**Trigger**: {trigger}\n"
        '**Description**: Test-Skill aus einem installierten Pack.\n'
        "**Tools**: \n\n"
        "## System Prompt\n\n"
        "Du bist ein Test-Skill fuer die Pack-Installation.\n"
    )


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _targz(files: dict[str, bytes]) -> bytes:
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os

    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    monkeypatch.setattr(
        "core.skills.DISABLED_SKILLS_FILE", tmp_path / "skills_state.json"
    )
    from server.main import create_app

    return TestClient(create_app())


def _install(client: TestClient, archive: bytes, filename: str = "pack.zip", force: bool = False):
    return client.post(
        "/api/skills/install",
        files={"file": (filename, archive, "application/zip")},
        data={"force": str(force).lower()},
    )


class TestInstallRoundtrip:
    def test_given_zip_pack_when_installed_then_skill_loadable_and_listed(self, client, tmp_path):
        r = _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()}))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["installed"][0]["name"] == "my-tool"
        assert body["installed"][0]["version"] == "1.0.0"
        # offline roundtrip: loaded + listed + version visible
        assert (tmp_path / "skills" / "my-tool" / "SKILL.md").exists()
        listed = client.get("/api/skills").json()["skills"]
        entry = next(s for s in listed if s["name"] == "my-tool")
        assert entry["version"] == "1.0.0" and entry["is_builtin"] is False

    def test_given_targz_pack_when_installed_then_skill_installed(self, client):
        r = _install(client, _targz({"gz-tool/SKILL.md": _skill_md("gz-tool", "1.0.0", "/gztool").encode()}),
                     filename="pack.tgz")
        assert r.status_code == 200, r.text
        assert r.json()["installed"][0]["name"] == "gz-tool"

    def test_given_flat_single_skill_md_when_installed_then_accepted(self, client):
        """An archive holding one bare SKILL.md at its root is a single-skill pack."""
        r = _install(client, _zip({"SKILL.md": _skill_md("root-tool", "1.0.0", "/roottool").encode()}))
        assert r.status_code == 200, r.text
        assert r.json()["installed"][0]["name"] == "root-tool"

    def test_given_no_skill_in_archive_when_installed_then_rejected(self, client):
        r = _install(client, _zip({"readme.txt": b"no skill here"}))
        assert r.status_code == 422

    def test_given_name_mismatch_when_installed_then_rejected(self, client):
        """The frontmatter name has to match the directory name — or installs turn to chaos."""
        r = _install(client, _zip({"wrong-dir/SKILL.md": _skill_md("other-name", "1.0.0").encode()}))
        assert r.status_code == 422


class TestInstallGuards:
    def test_given_traversal_entry_when_installed_then_rejected(self, client, tmp_path):
        archive = _zip({
            "evil/SKILL.md": _skill_md("evil", "1.0.0").encode(),
            "evil/../../../evil.txt": b"escape",
        })
        r = _install(client, archive)
        assert r.status_code == 422
        assert not (tmp_path / "skills" / "evil").exists()

    def test_given_absolute_entry_when_installed_then_rejected(self, client):
        r = _install(client, _zip({"/abs/evil.txt": b"x", "abs-tool/SKILL.md": _skill_md("abs-tool", "1.0.0").encode()}))
        assert r.status_code == 422

    def test_given_disallowed_extension_when_installed_then_rejected(self, client):
        archive = _zip({
            "sh-tool/SKILL.md": _skill_md("sh-tool", "1.0.0").encode(),
            "sh-tool/helper.sh": b"#!/bin/sh\nrm -rf /\n",
        })
        r = _install(client, archive)
        assert r.status_code == 422

    def test_given_builtin_name_when_installed_then_rejected(self, client):
        r = _install(client, _zip({"pdf-creator/SKILL.md": _skill_md("pdf-creator", "9.9.9").encode()}))
        assert r.status_code == 403
        # the real built-in is untouched
        from core.skills import BUILTIN_SKILLS_DIR
        original = (BUILTIN_SKILLS_DIR / "pdf-creator" / "SKILL.md").read_text(encoding="utf-8")
        assert "version: \"1.0.0\"" in original

    def test_given_oversized_archive_when_installed_then_rejected(self, client, monkeypatch):
        import server.routes.skills as skills_route

        monkeypatch.setattr(skills_route, "MAX_ARCHIVE_BYTES", 64)
        r = _install(client, _zip({"big-tool/SKILL.md": _skill_md("big-tool", "1.0.0").encode()}))
        assert r.status_code == 413


class TestInstallUpdateSemantics:
    def test_given_same_version_when_reinstalled_then_skipped(self, client):
        archive = _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()})
        assert _install(client, archive).status_code == 200
        r = _install(client, archive)
        assert r.status_code == 200
        assert r.json()["installed"] == []
        assert r.json()["skipped"][0]["reason"] == "already-installed"

    def test_given_older_version_when_installed_then_conflict(self, client):
        _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "2.0.0").encode()}))
        r = _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()}))
        assert r.status_code == 409

    def test_given_newer_version_when_installed_then_updated(self, client):
        _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()}))
        r = _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.1.0").encode()}))
        assert r.status_code == 200
        assert r.json()["updated"][0]["version"] == "1.1.0"

    def test_given_older_version_with_force_when_installed_then_overwritten(self, client):
        _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "2.0.0").encode()}))
        r = _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()}), force=True)
        assert r.status_code == 200
        assert r.json()["updated"][0]["version"] == "1.0.0"


class TestDeletePack:
    def test_given_installed_pack_when_deleted_then_directory_removed(self, client, tmp_path):
        _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()}))
        assert (tmp_path / "skills" / "my-tool").exists()
        r = client.delete("/api/skills/my-tool")
        assert r.status_code == 200
        assert not (tmp_path / "skills" / "my-tool").exists()


class TestDisableEnable:
    def test_given_installed_skill_when_disabled_then_not_resolved_but_listed(self, client):
        _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()}))

        r = client.post("/api/skills/my-tool/disable")
        assert r.status_code == 200 and r.json()["disabled"] is True

        # Persisted: still there after a fresh instantiation
        from core.skills import SkillLoader
        loader = SkillLoader(skills_dir=Path(os.environ["EPHE_SKILLS_DIR"]))
        assert loader.is_disabled("my-tool") is True
        # Auto-routing and trigger resolution no longer find the skill
        assert loader.resolve_trigger("/packtool") is None
        assert loader.resolve_for_message("please use packtool now") is None

        # But still listed (the UI toggle needs the entry)
        entry = next(s for s in client.get("/api/skills").json()["skills"] if s["name"] == "my-tool")
        assert entry["disabled"] is True

    def test_given_disabled_skill_when_enabled_then_resolved_again(self, client):
        _install(client, _zip({"my-tool/SKILL.md": _skill_md("my-tool", "1.0.0").encode()}))
        client.post("/api/skills/my-tool/disable")
        r = client.post("/api/skills/my-tool/enable")
        assert r.status_code == 200 and r.json()["disabled"] is False
        from core.skills import SkillLoader
        assert SkillLoader(skills_dir=Path(os.environ["EPHE_SKILLS_DIR"])).resolve_trigger("/packtool") is not None

    def test_given_unknown_skill_when_disabled_then_404(self, client):
        assert client.post("/api/skills/does-not-exist/disable").status_code == 404

    def test_given_builtin_when_disabled_then_persisted_and_respect(self, client):
        """Built-ins can be switched off (never deleted) — skill-manager basics."""
        r = client.post("/api/skills/pdf-creator/disable")
        assert r.status_code == 200
        from core.skills import SkillLoader
        loader = SkillLoader()
        assert loader.is_disabled("pdf-creator") is True
        assert loader.resolve_trigger("/pdf") is None
        assert client.post("/api/skills/pdf-creator/enable").status_code == 200


class TestUrlInstall:
    def test_given_zip_url_when_installed_then_skill_installed(self, client, monkeypatch):
        import server.routes.skills as skills_route

        archive = _zip({"url-tool/SKILL.md": _skill_md("url-tool", "1.0.0").encode()})

        class _FakeResponse:
            status_code = 200
            content = archive

            def raise_for_status(self):
                return None

        async def _fake_get(self, url, **kwargs):
            return _FakeResponse()

        monkeypatch.setattr("httpx.AsyncClient.get", _fake_get)
        # The install holds a host allowlist; this test widens it the way an operator would.
        monkeypatch.setenv("EPHE_SKILLS_INSTALL_HOSTS", "example.com")
        r = client.post("/api/skills/install/url", json={"url": "https://example.com/pack.zip"})
        assert r.status_code == 200, r.text
        assert r.json()["installed"][0]["name"] == "url-tool"

    def test_given_non_archive_url_when_installed_then_rejected(self, client, monkeypatch):
        class _FakeResponse:
            status_code = 200
            content = b"<html>kein archiv</html>"

            def raise_for_status(self):
                return None

        async def _fake_get(self, url, **kwargs):
            return _FakeResponse()

        monkeypatch.setattr("httpx.AsyncClient.get", _fake_get)
        monkeypatch.setenv("EPHE_SKILLS_INSTALL_HOSTS", "example.com")
        r = client.post("/api/skills/install/url", json={"url": "https://example.com/page.html"})
        assert r.status_code == 422

    def test_a_host_outside_the_allowlist_is_refused_before_any_request(self, client):
        r = client.post("/api/skills/install/url", json={"url": "http://169.254.169.254/pack.zip"})
        assert r.status_code == 422
        assert "not an allowed skill-pack source" in r.text


class TestPackIndex:
    """R16: curated offline pack index plus topic-pack export."""

    def test_given_index_when_listed_then_packs_annotated_and_offline(self, client):
        r = client.get("/api/skills/pack-index")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 1
        assert len(body["packs"]) == 5
        ids = {p["id"] for p in body["packs"]}
        assert {"office-pack", "dev-pack", "business-pack", "writing-pack", "research-pack"} == ids
        office = next(p for p in body["packs"] if p["id"] == "office-pack")
        assert office["complete"] is True, "THEN: alle referenzierten Built-ins existieren"
        assert all(s["installed"] for s in office["skills"])
        assert office["skills"][0]["trigger"].startswith("/")

    def test_given_unknown_pack_when_exported_then_404(self, client):
        assert client.get("/api/skills/export-pack/no-such-pack").status_code == 404

    def test_given_office_pack_when_exported_then_zip_installs_back(self, client):
        """Offline roundtrip: the export zip installs back through the install route
        (on another machine that is the actual point of the whole thing)."""
        r = client.get("/api/skills/export-pack/office-pack")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        import io
        import zipfile

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert "pdf-creator/SKILL.md" in zf.namelist()
        assert "deck-creator/SKILL.md" in zf.namelist()
        # Roundtrip over the install route — but pdf-creator is a built-in (403);
        # the export is meant for FOREIGN machines. Hence: simulate an own pack name.
        # Roundtrip with ONE entry only (the others are built-ins — the install
        # route rejects them with 403, rightly so; the export is for foreign
        # machines where the very same skills are NOT builtin).
        entries = {n: zf.read(n) for n in zf.namelist() if n.startswith("pdf-creator/")}
        renamed = {}
        for n, v in entries.items():
            renamed[n.replace("pdf-creator", "office-copy", 1)] = v.replace(b"name: pdf-creator", b"name: office-copy")
        r2 = client.post(
            "/api/skills/install",
            files={"file": ("office-copy.zip", _zip_bytes(renamed), "application/zip")},
            data={"force": "false"},
        )
        assert r2.status_code == 200, r2.text
        installed = {i["name"] for i in r2.json()["installed"]}
        assert "office-copy" in installed
        client.delete("/api/skills/office-copy")


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()
