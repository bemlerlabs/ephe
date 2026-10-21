"""OWN-02 — cancellable plugin calls and disposer teardown.

A plugin-owned tool call is registered while it runs. Disabling the plugin marks
the call cancelled, cancels its asyncio task and runs the plugin's disposers in
reverse order. A disposer failure is reported, not swallowed: the lifecycle keeps
the plugin on rather than claiming a teardown that did not finish.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_activity, plugin_runtime


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core import audit_log

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    plugin_activity.clear()
    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_activity.clear()
    plugin_runtime.invalidate_ownership_cache()


def _write_plugin(config: Path) -> None:
    plugin = config / "plugins" / "acme-research"
    plugin.mkdir(parents=True)
    (plugin / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "acme-research",
                "version": "1.0.0",
                "description": "Acme research",
                "permissions": {"tool_families": ["write"], "data_roots": []},
                "components": {
                    "skills": [],
                    "commands": [],
                    "tools": ["create_video"],
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_cancelling_an_inflight_call_marks_and_cancels_it(device) -> None:
    async def call() -> None:
        guard = plugin_activity.begin_call("acme-research")
        try:
            await asyncio.sleep(5)
        finally:
            plugin_activity.end_call(guard)

    task = asyncio.create_task(call())
    await asyncio.sleep(0.05)
    assert plugin_activity.cancel_calls("acme-research") == 1
    with pytest.raises(asyncio.CancelledError):
        await task


def test_disposers_run_in_reverse_order_and_errors_are_reported(device) -> None:
    order: list[str] = []
    plugin_activity.register_disposer("acme-research", lambda: order.append("first"))
    plugin_activity.register_disposer("acme-research", lambda: order.append("second"))
    plugin_activity.teardown_plugin("acme-research")
    assert order == ["second", "first"]

    def explode() -> None:
        raise RuntimeError("disposer failed")

    plugin_activity.register_disposer("acme-research", explode)
    with pytest.raises(plugin_activity.TeardownError) as err:
        plugin_activity.teardown_plugin("acme-research")
    assert "disposer failed" in str(err.value)


def test_a_failed_disposer_is_retried_and_successful_ones_are_not(device) -> None:
    order: list[str] = []
    fail = {"now": True}

    def flaky() -> None:
        order.append("flaky")
        if fail["now"]:
            fail["now"] = False
            raise RuntimeError("transient")

    plugin_activity.register_disposer("acme-research", flaky)
    plugin_activity.register_disposer("acme-research", lambda: order.append("ok"))

    with pytest.raises(plugin_activity.TeardownError) as err:
        plugin_activity.teardown_plugin("acme-research")
    assert "transient" in str(err.value)
    assert order == ["ok", "flaky"]

    plugin_activity.teardown_plugin("acme-research")
    assert order == ["ok", "flaky", "flaky"]


def test_a_successful_retry_leaves_no_disposer_for_a_third_call(device) -> None:
    calls: list[str] = []
    fail = {"now": True}

    def flaky() -> None:
        calls.append("flaky")
        if fail["now"]:
            fail["now"] = False
            raise RuntimeError("transient")

    plugin_activity.register_disposer("acme-research", flaky)
    with pytest.raises(plugin_activity.TeardownError):
        plugin_activity.teardown_plugin("acme-research")
    plugin_activity.teardown_plugin("acme-research")
    plugin_activity.teardown_plugin("acme-research")

    assert calls == ["flaky", "flaky"]


@pytest.mark.asyncio
async def test_execute_tool_reports_a_plugin_cancelled_call_as_cancelled(
    device,
    monkeypatch,
) -> None:
    import core.tools.registry as registry

    _write_plugin(device)
    plugin_runtime.invalidate_ownership_cache()
    lifecycle = plugin_runtime.lifecycle()
    lifecycle.set_enabled("acme-research", False)
    lifecycle.set_enabled("acme-research", True)

    started = asyncio.Event()
    finished = asyncio.Event()

    async def acme_wait() -> str:
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            finished.set()
        return "finished"

    monkeypatch.setitem(registry.TOOL_MAP, "create_video", acme_wait)
    task = asyncio.create_task(registry.execute_tool("create_video", {}))
    await asyncio.wait_for(started.wait(), timeout=5)
    await asyncio.to_thread(lifecycle.set_enabled, "acme-research", False)
    result = await asyncio.wait_for(task, timeout=5)

    assert "cancelled" in result.lower()
    assert finished.is_set()
    assert lifecycle.snapshot("acme-research").state.value == "disabled"
