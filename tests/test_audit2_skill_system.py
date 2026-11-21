""""
◑ Ephe – TDD: Deep-Audit 2026-09-13 follow-up (skill/tool system).

Covers the load-bearing findings of the principal audit (named during the
round; F1/P2-3 were retired together with R36 and the fast-path module):
  F2  reference_text/example_text are never injected into the system prompt.
  F3  the working-memory ledger does not capture role:"tool" results.
  F4  the skill-builder whitelist is hard-coded to 6 tools.

Given / When / Then – strictly. No real writes to ~/Downloads.
"""
from __future__ import annotations


# F2: reference_text/example_text injection


class TestReferenceInjection:

    def test_given_skill_with_references_when_assembled_then_prompt_has_rubric(self):
        """G: writer skill (references/) W: assemble T: rubric + golden in prompt"""
        from core.skills import SkillLoader
        skill = SkillLoader().load("writer")
        assert skill.has_references is True
        # The injected block (via _compose_extra_system) has to carry the rubric.
        from server.routes.chat import _compose_extra_system
        extra = _compose_extra_system(skill, ask_mode=False)
        assert "Quality Rubric" in (extra or "")
        assert "Golden Example" in (extra or "")

    def test_given_ask_mode_when_assembled_then_guard_and_refs_present(self):
        """G: ask_mode=True W: _compose_extra_system T: guard + rubric"""
        from core.skills import SkillLoader
        from server.routes.chat import _compose_extra_system
        skill = SkillLoader().load("writer")
        extra = _compose_extra_system(skill, ask_mode=True)
        assert "Quality Rubric" in extra
        assert "ASK" in extra.upper() or "NUR" in extra.upper() or "keine" in extra.lower()


# F3: ledger captures role:"tool"

class TestLedgerToolCoverage:

    def test_given_tool_messages_when_compacted_then_ledger_holds_tool_evidence(self):
        """G: history with role:tool W: compact_history T: tool evidence in ledger"""
        from core.conversation_compactor import compact_history
        history: list[dict] = []
        for i in range(40):
            history.append({"role": "user", "content": f"frage {i} mit projekt repo"})
            history.append({"role": "assistant", "content": f"antwort {i}"})
            history.append({"role": "tool", "content": f"PDF_FILE:/tmp/out_{i}.pdf"})
        out = compact_history(history)
        ledger = next((m["content"] for m in out if m["role"] == "system" and "Ledger" in m["content"]), "")
        assert "PDF_FILE" in ledger or "out_" in ledger   # the tool evidence survives


# F4: builder whitelist is dynamic

class TestBuilderWhitelist:

    def test_given_builder_prompt_then_lists_registered_tools(self):
        """G: SKILL_BUILDER_SYSTEM W: format T: create_pdf as an allowed tool"""
        from core.skill_builder import _build_system_prompt
        prompt = _build_system_prompt()
        assert "create_pdf" in prompt          # not 6 hard-coded tools only
        assert "run_shell" in prompt


# P2-1/P2-2: SKILL.md consistency (run_shell + diff limit)

class TestSkillMdConsistency:

    def test_given_coding_agent_then_run_shell_in_allowed_tools(self):
        """G: coding-agent SKILL W: load T: run_shell in allowed_tools"""
        from core.skills import SkillLoader
        skill = SkillLoader().load("coding-agent")
        assert "run_shell" in (skill.allowed_tools or [])

    def test_given_security_review_then_prompt_has_diff_limit(self):
        """G: security-review SKILL W: load T: diff limit in the system prompt"""
        from core.skills import SkillLoader
        skill = SkillLoader().load("security-review")
        assert "diff --stat" in (skill.system_prompt or "")
