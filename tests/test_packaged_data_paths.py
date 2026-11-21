"""The data the backend reads from its own tree has to travel with the wheel.

`core.marketplace_sources` and `core.plugin_store` resolve their catalogues
beside the package they live in — for a checkout that is the repository root,
for a wheel it is site-packages. A name left out of the build's include is not
a warning a reader can miss: the shelf opens empty and the curated plugin list
is gone, and only a packaged install shows it while the desktop backend, which
runs from a checkout, looks perfectly fine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

try:
    import tomllib  # stdlib from 3.11
except ModuleNotFoundError:  # 3.10
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]

#: What the running code reads beside its own package, in the tree it starts in.
RUNTIME_DATA = [
    "marketplace",
    "ephe-marketplace.json",
    "plugin-catalog.json",
    "plugin-marketplace.json",
]


def _wheel_include() -> list[str]:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(manifest["tool"]["hatch"]["build"]["targets"]["wheel"]["include"])


@pytest.mark.parametrize("name", RUNTIME_DATA)
def test_the_data_the_backend_reads_travels_in_the_wheel(name: str) -> None:
    declared = _wheel_include()
    assert name in declared or f"{name}/**" in declared, (
        f"{name} is read at runtime but the wheel does not carry it"
    )
    assert (ROOT / name).exists(), f"{name} is declared but the tree holds no such path"
