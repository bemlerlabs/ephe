"""Ephe – Lossless Semantic Tree (semindex).

AST-lossless syntax tree used as a project index. Nodes = symbols
(classes/functions/imports), edges = contains/references/imports.
Retrieval walks the tree (exact, deterministic), not vector embeddings.
"Lossless" = the tree loses no definition/relationship.
"""
from __future__ import annotations

from core.semindex.tree import (
    LANGUAGE_BY_SUFFIX,
    SUPPORTED_SUFFIXES,
    Node,
    SemanticTree,
    build_tree_from_language,
    build_tree_from_source,
    build_tree_for_file,
)
from core.semindex.store import (
    IndexResult,
    SemanticStore,
    index_database,
    index_workspace,
    iter_source_files,
)
from core.semindex.project_map import build_project_map, project_map_for_workspace
from core.semindex.retrieval import semantic_tree_search

__all__ = [
    "IndexResult",
    "LANGUAGE_BY_SUFFIX",
    "Node",
    "SUPPORTED_SUFFIXES",
    "SemanticStore",
    "SemanticTree",
    "build_project_map",
    "build_tree_from_language",
    "build_tree_from_source",
    "build_tree_for_file",
    "index_database",
    "index_workspace",
    "iter_source_files",
    "project_map_for_workspace",
    "semantic_tree_search",
]
