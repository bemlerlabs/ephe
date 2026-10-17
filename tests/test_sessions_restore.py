"""Restore-on-empty: serve mirrored pwa-* sessions back to the PWA.

The PWA keeps sessions in the browser's IndexedDB; POST /api/sessions/sync
mirrors them to the server store for search only. When the browser cache is
lost (storage eviction, fresh browser, cleared site data) the sidebar came up
empty even though every session was still on disk. GET /api/sessions/restore
closes that loop: the PWA hydrates from the server mirror when its local
cache is empty, then re-mirrors for future loads.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from server.routes.session_mirror import restore_sessions


def _write_session(tmp_path, raw_id: str, messages: list, mtime: float | None = None) -> None:
    path = tmp_path / f"pwa-{raw_id}.json"
    path.write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


async def test_restore_serves_latest_pwa_sessions(tmp_path, monkeypatch):
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    now = time.time()
    _write_session(tmp_path, "aaa", [{"role": "user", "content": "old", "timestamp": 1}], mtime=now - 100)
    _write_session(tmp_path, "bbb", [
        {"role": "user", "content": "hello", "timestamp": 2},
        {"role": "assistant", "content": "hi", "timestamp": 3},
    ], mtime=now)
    _write_session(tmp_path, "ccc", [{"role": "user", "content": "mid", "timestamp": 4}], mtime=now - 50)
    (tmp_path / "registry.json").write_text(json.dumps({
        "sessions": [
            {"id": "pwa-bbb", "title": "What can you do?", "last_active": "2026-09-11T20:01:11"},
            {"id": "pwa-aaa", "title": "Old one"},
        ],
    }), encoding="utf-8")

    res = await restore_sessions(limit=2)
    ids = [s["id"] for s in res["sessions"]]
    assert ids == ["bbb", "ccc"]  # newest first, capped
    bbb = res["sessions"][0]
    assert bbb["title"] == "What can you do?"
    assert len(bbb["messages"]) == 2
    assert bbb["messages"][0]["content"] == "hello"
    assert isinstance(bbb["updated_at"], int) and bbb["updated_at"] > 0
    # unknown-in-registry sessions restore with an empty title, not a crash
    assert res["sessions"][1]["title"] == ""


async def test_restore_empty_store(tmp_path, monkeypatch):
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    res = await restore_sessions()
    assert res == {"sessions": []}


async def test_restore_skips_non_pwa_and_invalid_ids(tmp_path, monkeypatch):
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    now = time.time()
    _write_session(tmp_path, "good", [{"role": "user", "content": "x", "timestamp": 1}], mtime=now)
    # REST-session (server-side) must never leak into the PWA mirror
    (tmp_path / "rest-live1.json").write_text(json.dumps([{"role": "user", "content": "secret"}]), encoding="utf-8")
    # invalid pwa id (dot) is refused by the same _ID_RE rule as sync
    (tmp_path / "pwa-..evil.json").write_text("[]", encoding="utf-8")
    res = await restore_sessions()
    assert [s["id"] for s in res["sessions"]] == ["good"]


async def test_restore_limit_capped(tmp_path, monkeypatch):
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    now = time.time()
    for i in range(60):
        _write_session(tmp_path, f"s{i:03d}", [], mtime=now - i)
    res = await restore_sessions(limit=999)
    assert len(res["sessions"]) <= 50
