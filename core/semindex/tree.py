"""Lossless Semantic Tree — tree construction (T1) + edges (T2).

One node per definition (class/function/import), edges contains/references/imports.
Deterministic: identical source code → identical tree.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

#: Suffix → language of the extractor that reads it.
LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
}

SUPPORTED_SUFFIXES = frozenset(LANGUAGE_BY_SUFFIX)


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
    """Any supported source file → SemanticTree (module name from the stem)."""
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    return build_tree_from_language(source, str(p), p.stem, LANGUAGE_BY_SUFFIX.get(p.suffix.lower()))


_TS_IMPORT = re.compile(
    r"^\s*import\s+(?:type\s+)?(?:([\w$]+)\s*,?\s*)?"
    r"(?:\*\s+as\s+([\w$]+)|\{([^}]*)\})?\s*(?:from\s*)?['\"]([^'\"]+)['\"]"
)
_TS_SIDE_EFFECT_IMPORT = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]")
_TS_DECLARATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?interface\s+([\w$]+)"), "interface"),
    (re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?type\s+([\w$]+)\s*(?:<[^>]*>)?\s*="), "type"),
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([\w$]+)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([\w$]+)"), "function"),
    (re.compile(r"^\s*export\s+(?:const|let)\s+([\w$]+)"), "const"),
)
_TS_METHOD = re.compile(
    r"^\s{2,}(?:(?:public|private|protected|static|async|readonly|override|get|set)\s+)*"
    r"([\w$]+)\s*(?:<[^>]*>)?\([^)]*\)\s*(?::\s*[^{;]+?)?\s*\{"
)


def _sanitize_for_braces(line: str) -> str:
    """Drop comments and string contents so braces inside them do not count."""
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
    text = re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)
    text = re.sub(r"`(?:[^`\\]|\\.)*`", "``", text)
    return text.split("//", 1)[0]


def _block_end(lines: list[str], start_index: int) -> int:
    """1-based end line of the block that opens on `start_index`, by brace depth."""
    depth = 0
    opened = False
    in_comment = False
    for index in range(start_index, len(lines)):
        text = lines[index]
        if in_comment:
            closing = text.find("*/")
            if closing < 0:
                continue
            text = text[closing + 2:]
            in_comment = False
        opening = text.find("/*")
        if opening >= 0:
            closing = text.find("*/", opening + 2)
            text = text[:opening] + (text[closing + 2:] if closing >= 0 else "")
            in_comment = closing < 0
        cleaned = _sanitize_for_braces(text)
        delta = cleaned.count("{") - cleaned.count("}")
        if delta > 0:
            opened = True
        depth += delta
        if opened and depth <= 0:
            return index + 1
    return start_index + 1


def _add_unique(tree: SemanticTree, node: Node) -> None:
    if node.id in tree.nodes:
        node.id = f"{node.id}@{node.start}"
        node.qualname = node.id
    tree.add(node)
    parent = tree.nodes.get(node.parent or "")
    if parent is not None:
        parent.children.append(node.id)


def build_tree_from_typescript(source: str, file: str, module: str) -> SemanticTree:
    """TS/JS symbols from the declaration lines: interfaces, types, classes,
    functions, exported consts and imports, each with its block's line span."""
    tree = SemanticTree()
    lines = source.split("\n")
    tree.add(Node(id=module, kind="module", name=module, qualname=module,
                  file=file, start=1, end=len(lines)))
    containers: list[tuple[str, str, int]] = []  # (qualname, kind, end)

    for index, line in enumerate(lines):
        line_no = index + 1
        containers = [c for c in containers if c[2] >= line_no]

        side_effect = _TS_SIDE_EFFECT_IMPORT.match(line)
        if side_effect:
            name = side_effect.group(1)
            _add_unique(tree, Node(id=f"{module}.{name}", kind="import", name=name,
                                   qualname=f"{module}.{name}", file=file,
                                   start=line_no, end=line_no, parent=module))
            continue
        imported = _TS_IMPORT.match(line)
        if imported:
            default_name, namespace, named, specifier = imported.groups()
            names: list[str] = []
            if default_name:
                names.append(default_name)
            if namespace:
                names.append(namespace)
            if named:
                names.extend(part.strip().split(" as ")[-1].strip()
                             for part in named.split(",") if part.strip())
            if not names:
                names.append(specifier)
            for name in names:
                _add_unique(tree, Node(id=f"{module}.{name}", kind="import", name=name,
                                       qualname=f"{module}.{name}", file=file,
                                       start=line_no, end=line_no, parent=module))
            continue

        for pattern, kind in _TS_DECLARATIONS:
            match = pattern.match(line)
            if not match:
                continue
            name = match.group(1)
            parent = containers[-1][0] if containers else module
            node_kind = kind
            if kind == "function" and containers and containers[-1][1] == "class":
                node_kind = "method"
            qualname = f"{module}.{name}" if parent == module else f"{parent}.{name}"
            end = _block_end(lines, index)
            _add_unique(tree, Node(id=qualname, kind=node_kind, name=name, qualname=qualname,
                                   file=file, start=line_no, end=end, parent=parent))
            if kind == "class":
                containers.append((qualname, "class", end))
            break
        else:
            if containers and containers[-1][1] == "class":
                method = _TS_METHOD.match(line)
                if method:
                    name = method.group(1)
                    parent = containers[-1][0]
                    end = _block_end(lines, index)
                    qualname = f"{parent}.{name}"
                    _add_unique(tree, Node(id=qualname, kind="method", name=name,
                                           qualname=qualname, file=file, start=line_no,
                                           end=end, parent=parent))
    return tree


