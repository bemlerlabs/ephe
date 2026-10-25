"""tests/test_artifacts_route.py — R17 Artifact Hub API + chat ingest.

Given/When/Then. The store DB and the allowed roots are set hermetically per
test; the ingest test drives the REAL /api/chat/stream with a mocked fast path
and checks that the artifact lands in the library.
"""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core import artifact_store
from core import artifact_workbench as workbench


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    monkeypatch.setattr(artifact_store, "ARTIFACTS_DB", tmp_path / "artifacts.db")
    from server.main import create_app

    return TestClient(create_app())


def _file(tmp_path, name, content=b"pdf-bytes"):
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


class TestListAndSearch:
    def test_given_registered_artifacts_when_listed_then_shape_and_filter(self, client, tmp_path):
        a = artifact_store.register_artifact(path=_file(tmp_path, "brief.pdf"), kind="pdf", session_id="s1", topic="Board Brief")
        artifact_store.register_artifact(path=_file(tmp_path, "pic.png"), kind="png", session_id="s2")

        r = client.get("/api/artifacts")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert {a["name"] for a in body["artifacts"]} == {"brief.pdf", "pic.png"}

        assert client.get("/api/artifacts", params={"q": "board"}).json()["total"] == 1
        assert client.get("/api/artifacts", params={"kind": "png"}).json()["total"] == 1
        assert client.get("/api/artifacts", params={"session_id": "s1"}).json()["total"] == 1

        assert a is not None  # the registration worked

    def test_given_unknown_filter_when_listed_then_empty_not_error(self, client):
        assert client.get("/api/artifacts", params={"q": "does-not-exist"}).json()["artifacts"] == []


class TestFavoriteTagsVersions:
    def test_given_favorite_toggle_when_flipped_then_persists(self, client, tmp_path):
        a = artifact_store.register_artifact(path=_file(tmp_path, "f.pdf"), kind="pdf", session_id="s1")
        r = client.post(f"/api/artifacts/{a['id']}/favorite", json={"favorite": True})
        assert r.status_code == 200 and r.json()["favorite"] is True
        listed = client.get("/api/artifacts", params={"favorite": True}).json()
        assert listed["total"] == 1

    def test_given_tags_when_put_then_normalized_list(self, client, tmp_path):
        a = artifact_store.register_artifact(path=_file(tmp_path, "t.pdf"), kind="pdf", session_id="s1")
        r = client.put(f"/api/artifacts/{a['id']}/tags", json={"tags": ["board", " q3 ", "board"]})
        assert r.status_code == 200
        assert r.json()["tags"] == ["board", "q3"]

    def test_given_version_line_when_queried_then_history_oldest_first(self, client, tmp_path):
        import pathlib

        gen = tmp_path / "gen"
        gen.mkdir()
        report = gen / "report.pdf"
        report.write_bytes(b"v1")
        first = artifact_store.register_artifact(path=str(report), kind="pdf", session_id="s1")
        report.write_bytes(b"v2")
        second = artifact_store.register_artifact(path=str(report), kind="pdf", session_id="s1")

        r = client.get(f"/api/artifacts/{first['id']}/versions")
        assert r.status_code == 200
        versions = r.json()["versions"]
        assert [v["version"] for v in versions] == [1, 2]
        assert versions[-1]["id"] == second["id"]

    def test_given_unknown_id_when_queried_then_404(self, client):
        assert client.get("/api/artifacts/unknown-id/versions").status_code == 404


class TestDelete:
    def test_given_delete_when_flag_set_and_inside_roots_then_file_removed(self, client, tmp_path, monkeypatch):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        path = _file(tmp_path, "gone.pdf")
        a = artifact_store.register_artifact(path=path, kind="pdf", session_id="s1")
        r = client.request("DELETE", f"/api/artifacts/{a['id']}", params={"delete_file": True})
        assert r.status_code == 200
        assert r.json()["file_removed"] is True
        import pathlib

        assert not pathlib.Path(path).exists()

    def test_given_delete_when_file_outside_roots_then_entry_only(self, client, tmp_path, monkeypatch):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path / "elsewhere"])
        path = _file(tmp_path, "safe.pdf")
        a = artifact_store.register_artifact(path=path, kind="pdf", session_id="s1")
        r = client.request("DELETE", f"/api/artifacts/{a['id']}", params={"delete_file": True})
        assert r.json()["file_removed"] is False
        import pathlib

        assert pathlib.Path(path).exists()


