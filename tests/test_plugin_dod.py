"""A plugin label without the definition of done is red; a preset is not."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plugin_dod.py"


def _load():
    spec = importlib.util.spec_from_file_location("plugin_dod_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dod = _load()

EXAMPLE = """## Example

Input: Create a one-page brief about the Q3 numbers.
Tool-Call: {"name": "create_pdf", "arguments": {"path": "brief.pdf"}}
Answer: brief.pdf is openable and verified. ARTIFACT_VERIFIED.

"""


def _skill_md(name: str, examples: int = 2) -> str:
    return (
        "---\nname: " + name + "\n---\n\n# " + name + "\n\n"
        "## System Prompt\n\nProduce a real artifact and verify it.\n\n"
        + EXAMPLE * examples
        + "## Test\n\n**Input**: Create a PDF.\n**Expect Tool**: create_pdf\n"
    )


def _plugin(
    root: Path,
    name: str,
    *,
    commands: int = 3,
    examples: int = 2,
    changelog: bool = True,
    golden: int = 6,
) -> None:
    directory = root / "plugins" / name
    (directory / "prompts").mkdir(parents=True)
    (directory / "skills" / name).mkdir(parents=True)
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": "1.0.0",
        "components": {
            "skills": [name],
            "commands": [
                {"name": f"cmd{i}", "description": "Produce a real artifact", "template": "Create {input}."}
                for i in range(commands)
            ],
        },
        **({"changelog": "1.0.0 - initial release"} if changelog else {}),
    }
    (directory / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "skills" / name / "SKILL.md").write_text(_skill_md(name, examples), encoding="utf-8")
    cases = [
        {
            "id": f"{name}-{i}",
            "command": "cmd0" if commands else None,
            "input": "Create a one-page PDF with a table and a source line.",
            "expect": {"kind": "contains", "any": ["ARTIFACT_VERIFIED"]},
        }
        for i in range(golden)
    ]
    (directory / "prompts" / "golden.jsonl").write_text(
        "\n".join(json.dumps(case) for case in cases) + "\n", encoding="utf-8"
    )
    (root / "README.md").write_text(f"[{name}](plugins/{name})\n", encoding="utf-8")
    (root / "ephe-marketplace.json").write_text(
        json.dumps({"plugins": [{"name": name, "quality_label": "plugin"}]}), encoding="utf-8"
    )


def _skill_pack(root: Path, member: str = "beta") -> None:
    (root / "skills" / member / "examples").mkdir(parents=True)
    (root / "skills" / member / "references").mkdir(parents=True)
    (root / "skills" / member / "SKILL.md").write_text(_skill_md(member), encoding="utf-8")
    (root / "skills" / member / "examples" / "golden.md").write_text(
        "# Golden Example\n\n1. Input: Create a PDF.\n2. ToolCall: create_pdf\n", encoding="utf-8"
    )
    (root / "skills" / member / "references" / "rubric.md").write_text(
        "# Quality Rubric\n\n- The artifact exists.\n", encoding="utf-8"
    )
    (root / "skills" / "pack-index.json").write_text(
        json.dumps({"packs": [{"id": "pack", "title": "Pack", "description": "A pack.", "skills": [member]}]}),
        encoding="utf-8",
    )


def test_a_complete_plugin_passes(tmp_path):
    _plugin(tmp_path, "alpha")
    row = dod.audit(tmp_path)[0]
    assert row["dod"] is True
    assert row["problem"] == ""


def test_a_plugin_label_without_dod_is_red(tmp_path):
    _plugin(tmp_path, "alpha", commands=1, examples=0, changelog=False)
    row = dod.audit(tmp_path)[0]
    assert row["dod"] is False
    assert "plugin label without DoD" in row["problem"]


def test_a_capability_preset_needs_no_dod(tmp_path):
    _plugin(tmp_path, "alpha", commands=0, examples=0, changelog=False)
    (tmp_path / "ephe-marketplace.json").write_text(
        json.dumps({"plugins": [{"name": "alpha", "quality_label": "capability-preset"}]}),
        encoding="utf-8",
    )
    row = dod.audit(tmp_path)[0]
    assert row["label"] == "capability-preset"
    assert row["problem"] == ""


def test_an_unknown_label_is_refused(tmp_path):
    _plugin(tmp_path, "alpha")
    (tmp_path / "ephe-marketplace.json").write_text(
        json.dumps({"plugins": [{"name": "alpha", "quality_label": "marketing"}]}),
        encoding="utf-8",
    )
    assert "unknown quality label" in dod.audit(tmp_path)[0]["problem"]


def test_an_empty_example_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    skill = tmp_path / "plugins" / "alpha" / "skills" / "alpha" / "SKILL.md"
    skill.write_text(
        "## System Prompt\n\nDo the task.\n\n## Example\n\nInput:\nTool-Call:\nAnswer:\n"
        "## Example\n\nInput:\nTool-Call:\nAnswer:\n",
        encoding="utf-8",
    )
    assert "example" in dod.audit(tmp_path)[0]["problem"]


def test_a_placeholder_example_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    skill = tmp_path / "plugins" / "alpha" / "skills" / "alpha" / "SKILL.md"
    skill.write_text(
        "## System Prompt\n\nDo the task.\n\n## Example\n\nInput: TODO\n"
        'Tool-Call: {"name": "create_pdf"}\nAnswer: TBD\n\n'
        "## Example\n\nInput: TODO\n"
        'Tool-Call: {"name": "create_pdf"}\nAnswer: TBD\n',
        encoding="utf-8",
    )
    assert "example" in dod.audit(tmp_path)[0]["problem"]


def test_a_command_without_template_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    manifest_path = tmp_path / "plugins" / "alpha" / "ephe-plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"]["commands"][1]["template"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "command" in dod.audit(tmp_path)[0]["problem"]


def test_duplicate_command_names_are_red(tmp_path):
    _plugin(tmp_path, "alpha")
    manifest_path = tmp_path / "plugins" / "alpha" / "ephe-plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"]["commands"][1]["name"] = "cmd0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "duplicate command" in dod.audit(tmp_path)[0]["problem"]


def test_changelog_without_the_manifest_version_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    manifest_path = tmp_path / "plugins" / "alpha" / "ephe-plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["changelog"] = "initial release"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "changelog" in dod.audit(tmp_path)[0]["problem"]


def test_a_broken_golden_line_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    golden = tmp_path / "plugins" / "alpha" / "prompts" / "golden.jsonl"
    golden.write_text(golden.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    assert "golden" in dod.audit(tmp_path)[0]["problem"]


def test_a_golden_case_with_an_unknown_command_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    golden = tmp_path / "plugins" / "alpha" / "prompts" / "golden.jsonl"
    line = json.loads(golden.read_text(encoding="utf-8").splitlines()[0])
    line["id"] = "alpha-99"
    line["command"] = "missing"
    golden.write_text(json.dumps(line) + "\n" + golden.read_text(encoding="utf-8"), encoding="utf-8")
    assert "unknown command" in dod.audit(tmp_path)[0]["problem"]


def _pack_row(root: Path) -> dict:
    return next(row for row in dod.audit(root) if row.get("kind") == "skill-pack")


def test_a_complete_skill_pack_passes(tmp_path):
    _skill_pack(tmp_path)
    row = _pack_row(tmp_path)
    assert row["dod"] is True
    assert row["problem"] == ""


def test_a_pack_member_without_rubric_is_red(tmp_path):
    _skill_pack(tmp_path)
    (tmp_path / "skills" / "beta" / "references" / "rubric.md").unlink()
    assert "rubric" in _pack_row(tmp_path)["problem"]


def test_a_pack_index_with_a_missing_skill_is_red(tmp_path):
    _skill_pack(tmp_path)
    index = tmp_path / "skills" / "pack-index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    data["packs"][0]["skills"].append("ghost")
    index.write_text(json.dumps(data), encoding="utf-8")
    assert "ghost" in _pack_row(tmp_path)["problem"]


def test_a_declared_tool_outside_the_skill_grant_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    manifest_path = tmp_path / "plugins" / "alpha" / "ephe-plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"]["tools"] = ["create_pdf"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "outside the skill grant" in dod.audit(tmp_path)[0]["problem"]


def test_a_golden_tool_outside_the_skill_grant_is_red(tmp_path):
    _plugin(tmp_path, "alpha")
    golden = tmp_path / "plugins" / "alpha" / "prompts" / "golden.jsonl"
    line = json.loads(golden.read_text(encoding="utf-8").splitlines()[0])
    line["id"] = "alpha-99"
    line["expect"] = {"kind": "tool_use", "any": ["create_pdf"]}
    golden.write_text(json.dumps(line) + "\n" + golden.read_text(encoding="utf-8"), encoding="utf-8")
    assert "outside the skill grant" in dod.audit(tmp_path)[0]["problem"]
