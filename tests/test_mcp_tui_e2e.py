"""P2-10: the product's own terminal initialises MCP servers at startup.

The whole MCP chain was reachable from the PWA server only; ``grep mcp ui/`` was
empty, so a server configured in mcp.json / EPHE_MCP_SERVERS never reached the
TUI or the CLI's in-process agent commands. These are the e2e proofs: a REAL
stdio MCP server (a real child process speaking JSON-RPC over stdin/stdout) is
configured, the TUI mounts / ``ephe code`` runs, and the server's tool shows up
in that process's registry — then answers a call.
"""
from __future__ import annotations

import argparse
import asyncio
import shlex
import sys
import time
from pathlib import Path

# A real MCP stdio server: newline-delimited JSON-RPC 2.0 on stdin/stdout.
# One tool "echo"; no SDK, no mock.
_SERVER_SOURCE = r'''
import json
import sys


def _reply(mid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        mid = msg.get("id")
        if mid is None:
            continue  # notification (e.g. notifications/initialized): no reply
        method = msg.get("method")
        if method == "initialize":
            _reply(mid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ephe-e2e-echo", "version": "1.0.0"},
            })
        elif method == "tools/list":
            _reply(mid, {"tools": [{
                "name": "echo",
                "description": "Echo the given text back.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }]})
        elif method == "tools/call":
            args = (msg.get("params") or {}).get("arguments") or {}
            _reply(mid, {
                "content": [{"type": "text", "text": f"echo:{args.get('text', '')}"}],
                "isError": False,
            })
        else:
            _reply(mid, {})


main()
'''


def _write_server(tmp_path: Path) -> Path:
    script = tmp_path / "e2e_echo_mcp.py"
    script.write_text(_SERVER_SOURCE, encoding="utf-8")
    return script


def _stdio_spec(script: Path) -> str:
    return "stdio:" + shlex.join([sys.executable, str(script)])


