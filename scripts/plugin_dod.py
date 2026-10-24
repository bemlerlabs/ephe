#!/usr/bin/env python3
"""Definition-of-done gate for the first-party catalogue.

A plugin label is only allowed when the manifest is v1 and carries 3–8
commands with a description and a non-empty template, at least two non-empty
few-shot examples with input, tool call and answer, a changelog line naming
the manifest version, a README section and at least six valid golden cases.
The five bundled skill packs carry their own DoD: every member skill ships a
SKILL.md with a system prompt and an example, a rubric and a golden file.

    python3 scripts/plugin_dod.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_golden import load_golden  # noqa: E402

LABELS = {"plugin", "capability-preset"}
MANIFEST_VERSION = 1
COMMAND_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
EXAMPLE = re.compile(r"^##\s+Example\b[^\n]*\n(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
SYSTEM = re.compile(r"^##\s+System Prompt\s*\n(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
LABEL = re.compile(r"^\s*(Input|Tool-Call|Answer)\s*:\s*(.+)$", re.MULTILINE)
PLACEHOLDER = re.compile(r"(?i)\b(todo|tbd|fixme|placeholder)\b|<[^>\n]+>")


def _labels(root: Path) -> dict[str, str]:
    try:
        entries = json.loads((root / "ephe-marketplace.json").read_text(encoding="utf-8")).get("plugins") or []
    except (OSError, ValueError):
        return {}
    return {
        str(entry.get("name")): str(entry.get("quality_label") or "plugin")
        for entry in entries
        if isinstance(entry, dict)
    }


def _placeholder(value: str) -> bool:
    return len(value.strip()) < 3 or bool(PLACEHOLDER.search(value))


def _command_problems(commands: object) -> list[str]:
    if not isinstance(commands, list):
        return ["commands: list expected"]
    problems: list[str] = []
    if not 3 <= len(commands) <= 8:
        problems.append(f"{len(commands)} commands (3-8 required)")
    seen: set[str] = set()
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            problems.append(f"command {index}: object expected")
            continue
        name = str(command.get("name") or "")
        if not COMMAND_NAME.match(name):
            problems.append(f"command {index}: bad slug {name!r}")
        elif name in seen:
            problems.append(f"duplicate command {name!r}")
        seen.add(name)
        for field in ("description", "template"):
            value = str(command.get(field) or "")
            if not value.strip():
                problems.append(f"command {name or index}: empty {field}")
            elif _placeholder(value):
                problems.append(f"command {name or index}: placeholder {field}")
    return problems


def _example_problems(text: str) -> list[str]:
    sections = EXAMPLE.findall(text)
    problems: list[str] = [f"{len(sections)} examples (at least 2 required)"] if len(sections) < 2 else []
    for index, body in enumerate(sections, 1):
        labels: dict[str, list[str]] = {"input": [], "tool-call": [], "answer": []}
        for match in LABEL.finditer(body):
            labels[match.group(1).lower()].append(match.group(2).strip())
        for label, values in labels.items():
            if not values:
                problems.append(f"example {index}: no {label}")
            elif any(_placeholder(value) for value in values):
                problems.append(f"example {index}: placeholder {label}")
        for value in labels["tool-call"]:
            try:
                record = json.loads(value)
            except ValueError:
                problems.append(f"example {index}: tool call is not JSON")
                continue
            if not isinstance(record, dict) or not record.get("name"):
                problems.append(f"example {index}: tool call needs a name")
    return problems


def _allowed_tools(plugin_dir: Path, packs: list[str]) -> set[str]:
    allowed: set[str] = set()
    for pack in packs:
        path = plugin_dir / "skills" / str(pack) / "SKILL.md"
        if not path.is_file():
            continue
        front = path.read_text(encoding="utf-8").split("---", 2)
        if len(front) < 2:
            continue
        for line in front[1].splitlines():
            if line.startswith("allowed_tools:"):
                raw = line.split(":", 1)[1].strip().strip("[]")
                allowed |= {item.strip() for item in raw.split(",") if item.strip()}
    return allowed


def _tool_grant_problems(plugin_dir: Path, manifest: dict, cases: list[dict]) -> list[str]:
    packs = [str(pack) for pack in (manifest.get("components") or {}).get("skills") or []]
    allowed = _allowed_tools(plugin_dir, packs)
    declared = {
        str(tool)
        for tool in (manifest.get("components") or {}).get("tools") or []
    }
    problems = [f"declared tool {tool!r} is outside the skill grant" for tool in sorted(declared - allowed)]
    used: set[str] = set()
    for case in cases:
        expect = case.get("expect") or {}
        if expect.get("kind") == "tool_use":
            used |= {str(tool) for tool in expect.get("any") or []}
    problems.extend(f"golden tool {tool!r} is outside the skill grant" for tool in sorted(used - allowed))
    return problems


def _golden_problems(plugin_dir: Path, name: str, commands: list[dict], manifest: dict) -> list[str]:
    path = plugin_dir / "prompts" / "golden.jsonl"
    if not path.is_file():
        return ["golden: prompts/golden.jsonl is missing"]
    try:
        cases = load_golden(path, name)
    except ValueError as exc:
        return [f"golden: {exc}"]
    problems: list[str] = []
    if len(cases) < 6:
        problems.append(f"{len(cases)} golden cases (<6)")
    names = {str(command.get("name")) for command in commands if isinstance(command, dict)}
    for case in cases:
        command = case.get("command")
        if command is not None and command not in names:
            problems.append(f"golden {case['id']}: unknown command {command!r}")
    problems.extend(_tool_grant_problems(plugin_dir, manifest, cases))
    return problems


def _skill_problems(skill_dir: Path) -> list[str]:
    markdown = skill_dir / "SKILL.md"
    label = skill_dir.name
    if not markdown.is_file():
        return [f"{label}: SKILL.md is missing"]
    text = markdown.read_text(encoding="utf-8")
    problems: list[str] = []
    match = SYSTEM.search(text)
    if not match or not match.group(1).strip():
        problems.append(f"{label}: no system prompt")
    example = EXAMPLE.search(text)
    if not example or not example.group(1).strip():
        problems.append(f"{label}: no example")
    for relative in ("references/rubric.md", "examples/golden.md"):
        path = skill_dir / relative
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            problems.append(f"{label}: {relative} is missing")
    return problems


def pack_audit(root: Path = ROOT) -> list[dict]:
    index = root / "skills" / "pack-index.json"
    if not index.is_file():
        return []
    try:
        packs = json.loads(index.read_text(encoding="utf-8")).get("packs") or []
    except (OSError, ValueError):
        return [{
            "kind": "skill-pack", "name": "pack-index", "label": "bundled",
            "skills": 0, "dod": False, "problem": "pack-index.json is not valid JSON",
        }]
    rows: list[dict] = []
    for pack in packs:
        pack_id = str(pack.get("id") or "?")
        skills = pack.get("skills") or []
        problems: list[str] = []
        if not isinstance(skills, list) or not skills:
            problems.append("pack lists no skills")
            skills = []
        elif len(set(skills)) != len(skills):
            problems.append("duplicate skill in pack")
        for skill in skills:
            problems.extend(_skill_problems(root / "skills" / str(skill)))
        rows.append({
            "kind": "skill-pack",
            "name": pack_id,
            "label": "bundled",
            "skills": len(skills),
            "dod": not problems,
            "problem": "; ".join(problems),
        })
    return rows


def audit(root: Path = ROOT) -> list[dict]:
    labels = _labels(root)
    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
    rows: list[dict] = []
    for manifest_path in sorted((root / "plugins").glob("*/ephe-plugin.json")):
        plugin_dir = manifest_path.parent
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            rows.append({
                "kind": "plugin", "name": plugin_dir.name, "label": labels.get(plugin_dir.name, "plugin"),
                "commands": 0, "examples": 0, "changelog": False, "readme": False, "golden": 0,
                "manifest_v1": False, "dod": False, "problem": f"manifest is not valid JSON: {exc}",
            })
            continue
        name = str(manifest.get("name") or plugin_dir.name)
        components = manifest.get("components") or {}
        commands = components.get("commands") or []
        skill_packs = components.get("skills") or []
        skill_text = ""
        for pack in skill_packs:
            path = plugin_dir / "skills" / str(pack) / "SKILL.md"
            if path.is_file():
                skill_text += path.read_text(encoding="utf-8")
        examples = len(EXAMPLE.findall(skill_text))
        changelog_text = str(manifest.get("changelog") or "").strip()
        version = str(manifest.get("version") or "")
        changelog = bool(changelog_text) and bool(re.search(rf"\b{re.escape(version)}\b", changelog_text))
        readme_ref = f"plugins/{name}" in readme
        golden_path = plugin_dir / "prompts" / "golden.jsonl"
        golden = sum(1 for line in golden_path.read_text(encoding="utf-8").splitlines() if line.strip()) if golden_path.is_file() else 0
        manifest_v1 = manifest.get("manifest_version") == MANIFEST_VERSION
        problems: list[str] = []
        if not manifest_v1:
            problems.append(f"manifest v{manifest.get('manifest_version')} (v{MANIFEST_VERSION} required)")
        if not skill_packs:
            problems.append("no declared skill pack")
        problems.extend(_command_problems(commands))
        problems.extend(_example_problems(skill_text))
        if not changelog_text:
            problems.append("no changelog")
        elif not changelog:
            problems.append(f"changelog does not name version {version or '?'}")
        if not readme_ref:
            problems.append("no README reference")
        problems.extend(_golden_problems(plugin_dir, name, commands, manifest))
        dod = not problems
        label = labels.get(name, "plugin")
        problem = ""
        if label not in LABELS:
            problem = f"unknown quality label {label!r}"
        elif label == "plugin" and not dod:
            problem = "plugin label without DoD: " + "; ".join(problems)
        rows.append({
            "kind": "plugin",
            "name": name,
            "label": label,
            "commands": len(commands) if isinstance(commands, list) else 0,
            "examples": examples,
            "changelog": changelog,
            "readme": readme_ref,
            "golden": golden,
            "manifest_v1": manifest_v1,
            "dod": dod,
            "problem": problem,
        })
    return rows + pack_audit(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable rows")
    args = parser.parse_args(argv)
    rows = audit()
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            mark = "PASS" if not row["problem"] else "FAIL"
            if row.get("kind") == "skill-pack":
                detail = f"skills={row['skills']}"
            else:
                detail = (
                    f"commands={row['commands']} examples={row['examples']} "
                    f"changelog={int(row['changelog'])} readme={int(row['readme'])} "
                    f"golden={row['golden']}"
                )
            print(
                f"{mark:4} {row['name']:14} {row['label']:18} {detail}"
                + (f" | {row['problem']}" if row["problem"] else "")
            )
    problems = [row for row in rows if row["problem"]]
    plugins = sum(1 for row in rows if row.get("kind") == "plugin")
    packs = sum(1 for row in rows if row.get("kind") == "skill-pack")
    print(f"plugin-dod: {plugins} plugins, {packs} skill packs, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
