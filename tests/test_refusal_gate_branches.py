"""The refusal branches of the approval and chat gates, pinned.

`request_approval` has four refusal-shaped outcomes and two file-touching ones.
The suite covered the denied callback, the dry-run report, `--no` and the
non-interactive deny; the interactive TTY prompt (`Execute? [y/N]`) existed
only in the module — no test ever answered it. Same for the precedence between
two contradictory levers: argparse keeps `--yes` and `--no` apart, but
`--yes --dry-run` parses, and the gate's own docstring calls its order
conservative. The contract pinned here: a no-execute lever outranks an execute
lever, so the pair resolves to the one that touches nothing.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

from core.tools.approval import (  # noqa: E402
    SAFE_TOOLS,
    ApprovalPolicy,
    classify_tool,
    request_approval,
)
from core.tools.chat_gate import (  # noqa: E402
    DENIAL_PREFIX,
    confirm_for_chat,
    denial_message,
)
from core.tools.registry import execute_tool  # noqa: E402


class TestInteractivePrompt:
    """The `input()` branch of `request_approval` — first tests to reach it."""

    def test_yes_runs_and_the_prompt_carries_the_diff(self, monkeypatch):
        prompts: list[str] = []

        def _answer(prompt: str) -> str:
            prompts.append(prompt)
            return "y"

        monkeypatch.setattr("builtins.input", _answer)
        decision = asyncio.run(
            request_approval("run_shell", {"command": "ls -la"}, ApprovalPolicy(interactive=True))
        )
        assert decision.approved is True
        assert decision.dry_run is False
        assert "confirmed interactively" in decision.report
        assert prompts and "[Approval]" in prompts[0]
        assert "ls -la" in prompts[0]  # the diff is the prompt, not a bare question

    def test_yes_survives_case_and_padding(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _prompt: "  YeS ")
        decision = asyncio.run(
            request_approval("create_svg", {"filename": "x.svg"}, ApprovalPolicy(interactive=True))
        )
        assert decision.approved is True

    @pytest.mark.parametrize("answer", ["", "n", "no", "later"])
    def test_anything_but_yes_denies(self, monkeypatch, answer):
        monkeypatch.setattr("builtins.input", lambda _prompt: answer)
        decision = asyncio.run(
            request_approval("run_shell", {"command": "ls"}, ApprovalPolicy(interactive=True))
        )
        assert decision.approved is False
        assert decision.dry_run is False
        assert "denied interactively" in decision.report

    def test_eof_on_the_prompt_denies_instead_of_raising(self, monkeypatch):
        def _eof(_prompt: str) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", _eof)
        decision = asyncio.run(
            request_approval("run_shell", {"command": "ls"}, ApprovalPolicy(interactive=True))
        )
        assert decision.approved is False
        assert "denied interactively" in decision.report

    def test_a_denied_prompt_executes_nothing(self, tmp_path, monkeypatch, werkbank):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr("builtins.input", lambda _prompt: "n")
        result = asyncio.run(execute_tool(
            "create_svg",
            {"svg_code": "<svg><rect/></svg>", "filename": "interactive_no.svg"},
            policy=ApprovalPolicy(interactive=True),
        ))
        assert "Denied" in result
        assert not (tmp_path / "Downloads" / "interactive_no.svg").exists()
        assert not (werkbank / "interactive_no.svg").exists()


class TestContradictoryLeversResolveToTheSafeOne:
    def test_declined_beats_auto_approve(self, monkeypatch):
        monkeypatch.setattr(
            "builtins.input", lambda _prompt: pytest.fail("the TTY must not be asked")
        )
        decision = asyncio.run(request_approval(
            "run_shell",
            {"command": "ls"},
            ApprovalPolicy(declined=True, auto_approve=True, interactive=True),
        ))
        assert decision.approved is False
        assert "(--no)" in decision.report

    def test_dry_run_beats_auto_approve_and_touches_nothing(self, tmp_path, monkeypatch, werkbank):
        """`--dry-run` is a no-touch promise; given `--yes` as well, nothing may execute."""
        monkeypatch.setenv("HOME", str(tmp_path))
        policy = ApprovalPolicy(auto_approve=True, dry_run=True)
        decision = asyncio.run(request_approval("create_svg", {"filename": "dry_yes.svg"}, policy))
        assert decision.approved is False
        assert decision.dry_run is True
        result = asyncio.run(execute_tool(
            "create_svg",
            {"svg_code": "<svg><rect/></svg>", "filename": "dry_yes.svg"},
            policy=policy,
        ))
        assert "DRY-RUN" in result.upper()
        assert not (tmp_path / "Downloads" / "dry_yes.svg").exists()
        assert not (werkbank / "dry_yes.svg").exists()


def test_e2e_cli_yes_with_dry_run_still_previews_only(tmp_path, monkeypatch, werkbank):
    """The user-reachable pair: `ephe tool create_svg --yes --dry-run`."""
    monkeypatch.setenv("HOME", str(tmp_path))
    env = {**os.environ, "HOME": str(tmp_path)}
    target = "proof_yes_dry.svg"
    proc = subprocess.run(
        [sys.executable, str(_REPO / "ephe_cli.py"), "tool", "create_svg",
         "--arg", f"filename={target}",
         "--arg", "svg_code=<svg><rect/></svg>",
         "--yes", "--dry-run"],
        cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    assert "DRY-RUN" in proc.stdout.upper()
    assert not (werkbank / target).exists()


class TestUserDenialCarriesItsCode:
    def test_a_user_refusal_code_survives_the_gate(self):
        async def _no(_name: str, _args: dict) -> bool:
            return False

        approved, denial = asyncio.run(confirm_for_chat("write_file", {}, on_confirm=_no))
        assert approved is False
        assert getattr(denial, "code", "") == "not_approved_by_user"
        assert dict(getattr(denial, "params", {}) or {}) == {}
        assert (
            "[TOOL-DENIED] write_file was not executed: the user did not approve the run."
            in denial
        )

    def test_auditing_can_be_skipped_for_a_caller_that_logs_elsewhere(self):
        from core.audit_log import tail

        asyncio.run(confirm_for_chat(
            "write_file", {"path": "quiet.txt"}, on_confirm=None, audit=False
        ))
        rows = [r for r in tail(limit=50, kind="approval") if r.get("tool") == "write_file"]
        assert rows == []

    def test_the_default_audits_the_denial_once(self):
        from core.audit_log import tail

        asyncio.run(confirm_for_chat("write_file", {"path": "loud.txt"}, on_confirm=None))
        rows = [
            r for r in tail(limit=50, kind="approval")
            if r.get("tool") == "write_file" and r.get("status") == "chat-gate"
        ]
        assert len(rows) == 1
        assert rows[0]["decision"] == "denied"


class TestFlagLeverOrderIsExhaustive:
    """The whole non-interactive flag table, so a reordered `if` in `request_approval` fails.

    The earlier suites pin lever pairs; the matrix pins the documented precedence: a
    no-execute lever (`declined`, `dry_run`) outranks an execute lever (`auto_approve`),
    and `declined` outranks `dry_run`.
    """

    @pytest.mark.parametrize(
        "declined,dry_run,auto_approve,approved,went_dry,marker",
        [
            (False, False, False, False, False, "non-interactive"),
            (False, False, True, True, False, "[--yes]"),
            (False, True, False, False, True, "DRY-RUN"),
            (False, True, True, False, True, "DRY-RUN"),
            (True, False, False, False, False, "(--no)"),
            (True, False, True, False, False, "(--no)"),
            (True, True, False, False, False, "(--no)"),
            (True, True, True, False, False, "(--no)"),
        ],
    )
    def test_decision_matches_the_lever_table(
        self, declined, dry_run, auto_approve, approved, went_dry, marker
    ):
        policy = ApprovalPolicy(
            declined=declined,
            dry_run=dry_run,
            auto_approve=auto_approve,
            interactive=False,
        )
        decision = asyncio.run(request_approval("create_svg", {"filename": "x.svg"}, policy))
        assert decision.approved is approved
        assert decision.dry_run is went_dry
        assert marker.lower() in decision.report.lower()

    @pytest.mark.parametrize("declined,dry_run", [(True, False), (False, True)])
    def test_a_flag_decides_before_the_tty_is_asked(self, monkeypatch, declined, dry_run):
        def _no_prompt(*_a, **_k):
            raise AssertionError("interactive prompt reached although a flag already decided")

        monkeypatch.setattr("builtins.input", _no_prompt)
        policy = ApprovalPolicy(declined=declined, dry_run=dry_run, interactive=True)
        decision = asyncio.run(request_approval("create_svg", {"filename": "x.svg"}, policy))
        assert decision.approved is False


class TestCallbackLeverOrder:
    """`on_confirm` sits between the flags and the TTY, and never overrides a flag."""

    def test_a_flag_outranks_the_callback(self):
        calls: list[str] = []

        async def _cb(name: str, _args: dict) -> bool:
            calls.append(name)
            return True

        declined = ApprovalPolicy(declined=True, on_confirm=_cb, interactive=True)
        dry = ApprovalPolicy(dry_run=True, on_confirm=_cb, interactive=True)
        d1 = asyncio.run(request_approval("create_svg", {}, declined))
        d2 = asyncio.run(request_approval("create_svg", {}, dry))
        assert d1.approved is False and d2.approved is False
        assert calls == []

    def test_a_grant_executes_over_the_non_interactive_deny(self):
        async def _yes(_name: str, _args: dict) -> bool:
            return True

        policy = ApprovalPolicy(on_confirm=_yes, interactive=False)
        decision = asyncio.run(request_approval("create_svg", {}, policy))
        assert decision.approved is True
        assert decision.dry_run is False
        assert "via callback" in decision.report

    def test_a_refusal_is_reported_as_a_callback_denial(self):
        async def _no(_name: str, _args: dict) -> bool:
            return False

        policy = ApprovalPolicy(on_confirm=_no, interactive=False)
        decision = asyncio.run(request_approval("create_svg", {}, policy))
        assert decision.approved is False
        assert "denied via callback" in decision.report

    def test_the_callback_decides_before_the_tty_is_asked(self, monkeypatch):
        def _no_prompt(*_a, **_k):
            raise AssertionError("interactive prompt reached although a callback was set")

        async def _no(_name: str, _args: dict) -> bool:
            return False

        monkeypatch.setattr("builtins.input", _no_prompt)
        policy = ApprovalPolicy(on_confirm=_no, interactive=True)
        decision = asyncio.run(request_approval("create_svg", {}, policy))
        assert decision.approved is False


class TestSafeToolOutranksEveryLever:
    """A read-only tool runs without a prompt and takes no dry-run: SAFE is the first branch."""

    def test_the_name_is_classified_safe(self):
        assert "read_file" in SAFE_TOOLS
        assert classify_tool("read_file").category == "SAFE"

    @pytest.mark.parametrize(
        "declined,dry_run,auto_approve",
        [(True, False, False), (False, True, False), (False, True, True), (True, True, True)],
    )
    def test_safe_runs_whatever_the_flags_say(self, declined, dry_run, auto_approve):
        policy = ApprovalPolicy(
            declined=declined,
            dry_run=dry_run,
            auto_approve=auto_approve,
            interactive=False,
        )
        decision = asyncio.run(request_approval("read_file", {"path": "x"}, policy))
        assert decision.approved is True
        assert decision.dry_run is False
        assert "[auto]" in decision.report


class TestChatGateRefusalCodes:
    """Each `confirm_for_chat` refusal carries its own code, and a grant carries none."""

    def test_a_missing_channel_names_itself(self):
        approved, denial = asyncio.run(confirm_for_chat("write_file", {}, on_confirm=None))
        assert approved is False
        assert getattr(denial, "code", None) == "no_approval_channel"
        assert denial == (
            f"{DENIAL_PREFIX} write_file was not executed: no approval channel is active "
            "(nobody is asking the user). Ask, or choose a read-only path."
        )

    def test_a_raising_callback_is_a_failed_channel_with_the_cause(self):
        async def _boom(_name: str, _args: dict) -> bool:
            raise ValueError("dialog gone")

        approved, denial = asyncio.run(confirm_for_chat("run_shell", {}, on_confirm=_boom))
        assert approved is False
        assert getattr(denial, "code", None) == "approval_channel_failed"
        assert dict(getattr(denial, "params", {}) or {}) == {"error": "ValueError"}
        assert "ValueError" in denial

    def test_a_grant_returns_an_empty_denial(self):
        async def _yes(_name: str, _args: dict) -> bool:
            return True

        assert asyncio.run(confirm_for_chat("write_file", {}, on_confirm=_yes)) == (True, "")

    def test_a_sync_callback_is_tolerated(self):
        approved, denial = asyncio.run(
            confirm_for_chat("write_file", {}, on_confirm=lambda _n, _a: True)
        )
        assert approved is True and denial == ""

    def test_an_auto_run_tool_never_reaches_a_raising_channel(self):
        def _boom(_name: str, _args: dict) -> bool:
            raise AssertionError("an auto-run tool must not reach the dialog")

        assert asyncio.run(confirm_for_chat("read_file", {"path": "x"}, on_confirm=_boom)) == (True, "")


class TestDenialMessageContract:
    """The one denial string both sinks consume, and the slot guard behind it."""

    def test_the_short_code_carries_no_reason_slot_and_keeps_the_next_step(self):
        denial = denial_message("write_file")
        assert denial == (
            f"{DENIAL_PREFIX} write_file was not executed. Ask, or choose a read-only path."
        )
        assert denial.code == "not_approved"
        assert denial.params == {}

    def test_an_unknown_code_passes_through_verbatim(self):
        denial = denial_message("write_file", "custom_reason")
        assert denial.code == "custom_reason"
        assert "custom_reason" in denial

    def test_a_code_with_a_missing_slot_refuses_to_leak_the_template(self):
        with pytest.raises(KeyError):
            denial_message("write_file", "approval_channel_failed")


class TestCliPolicyDenyBranch:
    """`execute_tool` with a policy denies at the registry and audits the cli-policy status."""

    def test_a_declined_policy_denies_audits_and_writes_nothing(self, tmp_path, monkeypatch, werkbank):
        from core.audit_log import tail

        monkeypatch.setenv("HOME", str(tmp_path))
        result = asyncio.run(execute_tool(
            "create_svg",
            {"svg_code": "<svg><rect/></svg>", "filename": "cli_denied.svg"},
            policy=ApprovalPolicy(declined=True),
        ))
        assert "(--no)" in result
        assert not (werkbank / "cli_denied.svg").exists()
        rows = [
            r for r in tail(limit=30, kind="approval")
            if r.get("tool") == "create_svg" and r.get("status") == "cli-policy"
        ]
        assert rows and rows[0]["decision"] == "denied"
