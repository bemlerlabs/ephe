"""An isolated device folder leaves the names under the home folder as they were.

Python writes ``desktop.json`` and, when no home was passed, the engine key into
``config_root()``. That folder is ``EPHE_CONFIG_DIR`` when the variable is set.
The check compares the home listing before and after the writes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from subprocess_env import hermetic_env  # noqa: E402


def _names(folder: Path) -> list[str]:
    return sorted(entry.name for entry in folder.iterdir())


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
    lines = [line for line in proc.stdout.splitlines() if line]
    assert lines[0] == str(device / "engine.key")
    assert lines[1] == str(device / "desktop.json")
    after = _names(kept)
    assert before == after, f"the home folder's names changed: {before} -> {after}"
    assert (device / "engine.key").is_file()
    assert (device / "desktop.json").is_file()
    assert not (kept / "engine.key").exists()
    assert not (kept / "desktop.json").exists()