class TestExport:
    def test_given_two_artifacts_when_exported_then_zip_contains_both(self, client, tmp_path):
        artifact_store.register_artifact(path=_file(tmp_path, "a.pdf", b"AAA"), kind="pdf", session_id="s1")
        artifact_store.register_artifact(path=_file(tmp_path, "b.png", b"BBB"), kind="png", session_id="s1")
        r = client.get("/api/artifacts/export")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert set(zf.namelist()) == {"a.pdf", "b.png"}
        assert zf.read("a.pdf") == b"AAA"

    def test_given_duplicate_names_when_exported_then_names_deduped(self, client, tmp_path):
        d1, d2 = tmp_path / "1", tmp_path / "2"
        d1.mkdir()
        d2.mkdir()
        (d1 / "same.pdf").write_bytes(b"1")
        (d2 / "same.pdf").write_bytes(b"2")
        artifact_store.register_artifact(path=str(d1 / "same.pdf"), kind="pdf", session_id="s1")
        artifact_store.register_artifact(path=str(d2 / "same.pdf"), kind="pdf", session_id="s2")
        r = client.get("/api/artifacts/export")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert len(zf.namelist()) == 2 and len(set(zf.namelist())) == 2

    def test_given_no_artifacts_when_exported_then_404(self, client):
        assert client.get("/api/artifacts/export").status_code == 404

    def test_given_id_selection_when_exported_then_only_selected(self, client, tmp_path):
        a = artifact_store.register_artifact(path=_file(tmp_path, "x.pdf", b"X"), kind="pdf", session_id="s1")
        artifact_store.register_artifact(path=_file(tmp_path, "y.pdf", b"Y"), kind="pdf", session_id="s1")
        r = client.get("/api/artifacts/export", params={"ids": a["id"]})
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert zf.namelist() == ["x.pdf"]


