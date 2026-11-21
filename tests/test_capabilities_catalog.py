"""R3: the tool catalog answers with the gate's own verdict.

The catalog exists so a reader can see, per tool, whether a call runs without a
prompt. That answer lives in the chat gate, `chat_tool_requires_confirm`; a route
that derived its own — as this one did from `SAFE_TOOLS`, the CLI's auto-approve
set — was a second opinion the guard never gave. Measured 2026-11-18 on this
checkout: 20 of 83 registered tools were badged the wrong way.
"""

from __future__ import annotations

from core.tools.approval_rules import SAFE_TOOLS, chat_tool_always_runs_alone
from server.routes.capabilities import capabilities


def test_every_row_carries_the_gates_verdict() -> None:
    catalog = capabilities()["tools"]
    rows = catalog["tools"]
    assert rows, "the catalog lists no tool"
    for row in rows:
        assert row["safe"] is chat_tool_always_runs_alone(row["name"]), row["name"]


def test_tools_the_chat_gate_runs_alone_are_not_badged_as_asking() -> None:
    """The rows that were wrong while the badge read `SAFE_TOOLS`.

    `memory` writes the memory store and `skill_manage` writes skill files on the chat
    path without a prompt; the page told the reader both ask first. Each name is also
    asserted absent from `SAFE_TOOLS`, which is what the badge used to be.
    """
    rows = {row["name"]: row for row in capabilities()["tools"]["tools"]}
    for name in ("memory", "skill_manage", "clipboard_write", "manage_tasks", "agent_message"):
        assert name in rows, name
        assert rows[name]["safe"] is True, name
        assert name not in SAFE_TOOLS, name


def test_a_tool_that_asks_in_some_moment_is_never_claimed_to_run_alone() -> None:
    """`execute_code` asks whenever no cell carries it, a browser tool whenever the
    session holds credentials; a settings page cannot see either moment."""
    rows = {row["name"]: row for row in capabilities()["tools"]["tools"]}
    for name in ("execute_code", "browser_click"):
        assert name in rows, name
        assert rows[name]["safe"] is False, name


def test_the_catalog_is_complete_and_ordered() -> None:
    catalog = capabilities()["tools"]
    names = [row["name"] for row in catalog["tools"]]
    assert catalog["count"] == len(names)
    assert len(set(names)) == len(names)
    assert names == sorted(names)
    assert catalog["safe_count"] == sum(1 for row in catalog["tools"] if row["safe"])


def test_read_only_tools_are_marked_safe_and_writes_are_not() -> None:
    rows = {row["name"]: row for row in capabilities()["tools"]["tools"]}
    for known_safe in ("read_file", "list_directory", "file_search"):
        assert rows[known_safe]["safe"] is True, known_safe
    for mutating in ("write_file", "delete_file", "edit_file"):
        if mutating in rows:
            assert rows[mutating]["safe"] is False, mutating
