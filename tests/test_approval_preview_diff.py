"""Wave B1: the approval dialog shows a real diff instead of raw JSON.

approval_preview_diff(name, args) builds the unified-diff preview that the
backend sends along as an optional `diff` field on the sandbox_confirm event.
Read-only and fail-soft: it never writes, returns "" for non-edit tools, for
disallowed paths and for any failure — the dialog then falls back to the
argument preview.
"""
from __future__ import annotations

import pytest

from core.tools.file_ops import approval_preview_diff


@pytest.fixture()
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "Desktop").mkdir(parents=True)
    monkeypatch.setattr("core.tools.base.Path.home", lambda: h)
    return h


class TestEditFilePreview:
    def test_produces_unified_diff_from_old_new(self, home):
        """GIVEN edit_file args WHEN previewed THEN real -/+ unified diff."""
        diff = approval_preview_diff("edit_file", {
            "path": str(home / "Desktop" / "a.txt"),
            "old_string": "alpha beta\ngamma\n",
            "new_string": "alpha BETA\ngamma\n",
        })
        assert "-alpha beta" in diff
        assert "+alpha BETA" in diff
        assert diff.startswith("---")  # file header → DiffView parses hunks

    def test_edit_preview_needs_no_disk(self, home):
        """GIVEN edit-args for a file that doesn't exist yet WHEN previewed THEN still diffs."""
        diff = approval_preview_diff("edit_file", {
            "path": str(home / "Desktop" / "ghost.txt"),
            "old_string": "one\n",
            "new_string": "two\n",
        })
        assert "-one" in diff and "+two" in diff


class TestWriteFilePreview:
    def test_diff_against_existing_content(self, home):
        """GIVEN existing file WHEN write_file previewed THEN diff old→new."""
        f = home / "Desktop" / "cfg.txt"
        f.write_text("keep\ndrop\n", encoding="utf-8")
        diff = approval_preview_diff("write_file", {
            "path": str(f),
            "content": "keep\nadd\n",
        })
        assert " drop" in diff or "-drop" in diff
        assert "+add" in diff

    def test_new_file_shows_all_additions(self, home):
        """GIVEN absent file WHEN write_file previewed THEN every line is '+'."""
        diff = approval_preview_diff("write_file", {
            "path": str(home / "Desktop" / "new.txt"),
            "content": "brand new\nsecond\n",
        })
        assert "+brand new" in diff and "+second" in diff

    def test_outside_whitelist_is_empty(self, home):
        """GIVEN disallowed path WHEN previewed THEN '' (fail-soft, no leak)."""
        diff = approval_preview_diff("write_file", {
            "path": "/etc/secret.conf",
            "content": "pwned\n",
        })
        assert diff == ""


class TestFailSoft:
    def test_unknown_tool_returns_empty(self, home):
        assert approval_preview_diff("run_shell", {"command": "ls"}) == ""

    def test_garbage_args_return_empty(self, home):
        """ANY malformed args must fail-soft to '' — never raise into the stream."""
        assert approval_preview_diff("write_file", {"path": 123}) == ""
        assert approval_preview_diff("edit_file", {}) == ""
        assert approval_preview_diff("write_file", {}) == ""

    def test_never_writes_to_disk(self, home):
        """Core guarantee: the preview is strictly read-only."""
        f = home / "Desktop" / "ro.txt"
        f.write_text("original\n", encoding="utf-8")
        approval_preview_diff("write_file", {"path": str(f), "content": "OVERWRITE\n"})
        assert f.read_text(encoding="utf-8") == "original\n"