class TestFileByIdentity:
    """A0: a card asks by its id, not by a path."""

    def _register(self, tmp_path, monkeypatch, content=b"pdf-bytes", name="brief.pdf"):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        row = artifact_store.register_artifact(path=_file(tmp_path, name, content), kind="pdf", session_id="s1")
        return row

    def test_given_artifact_when_fetched_by_id_then_bytes_arrive_inline(self, client, tmp_path, monkeypatch):
        row = self._register(tmp_path, monkeypatch)
        r = client.get(f"/api/artifacts/{row['id']}/file")
        assert r.status_code == 200
        assert r.content == b"pdf-bytes"
        assert r.headers["content-type"] == "application/pdf"
        assert "inline" in r.headers["content-disposition"]
        assert "brief.pdf" in r.headers["content-disposition"]
        assert artifact_store.get_artifact(row["id"])["viewed_at"], "a view is recorded only here"

    def test_given_download_flag_when_fetched_then_attachment_and_no_view_record(self, client, tmp_path, monkeypatch):
        row = self._register(tmp_path, monkeypatch)
        r = client.get(f"/api/artifacts/{row['id']}/file", params={"download": True})
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        assert artifact_store.get_artifact(row["id"])["viewed_at"] is None

    def test_given_name_with_quotes_when_served_then_header_is_not_injectable(self, client, tmp_path, monkeypatch):
        row = self._register(tmp_path, monkeypatch, name='a"; x=1.pdf')
        r = client.get(f"/api/artifacts/{row['id']}/file")
        assert "\n" not in r.headers["content-disposition"]
        assert 'x=1' not in r.headers["content-disposition"].split("filename*=")[0]

    def test_given_missing_bytes_when_fetched_then_404_not_a_wrong_file(self, client, tmp_path, monkeypatch):
        import pathlib

        row = self._register(tmp_path, monkeypatch)
        pathlib.Path(row["path"]).unlink()
        assert client.get(f"/api/artifacts/{row['id']}/file").status_code == 404

    def test_given_path_outside_roots_when_fetched_then_404(self, client, tmp_path, monkeypatch):
        row = self._register(tmp_path, monkeypatch)
        monkeypatch.setattr("core.tools.base._get_allowed_roots", lambda: [tmp_path / "leer"])
        assert client.get(f"/api/artifacts/{row['id']}/file").status_code == 404

    def test_given_unknown_id_when_fetched_then_404(self, client):
        assert client.get("/api/artifacts/unknown-id/file").status_code == 404


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class TestArtifactBytesGuard:
    def _row(self, tmp_path, monkeypatch, name, content=PNG_BYTES, kind="png"):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        return artifact_store.register_artifact(
            path=_file(tmp_path, name, content), kind=kind, session_id="s1"
        )

    def test_an_artifact_under_the_artifact_root_is_served(self, client, tmp_path, monkeypatch):
        from core import path_guard

        root = tmp_path / "cfg"
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
        monkeypatch.setattr(path_guard, "DENY_ROOTS", (str(root),))
        target = root / "artifacts" / "s1" / "pic.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(PNG_BYTES)
        row = artifact_store.register_artifact(
            path=str(target), kind="png", session_id="s1"
        )
        r = client.get(f"/api/artifacts/{row['id']}/file")
        assert r.status_code == 200
        assert r.content == PNG_BYTES
        assert r.headers["content-type"] == "image/png"

    def test_a_registered_secret_under_a_deny_root_is_refused(self, client, tmp_path, monkeypatch):
        from core import path_guard

        private = tmp_path / "private"
        private.mkdir()
        monkeypatch.setattr(path_guard, "DENY_ROOTS", (str(private),))
        row = self._row(tmp_path / "private", monkeypatch, "engine.json", b"{}")
        r = client.get(f"/api/artifacts/{row['id']}/file")
        assert r.status_code == 403

    def test_a_credential_shaped_name_is_refused_wherever_it_sits(self, client, tmp_path, monkeypatch):
        row = self._row(tmp_path, monkeypatch, "id_rsa", b"key")
        assert client.get(f"/api/artifacts/{row['id']}/file").status_code == 403

    def test_an_unknown_type_travels_as_a_download(self, client, tmp_path, monkeypatch):
        row = self._row(tmp_path, monkeypatch, "payload.bin", b"\x00\x01", kind="file")
        r = client.get(f"/api/artifacts/{row['id']}/file")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert "attachment" in r.headers["content-disposition"]

    def test_a_range_request_answers_206_for_video_and_pdf(self, client, tmp_path, monkeypatch):
        row = self._row(tmp_path, monkeypatch, "clip.mp4", b"0123456789", kind="video")
        r = client.get(
            f"/api/artifacts/{row['id']}/file", headers={"Range": "bytes=0-3"}
        )
        assert r.status_code == 206
        assert r.content == b"0123"
        assert r.headers["content-range"].startswith("bytes 0-3/")


class TestRemoteImageProxy:
    def test_a_non_https_url_is_refused(self, client):
        r = client.get("/api/artifacts/proxy", params={"url": "http://example.test/a.png"})
        assert r.status_code == 400

    def test_a_private_target_is_refused_by_the_guard(self, client):
        r = client.get(
            "/api/artifacts/proxy", params={"url": "https://localhost/a.png"}
        )
        assert r.status_code == 502

    def test_a_remote_png_is_stored_once_and_served_same_origin(
        self, client, tmp_path, monkeypatch
    ):
        import core.guarded_fetch as guarded

        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        calls = {"n": 0}

        def _fetch(url, **kwargs):
            calls["n"] += 1
            return PNG_BYTES

        monkeypatch.setattr(guarded, "fetch_https", _fetch)
        url = "https://images.example.test/cat.png"
        first = client.get("/api/artifacts/proxy", params={"url": url})
        assert first.status_code == 200
        assert first.headers["content-type"] == "image/png"
        cached = list((tmp_path / "cfg" / "artifacts" / "remote").glob("*.png"))
        assert len(cached) == 1
        second = client.get("/api/artifacts/proxy", params={"url": url})
        assert second.status_code == 200
        assert calls["n"] == 1

    def test_bytes_that_are_not_an_image_are_refused(self, client, tmp_path, monkeypatch):
        import core.guarded_fetch as guarded

        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setattr(guarded, "fetch_https", lambda url, **kw: b"<html>no</html>")
        r = client.get(
            "/api/artifacts/proxy", params={"url": "https://images.example.test/a.png"}
        )
        assert r.status_code == 415