async def _wait_for(predicate, pilot, timeout: float = 15.0) -> bool:
    """Pumps the app's loop until the predicate holds or the budget is spent."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.1)
    return predicate()


def test_tui_startup_registers_mcp_tools(tmp_path, monkeypatch):
    """GIVEN a configured stdio MCP server
    WHEN the TUI mounts
    THEN its startup worker registered the server's tool in this process and the
    tool answers a real call."""
    import core.session as session_module
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    script = _write_server(tmp_path)
    monkeypatch.setenv("EPHE_MCP_SERVERS", _stdio_spec(script))

    import core.tools.mcp_client as mcp
    from core.tools.registry import get_tool_schemas
    from ui.app import EpheApp

    app = EpheApp(model="gemma4:12b", reset=False)

    async def run():
        async with app.run_test(size=(100, 30)) as pilot:
            ok = await _wait_for(lambda: "mcp_echo" in mcp.get_mcp_tools(), pilot)
            assert ok, f"the TUI startup never registered the MCP tool: {mcp.get_mcp_tools()}"
            names = {s.get("function", {}).get("name") for s in get_tool_schemas()}
            assert "mcp_echo" in names
            text, is_error = await mcp.call_registered_mcp_tool("mcp_echo", {"text": "ping"})
            assert is_error is False
            assert text == "echo:ping"

    asyncio.run(run())


def test_cli_code_startup_registers_mcp_tools(chosen_engine, tmp_path, monkeypatch):
    """GIVEN a configured stdio MCP server
    WHEN `ephe code` runs its agent (engine stubbed)
    THEN the CLI startup attached the server before the loop, so the tool is in
    the registry of the CLI process."""
    script = _write_server(tmp_path)
    monkeypatch.setenv("EPHE_MCP_SERVERS", _stdio_spec(script))

    import core.run_evidence as evidence
    monkeypatch.setattr(evidence, "active_worktree", lambda: str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()

    import core.react
    import core.tools.mcp_client as mcp
    import ephe_cli

    before = set(mcp._LIVE_CLIENTS)

    async def _fake_loop(**kwargs):
        return "done"

    monkeypatch.setattr(core.react, "react_loop", _fake_loop)

    rc = ephe_cli.cmd_code(argparse.Namespace(
        task=["echo", "through", "mcp"], model=None, verify=None, rep=0,
    ))

    assert rc == 0
    assert "mcp_echo" in mcp.get_mcp_tools()
    # The other half of the attach: the child belongs to the loop `cmd_code` opened,
    # so the run has to close it before that loop ends. A client left in the
    # register outlives the loop, and its `BaseSubprocessTransport` is collected
    # after the loop is closed — the unraisable `RuntimeError: Event loop is closed`
    # that failed the coverage leg with every test green.
    assert set(mcp._LIVE_CLIENTS) == before, (
        "ephe code ended its event loop with the MCP child still registered"
    )


def test_cli_run_closes_the_mcp_clients_on_its_own_loop(chosen_engine, monkeypatch, tmp_path):
    """GIVEN a CLI run that attached an MCP client
    WHEN `ephe code`'s loop ends
    THEN the client's `close()` ran in that loop and it left the register.

    Hermetic: the attached client is a spy, so the claim does not depend on an OS
    boundary being available to spawn a real stdio child. This is the regression
    guard for the teardown half of `_init_cli_mcp`."""
    import core.mcp_config
    import core.react
    import core.run_evidence
    import core.tools.mcp_client as mcp
    import ephe_cli

    closed: list[str] = []

    class _SpyClient:
        async def close(self) -> None:
            closed.append("closed")

    attached: list[bool] = []

    async def _attach():
        attached.append(True)
        mcp._LIVE_CLIENTS["spy:mcp"] = _SpyClient()
        return ["mcp_echo"]

    async def _fake_loop(**kwargs):
        return "done"

    monkeypatch.setattr(core.mcp_config, "init_mcp_from_config", _attach)
    monkeypatch.setattr(core.react, "react_loop", _fake_loop)
    monkeypatch.setattr(core.run_evidence, "active_worktree", lambda: str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()

    rc = ephe_cli.cmd_code(argparse.Namespace(
        task=["echo", "through", "mcp"], model=None, verify=None, rep=0,
    ))

    assert rc == 0
    assert attached == [True], "the run never attached the MCP client"
    assert closed == ["closed"], "the attached client was never closed"
    assert "spy:mcp" not in mcp._LIVE_CLIENTS


def test_cli_init_helper_is_fail_tolerant(monkeypatch):
    """GIVEN no configured servers
    WHEN the CLI startup helper runs
    THEN it returns an empty list instead of raising."""
    monkeypatch.delenv("EPHE_MCP_SERVERS", raising=False)
    import ephe_cli

    assert asyncio.run(ephe_cli._init_cli_mcp()) == []


def test_a_client_that_will_not_close_does_not_fail_a_finished_run(
    chosen_engine, monkeypatch, tmp_path
):
    """GIVEN a run whose MCP client refuses to close (its transport is already gone)
    WHEN `ephe code` finishes and tears the client down
    THEN the teardown error stays in the teardown: the answer the run produced is the
    run's result and the exit code is 0. A finished run that answered must not become
    a failed one because a child process would not say goodbye."""
    import core.mcp_config
    import core.react
    import core.run_evidence
    import core.tools.mcp_client as mcp
    import ephe_cli

    attempted: list[str] = []

    class _SullenClient:
        async def close(self) -> None:
            attempted.append("close")
            raise RuntimeError("transport already torn down")

    async def _attach():
        mcp._LIVE_CLIENTS["sullen:mcp"] = _SullenClient()
        return ["mcp_echo"]

    async def _fake_loop(**kwargs):
        return "answered anyway"

    monkeypatch.setattr(core.mcp_config, "init_mcp_from_config", _attach)
    monkeypatch.setattr(core.react, "react_loop", _fake_loop)
    monkeypatch.setattr(core.run_evidence, "active_worktree", lambda: str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()

    try:
        rc = ephe_cli.cmd_code(argparse.Namespace(
            task=["finish", "the", "run"], model=None, verify=None, rep=0,
        ))
        assert attempted == ["close"], "the teardown never tried to close the client"
        assert rc == 0, "a failed teardown turned a finished run into a failed one"
    finally:
        # A failed close stays in the register on purpose (it is retryable), so the
        # test has to take its spy back out or the next MCP test inherits it.
        mcp._LIVE_CLIENTS.pop("sullen:mcp", None)
