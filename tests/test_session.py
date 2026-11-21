"""
Tests for core/session.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.session import (
    delete_session,
    load_last_session,
    save_session,
    session_info,
    was_session_corrupt,
)
from core.types import Message


# Basic save / load


def test_session_save_and_load(tmp_session_dir: Path, sample_messages: list[Message]):
    save_session(sample_messages)
    loaded = load_last_session()
    assert loaded == sample_messages


def test_load_nonexistent_returns_empty(tmp_session_dir: Path):
    loaded = load_last_session()
    assert loaded == []


def test_load_empty_file_returns_empty(tmp_session_dir: Path):
    import core.session as sm

    sm.SESSION_FILE.write_text("", encoding="utf-8")
    loaded = load_last_session()
    assert loaded == []


def test_load_corrupt_json_returns_empty(tmp_session_dir: Path):
    import core.session as sm

    sm.SESSION_FILE.write_text("{not valid json at all}", encoding="utf-8")
    loaded = load_last_session()
    assert loaded == []


def test_load_wrong_format_returns_empty(tmp_session_dir: Path):
    import core.session as sm

    import json

    sm.SESSION_FILE.write_text(json.dumps({"key": "not a list"}), encoding="utf-8")
    loaded = load_last_session()
    assert loaded == []


def test_save_creates_directory_if_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import core.session as sm

    new_dir = tmp_path / "deep" / "nested" / "sessions"
    monkeypatch.setattr(sm, "SESSION_DIR", new_dir)
    monkeypatch.setattr(sm, "SESSION_FILE", new_dir / "default.json")

    save_session([Message(role="user", content="hi")])
    assert (new_dir / "default.json").exists()


# Atomic write


def test_no_tmp_file_left_after_save(tmp_session_dir: Path, sample_messages: list[Message]):
    save_session(sample_messages)
    # No .tmp_ files should remain
    leftover = list(tmp_session_dir.glob(".tmp_*.json"))
    assert leftover == []


def test_session_file_created_atomically(tmp_session_dir: Path, sample_messages: list[Message]):
    save_session(sample_messages)
    import core.session as sm

    assert sm.SESSION_FILE.exists()
    assert sm.SESSION_FILE.stat().st_size > 0


# Delete


def test_delete_session(tmp_session_dir: Path, sample_messages: list[Message]):
    save_session(sample_messages)
    delete_session()
    assert load_last_session() == []


def test_delete_nonexistent_is_safe(tmp_session_dir: Path):
    delete_session()  # should not raise


# session_info


def test_session_info_empty(tmp_session_dir: Path):
    count, when = session_info()
    assert count == 0
    assert when == ""


def test_session_info_with_messages(tmp_session_dir: Path, sample_messages: list[Message]):
    save_session(sample_messages)
    count, when = session_info()
    assert count == len(sample_messages)
    assert isinstance(when, str)


# Corruption detection


def test_was_session_corrupt_false_when_no_file(tmp_session_dir: Path):
    assert was_session_corrupt() is False


def test_was_session_corrupt_false_when_valid(
    tmp_session_dir: Path, sample_messages: list[Message]
):
    save_session(sample_messages)
    assert was_session_corrupt() is False


def test_was_session_corrupt_true_when_invalid(tmp_session_dir: Path):
    import core.session as sm

    sm.SESSION_FILE.write_text("{ invalid }", encoding="utf-8")
    assert was_session_corrupt() is True


# Restore session (integration)


def test_restore_session_roundtrip(tmp_session_dir: Path):
    """Full roundtrip: save → delete instance → reload."""
    msgs: list[Message] = [
        Message(role="user", content="Hallo Schwarzwald"),
        Message(role="assistant", content="Grüß Gott!"),
    ]
    save_session(msgs)
    reloaded = load_last_session()
    assert reloaded[0]["content"] == "Hallo Schwarzwald"
    assert reloaded[1]["role"] == "assistant"
