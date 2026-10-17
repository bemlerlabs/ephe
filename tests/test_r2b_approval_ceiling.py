"""R2-B: the strict profile is the ceiling over every mode's auto-approve path.

Finding (review pass 2026-10-05): `_sandbox_confirm` released approval BEFORE
`load_security_config()` had been read. In composer mode "full access" — the
default of fresh sessions (`DEFAULT_COMPOSER_MODE`) — every mutation went through
without the profile ever being consulted. The "strict — always ask" slider
on the privacy page therefore had no reader, and the same screen
claimed "defaults are conservative — mutations always ask".

Contract:
- strict: none of the mode auto-paths (autonomous, edit-auto, full-access)
  skips the question — every mutation goes into the dialog.
- session/plan: behavior unchanged, "full access" keeps running straight through.
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


def _mk_request(mode: str, *, autonomous: bool = False) -> SimpleNamespace:
    return SimpleNamespace(mode=mode, session_id="s1", autonomous=autonomous)


def _confirm(request, name: str = "run_shell", args: dict | None = None):
    """Drives _sandbox_confirm and counts the approval dialogs it produces."""
    import server.routes.chat as chat_routes

    events: list[dict] = []

    async def _go():
        task = asyncio.create_task(
            chat_routes._sandbox_confirm(
                name, args or {"command": "ls"}, events.append, lambda _raw: None, request
            )
        )
        answered = False
        deadline = _t.time() + 2.0
        while _t.time() < deadline and not answered:
            await asyncio.sleep(0.01)
            for entry in list(chat_routes._active_sandbox_events.values()):
                if entry and not entry["event"].is_set():
                    entry["approved"] = True
                    entry["remember"] = False
                    entry["event"].set()
                    answered = True
        return await task

    approved = asyncio.run(_go())
    dialogs = [e for e in events if e.get("type") == "sandbox_confirm"]
    return approved, dialogs


class TestStrengeProfileIstDieDecke:
    def test_strict_haelt_full_access_zurueck(self):
        """G: profile strict, composer mode full access · W: a mutation · T: one dialog, the approval comes from the user."""
        SC.save_security_config(approval_profile="strict")
        approved, dialogs = _confirm(_mk_request("full-access"))
        assert len(dialogs) == 1, "das strenge Profil darf keinen Modi-Auto-Pfad durchlassen"
        assert approved is True

    def test_strict_haelt_den_autonomous_Opt_in_zurueck(self):
        SC.save_security_config(approval_profile="strict")
        approved, dialogs = _confirm(_mk_request("agent", autonomous=True))
        assert len(dialogs) == 1
        assert approved is True

    def test_strict_haelt_die_Edit_Familie_zurueck(self):
        SC.save_security_config(approval_profile="strict")
        approved, dialogs = _confirm(_mk_request("edit-auto"), name="write_file", args={"path": "/tmp/x", "content": "x"})
        assert len(dialogs) == 1
        assert approved is True


class TestAndereProfileBehaltenIhrenPfad:
    def test_session_Profil_laesst_full_access_durch_wie_bisher(self):
        """With no ceiling nothing may run differently: no dialog, free at once."""
        SC.save_security_config(approval_profile="session")
        approved, dialogs = _confirm(_mk_request("full-access"))
        assert dialogs == []
        assert approved is True

    def test_plan_Profil_laesst_die_Edit_Familie_nicht_durch(self):
        """Only edit-auto runs the edit family automatically — plan is exempt from that."""
        SC.save_security_config(approval_profile="plan")
        approved, dialogs = _confirm(_mk_request("plan"), name="write_file", args={"path": "/tmp/y", "content": "y"})
        assert len(dialogs) == 1
        assert approved is True
