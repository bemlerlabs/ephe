from pathlib import Path


EXPECTED_BUILTIN_TRIGGERS = {
    "/chart",
    "/code",
    "/deck",
    "/review",
    "/files",
    "/help",
    "/notebook",
    "/ephe",
    "/pdf",
    "/plan",
    "/shell",
    "/security-review",
    "/svg",
    "/scan",
    "/project",
    "/research",
    "/write",
    # Round 11 — artifacts + dev + business
    "/xlsx",
    "/docx",
    "/qr",
    "/image",
    "/diagram",
    "/test",
    "/refactor",
    "/debug",
    "/api",
    "/sql",
    "/regex",
    "/email",
    "/translate",
    "/summary",
    "/minutes",
    "/businessplan",
    "/cv",
    "/coverletter",
    "/data",
    "/competitor",
    "/swot",
    "/decision",
    "/roadmap",
    "/explain",
    "/quiz",
    "/checklist",
    "/social",
    # R34 — project factory (whole-project and document factories)
    "/factory",
    "/doc-factory",
    # R39 — media pipeline
    "/video",
    # Wave 4: new utility skills
    "/json",
    "/api-test",
    "/metrics",
    "/setup",
}


def test_given_builtin_skills_when_loaded_then_public_trigger_set_is_complete():
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    skills = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR).load_all()
    builtin = {
        path.name for path in BUILTIN_SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    builtin_skills = [skill for skill in skills if skill.name in builtin]
    triggers = {skill.trigger for skill in builtin_skills}

    assert triggers == EXPECTED_BUILTIN_TRIGGERS
    assert len(triggers) == len(builtin_skills)


def test_loaded_skill_triggers_are_unique_across_builtin_and_plugin_packs():
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    skills = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR).load_all()
    triggers = [skill.trigger for skill in skills if skill.trigger]
    duplicates = sorted({trigger for trigger in triggers if triggers.count(trigger) > 1})

    assert duplicates == []


def test_given_builtin_skills_when_tools_declared_then_every_tool_exists():
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader
    from core.tools.registry import addressable_tool_names

    known = addressable_tool_names()
    skills = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR).load_all()
    missing = {
        skill.name: [tool for tool in skill.tools if tool not in known]
        for skill in skills
    }
    missing = {name: tools for name, tools in missing.items() if tools}

    assert missing == {}


def test_given_shipped_packs_when_loaded_then_none_warns_about_its_own_text():
    """One pack contradicted itself, and the warning said less than the file did.

    The loader reads the frontmatter as the truth and warns when the bold line in the
    body answers differently. The warning was the smaller half of the symptom:
    `code-shell` promised `execute_code` in its body and in `allowed_tools`, while
    `tools` — the list `server/routes/chat.py` hands to the turn — left it out, so the
    skill advertised an instrument it was never offered. Every other pack that names
    the tool carries it in both fields, so the disagreement was an edit that landed in
    two of three places.

    The cache is emptied first: a warm read returns the parsed list without parsing,
    and the warning is a fact about parsing.
    """
    import warnings

    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader, invalidate_skill_cache

    invalidate_skill_cache()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = SkillLoader(
            skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR
        ).load_all()

    mismatched = sorted({str(w.message) for w in caught if "bold mismatch" in str(w.message)})

    assert mismatched == []
    assert len(loaded) > 1  # the answer is about the packs, and there have to be some


def test_given_high_impact_builtin_skills_when_loaded_then_they_require_real_tool_outputs():
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    loader = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR)

    for name, tool_name in {
        "chart-creator": "generate_chart",
        "deck-creator": "create_pptx_deck",
        "pdf-creator": "create_pdf",
        "svg-creator": "create_svg",
        "web-researcher": "web_search",
        "shell-helper": "run_shell",
        "vision-assistant": "analyze_image",
        "project-assistant": "analyze_project",
        "source-notebook": "create_source_notebook",
    }.items():
        skill = loader.load(name)
        assert tool_name in skill.tools
        assert "IMMER" in skill.system_prompt or "Always" in skill.system_prompt or "Nutze" in skill.system_prompt


def test_given_builtin_skills_when_loaded_then_each_has_high_end_output_contract():
    """
    GIVEN Ephe ships public built-in skills
    WHEN their prompts are loaded
    THEN every skill defines a premium output contract and quality gate.
    """
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    skills = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR).load_all()
    missing = {
        skill.name: [
            marker
            for marker in ["Output Contract", "Quality Gate", "Do not simulate"]
            if marker not in skill.system_prompt
        ]
        for skill in skills
    }
    missing = {name: markers for name, markers in missing.items() if markers}

    assert missing == {}


def test_given_tool_using_builtin_skills_when_loaded_then_they_require_evidence_from_real_tools():
    """
    GIVEN a built-in skill declares tools
    WHEN the prompt is inspected
    THEN it must require evidence from real tool output instead of invented results.
    """
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    skills = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR).load_all()
    missing = [
        skill.name
        for skill in skills
        if skill.tools and "real tool output" not in skill.system_prompt
    ]

    assert missing == []


def test_given_pdf_skill_when_loaded_then_it_requires_report_grade_documents():
    """
    GIVEN the PDF skill is a flagship user-facing artifact generator
    WHEN the prompt and tool schema are inspected
    THEN they require report-grade structure and verification-ready output.
    """
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader
    from core.tools import get_tool_schemas

    skill = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR).load("pdf-creator")
    prompt = skill.system_prompt
    assert "Executive Summary" in prompt
    assert "source notes" in prompt
    assert "appendix" in prompt
    assert "artifact-grade" in prompt

    schemas = get_tool_schemas()
    create_pdf_schema = next(s["function"] for s in schemas if s["function"]["name"] == "create_pdf")
    description = create_pdf_schema["description"]
    assert "Executive Summary" in description
    assert "quality-checked" in description


def test_given_high_impact_builtin_skills_when_loaded_then_they_have_progressive_references():
    """
    GIVEN high-impact skills should stay concise while offering deeper guidance
    WHEN they are loaded
    THEN each has external rubric/example support available to the quality layer.
    """
    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    loader = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR)
    for name in ["pdf-creator", "deck-creator", "project-assistant", "vision-assistant", "code-reviewer", "file-assistant"]:
        skill = loader.load(name)
        assert skill.has_references is True
        assert "Quality Rubric" in skill.reference_text
        assert "Golden Example" in skill.example_text


def test_given_builtin_skill_packs_when_loaded_then_each_declares_name_and_semver_version():
    """R16 pack format: every built-in skill is a pack (skills/{name}/SKILL.md)
    whose frontmatter declares name + semantic version. That is the basis
    for install/update/delete in the skill-pack management."""
    import re

    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    skills = SkillLoader(
        skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR
    ).load_all()
    builtin = {
        path.name for path in BUILTIN_SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    builtin_skills = [skill for skill in skills if skill.name in builtin]
    assert len(builtin_skills) >= 40

    semver = re.compile(r"^\d+\.\d+\.\d+$")
    problems: list[str] = []
    for skill in builtin_skills:
        pack_dir = BUILTIN_SKILLS_DIR / skill.name
        if not (pack_dir / "SKILL.md").exists():
            problems.append(f"{skill.name}: kein Pack (skills/{skill.name}/SKILL.md fehlt)")
            continue
        if skill.name != pack_dir.name:
            problems.append(f"{skill.name}: Frontmatter-name weicht vom Verzeichnisnamen ab")
        if not semver.match(skill.version):
            problems.append(f"{skill.name}: version '{skill.version}' ist keine semantische Version")
    assert not problems, f"THEN: Pack-Format-Verstoesse: {problems}"
