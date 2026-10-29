from __future__ import annotations

import asyncio
import threading

import pytest

from core import cpython_cell as cell


@pytest.fixture
def verified_guest(monkeypatch, tmp_path):
    monkeypatch.setenv("EPHE_CELL_WORK_ROOT", str(tmp_path))
    monkeypatch.setattr(cell, "guest_state", lambda: {"entry_ok": True, "tree_ok": True})
    monkeypatch.setattr(cell, "_async_locks", {})


@pytest.mark.parametrize("cancel_count", [0, 1, 2])
@pytest.mark.parametrize("worker_fails", [False, True])
def test_reset_cannot_erase_a_running_cells_workspace(
    verified_guest, monkeypatch, cancel_count, worker_fails,
):
    async def scenario():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = threading.Event()
        marker = cell.work_dir("shared") / "active.txt"

        def execute(code, session_id, **limits):
            if code == "first":
                marker.write_text("owned by first", encoding="utf-8")
                loop.call_soon_threadsafe(started.set)
                if not release.wait(10):
                    raise TimeoutError("test worker was not released")
                assert marker.read_text(encoding="utf-8") == "owned by first"
                if worker_fails:
                    raise RuntimeError("worker failed")
            return {"status": "OK", "stdout": code}

        monkeypatch.setattr(cell, "_run_sync", execute)
        first = asyncio.create_task(cell.run_python("first", "shared"))
        tasks = [first]
        try:
            await asyncio.wait_for(started.wait(), 5)
            for _ in range(cancel_count):
                first.cancel()
                checkpoint = asyncio.Event()
                loop.call_soon(checkpoint.set)
                await checkpoint.wait()
            attempted = asyncio.Event()

            async def next_run():
                attempted.set()
                return await cell.run_python("second", "shared", reset=True)

            second = asyncio.create_task(next_run())
            tasks.append(second)
            await attempted.wait()
            assert marker.exists(), "reset erased files while the prior worker was running"
            assert not second.done(), "the next run overlapped the prior worker"
            release.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if cancel_count:
                assert isinstance(results[0], asyncio.CancelledError)
            elif worker_fails:
                assert isinstance(results[0], RuntimeError)
            else:
                assert results[0]["stdout"] == "first"
            assert results[1] == {"status": "OK", "stdout": "second"}
            assert not marker.exists(), "the queued reset was never performed"
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scenario())


def test_cancelled_waiter_does_not_reset_the_active_workspace(verified_guest):
    async def scenario():
        marker = cell.work_dir("shared") / "active.txt"
        marker.write_text("keep", encoding="utf-8")
        attempted = asyncio.Event()

        async def waiting_run():
            attempted.set()
            return await cell.run_python("never execute", "shared", reset=True)

        async with cell._async_lock_for("shared"):
            waiter = asyncio.create_task(waiting_run())
            try:
                await attempted.wait()
                waiter.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await waiter
                assert marker.read_text(encoding="utf-8") == "keep"
            finally:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)

    asyncio.run(scenario())


def test_task_wide_cancellation_keeps_the_worker_lease(verified_guest, monkeypatch):
    async def scenario():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = threading.Event()
        marker = cell.work_dir("shared") / "active.txt"
        marker.write_text("keep", encoding="utf-8")

        def execute(code, session_id, **limits):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(10):
                raise TimeoutError("test worker was not released")
            return {"stdout": "done"}

        monkeypatch.setattr(cell, "_run_sync", execute)
        first = asyncio.create_task(cell.run_python("first", "shared"))
        tasks = [first]
        try:
            await asyncio.wait_for(started.wait(), 5)
            for task in asyncio.all_tasks() - {asyncio.current_task()}:
                task.cancel()
            attempted = asyncio.Event()

            async def next_run():
                attempted.set()
                return await cell.run_python("second", "shared", reset=True)

            second = asyncio.create_task(next_run())
            tasks.append(second)
            await attempted.wait()
            checkpoint = asyncio.Event()
            loop.call_soon(checkpoint.set)
            await checkpoint.wait()
            assert marker.exists(), "task-wide cancellation released the active workspace"
            assert not first.done(), "cancellation completed before the executor returned"
        finally:
            release.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
        assert isinstance(results[0], asyncio.CancelledError)
        assert results[1] == {"stdout": "done"}

    asyncio.run(scenario())


def test_another_session_does_not_wait_for_a_busy_session(verified_guest, monkeypatch):
    async def scenario():
        monkeypatch.setattr(cell, "_run_sync", lambda code, session_id, **kw: {"stdout": code})
        async with cell._async_lock_for("busy"):
            report = await asyncio.wait_for(cell.run_python("other result", "other"), 5)
            assert report["stdout"] == "other result"

    asyncio.run(scenario())


def test_worker_preserves_the_callers_session_context(verified_guest, monkeypatch):
    from core.tools.session_ctx import get_current_session, set_current_session

    def execute(code, session_id, **limits):
        return {"session": get_current_session()}

    monkeypatch.setattr(cell, "_run_sync", execute)

    async def scenario():
        set_current_session("context-owner")
        report = await cell.run_python("context", "context-owner")
        assert report["session"] == "context-owner"

    asyncio.run(scenario())