_RS_FN = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?fn\s+([\w]+)"
)
_RS_DECLARATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([\w]+)"), "struct"),
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([\w]+)"), "enum"),
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+([\w]+)"), "trait"),
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([\w]+)"), "mod"),
)
_RS_IMPL = re.compile(r"^\s*impl(?:<[^>]*>)?\s+(?:[\w:<>]+\s+for\s+)?([\w:]+)")
_RS_USE = re.compile(r"^\s*(?:pub\s+)?use\s+([^;]+);")


def build_tree_from_rust(source: str, file: str, module: str) -> SemanticTree:
    """Rust items (struct/enum/trait/fn/impl/mod/use); fns inside an impl are
    methods of that impl."""
    tree = SemanticTree()
    lines = source.split("\n")
    tree.add(Node(id=module, kind="module", name=module, qualname=module,
                  file=file, start=1, end=len(lines)))
    containers: list[tuple[str, str, int]] = []

    for index, line in enumerate(lines):
        line_no = index + 1
        containers = [c for c in containers if c[2] >= line_no]

        used = _RS_USE.match(line)
        if used:
            for part in used.group(1).split(","):
                name = part.strip().split("::")[-1].strip()
                if not name:
                    continue
                _add_unique(tree, Node(id=f"{module}.{name}", kind="import", name=name,
                                       qualname=f"{module}.{name}", file=file,
                                       start=line_no, end=line_no, parent=module))
            continue

        impl = _RS_IMPL.match(line)
        if impl:
            name = impl.group(1)
            end = _block_end(lines, index)
            _add_unique(tree, Node(id=f"{module}.{name}", kind="impl", name=name,
                                   qualname=f"{module}.{name}", file=file,
                                   start=line_no, end=end, parent=module))
            containers.append((f"{module}.{name}", "impl", end))
            continue

        fn = _RS_FN.match(line)
        if fn:
            name = fn.group(1)
            parent = containers[-1][0] if containers else module
            kind = "method" if containers and containers[-1][1] == "impl" else "function"
            qualname = f"{parent}.{name}" if parent != module else f"{module}.{name}"
            _add_unique(tree, Node(id=qualname, kind=kind, name=name, qualname=qualname,
                                   file=file, start=line_no, end=_block_end(lines, index),
                                   parent=parent))
            continue

        for pattern, kind in _RS_DECLARATIONS:
            match = pattern.match(line)
            if not match:
                continue
            name = match.group(1)
            qualname = f"{module}.{name}"
            _add_unique(tree, Node(id=qualname, kind=kind, name=name, qualname=qualname,
                                   file=file, start=line_no, end=_block_end(lines, index),
                                   parent=module))
            break
    return tree


def build_tree_from_language(source: str, file: str, module: str,
                             language: str | None) -> SemanticTree:
    """Dispatch to the extractor of `language`; unknown languages yield an empty tree."""
    if language == "python":
        return build_tree_from_source(source, file, module)
    if language in {"typescript", "tsx", "javascript"}:
        return build_tree_from_typescript(source, file, module)
    if language == "rust":
        return build_tree_from_rust(source, file, module)
    tree = SemanticTree()
    tree.add(Node(id=module, kind="module", name=module, qualname=module,
                  file=file, start=1, end=source.count("\n") + 1))
    return tree
