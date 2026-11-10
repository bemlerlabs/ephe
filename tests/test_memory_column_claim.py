"""What the memory docstring claims, measured on the store this process opens.

The live store is Kepta. A kind lands in the type column. A correction writes
superseded_by and valid_to. The chromadb pin is the retired importer command.
This process does not open that store, so the columns are not a no-op pass-through
on the path that runs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    from core.memory import Memory

    Memory.reset_scoped_instances()
    yield tmp_path
    Memory.reset_scoped_instances()


def test_the_names_stay_and_the_pass_through_sentence_is_gone():
    source = (ROOT / "core" / "tools" / "state_tools.py").read_text(encoding="utf-8")
    provider = (ROOT / "core" / "memory_provider.py").read_text(encoding="utf-8")
    from core.tools.state_tools import memory

    assert "Kepta" in (memory.__doc__ or "")
    assert "chromadb==1.5.9" in (memory.__doc__ or "")
    assert "Chroma" in (memory.__doc__ or "")
    assert "pass through without effect" not in source
    assert "in the same id" not in source
    assert "import chromadb" not in provider
    from core.memory_provider import IMPORT_COMMAND, VALID_PROVIDERS

    assert "chromadb==1.5.9" in IMPORT_COMMAND
    assert VALID_PROVIDERS == ("kepta", "kepta-bridge")


def test_the_live_store_writes_the_columns(cfg):
    """A procedural add writes the type column. A correction writes the descent columns."""
    from core.memory import Memory
    from core.tools.state_tools import memory

    asyncio.run(memory(
        action="add", target="memory",
        content="Write the column, then read it back",
        memory_type="procedural",
    ))
    mem = Memory()
    leading = mem.list_all()[0]
    assert leading["metadata"]["type"] == "procedural"

    asyncio.run(memory(
        action="replace", target="memory",
        old_text="Write the column",
        content="The correction is its own row",
        supersedes=leading["id"],
    ))
    row = mem._provider._db.execute(
        "SELECT superseded_by, valid_to FROM memories WHERE id = ?",
        (leading["id"],),
    ).fetchone()
    assert row["superseded_by"]
    assert row["valid_to"]