class TestExpiryQuestion:
    """The deadline asks a question. It does not answer itself."""

    def _due(self, tmp_path, monkeypatch, n=2):
        import core.tools.base as base
        from datetime import datetime, timedelta, timezone

        root = tmp_path / "ephe-home"
        (root / "artifacts" / "s1").mkdir(parents=True)
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        ids = []
        for i in range(n):
            p = root / "artifacts" / "s1" / f"alt-{i}.pdf"
            p.write_bytes(b"x" * (100 + i))
            row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
            artifact_store._write(
                "UPDATE artifacts SET expires_at = ? WHERE id = ?",
                ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds"), row["id"]),
            )
            ids.append(row["id"])
        return ids

    def test_given_nothing_due_when_asked_then_zero_and_no_bytes(self, client):
        r = client.get("/api/artifacts/expiry")
        assert r.status_code == 200
        assert r.json() == {"due": [], "count": 0, "bytes": 0, "days": 30}

    def test_given_due_copies_when_listed_then_count_and_bytes_are_honest(self, client, tmp_path, monkeypatch):
        ids = self._due(tmp_path, monkeypatch)
        body = client.get("/api/artifacts/expiry").json()
        assert body["count"] == 2 and body["days"] == 30
        assert body["bytes"] == 201 and [d["id"] for d in body["due"]] == ids

    def test_given_due_copies_when_answered_keep_then_nothing_is_due(self, client, tmp_path, monkeypatch):
        ids = self._due(tmp_path, monkeypatch)
        r = client.post("/api/artifacts/expiry/answer", json={"ids": ids, "action": "keep"})
        assert r.status_code == 200
        assert sorted(r.json()["kept"]) == sorted(ids)
        assert client.get("/api/artifacts/expiry").json()["count"] == 0

    def test_given_due_copies_when_answered_delete_then_files_are_gone(self, client, tmp_path, monkeypatch):
        ids = self._due(tmp_path, monkeypatch)
        r = client.post("/api/artifacts/expiry/answer", json={"ids": ids, "action": "delete"})
        assert sorted(r.json()["deleted"]) == sorted(ids)
        assert list((tmp_path / "ephe-home" / "artifacts" / "s1").iterdir()) == []
        assert client.get("/api/artifacts").json()["total"] == 0

    def test_given_untouched_question_when_polled_then_nothing_disappears(self, client, tmp_path, monkeypatch):
        self._due(tmp_path, monkeypatch, n=1)
        for _ in range(3):
            client.get("/api/artifacts/expiry")
        assert client.get("/api/artifacts").json()["total"] == 1, "asking does not delete"

    def test_given_unknown_action_when_answered_then_422(self, client):
        assert client.post("/api/artifacts/expiry/answer", json={"ids": ["x"], "action": "drop"}).status_code == 422


