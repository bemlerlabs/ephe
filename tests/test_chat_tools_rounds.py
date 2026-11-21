"""WA-5: the tool-round loop's gate, error-budget and retry branches.

Covers what the safe-path tests leave out: the chat gate's denial branch, the
CLI approval policy on run_shell (approved/denied, cwd pass-through), the
error-round budget with its success reset, the follow-up retry and the
connection mapping, and the open-plan nudge round.
"""
from __future__ import annotations

import asyncio

import pytest

from core.chat_tools import _run_tool_loop
from core.model_provider import (
    ProviderChatResponse,
    ProviderFunctionCall,
    ProviderMessage,
    ProviderToolCall,
)
from core.tools import ShellConfirmationRequired
from core.tools.approval import ApprovalPolicy
from core.tools.chat_gate import DENIAL_PREFIX


class _LocalProvider:
    provider = "local_ollama"


class _ScriptedClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.attempts = 0

    async def chat(self, **kwargs):
        self.attempts += 1
        return self._responses.pop(0)


class _FlakyClient:
    """Raises ``failures`` times, then serves the scripted responses."""

    def __init__(self, responses, failures, exc_factory=lambda: RuntimeError("boom")):
        self._responses = list(responses)
        self._failures = failures
        self._exc_factory = exc_factory
        self.attempts = 0

    async def chat(self, **kwargs):
        self.attempts += 1
        if self.attempts <= self._failures:
            raise self._exc_factory()
        return self._responses.pop(0)


def _call_response(name, arguments):
    return ProviderChatResponse(
        ProviderMessage(
            tool_calls=[ProviderToolCall(function=ProviderFunctionCall(name=name, arguments=arguments))]
        )
    )


def _final_response(text="done"):
    return ProviderChatResponse(ProviderMessage(content=text))


async def _no_sleep(*_args, **_kwargs):
    return None


class _Loop:
    """Runs the loop and exposes the callbacks the branches fire."""

    def __init__(self):
        self.phases: list[str] = []
        self.started: list[tuple[str, dict, str]] = []
        self.done: list[tuple[str, str, str]] = []

    def on_phase(self, text):
        self.phases.append(text)

    def on_tool_start(self, name, args, call_id):
        self.started.append((name, args, call_id))

    def on_tool_done(self, name, result, call_id):
        self.done.append((name, result, call_id))


async def _run(
    monkeypatch,
    responses,
    *,
    provider=None,
    approval_policy=None,
    on_shell_confirm=None,
    on_tool_confirm=None,
    budget_cap=8,
    client=None,
):
    loop = _Loop()
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
    client = client or _ScriptedClient(responses[1:])
    result = await _run_tool_loop(
        client=client,
        provider=provider or _LocalProvider(),
        model="gemma4:12b",
        messages=messages,
        tools=[],
        response=responses[0],
        detection_streamed=False,
        on_chunk=lambda *_: None,
        on_thinking=None,
        on_tool_start=loop.on_tool_start,
        on_tool_done=loop.on_tool_done,
        on_phase=loop.on_phase,
        on_shell_confirm=on_shell_confirm,
        on_tool_confirm=on_tool_confirm,
        approval_policy=approval_policy,
        budget_cap=budget_cap,
        turn_id="t",
    )
    return result, messages, loop, client


def _tool_messages(messages):
    return [m for m in messages if isinstance(m, dict) and m.get("role") == "tool"]


def _patch_executor(monkeypatch, executor):
    monkeypatch.setattr("core.chat.execute_tool", executor)


def _patch_shell(monkeypatch):
    calls: list[tuple] = []

    async def shell(command, confirmed, cwd=None):
        calls.append((command, confirmed, cwd))
        return f"shell ran: {command}"

    monkeypatch.setattr("core.chat.execute_confirmed_shell", shell)
    return calls


# Chat gate, policy None

@pytest.mark.asyncio
async def test_denial_branch_records_denial_and_skips_tool(monkeypatch):
    calls: list = []

    async def executor(name, args, policy=None):
        calls.append(name)
        return "should not run"

    _patch_executor(monkeypatch, executor)
    monkeypatch.setattr("core.chat._tool_detection_timeout", lambda _m: 1.0)

    async def no(_name, _args):
        return False

    responses = [_call_response("write_file", {"path": "x", "content": "y"}), _final_response()]
    _, messages, loop, client = await _run(
        monkeypatch, responses, on_tool_confirm=no
    )

    tool_msgs = _tool_messages(messages)
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["content"].startswith(DENIAL_PREFIX)
    assert "write_file" in tool_msgs[0]["content"]
    assert calls == []
    # on_tool_done still fires with the denial text, so the card shows the refusal
    assert loop.done and loop.done[0][0] == "write_file"
    assert client.attempts == 1


