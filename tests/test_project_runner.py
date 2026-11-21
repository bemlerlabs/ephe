"""The phase engine: parsing, atomic markers, gates, budget, resume."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.project_runner import (
    ProjectRunner,
    append_failure_note,
    parse_project_file,
    parse_project_text,
    run_gate,
    update_project_file,
)

PLAN = """\
# Refactor plan

Some prose before the first phase.

## Phase 1: Extract the parser
- [ ] move parse() into parser.py
- [ ] update the imports
Gate: `test -f parser.py`

## Phase 2 — Wire the CLI
- [ ] call the parser from the CLI
- [x] done already

## Notes
- [ ] this box belongs to no phase
"""


def _plan(tmp_path: Path, text: str = PLAN) -> Path:
    path = tmp_path / "PLAN.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_phases_tasks_and_gate(tmp_path: Path) -> None:
    phases = parse_project_file(_plan(tmp_path))
    assert [phase.title for phase in phases] == [
        "Phase 1: Extract the parser",
        "Phase 2 — Wire the CLI",
    ]
    assert [task.text for task in phases[0].tasks] == [
        "move parse() into parser.py",
        "update the imports",
    ]
    assert phases[0].gate == "test -f parser.py"
    assert phases[1].gate is None
    assert phases[1].tasks[1].status == "done"
    assert phases[0].done is False


def test_markers_are_written_line_exact(tmp_path: Path) -> None:
    path = _plan(tmp_path)
    before = path.read_text(encoding="utf-8")
    phases = parse_project_file(path)

    phases[0].tasks[0].status = "active"
    phases[0].tasks[1].status = "done"
    changed = update_project_file(path, phases)

    after = path.read_text(encoding="utf-8")
    assert changed == 2
    assert "- [>] move parse() into parser.py" in after
    assert "- [x] update the imports" in after
    assert after.replace("- [>]", "- [ ]").replace(
        "- [x] update the imports", "- [ ] update the imports"
    ) == before
    assert not list(tmp_path.glob(".PLAN.md.*"))


def test_failure_note_lands_after_the_last_task(tmp_path: Path) -> None:
    path = _plan(tmp_path)
    phases = parse_project_file(path)
    append_failure_note(path, phases[0], "gate failed: missing parser.py")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[7].startswith("> Failed: gate failed")


def _gate_ok(command: str, workspace: Path) -> tuple[bool, str]:
    return True, ""


def _gate_never(command: str, workspace: Path) -> tuple[bool, str]:
    return False, "gate failed on purpose"


def _gate_twice(command: str, workspace: Path) -> tuple[bool, str]:
    calls = getattr(_gate_twice, "calls", 0) + 1
    _gate_twice.calls = calls
    return (calls > 2), f"attempt {calls}"


def test_runner_completes_every_phase_and_reports_progress(tmp_path: Path) -> None:
    path = _plan(tmp_path)
    seen: list[str] = []
    percents: list[int] = []
    events: list[str] = []

    async def step(phase, map_text):
        seen.append(phase.title)
        return "done"

    runner = ProjectRunner(
        path,
        step=step,
        gate=_gate_ok,
        project_map="## Project map\n- Files: 1",
        on_event=lambda kind, **payload: events.append(kind),
        progress=percents.append,
    )
    results = asyncio.run(runner.run())

    assert [result.ok for result in results] == [True, True]
    assert seen == ["Phase 1: Extract the parser", "Phase 2 — Wire the CLI"]
    assert percents[-1] == 100
    assert events[0] == "project_start"
    assert events[-1] == "project_done"
    text = path.read_text(encoding="utf-8")
    assert "- [x] move parse() into parser.py" in text
    assert "- [x] call the parser from the CLI" in text
    assert "[ ] this box belongs to no phase" in text


def test_runner_stops_after_the_repair_budget(tmp_path: Path) -> None:
    path = _plan(tmp_path)
    calls: list[str] = []

    async def step(phase, map_text):
        calls.append(phase.title)
        return "attempt"

    runner = ProjectRunner(
        path, step=step, gate=_gate_never, max_repairs=3
    )
    results = asyncio.run(runner.run())

    assert calls == ["Phase 1: Extract the parser"] * 4
    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].attempts == 4
    text = path.read_text(encoding="utf-8")
    assert "- [!] move parse() into parser.py" in text
    assert "- [ ] call the parser from the CLI" in text
    assert "> Failed:" in text
    assert "gate failed on purpose" in text


def test_runner_recovers_when_a_repair_passes(tmp_path: Path) -> None:
    path = _plan(tmp_path)
    _gate_twice.calls = 0

    async def step(phase, map_text):
        return "fixed"

    runner = ProjectRunner(path, step=step, gate=_gate_twice, max_repairs=3)
    results = asyncio.run(runner.run())

    assert results[0].ok is True
    assert results[0].attempts == 3
    assert "- [x] move parse() into parser.py" in path.read_text(encoding="utf-8")


def test_runner_resumes_from_the_disk_state(tmp_path: Path) -> None:
    text = PLAN.replace("- [ ] move parse() into parser.py", "- [x] move parse() into parser.py")
    text = text.replace("- [ ] update the imports", "- [x] update the imports")
    path = _plan(tmp_path, text)
    seen: list[str] = []

    async def step(phase, map_text):
        seen.append(phase.title)
        return "done"

    results = asyncio.run(ProjectRunner(path, step=step, gate=_gate_ok).run())

    assert seen == ["Phase 2 — Wire the CLI"]
    assert [result.ok for result in results] == [True, True]
    assert results[0].attempts == 0


def test_no_phase_headings_is_a_named_error(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("# Title\n\n- [ ] a task without a phase\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no phase headings"):
        asyncio.run(ProjectRunner(path, gate=_gate_ok).run())


def test_gate_runs_a_real_command_in_the_workspace(tmp_path: Path) -> None:
    ok, output = run_gate("test -f missing.txt", tmp_path)
    assert ok is False
    (tmp_path / "missing.txt").write_text("x", encoding="utf-8")
    ok, output = run_gate("test -f missing.txt", tmp_path)
    assert ok is True
    assert output == ""


def test_phase_heading_forms_are_accepted() -> None:
    phases = parse_project_text(
        "# Stage 1: alpha\n- [ ] a\n"
        "## Step two\n- [ ] b\n"
        "### Milestone 3\n- [ ] c\n"
        "## Plain section\n- [ ] ignored\n"
    )
    assert [phase.title for phase in phases] == ["Stage 1: alpha", "Step two", "Milestone 3"]
    assert [len(phase.tasks) for phase in phases] == [1, 1, 1]
