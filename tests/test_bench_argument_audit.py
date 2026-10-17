"""The bench scores arguments, not just call counts — and it is proven to catch a lie.

`tool_calls: ["write_file", "read_file", ...]` says a call happened. It cannot tell
the file the task named from a file that never existed, so a rep could go green on a
wrong path. These tests pin the four classes the stream can check without rewriting a
task and without a judge: the `write_file` target, the `read_file`/`delete_file`
target, the `run_shell` prefix, and the `edit_file` pattern. The verdict axis is not
touched: `arg_audit` records findings next to `ok`, it does not set it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _bench(monkeypatch, tmp_path):
    """The harness module, pointed at a scratch workspace and no server."""
    monkeypatch.setenv("EPHE_BENCH_MODEL", "test-model")
    monkeypatch.setenv("EPHE_BENCH_BASE", "http://127.0.0.1:1")
    name = f"_bench_audit_{abs(hash(str(tmp_path)))}"
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_option_b.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.WORKSPACE = tmp_path / "ws"
    module.RUNS = tmp_path / "runs"
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    (module.WORKSPACE / "todos_seed.json").write_text('{"items": []}', encoding="utf-8")
    (module.WORKSPACE / "policy.md").write_text("# policy\n", encoding="utf-8")
    return module


def _frames(calls):
    events = []
    for i, (tool, args, result) in enumerate(calls):
        cid = f"c{i}"
        events.append({"type": "tool_start", "tool": tool, "call_id": cid, "args": args})
        events.append({"type": "tool_done", "tool": tool, "call_id": cid,
                       "result": result, "duration_ms": 12.0})
    return events


def _codes(audit: dict) -> list[str]:
    return [v["code"] for v in audit["violations"]]


def test_green_rep_with_a_wrong_read_target_is_flagged(monkeypatch, tmp_path):
    # Given a W1 rep whose endstate is correct (so today's assertion says PASS) but
    # whose final read points at a name that is not in the workspace
    bench = _bench(monkeypatch, tmp_path)
    (bench.WORKSPACE / "todos.json").write_text(
        json.dumps({"items": [{"title": "keep me", "done": False}]}), encoding="utf-8")
    task = next(t for t in bench.TASKS if t.id == "W1")
    frames = _frames([
        ("read_file", {"path": "todos_seed.json"}, "ok"),
        ("write_file", {"path": "todos.json", "content": "{\"items\": []}"}, "written"),
        ("edit_file", {"path": "todos.json", "old_string": "[]", "new_string": "[{}]"}, "edited"),
        ("read_file", {"path": "to-do.json"},
         "[tool-error 'read_file': File not found: 'to-do.json']"),
    ])
    bench.stream_turn_retry = lambda *a, **k: ("FINAL ANSWER: done", frames, 900.0,
                                               {"prompt_tokens": 900, "completion_tokens": 40})
    # When the rep is recorded
    manifest = bench.run_task(task, 1)
    # Then the verdict is green and the argument axis is not: four calls, one wrong
    assert manifest["ok"] is True
    assert len(manifest["tool_calls"]) == 4
    audit = manifest["arg_audit"]
    assert audit["calls"] == 4
    assert "unknown_target_file" in _codes(audit)
    assert "tool_result_error" in _codes(audit)
    bad = [v for v in audit["violations"] if v["code"] == "unknown_target_file"][0]
    assert bad["arg"] == "to-do.json"


def test_write_outside_the_workspace_and_missing_argument_are_violations(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    audit = bench.arg_audit(task, _frames([
        ("write_file", {"path": "/Users/someone/notes.md", "content": "x"}, "written"),
        ("write_file", {"path": "todos.json"}, "[tool-error 'write_file': content missing]"),
    ]), bench.WORKSPACE, ["todos_seed.json", "policy.md"])
    codes = _codes(audit)
    assert "path_outside_workspace" in codes
    assert "missing_arg:content" in codes


def test_shell_prefix_and_system_paths_are_separated(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    root = str(bench.WORKSPACE.resolve())
    audit = bench.arg_audit(task, _frames([
        ("run_shell", {"command": f"wc -l {root}/todos_seed.json 2>/dev/null"}, "3 lines"),
        ("run_shell", {"command": "curl http://127.0.0.1/x"}, "ok"),
        ("run_shell", {"command": "cat /etc/passwd"}, "ok"),
    ]), bench.WORKSPACE, [])
    codes = _codes(audit)
    shells = [o["arg"] for o in audit["observations"] if o["code"] == "shell_prefix"]
    assert shells == ["wc", "curl", "cat"]
    assert "shell_denied_prefix" in codes            # curl
    assert codes.count("path_outside_workspace") == 1  # /etc/passwd, but not /dev/null
    assert audit["classes"]["shell_prefix"] == 3


def test_edit_that_changes_nothing_and_a_clipped_argument(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    clipped = "x" * 300 + bench._CLIP
    audit = bench.arg_audit(task, _frames([
        ("edit_file", {"path": "policy.md", "old_string": "# policy", "new_string": "# policy"}, "ok"),
        ("read_file", {"path": clipped}, "ok"),
    ]), bench.WORKSPACE, ["policy.md", "todos_seed.json"])
    assert "edit_no_change" in _codes(audit)
    assert {"code": "arg_truncated:path", "tool": "read_file"} in audit["observations"]
    # a clipped argument is recorded as a gap in the ledger; only mechanical contract
    # breaks reach `violations`
    assert "unknown_target_file" not in _codes(audit)


def test_result_axis_names_its_source(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    audit = bench.arg_audit(task, _frames([
        ("read_file", {"path": "policy.md"}, "contents here"),
    ]), bench.WORKSPACE, ["policy.md"])
    assert audit["result_axis"] == "core.quality"
    assert _codes(audit) == []


def test_gaia_gets_a_provenance_ledger_and_the_others_do_not(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    frames = _frames([
        ("read_file", {"path": "g1_a.txt"}, "total_capacity = 84 seats"),
        ("web_search", {"query": "remaining seats 84 12"}, "see https://example.org/a (2026)"),
    ])
    ledger = bench.retrieval_ledger(frames, "FINAL ANSWER: 72", "Read g1_a.txt and g1_b.txt in 2026")
    assert ledger["provenance"] == "retrieved"
    assert ledger["web_calls"] == 1
    assert ledger["hosts"] == ["example.org"]
    assert ledger["source_dates"] == ["2026"]
    closed = bench.retrieval_ledger(frames[:2], "FINAL ANSWER: 72", "Read g1_a.txt")
    assert closed["provenance"] == "closed-book"
    assert closed["web_calls"] == 0

    task = next(t for t in bench.TASKS if t.id == "G1")
    (bench.WORKSPACE / "g1_a.txt").write_text("total = 84\n", encoding="utf-8")
    (bench.WORKSPACE / "g1_b.txt").write_text("reserved = 12\n", encoding="utf-8")
    bench.stream_turn_retry = lambda *a, **k: ("FINAL ANSWER: 72", frames, 800.0,
                                               {"prompt_tokens": 500, "completion_tokens": 20})
    gaia = bench.run_task(task, 1)
    assert gaia["ok"] is True
    assert gaia["retrieval"]["provenance"] == "retrieved"
    other = bench.run_task(next(t for t in bench.TASKS if t.id == "T1"), 1)
    assert "retrieval" not in other


def test_the_audit_never_moves_the_verdict(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    frames = _frames([("read_file", {"path": "nowhere.json"}, "ok")])
    bench.stream_turn_retry = lambda *a, **k: ("FINAL ANSWER: done", frames, 800.0,
                                               {"prompt_tokens": 10, "completion_tokens": 5})
    no_endstate = bench.run_task(task, 1)          # todos.json absent -> check fails
    (bench.WORKSPACE / "todos.json").write_text(
        json.dumps({"items": [{"title": "keep me"}]}), encoding="utf-8")
    with_endstate = bench.run_task(task, 1)
    assert no_endstate["ok"] is False and with_endstate["ok"] is True
    assert _codes(no_endstate["arg_audit"]) == _codes(with_endstate["arg_audit"])


def test_scorecard_prints_the_argument_axis(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    rep = {"task_id": "W1", "family": "endstate", "rep": 1, "ok": True, "note": "ok",
           "error_class": None, "wall_ms": 9000.0, "tool_calls": ["read_file"],
           "arg_audit": {"calls": 4, "violation_counts": {"unknown_target_file": 1}}}
    text = bench.score([rep])
    assert "W1 (endstate): pass^3=FAIL (1/1 reps)" in text
    assert "calls=4  violations={" in text
    assert '"unknown_target_file": 1' in text


def test_audit_survives_a_stream_without_tool_start_frames(monkeypatch, tmp_path):
    # Done frames with no start frame mean the arguments never arrived; the ledger says
    # so instead of auditing a call list that is silently shorter than the run.
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    events = [{"type": "tool_done", "tool": "write_file", "call_id": "z", "result": "written"}]
    audit = bench.arg_audit(task, events, bench.WORKSPACE, [])
    assert audit["calls"] == 0
    assert {"code": "stream_without_tool_start"} in audit["observations"]


def test_each_call_carries_a_digest_of_its_arguments(monkeypatch, tmp_path):
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    audit = bench.arg_audit(task, _frames([
        ("write_file", {"path": "todos.json", "content": "A"}, "written"),
        ("write_file", {"path": "todos.json", "content": "B"}, "written"),
        ("read_file", {"path": "policy.md"}, "ok"),
    ]), bench.WORKSPACE, ["policy.md"])
    digests = [c["digest"] for c in audit["ledger"]]
    assert len(digests) == 3 and len(set(digests)) == 3
    assert [c["tool"] for c in audit["ledger"]] == ["write_file", "write_file", "read_file"]
    assert audit["ledger"][2]["target"] == "policy.md"
    same = bench.arg_audit(task, _frames([("read_file", {"path": "policy.md"}, "ok")]),
                           bench.WORKSPACE, ["policy.md"])
    assert same["ledger"][0]["digest"] == digests[2]


def _gaia_bench(monkeypatch, tmp_path, fetched_result):
    bench = _bench(monkeypatch, tmp_path)
    (bench.WORKSPACE / "g1_a.txt").write_text("total_capacity = 84 seats\n", encoding="utf-8")
    (bench.WORKSPACE / "g1_b.txt").write_text("reserved = 12 seats\n", encoding="utf-8")
    frames = _frames([
        ("read_file", {"path": "g1_a.txt"}, "84 seats"),
        ("web_search", {"query": "capacity remaining"}, fetched_result),
    ])
    bench.stream_turn_retry = lambda *a, **k: ("FINAL ANSWER: 72", frames, 800.0,
                                               {"prompt_tokens": 400, "completion_tokens": 20})
    return bench, bench.run_task(next(t for t in bench.TASKS if t.id == "G1"), 1)


def test_a_fetched_answer_is_recorded_as_a_leak(monkeypatch, tmp_path):
    # Given a gaia rep whose web result contains the expected number
    bench, man = _gaia_bench(monkeypatch, tmp_path,
                             "https://github.com/some/benchmark says the answer is 72 seats")
    led = man["retrieval"]
    assert man["note"] == "final-answer==72"
    assert led["answer_leak"] is True
    assert led["benchmark_host_hits"] == ["github.com"]
    assert led["provenance"] == "retrieved"


def test_an_unrelated_fetch_is_not_called_a_leak(monkeypatch, tmp_path):
    bench, man = _gaia_bench(monkeypatch, tmp_path,
                             "https://example.org/venue notes 101 seats, built in 1728")
    led = man["retrieval"]
    assert led["answer_leak"] is False
    assert led["benchmark_host_hits"] == []
    # the shared `FINAL ANSWER:` wording is not task evidence, so it must not flag
    assert led["question_leak"] == []


def test_the_task_instruction_in_a_fetched_page_is_a_question_leak(monkeypatch, tmp_path):
    bench, man = _gaia_bench(
        monkeypatch, tmp_path,
        "https://arxiv.org/abs/x the prompt reads: Compute how many seats remain (capacity "
        "minus reserved) and report it")
    leaks = man["retrieval"]["question_leak"]
    assert leaks, "a copied instruction must be visible"
    assert any("capacity minus" in s for s in leaks)
    assert man["retrieval"]["benchmark_host_hits"] == ["arxiv.org"]


def test_a_reused_call_id_binds_each_start_to_the_done_that_follows_it(monkeypatch, tmp_path):
    # Given two rounds that reuse the same call ids — `_call_id` numbers calls by the
    # per-round enumerate index (core/chat_detect.py:337), so round 2 hits `-0`/`-1`
    # again — with the error result in round 2 only
    bench = _bench(monkeypatch, tmp_path)
    task = next(t for t in bench.TASKS if t.id == "W1")
    ok = "contents of the round-1 file"
    error = "[tool-error 'read_file': File not found: 'kdoc_003.json']"
    events = [
        {"type": "tool_start", "tool": "read_file", "call_id": "t1-0",
         "args": {"path": "round1_0.json"}},
        {"type": "tool_start", "tool": "read_file", "call_id": "t1-1",
         "args": {"path": "round1_1.json"}},
        {"type": "tool_done", "tool": "read_file", "call_id": "t1-0", "result": ok},
        {"type": "tool_done", "tool": "read_file", "call_id": "t1-1", "result": ok},
        {"type": "tool_start", "tool": "read_file", "call_id": "t1-0",
         "args": {"path": "round2_0.json"}},
        {"type": "tool_done", "tool": "read_file", "call_id": "t1-0", "result": error},
        {"type": "tool_start", "tool": "read_file", "call_id": "t1-1",
         "args": {"path": "round2_1.json"}},
        {"type": "tool_done", "tool": "read_file", "call_id": "t1-1", "result": ok},
    ]
    # When the audit joins the stream
    audit = bench.arg_audit(task, events, bench.WORKSPACE, [])
    flagged = [v["arg"] for v in audit["violations"] if v["code"] == "tool_result_error"]
    # Then round 1 is clean and only round 2's error call is flagged: a last-write-wins
    # dict would bind round 1's `-0` start to round 2's error result and flag it here
    assert "round1_0.json" not in flagged
    assert "round1_1.json" not in flagged
    assert flagged == ["round2_0.json"]


def test_k5_passes_only_when_the_rep_wrote_the_file_itself(monkeypatch, tmp_path):
    # Given a k5_out.json left on disk by an earlier rep
    bench = _bench(monkeypatch, tmp_path)
    (bench.WORKSPACE / "k5_out.json").write_text(
        json.dumps({"sum": 1210}), encoding="utf-8")
    reads_only = [
        {"type": "tool_start", "tool": "read_file", "call_id": "t1-0",
         "args": {"path": "kdoc_001.json"}},
        {"type": "tool_done", "tool": "read_file", "call_id": "t1-0", "result": "ok"},
    ]
    wrote = [
        {"type": "tool_start", "tool": "write_file", "call_id": "t1-0",
         "args": {"path": "k5_out.json", "content": "{\"sum\": 1210}"}},
        {"type": "tool_done", "tool": "write_file", "call_id": "t1-0",
         "result": "written k5_out.json"},
    ]
    # When a rep that only read is checked against the inherited file
    inherited_ok, inherited_note = bench.k5_check(bench.Ctx("FINAL ANSWER: done", reads_only, 0.0))
    # Then it fails for the missing write, even though the file is present and correct
    assert inherited_ok is False
    assert inherited_note == "k5_out.json not written by this rep"
    # And a rep that wrote the file itself passes on the existing sum test
    wrote_ok, wrote_note = bench.k5_check(bench.Ctx("FINAL ANSWER: done", wrote, 0.0))
    assert wrote_ok is True
    assert wrote_note == "sum=1210"


def test_the_per_rep_reset_removes_k5_out_json(monkeypatch, tmp_path):
    # A rep must not inherit an earlier rep's end-state file: the reset block has to
    # unlink k5_out.json at the start of every K5 rep.
    source = (REPO / "evals" / "bench_option_b.py").read_text(encoding="utf-8")
    assert 'if task.id == "K5":' in source
    assert '(WORKSPACE / "k5_out.json").unlink(missing_ok=True)' in source
