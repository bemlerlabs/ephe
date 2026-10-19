"""Wave 2 / B3 — per-category approval overrides, one direction only.

The review in `docs/SECURITY_THREAT_MODEL.md` bounds this feature: a user may ask to be
prompted for a category that would otherwise run by itself, and nothing may lower a
category. This file is the matrix the wave asks for — every profile, every category,
with and without the override — plus the two claims the review rests on: the defaults
are byte-for-byte today's answers, and `run_shell` is untouched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import engine_config
from core.security_config import ASKABLE_CATEGORIES, load_security_config, save_security_config
from core.tools.approval import _escalated_approval  # noqa: F401  (import surface)
from core.tools.approval_rules import (
    ApprovalPolicy,
    category_forces_confirm,
    chat_tool_requires_confirm,
    classify_tool,
)

PROFILES = ("strict", "session", "plan", "full")
#: One tool per category, chosen from the real sets.
TOOLS = {
    "SAFE": "read_file",
    "NETWORK": "web_search",
    "MUTATING": "write_file",
    "DANGEROUS": "run_shell",
}


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path)
    yield tmp_path


def _force(*categories: str) -> None:
    save_security_config(ask_categories=list(categories))


class TestTheMatrix:
    @pytest.mark.parametrize("profile", PROFILES)
    @pytest.mark.parametrize("category", tuple(TOOLS))
    def test_overrides_only_ever_add_a_prompt(self, profile: str, category: str):
        tool = TOOLS[category]
        save_security_config(approval_profile=profile)
        before = chat_tool_requires_confirm(tool)
        for forced in ASKABLE_CATEGORIES:
            _force(forced)
            after = chat_tool_requires_confirm(tool)
            assert after >= before, (profile, category, forced)
            if forced == category:
                assert after is True, (profile, category)

    @pytest.mark.parametrize("profile", PROFILES)
    def test_run_shell_asks_in_every_profile_and_override(self, profile: str):
        save_security_config(approval_profile=profile)
        for forced in ((), ("SAFE",), ("NETWORK",), ("SAFE", "NETWORK")):
            _force(*forced)
            assert chat_tool_requires_confirm("run_shell") is True

    def test_defaults_are_unchanged_for_every_category(self):
        # No override stored: the answers are the ones the static sets give.
        assert load_security_config().ask_categories == ()
        assert chat_tool_requires_confirm("read_file") is False
        assert chat_tool_requires_confirm("web_search") is False
        assert chat_tool_requires_confirm("write_file") is True
        assert chat_tool_requires_confirm("run_shell") is True
        assert chat_tool_requires_confirm("totally_unknown_tool") is True


class TestTheBounds:
    def test_only_the_auto_run_categories_are_accepted(self):
        save_security_config(ask_categories=["SAFE", "MUTATING", "DANGEROUS", "NETWORK"])
        assert load_security_config().ask_categories == ("SAFE", "NETWORK")
        assert ASKABLE_CATEGORIES == ("SAFE", "NETWORK")

    def test_a_forced_category_is_the_class_the_process_sees(self):
        _force("SAFE")
        assert classify_tool("read_file").category == "SAFE"
        assert category_forces_confirm("read_file") is True
        assert category_forces_confirm("web_search") is False

    def test_an_unreadable_store_forces_nothing(self, tmp_path: Path):
        (tmp_path / "security.json").write_text("{ broken", encoding="utf-8")
        assert category_forces_confirm("read_file") is False

    @pytest.mark.asyncio
    async def test_yes_does_not_override_a_forced_category(self):
        from core.tools.approval import request_approval

        _force("SAFE")
        asked: list[str] = []

        async def _confirm(name: str, args: dict) -> bool:
            asked.append(name)
            return True

        decision = await request_approval(
            "read_file",
            {"path": "notes.txt"},
            policy=ApprovalPolicy(auto_approve=True, on_confirm=_confirm),
        )
        assert decision.approved is True
        assert asked == ["read_file"], "--yes skipped the human the user asked for"

    @pytest.mark.asyncio
    async def test_a_declined_forced_prompt_keeps_the_denial_code(self):
        from core.tools.chat_gate import confirm_for_chat

        _force("NETWORK")

        async def _decline(name: str, args: dict) -> bool:
            return False

        approved, denial = await confirm_for_chat(
            "web_search", {"query": "anything"}, on_confirm=_decline, audit=False
        )
        assert approved is False
        # The existing code, unchanged: the override adds a prompt, not a reason.
        assert getattr(denial, "code", None) == "not_approved_by_user"
