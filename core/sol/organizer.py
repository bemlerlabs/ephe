"""SOL phase 1 — the workspace learning map.

What the agent would otherwise rediscover on every first tool call: which
runtime the project uses, with which version, how its own commands are spelled
and which environment details change their outcome (a Corepack pin, a Python
version file, a virtualenv). It is read from the manifests at the workspace
root, never from a model call, so the cost is a handful of stats when nothing
changed.

The map is keyed by a fingerprint over those manifests (relative name, mtime
and size). A manifest edit makes the next turn rebuild it; nothing else does.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

LEARNING_DIR = Path(".ephe") / "learning"
MAP_NAME = "map.json"
MAP_VERSION = 1

#: Manifests the map is built from; every one of them is part of the fingerprint.
TRACKED = (
    "package.json",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "poetry.lock",
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    "go.mod",
    "go.sum",
    ".python-version",
    ".nvmrc",
    ".node-version",
    ".tool-versions",
    "Makefile",
    "Dockerfile",
)

#: A manifest larger than this is a lock file in disguise; the map skips it.
MAX_MANIFEST_BYTES = 400_000

#: The prompt header is a context block, not a document: 200 tokens is ~800 chars.
MAP_HEADER_MAX_CHARS = 800

#: Per-list caps, so a monorepo cannot grow the header without bound.
MAX_COMMANDS = 6
MAX_QUIRKS = 6


def workspace_root() -> Path:
    """The active workspace, resolved the way the rules layer resolves it."""
    from core.workspace_rules import resolve_workspace_dir

    return Path(resolve_workspace_dir()).expanduser().resolve()


def learning_dir(root: Path | None = None) -> Path:
    return (root or workspace_root()) / LEARNING_DIR


def _rel_files(root: Path) -> list[tuple[str, int, int]]:
    """(name, mtime_ns, size) for every tracked manifest that exists."""
    out: list[tuple[str, int, int]] = []
    for name in TRACKED:
        path = root / name
        try:
            stat = path.stat()
        except OSError:
            continue
        if not path.is_file():
            continue
        out.append((name, stat.st_mtime_ns, stat.st_size))
    return out


def fingerprint(root: Path) -> str:
    digest = hashlib.blake2b(digest_size=12)
    for name, mtime, size in _rel_files(root):
        digest.update(f"{name}\0{mtime}\0{size}\n".encode())
    return digest.hexdigest()


def _read(root: Path, name: str) -> str:
    path = root / name
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _package_json(root: Path) -> dict:
    raw = _read(root, "package.json")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _node_version(root: Path) -> str:
    engines = (_package_json(root).get("engines") or {})
    if isinstance(engines, dict):
        value = str(engines.get("node") or "").strip()
        if value:
            return value.lstrip("^~>= ")
    for name in (".nvmrc", ".node-version"):
        value = _read(root, name).strip().splitlines()
        if value:
            return value[0].strip().lstrip("v")
    return ""


def _python_version(root: Path) -> str:
    value = _read(root, ".python-version").strip().splitlines()
    if value:
        return value[0].strip()
    match = re.search(r'requires-python\s*=\s*"([^"]+)"', _read(root, "pyproject.toml"))
    if match:
        return match.group(1).strip()
    return ""


def _rust_channel(root: Path) -> str:
    match = re.search(r'channel\s*=\s*"([^"]+)"', _read(root, "rust-toolchain.toml"))
    return match.group(1).strip() if match else ""


def _go_version(root: Path) -> str:
    match = re.search(r"^go\s+(\S+)", _read(root, "go.mod"), re.MULTILINE)
    return match.group(1).strip() if match else ""


def _make_targets(root: Path) -> list[str]:
    text = _read(root, "Makefile")
    if not text:
        return []
    return re.findall(r"^([A-Za-z][A-Za-z0-9_-]*):(?!=)", text, re.MULTILINE)


def _stack(root: Path) -> list[dict]:
    out: list[dict] = []
    if (root / "package.json").is_file():
        out.append({"name": "Node", "version": _node_version(root)})
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        out.append({"name": "Python", "version": _python_version(root)})
    if (root / "Cargo.toml").is_file():
        out.append({"name": "Rust", "version": _rust_channel(root)})
    if (root / "go.mod").is_file():
        out.append({"name": "Go", "version": _go_version(root)})
    return out


def _node_runner(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "package-lock.json").is_file():
        return "npm"
    return "pnpm" if (root / "pnpm-workspace.yaml").is_file() else "npm"


def _commands(root: Path) -> list[str]:
    out: list[str] = []
    scripts = _package_json(root).get("scripts")
    if isinstance(scripts, dict):
        runner = _node_runner(root)
        for name in ("dev", "build", "test", "lint"):
            if name in scripts:
                out.append(f"{name}: `{runner} run {name}`")
    targets = _make_targets(root)
    for name in ("dev", "test", "build", "lint"):
        if name in targets:
            out.append(f"{name}: `make {name}`")
    if (root / "uv.lock").is_file() and (root / "pyproject.toml").is_file():
        out.append("python: `uv run pytest`" if (root / "tests").is_dir() else "python: `uv sync`")
    elif (root / "pyproject.toml").is_file() and (root / "tests").is_dir():
        out.append("python: `pytest`")
    if (root / "Cargo.toml").is_file() and len(out) < MAX_COMMANDS:
        out.append("rust: `cargo test`")
    return out[:MAX_COMMANDS]


def _quirks(root: Path) -> list[str]:
    out: list[str] = []
    if (root / "pnpm-workspace.yaml").is_file():
        out.append("pnpm workspace (packages sit below the root)")
    if (root / "uv.lock").is_file():
        out.append("dependencies resolve with uv")
    python = _python_version(root)
    if python:
        out.append(f"Python pinned at {python}")
    node = _node_version(root)
    if node:
        out.append(f"Node pinned at {node}")
    if (root / ".venv").is_dir():
        out.append("a local .venv exists; call its interpreter by path")
    if (root / "Dockerfile").is_file():
        out.append("a container build exists")
    return out[:MAX_QUIRKS]


def discover(root: Path) -> dict:
    """The map for `root` as it stands right now (no cache read)."""
    root = root.expanduser().resolve()
    return {
        "version": MAP_VERSION,
        "root": str(root),
        "fingerprint": fingerprint(root),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stack": _stack(root),
        "commands": _commands(root),
        "quirks": _quirks(root),
    }


def map_path(root: Path | None = None) -> Path:
    return learning_dir(root) / MAP_NAME


def load_map(root: Path | None = None) -> dict | None:
    """The cached map, or None when it is missing, unreadable or stale."""
    root = (root or workspace_root()).expanduser().resolve()
    path = map_path(root)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(cached, dict) or cached.get("version") != MAP_VERSION:
        return None
    if cached.get("fingerprint") != fingerprint(root):
        return None
    return cached


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.part")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def ensure_map(root: Path | None = None) -> dict:
    """The current map, rebuilt and cached when the manifests moved."""
    root = (root or workspace_root()).expanduser().resolve()
    cached = load_map(root)
    if cached is not None:
        return cached
    fresh = discover(root)
    try:
        _write(map_path(root), json.dumps(fresh, indent=2, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("learning map not cached at %s: %s", map_path(root), exc)
    return fresh


def _join(parts: list[str], sep: str) -> str:
    return sep.join(part for part in parts if part)


def map_header(root: Path | None = None, *, max_chars: int = MAP_HEADER_MAX_CHARS) -> str | None:
    """The compact prompt block for the map, or None in an empty workspace."""
    root = (root or workspace_root()).expanduser().resolve()
    data = ensure_map(root)
    stack = [f"{entry['name']} {entry['version']}".strip() for entry in data.get("stack", [])]
    lines = ["## Project learning map (read from this workspace's manifests)"]
    if stack:
        lines.append("Stack: " + _join(stack, ", "))
    if data.get("commands"):
        lines.append("Verified commands: " + _join(list(data["commands"]), " | "))
        if any(cmd.startswith(("dev:", "start:")) for cmd in data["commands"]):
            # "Start my project" ends in a server, not in a tool round that
            # blocks: the run goes to the background and the URL is reported.
            lines.append(
                "To start it: run that start command with run_shell(run_in_background=true), "
                "then report the address it prints."
            )
    if data.get("quirks"):
        lines.append("Environment: " + _join(list(data["quirks"]), "; "))
    if len(lines) <= 1:
        return None
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text
