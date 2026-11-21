"""The promises a version 2 tool declaration makes, read against the bundle that ships.

scripts/plugin_dod_tools.py

`core/plugin_tools_contract.py` decides what a `components.tools` entry may say: its
fields, its name charset, the containment of its path, the length of the name it derives.
The questions below are the ones a text read of a declaration cannot answer, and they are
asked here because nothing else in the tree is placed to ask them — the entry file has to
ship, the callable has to be bound in it, the family has to be one the manifest itself
asks permission for, and one served name has to carry one declaration.

`tool_claims` answers "what does this bundle contribute" for this gate and for
`core.plugin_registry.scan_tool_activations` together, and `declared_families` spells the
permission question once for both validation and here. Nothing re-reads `components.tools`
for meaning; only its length is counted, so a declaration the contract cannot read is
named instead of silently contributing nothing.

The file the entry names is checked from the text the manifest spelled
(`ToolClaim.declared`), which is the only form that still says where the extension sits.
`core/sandbox/runner.resolve_entry_file` maps the same dotted entry back onto that path
when a call arrives, so the byte demanded here is the byte the worker will read.

The callable is a syntactic read, because ruling A1 keeps this process from importing a
plugin: `ast` over the shipped text, where a `def`, a `class`, a module-level binding or a
re-exported import answers yes. A name bound only inside a function body answers no, since
that is not where the worker's `getattr` looks.

A collision inside one bundle is a tie the mount cannot break, and the gate refuses it
while the author can still fix it. Across bundles the scan owns it, and the mount carries
it (#15).
"""
from __future__ import annotations

import ast
from pathlib import Path

from core.plugin_manifest import _under
from core.plugin_tools_contract import ToolClaim, declared_families, tool_claims

_MODULE_SUFFIX = ".py"

#: Statements that can still bind a name at module scope: a branch runs in the module's
#: namespace, while the body of a `def` or `class` never does.
_BRANCHES = (
    ast.If,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
)


def tool_problems(plugin_dir: Path, manifest: dict) -> list[str]:
    """What one bundle's tool declarations promise, as lines for the DoD problem list."""
    claims = tool_claims(manifest)
    problems = _unread_problems(manifest, claims)
    families = declared_families(manifest)
    served: dict[str, list[str]] = {}
    for claim in claims:
        if not claim.contributed:
            continue
        served.setdefault(claim.name, []).append(claim.suffix)
        if claim.family not in families:
            problems.append(
                f"tool {claim.suffix!r}: family {claim.family!r} is outside the "
                "manifest's declared tool families"
            )
        problems.extend(_entry_problems(plugin_dir, claim))
    problems.extend(
        f"duplicate tool name {suffixes[0]!r}: {len(suffixes)} declarations serve {name!r}"
        for name, suffixes in served.items()
        if len(suffixes) > 1
    )
    return problems


def _unread_problems(manifest: dict, claims: tuple[ToolClaim, ...]) -> list[str]:
    """A declaration the contract reads as no claim is a promise no runtime can keep."""
    components = manifest.get("components")
    listed = components.get("tools") if isinstance(components, dict) else None
    count = len(listed) if isinstance(listed, list) else 0
    if count == len(claims):
        return []
    return [f"components.tools: {count} declared, {len(claims)} claims read"]


def _entry_problems(plugin_dir: Path, claim: ToolClaim) -> list[str]:
    """The file the entry names ships inside the bundle, and binds the callable."""
    path_part, sep, callable_name = claim.declared.rpartition(":")
    if not sep or not path_part or not callable_name.isidentifier():
        return [f"tool {claim.suffix!r}: entry {claim.declared!r} names no module:callable"]
    if not path_part.lower().endswith(_MODULE_SUFFIX):
        return [f"tool {claim.suffix!r}: entry {claim.declared!r} is not a {_MODULE_SUFFIX} file"]
    target = _under(plugin_dir, *path_part.split("/"))
    if target is None:
        return [
            f"tool {claim.suffix!r}: entry {claim.declared!r} resolves outside the "
            "plugin directory"
        ]
    if not target.is_file():
        return [f"tool {claim.suffix!r}: entry file {path_part!r} does not ship"]
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        reason = exc.msg if isinstance(exc, SyntaxError) else exc.__class__.__name__
        return [f"tool {claim.suffix!r}: entry file {path_part!r} is unreadable ({reason})"]
    if _declares_callable(tree, callable_name):
        return []
    return [f"tool {claim.suffix!r}: {callable_name!r} is not bound in {path_part!r}"]


def _declares_callable(tree: ast.Module, name: str) -> bool:
    """Whether an import of this module would find `name` bound at module scope."""
    pending = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return True
            continue
        if isinstance(node, ast.Assign) and any(
            bound.id == name for bound in node.targets if isinstance(bound, ast.Name)
        ):
            return True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if any((alias.asname or alias.name.split(".")[0]) == name for alias in node.names):
                return True
        if isinstance(node, _BRANCHES):
            for field in ("body", "orelse", "finalbody", "handlers"):
                pending.extend(getattr(node, field, None) or [])
    return False

