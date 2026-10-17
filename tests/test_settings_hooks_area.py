"""I6-4 — the hooks area: the switch acts in the core, the view does not lie.

A settings field is a control only once production code reads the value
(tests/test_settings_surface_is_real.py). This test checks the two things
the surface claims:
1. `hooks.enabled` off = no child process starts out of hooks.json.
2. The read page shows only what is there — and marks events without a caller as
   such, instead of letting them look like active hooks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from core.settings_schema import save_deep_settings, validate_sections  # noqa: E402

# A pre_tool hook that reasons its own blockage: if the reason appears in the
# tool result, the process took place.
BLOCKING_HOOK = (
    f"{sys.executable} -c \"import json,sys; json.load(sys.stdin); "
    "print(json.dumps({'block': 'hook hat gelaufen'}))\""
)


def _write_hooks(cfg: Path) -> Path:
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "hooks.json").write_text(
        json.dumps(
            {
                "pre_tool": [{"command": BLOCKING_HOOK, "match": "read_file"}],
                # entered by hand, but with no production caller: the view
                # must show it as "without a caller", not as an active hook
                "session_start": [{"command": "true"}],
            }
        ),
        encoding="utf-8",
    )
    return cfg / "hooks.json"


def _set_enabled(value: bool) -> None:
    assert save_deep_settings(validate_sections({"hooks": {"hooks.enabled": value}}))


@pytest.fixture
def hooks_home(tmp_path, monkeypatch):
    """Empty hooks folder plus a fresh hook cache (the cache is pinned to mtime)."""
    from core import user_hooks

    cfg = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    user_hooks.reset_cache()
    yield cfg
    user_hooks.reset_cache()


def _run_tool() -> str:
    import asyncio

    from core.tools.registry import execute_tool

    return asyncio.run(execute_tool("read_file", {"path": "/tmp/ephe-hooks-probe"}))


def test_schalter_aus_laesst_keinen_hook_starten(hooks_home) -> None:
    from core import user_hooks

    _write_hooks(hooks_home)
    _set_enabled(True)
    user_hooks.reset_cache()
    assert user_hooks.hooks_enabled() is True
    assert "hook hat gelaufen" in _run_tool()

    _set_enabled(False)
    user_hooks.reset_cache()
    assert user_hooks.hooks_enabled() is False
    # the same file, the same call — no hook runs, because the switch is off
    assert "hook hat gelaufen" not in _run_tool()


def test_die_sicht_zeigt_datei_events_und_laeufe(hooks_home) -> None:
    from core import user_hooks

    path = _write_hooks(hooks_home)
    view = user_hooks.hooks_view()
    assert view["enabled"] is True
    assert view["exists"] is True
    assert view["path"] == str(path)
    by_key = {e["key"]: e for e in view["events"]}
    assert by_key["pre_tool"]["live"] is True
    assert by_key["pre_tool"]["hooks"][0]["match"] == "read_file"
    # post_tool is a real caller event, but it is not populated here
    assert by_key["post_tool"]["live"] is True
    assert by_key["post_tool"]["hooks"] == []
    # session_start has no production caller — the view states that openly
    assert by_key["session_start"]["live"] is False
    assert isinstance(view["recent"], list)


def test_get_settings_hooks_liefert_die_sicht(hooks_home) -> None:
    from fastapi.testclient import TestClient

    from server.main import app

    _write_hooks(hooks_home)
    client = TestClient(app)
    res = client.get("/api/settings/hooks")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert {e["key"] for e in body["events"]} >= {"pre_tool", "post_tool"}
