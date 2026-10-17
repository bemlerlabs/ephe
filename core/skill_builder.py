"""
◑ Ephe – Skill Builder
core/skill_builder.py

Automated skill creation: the AI scans the user's code style, generates a new
skill in Markdown format and stores it.

Security measures:
  - XML tag extraction (no chit-chat inside the .md file)
  - path traversal protection (sandbox on SKILLS_DIR)
  - overwrite protection (automatic versioning: -v2, -v3)
  - context limit (scan at most MAX_SCAN_FILES files, 20 today)
  - few-shot meta prompt (writer.md as the reference)

Ephe – Bad Liebenzell, Black Forest
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from core.chat import chat_with_tools
from core.skills import (
    SkillLoader,
    Skill,
    _parse_skill,
    SkillLoadError,
    BUILTIN_SKILLS_DIR,
)


# Scan limit

# P2-A: 20 instead of 5. The 5-file limit was a hard ceiling for realistic
# projects (core/ alone has 20+ files): the builder saw, say, core/skills.py
# but not core/tools/registry.py, so generated skills carried incomplete
# `tools:` lists. 20 still stays under ~2000 tokens per scan (short form per
# file), so it is budget-neutral.
MAX_SCAN_FILES = 20


# Load the few-shot reference

def _load_reference_skill() -> str:
    """Loads writer.md as the few-shot example for the meta prompt."""
    ref = BUILTIN_SKILLS_DIR / "writer.md"
    if ref.exists():
        return ref.read_text(encoding="utf-8")
    return ""


# System prompt with XML tags + few-shot

SKILL_BUILDER_SYSTEM = """\
You are the Skill Builder of ◑ Ephe. Your task: create a new skill for a topic the user describes.

## What is a skill?
A skill is a Markdown file in ~/.ephe/skills/.
It defines a specialized AI role with its own trigger command.

## Project structure (Ephe)
```
core/         → backend logic (chat.py, tools.py, skills.py, react.py)
server/       → FastAPI server (routes/chat.py, routes/memory.py)
app/src/      → web frontend
skills/       → built-in skills (writer.md, code-reviewer.md, etc.)
tests/        → TDD tests
```

## Reference skill (USE THIS EXACT FORMAT!)
Here is a perfect example of an existing skill:

{reference_skill}

## Your output format (STRICT!)
You MUST wrap your output in XML tags:

1. File name: <skill_filename>my-skill.md</skill_filename>
2. Content:   <new_skill_content>...the complete skill markdown...</new_skill_content>

Rules:
- skill name: lowercase with hyphens (e.g. fastapi-expert)
- Trigger: always starts with /, short (e.g. /fastapi)
- Description: at most 1 sentence
- System Prompt: precise role description. At most 200 words.
- Tools: only from: {tools}
- Test: a simple smoke test

## Context limit
When scanning code, read AT MOST {max_scan} files. That is enough to understand the style.

## IMPORTANT
- Output ONLY the XML tags. No smalltalk before or after.
- The content inside <new_skill_content> must follow the REFERENCE format EXACTLY.
"""


def _build_system_prompt() -> str:
    """Fill SKILL_BUILDER_SYSTEM with the dynamic, registered tool whitelist.

    Deep-Audit 2026-09-13 (F4): only 6 tools used to be hard-coded, so the
    builder could not reference the other 46 real ones. The list now comes from
    the registry — one source of truth, not a second fence.
    """
    from core.tools import get_tool_schemas

    names = sorted(
        entry.get("function", {}).get("name", "")
        for entry in get_tool_schemas()
        if entry.get("function", {}).get("name")
    )
    return SKILL_BUILDER_SYSTEM.format(
        reference_skill=_load_reference_skill(),
        max_scan=MAX_SCAN_FILES,
        tools=", ".join(names) if names else "web_search, read_file",
    )


# XML extraction (point 2: tame the output)

def extract_skill_content(llm_output: str) -> str:
    """
    Extract the skill Markdown content from the XML tags.

    Primary: <new_skill_content>...</new_skill_content>
    Fallback 1: ```markdown code block
    Fallback 2: the output starts directly with '# '

    Returns:
        The plain skill Markdown content (without smalltalk)

    Raises:
        SkillLoadError: no extractable content found
    """
    # Primary: XML tag extraction
    xml_match = re.search(
        r"<new_skill_content>\s*(.*?)\s*</new_skill_content>",
        llm_output,
        re.DOTALL,
    )
    if xml_match:
        return xml_match.group(1).strip()

    # Fallback 1: ```markdown code block
    md_match = re.search(
        r"```(?:markdown|md)\s*\n(.*?)```",
        llm_output,
        re.DOTALL,
    )
    if md_match:
        return md_match.group(1).strip()

    # Fallback 2: the output starts directly with # (no wrapper)
    if llm_output.strip().startswith("# "):
        return llm_output.strip()

    raise SkillLoadError(
        f"LLM output contains neither <new_skill_content> tags nor a ```markdown block.\nOutput (first 200 characters): {llm_output[:200]}"
    )


def extract_skill_filename(llm_output: str) -> str | None:
    """
    Extract the requested file name from the <skill_filename> tag.

    Returns:
        File name (e.g. "fastapi-expert.md") or None
    """
    match = re.search(
        r"<skill_filename>\s*(.*?)\s*</skill_filename>",
        llm_output,
    )
    if match:
        raw = match.group(1).strip()
        # First take the base name (strips ../ and directories)
        basename = Path(raw).name
        # Then keep only safe characters
        filename = re.sub(r"[^a-zA-Z0-9\-.]", "", basename)
        if filename and not filename.endswith(".md"):
            filename += ".md"
        return filename if filename else None
    return None


