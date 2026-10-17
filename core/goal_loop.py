"""Ephe – core/goal_loop: autonomous goal loop (W16-P1).

Pattern as in leading AI CLI clients: goal prompt -> the agent runs tools
-> a fixed check command (e.g. `pytest -q` / build) is evaluated ->
on failure one more turn automatically with the error output in context
(until max_turns or success). The loop is deliberately lightweight and
deterministic: only the check command counts, no model reflection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # the name is read by the checker; the policy itself is built in run()
    from core.tools.approval import ApprovalPolicy

#: Canonical failure signals in the check output (pytest/build convention).
_FAILED_RE = re.compile(r"\b(\d+)\s+failed\b", re.IGNORECASE)
_EXIT_RE = re.compile(r"\[exit\s+(\d+)\]", re.IGNORECASE)

#: The check a goal run is judged by, and the ceiling its turn chain stops at, when
#: the caller declares neither — `ephe goal` and the GUI's `/goal` read both here, so
#: the two surfaces cannot drift apart on the default.
DEFAULT_CHECK_COMMAND = "pytest -q"
DEFAULT_MAX_TURNS = 10


def _check_passed(output: str) -> bool:
    """Deterministic evaluation of the check command (no model call).

    Failure: a ⚠ rejection, [tool-error, an '[exit N]' where N != 0 or an
    'N failed' line where N > 0. Anything else counts as a passed check."""
    text = (output or "").strip()
    if not text:
        return False
    if text.startswith("⚠") or text.startswith("[tool-error"):
        return False
    exit_match = _EXIT_RE.search(text)
    if exit_match is not None and int(exit_match.group(1)) != 0:
        return False
    for match in _FAILED_RE.finditer(text):
        if int(match.group(1)) > 0:
            return False
    return True


@dataclass
class GoalResult:
    """Result of an autonomous goal run (for the log + the CLI output)."""

    goal: str
    success: bool
    turns: int
    check_output: str
    answer: str


class GoalRunner:
    """Autonomous goal worker: chat turn + check command + re-turn chain.

    Args:
        model:            model name for the provider system (as in cmd_code)
        check_command:    check command (runs via run_shell/execute_tool)
        max_turns:        ceiling for turn repetitions (default 10)
        on_event:         optional UI callback (kind, **payload) per phase
        turn_id:          run id the audit lines carry — the run record's filter (B1)
        on_phase:         optional callback for the agent loop's phase lines
        policy:           approval gate for the tool calls the loop makes. Without
                          one the headless CLI posture applies (auto-approved, no
                          prompt); a host that has its own gate — the server's
                          sandbox callback — passes it in instead of leaving the
                          loop a hole through that gate.
    """

    def __init__(
        self,
        *,
        model: str,
        check_command: str = DEFAULT_CHECK_COMMAND,
        max_turns: int = DEFAULT_MAX_TURNS,
        on_event: Callable[..., None] | None = None,
        turn_id: str = "",
        on_phase: Callable[[str], None] | None = None,
        policy: ApprovalPolicy | None = None,
    ) -> None:
        self.model = model
        self.check_command = check_command
        self.max_turns = max(1, int(max_turns))
        self.on_event = on_event
        # B1: the run record reads the tool and approval lines this turn writes to
        # the audit log, so it needs the turn id and the loop's own round phases.
        self.turn_id = turn_id
        self.on_phase = on_phase
        self.policy = policy

    async def run(self, goal: str) -> GoalResult:
        """ Runs the goal loop and returns the last result."""
        # Bind modules (not names): the paths stay current after a Monkeypatch
        # of the source modules (test isolation).
        import core.chat as _chat
        from core.tools.registry import execute_tool as _execute_tool
        from core.tools.approval import ApprovalPolicy

        history: list[dict] = [{"role": "user", "content": goal}]
        answer = ""
        check_output = ""
        policy = self.policy or ApprovalPolicy(auto_approve=True, interactive=False)
        # The loop's own state, before the first model call: the goal it works toward,
        # the check it will be judged by and the budget it has. A surface showing the
        # goal reads it here — the goal is the loop's, not a guess at the first message.
        self._emit("goal_start", goal=goal, check=self.check_command, max_turns=self.max_turns)

        for turn in range(1, self.max_turns + 1):
            answer = await _chat.chat_with_tools(
                model=self.model,
                history=list(history),
                on_chunk=lambda _t: None,
                on_phase=self.on_phase,
                turn_id=self.turn_id,
            ) or ""
            history.append({"role": "assistant", "content": answer})
            self._emit("goal_turn", turn=turn)

            check_output = await _execute_tool(
                "run_shell", {"command": self.check_command}, policy
            )
            ok = _check_passed(check_output)
            self._emit("goal_check", turn=turn, ok=ok, output=check_output[:400])
            if ok:
                return GoalResult(
                    goal=goal, success=True, turns=turn,
                    check_output=check_output, answer=answer,
                )

            history.append({
                "role": "user",
                "content": (
                    f"Der Pruefbefehl '{self.check_command}' schlug fehl:\n"
                    f"{check_output}\n"
                    "Korrigiere die Aenderungen und antworte mit der naechsten "
                    "Minimum-Aenderung."
                ),
            })

        return GoalResult(
            goal=goal, success=False, turns=self.max_turns,
            check_output=check_output, answer=answer,
        )

    def _emit(self, kind: str, **payload) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, **payload)
            except Exception:
                pass
