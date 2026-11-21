"""`ephe tool` must exit 1 when the tool itself reports a failure.

docs/CLI.md's exit-code table defines 1 as "runtime/repair error, including a
tool the approval policy blocks"; a tool that answered with an error (a refused
path, a missing argument, a handler failure) is that runtime error. The command
used to print the error text and return 0, so a script could not tell a failed
tool from a successful one.
"""

from __future__ import annotations

import argparse

import ephe_cli


async def _noop() -> None:
    return None


async def _noop_list() -> list[str]:
    return []


def _namespace() -> argparse.Namespace:
    return argparse.Namespace(
        tool_name="write_file",
        arg=[],
        dry_run=False,
        yes=True,
        no=False,
        json=False,
    )


def test_a_tool_error_result_exits_1(monkeypatch) -> None:
    async def fake_execute(name, arguments, policy=None):
        return "[tool-error 'write_file': access denied]"

    monkeypatch.setattr("core.tools.registry.execute_tool", fake_execute)
    monkeypatch.setattr(
        "core.tools.registry.get_tool_schemas",
        lambda: [{"function": {"name": "write_file"}}],
    )
    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _noop_list)
    monkeypatch.setattr(ephe_cli, "_close_cli_mcp", _noop)

    assert ephe_cli.cmd_tool(_namespace()) == 1


def test_a_successful_result_still_exits_0(monkeypatch) -> None:
    async def fake_execute(name, arguments, policy=None):
        return "written"

    monkeypatch.setattr("core.tools.registry.execute_tool", fake_execute)
    monkeypatch.setattr(
        "core.tools.registry.get_tool_schemas",
        lambda: [{"function": {"name": "write_file"}}],
    )
    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _noop_list)
    monkeypatch.setattr(ephe_cli, "_close_cli_mcp", _noop)

    assert ephe_cli.cmd_tool(_namespace()) == 0
