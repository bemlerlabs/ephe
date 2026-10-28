"""`ephe project`: argument refusals, the dry run, and both run outcomes."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import ephe_cli

PLAN = """\
# Plan

## Phase 1: one
- [ ] a
Gate: `test -f a`

## Phase 2: two
- [x] b
"""


def _args(**overrides) -> SimpleNamespace:
    values = {"project_file": "", "model": None, "dry_run": False, "json": False}
    values.update(overrides)
    return SimpleNamespace(**values)


def _plan(tmp_path: Path) -> Path:
    path = tmp_path / "PLAN.md"
    path.write_text(PLAN, encoding="utf-8")
    return path


def _stub_engine(monkeypatch) -> None:
    monkeypatch.setattr(
        ephe_cli, "engine_for_headless_run", lambda args, model: SimpleNamespace(model="stub")
    )

    async def noop() -> None:
        return None

    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", noop)


def test_missing_argument_and_missing_file_exit_two(tmp_path: Path, capsys) -> None:
    assert ephe_cli.cmd_project(_args()) == 2
    assert ephe_cli.cmd_project(_args(project_file=str(tmp_path / "absent.md"))) == 2
    assert "Usage: ephe project" in capsys.readouterr().out


def test_a_plan_without_phases_exits_two(tmp_path: Path, capsys) -> None:
    path = tmp_path / "README.md"
    path.write_text("# Title\n\n- [ ] a task\n", encoding="utf-8")
    assert ephe_cli.cmd_project(_args(project_file=str(path))) == 2
    assert "no phase headings" in capsys.readouterr().out


def test_dry_run_lists_phases_and_gates(tmp_path: Path, capsys) -> None:
    assert ephe_cli.cmd_project(_args(project_file=str(_plan(tmp_path)), dry_run=True)) == 0
    out = capsys.readouterr().out
    assert "Phase 1: one: 0/1 done — gate: test -f a" in out
    assert "Phase 2: two: 1/1 done" in out


def test_a_passing_run_returns_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    _stub_engine(monkeypatch)
    import core.project_runner as runner

    seen: dict = {}

    async def fake_run(plan, **kwargs):
        seen["plan"] = Path(plan)
        kwargs["progress"](100)
        kwargs["on_event"]("project_phase", phase="Phase 1: one")
        return [
            SimpleNamespace(ok=True, phase=SimpleNamespace(title="Phase 1: one"), attempts=1),
            SimpleNamespace(ok=True, phase=SimpleNamespace(title="Phase 2: two"), attempts=0),
        ]

    monkeypatch.setattr(runner, "run_project_file", fake_run)
    code = ephe_cli.cmd_project(_args(project_file=str(_plan(tmp_path))))

    assert code == 0
    assert seen["plan"].name == "PLAN.md"
    out = capsys.readouterr().out
    assert "2/2 phase(s) finished" in out


def test_a_failing_phase_returns_one(tmp_path: Path, monkeypatch, capsys) -> None:
    _stub_engine(monkeypatch)
    import core.project_runner as runner

    async def fake_run(plan, **kwargs):
        return [SimpleNamespace(ok=False, phase=SimpleNamespace(title="Phase 1: one"), attempts=4)]

    monkeypatch.setattr(runner, "run_project_file", fake_run)
    code = ephe_cli.cmd_project(_args(project_file=str(_plan(tmp_path))))

    assert code == 1
    out = capsys.readouterr().out
    assert "stopped at Phase 1: one after 4 attempt(s)" in out
