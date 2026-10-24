"""The cell runtime floor: a patched wasmtime, and a config that still builds.

Ephemora Cell 1.1.0 declares ``wasmtime<48``. That bound predates the engine the
advisories were patched in. PyPI publishes 48.0.0 but not the 48.0.6 fix, and
not the 49.0.3 fix; 50.0.1 is the first published release outside every affected
range. Ephe overrides the transitive bound, and these tests read the floor from
pyproject so a later ``uv lock`` cannot walk back into it.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _declared_floor() -> tuple[int, ...]:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"wasmtime>=([0-9.]+),<', text)
    assert match, "no wasmtime floor in the uv override block"
    return tuple(int(part) for part in match.group(1).split("."))


FLOOR = _declared_floor()


def _locked_wasmtime() -> tuple[int, ...]:
    text = (REPO / "uv.lock").read_text(encoding="utf-8")
    match = re.search(r'name = "wasmtime"\nversion = "([^"]+)"', text)
    assert match, "wasmtime is not resolved in uv.lock"
    return tuple(int(part) for part in match.group(1).split(".") if part.isdigit())


def test_the_locked_wasmtime_is_at_or_above_the_patched_floor():
    """GIVEN the dependency lock we ship
    THEN the resolved wheel is at least 48.0.0, the pip release that closes five
    of the advisories 47.0.1 carries."""
    version = _locked_wasmtime()
    assert version >= FLOOR, f"uv.lock resolves wasmtime {version}, floor is {FLOOR}"


def test_the_project_overrides_the_transitive_upper_bound():
    """GIVEN ephemora-cell declares ``wasmtime<48``
    THEN Ephe overrides that bound in its own file at or above 50.0.1, the first
    published release outside every affected range."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "override-dependencies" in text, "no uv override block"
    assert FLOOR >= (50, 0, 1), f"the declared wasmtime floor is {FLOOR}"
    assert _locked_wasmtime() >= FLOOR, "uv.lock sits below the declared floor"


def test_the_cell_config_still_builds_on_the_patched_engine():
    """GIVEN the patched engine
    WHEN the cell builds its sandbox config
    THEN the configuration object exists with its caps, so the version bump did
    not break the seam the product calls."""
    pytest.importorskip("ephemora_cell", reason="the sandbox extra is not installed")

    from ephemora_cell import WASIConfig

    config = WASIConfig()
    assert config.max_fuel > 0
    assert config.max_memory_mb > 0


def test_fuel_is_enforced_by_the_patched_engine(tmp_path):
    """GIVEN the patched engine and the cell's own config builder
    WHEN a guest spins without consuming any other resource
    THEN execution traps on exhausted fuel. The flags on ``wasmtime.Config``
    cannot be read back, so enforcement is the only honest check: a config the
    engine ignores would run forever instead of trapping."""
    pytest.importorskip("wasmtime", reason="the sandbox extra is not installed")

    script = tmp_path / "fuel_probe.py"
    script.write_text(
        "import wasmtime\n"
        "from ephemora_cell._engine_config import build_engine_config\n"
        "engine = wasmtime.Engine(build_engine_config(max_fuel=10_000, memory64=False))\n"
        "module = wasmtime.Module(engine, '(module (func (export \\\"spin\\\") (loop br 0)))')\n"
        "store = wasmtime.Store(engine)\n"
        "store.set_fuel(10_000)\n"
        "inst = wasmtime.Instance(store, module, [])\n"
        "try:\n"
        "    inst.exports(store)['spin'](store)\n"
        "    print('NO-TRAP')\n"
        "except wasmtime.Trap:\n"
        "    print('TRAPPED')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=45
    )
    assert "TRAPPED" in result.stdout, (result.stdout, result.stderr[-400:])
