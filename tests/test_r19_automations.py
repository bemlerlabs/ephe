"""tests/test_r19_automations.py — R19: scheduler depth + auto-memory.

Given/When/Then, hermetic (job and result files in tmp_path).
"""
from __future__ import annotations

import asyncio
import json
import threading

import pytest
from fastapi.testclient import TestClient


# A ceiling, not a delay. The stream hands the heavy post-turn jobs to a worker thread
# after the response is delivered, so a test that wants to observe that hand-off needs a
# synchronisation point with the worker — a wait returns the moment the job signals. The
# suite already uses this ceiling to drain the same executors in its teardown fixture.
_POST_TURN_CEILING = 30.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    monkeypatch.setenv("EPHE_SCHEDULE_RESULTS", str(tmp_path / "schedule_results.json"))
    monkeypatch.setenv("EPHE_SCHEDULE_JOBS", str(tmp_path / "scheduled_jobs.json"))
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    from server.main import create_app

    return TestClient(create_app())


class TestScheduleRoutes:
    def test_given_presets_when_listed_then_five_curated_offline(self, client):
        r = client.get("/api/schedule/presets")
        assert r.status_code == 200
        presets = r.json()["presets"]
        assert len(presets) == 5
        assert all({"id", "title", "task", "cron"} <= set(p) for p in presets)
        assert all(len(p["cron"].split()) == 5 for p in presets)

    def test_given_job_created_when_listed_then_task_and_cron_fields(self, client):
        r = client.post("/api/schedule", json={"task": "Fasse die News zusammen", "cron": "0 8 * * *"})
        assert r.status_code == 200
        jobs = client.get("/api/schedule").json()["jobs"]
        assert len(jobs) == 1
        job = jobs[0]
        assert job["task"] == "Fasse die News zusammen", "THEN: Schema-Mismatch task/name gefixt"
        assert job["cron"] == "0 8 * * *"
        assert "next_run" in job, "THEN: Feld existiert (produktiv befüllt, Test-Scheduler ungestartet)"

    def test_given_job_when_run_now_then_result_in_history(self, client, monkeypatch):
        # A job that runs names a model, and since #94 the scheduler names none of its
        # own: this test's fake react_loop already invents an answer, so it invents the
        # tag too.
        monkeypatch.setenv("EPHE_MODEL", "r19-fake:1b")
        created = client.post("/api/schedule", json={"task": "kurzer task", "cron": "0 8 * * *"}).json()
        job_id = created["job_id"]

        async def _fake_react_loop(*args, **kwargs):
            return "Erledigt: News zusammengefasst."

        # _run_task imports react_loop LAZY from core.react → patch it there
        monkeypatch.setattr("core.react.react_loop", _fake_react_loop)
        r = client.post(f"/api/schedule/{job_id}/run")
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "Erledigt: News zusammengefasst."
        assert body["error"] is None
        results = client.get("/api/schedule/results").json()["results"]
        assert any(res["job_id"] == job_id for res in results)

    def test_given_unknown_job_when_run_now_then_404(self, client):
        assert client.post("/api/schedule/nope/run").status_code == 404

    def test_given_results_when_server_restarts_then_history_persists(self, client, tmp_path, monkeypatch):
        """The run history survives restarts (before: in-memory only)."""
        monkeypatch.setenv("EPHE_MODEL", "r19-fake:1b")
        import asyncio

        import core.scheduler as sched
        import core.react as react_mod

        created = client.post("/api/schedule", json={"task": "persist test", "cron": "0 8 * * *"}).json()

        async def _fake_react_loop(*args, **kwargs):
            return "persistiertes Ergebnis"

        monkeypatch.setattr(react_mod, "react_loop", _fake_react_loop)
        asyncio.run(sched.ephe_scheduler.run_job_now(created["job_id"]))
        assert sched._results_file().exists()

        # simulated restart: the registry is empty, the file loads the results back
        sched._job_results.clear()
        sched._load_results()
        assert any(e["result"] == "persistiertes Ergebnis" for e in sched._job_results)


_DEPLOY_QUESTION = "Wie deploye ich Ephe auf dem Mac mini am besten?"
_DEPLOY_ANSWER_PIECES = (
    "Die Deploy-Strategie für den Mac mini: Docker Compose mit Volume für Chroma, ",
    "healthcheck-gated Backend, lokal gebundener Port 8765 und reproduzierbarem Backup über das Volume. ",
    "So startet der Server nach Reboots selbstständig und bleibt offline-fähig.",
)


