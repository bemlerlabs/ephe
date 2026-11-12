"""HOOK-P1 — the turn-end dispatcher: one confined run per active bundle, never the turn.

The seam this file pins: after a turn the kernel queues one run per active bundle, in
plugin-id order, with the fixed metadata payload and nothing else; the run goes through the
same confined runner a contributed tool uses, with the declared timeout and no bridge; the
turn does not wait for it; a full queue drops and audits; a bundle switched off or paused
spawns nothing; and a measured turn enters `suppressed()` so a pass³ number never carries a
bundle's hook.

The child really runs in `test_the_hook_receives_the_metadata_payload_and_no_network`; the
rest patch `run_worker` or `_execute`, because the subject is the queue, the ordering and
the payload rather than the boundary the runner's own suite already proves.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from core import mcp_sandbox, plugin_manifest, plugin_turn_hooks
from core.plugin_hooks_contract import TurnHook
from tests.support.plugin_bundle import mark_installed

HOOK_BODY = '''
import json
import os
import socket


def main(arguments, state_dir):
    with open(os.path.join(state_dir, "received.json"), "w", encoding="utf-8") as handle:
        json.dump(arguments, handle)
    denied = ""
    try:
        socket.create_connection(("127.0.0.1", 9), timeout=0.5)
    except OSError as exc:
        denied = type(exc).__name__
    with open(os.path.join(state_dir, "network.txt"), "w", encoding="utf-8") as handle:
        handle.write(denied)
    return "ok"
'''


def _manifest(name: str, *, timeout: int = 2, entry: str = "hooks/turn_end.py:main") -> dict:
    return {
        "manifest_version": 2,
        "name": name,
        "version": "1.0.0",
        "description": "Runs one hook when a turn ends.",
        "publisher": {"name": "Acme"},
        "license": "MIT",
        "engines": {"ephe": ">=0.6.0"},
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {
            "hooks": {"turn_end": {"entry": entry, "timeout_seconds": timeout}}
        },
    }


def _write_bundle(
    plugins: Path,
    name: str = "acme-hook",
    *,
    timeout: int = 2,
    body: str = HOOK_BODY,
) -> Path:
    directory = plugins / name
    (directory / "hooks").mkdir(parents=True, exist_ok=True)
    (directory / "hooks" / "turn_end.py").write_text(body, encoding="utf-8")
    (directory / "ephe-plugin.json").write_text(
        json.dumps(_manifest(name, timeout=timeout)), encoding="utf-8"
    )
    return directory


def _dispatch(**overrides: object) -> None:
    plugin_turn_hooks.note_turn_end(
        turn_id=str(overrides.get("turn_id", "turn-1")),
        stop_reason=str(overrides.get("stop_reason", "answer")),
        tool_names=overrides.get("tool_names", ["file_search", "read_file"]),  # type: ignore[arg-type]
        duration_ms=float(overrides.get("duration_ms", 12.5)),  # type: ignore[arg-type]
    )


def _rows(log: Path, kind: str = "plugin_hook") -> list[dict]:
    if not log.exists():
        return []
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [entry for entry in entries if entry.get("kind") == kind]


@pytest.fixture(autouse=True)
def _clean_dispatcher():
    plugin_turn_hooks.reset()
    from core import plugin_activity

    plugin_activity.clear()
    yield
    plugin_turn_hooks.reset()
    plugin_activity.clear()


@pytest.fixture()
def plugins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield root
    plugin_runtime.invalidate_ownership_cache()


@pytest.fixture()
def audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from core import audit_log

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    return log


def _active(plugins: Path, name: str = "acme-hook", **kwargs: object) -> Path:
    directory = _write_bundle(plugins, name, **kwargs)  # type: ignore[arg-type]
    mark_installed(name, enabled=True)
    return directory


def test_the_payload_is_the_kernel_metadata_and_nothing_else(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.plugin_turn_hooks import note_turn_end
    from core.sandbox import supervisor
    from core.sandbox.supervisor import WorkerOutcome

    directory = _active(plugins, timeout=2)
    captured: dict = {}

    def fake_run_worker(spec, *, protocol_check=None, stdin_payload=None, bridge_dispatch=None):
        captured["spec"] = spec
        captured["request"] = json.loads(stdin_payload)
        captured["bridge"] = bridge_dispatch
        return WorkerOutcome(status="ok")

    monkeypatch.setattr(supervisor, "run_worker", fake_run_worker)
    note_turn_end(
        turn_id="turn-42",
        stop_reason="answer",
        tool_names=["file_search", "read_file", "file_search"],
        duration_ms=321.7,
    )
    assert plugin_turn_hooks.flush(5.0)

    request = captured["request"]
    payload = request["arguments"]
    assert set(payload) == {
        "event",
        "plugin",
        "turn_id",
        "stop_reason",
        "tool_names",
        "duration_ms",
    }
    assert payload == {
        "event": "turn_end",
        "plugin": "acme-hook",
        "turn_id": "turn-42",
        "stop_reason": "answer",
        "tool_names": ["file_search", "read_file"],
        "duration_ms": 322,
    }
    for forbidden in ("answer", "history", "content", "messages", "context"):
        assert forbidden not in payload
    assert request["callable"] == "main"
    assert request["entry_file"] == str(directory / "hooks" / "turn_end.py")
    assert request["state_dir"] == str(mcp_sandbox.home_for("plugin_acme-hook"))

    spec = captured["spec"]
    assert spec.plugin_id == "acme-hook"
    assert Path(spec.plugin_dir) == directory
    assert spec.timeout_seconds == 2.0
    assert spec.launcher.endswith("worker_launcher.py")
    assert str(directory.resolve()) in spec.read_roots()
    assert captured["bridge"] is None

    rows = _rows(audit)
    assert [row["status"] for row in rows] == ["ok"]
    assert rows[0]["tool"] == "acme-hook"
    assert rows[0]["detail"] == "turn_end"
    assert isinstance(rows[0]["duration_ms"], int)


def test_a_turn_end_that_names_no_tool_carries_an_empty_list(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.sandbox import supervisor
    from core.sandbox.supervisor import WorkerOutcome

    _active(plugins)
    captured: list[dict] = []

    def fake_run_worker(spec, *, protocol_check=None, stdin_payload=None, bridge_dispatch=None):
        captured.append(json.loads(stdin_payload)["arguments"])
        return WorkerOutcome(status="ok")

    monkeypatch.setattr(supervisor, "run_worker", fake_run_worker)
    _dispatch(tool_names=[])
    assert plugin_turn_hooks.flush(5.0)
    assert captured[0]["tool_names"] == []
    assert captured[0]["stop_reason"] == "answer"


def test_the_turn_returns_before_the_run_completes(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _active(plugins)
    started = threading.Event()
    release = threading.Event()
    done = threading.Event()

    def blocking(hook, payload):
        started.set()
        release.wait(10)
        done.set()
        return "ok"

    monkeypatch.setattr(plugin_turn_hooks, "_execute", blocking)
    _dispatch()
    assert started.wait(5)
    assert not done.is_set()
    assert not plugin_turn_hooks.flush(0.05)
    release.set()
    assert plugin_turn_hooks.flush(10)
    assert done.is_set()


def test_the_run_is_registered_while_it_holds(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import plugin_activity

    _active(plugins)
    started = threading.Event()
    release = threading.Event()
    inflight: list[int] = []

    def blocking(hook, payload):
        inflight.append(plugin_activity.inflight_count(hook.plugin_id))
        started.set()
        release.wait(10)
        return "ok"

    monkeypatch.setattr(plugin_turn_hooks, "_execute", blocking)
    _dispatch()
    assert started.wait(5)
    assert inflight == [1]
    release.set()
    assert plugin_turn_hooks.flush(10)
    assert plugin_activity.inflight_count("acme-hook") == 0


def test_two_active_bundles_fire_in_plugin_id_order(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _active(plugins, "zulu")
    _active(plugins, "alpha")
    order: list[str] = []

    def record(hook, payload):
        order.append(hook.plugin_id)
        return "ok"

    monkeypatch.setattr(plugin_turn_hooks, "_execute", record)
    _dispatch()
    assert plugin_turn_hooks.flush(10)
    assert order == ["alpha", "zulu"]


def test_a_switched_off_bundle_spawns_nothing(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bundle(plugins, "acme-hook")
    mark_installed("acme-hook", enabled=False)
    calls: list[str] = []
    monkeypatch.setattr(
        plugin_turn_hooks, "_execute", lambda hook, payload: calls.append(hook.plugin_id)
    )
    _dispatch()
    assert plugin_turn_hooks.flush(5.0)
    assert calls == []
    assert _rows(audit) == []


def test_pause_all_spawns_nothing(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import plugin_runtime

    _active(plugins)
    plugin_runtime.lifecycle().set_pause_all(True)
    calls: list[str] = []
    monkeypatch.setattr(
        plugin_turn_hooks, "_execute", lambda hook, payload: calls.append(hook.plugin_id)
    )
    _dispatch()
    assert plugin_turn_hooks.flush(5.0)
    assert calls == []


def test_a_bundle_switched_off_before_the_worker_reaches_it_is_skipped(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import plugin_runtime

    _active(plugins)
    calls: list[str] = []
    monkeypatch.setattr(
        plugin_turn_hooks, "_execute", lambda hook, payload: calls.append(hook.plugin_id)
    )
    answers = iter([True, False])
    monkeypatch.setattr(plugin_runtime, "is_plugin_active", lambda *_: next(answers, False))
    _dispatch()
    assert plugin_turn_hooks.flush(5.0)
    assert calls == []
    assert [row["status"] for row in _rows(audit)] == ["inactive"]


def test_a_full_queue_drops_the_run_and_audits_it(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _active(plugins)
    started = threading.Event()
    release = threading.Event()
    runs: list[str] = []

    def blocking(hook, payload):
        runs.append(hook.plugin_id)
        started.set()
        release.wait(10)
        return "ok"

    monkeypatch.setattr(plugin_turn_hooks, "_execute", blocking)
    _dispatch()
    assert started.wait(5)
    for _ in range(plugin_turn_hooks.QUEUE_DEPTH):
        _dispatch()
    _dispatch()

    dropped = [row for row in _rows(audit) if row["status"] == "dropped"]
    assert len(dropped) == 1
    release.set()
    assert plugin_turn_hooks.flush(10)
    assert len(runs) == plugin_turn_hooks.QUEUE_DEPTH + 1


def test_a_raising_run_is_contained_and_audited(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _active(plugins)

    def boom(hook, payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(plugin_turn_hooks, "_execute", boom)
    _dispatch()
    assert plugin_turn_hooks.flush(5.0)
    assert [row["status"] for row in _rows(audit)] == ["refused"]


def test_a_claim_without_a_directory_is_refused(
    audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import plugin_runtime

    hook = TurnHook(
        plugin_id="acme-hook",
        event="turn_end",
        entry="hooks/turn_end.py:main",
        timeout_seconds=2,
    )
    monkeypatch.setattr(plugin_runtime, "turn_hooks", lambda: (hook,))
    monkeypatch.setattr(plugin_runtime, "is_plugin_active", lambda *_: True)
    spawned: list[str] = []
    from core.sandbox import supervisor

    monkeypatch.setattr(
        supervisor,
        "run_worker",
        lambda *a, **k: spawned.append("run"),
    )
    _dispatch()
    assert plugin_turn_hooks.flush(5.0)
    assert spawned == []
    assert [row["status"] for row in _rows(audit)] == ["refused"]


def test_a_measured_turn_runs_no_hook(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.chat as chat_module

    _active(plugins)
    calls: list[str] = []
    monkeypatch.setattr(
        plugin_turn_hooks, "_execute", lambda hook, payload: calls.append(hook.plugin_id)
    )
    seen: list[bool] = []

    async def fake_chat(**kwargs):
        seen.append(plugin_turn_hooks._SUPPRESSED.get())
        plugin_turn_hooks.note_turn_end(
            turn_id="bench", stop_reason="answer", tool_names=(), duration_ms=1
        )
        return "answer"

    monkeypatch.setattr(chat_module, "chat_with_tools", fake_chat)

    class _Engine:
        model = "test-model"

        def apply_env(self) -> None:
            pass

    from core import plugin_golden

    plugin_golden.run_measured({"id": "case-1", "input": "hi"}, _Engine())
    assert seen == [True]
    assert calls == []


@pytest.mark.requires_boundary
def test_the_hook_receives_the_metadata_payload_and_no_network(
    plugins: Path, audit: Path
) -> None:
    directory = _active(plugins, timeout=2)
    _dispatch(turn_id="turn-7", stop_reason="budget", tool_names=["run_shell"])
    assert plugin_turn_hooks.flush(10)

    home = mcp_sandbox.home_for("plugin_acme-hook")
    received = json.loads((home / "received.json").read_text(encoding="utf-8"))
    assert received == {
        "event": "turn_end",
        "plugin": "acme-hook",
        "turn_id": "turn-7",
        "stop_reason": "budget",
        "tool_names": ["run_shell"],
        "duration_ms": 12,
    }
    denied = (home / "network.txt").read_text(encoding="utf-8").strip()
    assert denied, "the worker reached the network, and the boundary promised it would not"
    assert (directory / "hooks" / "turn_end.py").is_file()
    assert [row["status"] for row in _rows(audit)] == ["ok"]


class _ScriptedClient:
    """`client.chat` hands out the queued responses; the last one repeats."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)

    async def chat(self, **kwargs):  # noqa: ARG002
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]

    async def aclose(self) -> None:
        return None


