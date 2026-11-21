"""`/project` in the chat route: the plan lookup and the command's own answers."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.routes import chat

PLAN = """\
# Plan

## Phase 1: one
- [ ] a
Gate: `test -f a`
"""


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path))
    return tmp_path


def _plan(tmp_path: Path, text: str = PLAN) -> Path:
    path = tmp_path / "plans" / "PLAN.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


async def _confirm(_name: str, _args: dict) -> bool:
    return False


def _run(message: str) -> tuple[bool, list[dict]]:
    frames: list[dict] = []
    finished = asyncio.run(
        chat._run_project_command(message, "stub", frames.append, _confirm)
    )
    return finished, frames


def test_a_named_plan_in_a_subfolder_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    plan = _plan(tmp_path)
    assert chat._project_plan_path("/project plans/PLAN.md") == plan
    assert chat._project_plan_path("/project plans\\PLAN.md") == plan


def test_a_name_outside_the_workspace_matches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    _plan(tmp_path)
    for message in (
        "/project",
        "/project ../PLAN.md",
        "/project /etc/hosts",
        "/project ~/PLAN.md",
        "/project plans/absent.md",
    ):
        assert chat._project_plan_path(message) is None


def test_a_bare_command_shows_the_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    finished, frames = _run("/project")
    assert finished is True
    assert "Usage: `/project <file.md>`" in frames[1]["data"]


def test_a_missing_plan_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    finished, frames = _run("/project absent.md")
    assert finished is True
    assert "is not a file inside the workspace" in frames[1]["data"]


def test_a_file_without_phases_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    readme = tmp_path / "README.md"
    readme.write_text("# Title\n\n- [ ] a task\n", encoding="utf-8")
    finished, frames = _run("/project README.md")
    assert finished is True
    assert "has no phase headings" in frames[1]["data"]


def test_a_finished_run_summarises_the_phases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    _plan(tmp_path)
    import core.project_runner as runner

    async def fake_run(plan, **kwargs):
        kwargs["on_event"]("project_phase", phase="Phase 1: one", state="done")
        kwargs["progress"](100)
        return [SimpleNamespace(ok=True, phase=SimpleNamespace(title="Phase 1: one"), attempts=1)]

    monkeypatch.setattr(runner, "run_project_file", fake_run)
    finished, frames = _run("/project plans/PLAN.md")

    assert finished is True
    kinds = [frame["type"] for frame in frames]
    assert "project_phase" in kinds and "project_progress" in kinds
    summary = frames[-2]["data"]
    assert "1/1 phase(s) finished" in summary


def test_a_stopped_run_names_the_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    _plan(tmp_path)
    import core.project_runner as runner

    async def fake_run(plan, **kwargs):
        return [SimpleNamespace(ok=False, phase=SimpleNamespace(title="Phase 1: one"), attempts=4)]

    monkeypatch.setattr(runner, "run_project_file", fake_run)
    _, frames = _run("/project plans/PLAN.md")
    summary = frames[-2]["data"]
    assert "0/1 phase(s) finished" in summary
    assert "Stopped at `Phase 1: one` after 4 attempt(s)" in summary
    assert "the tasks are marked [!]" in summary


def test_an_exception_ends_the_turn_with_its_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    _plan(tmp_path)
    import core.project_runner as runner

    async def fake_run(plan, **kwargs):
        raise RuntimeError("gate runner vanished")

    monkeypatch.setattr(runner, "run_project_file", fake_run)
    finished, frames = _run("/project plans/PLAN.md")
    assert finished is True
    assert frames[-2] == {"type": "error", "msg": "Project run failed: gate runner vanished"}


def test_an_unreachable_engine_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    _plan(tmp_path)
    import core.project_runner as runner

    async def fake_run(plan, **kwargs):
        raise chat.OllamaNotReachableError()

    monkeypatch.setattr(runner, "run_project_file", fake_run)
    monkeypatch.setattr(chat, "_unreachable_engine_message", lambda provider=None: "engine off")
    _, frames = _run("/project plans/PLAN.md")
    assert frames[-2] == {"type": "error", "msg": "engine off"}
