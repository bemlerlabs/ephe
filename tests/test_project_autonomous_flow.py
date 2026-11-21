"""The full loop: index a workspace, then run a four-phase plan to the last box."""
from __future__ import annotations

import asyncio
from pathlib import Path

from core.project_runner import parse_project_file, run_gate, run_project_file
from core.semindex.store import SemanticStore, index_database, index_workspace

PLAN = """\
# Workspace plan

## Phase 1: Boot the parser
- [ ] create parser.py
Gate: `test -f parser.py`

## Phase 2: Add the model
- [ ] create model.py
Gate: `test -f model.py`

## Phase 3: Wire the view
- [ ] create view.ts
Gate: `test -f view.ts`

## Phase 4: Prove it
- [ ] create engine.rs
Gate: `test -f engine.rs`
"""

STEPS = {
    "Phase 1": ("parser.py", "def parse(text):\n    return text.split()\n"),
    "Phase 2": ("model.py", "class Document:\n    def __init__(self, text):\n        self.text = text\n"),
    "Phase 3": ("view.ts", "export interface DocView {\n  text: string\n}\n"),
    "Phase 4": ("engine.rs", "pub struct Engine {\n    pub ready: bool,\n}\n"),
}


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def boot():\n    return 1\n", encoding="utf-8")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "index.js").write_text(
        "export const skipped = 1\n", encoding="utf-8"
    )
    (tmp_path / "PLAN.md").write_text(PLAN, encoding="utf-8")
    return tmp_path


def test_index_then_run_a_generic_four_phase_plan(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    first = index_workspace(workspace)
    assert first.files == 1
    assert first.symbols > 0

    prompts: list[str] = []
    events: list[tuple[str, dict]] = []
    percents: list[int] = []

    async def step(phase, map_text):
        prompts.append(map_text)
        name, body = next(body for key, body in STEPS.items() if phase.title.startswith(key))
        (workspace / name).write_text(body, encoding="utf-8")
        return f"wrote {name}"

    results = asyncio.run(
        run_project_file(
            workspace / "PLAN.md",
            step=step,
            workspace=workspace,
            on_event=lambda kind, **payload: events.append((kind, payload)),
            progress=percents.append,
        )
    )

    assert [result.ok for result in results] == [True, True, True, True]
    assert [result.attempts for result in results] == [1, 1, 1, 1]
    assert percents[-1] == 100
    assert all("Project map" in text for text in prompts)

    phases = parse_project_file(workspace / "PLAN.md")
    assert all(phase.done for phase in phases)
    text = (workspace / "PLAN.md").read_text(encoding="utf-8")
    assert "[ ]" not in text
    assert text.count("[x]") == 4
    assert "> Failed:" not in text
    assert any(kind == "project_done" and payload["ok"] for kind, payload in events)

    again = index_workspace(workspace)
    assert again.files == 5
    store = SemanticStore(index_database(workspace))
    try:
        names = {row[0] for row in store.conn.execute("SELECT name FROM semindex_nodes")}
        kinds = {row[0] for row in store.conn.execute("SELECT kind FROM semindex_nodes")}
    finally:
        store.close()
    assert {"Document", "DocView", "Engine"} <= names
    assert {"class", "interface", "struct"} <= kinds


def test_a_failing_phase_stops_the_chain_and_marks_the_file(tmp_path: Path) -> None:
    workspace = tmp_path
    (workspace / "PLAN.md").write_text(
        "## Phase 1: First\n- [ ] write a.txt\nGate: `test -f a.txt`\n\n"
        "## Phase 2: Second\n- [ ] write b.txt\nGate: `test -f b.txt`\n",
        encoding="utf-8",
    )

    async def step(phase, map_text):
        if phase.title.startswith("Phase 1"):
            (workspace / "a.txt").write_text("ok", encoding="utf-8")
        return "done"

    results = asyncio.run(
        run_project_file(
            workspace / "PLAN.md",
            step=step,
            workspace=workspace,
            max_repairs=1,
            on_event=None,
        )
    )

    assert len(results) == 2
    assert results[0].ok is True
    assert results[1].ok is False
    text = (workspace / "PLAN.md").read_text(encoding="utf-8")
    assert "- [x] write a.txt" in text
    assert "- [!] write b.txt" in text
    assert "> Failed:" in text


def test_real_gate_reads_the_workspace(tmp_path: Path) -> None:
    ok, _ = run_gate("test -f nothing", tmp_path)
    assert ok is False
    (tmp_path / "nothing").write_text("", encoding="utf-8")
    ok, _ = run_gate("test -f nothing", tmp_path)
    assert ok is True
