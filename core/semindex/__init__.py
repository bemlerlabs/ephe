"""Ephe – Lossless Semantic Tree (semindex).

AST-lossless syntax tree used as a project index. Nodes = symbols
(classes/functions/imports), edges = contains/references/imports.
Retrieval walks the tree (exact, deterministic), not vector embeddings.
"Lossless" = the tree loses no definition/relationship.
"""
from __future__ import annotations

from core.semindex.tree import (
    Node,
    SemanticTree,
    build_tree_from_source,
    build_tree_for_file,
)
from core.semindex.store import SemanticStore
from core.semindex.retrieval import semantic_tree_search

__all__ = [
    "Node",
    "SemanticTree",
    "SemanticStore",
    "semantic_tree_search",
    "build_tree_from_source",
    "build_tree_for_file",
]
