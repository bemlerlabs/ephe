"""Ephe – Base exceptions, helpers, and constants for tool modules."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# Module-level shared Ollama client (reuse TCP connection)
_shared_client: Any | None = None
TOOL_SCHEMA_CACHE_TTL_SECONDS = 60.0
_TOOL_SCHEMA_CACHE: tuple[float, list[dict]] | None = None


def _get_shared_client() -> Any:
    """Lazy-initialized shared AsyncClient. Reuses TCP connection across calls.

    `ollama` is imported here (not module-globally): the package must stay
    importable offline-first (offline-first positioning, AGENTS.md),
    even when the Ollama client/module is missing in the current environment.
    """
    global _shared_client
    if _shared_client is None:
        import ollama
        _shared_client = ollama.AsyncClient()
    return _shared_client


# Custom Exceptions

class WebSearchError(Exception):
    """DuckDuckGo unreachable or another search failure."""


class FileNotAllowedError(PermissionError):
    """Path is not in the allowed whitelist."""
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"access denied: '{path}' is not in the allowed directories.\nAllowed: HOME, Desktop, Documents, Downloads, tmp"
        )


class DirectoryNotFoundError(FileNotFoundError):
    """Directory does not exist."""
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Directory not found: '{path}'")


class ShellConfirmationRequired(Exception):
    """
    Raised by run_shell().
    Tells the app: "the user must confirm before this gets executed."
    """
    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(f"Confirmation required for: {command}")


class SandboxConfirmationRequired(Exception):
    """
    Raised by the vision_* tools when sandbox mode is on.
    Tells the frontend (Web-UI/TUI): "show the approval dialog".
    """
    def __init__(self, tool_name: str, args: dict) -> None:
        self.tool_name = tool_name
        self.args = args
        super().__init__(f"Sandbox confirmation required for: {tool_name}")


class ShellTimeoutError(TimeoutError):
    """The command exceeded the timeout."""
    def __init__(self, command: str, timeout: int) -> None:
        self.command = command
        self.timeout = timeout
        super().__init__(f"Befehl '{command}' timed out after {timeout}s")


# Shell Security Constants

SHELL_TIMEOUT_SECONDS = 30

ALLOWED_COMMANDS: set[str] = {
    "ls", "echo", "cat", "head", "tail", "wc", "pwd", "whoami", "uname",
    "python", "python3", "node", "npm", "pip", "pip3",
    # P1b (Deep-Audit 2026-09-16): kept in sync with TEST_RUNNERS — the
    # run_tests defaults 'pytest -q' and 'npx/vitest run' would otherwise fail
    # on this whitelist before the runner check ever runs (validate runs first).
    "pytest", "npx", "vitest",
    "git", "docker", "docker-compose",
    "mkdir", "cp", "mv", "touch", "chmod",
    "date", "cal", "df", "du", "find", "grep", "sort", "cut", "tr",
    "ps", "top", "kill",
    "make", "cmake",
    "which", "type", "file", "stat",
    "open", "code", "vim", "nano",
    # R39: media conversion (demo pipeline + artifact postprocessing); heads stay
    # checked segment-wise, redirects/substitutions apply as before.
    "ffmpeg", "ffprobe",
    # deliberately NOT whitelisted (repo-hygiene audit 2026-09-06):
    #   curl/wget  → network exit from the shell; research runs through the
    #                web tools (web_search/browser_*), otherwise curl|sh class.
}

BLOCKED_PATTERNS: list[str] = [
    "rm ", "rm -rf", "rmdir", "mkfs", "dd ", "format",
    ":(){ :|:& };:",
    "> /dev/", "> /", "| sh", "| bash", "| zsh",
    "sudo ", "su ", "chown", "passwd",
    "shutdown", "reboot", "halt", "poweroff",
    ">|", ">>/", "2>/dev/",
    # command/process substitution bypasses every head check
    "$(", "<(", ">(", "`",
    # a newline starts a second command below the segment check
    "\n",
]

#: The allowed roots that hold whatever the process's working directory does.
_STATIC_ALLOWED_ROOTS: tuple[Path, ...] = (
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / ".ephe",
)


def _current_cwd() -> Path | None:
    """The working directory, or None when the directory this process sits in is gone.

    ``Path.cwd()`` raises FileNotFoundError for a directory that was removed or
    unmounted under a live process. A caller can act on that condition; the tool
    layer cannot answer for it by being unimportable, so it is read as "no
    working directory" here and never left to propagate.
    """
    try:
        return Path.cwd()
    except FileNotFoundError:
        return None


def _resolve_allowed_roots() -> list[Path]:
    """``ALLOWED_ROOTS``, resolved where it is read and not where it is imported.

    The working directory belongs in the list only while it can be named; a
    directory that is gone drops out, the same way ``_get_allowed_roots`` skips a
    workspace folder that is not a directory. Reading it per call also keeps the
    entry true after a chdir, where a snapshot taken at import time could not.
    """
    roots = list(_STATIC_ALLOWED_ROOTS)
    cwd = _current_cwd()
    if cwd is not None:
        roots.append(cwd)
    return roots


def __getattr__(name: str) -> Any:
    """Lazy module attribute (PEP 562) for the one name that must not be built at import.

    ``ALLOWED_ROOTS`` is deliberately absent from the module namespace: building the
    list at import time is what read ``Path.cwd()`` before any caller could catch it.
    """
    if name == "ALLOWED_ROOTS":
        return _resolve_allowed_roots()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# File / Workspace Limits

MAX_FILE_CHARS = 100_000
MAX_WORKSPACE_CHARS = 200_000
MAX_WORKSPACE_DEPTH = 3

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# Deck Constants

ENTERPRISE_DECK_PROFILES = {
    "product-platform",
    "engineering-platform",
    "strategy-leadership",
    "gtm-growth",
    "finance-ir",
    "consumer-retail",
}
ENTERPRISE_DESIGN_THEMES = {"evergreen", "executive", "studio"}
AMATEUR_DECK_TERMS = {
    "awesome", "cool", "fun", "cute", "wow", "magic", "game changer",
    "revolutionary", "super", "mega", "kindisch", "lustig", "krass", "geil",
    "amazing", "unicorn",
}


# Whitelist Helpers

def _get_allowed_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home,
        home / "Desktop",
        home / "Documents",
        home / "Dokumente",
        home / "Downloads",
        home / "Developer",
        home / "Code",
        home / "Projects",
        home / "Projekte",
        home / "tmp",
        Path("/tmp"),
        Path(os.environ.get("TMPDIR", "/tmp")),
    ]
    # F (workspace): the user-set project folder is explicitly allowed —
    # it can sit outside the standard roots (e.g. ~/ephe). Lazy import
    # against a circular import; on error → simply leave out the workspace root.
    try:
        from core.engine_config import get_workspace_dir

        ws = Path(get_workspace_dir())
        if ws.is_dir():
            roots.append(ws)
    except Exception:
        pass
    return roots


def allowed_root_of(real: str) -> str | None:
    """The allowed root that governs the real path `real`, or None when no root does.

    Which allowance a path falls under is a policy answer, and a deeper root wins
    (the user-set workspace inside HOME, say). That the path really sits below that
    root is then asserted at the call site: the same normalized string goes through
    the prefix check there, which is the form the path-injection analysis follows.

    `real` is expected to carry the trailing separator, so the root itself counts as
    contained and a sibling with the root's name as a prefix (`/tmp` vs `/tmpx`)
    does not.
    """
    best: str | None = None
    for root in _get_allowed_roots():
        root_real = os.path.realpath(str(root))
        if real.startswith(root_real + os.sep) and (best is None or len(root_real) > len(best)):
            best = root_real
    return best


def _is_path_allowed(path: Path) -> bool:
    resolved = path.resolve()
    for root in _get_allowed_roots():
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False
