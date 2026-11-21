"""A locally authored bundle in the shape Creator Mode installs.

The directory carries the v2 contract a test needs to see a bundle end to end: one
contributed tool whose file ships, one floating-window surface document, one slash
command. `mark_installed` then writes the two rows the installer leaves behind — the
`plugins.json` switch and the lifecycle record — so a fixture reaches the state the
product reaches, not a hand-written approximation of it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def manifest_for(
    name: str,
    *,
    version: str = "0.1.0",
    tool: str = "now",
    surface_title: str = "",
    commands: tuple[str, ...] = ("ping",),
) -> dict[str, Any]:
    return {
        "manifest_version": 2,
        "name": name,
        "version": version,
        "description": f"{name} test bundle",
        "publisher": {"name": "Test"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "tools": [
                {
                    "name": tool,
                    "entry": "tools/handlers.py:run",
                    "family": "read",
                    "description": f"Answer for {name}.",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            "ui": {
                "type": "floating-window",
                "entry": "ui/index.html",
                "title": surface_title or name,
            },
            "commands": [
                {"name": command, "description": f"Run {command}."}
                for command in commands
            ],
            "skills": [],
        },
    }


def write_bundle(
    root: Path,
    name: str,
    *,
    version: str = "0.1.0",
    tool: str = "now",
    surface_title: str = "",
    commands: tuple[str, ...] = ("ping",),
) -> Path:
    """Write one valid v2 bundle below `root` and return its directory."""
    directory = Path(root) / name
    (directory / "tools").mkdir(parents=True, exist_ok=True)
    (directory / "ui").mkdir(parents=True, exist_ok=True)
    (directory / "tools" / "handlers.py").write_text(
        "def run(arguments, state_dir):\n    return 'ok'\n", encoding="utf-8"
    )
    (directory / "ui" / "index.html").write_text(
        "<!doctype html><title>Surface</title>", encoding="utf-8"
    )
    (directory / "ephe-plugin.json").write_text(
        json.dumps(
            manifest_for(
                name,
                version=version,
                tool=tool,
                surface_title=surface_title,
                commands=commands,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    return directory


def mark_installed(name: str, *, enabled: bool = False) -> None:
    """Write the switch row and the lifecycle record an install leaves.

    The device folders come from `EPHE_CONFIG_DIR`, which the fixture sets before
    calling this; the registry name is read through `registry_path()` for the same
    reason the installer reads it.
    """
    from core import plugin_runtime
    from core.plugin_store import registry_path, set_enabled

    set_enabled(name, enabled, path=registry_path())
    plugin_runtime.invalidate_ownership_cache()
    plugin_runtime.lifecycle().set_enabled(
        name, enabled, actor="test", reason="fixture install"
    )
    plugin_runtime.invalidate_ownership_cache()
