"""
◑ Ephe — TDD: R34 Project Factory (whole projects + briefing PDFs in one pass)

Owner order 2026-09-06: "Ephe has to be able to build complete projects —
finish them, not just hand them over" plus NotebookLM-style research PDFs.

Contract under test:
- deterministic factory intents route complete-project / briefing-PDF requests
  to the new skill packs (before generic artifact intents, without stealing
  plain "erstelle ein PDF" requests from pdf-creator);  # language-gate: ignore (the German utterance quoted from the routing cases this module pins)
- scaffold_project only reports success behind its verification gate and never
  touches non-empty directories;
- build_document produces a real page-count-verified PDF from local sources;
- both new tools are mutating (approval gate), verify_artifact is read-only.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.skills import BUILTIN_SKILLS_DIR, SkillLoader
from core.tools import base as tools_base
from core.tools import (
    build_document,
    factory_tools,
    scaffold_project,
    verify_artifact,
    verify_tools,
)


@pytest.fixture(scope="module")
def loader():
    return SkillLoader(skills_dir=Path("/tmp/ephe-r34-no-user-skills"),
                       builtin_dir=BUILTIN_SKILLS_DIR)


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "factory"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tools_base, "_resolve_allowed_roots", lambda: [root])
    return root


class TestFactoryIntentRouting:
    def test_given_complete_project_request_then_project_factory(self, loader):
        skill = loader.resolve_for_message(
            "Erstelle ein komplettes Projekt: ein CLI-Tool, das meine Ausgaben trackt.")
        assert skill is not None and skill.name == "project-factory"

    def test_given_from_scratch_english_request_then_project_factory(self, loader):
        skill = loader.resolve_for_message("Please build me a complete app from scratch: a bookmark shortener.")
        assert skill is not None and skill.name == "project-factory"

    def test_given_scaffold_phrase_then_project_factory(self, loader):
        skill = loader.resolve_for_message("Scaffold a new project called budget-tracker.")
        assert skill is not None and skill.name == "project-factory"

    def test_given_briefing_pdf_request_then_document_factory(self, loader):
        skill = loader.resolve_for_message(
            "Erstell mir ein Briefing-PDF über Batteriespeicher mit Quellen.")
        assert skill is not None and skill.name == "document-factory"

    def test_given_plain_pdf_request_then_pdf_creator_unaffected(self, loader):
        # Regression: the factory intents must NOT steal ordinary PDF jobs.
        skill = loader.resolve_for_message(
            "Erstelle eine atemberaubende PDF im McKinsey-Style über KI-Trends 2026.")
        assert skill is not None and skill.name == "pdf-creator"

    def test_given_project_analysis_request_then_not_factory(self, loader):
        # "analysiere mein Projekt" has no factory verb+complete pattern.  # language-gate: ignore (the German utterance quoted here is the literal resolved on the next line)
        skill = loader.resolve_for_message("Analysiere mein bestehendes Projekt und nenne Risiken.")
        assert skill is None or skill.name != "project-factory"


class TestFactorySkillPacks:
    def test_given_new_packs_when_loaded_then_quality_markers_present(self, loader):
        for name in ("project-factory", "document-factory"):
            skill = loader.load(name)
            prompt = skill.system_prompt
            for marker in ("Output Contract", "Quality Gate", "Do not simulate", "real tool output"):
                assert marker in prompt, f"{name} missing marker {marker!r}"
            assert skill.trigger in ("/factory", "/doc-factory")
            assert skill.version and skill.version[0].isdigit()

    def test_given_new_packs_when_tools_declared_then_all_registered(self, loader):
        from core.tools.registry import addressable_tool_names

        known = addressable_tool_names()
        for name in ("project-factory", "document-factory"):
            skill = loader.load(name)
            assert skill.tools
            for tool in skill.tools:
                assert tool in known, f"{name} declares unknown tool {tool}"

    def test_given_new_tools_when_registry_resolved_then_schemas_complete(self):
        from core.tools import get_tool_schemas

        schemas = {s["function"]["name"]: s["function"] for s in get_tool_schemas()}
        for name in ("scaffold_project", "build_document", "verify_artifact"):
            assert name in schemas
            assert len(schemas[name]["description"]) > 40
        scaffold = schemas["scaffold_project"]["parameters"]["properties"]
        assert "target_dir" in scaffold and "template" in scaffold
        document = schemas["build_document"]["parameters"]["properties"]
        assert "topic" in document and "source_paths" in document

    def test_given_scaffolder_and_builder_when_classified_then_mutating(self):
        from core.tools.approval import classify_tool

        assert classify_tool("scaffold_project").is_mutating is True
        assert classify_tool("build_document").is_mutating is True
        assert classify_tool("verify_artifact").is_mutating is False


class TestScaffoldProject:
    def test_given_fresh_dir_when_scaffolded_then_verified_with_full_layout(self, sandbox):
        out = asyncio.run(scaffold_project(str(sandbox / "budget-tracker"),
                                           template="python-cli",
                                           project_name="Budget Tracker",
                                           description="Track spending.",
                                           author=""))
        assert out.startswith("PROJECT_SCAFFOLD_VERIFIED"), out
        report = json.loads(out.split(": ", 1)[1])
        written = set(report["written"])
        for required in ("README.md", "LICENSE", ".gitignore", "docs/USAGE.md",
                         "pyproject.toml", "run.py", "tests/test_core.py"):
            assert required in written, f"missing {required}"
        assert report["checks"]["files"] >= 8
        assert report["checks"]["empty_files"] == []
        assert report["checks"]["has_readme"] is True

    def test_given_scaffolded_project_when_generated_tests_run_then_green(self, sandbox):
        import subprocess
        import sys

        asyncio.run(scaffold_project(str(sandbox / "qt"), template="python-cli",
                                     project_name="Quality Gates"))
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/"],
                                cwd=str(sandbox / "qt"), capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "3 passed" in result.stdout

    def test_given_all_templates_when_scaffolded_then_each_verifies(self, sandbox):
        for template in ("python-cli", "python-api", "node-cli", "web-app", "generic"):
            out = asyncio.run(scaffold_project(str(sandbox / f"p-{template}"),
                                               template=template, project_name="Demo One"))
            assert out.startswith("PROJECT_SCAFFOLD_VERIFIED"), f"{template}: {out[:200]}"

    def test_given_nonempty_dir_when_scaffolded_then_refuses_without_overwrite(self, sandbox):
        target = sandbox / "existing"
        target.mkdir()
        (target / "keepme.txt").write_text("precious data\n")
        out = asyncio.run(scaffold_project(str(target), template="generic", project_name="X"))
        assert out.startswith("[factory-error:") and "not empty" in out
        assert (target / "keepme.txt").read_text() == "precious data\n"

    def test_given_unknown_template_when_scaffolded_then_lists_allowed(self, sandbox):
        out = asyncio.run(scaffold_project(str(sandbox / "x"), template="kubernetes"))
        assert out.startswith("[factory-error:") and "python-cli" in out

    def test_given_outside_allowed_roots_when_scaffolded_then_denied(self):
        out = asyncio.run(scaffold_project("/etc/zz-not-allowed", template="generic"))
        assert out.startswith("[factory-error:") and "outside allowed roots" in out


class TestScaffoldScope:
    """The scaffold writes only where the call may write, and a data root is a read grant.

    A plugin call has its own roots: the workspace it may change plus the read roots its
    manifest declared. Until this class existed the scaffold resolved ALLOWED_ROOTS, which
    is plugin-agnostic, so a bridged call could land a whole skeleton in the checkout cwd
    or in a declared read-only data root.
    """

    @pytest.fixture()
    def plugin_scope(self, tmp_path, monkeypatch):
        from core.tools.base import PLUGIN_FILE_SCOPE

        workspace = tmp_path / "workspace"
        declared = tmp_path / "declared"
        workspace.mkdir()
        declared.mkdir()
        monkeypatch.setattr("core.engine_config.get_workspace_dir", lambda: str(workspace))
        monkeypatch.setattr(
            "core.capability_policy.resolved_data_roots",
            lambda plugin, root: [declared.resolve()],
        )
        token = PLUGIN_FILE_SCOPE.set("acme-research")
        try:
            yield SimpleNamespace(
                workspace=workspace, declared=declared, outside=tmp_path / "outside"
            )
        finally:
            PLUGIN_FILE_SCOPE.reset(token)

    def test_a_scope_escape_writes_no_file(self, plugin_scope):
        """A target outside the workspace and the declared read roots is refused."""
        target = plugin_scope.outside / "escaped"
        out = asyncio.run(
            scaffold_project(str(target), template="python-cli", project_name="Escape")
        )
        assert out.startswith("[factory-error:") and "outside allowed roots" in out, out
        assert not target.exists()

    def test_a_declared_data_root_stays_read_only(self, plugin_scope):
        """The manifest grants the data root as a read; the scaffold writes in the workspace."""
        from core.tools.base import ReadOnlyRootError

        target = plugin_scope.declared / "project"
        with pytest.raises(ReadOnlyRootError):
            asyncio.run(scaffold_project(str(target), template="generic"))
        assert list(plugin_scope.declared.iterdir()) == []

    def test_the_workspace_still_takes_a_full_skeleton(self, plugin_scope):
        """The rail that matters keeps working: a scope set, a workspace target, five files."""
        target = plugin_scope.workspace / "inside"
        out = asyncio.run(
            scaffold_project(str(target), template="python-cli", project_name="Inside")
        )
        assert out.startswith("PROJECT_SCAFFOLD_VERIFIED"), out
        written = list(target.rglob("*"))
        assert len([p for p in written if p.is_file()]) >= 5
        assert (target / "README.md").is_file()


class TestBuildDocument:
    @pytest.fixture()
    def doc_sandbox(self, tmp_path, monkeypatch, werkbank):
        root = tmp_path / "factory"
        root.mkdir(parents=True, exist_ok=True)
        # create_pdf delivers into the workbench (R4-A1) — the gate has to
        # accept that location for the PDF produced inside this test.
        monkeypatch.setattr(tools_base, "_resolve_allowed_roots", lambda: [root, werkbank])
        return root

    def test_given_local_sources_when_built_then_pdf_verified_on_disk(self, doc_sandbox):
        src = doc_sandbox / "notes.md"
        src.write_text(
            "# Notes\n\n"
            "- The renewable share grew by 14 percent in 2025 according to the agency report.\n"
            "- Battery pack costs fell below 100 dollars per kilowatt-hour this year.\n"
            "- Grid storage installations doubled compared to the previous year worldwide.\n")
        out = asyncio.run(build_document("State of battery storage 2026",
                                         source_paths=str(src),
                                         include_web_research=False))
        assert out.startswith("DOCUMENT_BUILT_VERIFIED"), out
        report = json.loads(out.split(": ", 1)[1])
        assert os.path.isfile(report["path"])
        assert report["metrics"]["pages"] >= 1
        assert str(src) in report["sources"]
        os.remove(report["path"])

    def test_given_empty_topic_when_built_then_honest_error(self, sandbox):
        out = asyncio.run(build_document("   ", include_web_research=False))
        assert out.startswith("[factory-error:")

    def test_given_unreadable_sources_when_built_then_still_delivers_report(self, doc_sandbox):
        out = asyncio.run(build_document("Quantum sensors market overview",
                                         source_paths=str(doc_sandbox / "missing.md"),
                                         include_web_research=False))
        # source is skipped honestly, the report is still generated from the fallback base
        assert out.startswith("DOCUMENT_BUILT_VERIFIED"), out
        report = json.loads(out.split(": ", 1)[1])
        assert report["sources"] == []
        os.remove(report["path"])

    def test_given_brief_composer_when_inspected_then_structured_sections(self):
        from core.tools.factory_tools import _compose_brief_markdown

        evidence = ("## Source: a.md\n\n- Long enough finding about the market here.\n"
                    "- Another substantive finding with numbers 42 percent growth.\n")
        md = _compose_brief_markdown("T", "topic", evidence)
        for section in ("Executive Summary", "Key Findings", "Analysis",
                        "Recommended Next Steps", "Source Notes"):
            assert section in md
        assert "a.md" in md