class TestAdopt:
    """Adopting (R4 §5.1-3): the workbench keeps its copy, the user gets one at
    the place they named — and the card remembers both."""

    def _art(self, tmp_path, monkeypatch, content=b"deck-bytes", name="deck.pdf"):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        return artifact_store.register_artifact(
            path=_file(tmp_path, name, content), kind="pdf", session_id="s1"
        )

    def test_given_artifact_when_adopted_then_copy_lands_and_the_card_remembers(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch)
        target = tmp_path / "Ziel"
        target.mkdir()
        r = client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": str(target / "deck.pdf")})
        assert r.status_code == 200
        body = r.json()
        assert (target / "deck.pdf").read_bytes() == b"deck-bytes"
        assert body["adopted_path"] == str(target / "deck.pdf")
        assert body["content_hash"] == body["adopted_hash"], "dieselben Bytes"
        back = artifact_store.get_artifact(art["id"])
        assert back["adopted_path"] == str(target / "deck.pdf")
        # the source stays: adopting copies it, and the original stays where it was
        assert (tmp_path / "deck.pdf").exists()

    def test_given_directory_destination_when_adopted_then_it_uses_the_card_name(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch, name="bericht.pdf")
        target = tmp_path / "Ziele mit Umlaut ü"
        target.mkdir()
        r = client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": str(target)})
        assert r.status_code == 200
        assert r.json()["adopted_path"] == str(target / "bericht.pdf")

    def test_given_foreign_existing_file_when_adopted_then_409_not_overwrite(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch)
        (tmp_path / "wichtig.docx").write_bytes(b"andere arbeit")
        r = client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": str(tmp_path / "wichtig.docx")})
        assert r.status_code == 409
        assert (tmp_path / "wichtig.docx").read_bytes() == b"andere arbeit"

    def test_given_own_last_copy_when_adopted_again_then_it_refreshes(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch)
        dest = tmp_path / "copy.pdf"
        client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": str(dest)})
        (tmp_path / "deck.pdf").write_bytes(b"neuere version")
        artifact_store._write(
            "UPDATE artifacts SET content_hash = ? WHERE id = ?",
            (workbench.content_hash(tmp_path / "deck.pdf"), art["id"]),
        )
        r = client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": str(dest)})
        assert r.status_code == 200
        assert dest.read_bytes() == b"neuere version"

    def test_given_relative_destination_when_adopted_then_422(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch)
        r = client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": "relativ.pdf"})
        assert r.status_code == 422

    def test_given_destination_outside_roots_when_adopted_then_403(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch)
        # Allowed roots stay [tmp_path] — the destination is deliberately outside.
        aussen = tmp_path.parent / f"{tmp_path.name}-aussen"
        aussen.mkdir()
        r = client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": str(aussen / "x.pdf")})
        assert r.status_code == 403
        assert not (aussen / "x.pdf").exists()

    def test_given_missing_bytes_when_adopted_then_404(self, client, tmp_path, monkeypatch):
        import pathlib

        art = self._art(tmp_path, monkeypatch)
        pathlib.Path(art["path"]).unlink()
        assert client.post(
            f"/api/artifacts/{art['id']}/adopt", json={"destination": str(tmp_path / "x.pdf")}
        ).status_code == 404


    def test_given_fresh_workbench_copy_when_stats_asked_then_no_question_is_announced(self, client, tmp_path, monkeypatch):
        """A card born today that will be asked in 30 days is not a pending
        question. The page header pretended otherwise anyway."""
        import datetime as dt

        root = tmp_path / "ephe-home"
        (root / "artifacts" / "s1").mkdir(parents=True)
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
        p = root / "artifacts" / "s1" / "fresh.pdf"
        p.write_bytes(b"x" * 10)
        row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
        assert row["expires_at"], "workbench copies carry a deadline"
        body = client.get("/api/artifacts/stats").json()
        assert body["count"] == 1
        assert body["expiring_count"] == 0 and body["next_expiry"] is None
        assert client.get("/api/artifacts/expiry").json()["count"] == 0

        artifact_store._write(
            "UPDATE artifacts SET expires_at = ? WHERE id = ?",
            ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds"), row["id"]),
        )
        after = client.get("/api/artifacts/stats").json()
        assert after["expiring_count"] == 1 and after["next_expiry"]


class TestCardDetail:
    """One card in full — the comparison against its adopted copy happens here,
    not in the list (hashing 500 files for a view nobody opens is not an answer,
    it is a load)."""

    def _art(self, tmp_path, monkeypatch):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        return artifact_store.register_artifact(
            path=_file(tmp_path, "karte.pdf", b"bytes"), kind="pdf", session_id="s1"
        )

    def test_given_unadopted_card_when_read_then_state_is_none(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch)
        r = client.get(f"/api/artifacts/{art['id']}")
        assert r.status_code == 200
        assert r.json()["adopted_state"] == "none"
        assert r.json()["name"] == "karte.pdf"

    def test_given_adopted_card_when_read_then_state_compares_the_copies(self, client, tmp_path, monkeypatch):
        art = self._art(tmp_path, monkeypatch)
        dest = tmp_path / "kopie.pdf"
        client.post(f"/api/artifacts/{art['id']}/adopt", json={"destination": str(dest)})
        assert client.get(f"/api/artifacts/{art['id']}").json()["adopted_state"] == "current"
        dest.write_bytes(b"andere bytes")
        assert client.get(f"/api/artifacts/{art['id']}").json()["adopted_state"] == "stale"
        dest.unlink()
        assert client.get(f"/api/artifacts/{art['id']}").json()["adopted_state"] == "missing"

    def test_given_unknown_id_when_read_then_404(self, client):
        assert client.get("/api/artifacts/no-card").status_code == 404


