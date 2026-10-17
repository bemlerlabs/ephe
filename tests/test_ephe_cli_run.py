"""The work verb `ephe run`: a task from the terminal that streams and can be resumed.

`tests/test_ephe_cli_surface.py` pins the parser shape; this file pins what the verb
does. Every case drives `ephe_cli.cmd_run` in-process through the real parser with the
engine resolver and the agent loop replaced by fakes: no network, no model, and the
operator's own ``~/.ephe`` session store is never read — the store cases repoint the
module globals at a ``tmp_path`` exactly the way the isolation suite does.

The seam under test is ``core/_cli_run.py``: the sink that turns the loop's callbacks
into terminal lines, the session read/write that makes a run resumable, and the
change-set hand-off that lets `ephe show`/`review`/`publish` close the loop.

Given / When / Then, strictly.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import ephe_cli


CHOICE = SimpleNamespace(provider="openai_compatible", model="stub-model", api_url="http://127.0.0.1:9/v1")


def run(*argv: str) -> int:
    """One CLI call through the real parser, the way `main()` dispatches it."""
    args = ephe_cli.build_parser().parse_args(list(argv))
    return args.func(args)


@pytest.fixture
def engine(monkeypatch):
    """A resolved engine, so no case has to hold a real choice to reach the loop."""
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda args, model: CHOICE)
    return CHOICE


@pytest.fixture
def streaming_loop(monkeypatch):
    """A fake react_loop that drives every callback a real one would, in order."""
    seen: dict = {}

    async def fake_loop(**kwargs):
        seen["kwargs"] = kwargs
        kwargs["on_phase"]("Round 1/1 — planning")
        kwargs["on_tool_start"]("read_file", {"path": "a.txt"})
        kwargs["on_tool_done"]("read_file", "A\n")
        kwargs["on_chunk"]("Done: ")
        kwargs["on_chunk"]("a.txt is updated.\n")
        return "Done: a.txt is updated.\n"

    monkeypatch.setattr("core.react.react_loop", fake_loop)
    return seen


@pytest.fixture
def isolated_seam(monkeypatch):
    """Keep the streaming cases off disk: no session opened, no change set recorded."""
    monkeypatch.setattr("core._cli_run.open_session", lambda title: "s-1")
    monkeypatch.setattr("core._cli_run.persist_turn", lambda *a, **k: None)
    monkeypatch.setattr("core._cli_run.record_change_set", lambda workspace, **k: None)


# the core promise: a run that streams


def test_run_streams_phases_tools_and_answer_in_order(engine, streaming_loop, isolated_seam, capsys):
    """
    GIVEN a run whose loop emits a phase, a tool call and answer chunks
    WHEN `ephe run` runs
    THEN every line reaches stdout as it happens, in the loop's order — not at the end.
    """
    assert run("run", "update a.txt") == 0

    out = capsys.readouterr().out
    assert "◑ Round 1/1 — planning" in out
    assert "→ read_file" in out
    assert "✓ read_file" in out
    assert "Done: a.txt is updated." in out
    # the phase printed before the tool, the tool before the answer
    assert out.index("◑ Round 1/1") < out.index("→ read_file") < out.index("Done:")


def test_run_forwards_the_turn_id_and_the_resume_history(engine, streaming_loop, isolated_seam):
    """
    GIVEN a plain run
    WHEN the loop is entered
    THEN it is handed the recorder's turn id, an empty context and the coding directive.
    """
    run("run", "update a.txt")

    kwargs = streaming_loop["kwargs"]
    assert kwargs["question"] == "update a.txt"
    assert kwargs["model"] == "stub-model"
    assert kwargs["context"] == []
    assert kwargs["extra_system_prompt"]  # the coding directive, not an empty string


def test_run_under_json_keeps_stdout_for_a_single_record(engine, streaming_loop, isolated_seam, capsys):
    """
    GIVEN a run asked for machine output
    WHEN it finishes
    THEN stdout holds exactly one JSON object and the stream went to stderr.
    """
    assert run("run", "--json", "update a.txt") == 0

    captured = capsys.readouterr()
    record = json.loads(captured.out)  # one object, or this raises
    assert record["entrypoint"] == "run"
    assert "◑" in captured.err and "→ read_file" in captured.err
    assert "◑" not in captured.out


def test_no_stream_buffers_the_answer_to_the_end(engine, streaming_loop, isolated_seam, capsys):
    """
    GIVEN a run asked not to stream
    WHEN the loop emits answer chunks
    THEN nothing is on stdout until the run finishes, then the whole answer is.
    """
    assert run("run", "--no-stream", "update a.txt") == 0

    out = capsys.readouterr().out
    assert out.count("Done: a.txt is updated.") == 1


# resume


def test_resume_of_an_unknown_session_is_refused_before_the_loop(engine, isolated_seam, monkeypatch, capsys):
    """
    GIVEN `--resume` naming a session the store does not hold
    WHEN `ephe run` runs
    THEN it refuses with the id, the store and the fix — the loop is never entered.
    """
    called = {"loop": False}

    async def boom(**kwargs):  # pragma: no cover - must not be reached
        called["loop"] = True
        return ""

    monkeypatch.setattr("core.react.react_loop", boom)

    assert run("run", "--resume", "nope", "task") == 1

    err = capsys.readouterr().err
    assert "nope" in err
    assert "ephe session list" in err
    assert called["loop"] is False


def test_resume_continues_a_saved_session(tmp_path, monkeypatch, engine, isolated_seam):
    """
    GIVEN a session holding a prior turn
    WHEN `ephe run --resume <id>` runs
    THEN the loop receives that history as its context.
    """
    from core import multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ms, "REGISTRY_FILE", tmp_path / "sessions" / "registry.json")
    entry = ms.create_session("prior")
    ms.save_messages(
        entry["id"],
        [{"role": "user", "content": "earlier?"}, {"role": "assistant", "content": "yes"}],
    )

    seen: dict = {}

    async def fake_loop(**kwargs):
        seen["context"] = kwargs["context"]
        return "ok"

    monkeypatch.setattr("core.react.react_loop", fake_loop)

    assert run("run", "--resume", entry["id"], "next") == 0
    assert seen["context"] == [
        {"role": "user", "content": "earlier?"},
        {"role": "assistant", "content": "yes"},
    ]


# the plan and the change-set hand-off


def test_dry_run_prints_the_plan_and_never_enters_the_loop(engine, isolated_seam, monkeypatch, capsys):
    """
    GIVEN `--dry-run`
    WHEN `ephe run` runs
    THEN the plan is printed and the loop is never entered — no turn is spent.
    """
    called = {"loop": False}

    async def boom(**kwargs):  # pragma: no cover - must not be reached
        called["loop"] = True
        return ""

    monkeypatch.setattr("core.react.react_loop", boom)

    assert run("run", "--dry-run", "do a thing") == 0

    out = capsys.readouterr().out
    assert "run plan:" in out
    assert "workspace:" in out
    assert "resume:    a new session" in out
    assert called["loop"] is False


def test_run_keeps_a_resumable_session_and_records_a_change_set(tmp_path, monkeypatch, engine, streaming_loop):
    """
    GIVEN a repository with a real edit
    WHEN `ephe run` finishes
    THEN the turn is saved in a session and the diff is recorded as a change set whose id
         the printout hands to `ephe show`/`review`/`publish`.
    """
    from core import change_set as store
    from core import multi_session as ms
    from core.change_set_read import list_for

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ms, "REGISTRY_FILE", tmp_path / "sessions" / "registry.json")
    monkeypatch.setattr(store, "CHANGESETS_DIR", tmp_path / "changesets")

    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (("init", "-q", "-b", "main"), ("config", "user.email", "cli@example.invalid"),
                 ("config", "user.name", "cli")):
        subprocess.run(["git", *argv], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("A\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("A2\n", encoding="utf-8")

    assert run("run", "--workspace", str(repo), "update a.txt") == 0

    sessions = ms.list_sessions()
    assert len(sessions) == 1
    assert len(ms.load_messages(sessions[0]["id"])) == 2  # the task and the answer

    built = list_for(str(repo))
    assert len(built) == 1
    assert [f.path for f in built[0].files] == ["a.txt"]


def test_run_names_the_review_loop_for_the_recorded_change_set(tmp_path, monkeypatch, streaming_loop, capsys):
    """
    GIVEN a run that records a change set
    WHEN the printout is read
    THEN it names `ephe show`, `ephe review` and `ephe publish` for that id.
    """
    from core import change_set as store
    from core import multi_session as ms
    from core.change_set_read import list_for

    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda args, model: CHOICE)
    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ms, "REGISTRY_FILE", tmp_path / "sessions" / "registry.json")
    monkeypatch.setattr(store, "CHANGESETS_DIR", tmp_path / "changesets")
    monkeypatch.setattr("core._cli_run.open_session", lambda title: "s-1")

    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (("init", "-q", "-b", "main"), ("config", "user.email", "cli@example.invalid"),
                 ("config", "user.name", "cli")):
        subprocess.run(["git", *argv], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("A\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("A2\n", encoding="utf-8")

    assert run("run", "--workspace", str(repo), "update a.txt") == 0

    built = list_for(str(repo))
    assert len(built) == 1
    out = capsys.readouterr().out
    assert f"change set {built[0].id}" in out
    assert f"ephe show {built[0].id}" in out
    assert f"ephe review {built[0].id}" in out
    assert f"ephe publish {built[0].id}" in out


def test_run_says_so_in_one_line_when_the_tree_is_clean(engine, streaming_loop, monkeypatch, capsys):
    """
    GIVEN a workspace that holds no diff
    WHEN `ephe run` finishes
    THEN it prints one line saying so instead of a change set with zero files.
    """
    monkeypatch.setattr("core._cli_run.record_change_set", lambda workspace, **k: None)

    assert run("run", "think") == 0
    assert "no change set:" in capsys.readouterr().out


# the seam's own pieces, reached without a parser


def test_the_sink_closes_a_half_written_answer_line():
    """
    GIVEN a sink whose answer did not end in a newline
    WHEN finish() runs
    THEN the line is closed so the next printout starts clean.
    """
    import io

    from core import _cli_run as seam

    buf = io.StringIO()
    sink = seam.StreamSink(as_json=False, stream=True, out=buf)
    sink.chunk("no newline")
    sink.finish()

    assert buf.getvalue() == "no newline\n"


# a task the verb refuses before it spends anything


def test_run_refuses_an_empty_task_before_it_resolves_an_engine(monkeypatch, capsys):
    """
    GIVEN `ephe run` with a task that is only whitespace
    WHEN it runs
    THEN it prints the usage line, returns 2 and never resolves an engine.
    """
    resolved: list = []
    monkeypatch.setattr(
        ephe_cli, "engine_for_headless_run",
        lambda args, model: resolved.append(model) or CHOICE,
    )

    assert run("run", "   ") == 2

    out = capsys.readouterr().out
    assert out.startswith("Usage: ephe run")
    assert "take the failing test" in out
    assert resolved == []


# a loop that dies, and a diff that cannot be recorded


def test_run_keeps_a_record_and_closes_the_stream_when_the_loop_raises(
    engine, isolated_seam, monkeypatch, capsys, tmp_path
):
    """
    GIVEN a loop that writes half an answer and then raises
    WHEN `ephe run` runs
    THEN the half-written line is closed, a record naming the exception is written, and
         the exception still reaches the caller.
    """
    async def boom(**kwargs):
        kwargs["on_chunk"]("half an ans")  # no newline: the sink has to close the line
        raise RuntimeError("engine died")

    monkeypatch.setattr("core.react.react_loop", boom)
    record_path = tmp_path / "run.json"

    with pytest.raises(RuntimeError, match="engine died"):
        run("run", "--run-record", str(record_path), "update a.txt")

    assert capsys.readouterr().out.endswith("half an ans\n")

    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["outcome"]["error"] == "RuntimeError: engine died"


def test_run_reports_why_a_workspace_could_not_be_recorded(engine, streaming_loop, monkeypatch, capsys):
    """
    GIVEN a workspace the change-set store refuses
    WHEN `ephe run` finishes
    THEN the store's own sentence is printed instead of the empty-tree line.
    """
    from core import _cli_run as seam

    def refuse(workspace, **kwargs):
        raise seam.RunError(
            f"the workspace {workspace} holds no change to record: not a git worktree",
            "`ephe run` records a change set only inside a git worktree.",
        )

    monkeypatch.setattr("core._cli_run.open_session", lambda title: "s-1")
    monkeypatch.setattr("core._cli_run.persist_turn", lambda *a, **k: None)
    monkeypatch.setattr("core._cli_run.record_change_set", refuse)

    assert run("run", "update a.txt") == 0

    out = capsys.readouterr().out
    assert "holds no change to record" in out
    assert "no change set:" not in out


# the verifier decides the process exit code, so a CI step can branch on the run


def test_a_failing_verifier_is_the_runs_exit_code(engine, streaming_loop, isolated_seam, monkeypatch):
    """
    GIVEN `ephe run --verify` whose verifier fails
    WHEN the turn ends
    THEN the verb returns the verifier's own status instead of 0.
    """
    async def failing(command):
        return "1 failed, 2 passed in 0.31s [exit 1]"

    monkeypatch.setattr("core.run_evidence.run_verifier", failing)

    assert run("run", "fix the failing test", "--verify", "pytest -q") == 1


def test_a_passing_verifier_is_exit_zero(engine, streaming_loop, isolated_seam, monkeypatch):
    """
    GIVEN `ephe run --verify` whose verifier passes
    WHEN the turn ends
    THEN the verb returns 0.
    """
    async def passing(command):
        return "3 passed in 0.12s [exit 0]"

    monkeypatch.setattr("core.run_evidence.run_verifier", passing)

    assert run("run", "fix the failing test", "--verify", "pytest -q") == 0


def test_the_exit_status_is_the_verifiers_own_number(engine, streaming_loop, isolated_seam, monkeypatch):
    """
    GIVEN a verifier that exits with a status of its own (a linter's 3)
    WHEN the run ends
    THEN the process carries that number, so the caller sees which check failed.
    """
    async def linter(command):
        return "2 lint errors [exit 3]"

    monkeypatch.setattr("core.run_evidence.run_verifier", linter)

    assert run("run", "tidy the module", "--verify", "ruff check") == 3


def test_the_exit_code_agrees_with_the_records_verdict(
    engine, streaming_loop, isolated_seam, monkeypatch, capsys
):
    """
    GIVEN the same failing verifier, read through --json
    WHEN the run ends
    THEN the record's own ``outcome.solved`` is false and the exit code is 1 — the two
         statements about one run cannot disagree.
    """
    async def failing(command):
        return "1 failed in 0.31s [exit 1]"

    monkeypatch.setattr("core.run_evidence.run_verifier", failing)
    monkeypatch.setattr("core.run_evidence.active_worktree", lambda: None)

    code = run("run", "fix the failing test", "--verify", "pytest -q", "--json")

    record = json.loads(capsys.readouterr().out)
    assert record["outcome"]["solved"] is False
    assert record["outcome"]["verifier"]["exit_code"] == 1
    assert code == 1


def test_a_run_without_a_verifier_still_returns_zero(engine, streaming_loop, isolated_seam, monkeypatch):
    """
    GIVEN `ephe run` with no --verify
    WHEN the turn ends
    THEN the verb answers 0 and never runs a check nobody asked for.
    """
    async def unexpected(command):
        raise AssertionError("no verifier was named")

    monkeypatch.setattr("core.run_evidence.run_verifier", unexpected)

    assert run("run", "just answer") == 0


def test_verifier_exit_falls_back_to_the_goal_loops_own_verdict():
    """
    GIVEN verifier output with no `[exit N]` marker
    WHEN the status is read
    THEN the goal loop's rule decides — the same rule the record's ``solved`` uses.
    """
    from core import _cli_run as seam

    assert seam.verifier_exit("3 passed in 0.12s [exit 0]") == 0
    assert seam.verifier_exit("2 failed, 1 passed [exit 2]") == 2
    assert seam.verifier_exit("3 failed, 1 passed in 0.4s") == 1
    assert seam.verifier_exit("⚠ rejected by the gate") == 1
    assert seam.verifier_exit("nothing was reported") == 0
    # No output at all is not a pass: the record's own verdict is false for it too.
    assert seam.verifier_exit("") == 1

