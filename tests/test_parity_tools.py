"""Parity harness for the parity harness tools (wave 2).

Covers execute_code (stateful kernel), todo_list (session ledger) and
process_manage (background process control) against the registry:
schema presence, classification, and the real execution behaviour.
"""
from __future__ import annotations

import asyncio

import pytest

from core.tools import execute_tool, get_tool_schemas, TOOL_MAP
from core.tools.approval import classify_tool


def _schema_names() -> set[str]:
    return {e.get("function", {}).get("name") for e in get_tool_schemas()}


@pytest.mark.parametrize("name", ["todo_list", "process_manage"])
def test_parity_tool_registered_and_classified(name):
    assert name in TOOL_MAP
    assert name in _schema_names()
    assert classify_tool(name).category == "SAFE"


def test_execute_code_registered_and_classified_contained(monkeypatch):
    """W3-15: ``execute_code`` is SAFE only while the cell carries the run.

    With a guest on disk the cell is the runtime, so the run is contained and
    auto-approved. The uncontained half is pinned in
    ``tests/test_cell_default_approval_gate.py``.
    """
    from core import cpython_cell

    assert "execute_code" in TOOL_MAP
    assert "execute_code" in _schema_names()
    monkeypatch.delenv(cpython_cell.ENV_EXEC, raising=False)
    monkeypatch.setattr(cpython_cell, "guest_installed", lambda: True)
    cls = classify_tool("execute_code")
    assert cls.category == "SAFE"
    assert cls.is_mutating is False and cls.auto_approve_by_default is True


def test_execute_code_is_stateful(no_cell_guest):
    """The state survives the single call — in the cell as well as in the kernel.

    Wave E1: the result carries a receipt line with runtime/caps ahead of the
    output, which is why the value is searched for here instead of comparing lines.
    `no_cell_guest` pins the runtime these parity cases assert; see its docstring.
    """
    asyncio.run(execute_tool("execute_code", {"code": "p_a=7", "reset": True}))
    out = asyncio.run(execute_tool("execute_code", {"code": "print(p_a*6)"}))
    assert "42" in out and "runtime=" in out


def test_execute_code_surfaces_errors(no_cell_guest):
    assert "NameError" in asyncio.run(
        execute_tool("execute_code", {"code": "print(nope)", "reset": True})
    )
    assert "ZeroDivisionError" in asyncio.run(
        execute_tool("execute_code", {"code": "1/0", "reset": True})
    )
    assert "SyntaxError" in asyncio.run(
        execute_tool("execute_code", {"code": "def f(:", "reset": True})
    )


def test_execute_code_reset_clears_namespace(no_cell_guest):
    asyncio.run(execute_tool("execute_code", {"code": "p_b=1", "reset": True}))
    out = asyncio.run(execute_tool("execute_code", {"code": "print(p_b)", "reset": True}))
    assert "NameError" in out


def test_execute_code_keeps_partial_stdout_on_error(no_cell_guest):
    out = asyncio.run(
        execute_tool("execute_code", {"code": "print('before')\n1/0", "reset": True})
    )
    assert "before" in out and "ZeroDivisionError" in out


def test_todo_list_lifecycle():
    set_out = asyncio.run(
        execute_tool("todo_list", {"action": "set", "items": "Alpha\nBeta;Gamma"})
    )
    assert "0/3" in set_out and "Gamma" in set_out
    upd = asyncio.run(
        execute_tool("todo_list", {"action": "update", "id": 2, "status": "in_progress"})
    )
    assert "[>]" in upd
    assert "outside" in asyncio.run(
        execute_tool("todo_list", {"action": "update", "id": 9, "status": "completed"})
    )


def test_todo_list_enum_validation_blocks_bad_values():
    # P1-9 schema validation: enum violations are caught before the function.
    out = asyncio.run(execute_tool("todo_list", {"action": "nope"}))
    # P1-2: enum "nope" repaired deterministically -> [todo_list] prefix (not [TOOL-ERROR])
    assert out.startswith("[todo_list]") or out.startswith("[TOOL-ERROR]")


def test_process_manage_unknown_id():
    out = asyncio.run(
        execute_tool("process_manage", {"action": "poll", "task_id": "bgX"})
    )
    assert "no process" in out


def test_process_manage_background_roundtrip():
    async def _run():
        tid = await execute_tool(
            "run_shell", {"command": "echo parity-bg", "run_in_background": True}
        )
        assert tid.startswith("bg")
        waited = await execute_tool(
            "process_manage", {"action": "wait", "task_id": tid, "timeout_s": 5}
        )
        assert "parity-bg" in waited and "done" in waited
    asyncio.run(_run())


# Wave 3: Progressive Tool Discovery

