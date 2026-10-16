"""tests/test_session_lifecycle.py — the store counts itself and can be pruned.

Finding 2026-10-13, measured on this machine: ``~/.ephe/sessions`` held more
than eight thousand JSON files while the PWA mirror could reach fifty of them
and the registry listed under two thousand. Nothing pruned the store.
``create_session`` writes one file per call, the REST mirror writes one file
per caller session id, and no route removed either class. Every case here
fails while that policy is absent, and every one of them runs against a
temporary store: the owner's real sessions are never the target.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MAX_RESTORE_SESSIONS = 50


def _life():
    from core import session_lifecycle

    return session_lifecycle


def _write(sdir: Path, name: str, messages=None, mtime: float | None = None) -> Path:
    path = sdir / f"{name}.json"
    path.write_text(json.dumps(messages if messages is not None else []), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A private store. The real directory is never the target of a test."""
    import core.multi_session as ms

    sdir = tmp_path / "sessions"
    sdir.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sdir)
    # The search index is a real database on this machine; point it at the test
    # directory too, so a drop never reaches the owner's index.
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    assert ms.SESSIONS_DIR == sdir
    return sdir


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(store))
    from server.main import create_app

    return TestClient(create_app())


def test_namespace_is_read_from_the_prefix(store):
    life = _life()
    assert life.namespace_of("rest-abc") == "rest-"
    assert life.namespace_of("pwa-abc") == "pwa-"
    assert life.namespace_of("0123abcd") == ""


def test_stats_count_each_namespace_and_its_bytes(store):
    life = _life()
    now = time.time()
    _write(store, "rest-one", [], mtime=now)
    _write(store, "rest-two", [], mtime=now - 10)
    _write(store, "pwa-one", [], mtime=now - 20)
    _write(store, "0123abcd", [{"role": "user", "content": "hello"}], mtime=now - 30)
    (store / "registry.json").write_text(json.dumps({"sessions": [{"id": "0123abcd"}]}), encoding="utf-8")

    stats = life.store_stats()
    assert stats["by_namespace"]["rest-"]["files"] == 2
    assert stats["by_namespace"]["pwa-"]["files"] == 1
    assert stats["by_namespace"][""]["files"] == 1
    assert stats["total"] == 4
    assert stats["bytes"] > 0
    assert stats["registered_sessions"] == 1
    assert stats["reachable_by_restore"] == 1


def test_stats_name_the_files_no_list_can_reach(store):
    life = _life()
    now = time.time()
    _write(store, "1a2b3c4d", [], mtime=now - 1)
    _write(store, "rest-hidden", [], mtime=now - 2)
    (store / "registry.json").write_text(json.dumps({"sessions": []}), encoding="utf-8")

    stats = life.store_stats()
    assert stats["registered_sessions"] == 0
    # the REST mirror is the class the registry never holds
    assert stats["unreachable_by_list"] == 2


def test_prune_keeps_the_newest_and_deletes_the_older(store):
    life = _life()
    now = time.time()
    for i in range(6):
        _write(store, f"rest-{i}", [], mtime=now - i)

    res = life.prune_store(keep={"rest-": 2})
    assert set(res["deleted"]) == {"rest-2", "rest-3", "rest-4", "rest-5"}
    assert sorted(p.name for p in store.glob("rest-*.json")) == ["rest-0.json", "rest-1.json"]
    assert res["bytes_freed"] > 0


def test_prune_defaults_bound_the_two_mirror_namespaces(store):
    life = _life()
    now = time.time()
    keep = life.DEFAULT_KEEP
    for i in range(keep["rest-"] + 4):
        _write(store, f"rest-{i:05d}", [], mtime=now - i)
    for i in range(keep["pwa-"] + 4):
        _write(store, f"pwa-{i:05d}", [], mtime=now - i)

    life.prune_store()
    assert len(list(store.glob("rest-*.json"))) == keep["rest-"]
    assert len(list(store.glob("pwa-*.json"))) == keep["pwa-"]


def test_prune_leaves_the_registered_sessions_and_the_registry(store):
    life = _life()
    now = time.time()
    _write(store, "0123abcd", [], mtime=now - 5000)
    _write(store, "rest-old", [], mtime=now - 5000)
    (store / "registry.json").write_text(json.dumps({"sessions": [{"id": "0123abcd"}]}), encoding="utf-8")

    life.prune_store(keep={"rest-": 0})
    assert (store / "0123abcd.json").exists()
    assert (store / "registry.json").exists()
    assert not (store / "rest-old.json").exists()


def test_a_named_namespace_is_the_only_one_pruned(store):
    life = _life()
    now = time.time()
    _write(store, "rest-a", [], mtime=now - 100)
    _write(store, "pwa-a", [], mtime=now - 100)

    life.prune_store(keep={"rest-": 0}, namespaces=("rest-",))
    assert not (store / "rest-a.json").exists()
    assert (store / "pwa-a.json").exists()


def test_dry_run_reports_the_work_without_doing_it(store):
    life = _life()
    now = time.time()
    for i in range(3):
        _write(store, f"rest-{i}", [], mtime=now - i)

    res = life.prune_store(keep={"rest-": 1}, dry_run=True)
    assert set(res["deleted"]) == {"rest-1", "rest-2"}
    assert res["dry_run"] is True
    assert len(list(store.glob("rest-*.json"))) == 3


