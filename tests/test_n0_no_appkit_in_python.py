"""N0 boundary gate: core/ and server/ import no macOS UI framework.

docs/NATIVE_DESKTOP_PLAN.md section N0 keeps native macOS capabilities in the Rust
shell or a signed sidecar. A Python import of AppKit would tie a backend route to the
window server and drop the Linux and container legs, so the rule gets an executable
check here.

The check walks import nodes from the parser. Comments and docstrings that mention
those frameworks stay quiet.
"""
from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("core", "server")
FORBIDDEN_HEADS = {"appkit", "cocoa", "foundation", "quartz", "webkit", "objc"}
FORBIDDEN_PREFIXES = ("pyobjc",)
_NAME_END = re.compile(r"[<>=!~\[;\s]")


def _is_forbidden(module: str) -> bool:
    head = module.split(".")[0].casefold()
    return head in FORBIDDEN_HEADS or head.startswith(FORBIDDEN_PREFIXES)


def forbidden_imports(tree: ast.AST) -> list[tuple[int, str]]:
    """The line number and module of every import of a macOS UI framework."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module and _is_forbidden(module):
                found.append((node.lineno, module))
            elif node.level:
                for alias in node.names:
                    if _is_forbidden(alias.name):
                        found.append((node.lineno, alias.name))
    return sorted(set(found))


def scan_paths(paths: Iterable[Path], root: Path = ROOT) -> dict[str, list[tuple[int, str]]]:
    """Every offending import under these paths, keyed by path relative to `root`."""
    hits: dict[str, list[tuple[int, str]]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = forbidden_imports(tree)
        if found:
            hits[str(path.relative_to(root))] = found
    return hits


def package_files(root: Path = ROOT) -> list[Path]:
    """Every Python file in the two packages the boundary covers."""
    files: list[Path] = []
    for package in PACKAGES:
        files.extend(sorted((root / package).rglob("*.py")))
    return files


def dependency_specs(root: Path = ROOT) -> list[str]:
    """Every requirement the project declares, including the uv constraint lists."""
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    for group in data.get("dependency-groups", {}).values():
        specs.extend(spec for spec in group if isinstance(spec, str))
    uv = data.get("tool", {}).get("uv", {})
    for key in ("constraint-dependencies", "override-dependencies"):
        specs.extend(uv.get(key, []))
    return specs


def distribution_name(spec: str) -> str:
    """The normalized distribution name of one requirement string."""
    return _NAME_END.split(spec.strip(), maxsplit=1)[0].casefold().replace("_", "-")


def test_core_and_server_import_no_macos_ui_framework() -> None:
    hits = scan_paths(package_files())
    assert hits == {}, hits


def test_the_scanned_packages_are_present() -> None:
    """A moved package would leave the gate above with nothing to read."""
    counts = {package: len(list((ROOT / package).rglob("*.py"))) for package in PACKAGES}
    assert counts["core"] > 100, counts
    assert counts["server"] > 20, counts


def test_pyproject_declares_no_pyobjc_package() -> None:
    offenders = [
        spec
        for spec in dependency_specs()
        if distribution_name(spec) == "objc" or distribution_name(spec).startswith("pyobjc")
    ]
    assert offenders == []


def test_a_direct_import_is_seen(tmp_path: Path) -> None:
    module = tmp_path / "module.py"
    module.write_text(
        "import AppKit\n"
        "from Foundation import NSObject\n"
        "from objc import nil\n"
        "import pyobjc_framework_cocoa\n"
        "from . import AppKit\n",
        encoding="utf-8",
    )
    assert scan_paths([module], root=tmp_path) == {
        "module.py": [
            (1, "AppKit"),
            (2, "Foundation"),
            (3, "objc"),
            (4, "pyobjc_framework_cocoa"),
            (5, "AppKit"),
        ]
    }


def test_prose_mentions_are_not_imports(tmp_path: Path) -> None:
    module = tmp_path / "module.py"
    module.write_text(
        '"""Talks about AppKit and Foundation without importing either."""\n'
        "# Cocoa lives in the Rust shell.\n"
        "MENTION = 'Quartz inside a string, WebKit beside it'\n"
        "import json\n",
        encoding="utf-8",
    )
    assert scan_paths([module], root=tmp_path) == {}
