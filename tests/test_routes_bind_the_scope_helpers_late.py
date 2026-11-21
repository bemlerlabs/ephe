"""tests/test_routes_bind_the_scope_helpers_late.py — the class #146 was filed for.

`358734d2` closed one instance: `server/routes/fs.py` wrote
`from core.tools.base import _get_allowed_roots`, which copies the name into the route's own
namespace at import time, so a patch on the kernel left the route holding whatever was live while
the module first imported. `tests/test_routes_read_the_kernel_list.py` guards that route from both
directions. It cannot see a new route repeating the move, and the same capture was still standing
in the route that decides whether a browser may read an artifact file:

    server/routes/files.py:24   from core.tools.base import allowed_root_of
    server/routes/files.py:175  root = allowed_root_of(probe)   # refusal: file_path_not_allowed

A function-local import (`server/routes/artifacts.py:349`, `core/artifact_workbench.py:109`)
re-reads the attribute on every call, which is why this scan walks module bodies and leaves
function bodies alone; hoisting one of those lines into the import block is the change this file
refuses.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVER = Path(__file__).resolve().parent.parent / "server"

# Names whose value belongs to the kernel's file scope. Importing one by name freezes which
# answer the route asks; reaching through the module asks it again on every call.
SCOPE_NAMES = frozenset(
    {
        "ALLOWED_ROOTS",
        "_get_allowed_roots",
        "_resolve_allowed_roots",
        "allowed_root_of",
        "_is_path_allowed",
    }
)


def _module_level_capture(path: Path) -> list[tuple[int, str]]:
    """Every top-level `from core.tools.base import …` name in `path` that holds a scope answer."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or node.module != "core.tools.base":
            continue
        if node.col_offset:  # inside a def/class: re-read per call, which is the late binding
            continue
        for alias in node.names:
            if alias.name in SCOPE_NAMES:
                found.append((node.lineno, alias.name))
    return sorted(found)


def _route_files() -> list[Path]:
    return sorted(p for p in _SERVER.rglob("*.py") if p.is_file())


def test_no_server_module_freezes_a_kernel_scope_answer():
    """The whole `server/` tree, read as source, holds no top-level by-value scope import."""
    offenders = [(p, hits) for p in _route_files() if (hits := _module_level_capture(p))]
    assert not offenders, "server modules that freeze a kernel scope answer at import time: " + ", ".join(
        f"{p.relative_to(_SERVER.parent)}:{lineno} imports {name}" for p, hits in offenders for lineno, name in hits
    )


def test_the_scan_reports_a_route_that_captures_the_helper(tmp_path: Path):
    """Proof the instrument can fail: a module-level capture is named with its line."""
    module = tmp_path / "route_like.py"
    module.write_text(
        "from core.tools.base import allowed_root_of\n\n\ndef handler(p):\n    return allowed_root_of(p)\n",
        encoding="utf-8",
    )
    assert _module_level_capture(module) == [(1, "allowed_root_of")]


def test_the_scan_leaves_an_import_the_call_repeats(tmp_path: Path):
    """The other side of the boundary: a function-local import resolves per call."""
    module = tmp_path / "route_like.py"
    module.write_text(
        "def handler(p):\n    from core.tools.base import allowed_root_of\n    return allowed_root_of(p)\n",
        encoding="utf-8",
    )
    assert _module_level_capture(module) == []


def test_the_server_tree_is_read_at_all() -> None:
    """A scan over nothing passes for the wrong reason, so the file count is asserted."""
    assert len(_route_files()) > 20, f"only {len(_route_files())} modules under {_SERVER}"


@pytest.mark.parametrize("name", sorted(SCOPE_NAMES))
def test_every_guarded_name_is_a_real_kernel_attribute(name: str) -> None:
    """A name the kernel stopped exporting would make this list a lie about coverage."""
    import core.tools.base as base

    assert hasattr(base, name), f"core.tools.base no longer exposes {name}; update SCOPE_NAMES"