class TestContentPreview:
    """A5: the two kinds no browser renders are reported as data the surface can read."""

    def _art(self, client, tmp_path, monkeypatch, marker: str, kind: str):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        produced = marker.splitlines()[0].split(":", 1)[1]
        row = artifact_store.register_artifact(path=produced, kind=kind, session_id="s1")
        return row

    def test_given_xlsx_when_previewed_then_it_arrives_as_a_table(self, client, tmp_path, monkeypatch):
        import asyncio

        from core.tools.office_tools import create_xlsx

        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        marker = asyncio.run(
            create_xlsx(title="Umsatz", data=[["Region", "Q3"], ["Nord", 24], ["Süd", 60]], filename="u.xlsx")
        )
        art = self._art(client, tmp_path / "cfg" / "artifacts" / "ohne-session", monkeypatch, marker, "xlsx")
        body = client.get(f"/api/artifacts/{art['id']}/preview").json()
        assert body["mode"] == "table"
        assert body["header"] == ["Region", "Q3"]
        assert body["rows"] == [["Nord", "24"], ["Süd", "60"]]
        assert body["sheets"] == ["Umsatz"]

    def test_given_docx_when_previewed_then_it_arrives_as_text(self, client, tmp_path, monkeypatch):
        import asyncio

        from core.tools.office_tools import create_docx

        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        marker = asyncio.run(
            create_docx(title="Brief", content="# Anrede\n\nGuten Tag.", filename="b.docx")
        )
        art = self._art(client, tmp_path / "cfg" / "artifacts" / "ohne-session", monkeypatch, marker, "docx")
        body = client.get(f"/api/artifacts/{art['id']}/preview").json()
        assert body["mode"] == "text"
        assert "Guten Tag." in body["text"]

    def test_given_pdf_when_previewed_then_the_answer_is_none_not_empty(self, client, tmp_path, monkeypatch):
        art = self._art(
            client, tmp_path, monkeypatch, f"PDF_FILE:{_file(tmp_path, 'x.pdf', b'%PDF')}", "pdf"
        )
        body = client.get(f"/api/artifacts/{art['id']}/preview").json()
        assert body == {"mode": "none", "reason": "no-text-preview"}

    def test_given_vanished_file_when_previewed_then_404(self, client, tmp_path, monkeypatch):
        import pathlib

        art = self._art(
            client, tmp_path, monkeypatch, f"XLSX_FILE:{_file(tmp_path, 'y.xlsx')}", "xlsx"
        )
        pathlib.Path(art["path"]).unlink()
        assert client.get(f"/api/artifacts/{art['id']}/preview").status_code == 404


class TestStats:
    def test_given_rows_when_stats_asked_then_counts_cover_every_row(self, client, tmp_path):
        artifact_store.register_artifact(path=_file(tmp_path, "a.pdf", b"x" * 10), kind="pdf", session_id="s1")
        artifact_store.register_artifact(path=_file(tmp_path, "b.png", b"x" * 90), kind="png", session_id="s2")
        body = client.get("/api/artifacts/stats").json()
        assert body["count"] == 2 and body["bytes"] == 100
        assert {k["kind"]: k["count"] for k in body["by_kind"]} == {"pdf": 1, "png": 1}
        # none of this lives in the workbench → no deadline, and the number says so
        assert body["expiring_count"] == 0 and body["next_expiry"] is None


    def test_given_turn_when_stream_runs_then_the_artifact_carries_turn_and_call(self, client, tmp_path, monkeypatch):
        """A3: the chain starts here. Without a turn id in the index, "which job
        produced this file?" would be an unanswerable question — and the call_id
        "0" was not an identifier but a counter value."""
        from unittest.mock import AsyncMock

        marker_file = _file(tmp_path, "kettenbrief.pdf", b"PDF")

        async def fake_chat_with_tools(**kwargs):
            assert kwargs.get("turn_id"), "the stream has to pass its turn through"
            kwargs["on_tool_start"]("create_pdf", {"title": "Kette"}, f"{kwargs['turn_id'][:8]}-0")
            kwargs["on_tool_done"]("create_pdf", f"PDF_FILE:{marker_file}\nPDF_PAGES:1", f"{kwargs['turn_id'][:8]}-0")
            return "PDF erstellt"

        monkeypatch.setattr("server.routes.chat.chat_with_tools", fake_chat_with_tools)
        monkeypatch.setattr(
            "server.routes.chat.reflect",
            AsyncMock(return_value=SimpleNamespace(needs_revision=False, reason="ok")),
        )
        r = client.post(
            "/api/chat/stream",
            json={"message": "Erzeuge kettenbrief.pdf", "session_id": "sess-kette"},
        )
        assert r.status_code == 200
        assert '"type": "turn"' in r.text or '"type":"turn"' in r.text.replace(" ", "") or "turn_id" in r.text

        rows = artifact_store.list_artifacts()
        assert len(rows) == 1
        art = rows[0]
        assert art["turn_id"], "the card must know which turn it came from"
        assert art["call_id"].startswith(art["turn_id"][:8]), (art["turn_id"], art["call_id"])
        assert art["args_hash"], "the tool call is recorded with its arguments"
        # the file_result event carries the card id (A0) and its turn identifier
        event = [line for line in r.text.splitlines() if "file_result" in line][0]
        assert art["id"] in event and art["turn_id"] in event


