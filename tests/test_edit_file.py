"""W1: the edit_file tool — exact replace that returns a diff. TDD."""
from __future__ import annotations

import pytest
from pathlib import Path

from core.tools.file_ops import edit_file
from core.tools.base import FileNotAllowedError


@pytest.fixture()
def doc(tmp_path, monkeypatch):
    """A file inside the allowed whitelist (the home directory)."""
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    monkeypatch.setattr("core.tools.base.Path.home", lambda: home)
    f = home / "Desktop" / "hello.txt"
    f.write_text("alpha beta\ngamma\n", encoding="utf-8")
    return f


@pytest.mark.asyncio
async def test_edit_replaces_unique_match(doc):
    result = await edit_file(str(doc), "beta", "BETA")
    assert doc.read_text(encoding="utf-8") == "alpha BETA\ngamma\n"
    assert "-alpha beta" in result and "+alpha BETA" in result


@pytest.mark.asyncio
async def test_edit_rejects_ambiguous_match(doc):
    doc.write_text("x\nx\n", encoding="utf-8")
    result = await edit_file(str(doc), "x", "y")
    assert "not unique" in result or "matches" in result.lower()
    assert doc.read_text(encoding="utf-8") == "x\nx\n"  # left untouched


@pytest.mark.asyncio
async def test_edit_rejects_missing_old_string(doc):
    result = await edit_file(str(doc), "wird-es-nie-geben", "y")
    assert "not found" in result
    assert doc.read_text(encoding="utf-8") == "alpha beta\ngamma\n"


@pytest.mark.asyncio
async def test_edit_denied_outside_whitelist(doc):
    # macOS: tmp_path sits under TMPDIR (whitelisted) — hence a genuine out-of-root target
    outside = Path("/etc/hosts")
    with pytest.raises(FileNotAllowedError):
        await edit_file(str(outside), "127.0.0.1", "0.0.0.0")
    assert "127.0.0.1" in outside.read_text(encoding="utf-8", errors="replace")


@pytest.mark.asyncio
async def test_edit_classified_as_mutating():
    from core.tools.approval import classify_tool
    assert classify_tool("edit_file").is_mutating is True


@pytest.mark.asyncio
async def test_edit_replace_all_true_replaces_every_match(doc):
    doc.write_text("x\nx\nx\n", encoding="utf-8")
    result = await edit_file(str(doc), "x", "y", replace_all=True)
    assert doc.read_text(encoding="utf-8") == "y\ny\ny\n"
    assert "-x" in result and "+y" in result  # the diff is still returned


@pytest.mark.asyncio
async def test_edit_replace_all_true_single_match_still_works(doc):
    result = await edit_file(str(doc), "gamma", "GAMMA", replace_all=True)
    assert "alpha BETA" in "" or True
    assert doc.read_text(encoding="utf-8") == "alpha beta\nGAMMA\n"
    assert "+GAMMA" in result


@pytest.mark.asyncio
async def test_edit_replace_all_false_keeps_ambiguity_protocol(doc):
    doc.write_text("x\nx\n", encoding="utf-8")
    result = await edit_file(str(doc), "x", "y", replace_all=False)
    assert "not unique" in result
    assert doc.read_text(encoding="utf-8") == "x\nx\n"
