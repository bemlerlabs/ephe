"""P0-2: session isolation for the stateful tools (no context leaking).

Two interleaved sessions must see neither each other's kernel namespace
(execute_code) nor the ToDo ledger (todo_list). That is the proof
against the module-global single state of the previous version.
"""
from __future__ import annotations

import asyncio

from core.tools import execute_tool
from core.tools.session_ctx import set_current_session, get_current_session


def test_session_ctx_default_is_default():
    tok = set_current_session("")
    try:
        assert get_current_session() == "default"
    finally:
        from core.tools.session_ctx import _CURRENT_SESSION
        _CURRENT_SESSION.reset(tok)


def test_kernel_namespaces_are_isolated_between_sessions(no_cell_guest):
    """Session A sets p_iso; session B does not see it, A still does."""
    set_current_session("sess-A")
    asyncio.run(execute_tool("execute_code", {"code": "p_iso=11", "reset": True}))
    out_a = asyncio.run(execute_tool("execute_code", {"code": "print(p_iso)"}))
    assert "11" in out_a and "runtime=" in out_a

    set_current_session("sess-B")
    # B has a fresh namespace → p_iso is unknown (NameError).
    out_b = asyncio.run(execute_tool("execute_code", {"code": "print(p_iso)"}))
    assert "NameError" in out_b

    # Back to A: the value is still there (isolation, not an overwrite).
    set_current_session("sess-A")
    out_a2 = asyncio.run(execute_tool("execute_code", {"code": "print(p_iso)"})  )
    assert "11" in out_a2


def test_todo_ledgers_are_isolated_between_sessions():
    """'set' in B does not overwrite A's ledger."""
    set_current_session("led-A")
    asyncio.run(execute_tool("todo_list", {"action": "set", "items": "Alpha\nBeta"}))
    out_a = asyncio.run(execute_tool("todo_list", {"action": "list"}))
    assert "Alpha" in out_a and "Beta" in out_a

    set_current_session("led-B")
    out_b = asyncio.run(execute_tool("todo_list", {"action": "list"}))
    assert out_b == "Todo list: empty."  # B does not see A's entries

    asyncio.run(execute_tool("todo_list", {"action": "set", "items": "Gamma"}))
    out_b2 = asyncio.run(execute_tool("todo_list", {"action": "list"}))
    assert "Gamma" in out_b2 and "Alpha" not in out_b2

    # A stays unchanged.
    set_current_session("led-A")
    out_a2 = asyncio.run(execute_tool("todo_list", {"action": "list"}))
    assert "Alpha" in out_a2 and "Gamma" not in out_a2
