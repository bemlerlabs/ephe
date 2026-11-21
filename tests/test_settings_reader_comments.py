"""A comment that names a reader has to name a file that reads.

`core/settings_schema.py` names, area by area, the module that reads its fields. Those
lines are how whoever follows a register value finds the wiring, and three of them had
drifted: the schedule block named `core/scheduler.py` while `core/scheduler_config.py`
holds the four `deep_number` calls, the delete switch named `server/routes/sessions.py`,
which never mentions the field, and the desktop shortcut named the shell bridge while
`app/src/main.tsx` is the reader. A comment cannot be imported, so this is the
source-reading case `tests/AGENTS.md` admits with a stated reason: the constraint exists
only in a file the product cannot import.

The rule is narrow on purpose. A path in a comment of that file has to exist and has to
carry a key the register itself declares, because being a reader is the only reason to
name it. A module named for a different duty is written without its extension, the way
the schema writes `core/ephemeral_cell.forget()` for the door a cell leaves by.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.settings_schema import SCHEMA  # noqa: E402

SCHEMA_FILE = ROOT / "core" / "settings_schema.py"

#: A named reader is written as a path: a directory and an extension. A bare filename in
#: prose (`duration.ts`) is a shorthand for the reader of this file, not a claim to check.
NAMED_PATH = re.compile(r"[A-Za-z0-9_./-]+/[A-Za-z0-9_./-]+\.(?:py|ts|tsx)\b")


def _comment_paths() -> list[str]:
    found: list[str] = []
    for line in SCHEMA_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            for match in NAMED_PATH.finditer(line):
                if match.group(0) not in found:
                    found.append(match.group(0))
    return found


@pytest.mark.parametrize("rel", _comment_paths())
def test_a_named_reader_exists_and_reads_a_register_key(rel: str) -> None:
    """The file a comment points at has to be where the key is actually read."""
    path = ROOT / rel
    assert path.is_file(), f"{rel} is named as a reader in a settings comment and does not exist"
    body = path.read_text(encoding="utf-8", errors="replace")
    assert any(key in body for key in SCHEMA), (
        f"{rel} is named as a reader in a settings comment but names no register key"
    )


def test_the_comment_names_at_least_one_reader_per_area() -> None:
    """A guard that measures nothing is not a guard.

    The named paths are the ones this file's own comments point at; an empty list would
    mean the comments stopped naming readers, and the drift below came back silently.
    """
    named = _comment_paths()
    assert len(named) >= 10, named
    for rel in ("core/scheduler_config.py", "server/routes/session_mirror.py", "app/src/main.tsx"):
        assert rel in named, f"{rel} read a field of this register and no comment names it"
