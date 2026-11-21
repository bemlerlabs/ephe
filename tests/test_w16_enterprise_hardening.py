"""
◑ Ephe – W16 · Enterprise security & concurrency hardening · TDD
tests/test_w16_enterprise_hardening.py

RULE: tests BEFORE implementation. RED first, then GREEN.

Locks down the six W16 points:
1. P0: post-turn jobs (auto_memory/learning/rest-mirror/compaction) run in
   a dedicated worker thread — while Chroma is storing, the event loop answers
   API pings with < 5 ms (median) and never > 150 ms.
2. P0: workspace scoping in the vector store — COLLECTION_NAME + persist path
   are bound to the SHA256 hash of the active workspace; facts from
   workspace A are not findable in workspace B (+ legacy migration only
   in the server-default context).
3. P0: POST /api/shell requires `X-Requested-With: XMLHttpRequest` (CSRF guard
   against browser-form/cross-origin POSTs) and interpreter flags such as
   `python3 -c` / `node -e` / REPLs are blocked, unless explicitly sandboxed.
4. P1: backend route POST /api/git/apply (hunk stage/discard) with a path guard.
5. P1: BPE subword tokenizer (tiktoken, optional) in the budget path — without
   tiktoken the calibrated 4.2-CJK fallback stays transparently active.
6. P1: GoalRunner (core/goal_loop.py) — goal → tools → check command → re-turn
   on failure, until max_turns or success; CLI mode `ephe goal`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from server.main import create_app

# Helpers

SHELL_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def _ns_response(content: str = "", tool_calls: list | None = None):
    return types.SimpleNamespace(
        message=types.SimpleNamespace(content=content, tool_calls=tool_calls or [])
    )


def _events(raw_lines: list[str]) -> list[dict]:
    out = []
    for line in raw_lines:
        for part in line.split("\n\n"):
            if part.startswith("data: "):
                out.append(json.loads(part[len("data: "):]))
    return out


@pytest.fixture
def hermetic_config(tmp_path, monkeypatch):
    """W16: make the device root + workspace resolution hermetic per test.

    EPHE_CONFIG_DIR is call-time (config_root), CONFIG_DIR is import-time —
    set both. get_workspace_dir reads engine.json from the patched root.
    """
    import core.engine_config as ec

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path / "cfg")
    (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _persist_workspace(tmp_path, name: str) -> str:
    """Persists a workspace into the hermetic engine.json."""
    from core.engine_config import EngineChoice, LOCAL_OLLAMA, save_engine_config

    ws = tmp_path / name
    ws.mkdir(parents=True, exist_ok=True)
    save_engine_config(
        EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b", workspace_dir=str(ws))
    )
    return str(ws)


# T1 · P0: post-turn jobs take the load off the event loop


class TestPostTurnOffload:

    @pytest.mark.asyncio
    async def test_post_turn_jobs_run_in_dedicated_worker_thread(self, monkeypatch):
        """Given: the heavy post-turn jobs
        When: run_post_turn_jobs(...) has finished
        Then: all of them ran — in order, in the same dedicated worker thread
           (NOT in the event-loop thread), and WITHOUT the REST history mirror.

        The mirror left this chain on 2026-10-09: a turn the next request reads back
        cannot live in a fire-and-forget task that may be cancelled when the stream
        closes (tests/test_r33_rest_history.py::test_stream_turn_is_mirrored). It now
        runs on its own worker, awaited before the sentinel.
        """
        from server.routes import chat as chat_route

        ran: list[tuple[str, str]] = []
        main_thread = threading.main_thread()

        def _rec(name):
            def _fn(*a, **k):
                ran.append((name, threading.current_thread().name))
            return _fn

        monkeypatch.setattr(chat_route, "_schedule_auto_memory", _rec("memory"))
        monkeypatch.setattr(chat_route, "_observe_for_learning", _rec("learning"))
        monkeypatch.setattr(chat_route, "_persist_rest_turn", _rec("rest"))
        monkeypatch.setattr(chat_route, "_preserve_compaction", _rec("compaction"))

        await chat_route.run_post_turn_jobs("warum ist der himmel blau?", "Antwort " * 40, "s-w16", [])

        names = [n for n, _ in ran]
        assert names == ["memory", "learning", "compaction"], ran
        threads = [t for _, t in ran]
        assert len(set(threads)) == 1, "the jobs have to serialise in one worker"
        assert not threads[0].startswith("MainThread")
        assert threads[0].startswith("ephe-post-turn"), threads

    @pytest.mark.asyncio
    async def test_ping_latency_during_memory_store_median_below_5ms(self, monkeypatch):
        """Given: auto-memory storing runs (slow fake, 250 ms in the worker thread)
        When: 5 parallel /ping calls hit THE SAME loop while it is storing
        Then: median latency < 5 ms and every call < 150 ms (loop never blocked)"""
        from server.routes import chat as chat_route

        loop = asyncio.get_running_loop()
        started = threading.Event()

        def slow_store(user_message: str, answer: str) -> None:
            started.set()
            time.sleep(0.25)

        monkeypatch.setattr(chat_route, "_schedule_auto_memory", slow_store)
        monkeypatch.setattr(chat_route, "_observe_for_learning", lambda *a, **k: None)
        monkeypatch.setattr(chat_route, "_persist_rest_turn", lambda *a, **k: None)
        monkeypatch.setattr(chat_route, "_preserve_compaction", lambda *a, **k: None)

        app = FastAPI()

        @app.get("/ping")
        async def ping() -> dict:
            return {"pong": True}

        job = None
        try:
            job = asyncio.create_task(
                chat_route.run_post_turn_jobs("frage ueber async loops?", "Antwort " * 40, "s-w16", [])
            )
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set(), "Worker-Job hat nie angefangen"

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                latencies = []
                for _ in range(5):
                    t0 = time.perf_counter()
                    r = await client.get("/ping")
                    latencies.append(time.perf_counter() - t0)
                    assert r.status_code == 200
            assert sorted(latencies)[2] < 0.005, f"Median {sorted(latencies)[2]*1000:.1f} ms — Loop blockiert"
            assert max(latencies) < 0.150, f"Max {max(latencies)*1000:.1f} ms — Loop blockiert"
        finally:
            await job

    @pytest.mark.asyncio
    async def test_stream_closes_before_post_turn_jobs_finish(self, monkeypatch):
        """Given: the post-turn jobs take a while (the gate stays closed)
        When: the SSE stream is read past done + : post + sentinel
        Then: the generator ends IMMEDIATELY (fire-and-forget), without waiting for the jobs"""
        from server.routes import chat as chat_route

        calls: list[tuple] = []
        gate = asyncio.Event()

        async def slow_jobs(user_message, answer, session_id, history=None):
            calls.append((user_message, session_id))
            await gate.wait()

        monkeypatch.setattr(chat_route, "run_post_turn_jobs", slow_jobs)

        async def fake_ct(**kwargs):
            cb = kwargs.get("on_chunk")
            if cb is not None:
                cb("hallo")
            return "hallo"

        monkeypatch.setattr(chat_route, "chat_with_tools", fake_ct)

        req = chat_route.StreamRequest(message="test", session_id="s-w16")
        resp = await chat_route.chat_stream(req)
        gen = resp.body_iterator
        raw_all = ""
        for _ in range(60):
            try:
                raw_all += await asyncio.wait_for(gen.__anext__(), 2.0)
            except (asyncio.TimeoutError, StopAsyncIteration):
                break
        assert '"type": "done"' in raw_all
        assert ": post" in raw_all
        # Give the task a scheduling chance (fire-and-forget on the loop).
        await asyncio.sleep(0)
        assert calls, "Post-Turn-Jobs wurden nicht dispatcht"
        gate.set()

    @pytest.mark.asyncio
    async def test_rest_chat_dispatches_post_turn_jobs_once(self, monkeypatch):
        """Given: REST /api/chat with an answer
        When: chat() has run through
        Then: exactly ONE run_post_turn_jobs dispatch with the turn data (no duplicate)"""
        from server.routes import chat as chat_route

        calls: list[tuple] = []

        async def fake_jobs(user_message, answer, session_id, history=None):
            calls.append((user_message, answer, session_id))

        monkeypatch.setattr(chat_route, "run_post_turn_jobs", fake_jobs)

        async def fake_react(**kwargs):
            return "REST-Antwort"

        monkeypatch.setattr(chat_route, "react_loop", fake_react)

        req = chat_route.ChatRequest(message="frage fuer rest?", session_id="s-rest")
        resp = await chat_route.chat(req)
        assert resp.response == "REST-Antwort"
        assert len(calls) == 1
        assert calls[0][0] == "frage fuer rest?"
        assert calls[0][1] == "REST-Antwort"
        assert calls[0][2] == "s-rest"


# T2 · P0: workspace scoping in the vector store


@pytest.fixture
def hermetic_memory(hermetic_config, monkeypatch):
    """Pin Memory to the tmp root + workspace A; returns the (ws_a, ws_b) paths."""
    return hermetic_config


class TestWorkspaceScopedMemory:

    def test_scope_functions_bind_to_workspace_sha256(self, hermetic_memory, monkeypatch):
        """Given: workspace /ws-alpha
        When: the scope functions resolve
        Then: persist path chroma_db/<hash16>, collection ephe_memory_<hash16>,
           hash == SHA256(resolved workspace)[:16]"""
        import core.engine_config as ec
        from core.memory import workspace_collection_name, workspace_memory_dir

        ws = _persist_workspace(hermetic_memory, "ws-alpha")
        monkeypatch.setattr(ec, "get_workspace_dir", lambda: ws)

        h = hashlib.sha256(str(ws).encode("utf-8")).hexdigest()[:16]
        assert workspace_memory_dir().name == h
        assert workspace_collection_name() == f"ephe_memory_{h}"
        assert workspace_memory_dir().parent.name == "chroma_db"

    def test_engine_config_workspace_hash_helper(self, hermetic_memory, monkeypatch):
        """Given: two workspaces
        When: ec.workspace_hash(...) is computed
        Then: 16 hex characters, deterministic, different per folder"""
        import core.engine_config as ec

        h1 = ec.workspace_hash(str(hermetic_memory / "proj-a"))
        h2 = ec.workspace_hash(str(hermetic_memory / "proj-b"))
        assert re.fullmatch(r"[0-9a-f]{16}", h1)
        assert h1 == ec.workspace_hash(str(hermetic_memory / "proj-a"))
        assert h1 != h2

    def test_facts_from_workspace_a_not_findable_in_b(self, hermetic_memory, monkeypatch):
        """Given: a fact stored in workspace A
        When: memory is searched in workspace B
        Then: 0 hits, 0 entries — and A still finds it"""
        import core.engine_config as ec
        from core.memory import Memory

        ws_a = _persist_workspace(hermetic_memory, "proj-alpha")
        ws_b = _persist_workspace(hermetic_memory, "proj-beta")

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: ws_a)
        Memory.reset_scoped_instances()
        mem_a = Memory()
        mem_a.store("Das Deploy-Token für Projekt Alpha ist pineapple-42")
        assert mem_a.count() == 1

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: ws_b)
        Memory.reset_scoped_instances()
        mem_b = Memory()
        assert mem_b.count() == 0, "Workspace B darf keine Fakten aus A sehen"
        assert mem_b.search("Deploy-Token Projekt Alpha") == []

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: ws_a)
        Memory.reset_scoped_instances()
        mem_a2 = Memory()
        assert mem_a2.count() == 1
        hits = mem_a2.search("Deploy-Token Projekt Alpha")
        assert any("pineapple-42" in r["text"] for r in hits)

    def test_singleton_is_per_workspace_scope(self, hermetic_memory, monkeypatch):
        """Given: two Memory() calls per workspace
        When: instances + persist paths are compared
        Then: same workspace → same instance (process singleton), other
           workspace → other instance with another persist path"""
        import core.engine_config as ec
        from core.memory import Memory, workspace_memory_dir

        ws_a = _persist_workspace(hermetic_memory, "proj-alpha")
        ws_b = _persist_workspace(hermetic_memory, "proj-beta")

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: ws_a)
        Memory.reset_scoped_instances()
        assert Memory() is Memory()
        dir_a = str(workspace_memory_dir())

        monkeypatch.setattr(ec, "get_workspace_dir", lambda: ws_b)
        assert str(workspace_memory_dir()) != dir_a
        m_b1, m_b2 = Memory(), Memory()
        assert m_b1 is m_b2

    def test_legacy_single_bucket_is_offered_only_in_server_default_context(
        self, hermetic_memory, monkeypatch, caplog
    ):
        """Given: a retired store in the chroma_db root  # gate:legacy
        When: Memory() WITHOUT a workspace set (server default = cwd fallback)
        Then: the store is recognised and the one command that reads it is named, in
           writing — this build cannot read it in-process any more, and a user with
           data must not be stranded in silence;
           WITH a workspace set nothing is offered (no cross-workspace ambiguity)"""
        import logging

        import core.engine_config as ec
        from core.engine_config import EngineChoice, LOCAL_OLLAMA, save_engine_config
        from core.memory import Memory

        legacy_dir = hermetic_memory / "cfg" / "memory" / "chroma_db"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "chroma.sqlite3").write_bytes(b"retired")

        # Server-default context: no workspace persisted → cwd fallback
        save_engine_config(EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b"))
        monkeypatch.setattr(ec, "get_workspace_dir", ec.get_workspace_dir)
        Memory.reset_scoped_instances()
        with caplog.at_level(logging.INFO, logger="core.memory"):
            mem = Memory()
        assert mem.count() == 0, "the source is no longer read in-process"
        offered = [r.getMessage() for r in caplog.records
                   if "import_legacy_store" in r.getMessage()]
        assert offered, (
            "a retired store nobody can read has to be named, not silently left behind"
        )
        assert str(legacy_dir) in offered[0]

        # With a workspace: no offer → no ambiguity about whose facts those are
        _persist_workspace(hermetic_memory, "proj-gamma")
        Memory.reset_scoped_instances()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="core.memory"):
            mem_ws = Memory()
        assert mem_ws.count() == 0
        assert not [r for r in caplog.records if "import_legacy_store" in r.getMessage()]


# T3 · P0: shell route CSRF guard + interpreter hardening


class TestShellRouteHeaderGuard:

    @pytest.fixture
    def client(self):
        return TestClient(create_app())

    def test_missing_header_rejected_403(self, client):
        """Given: POST /api/shell without X-Requested-With
        When: the route is checked
        Then: 403 — browser forms/simple cross-origin POSTs do not get through"""
        r = client.post("/api/shell", json={"command": "echo hi"})
        assert r.status_code == 403
        assert "X-Requested-With" in r.text

    def test_wrong_header_value_rejected(self, client):
        r = client.post("/api/shell", json={"command": "echo hi"},
                        headers={"X-Requested-With": "form-data"})
        assert r.status_code == 403

    def test_correct_header_allows_whitelisted_command(self, client):
        r = client.post("/api/shell", json={"command": "echo w16-hallo", "approved": True}, headers=SHELL_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert "w16-hallo" in r.json()["output"]

    def test_rce_via_python_dash_c_rejected_at_route(self, client, monkeypatch):
        """Given: RCE attempt through the interpreter, sandbox OFF (security default)
        When: POST /api/shell (with a legitimate header)
        Then: ok=False, security message — no output from 'id'"""
        class _Cfg:
            sandbox_enabled = False

        monkeypatch.setattr("core.security_config.load_security_config", lambda: _Cfg())
        r = client.post(
            "/api/shell",
            json={"command": 'python3 -c "import os; os.system(\'id\')"', "approved": True},
            headers=SHELL_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "Security" in data["output"]
        assert "uid=" not in data["output"]


class TestInterpreterHardening:

    def test_python_dash_c_blocked(self):
        from core.tools.shell_tools import validate_shell_command

        assert validate_shell_command('python3 -c "import os; os.system(\'sh\')"') is not None
        assert validate_shell_command("python -c 'print(1)'") is not None

    def test_node_dash_e_blocked(self):
        from core.tools.shell_tools import validate_shell_command

        assert validate_shell_command('node -e "require(\'child_process\').exec(\'id\')"') is not None
        assert validate_shell_command('node --eval "1+1"') is not None

    def test_interactive_repls_blocked(self):
        from core.tools.shell_tools import validate_shell_command

        assert validate_shell_command("python -i") is not None
        assert validate_shell_command("python3") is not None, "bare python = REPL"
        assert validate_shell_command("node") is not None, "bare node = REPL"

    def test_short_flag_cluster_with_eval_letters_blocked(self):
        from core.tools.shell_tools import validate_shell_command

        assert validate_shell_command("python -ic 'print(1)'") is not None

    def test_legitimate_interpreter_usage_still_allowed(self):
        from core.tools.shell_tools import validate_shell_command

        assert validate_shell_command("python3 script.py") is None
        assert validate_shell_command("python3 -m pytest -q") is None
        assert validate_shell_command("python3 --version") is None
        assert validate_shell_command("python -V") is None
        assert validate_shell_command("node server.js") is None
        assert validate_shell_command("npm test") is None

    def test_sandboxed_execution_allows_eval_flags(self):
        """Given: sandbox explicitly on (the Seatbelt wrapper engages)
        When: validate with sandboxed=True
        Then: python -c is allowed — the wrapper is the hard boundary"""
        from core.tools.shell_tools import validate_shell_command

        assert validate_shell_command('python3 -c "print(1)"', sandboxed=True) is None

    @pytest.mark.asyncio
    async def test_run_shell_rejects_eval_without_sandbox(self, monkeypatch):
        """Given: sandbox off (security default)
        When: run_shell('python3 -c ...')
        Then: rejection, subprocess is never reached"""
        from core.tools import shell_tools

        class _Cfg:
            sandbox_enabled = False

        monkeypatch.setattr("core.security_config.load_security_config", lambda: _Cfg())
        monkeypatch.setattr(shell_tools, "subprocess", None, raising=False)  # never reached

        out = await shell_tools.run_shell('python3 -c "print(1)"')
        assert out.startswith("⚠")
        assert "Security" in out

    @pytest.mark.asyncio
    async def test_sandbox_enabled_unblocks_eval_and_wraps_command(self, monkeypatch):
        """Given: security.json sandbox_enabled=True (the wrapper engages for real)
        When: run_shell('python3 -c ...')
        Then: no rejection; subprocess runs with the sandbox wrapper chain"""
        from core.tools import shell_tools

        class _Cfg:
            sandbox_enabled = True

        monkeypatch.setattr("core.security_config.load_security_config", lambda: _Cfg())
        monkeypatch.setattr(
            "core.shell_sandbox.wrap_command",
            lambda cmd, ws: ["sandbox-exec", "-p", "PROFILE", "/bin/sh", "-c", cmd],
        )
        captured: dict = {}

        class _FakeProc:
            def __init__(self, args, **kwargs):
                captured["args"] = args
                self.pid = 4242
                self.returncode = 0

            def communicate(self, input=None, timeout=None):
                return "sandboxed-run", ""

        def fake_popen(args, **kwargs):
            return _FakeProc(args, **kwargs)

        import core.tools._shell_proc as _shell_proc
        monkeypatch.setattr(_shell_proc.subprocess, "Popen", fake_popen)

        out = await shell_tools.run_shell('python3 -c "print(1)"')
        assert out == "sandboxed-run"
        assert captured["args"][:1] == ["sandbox-exec"], "muss Wrapper-Kette sein, nicht shell=True-String"

    @pytest.mark.asyncio
    async def test_sandbox_enabled_but_wrap_failed_still_rejects_eval(self, monkeypatch):
        """Given: sandbox_enabled=True, BUT wrap_command returns None (platform case)
        When: run_shell('python3 -c ...')
        Then: still a rejection — 'sandboxed' has to be REAL, not merely configured"""
        from core.tools import shell_tools

        class _Cfg:
            sandbox_enabled = True

        monkeypatch.setattr("core.security_config.load_security_config", lambda: _Cfg())
        monkeypatch.setattr("core.shell_sandbox.wrap_command", lambda cmd, ws: None)

        called = {"run": False}

        class _FakeProc:
            def __init__(self, *a, **k):
                self.pid = 4242
                self.returncode = 0

            def communicate(self, input=None, timeout=None):
                return "", ""

        def fake_popen(*a, **k):
            called["run"] = True
            return _FakeProc()

        import core.tools._shell_proc as _shell_proc
        monkeypatch.setattr(_shell_proc.subprocess, "Popen", fake_popen)
        out = await shell_tools.run_shell('python3 -c "print(1)"')
        assert out.startswith("⚠")
        assert called["run"] is False


# T4 · P1: git/apply backend route (hunk stage/discard)


class TestGitApplyRoute:

    @pytest.fixture
    def repo(self, hermetic_config):
        """Git repo in the hermetic workspace with a 10-line file + 2-hunk diff."""
        from core.engine_config import EngineChoice, LOCAL_OLLAMA, save_engine_config

        ws = hermetic_config / "apply-proj"
        ws.mkdir(parents=True, exist_ok=True)
        save_engine_config(
            EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b", workspace_dir=str(ws))
        )
        f = ws / "app.py"
        f.write_text("\n".join(f"line {i}" for i in range(1, 11)) + "\n", encoding="utf-8")
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        def git(*a):
            subprocess.run(["git", *a], cwd=ws, check=True, capture_output=True, env=env)
        git("init", "-q")
        git("add", ".")
        git("commit", "-qm", "base")
        # Two edits with a large gap between them (lines 1 and 10) → two
        # separate hunks; at a smaller distance git merges the 3-line contexts.
        lines = f.read_text(encoding="utf-8").splitlines()
        lines[0] = "line 1 edited"
        lines[9] = "line 10 edited"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        diff = subprocess.run(["git", "diff", "--", "app.py"], cwd=ws, check=True,
                              capture_output=True, text=True).stdout
        # Reset the working copy — the patch is only applied through the route
        git("checkout", "--", "app.py")
        return {"ws": ws, "file": f, "diff": diff}

    @pytest.fixture
    def client(self):
        return TestClient(create_app())

    def _hunk(self, diff: str, index: int) -> str:
        """File header + the n-th hunk as a complete patch (DiffView semantics)."""
        lines = diff.splitlines()
        first_hunk = next(i for i, l in enumerate(lines) if l.startswith("@@"))
        preamble = lines[:first_hunk]
        hunks: list[list[str]] = []
        for line in lines[first_hunk:]:
            if line.startswith("@@"):
                hunks.append([line])
            else:
                hunks[-1].append(line)
        return "\n".join(preamble + hunks[index]) + "\n"

    def test_apply_staged_hunk_only_stages_that_hunk(self, repo, client):
        """Given: a 2-hunk diff
        When: POST /api/git/apply with hunk 0, staged=True
        Then: only the line-2 change in the index, working copy untouched"""
        r = client.post("/api/git/apply", json={"patch": self._hunk(repo["diff"], 0), "staged": True})
        assert r.status_code == 200, r.text
        cached = subprocess.run(["git", "diff", "--cached", "--", "app.py"], cwd=repo["ws"],
                                capture_output=True, text=True, check=True).stdout
        assert "line 1 edited" in cached
        assert "line 10 edited" not in cached
        worktree = repo["file"].read_text(encoding="utf-8")
        assert "line 1 edited" not in worktree, "--cached darf die Arbeitskopie nicht anfassen"

    def test_apply_reverse_discards_change(self, repo, client):
        """Given: a modified working copy
        When: POST /api/git/apply with reverse=True (discard)
        Then: the file is back in its base state"""
        f = repo["file"]
        lines = f.read_text(encoding="utf-8").splitlines()
        lines[1] = "line 2 edited"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        diff = subprocess.run(["git", "diff", "--", "app.py"], cwd=repo["ws"],
                              capture_output=True, text=True, check=True).stdout
        r = client.post("/api/git/apply", json={"patch": diff, "reverse": True})
        assert r.status_code == 200, r.text
        assert "line 2 edited" not in f.read_text(encoding="utf-8")

    def test_apply_rejects_paths_outside_workspace(self, repo, client):
        evil = (
            "diff --git a/../../evil.txt b/../../evil.txt\n"
            "--- a/../../evil.txt\n"
            "+++ b/../../evil.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-harmlos\n"
            "+pwned\n"
        )
        r = client.post("/api/git/apply", json={"patch": evil})
        assert r.status_code == 400
        r2 = client.post("/api/git/apply", json={"patch": "+++ /etc/hosts\n@@ -1,1 +1,1 @@\n-a\n+b"})
        assert r2.status_code == 400

    def test_apply_rejects_empty_patch(self, repo, client):
        r = client.post("/api/git/apply", json={"patch": "   "})
        assert r.status_code == 400


# T5 · P1: BPE subword tokenizer in the budget path


class _FakeEncoding:
    """Deterministic BPE stand-in: one token per 3 characters."""

    def encode(self, text: str) -> list[int]:
        return list(range(max(1, len(text)) // 3 + 1)) if text else []


class _FakeTiktoken(types.ModuleType):
    def get_encoding(self, name: str):
        assert name == "cl100k_base"
        return _FakeEncoding()


@pytest.fixture
def bpe_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", _FakeTiktoken("tiktoken"))
    from core import usage

    usage.reset_tokenizer_cache()
    yield
    usage.reset_tokenizer_cache()


@pytest.fixture
def bpe_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # import → ImportError
    from core import usage

    usage.reset_tokenizer_cache()
    yield
    usage.reset_tokenizer_cache()


class TestBpeTokenizer:

    def test_tiktoken_available_uses_bpe_count(self, bpe_available):
        from core import usage

        text = "def add(a, b):\n    return a + b\n"
        expected = len(_FakeEncoding().encode(text))
        assert usage.estimate_tokens(text) == expected
        assert usage.tokenizer_backend() == "tiktoken-bpe"
        # BPE counts code noticeably differently from the 4.2 heuristic (32 characters → 11 BPE tokens)
        assert expected == 11
        assert usage.estimate_tokens("") == 0

    def test_tiktoken_absent_falls_back_to_calibrated_42(self, bpe_absent):
        from core import usage

        assert usage.tokenizer_backend() == "calibrated-4.2"
        assert usage.estimate_tokens("hallo welt") == 3  # ceil(10/4.2)
        assert usage.estimate_tokens("你好世界") == 4  # CJK 1:1

    def test_build_usage_flags_bpe_as_measured(self, bpe_available):
        from core import usage

        u = usage.build_usage("prompt text", "answer text")
        assert u["usage_estimated"] is False, "BPE-Zählung ist kein Schätzer"

    def test_build_usage_without_bpe_stays_estimated(self, bpe_absent):
        from core import usage

        u = usage.build_usage("prompt text", "answer text")
        assert u["usage_estimated"] is True

    def test_provider_measured_counts_still_win(self, bpe_available):
        from core import usage

        u = usage.build_usage("p", "c", prompt_tokens=11, completion_tokens=7)
        assert u["prompt_tokens"] == 11 and u["completion_tokens"] == 7
        assert u["total_tokens"] == 18
        assert u["usage_estimated"] is False

    def test_budget_endpoint_reports_tokenizer_backend(self, bpe_available):
        """Given: tiktoken available
        When: GET /api/context/budget
        Then: tokenizer='tiktoken-bpe' and estimated_tokens == the BPE sum (not /4.2)"""
        from core import multi_session

        user_text = "def add(a, b):\n    return a + b\n"
        answer_text = "Here is the function you asked for. " * 3
        multi_session.save_messages("rest-w16-bpe", [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": answer_text},
        ])
        client = TestClient(create_app())
        r = client.get("/api/context/budget?session_id=w16-bpe")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["tokenizer"] == "tiktoken-bpe"
        assert data["counted_via"] == "rest_mirror"
        enc = _FakeEncoding()
        expected = len(enc.encode(user_text)) + len(enc.encode(answer_text))
        assert data["estimated_tokens"] == expected

    def test_budget_endpoint_reports_calibrated_fallback(self, bpe_absent):
        from core import multi_session
        from core.usage import estimate_tokens

        multi_session.save_messages("rest-w16-cal", [
            {"role": "user", "content": "x" * 84},  # 84/4.2 = 20 Tokens
        ])
        client = TestClient(create_app())
        data = client.get("/api/context/budget?session_id=w16-cal").json()
        assert data["tokenizer"] == "calibrated-4.2"
        assert data["estimated_tokens"] == estimate_tokens("x" * 84) == 20


# T6 · P1: GoalRunner (autonomous goal loop)


class TestGoalRunner:

    @pytest.fixture
    def goal_loop(self, monkeypatch):
        """core.chat.chat_with_tools + core.tools.registry.execute_tool are faked."""
        import core.chat as cc
        from core.tools import registry as reg

        state = {"chat_calls": [], "chat_responses": [], "check_outputs": [], "check_queue": []}

        async def fake_chat(**kwargs):
            state["chat_calls"].append(kwargs)
            return state["chat_responses"].pop(0)

        async def fake_exec(name, args, policy=None):
            assert name == "run_shell"
            state["check_outputs"].append(args["command"])
            return state["check_queue"].pop(0)

        monkeypatch.setattr(cc, "chat_with_tools", fake_chat)
        monkeypatch.setattr(reg, "execute_tool", fake_exec)
        return state

    @pytest.mark.asyncio
    async def test_success_on_first_turn(self, goal_loop):
        from core.goal_loop import GoalRunner

        goal_loop["chat_responses"] = ["Implementiert: fix in app.py"]
        goal_loop["check_queue"] = ["3 passed in 0.12s"]

        runner = GoalRunner(model="m", check_command="pytest -q")
        result = await runner.run("Mache den Test grün")

        assert result.success is True
        assert result.turns == 1
        assert result.answer == "Implementiert: fix in app.py"
        assert "3 passed" in result.check_output
        # The goal prompt reached the agent, the check ran through run_shell
        assert goal_loop["chat_calls"][0]["history"][-1]["content"] == "Mache den Test grün"
        assert goal_loop["check_outputs"] == ["pytest -q"]

    @pytest.mark.asyncio
    async def test_failure_triggers_return_with_error_output(self, goal_loop):
        """Given: the check fails in turn 1
        When: turn 2
        Then: the re-turn prompt contains the error output; the 2nd check passes"""
        from core.goal_loop import GoalRunner

        goal_loop["chat_responses"] = ["Erster Versuch", "Zweiter Versuch"]
        goal_loop["check_queue"] = [
            "1 failed\n[exit 1] AssertionError: boom",
            "3 passed in 0.10s",
        ]

        runner = GoalRunner(model="m", check_command="pytest -q")
        result = await runner.run("Ziel")

        assert result.success is True
        assert result.turns == 2
        second_prompt = goal_loop["chat_calls"][1]["history"][-1]["content"]
        assert "boom" in second_prompt, "Fehlerausgabe muss in den Re-Turn"
        assert "pytest -q" in second_prompt
        assert "Erster Versuch" in "".join(
            m["content"] for m in goal_loop["chat_calls"][1]["history"]
        )

    @pytest.mark.asyncio
    async def test_gives_up_after_max_turns(self, goal_loop):
        from core.goal_loop import GoalRunner

        goal_loop["chat_responses"] = ["versuch"] * 3
        goal_loop["check_queue"] = ["[exit 1] fail"] * 3

        runner = GoalRunner(model="m", check_command="pytest -q", max_turns=3)
        result = await runner.run("Ziel")

        assert result.success is False
        assert result.turns == 3
        assert "[exit 1]" in result.check_output

    @pytest.mark.asyncio
    async def test_security_rejection_counts_as_failed_check(self, goal_loop):
        from core.goal_loop import GoalRunner

        goal_loop["chat_responses"] = ["a"]
        goal_loop["check_queue"] = ["⚠️ Security: command part 'curl' is not in the whitelist"]

        result = await GoalRunner(model="m", check_command="curl example.com", max_turns=1).run("Ziel")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_events_emitted_for_ui(self, goal_loop):
        from core.goal_loop import GoalRunner

        goal_loop["chat_responses"] = ["done"]
        goal_loop["check_queue"] = ["ok"]
        seen: list[str] = []
        runner = GoalRunner(model="m", check_command="true", on_event=lambda kind, **k: seen.append(kind))
        await runner.run("Ziel")
        # goal_start first: the goal, the check command and the budget are the loop's
        # own state, and the panel that shows "the goal" reads them there (P6 B3).
        assert seen == ["goal_start", "goal_turn", "goal_check"]

    def test_cli_goal_subcommand_wired(self, monkeypatch, capsys, chosen_engine):
        """Given: CLI arguments `goal "..." --check ...`
        When: cmd_goal runs (GoalRunner faked)
        Then: the runner gets goal/check/max_turns, the exit code follows the success"""
        import ephe_cli

        created: dict = {}

        class FakeRunner:
            def __init__(self, *, model, check_command, max_turns=10, **kw):
                created.update(model=model, check_command=check_command, max_turns=max_turns)

            async def run(self, goal):
                created["goal"] = goal
                from core.goal_loop import GoalResult
                return GoalResult(goal=goal, success=True, turns=1, check_output="ok", answer="fertig")

        monkeypatch.setattr(ephe_cli, "GoalRunner", FakeRunner)
        rc = ephe_cli.cmd_goal(types.SimpleNamespace(
            goal_task=["mache", "tests", "gruen"], check="pytest -q",
            model="gemma4:12b", max_turns=7,
        ))
        assert rc == 0
        assert created["goal"] == "mache tests gruen"
        assert created["check_command"] == "pytest -q"
        assert created["max_turns"] == 7
        out = capsys.readouterr().out
        assert "GOAL OK" in out

    def test_cli_goal_parser_has_check_flag(self):
        import ephe_cli

        parser = ephe_cli.build_parser()
        ns = parser.parse_args(["goal", "fix it", "--check", "pytest -q"])
        assert ns.check == "pytest -q"
        assert " ".join(ns.goal_task) == "fix it"
