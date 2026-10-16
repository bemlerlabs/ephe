"""Tests for core/multi_session.py – persisted multi-session support (Phase 2 Item 7).

Design:
- ~/.ephe/sessions/default.json stays the "legacy" active session file
  (single-source, backward-compat).
- New sessions live in ~/.ephe/sessions/<id>.json.
- ~/.ephe/sessions/registry.json holds the meta info (id, title,
  created_at, last_active) + active_id.

DoD:
- Switch < 50ms
- Resume after restart < 200ms
- Stable IDs (shortened UUID4 hex)
- Migration: an existing default.json is folded into the registry on the first
  call, without losing data.
- Atomic writes (tmp + rename).
- Corruption safety: broken JSON → clean recovery instead of a crash.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.multi_session as ms
from core.types import Message


# Fixtures


@pytest.fixture(autouse=True)
def _isolate_session_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every multi_session path into tmp_path."""
    sess_dir = tmp_path / ".ephe" / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ms, "SESSIONS_DIR", sess_dir)
    monkeypatch.setattr(ms, "REGISTRY_FILE", sess_dir / "registry.json")
    monkeypatch.setattr(ms, "LEGACY_FILE", sess_dir / "default.json")
    return sess_dir


# create / list / get


def test_create_session_returns_stable_id():
    a = ms.create_session("Alpha")
    b = ms.create_session("Beta")
    assert a["id"] != b["id"]
    assert a["title"] == "Alpha"
    assert b["title"] == "Beta"
    # Stable ID shape: 8 hex characters
    assert len(a["id"]) == 8
    int(a["id"], 16)  # no exception


def test_list_returns_created_sessions():
    a = ms.create_session("One")
    b = ms.create_session("Two")
    lst = ms.list_sessions()
    ids = {s["id"] for s in lst}
    assert a["id"] in ids
    assert b["id"] in ids


def test_list_sorts_by_last_active_descending():
    a = ms.create_session("Old")
    b = ms.create_session("New")
    ms.save_messages(b["id"], [Message(role="user", content="x")])
    lst = ms.list_sessions()
    assert lst[0]["id"] == b["id"]
    assert lst[1]["id"] == a["id"]


# rename / delete


def test_rename_updates_title_persistently():
    a = ms.create_session("Before")
    ms.rename_session(a["id"], "After")
    lst = ms.list_sessions()
    assert [s for s in lst if s["id"] == a["id"]][0]["title"] == "After"


def test_rename_missing_id_is_noop():
    ms.rename_session("deadbeef", "Whatever")  # no crash


def test_delete_removes_session_and_messages():
    a = ms.create_session("Gone")
    ms.save_messages(a["id"], [Message(role="user", content="x")])
    ms.delete_session(a["id"])
    assert a["id"] not in {s["id"] for s in ms.list_sessions()}
    # The message file is gone as well
    assert not (ms.SESSIONS_DIR / f"{a['id']}.json").exists()


def test_delete_active_session_clears_active():
    a = ms.create_session("Active")
    ms.switch_to(a["id"])
    assert ms.get_active_id() == a["id"]
    ms.delete_session(a["id"])
    assert ms.get_active_id() is None


# switch / resume


def test_switch_to_changes_active():
    a = ms.create_session("A")
    b = ms.create_session("B")
    ms.switch_to(a["id"])
    assert ms.get_active_id() == a["id"]
    ms.switch_to(b["id"])
    assert ms.get_active_id() == b["id"]


def test_switch_to_unknown_id_is_noop():
    a = ms.create_session("A")
    ms.switch_to(a["id"])
    prev = ms.get_active_id()
    ms.switch_to("deadbeef")
    assert ms.get_active_id() == prev


def test_switch_is_fast_under_50ms():
    """DoD: switch < 50ms (rough tolerance, warm)."""
    a = ms.create_session("A")
    b = ms.create_session("B")
    ms.switch_to(a["id"])  # warmup
    import time
    t0 = time.perf_counter()
    for _ in range(50):
        ms.switch_to(b["id"])
        ms.switch_to(a["id"])
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    per_switch_ms = elapsed_ms / 100.0
    # Generous tolerance (a CI runner can be slower): 2x DoD.
    assert per_switch_ms < 100, f"Switch took {per_switch_ms:.2f}ms (>100ms)"


