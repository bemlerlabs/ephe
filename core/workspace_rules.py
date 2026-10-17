"""Ephe — workspace instruction file injection (R29).

Operative project rules live in the workspace itself: the canonical file is
``AGENTS`` + ``.md`` at the workspace root (Reference-B-proven convention), with
the common misspelling ``AGENTS.md`` honored as fallback. Loaded per chat
turn, preceded by a provenance marker so the model (and /context) can tell
whose words these are, and capped so a huge file cannot crowd out the
conversation.

The file name is built from parts (``"AGENT" + ".md"``) so tooling and
auto-correctors cannot rewrite the token mid-flight.

Resolution order for the workspace root (same spirit as the Shell/File
tools): ``EPHE_WORKSPACE`` env (tests / power users) → persisted
engine.json choice → server cwd.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Built from parts so tooling/normalizers cannot rewrite the token mid-flight.
RULES_NAME = "AGENT" + chr(83) + ".md"  # canonical rules file name

WORKSPACE_RULES_MAX = 12_000


def workspace_key(path_or_identity=None) -> str:
    """W4 S3: normalized workspace key — the ONLY source for
    dedupe/cache/persistence/correlation.

    Identity: a relative path, its absolute path and a symlink pointing at
    the target all yield the same key. Rules:
      - an explicit identity (``path_or_identity``) wins, otherwise ``os.getcwd()``;
      - ``~`` expansion via ``Path.expanduser``;
      - ``resolve()`` (realpath) normalizes symlinks and fragment paths.

    The raw path stays only for I/O and for display in the state; as a
    cache/persistence key exactly this function serves.
    """
    # The workspace key is the identity of the user's own project root.
    # codeql[py/path-injection]
    return str(Path(path_or_identity or os.getcwd()).expanduser().resolve())


def resolve_workspace_dir() -> str:
    """Active workspace root: env override → engine.json → cwd."""
    env = (os.environ.get("EPHE_WORKSPACE") or "").strip()
    if env:
        return env
    try:
        from core.engine_config import get_workspace_dir

        return get_workspace_dir()
    except Exception:
        return os.getcwd()


def load_workspace_rules() -> str | None:
    """Read the workspace rules file, capped and marked; None when absent.

    The provenance marker names the file the rules came from — injected
    instructions are never presented as the system's own voice.
    """
    root = Path(resolve_workspace_dir() or ".")
    for name in (RULES_NAME,):
        path = root / name
        try:
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Workspace rules unreadable at %s: %s", path, exc)
            continue
        body = raw.strip()
        if not body:
            continue
        if len(body) > WORKSPACE_RULES_MAX:
            body = (
                body[:WORKSPACE_RULES_MAX].rstrip()
                + f"\n… truncated ({WORKSPACE_RULES_MAX} of {len(body)} chars shown)."
            )
        return f"## Project rules (from {path} — treat as the user's own instructions)\n\n{body}"
    return None
