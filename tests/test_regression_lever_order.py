"""The approval gate's lever order after this cycle's fix, pinned at the CLI.

``request_approval`` answered the execute lever (``--yes``) before the no-touch
lever (``--dry-run``), so one command on a real operator desk executed a mutating
tool under a flag that promises nothing runs. The unit order is already pinned in
``test_refusal_gate_branches.py``; what no test held is the CLI differential: the
same call writes with ``--yes`` alone and must write nothing with ``--dry-run``
beside it. Without that pair a tool that never ran would read as a correct refusal.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from core.tools.approval import ApprovalPolicy, request_approval
from core.tools.registry import execute_tool

REPO_ROOT = Path(__file__).resolve().parent.parent
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'


def _cli(tmp_path, target, *flags):
    env = {**os.environ, "HOME": str(tmp_path)}
    return subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "ephe_cli.py"), "tool", "create_svg",
            "--arg", f"filename={target}", "--arg", f"svg_code={SVG}", *flags,
        ],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120,
    )


class TestTheYesControlActuallyWrites:
    """A refusal is only proven against a run that would otherwise write."""

    def test_yes_alone_creates_the_file(self, tmp_path, werkbank):
        proc = _cli(tmp_path, "lever_yes_control.svg", "--yes")
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert (werkbank / "lever_yes_control.svg").exists()

    def test_the_same_call_with_dry_run_beside_yes_writes_nothing(self, tmp_path, werkbank):
        proc = _cli(tmp_path, "lever_yes_dry.svg", "--yes", "--dry-run")
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert not (werkbank / "lever_yes_dry.svg").exists()
        assert "DRY-RUN" in proc.stdout.upper()

    def test_no_alone_declines_with_exit_one_and_writes_nothing(self, tmp_path, werkbank):
        proc = _cli(tmp_path, "lever_no.svg", "--no")
        assert proc.returncode == 1, proc.stdout
        assert not (werkbank / "lever_no.svg").exists()


class TestTheDeclinedLeverOutranksDryRunInReports:
    """``--no`` is checked before ``--dry-run``, so its report names the refusal."""

    def test_declined_wins_over_dry_run(self):
        decision = asyncio.run(
            request_approval(
                "write_file",
                {"path": "/tmp/lever.txt", "content": "x"},
                ApprovalPolicy(declined=True, dry_run=True, auto_approve=True),
            )
        )
        assert decision.approved is False
        assert decision.dry_run is False
        assert "(--no)" in decision.report

    def test_dry_run_wins_over_auto_approve_without_declined(self):
        decision = asyncio.run(
            request_approval(
                "write_file",
                {"path": "/tmp/lever.txt", "content": "x"},
                ApprovalPolicy(dry_run=True, auto_approve=True),
            )
        )
        assert decision.approved is False
        assert decision.dry_run is True
        assert "DRY-RUN" in decision.report


class TestTheRegistryHonoursTheSameOrder:
    def test_the_store_call_writes_nothing_under_the_dry_run_lever(self, werkbank):
        target = werkbank / "lever_registry_dry.svg"
        result = asyncio.run(
            execute_tool(
                "create_svg",
                {"svg_code": SVG, "filename": target.name},
                policy=ApprovalPolicy(auto_approve=True, dry_run=True),
            )
        )
        assert "DRY-RUN" in result.upper()
        assert not target.exists()

    def test_the_store_call_writes_under_the_yes_lever(self, werkbank):
        target = werkbank / "lever_registry_yes.svg"
        result = asyncio.run(
            execute_tool(
                "create_svg",
                {"svg_code": SVG, "filename": target.name},
                policy=ApprovalPolicy(auto_approve=True),
            )
        )
        assert "DRY-RUN" not in result.upper()
        assert target.exists(), result
