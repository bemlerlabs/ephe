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
