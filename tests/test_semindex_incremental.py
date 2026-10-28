"""QD-013: a write refreshes its own file in the index and nothing else."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.semindex.store import SemanticStore, index_database, reindex_single_file


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.py").write_text("def one():\n    return 1\n", encoding="utf-8")
    (root / "b.py").write_text("def two():\n    return 2\n", encoding="utf-8")
    return root


def _store(root: Path) -> SemanticStore:
    database = index_database(root)
    database.parent.mkdir(parents=True, exist_ok=True)
    store = SemanticStore(database)
    store.index_workspace(root)
    return store


def _nodes(store: SemanticStore, path: Path) -> int:
    row = store.conn.execute(
        "SELECT COUNT(*) FROM semindex_nodes WHERE file = ?", (str(path.resolve()),)
    ).fetchone()
    return int(row[0]) if row else 0


def test_a_write_updates_that_file_and_leaves_the_rest_alone(workspace: Path) -> None:
    store = _store(workspace)
    try:
        a_before = _nodes(store, workspace / "a.py")
        other_before = _nodes(store, workspace / "b.py")
        assert a_before >= 1

        (workspace / "a.py").write_text(
            "def one():\n    return 1\n\ndef three():\n    return 3\n", encoding="utf-8"
        )
        written = reindex_single_file(store, workspace, workspace / "a.py")

        assert written == a_before + 1
        assert _nodes(store, workspace / "a.py") == a_before + 1
        # The untouched file kept its rows: this is not a full re-index.
        assert _nodes(store, workspace / "b.py") == other_before
    finally:
        store.close()


def test_an_unchanged_file_costs_no_rewrite(workspace: Path) -> None:
    store = _store(workspace)
    try:
        before = _nodes(store, workspace / "a.py")
        assert reindex_single_file(store, workspace, workspace / "a.py") == before
        assert _nodes(store, workspace / "a.py") == before
    finally:
        store.close()


def test_a_path_outside_the_workspace_is_never_indexed(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("def secret():\n    return 0\n", encoding="utf-8")
    store = _store(workspace)
    try:
        assert reindex_single_file(store, workspace, outside) == 0
        assert _nodes(store, outside) == 0
    finally:
        store.close()


def test_a_relative_path_resolves_against_the_workspace(workspace: Path) -> None:
    store = _store(workspace)
    try:
        (workspace / "c.py").write_text("def four():\n    return 4\n", encoding="utf-8")
        nodes = reindex_single_file(store, workspace, Path("c.py"))
        assert nodes >= 1
        assert _nodes(store, workspace / "c.py") == nodes
    finally:
        store.close()
