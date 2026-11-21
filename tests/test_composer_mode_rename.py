# tests/test_composer_mode_rename.py
"""The rename must not change what any stored session may do.

`edit-auto` leaves the menu, but a session that stored it keeps the behaviour it
had: the edit family runs, everything else still asks. Widening a stored value
under a rename is a privilege change dressed as typography. The two guards that
carry that promise run the real approval gate, `server/routes/chat.py::_sandbox_confirm`,
so an edit to its branches reddens this file: the audit label one stored mode
emits, and the auto-approved set of every approval profile. The client half — the
stored value goes back to the wire unchanged — lives in
`app/src/store/chatStore.mode-race.test.ts`.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time as _t
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import engine_config
from core import security_config as SC
from server.routes.chat import _EDIT_TOOL_NAMES, _resolve_mode

PROFILES = ("strict", "session", "plan", "full")
# A cross-section the approval gate actually branches on: two edit-family tools
# and two tools that live outside the family.
SAMPLE_TOOLS = sorted(_EDIT_TOOL_NAMES) + ["run_shell", "web_search"]
# One payload per sampled tool. The dialog half of the gate reads it for the diff
# preview, and the path exists nowhere, so a probe cannot touch a real document.
# `SAMPLE_TOOLS` grows with the family by itself and this dictionary does not, so
# `test_the_sample_covers_the_edit_family` is what reddens a family member that
# arrives without a payload.
SAMPLE_ARGS = {
    "edit_file": {"path": "rename-guard.md", "old_string": "one", "new_string": "two"},
    "write_file": {"path": "rename-guard.md", "content": "two"},
    "run_shell": {"command": "ls"},
    "web_search": {"query": "composer mode"},
}


class GateCall(NamedTuple):
    """One run of the real gate: its answer, whether it opened a dialog, and the
    audit line of the auto branch that answered (`None` when a dialog did)."""

    approved: bool
    asked: bool
    auto: dict | None


@pytest.fixture(autouse=True)
def gate_with_its_own_store(tmp_path, monkeypatch):
    """The gate reads the approval profile through `engine_config.CONFIG_DIR`, so
    each test gets a store of its own and no session memo crosses a probe."""
    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path)
    import server.routes.chat as chat_routes

    chat_routes._active_sandbox_events.clear()
    SC._session_approved.clear()
    SC._session_shell_heads.clear()
    yield
    chat_routes._active_sandbox_events.clear()
    SC._session_approved.clear()
    SC._session_shell_heads.clear()


def _audit_lines() -> list[dict]:
    """The stored instrument itself: `audit_event` appends one JSON line per entry,
    and `tests/conftest.py` keeps that file inside the test's own tmp dir."""
    from core.audit_log import AUDIT_LOG_FILE

    if not AUDIT_LOG_FILE.exists():
        return []
    return [json.loads(line) for line in
            AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def _probe_gate(mode: str, profile: str, tool: str, *, autonomous: bool = False) -> GateCall:
    """Runs `chat_routes._sandbox_confirm` once the way a turn does: the profile on
    disk, the stored mode on the request, the real emit path. A dialog that opens is
    answered with a refusal, so the asked/did-not-ask difference stays the gate's own
    doing. The audit entry is read back from the log file the gate writes, which is
    where a consumer of these labels would read them.

    The driver shape is the one `tests/test_r2b_approval_ceiling.py` and
    `tests/test_approval_treadmill_r36.py` already use."""
    import server.routes.chat as chat_routes

    SC.save_security_config(approval_profile=profile)
    chat_routes._active_sandbox_events.clear()
    SC._session_approved.clear()
    SC._session_shell_heads.clear()
    frames: list[dict] = []
    logged_before = len(_audit_lines())
    request = SimpleNamespace(mode=mode, session_id="rename-guard", autonomous=autonomous)

    async def _go() -> bool:
        task = asyncio.create_task(chat_routes._sandbox_confirm(
            tool, SAMPLE_ARGS[tool], frames.append, lambda _raw: None, request))
        deadline = _t.time() + 2.0
        while _t.time() < deadline and not task.done():
            await asyncio.sleep(0.01)
            for entry in list(chat_routes._active_sandbox_events.values()):
                if entry is not None and not entry["event"].is_set():
                    entry["approved"] = False
                    entry["remember"] = False
                    entry["event"].set()
        return await asyncio.wait_for(task, timeout=2.0)

    approved = asyncio.run(_go())
    released = [line for line in _audit_lines()[logged_before:]
                if line.get("kind") == "approval" and line.get("decision") == "auto"]
    return GateCall(
        approved=bool(approved),
        asked=any(frame.get("type") == "sandbox_confirm" for frame in frames),
        auto=released[0] if released else None,
    )


def _run_matrix(mode: str, profile: str) -> dict[str, GateCall]:
    """Every sampled tool through the gate for one stored mode under one profile."""
    return {tool: _probe_gate(mode, profile, tool) for tool in SAMPLE_TOOLS}


def _released(calls: dict[str, GateCall]) -> set[str]:
    """The tools the gate answered out of one of its auto branches."""
    return {tool for tool, call in calls.items() if call.auto is not None}


def test_the_sample_covers_the_edit_family() -> None:
    """`SAMPLE_TOOLS` is derived from `_EDIT_TOOL_NAMES` and `SAMPLE_ARGS` is written
    by hand, so a third edit-family tool would reach the probe with no payload and
    the ceiling tests below would die on a `KeyError` that reports no behaviour. This
    names the gap in the sample."""
    unsampled = sorted(set(_EDIT_TOOL_NAMES) - set(SAMPLE_TOOLS))
    assert not unsampled, f"edit-family tools outside SAMPLE_TOOLS: {unsampled}"
    unheld = sorted(set(SAMPLE_TOOLS) - set(SAMPLE_ARGS))
    assert not unheld, f"sampled tools with no payload in SAMPLE_ARGS: {unheld}"


def test_stored_edit_auto_keeps_its_approval_ceiling_under_every_profile() -> None:
    """Per-profile equivalence, measured through the gate: for a stored `edit-auto`
    the auto-approved set is exactly the edit family — empty while the profile is
    `strict` — and `run_shell` and `web_search` reach the dialog in all four
    profiles. The hyphen wire value the client keeps sending and the underscore
    spelling the alias table was written for release the same set."""
    for profile in PROFILES:
        calls = _run_matrix("edit-auto", profile)
        expected = set() if profile == "strict" else set(_EDIT_TOOL_NAMES)
        assert _released(calls) == expected, profile
        assert _released(_run_matrix("edit_auto", profile)) == expected, profile
        for tool, call in calls.items():
            if tool in expected:
                assert call.approved and not call.asked, (profile, tool)
                assert call.auto["status"] == "edit_auto", (profile, tool)
            else:
                assert call.asked and not call.approved and call.auto is None, (profile, tool)


def test_rewriting_edit_auto_onto_a_tile_would_widen_the_ceiling() -> None:
    """The control on the same gate: had the load-time rewrite mapped the stored
    value onto the Operator tile, `run_shell` and `web_search` would join the
    auto-approved set under session, plan and full. `edit-auto` is therefore retired
    from the menu only, never from its wire value."""
    for profile in ("session", "plan", "full"):
        kept = _released(_run_matrix("edit-auto", profile))
        rewritten = _released(_run_matrix("operator", profile))
        assert kept < rewritten, profile
        assert rewritten == set(SAMPLE_TOOLS), profile


#: (stored mode, profile, tool, autonomous, the label the gate has to emit)
AUDIT_LABELS = (
    ("edit-auto", "session", "edit_file", False, "edit_auto"),
    ("edit_auto", "session", "write_file", False, "edit_auto"),
    ("full-access", "session", "run_shell", False, "full_access"),
    ("full_access", "session", "web_search", False, "full_access"),
    ("operator", "session", "edit_file", False, "full_access"),
    ("operator", "session", "run_shell", False, "full_access"),
    # The autonomous flag is the client's own reading of the Operator tile
    # (`app/src/components/dashboard/chat/model.ts::autonomous`), and it outranks
    # both mode branches, for a stored edit-auto included.
    ("operator", "full", "edit_file", True, "autonomous"),
    ("edit-auto", "full", "write_file", True, "autonomous"),
)


def test_audit_status_labels_stay_frozen_across_the_rename() -> None:
    """`server/routes/chat.py` says the audit `status=` vocabulary is left behind the
    rename on purpose, because log consumers read it. That sentence is convention
    until a test reads the label, and this reads the line the gate appends. The UI
    moved to Operator; the stored instrument stays where the consumers are."""
    for mode, profile, tool, autonomous, label in AUDIT_LABELS:
        call = _probe_gate(mode, profile, tool, autonomous=autonomous)
        assert call.auto is not None and not call.asked, (mode, tool, autonomous)
        entry = call.auto
        assert entry["status"] == label, (mode, tool, autonomous)
        assert entry["kind"] == "approval" and entry["decision"] == "auto", (mode, tool)
        assert entry["tool"] == tool, (mode, tool)


def test_strict_profile_fires_no_auto_branch_for_any_stored_mode() -> None:
    """The freeze above only speaks about a branch that fires. Under `strict` no
    stored mode fires one, and every probe lands in the dialog: the ceiling the
    labels sit under, pinned next to them.

    One probe per stored mode carries that property, because `mode_auto` conjoins
    every auto branch and an edit-family name is the tool all three of them can
    release: `SAMPLE_TOOLS[0]`. The four-tool sweep under `strict` for the kept value
    stays in the ceiling test above."""
    # A dialog costs the driver two poll passes, so the 8 modes by 4 tools grid was
    # 32 of them running against the 2.0 s ceiling for one property per mode.
    for mode in ("edit-auto", "operator", "full-access", "analyst", "architect",
                 "creator", "agent", ""):
        call = _probe_gate(mode, "strict", SAMPLE_TOOLS[0])
        assert call.asked and not call.approved and call.auto is None, mode


def test_new_vocabulary_resolves() -> None:
    assert _resolve_mode("analyst")["analyst"] is True
    assert _resolve_mode("architect")["architect"] is True
    assert _resolve_mode("operator")["operator"] is True
    assert _resolve_mode("creator")["creator"] is True


def test_legacy_names_keep_their_own_semantics() -> None:
    for legacy, canonical in (("ask", "analyst"), ("plan", "architect"),
                              ("full-access", "operator"), ("full_access", "operator")):
        flags = _resolve_mode(legacy)
        assert flags[canonical] is True, legacy
        assert flags["operator"] is (canonical == "operator"), legacy


def test_retired_edit_auto_does_not_become_operator() -> None:
    flags = _resolve_mode("edit-auto")
    assert flags["edit_family_compat"] is True
    assert flags["operator"] is False, "a retired mode must not gain autonomous reach"


def test_execution_gate_refuses_renamed_modes_like_their_legacy_names() -> None:
    """The W10 execution gate sees the raw published mode, so the refusal has to
    move with the vocabulary: analyst refuses like ask, architect like plan."""
    from core.tools import chat_gate
    from core.tools.session_ctx import reset_current_mode, set_current_mode

    def _refusal(mode: str):
        token = set_current_mode(mode)
        try:
            return chat_gate.mode_denial("edit_file")
        finally:
            reset_current_mode(token)

    for legacy, renamed in (("ask", "analyst"), ("plan", "architect")):
        assert str(_refusal(legacy)) == str(_refusal(renamed)), renamed
        assert _refusal(renamed) is not None, renamed


def test_guard_text_names_the_mode_the_user_chose() -> None:
    """The model-facing guard text must not name a mode the user can no longer select."""
    from core.persona import ANALYST_MODE_GUARD, ARCHITECT_MODE_GUARD

    assert "Ask mode" not in ANALYST_MODE_GUARD
    assert "Analyst" in ANALYST_MODE_GUARD
    assert "Plan mode" not in ARCHITECT_MODE_GUARD
    assert "Architect" in ARCHITECT_MODE_GUARD
