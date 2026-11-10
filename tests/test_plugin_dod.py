"""A plugin label without the definition of done is red; a preset is not."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from core.plugin_registry import scan_tool_activations
from core.tools.dynamic_registry import served_tool_name

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plugin_dod.py"


def _load():
    spec = importlib.util.spec_from_file_location("plugin_dod_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dod = _load()

SURFACE_CASES = [
    {"kind": "contains", "any": ["00:10"]},
    {"kind": "contains", "any": ["countdown"]},
    {"kind": "tool_use", "any": ["mcp_countdown_set"]},
    {"kind": "tool_use", "any": ["mcp_countdown_status"]},
    {"kind": "contains", "any": ["remaining"]},
    {"kind": "not_contains", "any": ["TODO", "placeholder"]},
]

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


def _surface_plugin(
    root: Path,
    name: str = "alpha",
    *,
    entry_html: str = "<!doctype html><script src='app.js'></script>",
    changelog: bool = True,
    readme: bool = True,
    golden: bool = True,
    surface: dict | None = None,
    tools: list | None = None,
    families: list[str] | None = None,
    commands: list[dict] | None = None,
    include_surface: bool = True,
) -> Path:
    """One Tier-1 v2 bundle: a surface, its entry document, one script, a suite."""
    directory = root / "plugins" / name
    (directory / "ui").mkdir(parents=True)
    (directory / "prompts").mkdir(parents=True)
    descriptor = {
        "type": "floating-window",
        "entry": "ui/index.html",
        "title": "Alpha countdown",
        "default_size": {"width": 260, "height": 120},
        "transparent": True,
        "always_on_top": True,
        "capabilities": ["notifications", "dock-badge", "audio-out"],
    }
    manifest = {
        "manifest_version": 2,
        "name": name,
        "version": "1.0.0",
        "description": "A countdown that shows where the shell can show it.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "origin": "first-party",
        "permissions": {"tool_families": families or [], "data_roots": ["shared"]},
        "components": {
            **(
                {"ui": descriptor if surface is None else surface}
                if include_surface
                else {}
            ),
            "tools": tools or [],
            "commands": commands or [],
        },
        **({"changelog": "1.0.0 - the walking skeleton"} if changelog else {}),
    }
    (directory / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "ui" / "index.html").write_text(entry_html, encoding="utf-8")
    (directory / "ui" / "app.js").write_text("document.title = 'alpha';\n", encoding="utf-8")
    cases = [
        {
            "id": f"{name}-{index}",
            "input": "Start a ten minute countdown and read the remaining time back.",
            "expect": expect,
        }
        for index, expect in enumerate(SURFACE_CASES, 1)
    ]
    if golden:
        (directory / "prompts" / "golden.jsonl").write_text(
            "\n".join(json.dumps(case) for case in cases) + "\n", encoding="utf-8"
        )
    (root / "README.md").write_text(
        f"[{name}](plugins/{name})\n" if readme else "no reference here\n", encoding="utf-8"
    )
    (root / "ephe-marketplace.json").write_text(
        json.dumps({"plugins": [{"name": name, "quality_label": "plugin"}]}), encoding="utf-8"
    )
    return directory


def _surface_row(root: Path) -> dict:
    return next(row for row in dod.audit(root) if row["name"] == "alpha")


def test_a_complete_v2_surface_bundle_passes(tmp_path):
    _surface_plugin(tmp_path)
    row = _surface_row(tmp_path)
    assert row["surface"] is True
    assert row["manifest_version"] == 2
    assert row["dod"] is True, row["problem"]
    assert row["problem"] == ""


def test_a_v2_bundle_without_a_surface_is_named(tmp_path):
    _surface_plugin(tmp_path, surface={})
    assert "components.ui" in _surface_row(tmp_path)["problem"]


def test_a_v2_bundle_of_tools_and_no_surface_passes(tmp_path):
    directory = _surface_plugin(
        tmp_path, include_surface=False, tools=[_tool()], families=["read"]
    )
    _ship(directory, str(_tool()["entry"]))
    row = _surface_row(tmp_path)
    assert row["surface"] is True
    assert row["tools"] == 1
    assert row["dod"] is True, row["problem"]


def test_a_v2_bundle_with_neither_surface_nor_tools_is_named(tmp_path):
    _surface_plugin(tmp_path, include_surface=False, tools=[])
    assert "components.ui" in _surface_row(tmp_path)["problem"]


def _tool(name: str = "tick", **over) -> dict:
    """The smallest `components.tools` entry a version 2 bundle declares."""
    tool = {
        "name": name,
        "entry": f"{name}.py:run",
        "family": "read",
        "description": "Report how many seconds are left.",
    }
    tool.update(over)
    return tool


def _ship(plugin_dir: Path, entry: str) -> None:
    """The file one declared entry names, binding `run` and nothing else."""
    path_part, sep, _callable = entry.rpartition(":")
    if not sep or not path_part:
        return
    target = plugin_dir / path_part
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"def run(arguments, state_dir):\n    return {{'remaining': 0}}\n",
        encoding="utf-8",
    )


def _tools_plugin(
    root: Path,
    tools: list[dict],
    *,
    families: tuple[str, ...] = ("read",),
    ship: bool = True,
) -> Path:
    """A Tier-2 bundle: the surface above, the tools it declares and the files it names."""
    directory = _surface_plugin(root, tools=tools, families=list(families))
    if ship:
        for tool in tools:
            if isinstance(tool, dict):
                _ship(directory, str(tool.get("entry") or ""))
    return directory


def test_a_complete_v2_bundle_with_tools_passes(tmp_path):
    _tools_plugin(tmp_path, [_tool(), _tool("status", entry="tools/status.py:run")])
    row = _surface_row(tmp_path)
    assert row["surface"] is True
    assert row["tools"] == 2
    assert row["dod"] is True, row["problem"]


def test_the_gate_and_the_activation_scan_read_one_bundle_alike(tmp_path):
    """What the gate accepts is what the portfolio claims, name for name."""
    _tools_plugin(tmp_path, [_tool(), _tool("status")])
    assert _surface_row(tmp_path)["dod"] is True
    served = sorted(served_tool_name("alpha", name) for name in ("tick", "status"))
    scanned = scan_tool_activations(tmp_path / "plugins")
    assert scanned.contributed == tuple(served)
    assert scanned.owners == tuple((name, "alpha") for name in served)
    assert scanned.conflicts == ()


BROKEN_PROMISES = [
    # The entry names a file the bundle never carries.
    ([_tool()], ("read",), False, "tool 'tick': entry file 'tick.py' does not ship"),
    # The entry names something other than a Python module.
    (
        [_tool(entry="handlers.js:run")],
        ("read",),
        True,
        "tool 'tick': entry 'handlers.js:run' is not a .py file",
    ),
    # The tool works in a family the manifest never asks permission for.
    (
        [_tool(family="shell")],
        ("read",),
        True,
        "tool 'tick': family 'shell' is outside the manifest's declared tool families",
    ),
    # Two declarations answer one served name.
    (
        [_tool(), _tool()],
        ("read",),
        True,
        "duplicate tool name 'tick': 2 declarations serve 'tick'",
    ),
    # The file ships and binds something else than the callable it promises.
    (
        [_tool(entry="tick.py:report")],
        ("read",),
        True,
        "tool 'tick': 'report' is not bound in 'tick.py'",
    ),
]


@pytest.mark.parametrize(
    ("tools", "families", "ship", "expected"),
    BROKEN_PROMISES,
    ids=["missing-entry", "entry-not-python", "family-undeclared", "name-taken", "callable-absent"],
)
def test_a_broken_tool_promise_is_a_problem_line(tmp_path, tools, families, ship, expected):
    _tools_plugin(tmp_path, tools, families=families, ship=ship)
    row = _surface_row(tmp_path)
    assert row["dod"] is False
    assert expected in row["problem"]


def test_a_declaration_the_contract_cannot_read_is_still_named(tmp_path):
    """A version 1 list holding a version 2 entry contributes no claim, and says so."""
    _plugin(tmp_path, "alpha")
    path = tmp_path / "plugins" / "alpha" / "ephe-plugin.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["components"]["tools"] = [_tool()]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "1 declared, 0 claims read" in dod.audit(tmp_path)[0]["problem"]


def test_a_v2_bundle_without_tools_declares_none(tmp_path):
    """The surface-only bundle stays a surface-only bundle: no tool line is added."""
    _surface_plugin(tmp_path)
    assert _surface_row(tmp_path)["tools"] == 0


def test_a_v2_bundle_needs_the_golden_suite_too(tmp_path):
    _surface_plugin(tmp_path, golden=False)
    assert "golden" in _surface_row(tmp_path)["problem"]


def test_a_v2_bundle_carries_the_changelog_rule(tmp_path):
    _surface_plugin(tmp_path, changelog=False)
    assert "changelog" in _surface_row(tmp_path)["problem"]


def test_a_v2_bundle_carries_the_readme_rule(tmp_path):
    _surface_plugin(tmp_path, readme=False)
    assert "README" in _surface_row(tmp_path)["problem"]


def test_a_v2_bundle_with_commands_is_held_to_the_command_rules(tmp_path):
    _surface_plugin(tmp_path, commands=[{"name": "one", "description": "One", "template": "x"}])
    assert "3-8" in _surface_row(tmp_path)["problem"]


def test_a_manifest_outside_the_two_read_versions_is_named(tmp_path):
    _surface_plugin(tmp_path)
    path = tmp_path / "plugins" / "alpha" / "ephe-plugin.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["manifest_version"] = 3
    path.write_text(json.dumps(manifest), encoding="utf-8")
    row = _surface_row(tmp_path)
    assert "v3" in row["problem"]
    assert row["dod"] is False


def test_a_surface_the_manifest_contract_refuses_reaches_the_gate(tmp_path):
    _surface_plugin(
        tmp_path,
        surface={
            "type": "floating-window",
            "entry": "ui/index.html",
            "title": "Alpha",
            "capabilities": ["telepathy"],
        },
    )
    assert "unknown capability" in _surface_row(tmp_path)["problem"]


def test_a_reference_that_leaves_the_bundle_is_refused(tmp_path):
    _surface_plugin(
        tmp_path,
        entry_html="<script src='https://cdn.example/alpha.js'></script>",
    )
    assert "leaves the bundle" in _surface_row(tmp_path)["problem"]


def test_a_reference_to_a_file_that_does_not_ship_is_refused(tmp_path):
    _surface_plugin(tmp_path, entry_html="<script src='ghost.js'></script>")
    assert "does not ship" in _surface_row(tmp_path)["problem"]


def test_an_absolute_reference_is_refused(tmp_path):
    _surface_plugin(tmp_path, entry_html="<script src='/ui/app.js'></script>")
    assert "is absolute" in _surface_row(tmp_path)["problem"]


def test_a_reference_stepping_out_is_refused(tmp_path):
    _surface_plugin(tmp_path, entry_html="<img src='../outside.png'>")
    assert "steps out" in _surface_row(tmp_path)["problem"]



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
