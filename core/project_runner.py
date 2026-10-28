"""A phase runner for any multi-phase Markdown plan.

The file is the state: every task line carries `[ ]`, `[>]`, `[x]` or `[!]`,
and a phase's gate command sits in its own block. The runner reads that,
executes the phases in order, and writes each transition back atomically before
the next one starts — an interrupted run resumes where the file says it stopped.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from core import shell_sandbox

PHASES_DEFAULT_REPAIRS = 3
GATE_TIMEOUT_SECONDS = 300.0
MAX_GATE_OUTPUT = 4000

_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<body>.+?)\s*#*\s*$")
_PHASE_BODY = re.compile(
    r"^(?:phase|stage|step|milestone)\b[\s:.\-]*(?P<title>.*)$", re.IGNORECASE
)
_TASK = re.compile(r"^(?P<indent>\s*[-*+]\s+)\[(?P<mark>[ xX>!])\]\s+(?P<text>.+?)\s*$")
_GATE = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:gate|check|verify)\s*[:=]\s*`?(?P<command>[^`\n]+?)`?\s*$",
    re.IGNORECASE,
)

_MARK_BY_STATUS = {"open": " ", "active": ">", "done": "x", "failed": "!"}
_STATUS_BY_MARK = {" ": "open", "x": "done", "X": "done", ">": "active", "!": "failed"}


@dataclass
class ProjectTask:
    text: str
    line: int
    status: str = "open"


@dataclass
class ProjectPhase:
    title: str
    line: int
    level: int
    tasks: list[ProjectTask] = field(default_factory=list)
    gate: str | None = None

    @property
    def done(self) -> bool:
        return bool(self.tasks) and all(task.status == "done" for task in self.tasks)


@dataclass
class PhaseResult:
    phase: ProjectPhase
    ok: bool
    attempts: int
    output: str = ""


def parse_project_text(text: str) -> list[ProjectPhase]:
    """Phases and their tasks, in file order; headings outside the phase forms are ignored."""
    phases: list[ProjectPhase] = []
    current: ProjectPhase | None = None
    for index, raw in enumerate(text.split("\n")):
        heading = _HEADING.match(raw)
        if heading:
            body = heading.group("body")
            phase_match = _PHASE_BODY.match(body)
            if phase_match:
                current = ProjectPhase(
                    title=body,
                    line=index,
                    level=len(heading.group("hashes")),
                )
                phases.append(current)
            else:
                current = None
            continue
        if current is None:
            continue
        task = _TASK.match(raw)
        if task:
            current.tasks.append(
                ProjectTask(
                    text=task.group("text"),
                    line=index,
                    status=_STATUS_BY_MARK.get(task.group("mark"), "open"),
                )
            )
            continue
        gate = _GATE.match(raw)
        if gate and current.gate is None:
            current.gate = gate.group("command").strip()
    return phases


def parse_project_file(path: str | Path) -> list[ProjectPhase]:
    return parse_project_text(Path(path).read_text(encoding="utf-8"))


def _atomic_write(path: Path, lines: list[str]) -> None:
    directory = path.parent
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, prefix=f".{path.name}.", delete=False
    )
    try:
        handle.writelines(lines)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


def update_project_file(path: str | Path, phases: list[ProjectPhase]) -> int:
    """Write every task's marker into its line; all other lines stay byte-identical."""
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = 0
    for phase in phases:
        for task in phase.tasks:
            if not 0 <= task.line < len(lines):
                continue
            match = _TASK.match(lines[task.line].rstrip("\n"))
            if not match:
                continue
            mark = _MARK_BY_STATUS.get(task.status, " ")
            replacement = (
                f"{match.group('indent')}[{mark}] {match.group('text')}"
                + ("\n" if lines[task.line].endswith("\n") else "")
            )
            if replacement != lines[task.line]:
                lines[task.line] = replacement
                changed += 1
    if changed:
        _atomic_write(target, lines)
    return changed


def append_failure_note(path: str | Path, phase: ProjectPhase, note: str) -> None:
    """One blockquote line after the phase's last task carries the failure."""
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    anchor = phase.tasks[-1].line if phase.tasks else phase.line
    insert_at = min(anchor + 1, len(lines))
    text = " ".join(note.split())[:600]
    lines.insert(insert_at, f"> Failed: {text}\n")
    _atomic_write(target, lines)


