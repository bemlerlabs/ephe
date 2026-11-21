"""The goal loop's state on a surface — `/goal` in the chat, its way to the panel.

The gap this closes (register #50): goal control lived only in `ephe goal`, and the
status panel's "Goal" section showed the first line of the session's first message —
an echo, not the goal. The loop already keeps the goal, the check command and the
turn budget; the frames carry it, and the panel reads it there.

Pinned here:
  * the command registry names /goal and its parser reads the same three values the
    CLI's two flags name,
  * the loop emits `goal_start` with those three values before its first model call,
  * the route relays what the loop emits (`goal_start` → `goal_turn` → `goal_check`)
    and closes the turn with the CLI's own GOAL OK/FAILED sentence,
  * the loop's tool calls go through the route's approval gate — its headless
    auto-approve posture would be a hole in the gate the route owns,
  * ask and plan mode refuse the command instead of running tools behind a mode
    that promises none.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import core.goal_loop as goal_loop
from core.commands import (
    COMMANDS,
    GOAL_COMMANDS,
    _COMMAND_DESCRIPTIONS,
    get_completions,
    is_goal_command,
    parse_goal_command,
)
from core.goal_loop import (
    DEFAULT_CHECK_COMMAND,
    DEFAULT_MAX_TURNS,
    GoalResult,
    GoalRunner,
)
from server.routes import chat as chat_route


# the registry

def test_the_goal_command_is_registered_like_its_siblings():
    """Given the slash registry, When /goal is looked up,
    Then it is a special (app-handled) command with a description and a completion."""
    assert "/goal" in COMMANDS
    assert COMMANDS["/goal"] == "__goal__:{input}"
    assert _COMMAND_DESCRIPTIONS["/goal"]
    assert "/goal" in get_completions("/")
    assert GOAL_COMMANDS == frozenset({"/goal"})
    assert is_goal_command("/goal ship it") is True
    assert is_goal_command("/goals ship it") is False
    assert is_goal_command("goal ship it") is False


# the parser: the three values the loop is configured with

@pytest.mark.parametrize(
    "text,task,check,max_turns",
    [
        ("/goal", "", DEFAULT_CHECK_COMMAND, DEFAULT_MAX_TURNS),
        ("/goal Fix the login bug", "Fix the login bug", DEFAULT_CHECK_COMMAND, DEFAULT_MAX_TURNS),
        ("/goal Fix it --max-turns 2", "Fix it", DEFAULT_CHECK_COMMAND, 2),
        ('/goal Fix it --check "npm test"', "Fix it", "npm test", DEFAULT_MAX_TURNS),
        (
            '/goal --check "pytest -q tests/x.py" ship the fix --max-turns 3',
            "ship the fix",
            "pytest -q tests/x.py",
            3,
        ),
        # A flag whose value is not a number keeps the loop's default: the emitted
        # state carries what was used, so no surface shows a budget nobody obeys.
        ("/goal Fix it --max-turns nope", "Fix it", DEFAULT_CHECK_COMMAND, DEFAULT_MAX_TURNS),
        ('/goal Fix it --check', "Fix it", DEFAULT_CHECK_COMMAND, DEFAULT_MAX_TURNS),
        # An unclosed quote is not a parse error the user has to solve: the target
        # stays readable and the defaults hold.
        ('/goal Fix "the bug', 'Fix "the bug', DEFAULT_CHECK_COMMAND, DEFAULT_MAX_TURNS),
    ],
)
def test_parse_goal_command_names_the_same_three_values_as_the_cli(text, task, check, max_turns):
    spec = parse_goal_command(text)
    assert (spec.task, spec.check, spec.max_turns) == (task, check, max_turns)


def test_parse_goal_command_keeps_the_task_words_in_order():
    spec = parse_goal_command("/goal the build is red --max-turns 4 again")
    assert spec.task == "the build is red again"


# the loop's own state, emitted before its first model call

@pytest.fixture
def fake_loop(monkeypatch):
    """core.chat.chat_with_tools and the tool registry are faked, as in W16."""
    import core.chat as cc
    from core.tools import registry as reg

    state: dict = {"chat_calls": [], "chat_responses": [], "checks": [], "policies": []}

    async def fake_chat(**kwargs):
        state["chat_calls"].append(kwargs)
        return state["chat_responses"].pop(0)

    async def fake_exec(name, args, policy=None):
        state["checks"].append(args["command"])
        state["policies"].append(policy)
        return state["check_outputs"].pop(0)

    monkeypatch.setattr(cc, "chat_with_tools", fake_chat)
    monkeypatch.setattr(reg, "execute_tool", fake_exec)
    return state


@pytest.mark.asyncio
async def test_the_loop_emits_its_goal_check_and_budget_first(fake_loop):
    fake_loop["chat_responses"] = ["done"]
    fake_loop["check_outputs"] = ["ok"]
    seen: list[tuple[str, dict]] = []
    runner = GoalRunner(model="m", check_command="npm test", max_turns=3,
                        on_event=lambda kind, **payload: seen.append((kind, payload)))
    await runner.run("Fix the login bug")

    kind, payload = seen[0]
    assert kind == "goal_start"
    assert payload == {"goal": "Fix the login bug", "check": "npm test", "max_turns": 3}
    assert [k for k, _ in seen] == ["goal_start", "goal_turn", "goal_check"]
    # The goal also reaches the agent itself — the state and the prompt are one goal.
    assert fake_loop["chat_calls"][0]["history"][-1]["content"] == "Fix the login bug"


@pytest.mark.asyncio
async def test_an_injected_policy_is_the_gate_the_check_runs_through(fake_loop):
    """Given a host with its own approval gate, When the loop runs a check,
    Then that policy — not the headless auto-approve default — decides the call."""
    from core.tools.approval import ApprovalPolicy

    fake_loop["chat_responses"] = ["done"]
    fake_loop["check_outputs"] = ["ok"]
    asked: list[tuple[str, dict]] = []

    async def confirm(tool_name, arguments):
        asked.append((tool_name, arguments))
        return True

    policy = ApprovalPolicy(auto_approve=False, interactive=False, on_confirm=confirm)
    await GoalRunner(model="m", check_command="npm test", policy=policy).run("Ziel")

    assert fake_loop["policies"] == [policy]
    assert fake_loop["policies"][0].auto_approve is False


# the route: the frames, and the gate it keeps

class _FakeGoalRunner:
    """The loop's shape only — the route's job is to relay what the loop emits."""

    created: dict = {}

    def __init__(self, *, model, check_command, max_turns=DEFAULT_MAX_TURNS, on_event=None,
                 policy=None, **kwargs):
        self.__class__.created = {
            "model": model, "check_command": check_command,
            "max_turns": max_turns, "on_event": on_event, "policy": policy,
        }
        self.check_command = check_command
        self.max_turns = max_turns
        self.on_event = on_event

    async def run(self, goal):
        relay = self.on_event
        assert relay is not None  # the route always passes its relaying callback
        relay("goal_start", goal=goal, check=self.check_command, max_turns=self.max_turns)
        relay("goal_turn", turn=1)
        relay("goal_check", turn=1, ok=False, output="1 failed in 0.2s")
        return GoalResult(goal=goal, success=False, turns=2,
                          check_output="1 failed in 0.2s", answer="next try")


async def _stream(monkeypatch, message: str, *, mode: str = "agent") -> list[dict]:
    """Drive the real /chat/stream generator with the loop replaced; return the frames."""
    _FakeGoalRunner.created = {}  # the class attribute outlives one test
    monkeypatch.setattr(goal_loop, "GoalRunner", _FakeGoalRunner)
    req = chat_route.StreamRequest(message=message, session_id="s-goal", mode=mode)
    resp = await chat_route.chat_stream(req)
    gen = resp.body_iterator
    raw: list[str] = []
    while True:
        try:
            raw.append(await asyncio.wait_for(gen.__anext__(), 5.0))  # type: ignore[attr-defined]
        except StopAsyncIteration:
            break
    events: list[dict] = []
    for part in "".join(raw).split("\n\n"):
        part = part.strip()
        if part.startswith("data: "):
            events.append(json.loads(part[len("data: "):]))
    return events


@pytest.mark.asyncio
async def test_the_route_relays_the_loops_state_and_closes_with_its_sentence(monkeypatch):
    frames = await _stream(monkeypatch, '/goal Fix the login bug --check "npm test" --max-turns 4')
    types = [f.get("type") for f in frames]

    start = next(f for f in frames if f.get("type") == "goal_start")
    assert start["goal"] == "Fix the login bug"
    assert start["check"] == "npm test"
    assert start["max_turns"] == 4
    assert types.index("goal_start") < types.index("goal_turn") < types.index("goal_check")
    assert types[-1] == "done"

    text = "".join(f.get("data", "") for f in frames if f.get("type") == "chunk")
    assert "GOAL FAILED" in text and "check command: `npm test`" in text
    assert "1 failed in 0.2s" in text

    # The route configured the loop with the parsed values and its own gate.
    assert _FakeGoalRunner.created["check_command"] == "npm test"
    assert _FakeGoalRunner.created["max_turns"] == 4
    assert _FakeGoalRunner.created["policy"].auto_approve is False
    assert _FakeGoalRunner.created["policy"].on_confirm is not None


@pytest.mark.asyncio
async def test_a_goal_without_a_target_only_shows_the_usage_hint(monkeypatch):
    frames = await _stream(monkeypatch, "/goal")
    types = [f.get("type") for f in frames]
    assert "goal_start" not in types
    assert types[-1] == "done"
    text = "".join(f.get("data", "") for f in frames if f.get("type") == "chunk")
    assert "/goal <target>" in text
    assert _FakeGoalRunner.created == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ask", "plan"])
async def test_ask_and_plan_mode_refuse_the_command_instead_of_running_tools(monkeypatch, mode):
    frames = await _stream(monkeypatch, "/goal Fix the login bug", mode=mode)
    types = [f.get("type") for f in frames]
    assert "goal_start" not in types  # the loop never started
    assert types[-1] == "done"
    text = "".join(f.get("data", "") for f in frames if f.get("type") == "chunk")
    assert "ask or plan mode" in text
    assert _FakeGoalRunner.created == {}


@pytest.mark.asyncio
async def test_an_unreachable_engine_is_one_named_error_frame(monkeypatch):
    class _Raiser(_FakeGoalRunner):
        async def run(self, goal):
            from core.chat import OllamaNotReachableError

            raise OllamaNotReachableError()

    monkeypatch.setattr(goal_loop, "GoalRunner", _Raiser)
    req = chat_route.StreamRequest(message="/goal Fix it", session_id="s-goal")
    resp = await chat_route.chat_stream(req)
    gen = resp.body_iterator
    raw: list[str] = []
    while True:
        try:
            raw.append(await asyncio.wait_for(gen.__anext__(), 5.0))  # type: ignore[attr-defined]
        except StopAsyncIteration:
            break
    frames = [json.loads(p[len("data: "):]) for p in "".join(raw).split("\n\n")
              if p.strip().startswith("data: ")]
    errors = [f for f in frames if f.get("type") == "error"]
    assert len(errors) == 1
    # The engine's own hint has to survive into the frame (R37).
    assert "ollama serve" in errors[0]["msg"]
    assert frames[-1] == {"type": "done"}
