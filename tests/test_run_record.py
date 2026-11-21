"""tests/test_run_record.py — B1: the machine-readable run record for `ephe code`/`ephe goal`.

docs/CODING_AGENT_VS_PI_DESIGN.md §3.5 states the gap: both coding entry points printed
prose, accepted no machine-readable flag, and therefore could not emit the run record
the measurement protocol needs. These tests are the proof it now can, at the two levels
that matter:

* a **real** agent turn through the tool loop in core/chat.py — the provider is stubbed
  so nothing costs an engine call, while the registry, the approval gate, the audit log
  and the usage accounting all run for real, and the record is read back from them;
* the **CLI surface**: `--json` owns stdout with exactly one object (progress moves to
  stderr), `--run-record` writes that same object to a file, and the default human
  output stays byte-identical.

Plus the two properties a run file has to keep to be worth its name: a truncation that
stays provable through the recorded sha256, and a schema that refuses a record it cannot
fully explain.
"""
from __future__ import annotations

import argparse
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ephe_cli
from core import run_evidence
from core.chat import chat_with_tools
from core.run_evidence import RunRecorder, new_turn_id
from core.run_record import (
    DIFF_LIMIT,
    FAILURE_CLASSES,
    SCHEMA,
    RunRecordError,
    classify_failure,
    load_record,
    sha256_hex,
    validate_record,
    write_record,
)

# the shape, spelled out here and not read from the module
# A test that asked the module which keys it produced could never notice a key that
# quietly disappeared. These literals are the contract §2 of the design doc demands.
TOP = {"schema", "run_id", "entrypoint", "started_at", "identity", "outcome",
       "effort", "artifact", "failure", "determinism"}
IDENTITY = {"task", "worktree", "git_commit", "engine", "runtime"}
ENGINE = {"provider", "model", "endpoint", "decoding"}
ENDPOINT = {"kind", "is_loopback", "url_hash"}
DECODING = {"as_sent", "as_applied", "as_applied_reported"}
RUNTIME = {"python", "node", "npm", "platform", "machine"}
OUTCOME = {"solved", "solved_basis", "verifier", "error"}
VERIFIER = {"command", "exit_code", "tail", "tail_truncated", "tail_sha256", "turns"}
EFFORT = {"tool_rounds", "tool_rounds_source", "budget_cap", "tool_events",
          "tool_events_truncated", "tokens", "wall_seconds"}
EVENT = {"seq", "ts", "kind", "tool", "args_hash", "duration_ms", "status",
         "decision", "approval_consulted", "approval_decision"}
TOKENS = {"in", "out", "total", "estimated", "source", "tokenizer"}
ARTIFACT = {"diff", "diff_sha256", "diff_truncated", "diff_bytes", "diff_source"}
FAILURE = {"class", "evidence"}
DETERMINISM = {"rep", "repetitions", "grouping_key", "grouping_inputs"}


def key_shape(record: dict) -> dict:
    """Every key set of one record, as one comparable dict."""
    return {
        "top": set(record),
        "identity": set(record["identity"]),
        "engine": set(record["identity"]["engine"]),
        "endpoint": set(record["identity"]["engine"]["endpoint"]),
        "decoding": set(record["identity"]["engine"]["decoding"]),
        "runtime": set(record["identity"]["runtime"]),
        "outcome": set(record["outcome"]),
        "verifier": set(record["outcome"]["verifier"]),
        "effort": set(record["effort"]),
        "tokens": set(record["effort"]["tokens"]),
        "artifact": set(record["artifact"]),
        "failure": set(record["failure"]),
        "determinism": set(record["determinism"]),
    }


EXPECTED_SHAPE = {
    "top": TOP, "identity": IDENTITY, "engine": ENGINE, "endpoint": ENDPOINT,
    "decoding": DECODING, "runtime": RUNTIME, "outcome": OUTCOME, "verifier": VERIFIER,
    "effort": EFFORT, "tokens": TOKENS, "artifact": ARTIFACT, "failure": FAILURE,
    "determinism": DETERMINISM,
}


