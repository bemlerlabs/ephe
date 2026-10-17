"""N24 blocker 11: a delegated tool call asks the person watching, or says it ran exempt.

``core.subagent.Subagent`` runs its own LLM loop over a tool whitelist and called
``core.tools.execute_tool`` with no policy — and ``execute_tool`` skips its gate
without one. An agent profile may widen that whitelist to a mutating tool, so the
call wrote to the host with nobody asked and no line written anywhere. The standing
rule leaves no room for that (AGENTS.md, no silent default); the bar is the record.

Pins:
1. A read-only helper call runs exempt, and the record says so.
2. A mutating helper call asks the person watching the run; a no leaves the file
   unwritten and reaches the helper as the denial.
3. A yes lets it run, and the record names the approval.
4. With no channel reachable the mutating call is denied, never executed.
5. Each decision lands in the audit log under the delegate status.
6. End to end through ``spawn_agent`` and a real agent profile.
7. A swarm-v2 agent's denied call is a figure on the wave — ``skipped_for_approval``
   reaches the wave snapshot and the ``swarm_done`` counters (N24 R1).
8. The swarm-v2 loop refuses ``run_shell`` before any execution, so it needs no
   shell-approval branch — and the old unaudited string is gone (N24 R2).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import subagent_history  # noqa: E402
from core.model_provider import (  # noqa: E402
    ProviderChatResponse,
    ProviderFunctionCall,
    ProviderMessage,
    ProviderToolCall,
)
from core.subagent import Subagent  # noqa: E402

EXEMPT = "exempt"
APPROVED = "approved"
DENIED = "denied"
DELEGATE_STATUS = "delegate-gate"


def _msg(content="", tool_calls=None):
    return ProviderChatResponse(message=ProviderMessage(content=content, tool_calls=tool_calls))


def _call(name, **args):
    return _msg(tool_calls=[ProviderToolCall(function=ProviderFunctionCall(name=name, arguments=args))])


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, *, model, messages, stream=False, tools=None, **_):
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    subagent_history.reset_for_test()
    yield tmp_path
    subagent_history.reset_for_test()


@pytest.fixture(autouse=True)
def active_model(monkeypatch):
    monkeypatch.setattr(
        "core.model_provider.get_active_provider",
        lambda: SimpleNamespace(model="active-model-x"),
    )


class _Watcher:
    """The dialog the person watching the run answers (SSE sets the same ContextVar)."""

    def __init__(self, answer: bool):
        self.answer = answer
        self.asked: list[str] = []
        self._token = None

    def __enter__(self):
        from core.vision import _sandbox_cb_var

        async def cb(name, args):
            self.asked.append(name)
            return self.answer

        self._token = _sandbox_cb_var.set(cb)
        return self

    def __exit__(self, *_exc):
        from core.vision import _sandbox_cb_var

        _sandbox_cb_var.reset(self._token)
        return False


class _NobodyListening:
    """No approval channel at all: CLI, cron, a headless run."""

    def __init__(self):
        self._token = None

    def __enter__(self):
        from core.vision import _sandbox_cb_var

        self._token = _sandbox_cb_var.set(None)
        return self

    def __exit__(self, *_exc):
        from core.vision import _sandbox_cb_var

        _sandbox_cb_var.reset(self._token)
        return False


def _run(tool_call, *, allowed_tools=None, agent_id="subagent-1"):
    client = _FakeClient([tool_call, _msg(content="report")])
    import core.model_provider as provider

    original = provider.build_provider_client
    provider.build_provider_client = lambda: client
    try:
        sub = Subagent(
            agent_id=agent_id, role="helper", task="t", allowed_tools=allowed_tools
        )
        return asyncio.run(sub.run())
    finally:
        provider.build_provider_client = original


def _gate_records(agent_id="subagent-1") -> list[str]:
    rec = subagent_history._mem[agent_id]
    return [str(entry.get("gate", "")) for entry in rec.get("tool_calls", [])]


def _audit_rows(tool: str) -> list[dict]:
    from core import audit_log

    path = audit_log.AUDIT_LOG_FILE
    if not Path(path).exists():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("kind") == "approval" and row.get("tool") == tool:
            rows.append(row)
    return rows


def test_given_a_read_only_helper_call_then_the_record_says_it_ran_exempt(tmp_path):
    """Rule 1 — the design's own exemption, written down."""
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    with _Watcher(answer=False) as watcher:
        result = _run(_call("read_file", path=str(target)))

    assert result.status == "ok"
    assert watcher.asked == []
    assert len(_gate_records()) == 1 and EXEMPT in _gate_records()[0]
    assert "read_file" in _gate_records()[0]


