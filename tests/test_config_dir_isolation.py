"""An isolated device folder leaves the names under the home folder as they were.

Python writes ``desktop.json`` and the engine key into ``config_root()``. That folder
is ``EPHE_CONFIG_DIR`` when the variable is set, and ``$HOME/.ephe`` when it is empty.
The desktop shell reads both back from the same folder (`instance.rs::config_dir`).

Two ways the two surfaces can drift apart are pinned here. A writer that was given no
home lands in the variable's folder. A caller that hands in the process home used to
get ``<home>/.ephe`` built around it, so an isolated run read the owner's key while
the shell looked in the variable's folder. Every run below pins ``HOME`` to a scratch
folder, so the verdict does not depend on the machine that executes it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from subprocess_env import hermetic_env  # noqa: E402


def _names(folder: Path) -> list[str]:
    return sorted(entry.name for entry in folder.iterdir())


def _run(script: str, home: Path, device: Path) -> subprocess.CompletedProcess[str]:
    """Run ``script`` in a child whose home and device folder are both scratch."""
    env = hermetic_env(
        PATH=os.environ.get("PATH", ""),
        HOME=str(home),
        EPHE_CONFIG_DIR=str(device),
        PYTHONPATH=str(REPO),
        PYTHONDONTWRITEBYTECODE="1",
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return proc


def test_an_isolated_device_folder_leaves_the_home_listing(tmp_path: Path) -> None:
    """Writers aimed at the variable leave the home folder's names unchanged."""
    home = tmp_path / "home"
    device = tmp_path / "device"
    kept = home / ".ephe"
    kept.mkdir(parents=True)
    (kept / "sentinel").write_text("keep", encoding="utf-8")
    before = _names(kept)

    script = """
from pathlib import Path
import ephe_cli
import core.engine_config as ec
ec._store_engine_keyring = lambda _value: False
ec.store_engine_api_key("isolated-token")
written = ephe_cli._schreibe_desktop_konfig(Path("/project"), "/usr/bin/python")
print(ec.key_file_path())
print(written)
"""
    proc = _run(script, home, device)
    lines = [line for line in proc.stdout.splitlines() if line]
    assert lines[0] == str(device / "engine.key")
    assert lines[1] == str(device / "desktop.json")
    assert _names(kept) == before, f"the home folder's names changed: {before} -> {_names(kept)}"
    assert (device / "engine.key").is_file()
    assert (device / "desktop.json").is_file()
    assert not (kept / "engine.key").exists()
    assert not (kept / "desktop.json").exists()


def test_a_caller_handing_in_the_process_home_reads_the_device_folder(tmp_path: Path) -> None:
    """The process home follows the variable; only another home keeps ``<home>/.ephe``.

    The desktop spawn reads the engine key and ``desktop.json`` from ``config_dir()``,
    and Python's writer took the home it was handed. With the process home handed in,
    the reader answered with the token in the owner's home folder while the shell
    looked in the isolated one. The token below says which folder answered.
    """
    home = tmp_path / "home"
    device = tmp_path / "device"
    kept = home / ".ephe"
    kept.mkdir(parents=True)
    (kept / "engine.key").write_text("home-token\n", encoding="utf-8")
    (kept / "engine.key").chmod(0o600)
    device.mkdir()
    (device / "engine.key").write_text("device-token\n", encoding="utf-8")
    (device / "engine.key").chmod(0o600)
    before = _names(kept)

    script = """
from pathlib import Path
import ephe_cli
import core.engine_config as ec
ec._load_engine_keyring = lambda: ""
home = Path.home()
print(ec.key_file_path(home))
print(ec.engine_api_key_for("http://127.0.0.1:9/v1", home=home))
print(ephe_cli._schreibe_desktop_konfig(Path("/project"), "/usr/bin/python", home=home))
"""
    proc = _run(script, home, device)
    lines = [line for line in proc.stdout.splitlines() if line]
    assert lines[:3] == [
        str(device / "engine.key"),
        "device-token",
        str(device / "desktop.json"),
    ], lines
    assert _names(kept) == before
    assert (device / "desktop.json").is_file()


def test_the_tooling_defaults_name_the_device_folder(tmp_path: Path) -> None:
    """The audit, memory, stress and bench defaults carry the variable, not a home.

    Each of these scripts built its own copy of the root's rule. An isolated run that
    used them read the owner's folder: the audit log it counts, the Kepta store it
    re-embeds, the server home the stress snapshot walks, and the engine record the
    bench labels a cohort with.
    """
    home = tmp_path / "home"
    device = tmp_path / "device"
    kept = home / ".ephe"
    kept.mkdir(parents=True)
    (kept / "engine.json").write_text(
        json.dumps({"provider": "home", "model": "home"}), encoding="utf-8"
    )
    device.mkdir()
    (device / "engine.json").write_text(
        json.dumps({"provider": "device", "model": "device"}), encoding="utf-8"
    )

    script = """
import importlib.util
import sys
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit = load("audit_probe", "scripts/audit_usage.py")
print("rc", audit.main([]))
memory = load("memory_probe", "scripts/memory_embed_store_check.py")
stress = load("stress_probe", "scripts/stress_1000_messages.py")
trend = load("trend_probe", "evals/bench_trend.py")
gate = load("gate_probe", "evals/pass3_release_gate.py")
print("memory", memory.DEFAULT_ROOTS[0])
print("foreign", memory.DEFAULT_ROOTS[1])
print("stress", stress.SERVER_DATA_HOME)
print("trend", *trend._engine_meta())
print("gate", gate.DEFAULT_ENGINE)
"""
    proc = _run(script, home, device)
    out = proc.stdout + proc.stderr
    assert f"[audit-usage] no log at {device / 'audit.log'}" in out, out
    assert f"memory {device / 'memory' / 'kepta'}" in out, out
    assert f"foreign {home / '.kepta'}" in out, out
    assert f"stress {device}" in out, out
    assert f"trend device device {device / 'engine.json'}" in out, out
    assert f"gate {device / 'engine.json'}" in out, out
    assert _names(kept) == ["engine.json"]
