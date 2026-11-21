"""Start the workspace's own dev command and hand back a loopback URL.

The project declares how it runs, so Ephe reads `scripts.dev` instead of
guessing a framework. The port is chosen by binding :0 first, so a running
server never collides with another; a framework that accepts a port flag gets
the chosen one on the command line, everything else reads PORT from the env.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from core.engine_config import get_workspace_dir
from core.secret_broker import child_env

BIND_WAIT_S = 25.0
_RUNNING: dict[int, subprocess.Popen[bytes]] = {}


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _accepts_connections(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_bind(port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        if _accepts_connections(port):
            return True
        time.sleep(0.25)
    return False


def dev_command(root: Path, port: int) -> list[str] | None:
    """The command the project declares, with the chosen port asserted."""
    manifest = root / "package.json"
    if not manifest.is_file():
        return None
    try:
        scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError):
        return None
    script = scripts.get("dev")
    if not isinstance(script, str) or not script.strip():
        return None
    runner = "pnpm" if (root / "pnpm-lock.yaml").is_file() else "npm"
    head = [runner, "run", "dev"]
    if "next" in script:
        return [*head, "--", "-p", str(port), "-H", "127.0.0.1"]
    if "vite" in script or "astro" in script:
        return [*head, "--", "--port", str(port), "--host", "127.0.0.1"]
    return head


def start_workspace_dev_server(path: str = "", timeout_s: float = BIND_WAIT_S) -> dict[str, Any]:
    """Start the declared dev command in the background and wait until it listens."""
    root = Path(path).expanduser() if path.strip() else Path(get_workspace_dir())
    if not root.is_dir():
        return {"ok": False, "reason": "workspace_missing", "detail": f"no directory at {root}"}
    port = _free_loopback_port()
    command = dev_command(root, port)
    if command is None:
        return {
            "ok": False,
            "reason": "no_dev_script",
            "detail": "package.json declares no dev script",
        }
    env = {**child_env(), "PORT": str(port), "HOST": "127.0.0.1", "BROWSER": "none"}
    proc = subprocess.Popen(  # noqa: S603 — argv is the project's own script line
        command,
        cwd=str(root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    if not _wait_for_bind(port, time.monotonic() + timeout_s):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            proc.terminate()
        return {
            "ok": False,
            "reason": "no_bind",
            "detail": f"nothing listened on 127.0.0.1:{port} within {int(timeout_s)}s",
            "command": " ".join(command),
        }
    _RUNNING[port] = proc
    return {
        "ok": True,
        "url": f"http://127.0.0.1:{port}",
        "port": port,
        "pid": proc.pid,
        "command": " ".join(command),
    }


def stop_workspace_dev_server(port: int) -> dict[str, Any]:
    proc = _RUNNING.pop(port, None)
    if proc is None:
        return {"ok": False, "reason": "not_running", "detail": f"no server started on port {port}"}
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        proc.terminate()
    return {"ok": True, "port": port}