def test_given_a_mutating_helper_call_when_the_watcher_declines_then_nothing_is_written(tmp_path):
    """Rule 2 — the helper reaches the same dialog a main-turn call reaches."""
    target = tmp_path / "by-helper.txt"

    with _Watcher(answer=False) as watcher:
        _run(_call("write_file", path=str(target), content="silent"), allowed_tools=["write_file"])

    assert watcher.asked == ["write_file"]
    assert not target.exists()
    assert DENIED in _gate_records()[0]
    assert _audit_rows("write_file")[-1]["status"] == DELEGATE_STATUS
    assert _audit_rows("write_file")[-1]["decision"] == "denied"


def test_given_a_mutating_helper_call_when_the_watcher_approves_then_it_runs(tmp_path):
    """Rule 3 — an approved call runs, and the approval is the record."""
    target = tmp_path / "by-helper.txt"

    with _Watcher(answer=True) as watcher:
        _run(_call("write_file", path=str(target), content="approved"), allowed_tools=["write_file"])

    assert watcher.asked == ["write_file"]
    assert target.read_text(encoding="utf-8") == "approved"
    assert APPROVED in _gate_records()[0]
    assert _audit_rows("write_file")[-1]["decision"] == "approved"


def test_given_a_mutating_helper_call_with_no_channel_then_it_is_denied_not_run(tmp_path):
    """Rule 4 — no channel is a no, and the record says which no it was."""
    target = tmp_path / "by-helper.txt"

    with _NobodyListening():
        _run(_call("write_file", path=str(target), content="nobody-asked"), allowed_tools=["write_file"])

    assert not target.exists()
    assert DENIED in _gate_records()[0]
    assert "no approval channel" in _gate_records()[0]


def test_given_a_helper_gate_decision_then_the_exemption_is_audited_too(tmp_path):
    """Rule 5 — the exemption is a decision like any other, so it gets a row."""
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    with _Watcher(answer=False):
        _run(_call("read_file", path=str(target)))

    rows = _audit_rows("read_file")
    assert rows and rows[-1]["status"] == DELEGATE_STATUS
    assert rows[-1]["decision"] == EXEMPT


def test_given_an_agent_profile_that_widens_the_whitelist_then_the_gate_covers_it(tmp_path):
    """Rule 6 — the reachable route: a profile naming a mutating tool, end to end."""
    from core.tools import subagent_tool

    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agents" / "writer.json").write_text(
        json.dumps({"name": "writer", "tools": ["write_file"], "timeout": 60}),
        encoding="utf-8",
    )
    target = tmp_path / "from-profile.txt"

    import core.model_provider as provider

    original = provider.build_provider_client
    provider.build_provider_client = lambda: _FakeClient([
        _call("write_file", path=str(target), content="profile"),
        _msg(content="report"),
    ])
    try:
        with _Watcher(answer=False) as watcher:
            asyncio.run(subagent_tool.spawn_agent("profile run", "write it", subagent_type="writer"))
    finally:
        provider.build_provider_client = original

    assert watcher.asked == ["write_file"]
    assert not target.exists()