def test_prune_keeps_the_active_session_even_when_it_is_oldest(store, monkeypatch):
    life = _life()
    now = time.time()
    _write(store, "aaaaaaaa", [], mtime=now - 5000)
    _write(store, "bbbbbbbb", [], mtime=now)
    (store / "registry.json").write_text(
        json.dumps({"active_id": "aaaaaaaa", "sessions": [{"id": "aaaaaaaa"}, {"id": "bbbbbbbb"}]}),
        encoding="utf-8",
    )

    life.prune_store(keep={"": 1})
    assert (store / "aaaaaaaa.json").exists()
    assert not (store / "bbbbbbbb.json").exists()


def test_prune_leaves_artifacts_and_non_session_files_alone(store, tmp_path):
    life = _life()
    out = tmp_path / "artifacts" / "report.pdf"
    out.parent.mkdir()
    out.write_bytes(b"%PDF-1.4")
    (store / "images").mkdir()
    (store / "notes.txt").write_text("kept", encoding="utf-8")
    now = time.time()
    for i in range(4):
        _write(store, f"rest-{i}", [], mtime=now - i)

    res = life.prune_store(keep={"rest-": 1})
    assert out.exists()
    assert (store / "images").is_dir()
    assert (store / "notes.txt").exists()
    assert res["deleted"]


def test_remove_sessions_drops_one_file_and_its_registry_row(store):
    life = _life()
    now = time.time()
    _write(store, "rest-gone", [], mtime=now)
    _write(store, "rest-kept", [], mtime=now)
    (store / "registry.json").write_text(
        json.dumps({"sessions": [{"id": "rest-gone"}, {"id": "rest-kept"}]}), encoding="utf-8"
    )

    res = life.remove_sessions(["rest-gone"])
    assert res["deleted"] == ["rest-gone"]
    assert not (store / "rest-gone.json").exists()
    assert (store / "rest-kept.json").exists()
    reg = json.loads((store / "registry.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in reg["sessions"]] == ["rest-kept"]


def test_remove_sessions_refuses_a_path_that_leaves_the_store(store):
    life = _life()
    (store / "registry.json").write_text(json.dumps({"sessions": []}), encoding="utf-8")
    for bad in ("../registry", "a/b", ".", "registry", "default"):
        assert life.remove_sessions([bad]) == {"deleted": [], "missing": [bad]}
    assert (store / "registry.json").exists()


def test_remove_sessions_reports_an_unknown_id(store):
    life = _life()
    assert life.remove_sessions(["rest-absent"]) == {"deleted": [], "missing": ["rest-absent"]}


def test_list_route_reports_the_holdings(client, store):
    now = time.time()
    _write(store, "rest-a", [], mtime=now)
    _write(store, "0123abcd", [], mtime=now - 1)
    (store / "registry.json").write_text(
        json.dumps({"sessions": [{"id": "0123abcd", "title": "Alpha", "last_active": "2026-10-13T10:00:00"}]}),
        encoding="utf-8",
    )

    body = client.get("/api/sessions").json()
    assert body["total"] == 2
    assert body["by_namespace"]["rest-"]["files"] == 1
    assert [s["id"] for s in body["sessions"]] == ["0123abcd"]
    assert body["sessions"][0]["title"] == "Alpha"


def test_delete_route_removes_one_session(client, store):
    _write(store, "rest-doomed", [], mtime=time.time())
    _write(store, "rest-safe", [], mtime=time.time() - 1)

    res = client.delete("/api/sessions/rest-doomed")
    assert res.status_code == 200
    assert res.json()["deleted"] == ["rest-doomed"]
    assert not (store / "rest-doomed.json").exists()
    assert (store / "rest-safe.json").exists()


def test_delete_route_refuses_an_unknown_id(client, store):
    res = client.delete("/api/sessions/rest-absent")
    assert res.status_code == 404


def test_prune_route_bounds_the_store_and_keeps_the_registry(client, store):
    now = time.time()
    for i in range(5):
        _write(store, f"rest-{i}", [], mtime=now - i)
    (store / "registry.json").write_text(json.dumps({"sessions": [{"id": "0123abcd"}]}), encoding="utf-8")

    res = client.post("/api/sessions/prune", json={"keep_rest": 2})
    assert res.status_code == 200
    body = res.json()
    assert len(body["deleted"]) == 3
    assert body["remaining"]["rest-"] == 2
    assert (store / "registry.json").exists()


def test_prune_route_dry_run_changes_nothing(client, store):
    now = time.time()
    for i in range(4):
        _write(store, f"rest-{i}", [], mtime=now - i)

    body = client.post("/api/sessions/prune", json={"keep_rest": 1, "dry_run": True}).json()
    assert body["dry_run"] is True
    assert len(body["deleted"]) == 3
    # a dry run reports the state it would leave behind
    assert body["remaining"]["rest-"] == 1
    assert len(list(store.glob("rest-*.json"))) == 4


def test_prune_route_refuses_a_negative_keep(client, store):
    _write(store, "rest-a", [], mtime=time.time())
    assert client.post("/api/sessions/prune", json={"keep_rest": -1}).status_code == 422
