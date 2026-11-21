"""tests/test_session_trash.py — the chat trash: aside, back, and finally gone.

`DELETE /api/sessions/{id}` unlinks, and one sidebar click should not be final
before the click is noticed. These cases pin the divergence from the plain
delete: the file waits in the declared trash tree with its registry row kept
in the manifest, the list and the search stop seeing it while live, restore
brings both halves back, and only the emptying forgets the Creator consent.
Every case runs against a temporary store and a temporary config root; the
owner's sessions and the owner's trash are never the target.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _trash():
    from core import session_trash

    return session_trash


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A private store and a private device folder, both resolved per call."""
    import core.multi_session as ms

    sdir = tmp_path / "sessions"
    sdir.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sdir)
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "ephe-home"))
    return sdir


@pytest.fixture
def client(store):
    from server.main import create_app

    return TestClient(create_app())


def _seed(store: Path, session_id: str, *, title: str = "A quiet session") -> Path:
    (store / f"{session_id}.json").write_text(
        json.dumps([{"role": "user", "content": "hello"}]), encoding="utf-8"
    )
    from core.session_lifecycle import read_registry, save_registry

    registry = read_registry(store)
    registry.setdefault("sessions", []).append(
        {"id": session_id, "title": title, "created_at": 1, "source": "chat"}
    )
    save_registry(registry, store)
    return store / f"{session_id}.json"


def _registry_ids(store: Path) -> list[str]:
    from core.session_lifecycle import read_registry

    return [str(e.get("id")) for e in read_registry(store).get("sessions", [])]


def _live_ids(client) -> list[str]:
    return [s["id"] for s in client.get("/api/sessions").json()["sessions"]]


def _age_run(run_dir: Path, days: int) -> Path:
    """Make a run look like it has waited `days`, the way the sweep reads it."""
    from datetime import datetime, timedelta, timezone

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    waited = datetime.now(timezone.utc) - timedelta(days=days)
    manifest["trashed_at"] = waited.isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


def test_trashing_moves_the_file_aside_and_clears_it_from_the_live_store(store, client):
    path = _seed(store, "abcd1234")
    response = client.post("/api/sessions/abcd1234/trash")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trashed"] == "abcd1234"
    assert body["bytes_moved"] > 0
    assert not path.exists()
    assert "abcd1234" not in _live_ids(client)
    assert "abcd1234" not in _registry_ids(store)
    trashed_file = _trash().trash_root() / body["run"] / "abcd1234.json"
    assert trashed_file.exists()
    assert json.loads(trashed_file.read_text(encoding="utf-8"))[0]["content"] == "hello"


