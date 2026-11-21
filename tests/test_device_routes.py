"""tests/test_device_routes.py — the device declaration reaches the app (F2).

`ephe device` has read `core/persistence.py` from the terminal since F1; these two
routes carry the same answer into the product's own surface. The round trip runs
against the live app (the way `tests/test_file_route.py` reads files through it),
over a device folder the test builds, so every number is arithmetic over a known
ground. The promises pinned here are the declaration's own: a dry run unlinks
nothing, apply reaches only the rows marked forgettable, the kept rows survive,
and an entry no row names is never removed — refused by name before the run starts.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def device(tmp_path):
    """A device folder with one row from each class the declaration answers for."""
    folder = tmp_path / "ephe"
    (folder / "sessions").mkdir(parents=True)
    (folder / "sessions" / "one.json").write_text('{"ok": true}\n', encoding="utf-8")
    (folder / "settings.json").write_text("{}\n", encoding="utf-8")
    (folder / "audit.log").write_text("line\n", encoding="utf-8")
    (folder / "cells").mkdir()
    (folder / "trusted-keys").mkdir()
    # What the folder holds and no row declares: a leftover, always someone's file.
    (folder / "hand-backup").write_text("keep me?", encoding="utf-8")
    return folder


@pytest.fixture
def client(device, tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    os.environ.pop("EPHE_SETUP_MODE", None)
    from server.main import create_app

    return TestClient(create_app())


class TestDeviceStateRoute:
    """GET /api/device — the read-only answer the settings card renders."""

    def test_the_shape_answers_the_declaration(self, client):
        answer = client.get("/api/device")
        assert answer.status_code == 200
        body = answer.json()
        from core.persistence import EPHE_PERSISTENCE

        assert body["declared"] == len(EPHE_PERSISTENCE)
        assert {row["name"] for row in body["entries"]} <= {
            entry.name for entry in EPHE_PERSISTENCE
        }
        assert body["total_bytes"] == sum(int(row["bytes"]) for row in body["entries"])
        assert isinstance(body["unnamed"], list)

    def test_every_present_entry_arrives_with_its_kind_its_hold_and_its_size(self, client):
        body = client.get("/api/device").json()
        rows = {row["name"]: row for row in body["entries"]}
        # The app creates its own declared entries when it starts; the fixture's
        # rows all answer, each with kind, hold and measured bytes.
        assert rows["sessions"]["kind"] == "dir"
        assert rows["settings.json"]["kind"] == "file"
        assert int(rows["sessions"]["bytes"]) >= len('{"ok": true}\n')
        assert rows["audit.log"]["forgettable"] is False
        assert rows["sessions"]["forgettable"] is True
        assert "task history" in rows["sessions"]["holds"]
        assert all(row["present"] for row in body["entries"])

    def test_the_leftover_is_counted_and_named(self, client):
        body = client.get("/api/device").json()
        assert body["unnamed"] == ["hand-backup"]
        assert "hand-backup" not in {row["name"] for row in body["entries"]}

    def test_a_folder_that_never_ran_answers_zero_entries(self, client, tmp_path, monkeypatch):
        quiet = tmp_path / "quiet"
        quiet.mkdir()
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(quiet))
        body = client.get("/api/device").json()
        assert body["entries"] == []
        assert body["present"] == 0
        assert body["total_bytes"] == 0
        assert body["unnamed"] == []


class TestDeviceForgetRoute:
    """POST /api/device/forget — the clear, dry run first, kept rows refused by name."""

    def test_the_default_is_a_dry_run_and_it_unlinks_nothing(self, client, device):
        answer = client.post("/api/device/forget", json={})
        assert answer.status_code == 200
        body = answer.json()
        assert body["dry_run"] is True
        assert "settings.json" in body["removed"]
        assert "audit.log" in body["kept"]
        assert body["unnamed"] == ["hand-backup"]
        assert (device / "settings.json").exists()
        assert (device / "sessions").is_dir()

    def test_an_explicit_apply_forgot_only_what_the_declaration_marks_forgettable(
        self, client, device
    ):
        body = client.post("/api/device/forget", json={"dry_run": False}).json()
        assert body["dry_run"] is False
        assert not (device / "settings.json").exists()
        assert not (device / "sessions").exists()
        assert {"sessions", "settings.json"} <= set(body["removed"])
        assert set(body["removed"]) <= {"sessions", "settings.json", "artifacts", "tasks.json"}

    def test_the_kept_rows_survive_the_apply(self, client, device):
        client.post("/api/device/forget", json={"dry_run": False})
        assert (device / "audit.log").exists()
        assert (device / "cells").is_dir()
        assert (device / "trusted-keys").is_dir()

    def test_an_entry_no_row_names_is_never_removed(self, client, device):
        client.post("/api/device/forget", json={"dry_run": False})
        assert (device / "hand-backup").exists()

    def test_a_scoped_run_clears_only_the_names_it_was_given(self, client, device):
        body = client.post(
            "/api/device/forget",
            json={"names": ["settings.json"], "dry_run": False},
        ).json()
        assert body["removed"] == ["settings.json"]
        assert not (device / "settings.json").exists()
        assert (device / "sessions").is_dir()

    def test_a_name_outside_the_declaration_is_refused_before_anything_goes(self, client, device):
        answer = client.post(
            "/api/device/forget",
            json={"names": ["hand-backup", "settings.json"], "dry_run": False},
        )
        assert answer.status_code == 400
        error = answer.json()["error"]
        assert error["reason_code"] == "device_forget_undeclared"
        assert "hand-backup" in error["message"]
        assert (device / "settings.json").exists(), "a refused run never starts halfway"
        assert (device / "hand-backup").exists()

    def test_a_row_the_declaration_keeps_is_refused_by_name(self, client, device):
        answer = client.post(
            "/api/device/forget", json={"names": ["audit.log"], "dry_run": False}
        )
        assert answer.status_code == 409
        error = answer.json()["error"]
        assert error["reason_code"] == "device_forget_kept"
        assert (device / "audit.log").exists()

    def test_the_round_trip_reports_the_folder_as_it_now_stands(self, client):
        """The card's own sequence: read, apply, read again — one live server."""
        before = client.get("/api/device").json()
        assert before["present"] == len(before["entries"])
        assert {"sessions", "settings.json", "audit.log"} <= {
            row["name"] for row in before["entries"]
        }
        client.post("/api/device/forget", json={"dry_run": False})
        after = client.get("/api/device").json()
        assert {row["name"] for row in after["entries"]} == {"audit.log", "cells", "trusted-keys"}
        assert after["present"] == 3
        assert after["total_bytes"] < before["total_bytes"]