def test_discovery_reduces_base_array():
    from core.chat import _tools_for_messages

    full = {e["function"]["name"] for e in get_tool_schemas()}
    visible = {e["function"]["name"] for e in _tools_for_messages([{"role": "user", "content": "hi"}])}
    assert len(visible) < len(full)
    assert "tool_search" in visible and "tool_call" in visible
    assert "create_pdf" not in visible


def test_discovery_whitelist_bypasses_deferral():
    from core.chat import _tools_for_messages

    allowed = ["create_pdf", "read_file"]
    visible = {e["function"]["name"] for e in _tools_for_messages([{"role": "user", "content": "hi"}], allowed)}
    # P0-1: declared tools + the three meta tools (progressive disclosure applies even
    # with an active skill) + the read primitives a whitelist may not take away
    # (owner decision 2026-10-10). Deferred non-meta tools stay outside.
    assert visible == {
        "create_pdf", "read_file", "list_directory", "file_search",
        "tool_search", "tool_describe", "tool_call",
    }
    assert "create_xlsx" not in visible  # deferred, not meta


def test_whitelist_empty_stays_empty():
    """P0-2: ask_mode passes [] → deliberately NO tool dialog (not even meta tools)."""
    from core.chat import _tools_for_messages

    visible = {e["function"]["name"] for e in _tools_for_messages([{"role": "user", "content": "hi"}], [])}
    assert visible == set()


def test_whitelist_gets_meta_tools_injected():
    """P0-1: every non-empty whitelist gets the discovery meta tools."""
    from core.chat import _tools_for_messages
    from core.tools.discovery import META_TOOL_NAMES

    visible = {e["function"]["name"] for e in _tools_for_messages(
        [{"role": "user", "content": "hi"}], ["read_file"])}
    assert META_TOOL_NAMES <= visible
    assert "read_file" in visible


def test_tool_search_finds_deferred():
    out = asyncio.run(execute_tool("tool_search", {"query": "pdf"}))
    assert "create_pdf" in out


def test_tool_describe_returns_schema():
    out = asyncio.run(execute_tool("tool_describe", {"name": "create_pdf"}))
    assert "create_pdf" in out and "parameters" in out


def test_tool_call_executes_deferred_tool():
    out = asyncio.run(execute_tool("tool_call", {"name": "get_datetime", "arguments": "{}"}))
    assert "September" in out or "2026" in out


def test_tool_call_bad_json():
    out = asyncio.run(execute_tool("tool_call", {"name": "get_datetime", "arguments": "notjson"}))
    assert out.startswith("[tool_call]")


# Wave 4: stateful agent tools (memory 2-tier + skill_manage)

def test_memory_add_and_list():
    out = asyncio.run(execute_tool("memory", {
        "action": "add", "target": "memory",
        "content": "parity-fact-xyz 42",
    }))
    assert "stored" in out
    listing = asyncio.run(execute_tool("memory", {"action": "list", "target": "memory"}))
    assert "parity-fact-xyz" in listing


def test_memory_remove():
    asyncio.run(execute_tool("memory", {
        "action": "add", "target": "memory", "content": "parity-tmp-999",
    }))
    out = asyncio.run(execute_tool("memory", {
        "action": "remove", "target": "memory", "old_text": "parity-tmp-999",
    }))
    assert "removed 1 entries" in out


def test_memory_bad_action():
    # Enum validation (P1-9) catches unknown action/target before the function.
    r = asyncio.run(execute_tool("memory", {"action": "nope", "target": "memory"}))
    assert "ERROR" in r or r.startswith("[memory]")
    r2 = asyncio.run(execute_tool("memory", {"action": "add", "target": "nope"}))
    assert "ERROR" in r2 or r2.startswith("[memory]")
    # Valid enum value, but a required field is missing → internal [memory] prefix.
    assert "[memory]" in asyncio.run(execute_tool("memory", {"action": "add", "target": "memory", "content": ""}))


def test_skill_manage_list_and_show():
    listing = asyncio.run(execute_tool("skill_manage", {"action": "list"}))
    assert "coding-agent" in listing
    show = asyncio.run(execute_tool("skill_manage", {"action": "show", "name": "coding-agent"}))
    assert "coding-agent" in show and "Trigger" in show


def test_skill_manage_create_and_delete():
    created = asyncio.run(execute_tool("skill_manage", {
        "action": "create", "name": "parity-skill-tmp",
        "trigger": "parity trigger", "description": "parity skill",
        "tools": "read_file, run_shell", "system_prompt": "Du bist ein Paritaets-Skill.",
    }))
    assert "saved" in created
    listing = asyncio.run(execute_tool("skill_manage", {"action": "list"}))
    assert "parity-skill-tmp" in listing
    deleted = asyncio.run(execute_tool("skill_manage", {"action": "delete", "name": "parity-skill-tmp"}))
    assert "deleted" in deleted


def test_skill_manage_create_missing_fields():
    out = asyncio.run(execute_tool("skill_manage", {"action": "create", "name": "x"}))
    assert out.startswith("[skill_manage]")


