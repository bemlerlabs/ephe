"""The approval window closing is not a decision of the person.

Audit finding 40, server half. `_sandbox_confirm` opened a dialog, waited
`APPROVAL_TTL_SECONDS`, got nothing, and wrote two audit lines about it: one that
named the expiry and one that named a decision with `status="user"`. The second line
told the stored instrument that a person had refused a run nobody was ever asked
about. The expiry is the truth and it is the only line an unanswered gate leaves.

The client half — a card that stays answerable until the window closes and then reads
as expired — is `app/src/lib/sandboxGate.ts` with its specs.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import engine_config
from core import security_config as SC

ASKED_TOOL = "run_shell"
ASKED_ARGS = {"command": "ls"}


@pytest.fixture(autouse=True)
def gate_with_its_own_store(tmp_path, monkeypatch):
    """Strict profile in a store of its own, so the gate always opens a dialog and no
    session memo from another test answers it."""
    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path)
    import server.routes.chat as chat_routes

    SC.save_security_config(approval_profile="strict")
    chat_routes._active_sandbox_events.clear()
    chat_routes._expired_sandbox_tokens.clear()
    SC._session_approved.clear()
    SC._session_shell_heads.clear()
    yield
    chat_routes._active_sandbox_events.clear()
    chat_routes._expired_sandbox_tokens.clear()
    SC._session_approved.clear()
    SC._session_shell_heads.clear()


def _approval_lines() -> list[dict]:
    """The stored instrument itself: `audit_event` appends one JSON line per entry and
    `tests/conftest.py` keeps that file inside the test's own tmp dir."""
    from core.audit_log import AUDIT_LOG_FILE

    if not AUDIT_LOG_FILE.exists():
        return []
    return [
        json.loads(line)
        for line in AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_gate_unanswered(monkeypatch, *, ttl: float = 0.05) -> tuple[bool, list[dict]]:
    """One turn of the real gate with nobody at the other end of the stream."""
    import server.routes.chat as chat_routes

    monkeypatch.setattr(chat_routes, "APPROVAL_TTL_SECONDS", ttl)
    monkeypatch.setattr(chat_routes, "SANDBOX_KEEPALIVE_SECONDS", 10.0)
    chat_routes._active_sandbox_events.clear()
    frames: list[dict] = []
    # The turn shape the gate reads; a stand-in for `StreamRequest` is the point of
    # the seam, so the annotation stays with the reader rather than the parameter.
    request: Any = SimpleNamespace(mode="chat", session_id="expiry-audit", autonomous=False)

    approved = asyncio.run(
        chat_routes._sandbox_confirm(
            ASKED_TOOL, ASKED_ARGS, frames.append, lambda _raw: None, request
        )
    )
    return approved, frames


def test_an_unanswered_gate_leaves_one_line_and_it_is_an_expiry(monkeypatch):
    approved, frames = _run_gate_unanswered(monkeypatch)
    lines = [
        line
        for line in _approval_lines()
        if line.get("kind") == "approval" and line.get("tool") == ASKED_TOOL
    ]

    assert approved is False
    assert [frame.get("type") for frame in frames] == ["sandbox_confirm"]
    assert [line["status"] for line in lines] == ["awaiting-user", "expired"]
    # The line that claimed a person had answered is the defect; it has no status to
    # keep and no consumer to miss it.
    assert not any(line.get("status") == "user" for line in lines)
    assert not any(line.get("decision") == "approved" for line in lines)


def test_the_expiry_still_answers_410_for_its_token(monkeypatch):
    """The audit fix must not soften the server's own answer: the token of a closed
    window is refused, so a card that was still open cannot be answered afterwards."""
    from fastapi import HTTPException

    import server.routes.chat as chat_routes

    _run_gate_unanswered(monkeypatch)
    token = next(iter(chat_routes._expired_sandbox_tokens))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            chat_routes.approve_sandbox(
                chat_routes.ApproveRequest(token=token, approved=True)
            )
        )
    assert exc.value.status_code == 410
