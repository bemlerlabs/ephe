"""The version number has one home: `pyproject.toml` `[project].version`.

A packaged install answers from the distribution metadata, which was built from
that field; a source-tree run parses the file back. This module reads the number,
so no second literal can drift away from the manifest.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

try:
    import tomllib  # stdlib from 3.11
except ModuleNotFoundError:  # 3.10: tomli is the marker-scoped main dependency
    import tomli as tomllib  # type: ignore[no-redef]

__all__ = ["__version__", "source_tree_version", "version_string"]

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _installed_version() -> str | None:
    try:
        return importlib.metadata.version("ephe")
    except importlib.metadata.PackageNotFoundError:
        return None


def source_tree_version() -> str | None:
    """`[project].version` of the repo-root pyproject.toml, or None off the tree."""
    try:
        with _PYPROJECT.open("rb") as fh:
            return str(tomllib.load(fh)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return None


def version_string() -> str:
    # A checkout is authoritative for the tree it runs: an older `ephe`
    # distribution in the same interpreter must not answer for code it does not
    # contain. A wheel ships no pyproject and falls back to its metadata.
    return source_tree_version() or _installed_version() or "0.0.0+unknown"


__version__ = version_string()
