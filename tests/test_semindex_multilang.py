"""Multi-language extraction, ignore rules, incremental reindex, map and tool."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from core.semindex.project_map import build_project_map
from core.semindex.store import (
    SemanticStore,
    index_database,
    index_workspace,
    iter_source_files,
)
from core.semindex.tree import build_tree_for_file, build_tree_from_language

TYPESCRIPT_SOURCE = """\
import { readFile } from 'node:fs'
import './polyfill'

export interface Widget {
  id: string
}

export type WidgetKind = 'a' | 'b'

export class WidgetStore {
  private items: Widget[] = []

  add(item: Widget): void {
    this.items.push(item)
  }
}

export function makeWidget(id: string): Widget {
  return { id }
}

export const DEFAULT_KIND = 'a'
"""

RUST_SOURCE = """\
use std::collections::HashMap;

pub struct Engine {
    name: String,
}

pub enum Mode {
    Fast,
}

pub trait Runnable {
    fn run(&self);
}

impl Engine {
    pub fn render(&self) -> String {
        self.name.clone()
    }
}

pub fn boot() -> Engine {
    Engine { name: String::from("x") }
}
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    _write(tmp_path / "src" / "index.ts", TYPESCRIPT_SOURCE)
    _write(tmp_path / "src" / "main.rs", RUST_SOURCE)
    _write(tmp_path / "pkg" / "mod.py", "class Service:\n    def run(self):\n        return 1\n")
    _write(tmp_path / "node_modules" / "dep" / "index.js", "export const dep = 1\n")
    _write(tmp_path / "target" / "build.rs", "fn generated() {}\n")
    _write(tmp_path / "dist" / "bundle.js", "export const bundled = 1\n")
    _write(tmp_path / ".venv" / "lib" / "site.py", "def hidden():\n    pass\n")
    _write(tmp_path / "generated" / "out.js", "export const skip = 1\n")
    _write(tmp_path / ".epheignore", "generated/\n")
    return tmp_path


def test_typescript_symbols_and_spans(tmp_path: Path) -> None:
    path = _write(tmp_path / "widget.ts", TYPESCRIPT_SOURCE)
    tree = build_tree_for_file(path)
    kinds = {name: node.kind for name, node in tree.nodes.items()}

    assert kinds["widget.Widget"] == "interface"
    assert kinds["widget.WidgetKind"] == "type"
    assert kinds["widget.WidgetStore"] == "class"
    assert kinds["widget.WidgetStore.add"] == "method"
    assert kinds["widget.makeWidget"] == "function"
    assert kinds["widget.DEFAULT_KIND"] == "const"
    assert kinds["widget.readFile"] == "import"
    assert kinds["widget../polyfill"] == "import"

    interface = tree.nodes["widget.Widget"]
    assert interface.start == 4
    assert interface.end == 6
    method = tree.nodes["widget.WidgetStore.add"]
    assert method.start == 13
    assert method.end == 15


def test_rust_symbols_and_impl_methods(tmp_path: Path) -> None:
    path = _write(tmp_path / "engine.rs", RUST_SOURCE)
    tree = build_tree_for_file(path)
    kinds = {name: node.kind for name, node in tree.nodes.items()}

    assert kinds["engine.Engine"] == "struct"
    assert kinds["engine.Mode"] == "enum"
    assert kinds["engine.Runnable"] == "trait"
    assert kinds["engine.Engine"] == "struct"
    assert kinds["engine.Engine.render"] == "method"
    assert kinds["engine.boot"] == "function"
    assert kinds["engine.HashMap"] == "import"
    assert tree.nodes["engine.Engine"].end == 5


def test_python_extractor_still_used() -> None:
    tree = build_tree_from_language(
        "class A:\n    def f(self):\n        return 1\n", "a.py", "a", "python"
    )
    assert tree.nodes["a.A"].kind == "class"
    assert tree.nodes["a.A.f"].kind == "method"


def test_workspace_index_skips_generated_trees(workspace: Path) -> None:
    result = index_workspace(workspace)
    indexed = {Path(row[0]).name for row in _files(workspace)}

    assert {"index.ts", "main.rs", "mod.py"} <= indexed
    assert "bundle.js" not in indexed
    assert "site.py" not in indexed
    assert "out.js" not in indexed
    assert result.files == 3
    assert result.symbols > 0
    assert (workspace / ".ephe" / "index.db").exists()


