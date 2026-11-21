"""Aim a tool double at the dispatch the called name really takes.

execute_tool resolves a marker to its bundle name and then asks the kernel map:
a name the map holds runs there, a name it does not hold goes to the confined
worker through dynamic_wiring.dispatch_dynamic_call, on a worker thread. This
helper reads the same two authorities, so the double sits on the seam the call
uses instead of one it never reaches.

The map half is only safe for a name the map already holds. Adding a contributed
name to it does worse than miss: the reserved name space is the kernel map, so the
entry makes the bundle's own claim on that name a collision, the activation scan
reports a conflict, and the plugin gate refuses the call before any dispatch.

An awaitable double keeps its await count: the worker seam runs on a thread with
no loop of its own, so the coroutine gets one.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def patched_tool(name: str, executor):
    from core.tools.dynamic_wiring import MARKER_ALIASES, dispatch_dynamic_call
    from core.tools.registry import TOOL_MAP

    resolved = MARKER_ALIASES.get(name, name)

    async def _dispatch(tool: str, arguments: dict):
        if tool != resolved:
            return await dispatch_dynamic_call(tool, arguments)
        answer = executor(**arguments)
        if asyncio.iscoroutine(answer):
            return await answer
        return answer

    if resolved in TOOL_MAP:
        with patch.dict(TOOL_MAP, {resolved: executor}, clear=False):
            yield
    else:
        with patch("core.tools.dynamic_wiring.dispatch_dynamic_call", _dispatch):
            yield