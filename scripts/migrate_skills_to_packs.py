"""Migrate flat skills (skills/{name}.md) into the pack format (skills/{name}/SKILL.md).

R16 (docs/ROADMAP.md): versioned pack format for ALL built-in skills.
The pack format carries the skill metadata in YAML frontmatter (name, version,
trigger, tools, …); the Markdown body stays unchanged (the parser reads both,
frontmatter wins). Existing references folders (e.g. skills/pdf-creator/
references/) are left untouched — they already belong to the skill directory.

Idempotent: flat files that have already been migrated are skipped.
After writing, every SKILL.md is parsed again; if that fails, the
flat file stays in place (no data loss).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.skills import BUILTIN_SKILLS_DIR, SkillLoadError, _parse_skill  # noqa: E402


def _q(value: str) -> str:
    """Frontmatter-safe scalar (the naive parser strips surrounding quotes)."""
    return f'"{value}"'


def _frontmatter(skill) -> str:
    lines = [
        f"name: {skill.name}",
        f"version: {_q(skill.version)}",
        f"trigger: {skill.trigger}",
        f"description: {_q(skill.description)}",
        f"tools: [{', '.join(skill.tools)}]",
    ]
    if skill.when_to_use:
        lines.append(f"when_to_use: [{', '.join(skill.when_to_use)}]")
    if skill.when_not_to_use:
        lines.append(f"when_not_to_use: [{', '.join(skill.when_not_to_use)}]")
    lines.append(f"quality_profile: {skill.quality_profile}")
    if skill.artifact_types:
        lines.append(f"artifact_types: [{', '.join(skill.artifact_types)}]")
    lines.append(f"allowed_tools: [{', '.join(skill.allowed_tools)}]")
    return "---\n" + "\n".join(lines) + "\n---\n"


def main() -> int:
    skills_dir = BUILTIN_SKILLS_DIR
    flat = sorted(p for p in skills_dir.glob("*.md"))
    if not flat:
        print("no flat skills found — already migrated.")
        return 0

    migrated, failed = 0, 0
    for path in flat:
        name = path.stem
        content = path.read_text(encoding="utf-8")
        try:
            skill = _parse_skill(name, content, skill_dir=skills_dir / name)
        except SkillLoadError as exc:
            print(f"SKIP (unparsbar): {name}: {exc}")
            failed += 1
            continue

        target_dir = skills_dir / name
        target = target_dir / "SKILL.md"
        target_dir.mkdir(exist_ok=True)
        pack_content = _frontmatter(skill) + "\n" + content
        target.write_text(pack_content, encoding="utf-8")

        # Validate BEFORE the flat file gives way — no data loss.
        try:
            reparsed = _parse_skill(name, target.read_text(encoding="utf-8"), skill_dir=target_dir)
        except SkillLoadError as exc:
            target.unlink()
            print(f"FAIL (Reparse): {name}: {exc}")
            failed += 1
            continue
        if reparsed.trigger != skill.trigger or reparsed.tools != skill.tools:
            target.unlink()
            print(f"FAIL (Drift): {name}: trigger/tools weichen ab")
            failed += 1
            continue

        path.unlink()
        migrated += 1
        print(f"OK: {name} v{skill.version} ({'references' if reparsed.has_references else 'flat body'})")

    print(f"\n{migrated} migriert, {failed} fehlgeschlagen")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
