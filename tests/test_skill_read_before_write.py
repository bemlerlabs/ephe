"""R38: a skill that edits workspace files must also be able to read them."""

from pathlib import Path

from core.skills import _parse_frontmatter
from core.tools import TOOL_MAP
from core.tools.file_ops import (
    delete_file,
    edit_file,
    file_search,
    list_directory,
    read_file,
    write_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# Aliases (read/edit) fold onto the same functions in TOOL_MAP, so the
# capability sets come from the registry instead of a second name list.
READ_TOOLS = {
    name for name, impl in TOOL_MAP.items()
    if impl in {read_file, file_search, list_directory}
}
WRITE_TOOLS = {
    name for name, impl in TOOL_MAP.items()
    if impl in {write_file, edit_file, delete_file}
}


def _skill_files() -> list[Path]:
    return [
        *sorted((REPO_ROOT / "skills").glob("*/SKILL.md")),
        *sorted((REPO_ROOT / "marketplace" / "sources").glob("*/skills/*/SKILL.md")),
    ]


def test_every_skill_that_writes_files_can_read_them():
    files = _skill_files()
    assert files, "no SKILL.md files found"

    offenders = []
    for path in files:
        meta, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
        for field in ("tools", "allowed_tools"):
            declared = meta.get(field) or []
            if isinstance(declared, str):
                declared = [declared]
            declared = {str(tool).strip() for tool in declared}
            writes = sorted(declared & WRITE_TOOLS)
            if writes and not declared & READ_TOOLS:
                offenders.append(
                    f"{path.parent.name} ({path.relative_to(REPO_ROOT)}): "
                    f"{field} declares {', '.join(writes)} without a read tool"
                )

    assert not offenders, "\n".join(offenders)
