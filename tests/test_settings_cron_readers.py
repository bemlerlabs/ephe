"""I7-3 — the schedule dials reach the scheduler.

Four values were literals in the code (misfire 3600 s, history 50, view 20,
the `max_instances` APScheduler default 1), while the Cronjobs section showed
none of them. The check targets the effect, not the call.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from core.settings_schema import save_deep_settings, validate_sections  # noqa: E402


def _set(**fields) -> None:
    assert save_deep_settings(validate_sections({"cron": fields}))


@pytest.fixture
def cron_home(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", cfg, raising=False)
    return cfg


def test_nachholen_und_gleichzeitigkeit_kommen_beim_job_an(cron_home) -> None:
    from core import scheduler as sc

    captured: dict = {}
    fake = MagicMock()
    fake.add_job.side_effect = lambda **kw: captured.update(kw)

    sched = sc.EpheScheduler()
    sched._ensure_scheduler = lambda: fake  # type: ignore[method-assign]

    sched.add_job("Test Aufgabe", cron_expr="0 8 * * *")
    assert captured["misfire_grace_time"] == 3600  # the default is 60 minutes
    assert captured["max_instances"] == 1  # the APScheduler default, unchanged

    _set(**{"cron.misfire_grace_minutes": 5, "cron.max_parallel_jobs": 4})
    captured.clear()
    sched.add_job("Test Aufgabe 2", cron_expr="0 9 * * *")
    assert captured["misfire_grace_time"] == 300
    assert captured["max_instances"] == 4


def test_verlauf_groesse_und_ansicht_lesen_den_regler(cron_home) -> None:
    from core import scheduler as sc

    assert sc.history_keep() == 50
    assert sc.history_rows() == 20
    _set(**{"cron.history_keep": 12, "cron.history_rows": 7})
    assert sc.history_keep() == 12
    assert sc.history_rows() == 7

    sched = sc.EpheScheduler()
    saved = list(sc._job_results)
    try:
        sc._job_results.clear()
        sc._job_results.extend(
            {"job_id": f"j{i}", "executed_at": str(i), "task": "t", "result": "ok", "error": None}
            for i in range(30)
        )
        assert len(sched.get_results()) == 7, "die Ansicht folgt dem Regler"
        assert len(sched.get_results(limit=3)) == 3, "eine ausdrückliche Zahl gewinnt"
    finally:
        sc._job_results.clear()
        sc._job_results.extend(saved)


def test_die_schranken_sind_im_payload(cron_home) -> None:
    from core.settings_schema import deep_view

    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    for key in (
        "cron.misfire_grace_minutes",
        "cron.history_keep",
        "cron.history_rows",
        "cron.max_parallel_jobs",
    ):
        entry = entries[key]
        assert entry["type"] == "number" and entry["step"] == 1, key
        assert entry["min"] <= entry["default"] <= entry["max"], key
        assert entry["hint"] and entry["hintEn"], key
    with pytest.raises(ValueError):
        validate_sections({"cron": {"cron.max_parallel_jobs": 99}})


def test_route_ohne_angabe_nimmt_die_Reglerzahl(cron_home) -> None:
    from fastapi.testclient import TestClient

    from server.main import app

    _set(**{"cron.history_rows": 6})
    client = TestClient(app)
    _set(**{"cron.history_rows": 6})  # environment isolation after the import
    body = client.get("/api/schedule/results").json()
    assert len(body["results"]) <= 6