def _patch_stream_answer(monkeypatch, pieces):
    """Feed `pieces` through the stream's model path and hand back the patched module.

    R36: the skill fast-path was removed, so chat_with_tools is the only model path —
    and it reports progress through on_chunk the way a real LLM response does. The
    German text stays here: on the auto-memory path it is product content.
    """
    import server.routes.chat as chat_route

    async def _fake_chat(**kwargs):
        on_chunk = kwargs.get("on_chunk")
        for piece in pieces:
            if on_chunk:
                on_chunk(piece)
        return "".join(pieces)

    monkeypatch.setattr(chat_route, "chat_with_tools", _fake_chat)
    return chat_route


def _quiet_other_post_turn_jobs(monkeypatch, chat_route):
    """No-op the post-turn jobs that are not under test.

    Their order is pinned by the W16 suite; running them for real here would only add
    Chroma and observation work to the queue the hand-off test waits on."""
    monkeypatch.setattr(chat_route, "_observe_for_learning", lambda *a, **k: None)
    monkeypatch.setattr(chat_route, "_preserve_compaction", lambda *a, **k: None)


async def _read_stream_to_end(chat_route, session_id):
    """Drive the real chat_stream route and return everything its SSE generator emits."""
    req = chat_route.StreamRequest(message=_DEPLOY_QUESTION, session_id=session_id)
    resp = await chat_route.chat_stream(req)
    gen = resp.body_iterator
    chunks = []
    while True:
        try:
            # The guard only stops a generator that never ends; the hand-off itself is
            # synchronised by _await_post_turn_dispatch, so this number stops nothing.
            chunks.append(await asyncio.wait_for(gen.__anext__(), _POST_TURN_CEILING))
        except (asyncio.TimeoutError, StopAsyncIteration):
            break
    return "".join(chunks)


async def _await_post_turn_dispatch(chat_route):
    """Happens-before with the stream's fire-and-forget dispatch — no clock involved.

    Two joins, both on state the product itself keeps. The route holds its detached
    dispatch tasks in a module set (so the GC cannot drop them mid-flight), and awaiting
    that set waits for exactly the jobs this turn queued. The executor barrier after it
    rides the same single worker thread, so it also covers a job that was already queued
    by an earlier request. `sleep(...)` would have been the clock this suite rejected in
    the AgentPanel case: a ceiling on a wait is not a synchronisation point.
    """
    await asyncio.gather(*list(chat_route._POST_TURN_TASKS))
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(chat_route._POST_TURN_EXECUTOR, lambda: None)


