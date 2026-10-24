"""Engine-facing prompts are English unless the pack is explicitly German."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "engine_language_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("engine_language_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    plugin = root / "plugins" / "alpha"
    (plugin / "prompts").mkdir(parents=True)
    (plugin / "skills" / "alpha").mkdir(parents=True)
    (root / "skills" / "beta").mkdir(parents=True)
    return root


def _manifest(root: Path, **extra) -> Path:
    path = root / "plugins" / "alpha" / "ephe-plugin.json"
    path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "alpha",
                "version": "1.0.0",
                "components": {},
                **extra,
            }
        ),
        encoding="utf-8",
    )
    return path


def _kinds(root: Path) -> list[str]:
    return [item["kind"] for item in gate.scan(root)]


def test_a_german_command_template_is_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root, components={"commands": [{"name": "x", "description": "d", "template": "Erstelle ein Dokument."}]})
    assert "command" in _kinds(root)


def test_a_german_command_description_is_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root, components={"commands": [{"name": "x", "description": "Erstelle ein Dokument", "template": "Create it."}]})
    assert "command-description" in _kinds(root)


def test_a_german_manifest_description_is_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root, description="Erstellt echte PDF-Dokumente.")
    assert "manifest" in _kinds(root)


def test_an_english_command_passes(tmp_path):
    root = _root(tmp_path)
    _manifest(root, components={"commands": [{"name": "x", "description": "Create a document", "template": "Create a document."}]})
    assert gate.scan(root) == []


def test_english_with_the_word_die_is_not_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    skill = root / "skills" / "beta" / "SKILL.md"
    skill.write_text(
        "---\nname: beta\ndescription: The die is cast; multiply the matrix by the vector.\n---\n\n"
        "## System Prompt\n\nUse the MIT license. The die is cast; multiply the matrix by the vector.\n",
        encoding="utf-8",
    )
    assert gate.scan(root) == []


def test_a_german_golden_input_note_and_expectation_are_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    golden = root / "plugins" / "alpha" / "prompts" / "golden.jsonl"
    golden.write_text(
        json.dumps({"id": "alpha-1", "input": "Zähle die Zeilen.", "expect": {"kind": "contains", "any": ["ok"]}}) + "\n"
        + json.dumps({"id": "alpha-2", "input": "Count the lines.", "note": "Prüfe die Ausgabe.", "expect": {"kind": "contains", "any": ["ok"]}}) + "\n"
        + json.dumps({"id": "alpha-3", "input": "Count the lines.", "expect": {"kind": "contains", "any": ["Zähle die Zeilen"]}}) + "\n",
        encoding="utf-8",
    )
    kinds = _kinds(root)
    assert kinds.count("golden") == 3


def test_a_german_system_prompt_is_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    (root / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\n---\n\n## System Prompt\n\nDu bist ein Assistent.\n", encoding="utf-8"
    )
    assert "system-prompt" in _kinds(root)


def test_german_frontmatter_is_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    (root / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\ndescription: Erstellt echte PDF-Dokumente.\ntrigger: /pdf\n---\n\n"
        "## System Prompt\n\nYou are an assistant.\n",
        encoding="utf-8",
    )
    assert "frontmatter" in _kinds(root)


def test_german_example_test_and_reference_sections_are_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    skill = root / "skills" / "beta" / "SKILL.md"
    skill.write_text(
        "---\nname: beta\n---\n\n## System Prompt\n\nYou are an assistant.\n\n"
        "## Example\n\nInput: Erstelle ein PDF.\nAnswer: Done.\n\n"
        "## Test\n\n**Input**: Prüfe die Ausgabe.\n\n## Reference\n\n- Prüfe die Quelle.\n",
        encoding="utf-8",
    )
    kinds = _kinds(root)
    for kind in ("example", "test", "reference"):
        assert kind in kinds


def test_german_sidecar_example_and_reference_are_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    (root / "skills" / "beta" / "examples").mkdir()
    (root / "skills" / "beta" / "references").mkdir()
    (root / "skills" / "beta" / "examples" / "golden.md").write_text(
        "# Golden Example\n\n1. Input: Erstelle ein PDF.\n", encoding="utf-8"
    )
    (root / "skills" / "beta" / "references" / "rubric.md").write_text(
        "# Quality Rubric\n\n- Prüfe die Quelle.\n", encoding="utf-8"
    )
    kinds = _kinds(root)
    assert "example-file" in kinds
    assert "reference-file" in kinds


def test_a_german_pack_description_is_flagged(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    (root / "skills" / "pack-index.json").write_text(
        json.dumps({"packs": [{"id": "pack", "title": "Paket", "description": "Erstelle echte Dokumente.", "skills": []}]}),
        encoding="utf-8",
    )
    assert "pack-description" in _kinds(root)


def test_a_marker_on_an_unlisted_skill_is_red(tmp_path):
    root = _root(tmp_path)
    _manifest(root)
    (root / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nlanguage: de\n---\n\n## System Prompt\n\nDu bist ein Assistent.\n",
        encoding="utf-8",
    )
    kinds = _kinds(root)
    assert "language-marker" in kinds
    assert "system-prompt" in kinds


def test_an_allowlisted_german_pack_may_be_marked(tmp_path, monkeypatch):
    root = _root(tmp_path)
    _manifest(root)
    (root / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nlanguage: de\n---\n\n## System Prompt\n\nDu bist ein Assistent.\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(gate.GERMAN_PACKS, "beta", "deliberately German pack")
    assert gate.scan(root) == []


def test_a_baselined_finding_is_not_growth():
    findings = [{"path": "plugins/a.json", "kind": "command", "text": "x"}]
    assert gate.growth(findings, {"plugins/a.json::command": 1}) == []


def test_a_new_finding_is_growth():
    findings = [{"path": "plugins/a.json", "kind": "command", "text": "x"}]
    assert gate.growth(findings, {}) == ["plugins/a.json::command: 1 > baseline 0"]


def test_a_lower_count_than_baseline_is_allowed():
    findings = [{"path": "plugins/a.json", "kind": "command", "text": "x"}]
    assert gate.growth(findings, {"plugins/a.json::command": 2}) == []