def _files(root: Path) -> list[tuple[str]]:
    store = SemanticStore(index_database(root))
    try:
        return store.conn.execute("SELECT file FROM semindex_files").fetchall()
    finally:
        store.close()


def test_reindex_is_incremental_and_updates_symbols(workspace: Path) -> None:
    first = index_workspace(workspace)
    again = index_workspace(workspace)
    assert again.symbols == first.symbols

    service = workspace / "pkg" / "mod.py"
    service.write_text(
        service.read_text(encoding="utf-8") + "\ndef extra():\n    return 2\n",
        encoding="utf-8",
    )
    os.utime(service, (service.stat().st_atime, service.stat().st_mtime + 5))
    third = index_workspace(workspace)
    assert third.symbols == first.symbols + 1


def test_project_map_names_languages_entrypoints_and_types(workspace: Path) -> None:
    index_workspace(workspace)
    store = SemanticStore(index_database(workspace))
    try:
        text = build_project_map(store, workspace)
    finally:
        store.close()

    assert "languages: python 1, rust 1, typescript 1" in text
    assert "src/index.ts" in text
    assert "src/main.rs" in text
    assert "WidgetStore (class)" in text
    assert "query_codebase" in text


def test_search_filters_by_kind(workspace: Path) -> None:
    index_workspace(workspace)
    store = SemanticStore(index_database(workspace))
    try:
        hits = store.search("Widget", kind="interface")
        assert [hit["name"] for hit in hits] == ["Widget"]
        assert store.search("Widget", kind="struct") == []
    finally:
        store.close()


def test_query_codebase_tool_reads_the_workspace(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.tools.codebase_tools import query_codebase

    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    index_workspace(workspace)

    answer = asyncio.run(query_codebase("WidgetStore", kind="class"))
    assert "class src.index.WidgetStore" in answer
    assert "src/index.ts" in answer
    assert "class WidgetStore" in answer

    missing = asyncio.run(query_codebase("NoSuchSymbol"))
    assert "no symbol or file matches" in missing


def test_index_routes_report_progress_and_search(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server.routes import project

    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    project._jobs.clear()

    started = asyncio.run(project.start_index(project.IndexRequest()))
    assert started["state"] == "indexing"

    async def _wait() -> dict:
        for _ in range(200):
            status = await project.index_status()
            if status["state"] != "indexing":
                return status
            await asyncio.sleep(0.02)
        raise AssertionError("index job did not finish")

    finished = asyncio.run(_wait())
    assert finished["state"] == "ready"
    assert finished["files"] == 3
    assert finished["indexed"] == finished["total"] == 3
    assert finished["symbols"] > 0

    found = asyncio.run(project.search_index(project.SearchRequest(query="Engine")))
    assert found["status"] == "ready"
    assert any(hit["name"] == "Engine" for hit in found["hits"])


def test_index_request_names_no_path() -> None:
    from server.routes import project

    assert "path" not in project.IndexRequest.model_fields


def test_iter_source_files_is_stable(workspace: Path) -> None:
    first = [p.relative_to(workspace).as_posix() for p in iter_source_files(workspace)]
    second = [p.relative_to(workspace).as_posix() for p in iter_source_files(workspace)]
    assert first == second == ["pkg/mod.py", "src/index.ts", "src/main.rs"]


def test_status_is_idle_before_the_first_index(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server.routes import project

    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    project._jobs.clear()
    status = asyncio.run(project.index_status())
    assert status["state"] == "idle"
    assert status["files"] == 0 and status["symbols"] == 0


def test_search_before_the_first_index_says_so(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server.routes import project

    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    found = asyncio.run(project.search_index(project.SearchRequest(query="Widget")))
    assert found["status"] == "not_indexed"
    assert found["hits"] == []


def test_search_carries_the_relative_path_and_source(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server.routes import project

    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    index_workspace(workspace)
    found = asyncio.run(project.search_index(project.SearchRequest(query="WidgetStore")))
    hit = next(entry for entry in found["hits"] if entry["name"] == "WidgetStore")
    assert hit["relative"] == "src/index.ts"
    assert "class WidgetStore" in hit["source"]


def test_status_from_disk_carries_language_and_kind_counts(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server.routes import project

    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    project._jobs.clear()
    index_workspace(workspace)
    status = asyncio.run(project.index_status())
    assert status["state"] == "ready"
    assert status["languages"]["typescript"] == 1
    assert status["kinds"]["class"] >= 1