def run_gate(command: str, workspace: str | Path,
             timeout: float = GATE_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Run a phase gate through the Seatbelt when the platform offers it."""
    base = str(Path(workspace).resolve())
    wrapped = shell_sandbox.wrap_command(command, base) if shell_sandbox.is_available() else None
    argv = wrapped or ["/bin/sh", "-lc", command]
    try:
        done = subprocess.run(
            argv, cwd=base, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"gate could not run: {exc}"
    output = f"{done.stdout}{done.stderr}".strip()
    return done.returncode == 0, output[-MAX_GATE_OUTPUT:]


def phase_prompt(phase: ProjectPhase, map_text: str, plan_path: Path) -> str:
    tasks = "\n".join(f"- {task.text}" for task in phase.tasks if task.status != "done")
    gate = f"\nIts gate command is: {phase.gate}" if phase.gate else ""
    map_block = f"\n\n{map_text}" if map_text else ""
    return (
        f"Work on one phase of the plan {plan_path.name}: {phase.title}\n"
        f"Tasks:\n{tasks}{gate}\n"
        "Edit the files the tasks describe, then stop. The runner marks the "
        "checkboxes and runs the gate; do not edit the plan file itself."
        f"{map_block}"
    )


Step = Callable[[ProjectPhase, str], Awaitable[str]]
Gate = Callable[[str, Path], tuple[bool, str]]
Progress = Callable[[int], None]
EventListener = Callable[..., None]


def goal_phase_step(model: str, policy=None, on_event: EventListener | None = None,
                    plan_path: Path | None = None) -> Step:
    """A step that hands one phase to the goal loop (model + tools + re-turns)."""
    from core.goal_loop import GoalRunner

    async def _step(phase: ProjectPhase, map_text: str) -> str:
        runner = GoalRunner(
            model=model,
            check_command="true",
            max_turns=3,
            on_event=on_event,
            policy=policy,
        )
        result = await runner.run(
            phase_prompt(phase, map_text, plan_path or Path("plan.md"))
        )
        return getattr(result, "final_answer", "") or str(result)

    return _step


class ProjectRunner:
    """Sequential, resumable execution of a Markdown phase plan."""

    def __init__(
        self,
        path: str | Path,
        *,
        workspace: str | Path | None = None,
        step: Step | None = None,
        gate: Gate = run_gate,
        project_map: str = "",
        max_repairs: int = PHASES_DEFAULT_REPAIRS,
        on_event: EventListener | None = None,
        progress: Progress | None = None,
    ) -> None:
        self.path = Path(path)
        self.workspace = Path(workspace) if workspace else self.path.parent
        self.step = step
        self.gate = gate
        self.project_map = project_map
        self.max_repairs = max(1, int(max_repairs))
        self.on_event = on_event
        self.progress = progress

    def _emit(self, kind: str, **payload) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(kind, **payload)
        except Exception:
            pass

    def _report_progress(self, done: int, total: int) -> None:
        if self.progress is None:
            return
        percent = int(round((done / total) * 100)) if total else 0
        try:
            self.progress(max(0, min(100, percent)))
        except Exception:
            pass

    async def run(self) -> list[PhaseResult]:
        phases = parse_project_file(self.path)
        if not phases:
            raise ValueError(
                f"{self.path.name} has no phase headings "
                "(# Phase 1, ## Stage 2, ...)"
            )
        total = sum(len(phase.tasks) for phase in phases) or len(phases)
        done = sum(1 for phase in phases for task in phase.tasks if task.status == "done")
        self._report_progress(done, total)
        self._emit("project_start", path=str(self.path), phases=len(phases), tasks=total)

        results: list[PhaseResult] = []
        failures: list[tuple[ProjectPhase, str]] = []
        for phase in phases:
            open_tasks = [task for task in phase.tasks if task.status != "done"]
            if not open_tasks:
                results.append(PhaseResult(phase=phase, ok=True, attempts=0))
                continue
            for task in open_tasks:
                task.status = "active"
            update_project_file(self.path, [phase])
            self._emit("project_phase", phase=phase.title, state="active")

            ok = False
            attempts = 0
            output = ""
            for attempt in range(self.max_repairs + 1):
                attempts = attempt + 1
                if self.step is not None:
                    output = await self.step(phase, self.project_map)
                if phase.gate:
                    ok, gate_output = await asyncio.to_thread(
                        self.gate, phase.gate, self.workspace
                    )
                    output = f"{output}\n{gate_output}".strip()
                else:
                    ok = True
                if ok:
                    break
                self._emit(
                    "project_repair",
                    phase=phase.title,
                    attempt=attempts,
                    budget=self.max_repairs,
                    output=output[-MAX_GATE_OUTPUT:],
                )
            if ok:
                for task in open_tasks:
                    task.status = "done"
                update_project_file(self.path, [phase])
                done += len(open_tasks)
                self._report_progress(done, total)
                self._emit("project_phase", phase=phase.title, state="done")
                results.append(PhaseResult(phase=phase, ok=True, attempts=attempts, output=output))
                continue

            for task in open_tasks:
                task.status = "failed"
            update_project_file(self.path, [phase])
            failures.append((phase, output))
            self._emit("project_phase", phase=phase.title, state="failed")
            results.append(PhaseResult(phase=phase, ok=False, attempts=attempts, output=output))
            break

        for phase, output in reversed(failures):
            append_failure_note(self.path, phase, output or "gate failed")
        self._emit(
            "project_done",
            ok=all(result.ok for result in results),
            phases=len(results),
        )
        return results


async def run_project_file(
    path: str | Path,
    *,
    model: str | None = None,
    step: Step | None = None,
    policy=None,
    workspace: str | Path | None = None,
    max_repairs: int = PHASES_DEFAULT_REPAIRS,
    on_event: EventListener | None = None,
    progress: Progress | None = None,
) -> list[PhaseResult]:
    """Run a plan with the goal loop as its step unless a step is injected."""
    from core.semindex.project_map import project_map_for_workspace

    plan = Path(path)
    base = Path(workspace) if workspace else plan.parent
    chosen_step = step or (
        goal_phase_step(model or "", policy, on_event, plan) if model else None
    )
    runner = ProjectRunner(
        plan,
        workspace=base,
        step=chosen_step,
        project_map=project_map_for_workspace(base),
        max_repairs=max_repairs,
        on_event=on_event,
        progress=progress,
    )
    return await runner.run()
