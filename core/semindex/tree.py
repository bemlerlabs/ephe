"""Lossless Semantic Tree — tree construction (T1) + edges (T2).

One node per definition (class/function/import), edges contains/references/imports.
Deterministic: identical source code → identical tree.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Node:
    """A syntax node in the tree."""

    id: str                    # unique ID (qualname)
    kind: str                  # class | function | method | import | module
    name: str                  # short name
    qualname: str              # dot-qualified path (module.Class.method)
    file: str                  # file path
    start: int                 # first line (1-based)
    end: int                   # last line
    parent: str | None = None  # ID of the parent node
    children: list[str] = field(default_factory=list)  # IDs of the children
    refs: list[str] = field(default_factory=list)       # referenced names


class SemanticTree:
    """In-memory tree with a lookup index."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}

    def add(self, node: Node) -> None:
        self.nodes[node.id] = node

    def get_node(self, qualname: str) -> Node | None:
        return self.nodes.get(qualname)

    def children_of(self, node_id: str) -> list[Node]:
        n = self.nodes.get(node_id)
        if n is None:
            return []
        return [self.nodes[c] for c in n.children if c in self.nodes]

    def refs_of(self, node_id: str) -> list[str]:
        n = self.nodes.get(node_id)
        return list(n.refs) if n is not None else []

    def symbols_in(self, file: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.file == file]

    def nearest_def(self, file: str, line: int) -> Node | None:
        """Deepest node in the file that encloses the line."""
        best: Node | None = None
        for n in self.nodes.values():
            if n.file != file or n.kind == "module":
                continue
            if n.start <= line <= n.end:
                if best is None or (n.end - n.start) < (best.end - best.start):
                    best = n
        return best


def _line(node: ast.AST) -> int:
    return getattr(node, "lineno", 0) or 0


def _end(node: ast.AST) -> int:
    return getattr(node, "end_lineno", None) or getattr(node, "lineno", 0) or 0


def _collect_refs(body_node: ast.AST) -> list[str]:
    """Names from the body (usage), for the references edges."""
    out: list[str] = []
    for sub in ast.walk(body_node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            if sub.id not in out:
                out.append(sub.id)
    return out


def build_tree_from_source(source: str, file: str, module: str) -> SemanticTree:
    """AST → SemanticTree. Deterministic, lossless per definition."""
    tree = SemanticTree()
    try:
        parsed = ast.parse(source)
    except SyntaxError:
        return tree

    total = source.count("\n") + 1
    tree.add(Node(id=module, kind="module", name=module.rsplit(".", 1)[-1],
                  qualname=module, file=file, start=1, end=total))

    def walk(nodes: list[ast.AST], prefix: str, parent_id: str) -> None:
        for n in nodes:
            if isinstance(n, ast.ClassDef):
                q = f"{prefix}.{n.name}"
                node = Node(id=q, kind="class", name=n.name, qualname=q,
                            file=file, start=_line(n), end=_end(n),
                            parent=parent_id, refs=_collect_refs(n))
                tree.add(node)
                tree.nodes[parent_id].children.append(q)
                walk(n.body, q, q)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if "." in prefix and prefix != module else "function"
                q = f"{prefix}.{n.name}"
                node = Node(id=q, kind=kind, name=n.name, qualname=q,
                            file=file, start=_line(n), end=_end(n),
                            parent=parent_id, refs=_collect_refs(n))
                tree.add(node)
                tree.nodes[parent_id].children.append(q)
                walk(n.body, q, q)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    q = f"{prefix}.{a.name}"
                    tree.add(Node(id=q, kind="import", name=a.name, qualname=q,
                                  file=file, start=_line(n), end=_end(n),
                                  parent=parent_id))
                    tree.nodes[parent_id].children.append(q)
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    q = f"{prefix}.{a.name}"
                    tree.add(Node(id=q, kind="import", name=a.name, qualname=q,
                                  file=file, start=_line(n), end=_end(n),
                                  parent=parent_id))
                    tree.nodes[parent_id].children.append(q)

    walk(parsed.body, module, module)
    return tree


def build_tree_for_file(path: str | Path) -> SemanticTree:
    """A .py file → SemanticTree (module name derived from the path)."""
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    module = p.stem
    return build_tree_from_source(source, str(p), module)
