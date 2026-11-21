"""Warm the request-path imports before the first click.

The server imports its route modules at startup, but the core half a handler
needs is imported where it runs. Measured cold (fresh process, the 45-session /
6-plugin / 80-skill home of the PERF-BE report): ``/api/context/stages`` pays
0.32 s (the tool-schema build and the plugin mount), ``/api/plugins`` 0.27 s,
``/api/sessions`` 0.19 s, ``/api/memory/stats`` 0.41 s (an embedding model, not
an import). Server start is 0.4-0.7 s of imports either way; this moves the
*first request* cost into one background thread that runs while the shell is
still polling ``/api/health``.

Every step is best effort, idempotent and touches no network. A broken optional
subsystem logs one line and the server keeps serving; the click then pays what
it always paid.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _warm_tool_schemas() -> None:
    """Build the base tool array once — the mount replay and the plugin gate."""
    from core.tools import get_tool_schemas

    get_tool_schemas()


def _warm_plugin_view() -> None:
    """Run the portfolio scan the plugin page asks for on its first load."""
    from core.plugin_store import plugins_view

    plugins_view()


def _warm_session_store() -> None:
    """Import the store the session list reads and load its registry once."""
    from core import session_lifecycle

    registry = session_lifecycle.read_registry()
    session_lifecycle.store_stats(registry=registry)


def _warm_memory_stack() -> None:
    """Import the memory read path; the embedding model stays a first-use load."""
    from core import memory, memory_embed, memory_provider  # noqa: F401


_STEPS = (
    ("tool schemas", _warm_tool_schemas),
    ("plugin view", _warm_plugin_view),
    ("session store", _warm_session_store),
    ("memory stack", _warm_memory_stack),
)


def warm_request_paths() -> None:
    """Run every warmup step; one failing step never hides the others."""
    for name, step in _STEPS:
        try:
            step()
        except Exception:
            logger.debug("warmup step '%s' skipped", name, exc_info=True)
