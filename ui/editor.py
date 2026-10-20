"""Open the composer draft in ``$VISUAL`` or ``$EDITOR`` and read it back.

The file is a temporary markdown document, so an editor with syntax support
treats the draft as prose. A missing editor or a non-zero exit leaves the
draft unchanged and names the reason; the app owns the terminal suspension.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path


def editor_command() -> list[str] | None:
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ""
    raw = raw.strip()
    if not raw:
        return None
    try:
        parts = shlex.split(raw)
    except ValueError:
        return None
    return parts or None


def run_editor(text: str, command: list[str] | None = None) -> tuple[str | None, str]:
    """Return the edited text, or ``(None, reason)`` when it did not change hands."""
    command = command or editor_command()
    if not command:
        return None, "No editor configured — set $VISUAL or $EDITOR."
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".md", prefix="ephe-draft-", delete=False, encoding="utf-8"
    )
    path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        try:
            completed = subprocess.run([*command, str(path)], check=False)
        except OSError as exc:
            return None, f"Could not start the editor ({command[0]}): {exc}"
        if completed.returncode != 0:
            return (
                None,
                f"The editor exited with code {completed.returncode}; the draft is unchanged.",
            )
        return path.read_text(encoding="utf-8").rstrip("\n"), ""
    finally:
        path.unlink(missing_ok=True)
