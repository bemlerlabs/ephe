"""WG-47: a fact a running Ephe wrote into memory is readable after a restart.

The restart here is real. The interpreter that stores the fact exits before the
interpreter that reads it starts, so only the store on disk can carry the fact
across the boundary. Each side runs ``tests/e2e/memory_restart_leg.py`` over the
shipped FastAPI app; the engine is never built, so no model and no network are
involved.

The second test reads a *different* ``EPHE_MEMORY_DIR`` and must find nothing.
That is what separates "the fact survived on disk" from "the read route answers
from somewhere other than the directory it was handed".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEG = Path(__file__).with_name("memory_restart_leg.py")

FACT = "The Ephe maintainer keeps a green bicycle in Freiburg."
QUERY = "where does the maintainer keep the bicycle"

#: A child that imports chromadb takes a few seconds; the legs get room.
LEG_TIMEOUT_S = 180


def _leg_env(memory_dir: Path, home: Path) -> dict[str, str]:
    """The child env: this checkout on the path, every write under `home`."""
    env = dict(os.environ)
    env.update(
        {
            "EPHE_CONFIG_DIR": str(home),
            "EPHE_SESSIONS_DIR": str(home / "sessions"),
            "EPHE_MEMORY_DIR": str(memory_dir),
            "EPHE_MEMORY_PROVIDER": "chroma",
            "EPHE_OFFLINE": "1",
            "PYTHONPATH": str(REPO_ROOT),
        }
    )
    return env


def _run_leg(mode: str, payload: str, env: dict[str, str]) -> dict:
    """Start one interpreter, run one leg in it, and return its JSON result."""
    done = subprocess.run(
        [sys.executable, str(LEG), mode, payload],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=LEG_TIMEOUT_S,
    )
    assert done.returncode == 0, f"leg {mode!r} failed:\n{done.stdout}\n{done.stderr}"
    return json.loads(done.stdout.strip().splitlines()[-1])["result"]


def test_a_stored_fact_survives_a_restart(tmp_path):
    memory_dir = tmp_path / "memory"
    home = tmp_path / "ephe-home"
    env = _leg_env(memory_dir, home)

    stored = _run_leg("store", FACT, env)
    assert stored["status"] == 200, stored
    assert stored["body"]["stored"] is True, stored
    memory_id = stored["body"]["id"]
    assert memory_id

    after = _run_leg("read", QUERY, env)
    assert after["total"] == 1, after
    assert after["stats_total"] == 1, after
    assert [e["text"] for e in after["entries"]] == [FACT], after
    assert [e["id"] for e in after["entries"]] == [memory_id], after
    assert after["results"] and after["results"][0]["id"] == memory_id, after


def test_a_different_memory_dir_does_not_see_the_fact(tmp_path):
    stored = _run_leg("store", FACT, _leg_env(tmp_path / "source-memory", tmp_path / "source-home"))
    assert stored["body"]["stored"] is True, stored

    elsewhere = _run_leg("read", QUERY, _leg_env(tmp_path / "reader-memory", tmp_path / "reader-home"))
    assert elsewhere["entries"] == [], elsewhere
    assert elsewhere["total"] == 0, elsewhere
    assert elsewhere["stats_total"] == 0, elsewhere
    assert elsewhere["results"] == [], elsewhere