# Legacy alias for compatibility with the existing tests
extract_skill_markdown = extract_skill_content


def extract_skill_name(markdown: str) -> str:
    """Extract the skill name from the Markdown H1 line."""
    match = re.match(r"#\s+(.+)", markdown)
    if not match:
        raise SkillLoadError("No '# skill-name' header found.")
    return match.group(1).strip().lower().replace(" ", "-")


# Path traversal protection (point 1: sandboxing)

def _validate_skill_path(skills_dir: Path, filename: str) -> Path:
    """
    Validate the target path against path traversal attacks.

    Args:
        skills_dir: permitted base directory
        filename:   requested file name

    Returns:
        Safe, absolute path

    Raises:
        SecurityError: when the path lies outside skills_dir
    """
    # Normalise
    safe_name = Path(filename).name  # strips ../ and directories
    if not safe_name or safe_name.startswith("."):
        raise ValueError(f"invalid skill file name: '{filename}'")

    target = (skills_dir / safe_name).resolve()
    allowed = skills_dir.resolve()

    if not str(target).startswith(str(allowed)):
        raise PermissionError(
            f"Security violation: '{target}' is outside of '{allowed}'"
        )

    return target


# Overwrite protection (point 1b: versioning)

def _unique_skill_name(loader: SkillLoader, name: str) -> str:
    """
    A name free in both stores, suffixed until it is.
    If 'fastapi-expert' exists → 'fastapi-expert-v2', etc.

    Returns:
        Unique name (without .md)
    """
    if not loader.is_user_skill(name) and not loader.is_builtin(name):
        return name

    for version in range(2, 100):
        candidate = f"{name}-v{version}"
        if not loader.is_user_skill(candidate) and not loader.is_builtin(candidate):
            return candidate

    raise SkillLoadError(f"Too many versions of skill '{name}' (max 99).")


# Builder

async def build_skill(
    topic: str,
    model: str,
    on_phase: Callable[[str], None] | None = None,
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_done: Callable[[str, str], None] | None = None,
    skills_loader: SkillLoader | None = None,
) -> Skill:
    """
    Build a new skill from a topic.

    Security measures:
      - path traversal protection (sandboxing)
      - overwrite protection (automatic versioning)
      - XML extraction (clean output)
      - context limit (max 20 files, from MAX_SCAN_FILES)

    Args:
        topic:         what the skill should be able to do
        model:         Ollama model name
        on_phase:      callback for phase updates
        on_chunk:      callback for text chunks
        on_thinking:   callback for thinking tokens
        on_tool_start: callback when a tool starts
        on_tool_done:  callback when a tool finishes
        skills_loader: optional: SkillLoader instance (for tests)

    Returns:
        The stored Skill object

    Raises:
        ValueError:       empty topic
        SkillLoadError:   generated skill is invalid
        PermissionError:  path traversal attempt
    """
    topic = topic.strip()
    if not topic:
        raise ValueError("topic must not be empty.")

    loader = skills_loader or SkillLoader()

    # Phase 1+2: scan + generation
    if on_phase:
        on_phase("📚 Analyzing code patterns…")

    # Few-shot reference + dynamic tool whitelist (one source of truth: the registry)
    system = _build_system_prompt()

    # Collect the entire LLM output
    output_chunks: list[str] = []

    def _collect_chunk(chunk: str) -> None:
        output_chunks.append(chunk)
        if on_chunk:
            on_chunk(chunk)

    user_prompt = (
        f"Create a new skill for the following topic:\n\n"
        f"**{topic}**\n\n"
        f"First scan at most {MAX_SCAN_FILES} relevant files in the project "
        f"to understand the code style (use list_directory and read_file). "
        f"Then generate the skill in the XML tags "
        f"<skill_filename> and <new_skill_content>."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]

    await chat_with_tools(
        model=model,
        history=messages,
        on_chunk=_collect_chunk,
        on_thinking=on_thinking,
        on_tool_start=on_tool_start,
        on_tool_done=on_tool_done,
        on_phase=on_phase,
    )

    full_output = "".join(output_chunks)

    # Phase 3: XML extraction + validation + save
    if on_phase:
        on_phase("💾 Saving skill…")

    # Content extracted from the XML tags (no smalltalk!)
    skill_markdown = extract_skill_content(full_output)

    # Extract the name
    name = extract_skill_name(skill_markdown)

    # Parse for validation (before saving!)
    parsed = _parse_skill(name, skill_markdown)

    # Overwrite protection: generate a unique name
    unique_name = _unique_skill_name(loader, parsed.name)
    if unique_name != parsed.name:
        if on_phase:
            on_phase(f"📝 name '{parsed.name}' exists → '{unique_name}'")
        parsed = Skill(
            name=unique_name,
            trigger=parsed.trigger if unique_name == parsed.name else f"/{unique_name}",
            description=parsed.description,
            system_prompt=parsed.system_prompt,
            tools=parsed.tools,
            test=parsed.test,
        )

    # Path traversal protection: validate the path
    _validate_skill_path(loader._user_dir, f"{parsed.name}.md")

    # Save atomically via SkillLoader
    saved_skill = loader.save(
        name=parsed.name,
        trigger=parsed.trigger,
        description=parsed.description,
        tools=parsed.tools,
        system_prompt=parsed.system_prompt,
    )

    return saved_skill
