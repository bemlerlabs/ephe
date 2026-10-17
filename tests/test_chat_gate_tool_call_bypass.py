"""
◑ Ephe – wave G1 · TDD
tests/test_chat_gate_tool_call_bypass.py

RULE: these tests were written BEFORE the implementation.

The hole (audit 2026-10-02, confirmed in the code):
the PWA chat path calls ``execute_tool(name, args, policy=None)`` and gates itself
via ``chat_tool_requires_confirm`` (core/chat.py). ``tool_call`` sits in
CHAT_AUTO_RUN_TOOLS — so it ALWAYS runs without a dialog — and passes the policy on,
which is None on this path. A gated tool (browser_exec, write_file, run_shell …)
therefore landed in the inner ``execute_tool`` without a policy, where the gate is
skipped: a single auto-run call switched off every gate.

The countermeasure is a shared choke point (core.tools.chat_gate) that model
dispatch AND the meta router both go through — without a new dialog mechanism.
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.tools.approval import ApprovalPolicy
from core.tools.chat_gate import confirm_for_chat
from core.tools.discovery import tool_call
from core.tools.session_ctx import set_current_policy
from core.vision import set_sandbox_confirm_cb


def _patched(name: str, executor):
    return patch.dict("core.tools.registry.TOOL_MAP", {name: executor}, clear=False)


class TestMetaRouterGate:
    """``tool_call`` must not pass through a tool that needed a dialog directly."""

    def test_gated_tool_is_denied_when_no_dialog_exists(self):
        executor = AsyncMock(return_value="geschrieben")

        async def _run():
            with _patched("write_file", executor):
                return await tool_call("write_file", {"path": "x.txt", "content": "hi"})

        out = asyncio.run(_run())
        executor.assert_not_awaited()
        assert "[TOOL-DENIED]" in out

    def test_the_request_scoped_callback_decides(self):
        seen: list[tuple[str, dict]] = []

        async def _cb(name: str, args: dict) -> bool:
            seen.append((name, args))
            return True

        executor = AsyncMock(return_value="geschrieben")

        async def _run():
            set_sandbox_confirm_cb(_cb)
            with _patched("write_file", executor):
                return await tool_call("write_file", {"path": "x.txt", "content": "hi"})

        out = asyncio.run(_run())
        assert seen == [("write_file", {"path": "x.txt", "content": "hi"})]
        executor.assert_awaited_once()
        assert out == "geschrieben"

    def test_user_denial_stops_the_inner_tool(self):
        executor = AsyncMock(return_value="geschrieben")

        async def _run():
            set_sandbox_confirm_cb(lambda name, args: False)
            with _patched("write_file", executor):
                return await tool_call("write_file", {"path": "x.txt", "content": "hi"})

        out = asyncio.run(_run())
        executor.assert_not_awaited()
        assert "[TOOL-DENIED]" in out

    def test_auto_run_tools_still_flow_through(self):
        """No double dialog: what chat would run unasked anyway, tool_call does not ask about."""
        executor = AsyncMock(return_value="2026-10-02")

        async def _run():
            with _patched("get_datetime", executor):
                return await tool_call("get_datetime", {})

        out = asyncio.run(_run())
        executor.assert_awaited_once()
        assert out == "2026-10-02"

    def test_cli_policy_is_still_the_gate_when_one_is_active(self):
        """With an active policy (CLI) request_approval stays the choke point —
        tool_call does not ask on top of it."""
        prompts: list[str] = []

        async def _on_confirm(name: str, args: dict) -> bool:
            prompts.append(name)
            return True

        set_current_policy(ApprovalPolicy(auto_approve=False, interactive=True, on_confirm=_on_confirm))
        executor = AsyncMock(return_value="geschrieben")

        async def _run():
            with _patched("write_file", executor):
                return await tool_call("write_file", {"path": "x.txt", "content": "hi"})

        asyncio.run(_run())
        assert prompts == ["write_file"]
        executor.assert_awaited_once()

    def test_unknown_tool_names_are_gated(self):
        """deny-by-default also holds for foreign names: unknown is not approved."""
        out = asyncio.run(tool_call("ein_fremdes_tool", {}))
        assert "[TOOL-DENIED]" in out


class TestBrowserExecReachable:
    """The actual attack: host Python exec through the meta router."""

    def test_browser_exec_needs_the_dialog_even_via_tool_call(self, tmp_path: Path):
        victim = tmp_path / "pwned.txt"
        code = f"open({str(victim)!r}, 'w').write('x')"

        out = asyncio.run(tool_call("browser_exec", {"code": code, "session": "gate-test"}))
        assert "[TOOL-DENIED]" in out
        assert not victim.exists(), "Host-Datei geschrieben, obwohl niemand zustimmte"

    def test_approval_opens_browser_exec(self, tmp_path: Path):
        victim = tmp_path / "written.txt"
        code = f"open({str(victim)!r}, 'w').write('ok')"

        async def _run():
            set_sandbox_confirm_cb(lambda name, args: True)
            return await tool_call("browser_exec", {"code": code, "session": "gate-approve"})

        asyncio.run(_run())
        assert victim.read_text() == "ok"


class TestGateIsShared:
    """One gate, two paths: dispatch and the meta router must do the same thing."""

    def test_no_channel_no_dialog_means_no_run(self):
        approved, reason = asyncio.run(confirm_for_chat("write_file", {}, on_confirm=None))
        assert approved is False
        assert reason

    def test_the_denial_is_audited_at_the_gate(self):
        """The denial is the point where it is decided — not only inside the caller."""
        from core.audit_log import tail

        asyncio.run(confirm_for_chat("write_file", {"path": "x.txt"}, on_confirm=None))
        rows = [
            r for r in tail(limit=30, kind="approval")
            if r.get("tool") == "write_file" and r.get("status") == "chat-gate"
        ]
        assert rows and rows[0]["decision"] == "denied"

    def test_chat_dispatch_uses_the_shared_gate(self):
        """Regression guard against re-inlining: core/chat.py calls confirm_for_chat."""
        import core.chat as chat_module

        assert "confirm_for_chat" in inspect.getsource(chat_module)

    def test_gate_prefers_the_explicit_callback(self):
        calls: list[str] = []

        async def _explicit(name: str, args: dict) -> bool:
            calls.append("explicit")
            return True

        async def _run():
            set_sandbox_confirm_cb(lambda name, args: calls.append("context") or True)
            return await confirm_for_chat("write_file", {}, on_confirm=_explicit)

        approved, _ = asyncio.run(_run())
        assert approved is True
        assert calls == ["explicit"]

    def test_a_raising_callback_denies_instead_of_running(self):
        async def _boom(name: str, args: dict) -> bool:
            raise RuntimeError("dialog gone")

        approved, reason = asyncio.run(confirm_for_chat("write_file", {}, on_confirm=_boom))
        assert approved is False
        assert "RuntimeError" in reason

    def test_read_only_tools_are_never_asked(self):
        asked: list[str] = []

        async def _cb(name: str, args: dict) -> bool:
            asked.append(name)
            return False

        async def _run():
            return await confirm_for_chat("read_file", {"path": "x"}, on_confirm=_cb)

        approved, _ = asyncio.run(_run())
        assert approved is True
        assert asked == []
