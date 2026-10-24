"""The Superpowers pack: adapted skills, nothing executable, attribution intact.

The upstream review (docs/SUPERPOWERS_REVIEW_PACKAGE_2026-10-23.md) refused a
core import for three reasons. This pack answers them in the marketplace shape:
provenance names the exact archive, the four skills that run local scripts are
excluded, and every skill parses in the Ephe loader.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import warnings
from pathlib import Path

from core import plugin_manifest
from core.skills import _parse_skill

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "marketplace" / "sources" / "superpowers"

EXPECTED = {
    "dispatching-parallel-agents",
    "executing-plans",
    "finishing-a-development-branch",
    "receiving-code-review",
    "requesting-code-review",
    "test-driven-development",
    "using-git-worktrees",
    "using-superpowers",
    "verification-before-completion",
    "writing-plans",
}


def test_the_manifest_is_valid_and_declares_only_skills() -> None:
    manifest, error = plugin_manifest.load_manifest(PACK)
    assert error is None, error
    assert manifest["name"] == "superpowers"
    assert manifest["origin"] == "third-party"
    assert set(manifest["components"]["skills"]) == EXPECTED
    assert manifest["components"]["tools"] == []
    assert manifest["components"]["commands"] == []


def test_every_skill_loads_with_a_real_prompt_and_no_frontmatter_drift() -> None:
    seen = set()
    for directory in sorted((PACK / "skills").iterdir()):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            skill = _parse_skill(
                directory.name,
                (directory / "SKILL.md").read_text(encoding="utf-8"),
                skill_dir=directory,
            )
        assert not caught, [str(w.message) for w in caught]
        assert skill.trigger.startswith("/sp-")
        assert len(skill.system_prompt) > 500, skill.name
        assert "## " not in skill.system_prompt, "a heading would cut the prompt block"
        seen.add(skill.name)
    assert seen == EXPECTED


def test_nothing_executable_or_host_specific_is_shipped() -> None:
    allowed_suffixes = {"", ".md", ".json"}
    for path in PACK.rglob("*"):
        relative = path.relative_to(PACK)
        assert not path.is_symlink(), relative
        if path.is_dir():
            assert relative.name not in {"hooks", "tests", "scripts", "references"}, relative
            assert not relative.name.endswith("-plugin"), relative
            continue
        mode = path.stat().st_mode
        assert not mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), relative
        assert path.suffix in allowed_suffixes, relative
        assert not relative.name.endswith("-tools.md"), relative
    for skill in (PACK / "skills").glob("*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        for marker in ("~/.codex", "codex-tools", "gemini-tools", "pi-tools",
                       "hermes-tools", "antigravity-tools", "references/"):
            assert marker not in text, f"{skill.parent.name}: host adapter marker {marker}"
        for excluded in ("subagent-driven-development", "brainstorming",
                         "systematic-debugging", "writing-skills"):
            assert excluded not in text, f"{skill.parent.name}: names excluded {excluded}"


def test_fenced_commands_were_not_turned_into_bold_prose() -> None:
    """Heading flattening once rewrote shell comments inside fences into bold
    lines; copied out, those are broken commands."""
    for skill in (PACK / "skills").glob("*/SKILL.md"):
        fenced = False
        for line in skill.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced and re.match(
                r"^\*\*(npm|npx|pnpm|yarn|git|cd|python|pytest|cargo|bun|ls|cat|mkdir|"
                r"echo|export|if|for|source)\b",
                line,
            ):
                raise AssertionError(f"{skill.parent.name}: bold command inside a fence: {line}")


def test_the_four_script_running_skills_are_not_present() -> None:
    for excluded in (
        "brainstorming",
        "systematic-debugging",
        "subagent-driven-development",
        "writing-skills",
    ):
        assert not (PACK / "skills" / excluded).exists(), excluded


def test_provenance_names_the_archive_and_the_exclusions() -> None:
    provenance = json.loads((PACK / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["commit"] == "b36e0829c6d0140e93cfef2ca599b1b07d4a7797"
    assert provenance["archive"]["sha256"] == (
        "7631e472822436006e15a399be890a01acae5a9d0d21fa02646c82e7449a3bc3"
    )
    assert set(provenance["included_skills"]) == EXPECTED
    assert set(provenance["excluded_skills"]) == {
        "brainstorming",
        "systematic-debugging",
        "subagent-driven-development",
        "writing-skills",
    }
    license_text = (PACK / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Jesse Vincent" in license_text
    notices = (PACK / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "b36e0829c6d0140e93cfef2ca599b1b07d4a7797" in notices


def test_the_marketplace_lists_the_pack_with_a_matching_artifact() -> None:
    index = json.loads((ROOT / "marketplace" / "index.json").read_text(encoding="utf-8"))
    entry = next(p for p in index["plugins"] if p["name"] == "superpowers")
    source = entry["versions"][0]["source"]
    artifact = ROOT / "marketplace" / source["url"]
    assert artifact.is_file()
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == source["sha256"]


def test_the_pack_takes_no_skill_name_from_the_builtins() -> None:
    builtin = {
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    assert not (EXPECTED & builtin)


def test_a_bundled_install_lands_the_pack_in_the_profile(tmp_path, monkeypatch) -> None:
    """The one-click path: plan from the bundled source, consent to the local
    unsigned artifact, install into the user's config root."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    from core import marketplace_service, plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    plan = marketplace_service.plan("bundled", "superpowers", allow_local_trust=True)
    assert plan["status"] == "ready", plan
    result = marketplace_service.install(plan)
    assert result["status"] == "extracted", result
    installed = tmp_path / "cfg" / "plugins" / "superpowers"
    assert len(list((installed / "skills").iterdir())) == 10
    assert plugin_runtime.lifecycle().snapshot("superpowers").enabled is True

    removed = marketplace_service.remove("superpowers")
    assert removed["status"] == "removed", removed
    assert not installed.exists()
    plugin_runtime.invalidate_ownership_cache()