@pytest.mark.asyncio
async def test_given_a_swarm_agent_mutating_call_then_it_takes_the_same_gate(tmp_path):
    """Rule 7 — the finding's own words: a swarm agent calling a gated tool."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.swarm import _call_model

    target = tmp_path / "by-swarm.txt"
    call = MagicMock()
    call.function.name = "write_file"
    call.function.arguments = {"path": str(target), "content": "swarm"}
    first = MagicMock()
    first.message.content = ""
    first.message.tool_calls = [call]
    second = MagicMock()
    second.message.content = "swarm answer"
    client = MagicMock()
    client.chat = AsyncMock(side_effect=[first, second])

    with _Watcher(answer=False) as watcher, \
            patch("core.swarm._make_client", return_value=client), \
            patch("core.tools.get_tool_schemas", return_value=[]):
        result = await _call_model("sys", "user", "model", use_tools=True)

    assert result == "swarm answer"
    assert watcher.asked == ["write_file"]
    assert not target.exists()
    rows = _audit_rows("write_file")
    assert rows and rows[-1]["status"] == DELEGATE_STATUS
    assert rows[-1]["decision"] == "denied"


# N24 R1 — the gate outcome is a figure on the wave, never a discard.

def test_given_a_wave_counter_then_a_gate_skip_is_a_figure_on_the_snapshot():
    """Rule 7 (unit) — a refused call is counted as one tool skipped for approval."""
    from core.swarm_v2 import WaveCounters

    counters = WaveCounters(total=2, cap=2)
    assert counters.snapshot()["skipped_for_approval"] == 0

    counters.record_gate_skip()
    counters.record_gate_skip()

    assert counters.snapshot()["skipped_for_approval"] == 2


@pytest.mark.asyncio
async def test_given_a_swarm_v2_agent_denied_then_the_wave_counts_it_as_skipped(tmp_path):
    """Rule 7 — the v2 loop keeps ``_gate_note``'s outcome as a figure, not a discard."""
    import core.model_provider as provider
    from core.swarm_state import SwarmStateStore
    from core.swarm_v2 import SwarmAgent, WaveCounters

    target = tmp_path / "by-swarm-v2.txt"
    client = _FakeClient([
        _call("write_file", path=str(target), content="swarm-v2"),
        _msg(content="done"),
    ])

    original = provider.build_provider_client
    provider.build_provider_client = lambda: client
    counters = WaveCounters(total=1, cap=1)
    agent = SwarmAgent(
        agent_id="swarm-v2-agent", role="researcher", subtask="write it",
        main_task="write it", model="test-model", state_store=SwarmStateStore(),
        swarm_id="swarm-v2", tool_whitelist=["write_file"],
    )
    agent.wave = counters
    try:
        with _NobodyListening():
            envelope = await agent.run()
    finally:
        provider.build_provider_client = original

    assert envelope.status == "ok"
    assert not target.exists()
    assert counters.snapshot()["skipped_for_approval"] == 1
    rows = _audit_rows("write_file")
    assert rows and rows[-1]["status"] == DELEGATE_STATUS
    assert rows[-1]["decision"] == "denied"


@pytest.mark.asyncio
async def test_given_a_swarm_v2_wave_then_the_skip_figure_reaches_swarm_done(monkeypatch):
    """Rule 7 — the orchestrator attaches the counters, and swarm_done carries them."""
    from core.swarm_state import SwarmStateStore
    from core.swarm_v2 import SwarmAgent, SwarmOrchestrator, _make_envelope

    events: list[dict] = []
    orch = SwarmOrchestrator(
        task="write it", model="test-model",
        on_event=events.append, state_store=SwarmStateStore(),
    )

    async def manager(self):
        return {"count": 1, "role": "researcher", "subtasks": ["sub-1"], "task_type": "general"}

    async def synthesize(self, subtasks, results):
        return "final answer"

    async def run(self):
        # What the real loop does on a gate denial — counted on the attached wave.
        self.wave.record_gate_skip()
        return _make_envelope(self.agent_id, "answer", run_id=self.run_id)

    monkeypatch.setattr(SwarmOrchestrator, "_run_manager", manager)
    monkeypatch.setattr(SwarmOrchestrator, "_synthesize", synthesize)
    monkeypatch.setattr(SwarmAgent, "run", run)

    result = await orch.run()

    assert result.counters["skipped_for_approval"] == 1
    done = [event for event in events if event.get("type") == "swarm_done"]
    assert done and done[-1]["counters"]["skipped_for_approval"] == 1


# N24 R2 — no unaudited shell-approval swallow in the swarm-v2 loop.

@pytest.mark.asyncio
async def test_given_a_swarm_v2_agent_shell_call_then_it_never_reaches_execution(monkeypatch):
    """Rule 8 — run_shell is refused before the gate, so no shell path is taken."""
    import core.model_provider as provider
    from core.swarm_state import SwarmStateStore
    from core.swarm_v2 import SwarmAgent

    executed: list[str] = []

    async def _fake_execute(name, args, *extra, **kwargs):
        executed.append(name)
        return "ran"

    client = _FakeClient([
        _call("run_shell", command="touch /tmp/swarm-v2-should-not-exist"),
        _msg(content="done"),
    ])

    original = provider.build_provider_client
    provider.build_provider_client = lambda: client
    agent = SwarmAgent(
        agent_id="swarm-v2-shell", role="researcher", subtask="shell", main_task="shell",
        model="test-model", state_store=SwarmStateStore(), swarm_id="swarm-v2-shell",
        tool_whitelist=["run_shell"],
    )
    monkeypatch.setattr("core.tools.execute_tool", _fake_execute)
    try:
        with _NobodyListening():
            envelope = await agent.run()
    finally:
        provider.build_provider_client = original

    assert envelope.status == "ok"
    assert executed == []


def test_swarm_v2_carries_no_unaudited_shell_confirmation_swallow():
    """Rule 8 — the bare swallow string and its handler are gone from the module."""
    source = (PROJECT_ROOT / "core" / "swarm_v2.py").read_text(encoding="utf-8")
    assert "shell approval not available inside swarm" not in source
    assert "except ShellConfirmationRequired" not in source
