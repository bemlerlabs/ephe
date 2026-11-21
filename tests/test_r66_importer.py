"""R66 — Reference-client import (Extensions wave E6).

`ephe import <dir>` makes switching TO Ephe a first-class path. The importer
is vendor-neutral: it detects common local-agent artifacts by STRUCTURE
(persona files, SKILL.md skill trees, tool-server json, settings files) and
maps them onto Ephe's formats.

Contract (PR/FAQ): the plan is built and shown FIRST; nothing is written
without `apply`. An apply never overwrites existing Ephe state (persona,
mcp servers, skills are additive) and imported SKILLS LAND DISABLED until
the user switches them on.

1. scan/build_plan detects persona file, skill packs, tool-server json,
   settings file from a staged source directory — without any write.
2. apply_import copies the persona additively, imports skill packs into the
   user skills dir and marks them disabled, merges tool servers into
   mcp.json (existing servers preserved).
3. After apply, an imported skill is known to the loader but DISABLED
   (resolve_trigger returns None until enabled).
4. CLI: `ephe import <dir>` (plan) and `ephe import <dir> --apply`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import importer  # noqa: E402


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "source-agent"
    skills = src / "skills" / "my-skill"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: my-skill\nversion: \"1.0.0\"\ntrigger: /my-skill\ndescription: imported pack\n---\n"
        "# my-skill\n\n## System Prompt\nYou are imported. Do real work.\n",
        encoding="utf-8",
    )
    (src / "SOUL.md").write_text("You are a focused research agent.\n", encoding="utf-8")
    (src / ".mcp.json").write_text(json.dumps({"mcpServers": {"fs": {"url": "http://127.0.0.1:9000/mcp"}}}), encoding="utf-8")
    (src / "config.yaml").write_text("temperature: 0.2\nmax_tokens: 4096\n", encoding="utf-8")
    return src


class TestPlan:

    def test_plan_detects_everything_without_writing(self, source, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        plan = importer.build_import_plan(source)
        assert plan["persona"]["found"] is True and plan["persona"]["source_file"] == "SOUL.md"
        assert [s["name"] for s in plan["skills"]] == ["my-skill"]
        assert plan["mcp"]["servers"] == ["fs"]
        assert plan["settings"]["found"] is True
        assert plan["writes"] == []  # plan only — nothing recorded as written

    def test_empty_dir_is_honest(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        empty = tmp_path / "empty"
        empty.mkdir()
        plan = importer.build_import_plan(empty)
        assert plan["persona"]["found"] is False
        assert plan["skills"] == []
        assert plan["mcp"]["servers"] == []


class TestApply:

    def test_apply_imports_additively_and_disabled(self, source, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)
        result = importer.apply_import(source)
        assert result["persona"] is True
        assert result["skills"] == ["my-skill"]
        assert result["mcp_servers"] == ["http://127.0.0.1:9000/mcp"]

        cfg = tmp_path / "cfg"
        # persona lands additively; a second apply NEVER overwrites it
        persona = cfg / "persona.md"
        assert persona.read_text(encoding="utf-8").startswith("You are a focused")
        persona.write_text("custom persona", encoding="utf-8")
        importer.apply_import(source)
        assert persona.read_text(encoding="utf-8") == "custom persona"

        # skill pack copied into the user skills dir…
        assert (cfg / "skills" / "my-skill" / "SKILL.md").is_file()
        # …and DISABLED via the skills state file
        state = json.loads((cfg / "skills_state.json").read_text())
        assert state.get("disabled", {}).get("my-skill") is True

        # mcp servers merged as ephe spec strings; existing ones preserved
        mcp = json.loads((cfg / "mcp.json").read_text())
        assert "http://127.0.0.1:9000/mcp" in mcp["servers"]

    def test_imported_skill_known_but_disabled(self, source, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)
        importer.apply_import(source)
        monkeypatch.setattr("core.skills.DEFAULT_USER_SKILLS_DIR", tmp_path / "cfg" / "skills")
        monkeypatch.setattr("core.skills.DISABLED_SKILLS_FILE", tmp_path / "cfg" / "skills_state.json")
        from core.skills import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path / "cfg" / "skills")
        names = [s.name for s in loader.load_all()]
        assert "my-skill" in names
        assert loader.resolve_trigger("/my-skill") is None  # disabled until enabled


class TestCli:

    def test_parser_import(self):
        from ephe_cli import build_parser

        args = build_parser().parse_args(["import", "/tmp/src"])
        assert args.command == "import" and args.source == "/tmp/src"
        assert args.apply is False
        args = build_parser().parse_args(["import", "/tmp/src", "--apply"])
        assert args.apply is True
