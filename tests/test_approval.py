"""P0-1 E1: Approval-Gates + Diff + --dry-run (conservative defaults).

Regression tests for the new approval/dry-run layer in `core/tools/approval.py`.
All tests are deterministic and offline; no mocks of the real tool layer.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Make `core.tools.approval` importable regardless of CWD.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


# Classification

def test_classification_safe_tools_do_not_need_approval():
    from core.tools.approval import classify_tool
    for name in ("read_file", "list_directory", "file_search", "get_datetime",
                 "query_source_notebook", "browser_screenshot"):
        assert classify_tool(name).auto_approve_by_default is True, name


def test_classification_mutating_tools_require_approval():
    from core.tools.approval import classify_tool
    for name in ("run_shell", "manage_tasks", "create_svg", "create_pdf",
                 "generate_chart", "create_pitch_deck", "create_pptx_deck"):
        assert classify_tool(name).auto_approve_by_default is False, name


def test_classification_shell_never_auto_approved():
    from core.tools.approval import classify_tool
    assert classify_tool("run_shell").auto_approve_by_default is False


# Dry-run: no side effects

def test_dry_run_policy_blocks_execution():
    from core.tools.approval import ApprovalPolicy, request_approval

    policy = ApprovalPolicy(dry_run=True)
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is False
    assert decision.dry_run is True
    assert "ls" in decision.report
    assert "DRY-RUN" in decision.report.upper()


def test_dry_run_policy_blocks_svg_creation_no_file_written(tmp_path):
    from core.tools.approval import ApprovalPolicy, request_approval
    from core.tools.registry import execute_tool

    target = tmp_path / "no_write.svg"
    policy = ApprovalPolicy(dry_run=True)
    result = asyncio.run(execute_tool(
        "create_svg",
        {"svg_code": "<svg><rect/></svg>", "filename": target.name},
        policy=policy,
    ))
    # Dry-run must NOT write the file.
    assert not target.exists()
    assert "DRY-RUN" in result.upper() or "[dry-run]" in result.lower()


def test_executing_with_policy_yes_writes_svg(tmp_path, monkeypatch, werkbank):
    from core.tools.approval import ApprovalPolicy
    from core.tools.registry import execute_tool

    monkeypatch.setenv("HOME", str(tmp_path))
    policy = ApprovalPolicy(auto_approve=True)
    result = asyncio.run(execute_tool(
        "create_svg",
        {"svg_code": "<svg><rect width='10' height='10'/></svg>",
         "filename": "proof_yes.svg"},
        policy=policy,
    ))
    written = werkbank / "proof_yes.svg"
    assert written.exists(), f"expected {written} to exist, got: {result!r}"


def test_executing_with_policy_no_blocks_execution(tmp_path, monkeypatch, werkbank):
    from core.tools.approval import ApprovalPolicy
    from core.tools.registry import execute_tool

    monkeypatch.setenv("HOME", str(tmp_path))

    async def deny(_name, _args):
        return False

    policy = ApprovalPolicy(auto_approve=False, on_confirm=deny)
    result = asyncio.run(execute_tool(
        "create_svg",
        {"svg_code": "<svg><rect/></svg>", "filename": "proof_no.svg"},
        policy=policy,
    ))
    written = werkbank / "proof_no.svg"
    assert not written.exists()
    assert "Denied" in result or "denied" in result.lower()


def test_safe_tools_bypass_policy_even_without_auto_approve(tmp_path, monkeypatch):
    from core.tools.approval import ApprovalPolicy
    from core.tools.registry import execute_tool

    # read_file on a file in the allowed roots must work with a strict policy
    # (SAFE tools never need approval).
    target = tmp_path / "allow.txt"
    target.write_text("ok\n")
    policy = ApprovalPolicy(auto_approve=False)

    async def deny(_n, _a):
        return False

    policy.on_confirm = deny
    result = asyncio.run(execute_tool("read_file", {"path": str(target)}, policy=policy))
    assert "ok" in result


def test_policy_yes_overrides_deny_callback():
    """`--yes` is a CLI override; even a strict deny-callback yields when auto_approve."""
    from core.tools.approval import ApprovalPolicy, request_approval

    async def deny(_n, _a):
        return False

    policy = ApprovalPolicy(auto_approve=True, on_confirm=deny)
    decision = asyncio.run(request_approval("create_svg", {"filename": "x"}, policy))
    assert decision.approved is True


# Diff

def test_format_diff_for_svg_shows_preview():
    from core.tools.approval import format_diff
    d = format_diff("create_svg", {"svg_code": "<svg><rect width='1' height='1'/></svg>",
                                   "filename": "x.svg"})
    assert "x.svg" in d
    assert "<svg>" in d


def test_format_diff_for_shell_shows_command():
    from core.tools.approval import format_diff
    d = format_diff("run_shell", {"command": "ls -la"})
    assert "ls -la" in d


# Non-interactive guard

def test_non_interactive_requires_explicit_flag():
    """A MUTATING tool with no policy + non-interactive TTY must refuse (raise)."""
    from core.tools.approval import ApprovalPolicy, request_approval

    policy = ApprovalPolicy(auto_approve=False, interactive=False)
    decision = asyncio.run(request_approval("run_shell", {"command": "rm -rf /"}, policy))
    assert decision.approved is False
    assert "interaktiv" in decision.report or "INTERACTIVE" in decision.report.upper() or \
        "--yes" in decision.report or "non-interactive" in decision.report.lower()


def test_policy_defaults_conservative():
    """No auto-approval, no dry-run, strict on_confirm by default (E1 mitigation)."""
    from core.tools.approval import ApprovalPolicy
    p = ApprovalPolicy()
    assert p.auto_approve is False
    assert p.dry_run is False


# CLI: argparse surface

def test_cli_tool_subcommand_parses_dry_run():
    import ephe_cli
    parser = ephe_cli.build_parser()
    args = parser.parse_args(["tool", "create_svg",
                              "--arg", "filename=proof_dry.svg",
                              "--arg", "svg_code=<svg><rect/></svg>",
                              "--dry-run"])
    assert args.command == "tool"
    assert args.tool_name == "create_svg"
    assert args.dry_run is True
    assert args.yes is False


def test_cli_tool_subcommand_parses_yes():
    import ephe_cli
    parser = ephe_cli.build_parser()
    args = parser.parse_args(["tool", "run_shell",
                              "--arg", "command=echo hi",
                              "--yes"])
    assert args.yes is True
    assert args.dry_run is False


def test_cli_tool_subcommand_yes_no_mutually_exclusive():
    import ephe_cli
    parser = ephe_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["tool", "run_shell", "--arg", "command=echo",
                           "--yes", "--no"])


def test_cli_tool_subcommand_requires_name():
    import ephe_cli
    parser = ephe_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["tool"])


# E2E: CLI subprocess dry-run leaves workspace clean

def test_e2e_cli_tool_dry_run_creates_no_file(tmp_path, monkeypatch, werkbank):
    """Run `ephe tool create_svg --dry-run` via real CLI subprocess.

    HOME is pointed at tmp_path so no real files are touched.
    The target SVG must NOT be created on disk.
    """
    env = {**os.environ, "HOME": str(tmp_path)}
    target = "proof_e2e_dry.svg"
    proc = subprocess.run(
        [sys.executable, str(_REPO / "ephe_cli.py"),
         "tool", "create_svg",
         "--arg", f"filename={target}",
         "--arg", "svg_code=<svg><rect/></svg>",
         "--dry-run"],
        cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    assert not (werkbank / target).exists(), "A1: dry-run schreibt weder dorthin, wo es früher landete, noch in die Werkbank"
    assert "DRY-RUN" in proc.stdout.upper() or "[dry-run]" in proc.stdout.lower()


def test_e2e_cli_tool_yes_writes_file(tmp_path, monkeypatch, werkbank):
    """The same call WITHOUT --dry-run but WITH --yes writes the file."""
    env = {**os.environ, "HOME": str(tmp_path)}
    target = "proof_e2e_yes.svg"
    proc = subprocess.run(
        [sys.executable, str(_REPO / "ephe_cli.py"),
         "tool", "create_svg",
         "--arg", f"filename={target}",
         "--arg", "svg_code=<svg><rect/></svg>",
         "--yes"],
        cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    assert (werkbank / target).exists(), "A1: der Geburtsort ist die Werkbank"


def test_e2e_cli_tool_without_flag_in_noninteractive_blocks(tmp_path, monkeypatch, werkbank):
    """Default = conservative: a non-interactive call without --yes/--dry-run
    must NOT execute a mutating tool and must return exit code 1."""
    env = {**os.environ, "HOME": str(tmp_path), "CI": "1"}
    target = "proof_e2e_default.svg"
    proc = subprocess.run(
        [sys.executable, str(_REPO / "ephe_cli.py"),
         "tool", "create_svg",
         "--arg", f"filename={target}",
         "--arg", "svg_code=<svg><rect/></svg>"],
        cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=30,
        stdin=subprocess.DEVNULL,
    )
    assert proc.returncode != 0
    assert not (werkbank / target).exists()


# W3-33: opt-in confidence escalation (a floor, never a grant)

def test_escalation_policy_defaults_off():
    """The opt-in is off and carries no signal, so nothing drifts by default."""
    from core.tools.approval import DEFAULT_CONFIDENCE_THRESHOLD, ApprovalPolicy

    p = ApprovalPolicy()
    assert p.escalate_on_low_confidence is False
    assert p.confidence is None
    assert p.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD == 0.6


def test_escalation_off_by_default_keeps_yes_auto_approve():
    """Low confidence with the opt-in OFF changes nothing — `--yes` still approves."""
    from core.tools.approval import ApprovalPolicy, request_approval

    policy = ApprovalPolicy(auto_approve=True, interactive=False, confidence=0.05)
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is True
    assert "[--yes]" in decision.report
    assert decision.extra.get("escalated") is None


def test_escalation_overrides_yes_and_denies_non_interactive():
    """With the opt-in ON a low-confidence mutating call is not blanket-approved."""
    from core.tools.approval import ApprovalPolicy, request_approval

    policy = ApprovalPolicy(
        auto_approve=True, interactive=False,
        escalate_on_low_confidence=True, confidence=0.2,
    )
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is False
    assert decision.dry_run is False
    assert "escalated" in decision.report
    assert "0.20" in decision.report and "0.60" in decision.report
    assert decision.extra.get("escalated") is True
    assert decision.extra.get("confidence") == 0.2


def test_escalation_callback_can_still_approve():
    from core.tools.approval import ApprovalPolicy, request_approval

    async def yes(_n, _a):
        return True

    policy = ApprovalPolicy(
        auto_approve=True, on_confirm=yes, interactive=False,
        escalate_on_low_confidence=True, confidence=0.1,
    )
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is True
    assert "approved via callback" in decision.report
    assert decision.extra.get("escalated") is True


def test_escalation_callback_deny_stops_execution():
    from core.tools.approval import ApprovalPolicy, request_approval

    async def no(_n, _a):
        return False

    policy = ApprovalPolicy(
        auto_approve=True, on_confirm=no,
        escalate_on_low_confidence=True, confidence=0.1,
    )
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is False
    assert "denied via callback" in decision.report
    assert decision.extra.get("escalated") is True


def test_escalation_interactive_confirm(monkeypatch):
    from core.tools.approval import ApprovalPolicy, request_approval

    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")
    policy = ApprovalPolicy(
        auto_approve=True, interactive=True,
        escalate_on_low_confidence=True, confidence=0.1,
    )
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is True
    assert "confirmed interactively" in decision.report
    assert "escalated" in decision.report


def test_escalation_interactive_decline(monkeypatch):
    from core.tools.approval import ApprovalPolicy, request_approval

    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    policy = ApprovalPolicy(
        auto_approve=True, interactive=True,
        escalate_on_low_confidence=True, confidence=0.1,
    )
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is False
    assert "denied interactively" in decision.report


def test_escalation_boundary_is_strictly_below_threshold():
    """Exactly at the threshold is confident enough; nothing below is."""
    from core.tools.approval import ApprovalPolicy, request_approval

    async def no(_n, _a):
        return False

    base = dict(auto_approve=True, on_confirm=no, escalate_on_low_confidence=True)

    at = asyncio.run(request_approval(
        "run_shell", {"command": "ls"}, ApprovalPolicy(**base, confidence=0.6)))
    assert at.approved is True  # 0.6 is not below 0.6 → not escalated → callback runs

    below = asyncio.run(request_approval(
        "run_shell", {"command": "ls"}, ApprovalPolicy(**base, confidence=0.59)))
    assert below.approved is False  # escalated → callback denies, `--yes` unreachable
    assert below.extra.get("escalated") is True


def test_escalation_read_only_tools_never_escalate():
    """A read acts on nothing, so there is nothing to defer to a human."""
    from core.tools.approval import ApprovalPolicy, request_approval

    policy = ApprovalPolicy(
        auto_approve=False, interactive=False,
        escalate_on_low_confidence=True, confidence=0.01,
    )
    decision = asyncio.run(request_approval("read_file", {"path": "x"}, policy))
    assert decision.approved is True
    assert "[auto]" in decision.report


def test_escalation_declined_and_dry_run_still_win():
    """The confidence floor sits behind the hard no-execute levers."""
    from core.tools.approval import ApprovalPolicy, request_approval

    declined = ApprovalPolicy(
        declined=True, escalate_on_low_confidence=True, confidence=0.01)
    d1 = asyncio.run(request_approval("run_shell", {"command": "ls"}, declined))
    assert d1.approved is False and "--no" in d1.report

    dry = ApprovalPolicy(
        dry_run=True, auto_approve=True,
        escalate_on_low_confidence=True, confidence=0.01)
    d2 = asyncio.run(request_approval("run_shell", {"command": "ls"}, dry))
    assert d2.approved is False and d2.dry_run is True
    assert "DRY-RUN" in d2.report.upper()


def test_escalation_unknown_confidence_is_not_low():
    from core.tools.approval import ApprovalPolicy, request_approval

    policy = ApprovalPolicy(
        auto_approve=True, interactive=False,
        escalate_on_low_confidence=True, confidence=None)
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is True
    assert "[--yes]" in decision.report


def test_escalation_per_call_confidence_overrides_policy():
    from core.tools.approval import ApprovalPolicy, request_approval

    confident_policy = ApprovalPolicy(
        auto_approve=True, interactive=False,
        escalate_on_low_confidence=True, confidence=0.9)
    # A per-call low signal escalates even though the policy's own value is high.
    d1 = asyncio.run(request_approval(
        "run_shell", {"command": "ls"}, confident_policy, confidence=0.1))
    assert d1.approved is False and d1.extra.get("escalated") is True

    unsure_policy = ApprovalPolicy(
        auto_approve=True, interactive=False,
        escalate_on_low_confidence=True, confidence=0.1)
    # A per-call high signal does not escalate even though the policy's value is low.
    d2 = asyncio.run(request_approval(
        "run_shell", {"command": "ls"}, unsure_policy, confidence=0.95))
    assert d2.approved is True and d2.extra.get("escalated") is None


def test_escalation_custom_threshold():
    from core.tools.approval import ApprovalPolicy, request_approval

    policy = ApprovalPolicy(
        auto_approve=True, interactive=False,
        escalate_on_low_confidence=True, confidence=0.8, confidence_threshold=0.9)
    decision = asyncio.run(request_approval("run_shell", {"command": "ls"}, policy))
    assert decision.approved is False
    assert "0.90" in decision.report


def test_low_confidence_escalation_helper():
    import math as _math

    from core.tools.approval import ApprovalPolicy, low_confidence_escalation

    off = ApprovalPolicy(confidence=0.0)
    assert low_confidence_escalation(off, 0.0) is False

    on = ApprovalPolicy(escalate_on_low_confidence=True, confidence_threshold=0.6)
    assert low_confidence_escalation(on, 0.3) is True
    assert low_confidence_escalation(on, 0.6) is False
    assert low_confidence_escalation(on, 0.99) is False
    assert low_confidence_escalation(on) is False
    assert low_confidence_escalation(on, None) is False
    # present but unusable → counts as low, never as high
    assert low_confidence_escalation(on, _math.nan) is True
    assert low_confidence_escalation(on, "high") is True
    assert low_confidence_escalation(on, "0.2") is True
    # read-only calls have nothing to defer
    assert low_confidence_escalation(on, 0.0, mutating=False) is False


def test_chat_tool_requires_confirm_default_unchanged():
    from core.tools.approval import chat_tool_requires_confirm

    assert chat_tool_requires_confirm("memory") is False
    assert chat_tool_requires_confirm("read_file") is False
    assert chat_tool_requires_confirm("run_shell") is True


def test_chat_tool_requires_confirm_escalates_on_low_confidence():
    from core.tools.approval import ApprovalPolicy, chat_tool_requires_confirm

    policy = ApprovalPolicy(escalate_on_low_confidence=True, confidence=0.2)
    # An auto-run chat tool the model is unsure about is asked about after all.
    assert chat_tool_requires_confirm("memory", policy=policy) is True
    # A confident one is not.
    assert chat_tool_requires_confirm(
        "memory", policy=policy, confidence=0.9) is False
    # A read-only tool is never escalated into a dialog.
    assert chat_tool_requires_confirm("read_file", policy=policy) is False


def test_escalation_reads_a_confidence_bearing_object():
    """A Decision-like object is accepted in place of a number."""
    from core.tools.approval import ApprovalPolicy, request_approval

    class Signal:
        confidence = 0.15

    policy = ApprovalPolicy(
        auto_approve=True, interactive=False, escalate_on_low_confidence=True)
    result = asyncio.run(
        request_approval("run_shell", {"command": "ls"}, policy, Signal()))
    assert result.approved is False
    assert result.extra.get("confidence") == 0.15


def test_escalation_consumes_the_decision_layer():
    """The Ephe Decision layer's own confidence drives the floor."""
    pytest.importorskip("core.decisions")
    from core.decisions import Decision
    from core.tools.approval import ApprovalPolicy, request_approval

    decision = Decision(
        verb="choose", state="run a shell command", options=("run_shell",),
        chosen="run_shell", confidence=0.1,
        distribution=(("run_shell", 1.0),), backend="local", cost_seconds=0.0,
    )
    policy = ApprovalPolicy(
        auto_approve=True, interactive=False, escalate_on_low_confidence=True)
    result = asyncio.run(
        request_approval("run_shell", {"command": "ls"}, policy, decision))
    assert result.approved is False
    assert result.extra.get("escalated") is True
    assert result.extra.get("confidence") == 0.1
