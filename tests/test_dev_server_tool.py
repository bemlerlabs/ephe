"""The workspace's own dev command, started on a loopback port."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tools.dev_server_tools import (  # noqa: E402
    dev_command,
    start_workspace_dev_server,
    stop_workspace_dev_server,
)
from core.tools.registry import TOOL_MAP  # noqa: E402


def test_a_directory_without_a_manifest_has_no_command(tmp_path: Path) -> None:
    assert dev_command(tmp_path, 4321) is None


def test_a_script_without_dev_is_refused(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}))
    assert dev_command(tmp_path, 4321) is None


def test_a_vite_script_receives_the_chosen_port(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "vite --host"}}))
    assert dev_command(tmp_path, 4321) == [
        "npm",
        "run",
        "dev",
        "--",
        "--port",
        "4321",
        "--host",
        "127.0.0.1",
    ]


def test_the_projects_own_command_answers_on_the_returned_url(tmp_path: Path) -> None:
    (tmp_path / "server.js").write_text(
        "require('http').createServer((q, s) => s.end('ok'))"
        ".listen(process.env.PORT, '127.0.0.1')"
    )
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "node server.js"}}))
    started = start_workspace_dev_server(str(tmp_path), timeout_s=20)
    try:
        assert started["ok"] is True, started
        with urllib.request.urlopen(started["url"], timeout=5) as response:
            assert response.read() == b"ok"
    finally:
        if started.get("ok"):
            assert stop_workspace_dev_server(started["port"])["ok"] is True


def test_the_tool_is_registered() -> None:
    assert "start_workspace_dev_server" in TOOL_MAP