def test_skill_manage_create_with_test_block():
    """P2-2: create with test fields writes a ## Test block (parity gate)."""
    created = asyncio.run(execute_tool("skill_manage", {
        "action": "create", "name": "parity-tb-tmp",
        "trigger": "tb trigger", "description": "tb skill",
        "tools": "read_file", "system_prompt": "TB-Skill.",
        "test_input": "tb input", "test_expect_tool": "read_file",
        "test_expect_contains": "tb",
    }))
    assert "saved" in created
    show = asyncio.run(execute_tool("skill_manage", {"action": "show", "name": "parity-tb-tmp"}))
    assert "TB-Skill." in show
    asyncio.run(execute_tool("skill_manage", {"action": "delete", "name": "parity-tb-tmp"}))


def test_memory_ceiling_enforced():
    """P2-1: the collection stays <= MEMORY_TIER_CEILING."""
    from core.tools.state_tools import MEMORY_TIER_CEILING, _enforce_memory_ceiling
    from core.memory import Memory
    mem = Memory()
    _enforce_memory_ceiling(mem)
    assert mem.count() <= MEMORY_TIER_CEILING


# browser_exec: built-in browser as a one-namespace Python tool

def test_browser_exec_registered_and_classified():
    """browser_exec is in the map, the schema and CORE_TOOLS (always active)."""
    from core.tools.discovery import CORE_TOOLS
    assert "browser_exec" in TOOL_MAP
    assert "browser_exec" in _schema_names()
    assert "browser_exec" in CORE_TOOLS


def test_browser_exec_keeps_one_namespace_per_session():
    """The per-session kernel is the claim, and it needs no browser to prove.

    `core/tools/browser_tools.py::browser_exec` caches one namespace per session
    (`_BROWSER_KERNELS`), so a name defined in one block is readable in the next block of the
    same session and absent in another session. Neither half is a Chromium fact: the helpers are
    closures over a session loop and only launch when a helper is called, so this runs on every
    leg. Make the kernel per call and the `SEEN` line comes back a NameError; make it global and
    the `ABSENT` line comes back False.
    """
    asyncio.run(execute_tool("browser_exec", {"code": "kept = 'shared-kernel'", "session": "parity-shared"}))
    same = asyncio.run(
        execute_tool("browser_exec", {"code": "print('SEEN', kept)", "session": "parity-shared"})
    )
    assert "SEEN shared-kernel" in same, same
    other = asyncio.run(
        execute_tool("browser_exec", {"code": "print('ABSENT', 'kept' not in globals())", "session": "parity-isolated"})
    )
    assert "ABSENT True" in other, other


def _no_browser_for_this_playwright(out: str) -> bool:
    """Does this leg have the Chromium build its Playwright expects? Only the launcher knows,
    and the tool answers with `BROWSER_INSTALL_HINT` when the build is missing.

    Playwright ships as a Python dependency and the binary never does, so a leg without one is a
    supported state — and `core/browser.py::_launch_chromium` already answers it with
    `BROWSER_INSTALL_HINT`, a line `tests/test_j5_browser.py` pins.

    The guard this replaces globbed the ms-playwright cache and counted any `chromium-*`. On the
    macOS leg of run 38098961455 that glob matched four builds of other Playwright versions
    (`chromium-1208/1223/1228/1248`) while the installed 1.62.0 names `chromium-1234`, which is
    absent: the guard said installed, the launcher said otherwise, and only a host carrying
    foreign caches could show it. `.github/workflows/tests.yml:131` installs the binary on the
    py3.13 leg only, so this case is a one-leg proof and reports the missing build elsewhere.
    """
    from core.browser import BROWSER_INSTALL_HINT

    return BROWSER_INSTALL_HINT in out


def test_browser_exec_runs_helpers_in_one_namespace():
    """Several helper calls share the same namespace and the same loop, against a real page.

    The hermetic case above owns the namespace claim on every leg; what only a live Chromium can
    show is that the Playwright objects stay bound to one loop across calls — `page_info()` and
    `js()` both run against the tab `new_tab()` opened, in the same block.
    """
    code = (
        "# open a data: page, read title and text\n"
        "new_tab('data:text/html,<h1>Paritaet</h1>')\n"
        "wait_for_load()\n"
        "info = page_info()\n"
        "print('HAS_TEXT', bool(info.get('text')))\n"
        "print('JS_H1', js(\"document.querySelector('h1').textContent\"))\n"
    )
    out = asyncio.run(execute_tool("browser_exec", {"code": code, "session": "parity"}))
    if _no_browser_for_this_playwright(out):
        pytest.skip(
            "no Chromium build for this leg's Playwright; the workflow installs one on the "
            f"py3.13 leg only. The tool's own answer: {out.strip()}"
        )
    assert "HAS_TEXT True" in out
    assert "Paritaet" in out