class TestAutoMemory:
    def test_given_substantial_turn_when_stored_then_searchable_and_deduped(self, client, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        import core.auto_memory as auto_memory
        from core.memory import Memory

        mem = Memory(persist_dir=str(tmp_path / "chroma-auto"))
        monkeypatch.setattr(auto_memory, "_memory_factory", lambda: mem)
        from core.auto_memory import maybe_store_turn

        question = "Welche Docker-Compose-Strategie empfiehlst du für Ephe auf dem Mac mini?"
        answer = (
            "Für den Mac mini empfehle ich Docker Compose mit einem Volume für Chroma und "
            "einem healthcheck-gated Backend-Service. Das Deployment bleibt reproduzierbar, "
            "Backups laufen über das Volume, und der Server startet nach Reboots selbstständig. "
            "Port 8765 bleibt lokal gebunden."
        )
        first = maybe_store_turn(question, answer)
        assert first["stored"] is True, first
        second = maybe_store_turn(question, answer)
        assert second == {"stored": False, "reason": "duplicate"}, "THEN: Embedding-Dedupe verhindert Doppel"

    def test_given_disabled_toggle_when_stored_then_honest_skip(self, client, monkeypatch):
        monkeypatch.setenv("EPHE_MEMORY_ENABLED", "0")
        from core.auto_memory import maybe_store_turn

        result = maybe_store_turn("Was empfiehlst du für das Backup-Layout?", "x" * 200)
        assert result == {"stored": False, "reason": "disabled"}

    def test_given_artifact_answer_when_stored_then_skipped(self, client):
        from core.auto_memory import maybe_store_turn

        result = maybe_store_turn(
            "Erstelle eine Excel-Tabelle für das Budget",
            "## Excel-Tabelle erstellt\nXLSX_FILE:/tmp/x.xlsx\nDie Datei liegt in ~/Downloads und lässt sich öffnen. " * 2,
        )
        assert result == {"stored": False, "reason": "artifact"}, "THEN: Artefakte gehören in die R17-Bibliothek"

    @pytest.mark.asyncio
    async def test_given_stream_turn_when_done_then_auto_memory_fires(self, monkeypatch):
        """The REAL stream hands the finished turn to Auto-Memory at the done point.

        The hand-off is asserted through the post-turn queue and never through a read right
        after the response: the stream dispatches the heavy jobs to a worker thread and
        closes without waiting for them, so the old shape of this test — post, then read
        `calls` immediately — was a race it only won while the machine was fast. CI run
        37948780870 lost it on the slowest leg (ubuntu py3.13) with
        `assert 0 > 100` on this very line.

        It also cannot be driven through TestClient: that helper builds a fresh event
        loop per request and closes it when the response ends, which can destroy the
        detached dispatch task before it ever starts (measured — with the worker
        occupied, releasing the gate afterwards produced no hand-off at all). Reading
        the route's own generator inside the test's loop keeps the dispatch alive, the
        way the W16 hardening suite already does.
        """
        chat_route = _patch_stream_answer(monkeypatch, _DEPLOY_ANSWER_PIECES)
        calls = {}
        handed_over = threading.Event()

        def _fake_schedule(user_message, answer):
            calls["q"] = user_message
            calls["a"] = answer
            handed_over.set()

        monkeypatch.setattr(chat_route, "_schedule_auto_memory", _fake_schedule)
        _quiet_other_post_turn_jobs(monkeypatch, chat_route)

        body = await _read_stream_to_end(chat_route, "s-r19-fire")
        assert '"type": "done"' in body, body
        await _await_post_turn_dispatch(chat_route)

        assert handed_over.is_set(), (
            "THEN: the completed turn reaches Auto-Memory — the dispatched job never ran. "
            "Nothing sleeps here: the barrier returns as soon as the worker is empty."
        )
        assert len(calls.get("a", "")) > 100, "THEN: turn end hands Q and A to Auto-Memory"
        assert calls.get("q") == _DEPLOY_QUESTION, calls

    @pytest.mark.asyncio
    async def test_given_stream_turn_when_auto_memory_is_gated_then_the_answer_left_first(
        self, monkeypatch
    ):
        """
        GIVEN Auto-Memory blocked on a gate that only this test opens
        WHEN the stream generator has produced everything it produces
        THEN the body already carries `done` while the hand-off has not happened, and the
             same job lands as soon as the gate opens.

        This is the clock-free form of the failure above: the gate makes the incomplete
        hand-off a certainty instead of a scheduling accident, so a test that read the
        result without a synchronisation point would fail here every single time. It also
        pins the direction of the order — the response first, the heavy jobs after —
        which is a deliberate product decision held by the W16 suite
        (test_stream_closes_before_post_turn_jobs_finish); if Auto-Memory ever moves onto
        the request path, this test says so out loud instead of silently passing.
        """
        chat_route = _patch_stream_answer(monkeypatch, _DEPLOY_ANSWER_PIECES)
        calls = {}
        handed_over = threading.Event()
        gate = threading.Event()

        def _gated_schedule(user_message, answer):
            gate.wait(_POST_TURN_CEILING)
            calls["q"] = user_message
            calls["a"] = answer
            handed_over.set()

        monkeypatch.setattr(chat_route, "_schedule_auto_memory", _gated_schedule)
        _quiet_other_post_turn_jobs(monkeypatch, chat_route)

        try:
            body = await _read_stream_to_end(chat_route, "s-r19-gate")
            assert '"type": "done"' in body, body
            assert not handed_over.is_set(), (
                "THEN: the answer is delivered before Auto-Memory runs — reading the "
                "hand-off without synchronising is the race itself"
            )
            assert calls == {}, calls
        finally:
            gate.set()

        await _await_post_turn_dispatch(chat_route)
        assert handed_over.is_set(), "THEN: the gated job ran once the gate opened"
        assert calls.get("a") == "".join(_DEPLOY_ANSWER_PIECES), calls


class TestMemoryExportImport:
    def test_given_entries_when_exported_then_json_roundtrip(self, client):
        client.post("/api/memory/store", json={"text": "Backup läuft mittwochs", "metadata": {"source": "manual"}})
        r = client.get("/api/memory/export")
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert any("Backup läuft mittwochs" in e["text"] for e in entries)

        # simulate importing into the same (emptied) collection: clear it first
        client.request("DELETE", "/api/memory")
        r2 = client.post("/api/memory/import", json={"entries": entries})
        assert r2.status_code == 201
        assert r2.json()["imported"] >= 1
        listed = client.get("/api/memory/list").json()
        assert any("Backup läuft mittwochs" in e["text"] for e in listed["entries"])
