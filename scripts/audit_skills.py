import sys, json, re, os
sys.path.insert(0, ".")

from core.skills import SkillLoader, SkillLoadError, _parse_frontmatter
from core.tools.registry import TOOL_MAP

loader = SkillLoader()

skill_names = sorted([d for d in os.listdir("skills") if os.path.isdir(f"skills/{d}")])

results = {
    "skills_checked": len(skill_names),
    "parse_errors": [],
    "missing_frontmatter": [],
    "tools_vs_allowed_tools_mismatch": [],
    "dead_tool_names": [],
    "empty_or_missing_refs_examples": [],
    "missing_test_block": [],
}

REQUIRED_FM_FIELDS = ["name", "trigger", "description", "tools", "allowed_tools", "when_to_use", "when_not_to_use", "quality_profile", "artifact_types"]

for name in skill_names:
    # (2) Parse with real loader
    try:
        skill = loader.load(name)
        parse_ok = bool(skill.system_prompt)
    except SkillLoadError as e:
        results["parse_errors"].append(f"{name}: {e}")
        continue
    except Exception as e:
        results["parse_errors"].append(f"{name}: {type(e).__name__}: {e}")
        continue

    # (1) Frontmatter completeness - check raw frontmatter
    skill_path = f"skills/{name}/SKILL.md"
    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()

    meta, body = _parse_frontmatter(content)

    missing = []
    for field_name in REQUIRED_FM_FIELDS:
        val = meta.get(field_name)
        if val is None or val == "" or val == []:
            missing.append(field_name)
    if missing:
        results["missing_frontmatter"].append({"skill": name, "missing": missing})

    # (3) tools vs allowed_tools consistency
    tools_set = set(skill.tools) if skill.tools else set()
    allowed_set = set(skill.allowed_tools) if skill.allowed_tools else set()
    if tools_set != allowed_set:
        results["tools_vs_allowed_tools_mismatch"].append({
            "skill": name,
            "tools": sorted(tools_set),
            "allowed_tools": sorted(allowed_set)
        })

    # Dead tool names: check allowed_tools against TOOL_MAP
    for t in skill.allowed_tools:
        if t not in TOOL_MAP:
            results["dead_tool_names"].append(f"{name}: {t}")

    # (4) references/rubric.md and examples/golden.md
    ref_path = f"skills/{name}/references/rubric.md"
    ex_path = f"skills/{name}/examples/golden.md"
    issues = []
    if not os.path.exists(ref_path):
        issues.append("missing references/rubric.md")
    else:
        with open(ref_path, "r", encoding="utf-8") as f:
            rc = f.read().strip()
        if len(rc) < 20:
            issues.append(f"references/rubric.md too short ({len(rc)} chars)")
    if not os.path.exists(ex_path):
        issues.append("missing examples/golden.md")
    else:
        with open(ex_path, "r", encoding="utf-8") as f:
            ec = f.read().strip()
        if len(ec) < 20:
            issues.append(f"examples/golden.md too short ({len(ec)} chars)")
    if issues:
        results["empty_or_missing_refs_examples"].append({"skill": name, "issues": issues})

    # (5) Test block coverage
    has_test = bool(skill.test.input or skill.test.expect_tool or skill.test.expect_contains)
    if not has_test:
        results["missing_test_block"].append(name)

print(json.dumps(results, ensure_ascii=False, indent=2))