def _recorder(entrypoint: str = "code", **kw) -> RunRecorder:
    opts = {
        "entrypoint": entrypoint,
        "task": "make the failing test in tests/test_x.py green",
        "provider": "local_ollama",
        "model": "gemma4:12b",
        "turn_id": new_turn_id(entrypoint),
        "api_url": None,
        "gate_posture": "chat-gate",
    }
    opts.update(kw)
    return RunRecorder(**opts)


def _ollama_response(content: str = "", tool_calls=None):
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    response = MagicMock()
    response.message = message
    return response


def _tool_call(name: str, arguments: dict):
    function = MagicMock()
    function.name = name
    function.arguments = arguments
    call = MagicMock()
    call.function = function
    return call


class TestRealTurnRecord:
    """One real tool-loop turn: registry, approval gate, audit and usage all run for real."""

    async def test_given_real_tool_loop_when_recorded_then_shape_and_evidence(self, tmp_path):
        """Given: the agent asks for a read-only tool and a mutating write_file
        When: the loop runs with the recorder's turn id and the record is built
        Then: every required key is present, the round counter and both tool events come
              from the run itself, and the gate's decision is on the record"""
        recorder = _recorder(worktree=str(tmp_path))
        asked = [
            _tool_call("get_datetime", {}),
            _tool_call("write_file", {"path": "outside.py", "content": "x = 1\n"}),
        ]
        with patch("core.chat.ollama.AsyncClient") as client_class:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[
                _ollama_response(tool_calls=asked),
                _ollama_response(content="The change is applied and checked."),
            ])
            client_class.return_value = client
            answer = await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": recorder.task}],
                on_chunk=lambda _t: None,
                on_phase=recorder.on_phase,
                turn_id=recorder.turn_id,
            )
        record = recorder.build(answer=answer)

        assert key_shape(record) == EXPECTED_SHAPE
        assert record["schema"] == SCHEMA
        assert record["run_id"] == recorder.turn_id
        assert record["identity"]["task"] == recorder.task
        assert record["identity"]["engine"]["provider"] == "local_ollama"
        assert record["identity"]["engine"]["model"] == "gemma4:12b"
        # §3.3: the runtimes a verifier can reach are pinned, never assumed.
        assert record["identity"]["runtime"]["python"]
        assert set(record["determinism"]["grouping_inputs"]) > {"task", "model", "temperature"}

        effort = record["effort"]
        assert effort["tool_rounds"] == 1
        assert effort["tool_rounds_source"] == "phase"
        assert effort["budget_cap"] >= 1
        assert effort["wall_seconds"] >= 0.0
        # No provider usage frame in this turn, so the count is labelled as what it
        # is: not measured by the engine (`source` is the axis the auditor reads).
        assert effort["tokens"]["source"] == "estimated"
        assert effort["tokens"]["total"] > 0

        events = effort["tool_events"]
        assert [e["tool"] for e in events if e["kind"] == "tool_exec"] == ["get_datetime"]
        assert all(set(e) == EVENT for e in events)
        executed = next(e for e in events if e["kind"] == "tool_exec")
        assert len(executed["args_hash"]) == 16
        assert isinstance(executed["duration_ms"], int)
        assert executed["approval_consulted"] is False
        assert executed["approval_decision"] == "auto-approved"
        # The gate denied the mutating call (no approval channel in a headless CLI run),
        # and the record shows that decision instead of the run pretending it happened.
        denied = next(e for e in events if e["tool"] == "write_file")
        assert denied["kind"] == "approval"
        assert denied["approval_consulted"] is True
        assert denied["approval_decision"] == "denied"

        # No verifier was defined for `code`, so no verdict may be claimed (§2.2).
        assert record["outcome"]["solved"] is None
        assert record["outcome"]["solved_basis"] == "no_verifier"
        assert record["failure"]["class"] is None
        assert record["failure"]["evidence"]["diff_observable"] is False

    async def test_given_no_engine_answer_when_recorded_then_engine_degraded_not_wrong_code(
        self, tmp_path
    ):
        """A run that never got an answer is the engine's row, not the agent's (§2.4)."""
        recorder = _recorder(worktree=str(tmp_path))
        record = recorder.build(
            answer="",
            verifier_command="pytest -q",
            verifier_output="2 failed [exit 1]",
            exception="OllamaNotReachableError: connection refused",
        )
        assert record["failure"]["class"] == "engine_degraded"
        assert record["failure"]["evidence"]["engine_error"] == "OllamaNotReachableError"

    async def test_given_verifier_when_recorded_then_exit_marker_drives_solved(self, tmp_path):
        """Given: a verifier that reports a passing run
        Then: solved true, its tail bounded with the digest of the full text"""
        output = "18 passed in 4.21s\n" + ("detail line\n" * 50)
        record = _recorder(worktree=str(tmp_path)).build(
            answer="ok", verifier_command="pytest -q", verifier_output=output, turns=3,
        )
        assert record["outcome"]["solved"] is True
        assert record["outcome"]["verifier"]["exit_code"] is None
        assert record["outcome"]["verifier"]["turns"] == 3
        assert record["outcome"]["verifier"]["tail"] == output
        assert record["outcome"]["verifier"]["tail_truncated"] is False