def test_the_trashed_run_remembers_the_registry_row_verbatim(store, client):
    _seed(store, "ef567890", title="Keeps its name")
    run = client.post("/api/sessions/ef567890/trash").json()["run"]
    manifest = json.loads((_trash().trash_root() / run / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["entries"][0]
    assert entry["title"] == "Keeps its name"
    assert entry["registry_entry"]["title"] == "Keeps its name"
    assert entry["namespace"] == ""


def test_restore_brings_file_and_registry_row_back(store, client):
    _seed(store, "cafe0001")
    run = client.post("/api/sessions/cafe0001/trash").json()["run"]
    response = client.post("/api/sessions/trash/cafe0001/restore")
    assert response.status_code == 200, response.text
    assert response.json() == {"restored": "cafe0001", "run": run}
    assert (store / "cafe0001.json").exists()
    assert "cafe0001" in _registry_ids(store)
    assert "cafe0001" in _live_ids(client)


def test_restoring_twice_names_the_second_one_as_gone(store, client):
    _seed(store, "cafe0002")
    client.post("/api/sessions/cafe0002/trash")
    assert client.post("/api/sessions/trash/cafe0002/restore").status_code == 200
    second = client.post("/api/sessions/trash/cafe0002/restore")
    assert second.status_code == 404
    assert second.json()["error"]["reason_code"] == "session_not_in_trash"


def test_a_live_file_under_the_id_beats_the_trashed_copy(store, client):
    _seed(store, "cafe0003")
    run = client.post("/api/sessions/cafe0003/trash").json()["run"]
    (store / "cafe0003.json").write_text(json.dumps([]), encoding="utf-8")
    response = client.post("/api/sessions/trash/cafe0003/restore")
    assert response.status_code == 409
    assert response.json()["error"]["reason_code"] == "session_exists"
    assert "cafe0003" in response.json()["error"]["message"]
    assert (_trash().trash_root() / run / "cafe0003.json").exists()


def test_trashing_an_unknown_id_is_a_coded_refusal(store, client):
    response = client.post("/api/sessions/nosuchid/trash")
    assert response.status_code == 404
    assert response.json()["error"]["reason_code"] == "session_not_found"
    assert "nosuchid" in response.json()["error"]["message"]


def test_an_id_that_could_name_a_path_outside_the_store_is_refused(store):
    result = _trash().move_sessions_to_trash(["../escape", "bad/name", "ok_but_absent"])
    assert result["trashed"] == []
    assert result["missing"] == ["../escape", "bad/name", "ok_but_absent"]


def test_the_trash_lists_newest_first_and_counts_every_run(store, client, monkeypatch):
    _seed(store, "aaa11111")
    _seed(store, "bbb22222")
    stamps = iter(["20261101T000000Z", "20261102T000000Z"])
    monkeypatch.setattr(_trash(), "_now_stamp", lambda: next(stamps))
    client.post("/api/sessions/aaa11111/trash")
    client.post("/api/sessions/bbb22222/trash")
    body = client.get("/api/sessions/trash").json()
    assert body["total"] == 2
    assert body["entries"][0]["session_id"] == "bbb22222"
    assert [e["run"] for e in body["entries"]] == ["20261102T000000Z", "20261101T000000Z"]
    assert all("trashed_at" in e for e in body["entries"])


def test_a_trashed_session_stops_answer_to_the_list_and_the_export(store, client):
    _seed(store, "ddd44444")
    assert "ddd44444" in _live_ids(client)
    client.post("/api/sessions/ddd44444/trash")
    assert "ddd44444" not in _live_ids(client)


def test_emptying_is_the_only_path_that_forgets_consent(store, client, monkeypatch):
    from core.tools import creator_guard

    forgotten: list[str] = []
    monkeypatch.setattr(creator_guard, "forget_session", lambda sid: forgotten.append(sid))
    _seed(store, "eee55555")
    client.post("/api/sessions/eee55555/trash")
    assert forgotten == []
    dry = client.post("/api/sessions/trash/empty", json={"dry_run": True})
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True
    assert dry.json()["deleted"] == ["eee55555"]
    assert forgotten == []
    assert client.get("/api/sessions/trash").json()["total"] == 1
    final = client.post("/api/sessions/trash/empty", json={"dry_run": False})
    assert final.status_code == 200
    assert final.json()["deleted"] == ["eee55555"]
    assert forgotten == ["eee55555"]
    assert client.get("/api/sessions/trash").json()["entries"] == []


def test_emptying_an_empty_trash_says_so(store, client):
    response = client.post("/api/sessions/trash/empty", json={"dry_run": False})
    assert response.status_code == 409
    assert response.json()["error"]["reason_code"] == "trash_empty"


def test_a_mutation_from_a_foreign_origin_stays_at_the_guard(store):
    from server.main import create_app

    desktop = TestClient(create_app(), base_url="http://localhost:8765")
    response = desktop.post("/api/sessions/abcd1234/trash")
    assert response.status_code == 403
    assert response.json()["error"]["detail"]["code"] == "untrusted_origin"


def test_a_mirror_file_without_a_registry_row_trashes_and_restores_plainly(store, client):
    (store / "pwa-caller1.json").write_text(json.dumps([]), encoding="utf-8")
    response = client.post("/api/sessions/pwa-caller1/trash")
    assert response.status_code == 200
    assert client.post("/api/sessions/trash/pwa-caller1/restore").status_code == 200
    assert (store / "pwa-caller1.json").exists()
    assert _registry_ids(store) == []


# The window that bounds the folder. A store under the config dir that nothing
# empties is the shape core/store_retention.py measured on 2026-10-14, so a run
# does not wait forever. The window is a control in the ephemera section, which
# is what separates it from a delete nobody authorized.


def _two_runs(store, client, monkeypatch):
    """One run from yesterday, one from long ago; both hold one session."""
    _seed(store, "old11111")
    _seed(store, "new22222")
    stamps = iter(["20260201T000000Z", "20260202T000000Z"])
    monkeypatch.setattr(_trash(), "_now_stamp", lambda: next(stamps))
    client.post("/api/sessions/old11111/trash")
    client.post("/api/sessions/new22222/trash")
    root = _trash().trash_root()
    return _age_run(root / "20260201T000000Z", 31), root / "20260202T000000Z"


def test_the_window_takes_the_old_run_and_spares_the_younger_one(store, client, monkeypatch):
    old, young = _two_runs(store, client, monkeypatch)
    result = _trash().purge_expired()
    assert result["deleted"] == ["old11111"]
    assert result["runs"] == [old.name]
    assert result["kept"] == 1
    assert result["retention_days"] == 30, "the register default is the window nobody set"
    assert not old.exists(), "a run past the window leaves no folder behind"
    assert young.exists()
    body = client.get("/api/sessions/trash").json()
    assert [e["session_id"] for e in body["entries"]] == ["new22222"]


def test_zero_keeps_everything_until_the_owner_empties(store, client):
    from core.settings_schema import save_deep_settings

    _seed(store, "old44444")
    run = _trash().trash_root() / client.post("/api/sessions/old44444/trash").json()["run"]
    _age_run(run, 400)
    assert save_deep_settings({"ephemera": {"ephemera.trash_retention_days": 0}})
    result = _trash().purge_expired()
    assert result["retention_days"] == 0
    assert result["deleted"] == [] and result["kept"] == 1
    assert run.exists(), "0 is the owner's answer: nothing goes without the click"


def test_the_owner_widens_the_window_before_an_old_run_would_go(store, client):
    from core.settings_schema import save_deep_settings

    _seed(store, "old55555")
    run = _trash().trash_root() / client.post("/api/sessions/old55555/trash").json()["run"]
    _age_run(run, 45)
    save_deep_settings({"ephemera": {"ephemera.trash_retention_days": 90}})
    assert _trash().purge_expired()["kept"] == 1
    assert run.exists()
    save_deep_settings({"ephemera": {"ephemera.trash_retention_days": 30}})
    assert _trash().purge_expired()["deleted"] == ["old55555"]
    assert not run.exists()


def test_a_hand_written_window_beyond_the_register_bounds_is_clamped(store, client):
    from core.settings_schema import save_deep_settings

    _seed(store, "old66666")
    run = _trash().trash_root() / client.post("/api/sessions/old66666/trash").json()["run"]
    _age_run(run, 200)
    save_deep_settings({"ephemera": {"ephemera.trash_retention_days": 5000}})
    assert _trash().retention_days() == 365, "the register states the bounds, not the file"
    assert run.exists()


def test_a_purge_forgets_consent_only_when_it_actually_deletes(store, client, monkeypatch):
    from core.tools import creator_guard

    forgotten: list[str] = []
    monkeypatch.setattr(creator_guard, "forget_session", lambda sid: forgotten.append(sid))
    _seed(store, "old77777")
    run = _trash().trash_root() / client.post("/api/sessions/old77777/trash").json()["run"]
    _age_run(run, 60)
    counted = _trash().purge_expired(dry_run=True)
    assert counted["deleted"] == ["old77777"]
    assert counted["dry_run"] is True
    assert forgotten == [], "a count is not a delete"
    assert run.exists()
    final = _trash().purge_expired()
    assert final["deleted"] == ["old77777"]
    assert forgotten == ["old77777"], "past the window is as gone as the emptying"
    assert not run.exists()


def test_a_run_without_a_manifest_ages_by_its_folder(store, client):
    import os
    import time

    _seed(store, "old88888")
    run = _trash().trash_root() / client.post("/api/sessions/old88888/trash").json()["run"]
    (run / "manifest.json").unlink()
    wrote = time.time() - 40 * 86400
    os.utime(run, (wrote, wrote))
    assert _trash().purge_expired()["deleted"] == ["old88888"]
    assert not run.exists()


def test_an_unreadable_settings_file_keeps_the_default_window_and_the_files(store, client):
    _seed(store, "old99999")
    run = _trash().trash_root() / client.post("/api/sessions/old99999/trash").json()["run"]
    _age_run(run, 60)
    from core.settings_schema import settings_path

    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text("{ not json", encoding="utf-8")
    assert _trash().retention_days() == 30
    assert _trash().purge_expired()["deleted"] == ["old99999"]
    assert not run.exists(), "the broken file costs the owner nothing but the override"