def _response(content: str = "", tool_calls=None):
    from unittest.mock import MagicMock

    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    response = MagicMock()
    response.message = message
    return response


def _read_calls():
    from unittest.mock import MagicMock

    function = MagicMock()
    function.name = "read_file"
    function.arguments = {"path": "notes.txt"}
    call = MagicMock()
    call.function = function
    return _response(tool_calls=[call])


@pytest.mark.asyncio
async def test_the_chat_finally_hands_the_turn_to_the_hook(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock, patch

    from core import loop_observability
    from core.chat import chat_with_tools

    client = _ScriptedClient([_read_calls(), _response(content="done")])
    handed: dict = {}
    callback_names: list[str] = []

    def fake_note(**kwargs):
        handed.update(kwargs)
        handed["observer_bound"] = loop_observability.current_observer() is not None

    monkeypatch.setattr(plugin_turn_hooks, "note_turn_end", fake_note)
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ):
        answer = await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "read notes.txt"}],
            on_chunk=lambda chunk: None,
            on_tool_start=lambda name, arguments, *call: callback_names.append(name),
            allowed_tool_names=["read_file"],
            max_tool_iterations=3,
            session_id="session-9",
            turn_id="turn-hook",
        )

    assert answer == "done"
    assert callback_names == ["read_file"]
    assert handed["turn_id"] == "turn-hook"
    assert handed["stop_reason"] == "answer"
    assert handed["tool_names"] == ["read_file"]
    assert handed["duration_ms"] > 0
    assert handed["observer_bound"] is True


@pytest.mark.asyncio
async def test_a_failing_hook_dispatch_leaves_the_turn_alone(
    plugins: Path, audit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock, patch

    from core.chat import chat_with_tools

    client = _ScriptedClient([_response(content="done")])

    def boom(**kwargs):
        raise RuntimeError("hook dispatch failed")

    monkeypatch.setattr(plugin_turn_hooks, "note_turn_end", boom)
    with patch("core.chat.build_provider_client", return_value=client), patch(
        "core.chat.execute_tool", new=AsyncMock(return_value="ok")
    ):
        answer = await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "hello"}],
            on_chunk=lambda chunk: None,
            allowed_tool_names=[],
        )

    assert answer == "done"