class TestClassificationIsEvidenceBased:
    """§2.4: the class names the signal it came from; an exit code alone decides nothing."""

    def test_solved_run_has_no_failure_class(self):
        assert classify_failure(
            solved=True, diff_present=True, answer="ok", rounds=3, cap=25, verifier_exit=0,
        )[0] is None

    def test_runner_exception_is_harness_error(self):
        kind, _ = classify_failure(
            solved=False, diff_present=True, answer="", rounds=1, cap=25, verifier_exit=1,
            runner_error="KeyError: 'usage'",
        )
        assert kind == "harness_error"

    def test_budget_note_in_the_answer_is_stalled(self):
        from core.chat import _budget_exhausted_note

        note = _budget_exhausted_note(25)
        kind, evidence = classify_failure(
            solved=False, diff_present=True, answer=f"work in progress\n\n{note}",
            rounds=25, cap=25, verifier_exit=1,
        )
        assert kind == "stalled"
        assert evidence["stalled_by_budget"] is True

    def test_lost_context_is_unreachable_without_the_compaction_event(self):
        """The verdict requires the event, never a guess (§2.4) — so a failing run that
        never showed a compaction event cannot be filed as lost context."""
        kind, evidence = classify_failure(
            solved=False, diff_present=True, answer="alle Tests grün", rounds=30, cap=25,
            verifier_exit=1, compaction_fired=None, needed_fact_predates=True,
        )
        assert kind != "lost_context"
        assert evidence["compaction_fired"] is None
        both = classify_failure(
            solved=False, diff_present=True, answer="x", rounds=1, cap=25, verifier_exit=1,
            compaction_fired=True, needed_fact_predates=True,
        )
        assert both[0] == "lost_context"

    def test_empty_diff_in_a_git_tree_is_refused_not_wrong_code(self):
        kind, _ = classify_failure(
            solved=False, diff_present=False, answer="", rounds=2, cap=25, verifier_exit=1,
        )
        assert kind == "refused"

    def test_success_claim_while_the_verifier_fails_is_false_claim(self):
        kind, evidence = classify_failure(
            solved=False, diff_present=True, answer="Done — all tests pass.",
            rounds=2, cap=25, verifier_exit=1,
        )
        assert kind == "false_claim"
        assert evidence["success_claim"] is True
        assert kind in FAILURE_CLASSES


