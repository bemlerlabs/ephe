"""Reload one bundle through the mount the process already has.

``reload_bundle`` calls ``PluginLifecycle.mount`` and nothing else. It passes
an empty acknowledge list, so a schema or a description that moved since the
last accepted mount comes back as that mount's pin refusal. The previous
descriptors stay served. A mount that holds publishes ``plugin.mount`` on the
existing stream, which is what an open surface uses to load its document again.
"""
from __future__ import annotations

from typing import Any


def reload_bundle(plugin_id: str, *, lifecycle: Any = None):
    """Re-enter the one mount. A moved contract is the pin refusal, unchanged."""
    if lifecycle is None:
        from core import plugin_runtime

        lifecycle = plugin_runtime.lifecycle()
    return lifecycle.mount(
        str(plugin_id),
        acknowledge=(),
        acknowledge_artifact=False,
        actor="reload",
        reason="hot-reload",
    )