class TestTurnQuery:
    """A3 backwards: the job knows its files."""

    def test_given_two_turns_when_queried_by_turn_then_only_its_own_files(self, client, tmp_path):
        artifact_store.register_artifact(path=_file(tmp_path, "turn-a.pdf"), kind="pdf", session_id="s1", turn_id="turn-a")
        artifact_store.register_artifact(path=_file(tmp_path, "turn-b.pdf"), kind="pdf", session_id="s1", turn_id="turn-b")
        body = client.get("/api/artifacts", params={"turn_id": "turn-a"}).json()
        assert [a["name"] for a in body["artifacts"]] == ["turn-a.pdf"]
        assert client.get("/api/artifacts", params={"turn_id": "unbekannt"}).json()["total"] == 0
        # without the filter the list stays what it was — the filter is an addition
        assert client.get("/api/artifacts").json()["total"] == 2


class TestProvenance:
    """The chain has to say where it starts — and say so when it cannot."""

    def test_given_old_card_without_turn_then_the_gap_is_named(self, client, tmp_path):
        art = artifact_store.register_artifact(path=_file(tmp_path, "alt.pdf"), kind="pdf", session_id="s1")
        body = client.get(f"/api/artifacts/{art['id']}/provenance").json()
        assert body["known"] is False and body["calls"] == []

    def test_given_turn_card_then_its_audit_lines_come_back(self, client, tmp_path, monkeypatch):
        from core import audit_log

        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
        art = artifact_store.register_artifact(
            path=_file(tmp_path, "neu.pdf"), kind="pdf", session_id="s1",
            turn_id="deadbeef0102", call_id="deadbe-0", args_hash="ab" * 8,
        )
        audit_log.audit_event("tool_exec", tool="create_pdf", args={"title": "Neu"}, status="ok", turn_id="deadbeef0102")
        audit_log.audit_event("tool_exec", tool="read_file", args={"path": "/tmp/x"}, status="ok", turn_id="anderein")
        body = client.get(f"/api/artifacts/{art['id']}/provenance").json()
        assert body["known"] is True
        assert body["call_id"] == "deadbe-0"
        assert [c["tool"] for c in body["calls"]] == ["create_pdf"], "only its own turn"

    def test_given_auto_turn_when_audited_then_the_line_carries_it_without_being_asked(self, tmp_path, monkeypatch):
        """The turn comes from the contextvar and never from the caller — otherwise
        the chain breaks exactly at the tool calls it is meant to cover."""
        from core import audit_log
        from core.artifact_workbench import set_artifact_turn

        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
        set_artifact_turn("cafe1234babe")
        audit_log.audit_event("tool_exec", tool="create_svg", args={"filename": "x.svg"}, status="ok")
        set_artifact_turn("")
        lines = audit_log.tail()
        assert lines and lines[0]["turn_id"] == "cafe1234babe"
        assert audit_log.tail(turn_id="cafe1234babe") and audit_log.tail(turn_id="fehle") == []