class TestCliMachineMode:
    """B1's surface: `--json` on the two coding entry points, `--run-record` as a file."""

    @pytest.fixture
    def pinned_worktree(self, tmp_path, monkeypatch):
        """Pin the recorded worktree to the test folder.

        Without this the CLI path resolves the real Ephe workspace, so the record
        would carry the developer's working copy (and, on a busy tree, a few hundred
        kilobytes of it) into a test assertion that is about the schema.
        """
        import core.run_evidence as evidence

        monkeypatch.setattr(evidence, "active_worktree", lambda: str(tmp_path / "ws"))
        (tmp_path / "ws").mkdir()
        return tmp_path

    def test_given_code_json_when_cmd_code_runs_then_stdout_is_exactly_one_object(
        self, chosen_engine, pinned_worktree, monkeypatch, capsys, tmp_path
    ):
        """Then: stdout parses as one record, the loop got the turn id and the phase
        callback, and the progress line moved to stderr."""
        import core.react

        seen: dict = {}

        async def _fake_loop(**kwargs):
            seen.update(kwargs)
            kwargs["on_phase"]("Tool round 1…")
            kwargs["on_phase"]("Processing results…")
            return "Edited the file and ran the tests."

        monkeypatch.setattr(core.react, "react_loop", _fake_loop)
        rc = ephe_cli.cmd_code(argparse.Namespace(
            task=["fix", "the", "test"], model=None, json=True, rep=2, verify=None,
            run_record=str(tmp_path / "runs" / "code.json"),
        ))
        captured = capsys.readouterr()

        assert rc == 0
        record = json.loads(captured.out)          # any stray print on stdout raises here
        assert captured.out.strip().startswith("{")
        assert captured.out.strip().endswith("}")
        assert key_shape(record) == EXPECTED_SHAPE
        assert record["entrypoint"] == "code"
        assert record["identity"]["task"] == "fix the test"
        assert record["determinism"]["rep"] == 2
        assert record["effort"]["tool_rounds"] == 1
        assert seen["turn_id"] == record["run_id"], "the audit filter must be the loop's turn id"
        assert callable(seen["on_phase"])
        assert "◑ ephe code: fix the test" in captured.err
        assert "◑ ephe code" not in captured.out
        assert load_record(tmp_path / "runs" / "code.json") == record

    def test_given_default_flags_when_cmd_code_runs_then_human_output_is_unchanged(
        self, chosen_engine, monkeypatch, capsys
    ):
        """The prose path stays byte-identical: same two lines on stdout, nothing on stderr."""
        import core.react

        async def _fake_loop(**kwargs):
            return "Test läuft grün, Datei geändert."

        monkeypatch.setattr(core.react, "react_loop", _fake_loop)
        rc = ephe_cli.cmd_code(argparse.Namespace(task=["fix", "the", "test"], model=None))
        captured = capsys.readouterr()

        assert rc == 0
        assert captured.out == "◑ ephe code: fix the test\nTest läuft grün, Datei geändert.\n"
        assert captured.err == ""

    def test_given_goal_json_when_run_then_the_check_command_is_the_verifier(
        self, chosen_engine, pinned_worktree, monkeypatch, capsys
    ):
        """GoalRunner's check command is §2.2's verifier: its verdict, exit marker and
        bounded output land in the record, and a false claim is named as one."""

        class FakeRunner:
            def __init__(self, **kw):
                self.kw = kw

            async def run(self, goal):
                from core.goal_loop import GoalResult

                self.kw["on_phase"]("Tool round 4…")
                return GoalResult(
                    goal=goal, success=False, turns=4,
                    check_output="1 failed in 0.9s\n[exit 1]", answer="alle Tests grün",
                )

        monkeypatch.setattr(ephe_cli, "GoalRunner", FakeRunner)
        rc = ephe_cli.cmd_goal(argparse.Namespace(
            goal_task=["mache", "die", "tests", "gruen"], check="pytest -q", max_turns=4,
            model=None, json=True, rep=0, run_record=None,
        ))
        captured = capsys.readouterr()

        assert rc == 1
        record = json.loads(captured.out)
        assert key_shape(record) == EXPECTED_SHAPE
        assert record["entrypoint"] == "goal"
        assert record["outcome"]["solved"] is False
        assert record["outcome"]["solved_basis"] == "verifier"
        assert record["outcome"]["verifier"]["command"] == "pytest -q"
        assert record["outcome"]["verifier"]["exit_code"] == 1
        assert record["outcome"]["verifier"]["turns"] == 4
        assert record["effort"]["tool_rounds"] == 4
        assert record["effort"]["budget_cap"] >= record["effort"]["tool_rounds"]
        assert record["failure"]["class"] == "false_claim"
        assert "GOAL FAILED" in captured.err

    def test_given_goal_record_path_when_run_then_file_matches_stdout(
        self, chosen_engine, pinned_worktree, monkeypatch, capsys, tmp_path
    ):
        class FakeRunner:
            def __init__(self, **kw):
                pass

            async def run(self, goal):
                from core.goal_loop import GoalResult

                return GoalResult(goal=goal, success=True, turns=1,
                                  check_output="all tests pass\n[exit 0]", answer="ok")

        target = tmp_path / "goal-run.json"
        monkeypatch.setattr(ephe_cli, "GoalRunner", FakeRunner)
        rc = ephe_cli.cmd_goal(argparse.Namespace(
            goal_task=["ziel"], check="pytest -q", max_turns=2, model=None,
            json=False, rep=1, run_record=str(target),
        ))
        captured = capsys.readouterr()

        assert rc == 0
        assert captured.out.startswith("GOAL OK after 1 turn(s)"), "human path keeps its lines"
        record = load_record(target)
        assert record["outcome"]["solved"] is True
        assert record["failure"]["class"] is None
        assert record["determinism"]["grouping_key"]

    def test_given_code_verify_when_run_then_the_verifier_decides_solved(
        self, chosen_engine, pinned_worktree, monkeypatch, capsys
    ):
        """`--verify` gives `code` the verifier §2.2 asks for: it runs on the goal
        loop's own gated tool path, its decision lands in the record, and `solved`
        follows the verifier's output instead of the agent's text."""
        import core.react

        async def _fake_loop(**kwargs):
            # What chat_with_tools does for a real turn: the id every audit line of
            # this run is filtered by.
            from core.artifact_workbench import set_artifact_turn

            set_artifact_turn(kwargs["turn_id"])
            return "Edited it."

        monkeypatch.setattr(core.react, "react_loop", _fake_loop)
        rc = ephe_cli.cmd_code(argparse.Namespace(
            task=["fix"], model=None, json=True, rep=0, verify="echo verified", run_record=None,
        ))
        record = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert record["outcome"]["solved"] is True
        assert record["outcome"]["solved_basis"] == "verifier"
        assert record["outcome"]["verifier"]["command"] == "echo verified"
        assert record["outcome"]["verifier"]["tail"] == "verified"
        verifier_event = record["effort"]["tool_events"][-1]
        assert verifier_event["tool"] == "run_shell"
        assert verifier_event["approval_consulted"] is True
        assert verifier_event["approval_decision"] == "approved"

    def test_given_fail_closed_engine_when_code_json_then_no_record_and_no_run(
        self, empty_ephe_home, monkeypatch, capsys
    ):
        """No engine chosen, no run — so no run record either. The CLI's existing
        machine-readable error object stays the only thing on stdout, and it still
        points at `ephe configure`."""
        import core.react

        async def _never(**kwargs):  # pragma: no cover — the abort happens first
            raise AssertionError("a run without a chosen engine is not a run")

        monkeypatch.setattr(core.react, "react_loop", _never)
        with pytest.raises(SystemExit) as excinfo:
            ephe_cli.cmd_code(argparse.Namespace(
                task=["x"], model=None, json=True, rep=0, verify=None, run_record=None))

        assert excinfo.value.code == 1
        payload = json.loads(capsys.readouterr().out)
        assert set(payload) == {"error"}
        assert "ephe configure" in payload["error"]["fix"]


