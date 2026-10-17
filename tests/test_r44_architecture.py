"""
◑ Ephe – W1 (2026-09-09): architecture foundation.
tests/test_r44_architecture.py

RULE: the tests were written BEFORE the implementation.

Pins:
1. `logging` is imported at module level in server/main.py (the lifespan's
   error path uses logging.getLogger — without the module import, a latent NameError).
2. The lifespan runs through and starts the scheduler (ephe_scheduler.running).
"""
from __future__ import annotations

import server.main as m


def test_module_level_logging_import():
    """GIVEN server.main is imported
    THEN the module attribute `logging` exists (module level, not only in
    configure_gui_safety) — otherwise the lifespan except path raises NameError.
    """
    assert m.logging is not None
    assert m.logging.getLogger("uvicorn.error") is not None


def test_lifespan_boots_scheduler():
    """GIVEN the FastAPI app container
    WHEN the lifespan runs (TestClient context)
    THEN the Ephe scheduler has started (running=True)."""
    from starlette.testclient import TestClient

    from core.scheduler import ephe_scheduler

    app = m.create_app()
    with TestClient(app):
        # the inner AsyncIOScheduler object (core/scheduler.py:94) carries `running`,
        # not the EpheScheduler wrapper.
        assert ephe_scheduler._scheduler is not None
        assert ephe_scheduler._scheduler.running is True
