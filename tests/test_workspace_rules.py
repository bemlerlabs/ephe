"""R29 — Workspace instruction file injection + context transparency.

The agent must honor the project rules the user wrote in the workspace itself
(the canonical Referenz-B-convention file at the workspace root), injected with a  # language-gate: ignore (Referenz-B is the project's own name for that convention, used verbatim in app/src/locales/en.json:747 too)
provenance marker and a size cap — and the whole assembled prompt must be
inspectable stage by stage via GET /api/context/stages (the transparency
competitors do not offer).

Filenames always come from core.workspace_rules.RULES_NAME — tests never
re-spell the token, so no drift is possible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.workspace_rules import RULES_NAME, WORKSPACE_RULES_MAX


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    wd = tmp_path / "ws"
    wd.mkdir()
    monkeypatch.setenv("EPHE_WORKSPACE", str(wd))
    return wd


class TestWorkspaceRulesLoader:
    def test_missing_file_injects_nothing(self, workspace):
        from core.workspace_rules import load_workspace_rules

        assert load_workspace_rules() is None

    def test_rules_carry_provenance_marker(self, workspace):
        from core.workspace_rules import load_workspace_rules

        (workspace / RULES_NAME).write_text(
            "Use rg for search. Prefer WGT/TDD.", encoding="utf-8"
        )
        text = load_workspace_rules()
        assert "Use rg for search" in text
        assert str(workspace / RULES_NAME) in text  # provenance shown

    def test_oversized_file_is_capped_with_note(self, workspace):
        from core.workspace_rules import load_workspace_rules

        body = "line rule\n" * 4000  # ~40k chars
        (workspace / RULES_NAME).write_text(body, encoding="utf-8")
        text = load_workspace_rules()
        assert len(text) <= WORKSPACE_RULES_MAX + 400
        assert "truncated" in text.lower()

    def test_empty_file_injects_nothing(self, workspace):
        from core.workspace_rules import load_workspace_rules

        (workspace / RULES_NAME).write_text("   \n  ", encoding="utf-8")
        assert load_workspace_rules() is None


class TestAssemblyPlacement:
    def test_workspace_rules_land_after_extra_before_profile(self):
        from core.chat import assemble_system_prompt

        prompt = assemble_system_prompt(
            model="test-model",
            incoming_system="[Skill]",
            extra_system_prompt="[Extra]",
            workspace_rules_ctx="[Workspace rules at C:]",
            profile_ctx="[Profile]",
        )
        p_extra = prompt.find("[Extra]")
        p_rules = prompt.find("[Workspace rules")
        p_profile = prompt.find("[Profile]")
        assert 0 <= p_extra < p_rules < p_profile


class TestContextStagesEndpoint:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        import os

        os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
        os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
        import core.engine_config as engine_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")

        from fastapi.testclient import TestClient
        from server.main import create_app

        return TestClient(create_app())

    def test_stages_report_char_counts(self, client, tmp_path):
        # Hermetic persona + workspace so the stage list is deterministic
        import os

        os.environ["EPHE_PERSONA_DIR"] = os.environ["EPHE_PERSONA_DIR"] = str(tmp_path / "persona")
        wd = tmp_path / "ws"
        wd.mkdir()
        os.environ["EPHE_WORKSPACE"] = os.environ["EPHE_WORKSPACE"] = str(wd)
        (wd / RULES_NAME).write_text("Project rule: test first.", encoding="utf-8")

        resp = client.get("/api/context/stages")
        assert resp.status_code == 200
        stages = {s["name"]: s for s in resp.json()["stages"]}
        assert {"identity", "persona", "tool_guidelines", "workspace_rules"} <= set(stages)
        assert stages["identity"]["chars"] > 0
        assert stages["persona"]["chars"] > 0
        assert "Project rule" in stages["workspace_rules"]["preview"]
        assert str(wd) in stages["workspace_rules"]["preview"]  # provenance path shown


class TestTheRulesDirectory:
    """Wave 2/B2: `.ephe/rules/*.md` joins AGENTS.md, deterministically and bounded."""

    def _rules(self, ws: Path) -> Path:
        rules = ws / ".ephe" / "rules"
        rules.mkdir(parents=True)
        return rules

    def test_agents_first_then_the_directory_sorted_by_name(self, workspace):
        from core.workspace_rules import read_workspace_rules

        (workspace / RULES_NAME).write_text("agents-body", encoding="utf-8")
        rules = self._rules(workspace)
        (rules / "20-later.md").write_text("later-body", encoding="utf-8")
        (rules / "10-first.md").write_text("first-body", encoding="utf-8")
        (rules / "notes.txt").write_text("not rules", encoding="utf-8")

        result = read_workspace_rules()
        text = result.text or ""
        assert text.index("agents-body") < text.index("first-body") < text.index("later-body")
        assert "not rules" not in text
        names = [entry.name for entry in result.files]
        assert names[0] == RULES_NAME
        assert names[1:] == [".ephe/rules/10-first.md", ".ephe/rules/20-later.md"]

    def test_a_missing_directory_is_simply_absent(self, workspace):
        from core.workspace_rules import read_workspace_rules

        (workspace / RULES_NAME).write_text("only agents", encoding="utf-8")
        result = read_workspace_rules()
        assert result.text and "only agents" in result.text
        assert [entry.name for entry in result.files] == [RULES_NAME]

    def test_each_file_carries_its_own_provenance_marker(self, workspace):
        from core.workspace_rules import read_workspace_rules

        rules = self._rules(workspace)
        (rules / "a.md").write_text("alpha", encoding="utf-8")
        (rules / "b.md").write_text("beta", encoding="utf-8")
        text = read_workspace_rules().text or ""
        assert text.count("## Project rules (from ") == 2
        assert "a.md" in text and "b.md" in text

    def test_the_per_file_cap_is_marked(self, workspace):
        from core.workspace_rules import RULE_FILE_MAX, read_workspace_rules

        rules = self._rules(workspace)
        (rules / "big.md").write_text("z" * (RULE_FILE_MAX + 50), encoding="utf-8")
        result = read_workspace_rules()
        entry = next(e for e in result.files if e.name.endswith("big.md"))
        assert entry.status == "truncated"
        assert "truncated" in (result.text or "")

    def test_the_combined_cap_marks_what_did_not_fit(self, workspace, monkeypatch):
        from core import workspace_rules as wr

        monkeypatch.setattr(wr, "WORKSPACE_RULES_MAX", 300)
        rules = self._rules(workspace)
        (rules / "a.md").write_text("a" * 250, encoding="utf-8")
        (rules / "b.md").write_text("b" * 250, encoding="utf-8")
        result = wr.read_workspace_rules()
        statuses = {e.name: e.status for e in result.files}
        assert statuses[".ephe/rules/a.md"] in ("included", "truncated")
        assert statuses[".ephe/rules/b.md"] in ("truncated", "skipped")
        assert len(result.text or "") <= 300
        assert "combined cap" in (result.text or "") or statuses[".ephe/rules/b.md"] == "skipped"

    def test_a_symlink_leaving_the_directory_is_denied(self, workspace, tmp_path):
        from core.workspace_rules import read_workspace_rules

        secret = tmp_path / "outside.md"
        secret.write_text("outside-body", encoding="utf-8")
        rules = self._rules(workspace)
        (rules / "escape.md").symlink_to(secret)
        result = read_workspace_rules()
        entry = next(e for e in result.files if e.name.endswith("escape.md"))
        assert entry.status == "denied"
        assert entry.reason == "outside-root"
        assert "outside-body" not in (result.text or "")

    def test_a_denied_root_is_skipped_with_the_stable_code(self, workspace, monkeypatch):
        from core import path_guard, workspace_rules as wr

        rules = self._rules(workspace)
        (rules / "protected.md").write_text("protected-body", encoding="utf-8")
        monkeypatch.setattr(
            path_guard, "DENY_ROOTS", (*path_guard.DENY_ROOTS, str(rules))
        )
        result = wr.read_workspace_rules()
        entry = next(e for e in result.files if e.name.endswith("protected.md"))
        assert entry.status == "denied"
        assert entry.reason == "protected-root"
        assert "protected-body" not in (result.text or "")

    def test_an_empty_file_is_named_not_injected(self, workspace):
        from core.workspace_rules import read_workspace_rules

        rules = self._rules(workspace)
        (rules / "void.md").write_text("   \n", encoding="utf-8")
        result = read_workspace_rules()
        entry = next(e for e in result.files if e.name.endswith("void.md"))
        assert entry.status == "empty"
        assert result.text is None

    def test_the_display_reads_the_same_text_the_prompt_does(self, workspace):
        from core.workspace_rules import load_workspace_rules, read_workspace_rules
        from server.routes.context import context_stages

        (workspace / RULES_NAME).write_text("agents-body", encoding="utf-8")
        result = read_workspace_rules()
        assert load_workspace_rules() == result.text
        stage = next(s for s in context_stages()["stages"] if s["name"] == "workspace_rules")
        assert (result.text or "")[:220] == stage["preview"]
        assert [f["name"] for f in stage["files"]] == [RULES_NAME]