class TestTruncationIsProvable:
    """A bounded field is only honest with the digest of the whole value next to it."""

    def test_given_long_diff_when_recorded_then_digest_is_of_the_full_text(
        self, tmp_path, monkeypatch
    ):
        whole = "diff --git a/x.py b/x.py\n" + ("+print(1)\n" * 4000)
        assert len(whole) > DIFF_LIMIT
        monkeypatch.setattr(run_evidence, "worktree_diff", lambda _ws: whole)
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")

        artifact = record["artifact"]
        assert artifact["diff_truncated"] is True
        assert len(artifact["diff"]) == DIFF_LIMIT
        assert artifact["diff_sha256"] == sha256_hex(whole)
        # The detectability itself: the kept text does not hash to the recorded digest.
        assert sha256_hex(artifact["diff"]) != artifact["diff_sha256"]
        assert artifact["diff_bytes"] == len(whole.encode("utf-8"))

        path = write_record(record, tmp_path / "run.json")
        assert load_record(path) == record

    def test_given_truncated_value_claimed_complete_when_validated_then_it_fails(self, tmp_path):
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")
        record["artifact"]["diff"] = "half a diff\n"
        record["artifact"]["diff_sha256"] = sha256_hex("a different diff\n")
        record["artifact"]["diff_truncated"] = False

        with pytest.raises(RunRecordError, match="truncation flag"):
            validate_record(record)

    def test_given_absent_diff_when_validated_then_no_digest_is_allowed(self, tmp_path):
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")
        assert record["artifact"]["diff"] is None
        record["artifact"]["diff_sha256"] = sha256_hex("invented")

        with pytest.raises(RunRecordError, match="an absent value carries no digest"):
            validate_record(record)