class TestChatIngest:
    def test_given_agent_pdf_tool_result_when_streamed_then_artifact_registered(self, client, tmp_path, monkeypatch):
        """R17 core: the REAL stream registers file outputs in the library
        (R36: injection through the agent path — the create_pdf tool result)."""
        from unittest.mock import AsyncMock

        marker_file = _file(tmp_path, "auto_brief.pdf", b"PDF")

        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_done"]("create_pdf", f"PDF_FILE:{marker_file}\nPDF_PAGES:1")
            kwargs["on_chunk"]("## PDF erstellt")
            return "## PDF erstellt"

        monkeypatch.setattr("server.routes.chat.chat_with_tools", fake_chat_with_tools)
        monkeypatch.setattr(
            "server.routes.chat.reflect",
            AsyncMock(return_value=SimpleNamespace(needs_revision=False, reason="ok")),
        )
        r = client.post(
            "/api/chat/stream",
            json={"message": "erstelle ein PDF über Project Northstar", "session_id": "sess-42"},
        )
        assert r.status_code == 200
        rows = artifact_store.list_artifacts()
        assert len(rows) == 1
        assert rows[0]["name"] == "auto_brief.pdf"
        assert rows[0]["kind"] == "pdf"
        assert rows[0]["session_id"] == "sess-42"

    def test_given_store_failure_when_streaming_then_stream_survives(self, client, tmp_path, monkeypatch):
        """A registration failure must never tear the chat stream down."""
        from unittest.mock import AsyncMock

        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_done"]("create_pdf", f"PDF_FILE:{_file(tmp_path, 'ok.pdf')}\nPDF_PAGES:1")
            kwargs["on_chunk"]("## PDF erstellt")
            return "## PDF erstellt"

        monkeypatch.setattr("server.routes.chat.chat_with_tools", fake_chat_with_tools)
        monkeypatch.setattr(
            "server.routes.chat.reflect",
            AsyncMock(return_value=SimpleNamespace(needs_revision=False, reason="ok")),
        )
        monkeypatch.setattr(
            artifact_store, "register_artifact",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("store down")),
        )
        r = client.post(
            "/api/chat/stream",
            json={"message": "erstelle ein PDF über Resilienz", "session_id": "sess-7"},
        )
        assert r.status_code == 200
        assert "PDF erstellt" in r.text

    def test_given_multi_marker_deck_result_when_streamed_then_every_artifact_is_registered(
        self, client, tmp_path, monkeypatch
    ):
        """W10: one deck tool result carries several markers on several lines —
        the library must hold every one of them, the first included."""
        from unittest.mock import AsyncMock

        markers = {
            "PPTX_DECK_FILE:": _file(tmp_path, "deck.pptx", b"pptx"),
            "SCORECARD_FILE:": _file(tmp_path, "scorecard.json", b"{}"),
            "MANIFEST_FILE:": _file(tmp_path, "manifest.json", b"{}"),
            "QA_FILE:": _file(tmp_path, "qa.json", b"{}"),
            "CONTACT_SHEET_FILE:": _file(tmp_path, "contact.html", b"<html></html>"),
        }
        deck_result = "\n".join(f"{marker}{path}" for marker, path in markers.items())

        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_done"]("create_pptx_deck", deck_result)
            kwargs["on_chunk"]("## Deck bereit")
            return "## Deck bereit"

        monkeypatch.setattr("server.routes.chat.chat_with_tools", fake_chat_with_tools)
        monkeypatch.setattr(
            "server.routes.chat.reflect",
            AsyncMock(return_value=SimpleNamespace(needs_revision=False, reason="ok")),
        )
        r = client.post(
            "/api/chat/stream",
            json={"message": "erstelle ein Deck", "session_id": "sess-deck"},
        )
        assert r.status_code == 200
        assert r.text.count('"type": "file_result"') == 5

        rows = artifact_store.list_artifacts()
        assert len(rows) == 5, f"only {len(rows)} of 5 markers reached the library"
        assert {row["name"] for row in rows} == {
            "deck.pptx", "scorecard.json", "manifest.json", "qa.json", "contact.html",
        }
        assert {row["kind"] for row in rows} == {"pptx", "scorecard", "manifest", "qa", "html"}
        assert {row["session_id"] for row in rows} == {"sess-deck"}
