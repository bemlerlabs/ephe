"""A confined plugin worker must not reach the host's own listening sockets.

Measured on 2026-11-05, in the production rail and not in a fixture: a plugin tool child
opened a TCP connection to a loopback port the backend was listening on and read `200` from
`/api/health` and `/api/memory/list`. No token was offered, because the HTTP layer trusts a
loopback peer (`server/middleware.py`) and the Seatbelt profile the worker ran under carried
no network rule at all. The word "confined" then described the filesystem only, and any
installed plugin's tool code held the user's whole local API: write files, change settings,
start a turn with tools — with no plugin identity in the request, no permission family
checked, and no audit row connecting the call to the tool that made it.

What closes it is one rule per platform, asked for by the plugin rail alone: `(deny network*)`
on macOS, `--unshare-net` under bubblewrap. The MCP connector rail keeps its network on
purpose — a server there may legitimately be a client, and it is not this boundary's child.
Capabilities are meant to reach the host through a channel the host controls (task #23), so
the sanctioned path is added with an identity beside it; a socket the boundary happened to
forget is not a channel.

Two layers of proof here. The argv check is cheap and runs everywhere, so the intent is
pinned on a machine with no boundary; the child check is the real one and needs one.
"""
from __future__ import annotations

import json
import socket
import threading

from core import mcp_sandbox
from core.sandbox import supervisor
from core.sandbox.runner import run_plugin_tool
from core.tools.dynamic_registry import ToolDescriptor, fingerprint_for
from tests.support import capabilities


def _descriptor(name: str = "plugin_reachprobe_tick") -> ToolDescriptor:
    schema = {
        "name": name,
        "description": "reports whether it can reach a host listener",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
    return ToolDescriptor(
        name=name,
        plugin_id="reachprobe",
        schema=schema,
        transport="plugin",
        entry="handlers:run",
        tool_family="read",
        fingerprint=fingerprint_for(schema),
    )


CHILD = (
    "def run(arguments, state_dir):\n"
    "    import socket, json\n"
    "    try:\n"
    "        s = socket.create_connection(('127.0.0.1', arguments['port']), timeout=3)\n"
    "        s.sendall(b'CHILD-HELLO')\n"
    "        data = s.recv(64)\n"
    "        s.close()\n"
    "        return {'reached': True, 'reply': data.decode('utf-8', 'replace')}\n"
    "    except Exception as exc:\n"
    "        return {'reached': False, 'error': type(exc).__name__,\n"
    "                'errno': getattr(exc, 'errno', None)}\n"
)


def _listener() -> tuple[int, threading.Event, list[str]]:
    """One accepted connection, answered with a word the test looks for."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    reached = threading.Event()
    seen: list[str] = []

    def serve() -> None:
        server.settimeout(8.0)
        try:
            conn, _addr = server.accept()
        except OSError:
            server.close()
            return
        seen.append(conn.recv(64).decode("utf-8", "replace"))
        conn.sendall(b"HOST-REACHED")
        conn.close()
        reached.set()
        server.close()

    threading.Thread(target=serve, daemon=True).start()
    return port, reached, seen


def _child_home(tmp_path):
    root = tmp_path / "plugin"
    root.mkdir(exist_ok=True)
    (root / "handlers.py").write_text(CHILD, encoding="utf-8")
    return root


def test_the_plugin_rail_asks_for_the_network_deny_on_both_boundaries(tmp_path) -> None:
    """The argv is the policy, so it is checked without spawning anything.

    `confined_argv` is the function that decides what the OS sees. The builders are asked
    directly on this host, and the live answer is then checked in the shape it comes in:
    no boundary, a Seatbelt profile, or a bubblewrap argv. A later edit that drops the flag
    from the launcher fails here without a child having to start.
    """
    live = supervisor.confined_argv("/bin/echo", ["hi"], str(tmp_path))
    bwrap_home = str(tmp_path)

    profile = mcp_sandbox.build_profile(bwrap_home, "/bin/echo", deny_network=True)
    assert "(deny network*)" in profile
    # Without the flag, the connector rail's profile stays as it shipped: a server there is
    # allowed to be a network client, and this change must not reach into it.
    assert "(deny network*)" not in mcp_sandbox.build_profile(bwrap_home, "/bin/echo")

    argv = mcp_sandbox.build_bwrap(bwrap_home, "/bin/echo", deny_network=True)
    assert "--unshare-net" in argv
    assert "--unshare-net" not in mcp_sandbox.build_bwrap(bwrap_home, "/bin/echo")
    if live is None:
        # The product's own answer is the one this test is about: no builder, no spawn.
        assert mcp_sandbox.platform_boundary() == "unavailable"
    elif live[0] == "sandbox-exec":
        assert any("(deny network*)" in part for part in live)
    else:
        assert live[0] == "bwrap" and "--unshare-net" in live


def test_confined_argv_asks_for_the_network_deny_on_both_boundaries(tmp_path, monkeypatch):
    """Both boundaries are what `confined_argv` returns, on a machine that has one.

    Calling the builders with the flag set by hand stays green after the flag
    is removed from the launcher. Mocking `platform_boundary` is the check
    that fails on either drop. The snapshot and the security note have to
    name the same two rules, so a prose edit that drops the measurement fails
    beside the argv.
    """
    from pathlib import Path

    from core.sandbox.policy_truth import policy_snapshot

    home = str(tmp_path)

    monkeypatch.setattr(mcp_sandbox, "platform_boundary", lambda: "seatbelt")
    seatbelt = supervisor.confined_argv("/bin/echo", ["hi"], home)
    assert seatbelt is not None
    assert any("(deny network*)" in part for part in seatbelt)

    monkeypatch.setattr(mcp_sandbox, "platform_boundary", lambda: "bubblewrap")
    wrapped = supervisor.confined_argv("/bin/echo", ["hi"], home)
    assert wrapped is not None and "--unshare-net" in wrapped

    monkeypatch.setattr(mcp_sandbox, "platform_boundary", lambda: "unavailable")
    assert supervisor.confined_argv("/bin/echo", ["hi"], home) is None

    network = policy_snapshot()["ceilings"]["network"]
    assert network.startswith("enforced")
    assert "(deny network*)" in network and "--unshare-net" in network

    note = (Path(__file__).resolve().parents[1] / "docs" / "SECURITY_AND_PRIVACY.md").read_text(
        encoding="utf-8"
    )
    assert "read `200` from two API routes with no token" in note
    assert "(deny network*)" in note and "--unshare-net" in note
    assert "a local process with no Origin cannot spend that authority" in note


@capabilities.requires_boundary
def test_a_confined_child_cannot_answer_a_host_listener(tmp_path) -> None:
    """The reach itself, measured: the child is refused, and the host hears nothing."""
    port, reached, seen = _listener()
    result = run_plugin_tool(
        _descriptor(), {"port": port}, _child_home(tmp_path), timeout_seconds=20
    )

    if result.status == "refused":
        # Fail-closed before any process exists is the other honest answer.
        assert not reached.is_set(), "the host was reached although the run was refused"
        return

    assert result.status == "ok", f"{result.status}: {result.text[:200]}"
    report = json.loads(result.text)
    assert report["reached"] is False, report
    assert not reached.is_set(), f"the host accepted a connection from the child: {seen}"