class TestSchemaGate:
    """Versioned, whitelisted, loud: the same policy shape as the ratchet baselines."""

    def test_a_fresh_record_validates_and_round_trips(self, tmp_path):
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")
        assert validate_record(record) is record
        assert json.loads(json.dumps(record)) == record

    def test_unknown_key_is_refused(self, tmp_path):
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")
        record["outcome"]["solved_by_hope"] = True

        with pytest.raises(RunRecordError, match="unknown key"):
            validate_record(record)

    def test_missing_key_is_refused(self, tmp_path):
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")
        del record["run_id"]

        with pytest.raises(RunRecordError, match="missing key"):
            validate_record(record)

    def test_foreign_schema_version_is_refused(self, tmp_path):
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")
        record["schema"] = SCHEMA + 1

        with pytest.raises(RunRecordError, match="this reader speaks"):
            validate_record(record)

    def test_failure_class_must_be_a_taxonomy_value(self, tmp_path):
        record = _recorder(worktree=str(tmp_path)).build(answer="ok")
        record["failure"]["class"] = "agent_was_tired"

        with pytest.raises(RunRecordError, match="taxonomy value"):
            validate_record(record)

    def test_engine_endpoint_is_never_written_in_clear_text(self, tmp_path):
        """The URL is the user's, so the record keeps a kind and a digest only (§3.4.1)."""
        url = "http://127.0.0.1:8000/v1"
        record = _recorder(worktree=str(tmp_path), api_url=url).build(answer="ok")
        body = json.dumps(record)

        assert "8000/v1" not in body
        assert record["identity"]["engine"]["endpoint"]["kind"] == "openai_compatible"
        assert record["identity"]["engine"]["endpoint"]["is_loopback"] is True
        assert len(record["identity"]["engine"]["endpoint"]["url_hash"]) == 16

    def test_repetitions_group_by_key_and_not_by_rep(self, tmp_path):
        first = _recorder(worktree=str(tmp_path), rep=0).build(answer="ok")
        second = _recorder(worktree=str(tmp_path), rep=1).build(answer="ok")

        assert first["determinism"]["grouping_key"] == second["determinism"]["grouping_key"]
        assert first["determinism"]["rep"] != second["determinism"]["rep"]

    def test_unknown_entrypoint_or_posture_is_refused_at_construction(self, tmp_path):
        with pytest.raises(RunRecordError, match="entrypoint"):
            _recorder("chat", worktree=str(tmp_path))
        with pytest.raises(RunRecordError, match="posture"):
            _recorder(worktree=str(tmp_path), gate_posture="whatever")