@pytest.mark.asyncio
async def test_confirm_true_runs_tool_without_policy(monkeypatch):
    seen: list = []

    async def executor(name, args, policy=None):
        seen.append((name, policy))
        return "ok"

    _patch_executor(monkeypatch, executor)

    async def yes(_name, _args):
        return True

    responses = [_call_response("write_file", {"path": "x"}), _final_response()]
    _, messages, _loop, _client = await _run(monkeypatch, responses, on_tool_confirm=yes)

    assert seen == [("write_file", None)]
    assert _tool_messages(messages)[0]["content"] == "ok"


@pytest.mark.asyncio
async def test_policy_present_skips_chat_gate_and_forwards_policy(monkeypatch):
    seen: list = []

    async def executor(name, args, policy=None):
        seen.append((name, policy))
        return "ok"

    _patch_executor(monkeypatch, executor)
    policy = ApprovalPolicy(auto_approve=True)

    # A mutating tool with a policy must not go through confirm_for_chat.
    async def explode(*_a, **_k):
        raise AssertionError("chat gate must not be consulted when a policy is set")

    responses = [_call_response("write_file", {"path": "x"}), _final_response()]
    _, _messages, _loop, _client = await _run(
        monkeypatch, responses, approval_policy=policy, on_tool_confirm=explode
    )

    assert seen == [("write_file", policy)]


# run_shell under the CLI approval policy

@pytest.mark.asyncio
async def test_shell_policy_approved_passes_cwd(monkeypatch):
    shell_calls = _patch_shell(monkeypatch)

    async def approve(_name, _args):
        return True

    policy = ApprovalPolicy(on_confirm=approve)
    responses = [_call_response("run_shell", {"command": "ls", "cwd": "/tmp"}), _final_response()]
    _, messages, _loop, _client = await _run(monkeypatch, responses, approval_policy=policy)

    assert shell_calls == [("ls", True, "/tmp")]
    assert _tool_messages(messages)[0]["content"] == "shell ran: ls"


@pytest.mark.asyncio
async def test_shell_policy_denied_blocks_execution(monkeypatch):
    shell_calls = _patch_shell(monkeypatch)

    async def deny(_name, _args):
        return False

    policy = ApprovalPolicy(on_confirm=deny)
    responses = [_call_response("run_shell", {"command": "rm -rf /"}), _final_response()]
    _, messages, _loop, _client = await _run(monkeypatch, responses, approval_policy=policy)

    assert shell_calls == []
    content = _tool_messages(messages)[0]["content"]
    assert "denied via callback" in content


@pytest.mark.asyncio
async def test_shell_no_policy_sync_confirm_callback(monkeypatch):
    shell_calls = _patch_shell(monkeypatch)
    responses = [_call_response("run_shell", {"command": "ls", "cwd": "/work"}), _final_response()]
    _, messages, _loop, _client = await _run(
        monkeypatch, responses, on_shell_confirm=lambda _cmd: True
    )

    assert shell_calls == [("ls", True, "/work")]
    assert _tool_messages(messages)[0]["content"] == "shell ran: ls"


@pytest.mark.asyncio
async def test_shell_no_policy_awaitable_confirm_callback(monkeypatch):
    shell_calls = _patch_shell(monkeypatch)

    async def confirm(_cmd):
        return True

    responses = [_call_response("run_shell", {"command": "pwd"}), _final_response()]
    _, _messages, _loop, _client = await _run(monkeypatch, responses, on_shell_confirm=confirm)

    assert shell_calls == [("pwd", True, None)]


@pytest.mark.asyncio
async def test_shell_no_policy_no_callback_raises(monkeypatch):
    _patch_shell(monkeypatch)
    responses = [_call_response("run_shell", {"command": "ls"}), _final_response()]

    with pytest.raises(ShellConfirmationRequired):
        await _run(monkeypatch, responses)


# Error-round budget

