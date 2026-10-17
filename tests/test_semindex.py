"""Tests for core/semindex — the Lossless Semantic Tree (T1–T5)."""
from __future__ import annotations

import pytest

from core.semindex import (
    Node,
    SemanticTree,
    SemanticStore,
    semantic_tree_search,
    build_tree_from_source,
    build_tree_for_file,
)

SRC = '''
import os
from typing import Any

class Alpha:
    def one(self) -> int:
        return os.sep

def top(x: Any) -> Any:
    return x
'''


def test_t1_knoten_und_kanten():
    t = build_tree_from_source(SRC, "m.py", "m")
    assert isinstance(t, SemanticTree)
    assert t.get_node("m.Alpha") is not None
    assert t.get_node("m.Alpha.one") is not None
    assert t.get_node("m.top") is not None
    # contains-Kante: modul → Alpha
    assert "m.Alpha" in t.get_node("m").children


def test_t2_refs_kante():
    t = build_tree_from_source(SRC, "m.py", "m")
    one = t.get_node("m.Alpha.one")
    assert "os" in one.refs


def test_t3_nearest_def():
    t = build_tree_from_source(SRC, "m.py", "m")
    # the line of the return statement inside top() → top
    line = next(i for i, ln in enumerate(SRC.split("\n"), 1) if "return x" in ln)
    nd = t.nearest_def("m.py", line)
    assert nd is not None and nd.qualname == "m.top"


def test_t3_store_lookup(tmp_path):
    st = SemanticStore(tmp_path / "db.sqlite")
    try:
        n = st.index_file("core/ephemeral_cell.py")
        assert n > 0
        assert st.get_node("ephemeral_cell.create_cell")["kind"] == "function"
        assert len(st.children_of("ephemeral_cell")) > 0
        assert len(st.symbols_in("core/ephemeral_cell.py")) == n
        assert st.nearest_def("core/ephemeral_cell.py", 105)["qualname"] == "ephemeral_cell.create_cell"
    finally:
        st.close()


def test_t4_retrieval(tmp_path):
    st = SemanticStore(tmp_path / "db.sqlite")
    try:
        st.index_file("core/ephemeral_cell.py")
        hits = semantic_tree_search(st, "create_cell")
        assert hits and hits[0]["qualname"] == "ephemeral_cell.create_cell"
        assert len(hits[0]["source"]) > 0
    finally:
        st.close()


def test_t5_inkrementell_cached(tmp_path):
    st = SemanticStore(tmp_path / "db.sqlite")
    try:
        n1 = st.index_file("core/ephemeral_cell.py")
        n2 = st.index_file("core/ephemeral_cell.py")  # cached, no re-parse
        assert n1 == n2
    finally:
        st.close()


def test_lossless_deterministisch():
    """Identical source → identical tree (lossless/deterministic)."""
    a = build_tree_from_source(SRC, "m.py", "m")
    b = build_tree_from_source(SRC, "m.py", "m")
    assert sorted(a.nodes) == sorted(b.nodes)
    for k in a.nodes:
        assert a.nodes[k].start == b.nodes[k].start
        assert a.nodes[k].end == b.nodes[k].end


def test_syntaxfehler_fail_sanity():
    t = build_tree_from_source("def broken(:\n", "b.py", "b")
    assert isinstance(t, SemanticTree)
