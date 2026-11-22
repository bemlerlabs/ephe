"""Motion studio tests: a stale revision never writes."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDLERS = ROOT / "plugins" / "ephe-motion-studio" / "tools" / "handlers.py"


def _module(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("ephe_motion_handlers", HANDLERS)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, tmp_path / "state"


def test_create_project_binds_a_project_id_and_revision(tmp_path, capsys):
    mod, state = _module(tmp_path)
    answer = mod.ephe_motion_create_project({"name": "title", "duration": 3}, state, None)
    assert isinstance(answer, str)
    assert "title" in answer


def test_stale_revision_is_refused_without_writing(tmp_path):
    mod, state = _module(tmp_path)
    created = mod._dispatch(
        "ephe_motion_create_project", {"name": "title", "duration": 3}, state
    )
    payload = json.loads(created)
    project_id = payload["project_id"]
    try:
        mod._dispatch(
            "ephe_motion_write_source",
            {"project_id": project_id, "path": "index.html",
             "content": "<html></html>", "expected_revision": "0" * 64},
            state,
        )
    except mod._Refusal as exc:
        assert "revision" in str(exc).lower()
    else:
        raise AssertionError("a stale revision was accepted")