@pytest.mark.asyncio
async def test_error_rounds_exhaust_repair_budget(monkeypatch):
    async def boom(_name, _args, policy=None):
        raise ValueError("kaboom")

    _patch_executor(monkeypatch, boom)
    # Every round errors, so the loop stops once consecutive_error_rounds > MAX_REPAIRS_PER_STEP (2).
    responses = [_call_response("read_file", {"path": f"f{i}"}) for i in range(4)]
    responses.append(_final_response())
    result, messages, _loop, client = await _run(
        monkeypatch, responses, budget_cap=10
    )

    iteration = result[0]
    assert iteration == 3
    assert client.attempts == 3
    tool_msgs = _tool_messages(messages)
    assert len(tool_msgs) == 3
    assert all(m["content"].startswith("[TOOL-ERROR]") for m in tool_msgs)


@pytest.mark.asyncio
async def test_success_resets_error_round_budget(monkeypatch):
    state = {"n": 0}

    async def flaky(_name, _args, policy=None):
        state["n"] += 1
        if state["n"] % 2 == 1:
            raise ValueError("kaboom")
        return "ok"

    _patch_executor(monkeypatch, flaky)
    # Alternating error/success would stop after 3 rounds without the reset; with it, all 6 run.
    responses = [_call_response("read_file", {"path": f"f{i}"}) for i in range(6)]
    responses.append(_final_response())
    result, _messages, _loop, client = await _run(monkeypatch, responses, budget_cap=10)

    assert result[0] == 6
    assert client.attempts == 6


# Follow-up retry

@pytest.mark.asyncio
async def test_follow_up_retry_recovers_after_transient_failures(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    async def executor(_name, _args, policy=None):
        return "ok"

    _patch_executor(monkeypatch, executor)
    client = _FlakyClient([_final_response("recovered")], failures=2)
    responses = [_call_response("read_file", {"path": "x"})]
    result, _messages, _loop, _client = await _run(monkeypatch, responses, client=client)

    assert client.attempts == 3
    assert result[2].message.content == "recovered"


@pytest.mark.asyncio
async def test_follow_up_retry_exhausted_raises(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    async def executor(_name, _args, policy=None):
        return "ok"

    _patch_executor(monkeypatch, executor)
    client = _FlakyClient([], failures=99)
    responses = [_call_response("read_file", {"path": "x"})]

    with pytest.raises(RuntimeError):
        await _run(monkeypatch, responses, client=client)
    # 1 + max_retries (2) attempts before the last error is re-raised
    assert client.attempts == 3


@pytest.mark.asyncio
async def test_connection_error_maps_to_ollama_unreachable(monkeypatch):
    from core.chat_stream import OllamaNotReachableError

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    async def executor(_name, _args, policy=None):
        return "ok"

    _patch_executor(monkeypatch, executor)
    client = _FlakyClient([], failures=99, exc_factory=lambda: ConnectionError("connection refused"))
    responses = [_call_response("read_file", {"path": "x"})]

    with pytest.raises(OllamaNotReachableError):
        await _run(monkeypatch, responses, client=client)


# Open-plan nudge round

@pytest.mark.asyncio
async def test_nudge_round_runs_a_tool_round(monkeypatch):
    monkeypatch.setattr("core.chat_tools._continue_attempts", lambda: 1)

    async def executor(_name, _args, policy=None):
        return "ok"

    _patch_executor(monkeypatch, executor)
    plan = ProviderChatResponse(ProviderMessage(content="Step 1: read the file."))
    responses = [plan, _call_response("read_file", {"path": "x"}), _final_response()]
    result, messages, loop, client = await _run(monkeypatch, responses)

    assert result[0] == 1
    assert client.attempts == 2
    assert any("nudge 1" in phase for phase in loop.phases)
    assert _tool_messages(messages)[0]["content"] == "ok"


# Call-ID spans

@pytest.mark.asyncio
async def test_tool_start_and_done_share_call_id(monkeypatch):
    async def executor(_name, _args, policy=None):
        return "ok"

    _patch_executor(monkeypatch, executor)
    responses = [_call_response("read_file", {"path": "x"}), _final_response()]
    _, _messages, loop, _client = await _run(monkeypatch, responses)

    assert len(loop.started) == 1 and len(loop.done) == 1
    assert loop.started[0][2] == loop.done[0][2]
