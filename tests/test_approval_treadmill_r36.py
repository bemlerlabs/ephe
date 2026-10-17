"""R36 P1-UX: B-7 approval treadmill — a head memo per shell command + the full-access factor.

Finding (full audit 2026-09-18): in the 'session' profile the chat only remembered
tool TYPES; run_shell sits in NEVER_REMEMBER ⇒ every run_shell was asked again, even
identical command heads. The composer mode 'full_access' ('Full access', run-through)
had so far never fired an auto path.

Contract:
- session profile: approved+remember stores the segment HEADS of the command;
  identical heads then run dialog-free (audit 'session-approved').
- full_access mode: run-through, no dialog.
- strict profile: every request asked, unchanged.
"""
from __future__ import annotations

import asyncio
import time as _t
from types import SimpleNamespace

import pytest

from core import engine_config
from core import security_config as SC


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path)
    SC._session_approved.clear()
    SC._session_shell_heads.clear()
    yield
    SC._session_approved.clear()
    SC._session_shell_heads.clear()


def _mk_request(mode: str = "agent", sid: str = "s1") -> SimpleNamespace:
    return SimpleNamespace(mode=mode, session_id=sid, autonomous=False)


def _run_confirm(request, name, args, events, *, approved=True, remember=True):
    """Runs _sandbox_confirm and satisfies the approval event that is waiting."""
    import server.routes.chat as chat_routes

    async def _go():
        task = asyncio.create_task(
            chat_routes._sandbox_confirm(name, args, events.append, lambda _raw: None, request)
        )
        deadline = _t.time() + 2.0
        while _t.time() < deadline:
            await asyncio.sleep(0.01)
            for token, entry in list(chat_routes._active_sandbox_events.items()):
                if entry is not None and not entry["event"].is_set():
                    entry["approved"] = approved
                    entry["remember"] = remember
                    entry["event"].set()
        return await task

    return asyncio.run(_go())


class TestShellHeadMemo:
    def test_given_session_profile_when_same_head_then_second_call_without_dialog(self, tmp_path, monkeypatch):
        """G: profile session, 'git status' approved+remember
           W: a second run_shell with the same head 'git log'
           T: exactly one sandbox_confirm event, both True."""
        SC.save_security_config(approval_profile="session", path=tmp_path / "security.json")
        import server.routes.chat as chat_routes
        chat_routes._active_sandbox_events.clear()

        events: list[dict] = []
        req = _mk_request()
        first = _run_confirm(req, "run_shell", {"command": "git status --short"}, events)
        second = _run_confirm(req, "run_shell", {"command": "git log --oneline -5"}, events)
        dialogs = [e for e in events if e.get("type") == "sandbox_confirm"]

        assert first is True and second is True
        assert len(dialogs) == 1, f"zweiter Dialog trotz Kopf-Memo: {len(dialogs)}"
        assert dialogs[0]["rememberable"] is True

    def test_given_session_profile_when_different_head_then_new_dialog(self, tmp_path):
        """G: 'npx …' remembered
           W: 'npm test' (a different head)
           T: a second sandbox_confirm event; afterwards 'npx' is dialog-free again."""
        SC.save_security_config(approval_profile="session", path=tmp_path / "security.json")
        import server.routes.chat as chat_routes
        chat_routes._active_sandbox_events.clear()

        events: list[dict] = []
        req = _mk_request()
        _run_confirm(req, "run_shell", {"command": "npx -- vite --port 5173"}, events)
        _run_confirm(req, "run_shell", {"command": "npm test"}, events)
        dialogs = [e for e in events if e.get("type") == "sandbox_confirm"]
        assert len(dialogs) == 2
        # third call with the remembered head npx => no new dialog event
        third = _run_confirm(req, "run_shell", {"command": "npx -- tsc -b"}, events)
        assert third is True
        assert len([e for e in events if e.get("type") == "sandbox_confirm"]) == 2

    def test_given_approved_without_remember_then_next_call_asks_again(self, tmp_path):
        SC.save_security_config(approval_profile="session", path=tmp_path / "security.json")
        import server.routes.chat as chat_routes
        chat_routes._active_sandbox_events.clear()

        events: list[dict] = []
        req = _mk_request()
        first = _run_confirm(req, "run_shell", {"command": "git status"}, events, remember=False)
        second = _run_confirm(req, "run_shell", {"command": "git status"}, events, remember=False)
        assert first is True and second is True
        assert len([e for e in events if e.get("type") == "sandbox_confirm"]) == 2

    def test_given_denied_then_no_head_is_remembered(self, tmp_path):
        SC.save_security_config(approval_profile="session", path=tmp_path / "security.json")
        import server.routes.chat as chat_routes
        chat_routes._active_sandbox_events.clear()

        events: list[dict] = []
        req = _mk_request()
        first = _run_confirm(req, "run_shell", {"command": "git status"}, events, approved=False)
        second = _run_confirm(req, "run_shell", {"command": "git status"}, events)
        assert first is False
        assert len([e for e in events if e.get("type") == "sandbox_confirm"]) == 2

    def test_given_strict_profile_then_dialog_every_time_and_no_remember_checkbox(self, tmp_path):
        SC.save_security_config(approval_profile="strict", path=tmp_path / "security.json")
        import server.routes.chat as chat_routes
        chat_routes._active_sandbox_events.clear()

        events: list[dict] = []
        req = _mk_request()
        _run_confirm(req, "run_shell", {"command": "git status"}, events)
        _run_confirm(req, "run_shell", {"command": "git status"}, events)
        dialogs = [e for e in events if e.get("type") == "sandbox_confirm"]
        assert len(dialogs) == 2
        assert all(e["rememberable"] is False for e in dialogs)


class TestFullAccessMode:
    def test_given_full_access_mode_then_no_dialog_at_all(self, tmp_path):
        """'Full access' = run-through: no sandbox_confirm, still approved.

        The profile here is 'session', not 'strict': R2-B keeps the strict profile in
        as a ceiling over every mode auto path (tests/test_r2b_approval_ceiling.py).
        The line below used to be 'strict' — that froze exactly the contradiction the
        privacy page claimed to resolve.
        """
        SC.save_security_config(approval_profile="session", path=tmp_path / "security.json")
        import server.routes.chat as chat_routes
        chat_routes._active_sandbox_events.clear()

        events: list[dict] = []
        req = _mk_request(mode="full_access")
        first = _run_confirm(req, "run_shell", {"command": "git status"}, events)
        second = _run_confirm(req, "edit_file", {"path": "x.txt"}, events)
        assert first is True and second is True
        assert not [e for e in events if e.get("type") == "sandbox_confirm"]


class TestHeadExtraction:
    def test_given_multi_segment_command_then_heads_per_segment(self):
        import server.routes.chat as chat_routes
        heads = chat_routes._shell_segment_heads("git status --short && npx -- vite --port 5173")
        assert heads == ["git", "npx"]

    def test_given_unparseable_command_then_empty_heads(self):
        import server.routes.chat as chat_routes
        assert chat_routes._shell_segment_heads('echo "unbalanced') == []

    def test_given_empty_command_then_empty_heads(self):
        import server.routes.chat as chat_routes
        assert chat_routes._shell_segment_heads("") == []