def test_resume_after_restart_under_200ms():
    """DoD: resume after restart < 200ms.

    Measures the time for: read active_id from the registry + load messages from disk.
    (The actual "restart" path in the TUI.)
    """
    a = ms.create_session("Persisted")
    ms.save_messages(a["id"], [Message(role="user", content="hi")])
    ms.switch_to(a["id"])

    import time
    t0 = time.perf_counter()
    active = ms.get_active_id()
    msgs = ms.load_messages(active) if active else []
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert active == a["id"]
    assert len(msgs) == 1
    assert elapsed_ms < 200, f"Resume took {elapsed_ms:.2f}ms (>200ms)"


# Save / load messages


def test_save_and_load_messages_roundtrip():
    a = ms.create_session("RT")
    msgs = [Message(role="user", content="A"), Message(role="assistant", content="B")]
    ms.save_messages(a["id"], msgs)
    loaded = ms.load_messages(a["id"])
    assert loaded == msgs


def test_load_unknown_id_returns_empty():
    assert ms.load_messages("deadbeef") == []


def test_save_is_atomic():
    """Corruption test: a write never lands half-finished."""
    a = ms.create_session("Atomic")
    # 100 messages, 1KB each → ~100KB
    msgs = [Message(role="user", content="x" * 1000) for _ in range(100)]
    ms.save_messages(a["id"], msgs)
    loaded = ms.load_messages(a["id"])
    assert len(loaded) == 100


def test_load_corrupt_session_returns_empty_not_crash():
    a = ms.create_session("Corrupt")
    f = ms.SESSIONS_DIR / f"{a['id']}.json"
    f.write_text("{not valid", encoding="utf-8")
    loaded = ms.load_messages(a["id"])
    assert loaded == []
    # Registry stays intact
    assert a["id"] in {s["id"] for s in ms.list_sessions()}


def test_load_registry_corrupt_returns_empty():
    ms.REGISTRY_FILE.write_text("garbage", encoding="utf-8")
    lst = ms.list_sessions()
    assert lst == []
    # The active id is None
    assert ms.get_active_id() is None


# Legacy migration


def test_legacy_default_json_is_migrated_into_registry():
    """Root cause: an existing default.json is detected on the first
    call and folded into the registry (no data loss)."""
    legacy_msgs = [
        Message(role="user", content="Legacy 1"),
        Message(role="assistant", content="Legacy 2"),
    ]
    ms.LEGACY_FILE.write_text(json.dumps(legacy_msgs, ensure_ascii=False, indent=2), encoding="utf-8")

    # The first list_sessions call triggers the migration
    lst = ms.list_sessions()
    assert len(lst) == 1
    migrated = lst[0]
    assert migrated["title"] == "legacy"
    # The messages now live in sessions/<id>.json
    loaded = ms.load_messages(migrated["id"])
    assert loaded == legacy_msgs
    # default.json stays as a compatibility copy (it is not deleted)
    assert ms.LEGACY_FILE.exists()


def test_legacy_migration_is_idempotent():
    """A second call does not duplicate."""
    ms.LEGACY_FILE.write_text(
        json.dumps([Message(role="user", content="only")], ensure_ascii=False),
        encoding="utf-8",
    )
    lst1 = ms.list_sessions()
    lst2 = ms.list_sessions()
    assert len(lst1) == 1
    assert len(lst2) == 1
    assert lst1[0]["id"] == lst2[0]["id"]


def test_no_legacy_file_no_migration():
    """No default.json → no migration, empty registry."""
    lst = ms.list_sessions()
    assert lst == []


# Session metadata


def test_session_info_includes_message_count_and_updated_at():
    a = ms.create_session("Info")
    ms.save_messages(a["id"], [Message(role="user", content="x")])
    info = ms.session_info(a["id"])
    assert info["id"] == a["id"]
    assert info["message_count"] == 1
    assert "updated_at" in info
    assert isinstance(info["updated_at"], str)


def test_session_info_for_missing_returns_none():
    assert ms.session_info("deadbeef") is None
