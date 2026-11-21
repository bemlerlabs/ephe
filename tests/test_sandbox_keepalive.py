"""
◑ Ephe – I6 fix P2 · TDD
tests/test_sandbox_keepalive.py

Finding: while the server waits for a sandbox approval no SSE bytes flow — the
frontend idle timeout (90s, app/src/lib/stream.ts) throws
"Zeitueberschreitung: keine Antwort der Engine" as a misleading stream  # language-gate: ignore (quoted frontend timeout string as it ships, app/src/lib/stream.ts:64)
error, although the agent is only waiting for the user to click.

Fix contract: the /stream route sends SSE comment lines ': keepalive' regularly
while it waits for the approval. Comments are invisible to every
SSE parser but they reset the reader's idle detection.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time as _t
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

#: Patience for the keeper's first comment — not a budget. The assertion below waits for the
#: mechanism itself (the comment the keeper puts on the route's queue), so a loaded runner
#: only waits longer; this ceiling is reached by a keeper that stopped emitting, which is the
#: path that ends in the red assertions.
KEEPALIVE_PATIENCE_S = 10.0

#: Grace for a keeper that has already commented, so a one-shot break (one comment, then the
#: loop ends) shows up as a finished task before the liveness read. A live keeper is parked
#: in its next wait and cannot finish inside this window, so the grace can only turn a loop
#: that ended into a red.
KEEPER_DEATH_GRACE_S = 0.3


@pytest.fixture
def client(tmp_path):
    import os
    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")

    from server.routes.memory import _get_memory
    _get_memory.cache_clear()

    from server.main import create_app
    return TestClient(create_app())


def _resolve_first_sandbox_event(
    module, approved: bool, timeout_s: float = 5.0, ignore: set[str] | None = None
) -> bool:
    """Simulates the frontend click: waits for the first sandbox event and resolves it.

    CRITICAL (full-suite hang 2026-09-08): the registry is module globals; tests
    that ran before us can leave ghost entries. 'ignore'
    holds the token snapshot from before the request — only a FRESH token gets
    resolved, never a ghost event (otherwise our own cb blocks on event.wait()).
    """
    deadline = _t.time() + timeout_s
    while _t.time() < deadline:
        for token in list(module._active_sandbox_events.keys()):
            if ignore is not None and token in ignore:
                continue
            entry = module._active_sandbox_events.get(token)
            if entry is not None:
                entry["approved"] = approved
                entry["event"].set()
                return True
        _t.sleep(0.05)
    return False


def _keeper_spy(captured: list) -> Callable[..., asyncio.Task]:
    """Captures the sandbox route's keepalive task through the call that starts it.

    `_keepalive()` is created inside the route and never handed out, so the module-level
    `asyncio.create_task` is the only handle on the running loop. The returned callable
    delegates to the real one, so every other creator in the process is untouched — only the
    task whose coroutine is named `_keepalive` lands in `captured`. `server/routes/chat.py`
    resolves that attribute at call time, which is what makes it the right seam.
    """
    real = asyncio.create_task

    def spy(coro, **kwargs):
        task = real(coro, **kwargs)
        if "keepalive" in getattr(coro, "__qualname__", ""):
            captured.append(task)
        return task

    return spy


def _comment_spy(emitted: list) -> Callable[..., None]:
    """Records every raw SSE comment the route queues, at the moment it is queued.

    The test client hands the response body over only once the stream has closed (measured: a
    10 s stream delivers every line with the same arrival stamp), so the wire cannot tell a
    reader that the keeper has already ticked. The queue is that same signal one step earlier
    and it is readable while the request runs. A `: keepalive` item can only come from the
    keeper: the idle heartbeat yields its comment straight into the generator, past the queue.
    """
    real_put = asyncio.Queue.put_nowait

    def spy(queue, item):
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "raw" and "keepalive" in str(item[1]):
            emitted.append(item[1])
        return real_put(queue, item)

    return spy


def _line_index(lines: list[str], needle: str) -> int:
    """Position of the first line carrying `needle`, or -1 when no line carries it."""
    return next((i for i, line in enumerate(lines) if needle in line), -1)


def _drain(client, body: dict) -> list[str]:
    lines: list[str] = []
    with client.stream("POST", "/api/chat/stream", json=body) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            lines.append(line.strip())
    return lines


class TestSandboxKeepalive:

    def test_keepalive_comments_flow_during_approval_wait_then_deny_drains(self, client):
        """G: the user holds the approval open until the keeper has spoken (interval 0.2s)
           W: the stream is read to done, then the Deny is resolved
           T: one ': keepalive' line between sandbox_confirm and done, and the loop still
              running at that moment — both are mechanism facts, neither a clock count."""
        async def fake_chat_with_tools(**kwargs):
            cb = kwargs["on_tool_confirm"]
            kwargs["on_chunk"]("ich schreibe mal…")
            approved = await cb("write_file", {"path": "x.txt", "content": "y"})
            kwargs["on_chunk"](f"freigabe={approved}")
            return "fertig"

        import server.routes.chat as chat_routes

        body = {"message": "schreib x.txt", "session_id": "ka-1", "history": [], "autonomous": False}
        resolved: dict = {}
        obs: dict = {}
        emitted: list = []
        keepers: list = []
        before = set(chat_routes._active_sandbox_events.keys())

        def resolve_once_the_keeper_has_emitted() -> None:
            # The Deny, held back until the keeper has put a comment on the queue. The old
            # driver slept a fixed 0.8 s and the assertion counted what fitted into that
            # window: under an xdist worker the keeper's 0.2 s tick stretched past it and one
            # comment was all that fitted. Waiting on the mechanism makes that runner slower
            # instead of redder — only a keeper that never emits reaches the ceiling.
            deadline = _t.time() + KEEPALIVE_PATIENCE_S
            while _t.time() < deadline and not emitted:
                _t.sleep(0.01)
            # A one-shot loop ends right after its comment, a live one is parked in its next
            # wait. The grace lets a dead loop show itself; a live one cannot end inside it.
            _t.sleep(KEEPER_DEATH_GRACE_S)
            obs["comment_emitted"] = len(emitted) > 0
            obs["keeper_captured"] = len(keepers) > 0
            obs["keeper_alive"] = any(not task.done() for task in keepers)
            resolved["ok"] = _resolve_first_sandbox_event(chat_routes, approved=False, ignore=before)

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools), patch(
            "server.routes.chat.reflect", new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok"))
        ), patch.object(chat_routes, "SANDBOX_KEEPALIVE_SECONDS", 0.2), patch(
            "asyncio.create_task", new=_keeper_spy(keepers)
        ), patch.object(asyncio.Queue, "put_nowait", new=_comment_spy(emitted)):
            th = threading.Thread(target=resolve_once_the_keeper_has_emitted, daemon=True)
            th.start()
            lines = _drain(client, body)
            th.join(KEEPALIVE_PATIENCE_S + 5)

        text = "\n".join(lines)
        assert resolved.get("ok") is True, "sandbox-event wurde nicht aufgelöst"
        assert obs.get("comment_emitted") is True, (
            f"the keeper put no comment on the stream within {KEEPALIVE_PATIENCE_S:.0f}s — it "
            "stopped emitting"
        )
        marks = {kind: _line_index(lines, token) for kind, token in (
            ("confirm", "sandbox_confirm"),
            ("comment", ": keepalive"),
            ("done", '"type": "done"'),
        )}
        assert marks["comment"] >= 0, "the comment the keeper queued never reached the body"
        assert -1 < marks["confirm"] < marks["comment"] < marks["done"], (
            f"the keepalive comment is not inside the open approval window: {marks}"
        )
        assert obs.get("keeper_captured") is True, "the keepalive task was never created"
        assert obs.get("keeper_alive") is True, (
            "the keepalive loop was no longer running when the approval resolved — a loop that "
            "ends after its first comment leaves a long wait without bytes again"
        )
        assert '"type": "error"' not in text
        assert "freigabe=False" in text

    def test_no_keepalive_when_tool_completes_without_approval(self, client):
        """SAFE tools with no approval duty: not a single ': keepalive' (no sustained fire)."""
        async def fake_chat_with_tools(**kwargs):
            kwargs["on_chunk"]("nur lesen")
            return " gelesen"

        import server.routes.chat as chat_routes

        body = {"message": "lies was", "session_id": "ka-2", "history": [], "autonomous": False}
        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools), patch(
            "server.routes.chat.reflect", new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok"))
        ), patch.object(chat_routes, "SANDBOX_KEEPALIVE_SECONDS", 0.2):
            lines = _drain(client, body)

        assert not any(l == ": keepalive" for l in lines)
        assert '"type": "done"' in "\n".join(lines)

    def test_ghost_registry_entry_does_not_block_own_approval_resolution(self, client):
        """Full-suite hang regression (2026-09-08): a ghost entry left in the module
        registry by an earlier test must not steer the resolver to the wrong
        event — the own approval waiter still has to be
        resolved and the stream still has to run to done (no hang)."""
        import uuid

        async def fake_chat_with_tools(**kwargs):
            cb = kwargs["on_tool_confirm"]
            kwargs["on_chunk"]("ich schreibe mal…")
            approved = await cb("write_file", {"path": "x.txt", "content": "y"})
            kwargs["on_chunk"](f"freigabe={approved}")
            return "fertig"

        import server.routes.chat as chat_routes

        ghost_token = str(uuid.uuid4())
        ghost = {"event": __import__("asyncio").Event(), "approved": False}
        chat_routes._active_sandbox_events[ghost_token] = ghost
        try:
            body = {"message": "schreib x.txt", "session_id": "ka-3", "history": [], "autonomous": False}
            resolved: dict = {}
            before = set(chat_routes._active_sandbox_events.keys())

            def deny_soon() -> None:
                _t.sleep(0.5)
                resolved["ok"] = _resolve_first_sandbox_event(chat_routes, approved=False, ignore=before)

            with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools), patch(
                "server.routes.chat.reflect", new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok"))
            ), patch.object(chat_routes, "SANDBOX_KEEPALIVE_SECONDS", 0.2):
                th = threading.Thread(target=deny_soon, daemon=True)
                th.start()
                lines = _drain(client, body)
                th.join(6)

            assert resolved.get("ok") is True
            assert '"type": "done"' in "\n".join(lines)
            assert "freigabe=False" in "\n".join(lines)
            # The ghost entry was left untouched — only our own token
            # (not in 'before') got resolved; the ghost event stays untargeted.
            assert not ghost["event"].is_set()
        finally:
            chat_routes._active_sandbox_events.pop(ghost_token, None)

    def test_sandbox_confirm_event_carries_real_diff(self, client):
        """Wave B1: the sandbox_confirm event carries a real unified
        diff for edit_file as an optional `diff` field — the approval dialog shows
        the change with it, not the raw arguments."""

        async def fake_chat_with_tools(**kwargs):
            cb = kwargs["on_tool_confirm"]
            approved = await cb(
                "edit_file",
                {"path": "a.txt", "old_string": "x\n", "new_string": "y\n"},
            )
            kwargs["on_chunk"](f"freigabe={approved}")
            return "fertig"

        import server.routes.chat as chat_routes

        body = {"message": "aendere a.txt", "session_id": "ka-diff", "history": [], "autonomous": False}
        resolved: dict = {}
        before = set(chat_routes._active_sandbox_events.keys())

        def deny_soon() -> None:
            _t.sleep(0.3)
            resolved["ok"] = _resolve_first_sandbox_event(chat_routes, approved=False, ignore=before)

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools), patch(
            "server.routes.chat.reflect", new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok"))
        ), patch.object(chat_routes, "SANDBOX_KEEPALIVE_SECONDS", 0.2):
            th = threading.Thread(target=deny_soon, daemon=True)
            th.start()
            lines = _drain(client, body)
            th.join(6)

        confirm = next(json.loads(l[len("data:"):].strip()) for l in lines if '"sandbox_confirm"' in l)
        assert confirm["tool"] == "edit_file"
        diff = confirm.get("diff", "")
        assert "-x" in diff and "+y" in diff
        assert diff.startswith("---")
