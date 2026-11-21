"""Tests for the live half of the creation eval (task #51e).

`evals/creation_run.py` spends an engine: it boots a server, posts each case's turn, and
hands the result to `evals.creation_transcript` and `evals.creation_runner`. These tests
prove the decisions it makes around that spend, without a server and without a key:

* a case is run as the turn its own line describes, or the run refuses it;
* a turn that never answered is recorded as a broken run, and a broken run is not a
  verdict on the case;
* the server is asked which engine it is actually talking to before 24 turns are spent on
  the assumption that it is the one named on the command line;
* the server is booted with a command the child can run: it lives in the run's own folder,
  so the script has to be named by a path that resolves from there;
* the key that pays for the run reaches the child's environment and no artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from evals.creation_run import (
    CasePlan,
    HealthMismatch,
    plan_case,
    run_record,
    verify_health,
)

CASE = {
    "id": "creation-02",
    "category": "widget",
    "input": "Make a world clock with Berlin, Lima and Tokyo.",
    "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]},
    "checks": ["manifest_valid"],
    "mode": "creator",
    "privileges": ["files"],
    "tools": ["create_plugin_scaffold", "write_plugin_source", "verify_plugin_bundle"],
}


# what a case turns into


def test_a_creator_case_becomes_the_turn_its_own_line_describes():
    plan = plan_case(CASE, nonce="r1")
    assert isinstance(plan, CasePlan)
    assert plan.session_id.startswith("creation-02-r1")
    assert plan.mode == "creator"
    assert plan.privileges == ["files"]
    assert plan.message == CASE["input"]


def test_a_session_id_is_unique_per_run_so_two_runs_never_share_state():
    assert plan_case(CASE, nonce="r1").session_id != plan_case(CASE, nonce="r2").session_id


def test_a_case_that_is_not_a_creator_turn_is_refused_rather_than_run_as_one():
    """Without the mode the engine is graded in a mode it was never in (rubric, §the turn)."""
    with pytest.raises(ValueError, match="mode"):
        plan_case({**CASE, "mode": "operator"}, nonce="r1")


def test_a_privilege_the_guard_does_not_know_is_refused():
    with pytest.raises(ValueError, match="privilege"):
        plan_case({**CASE, "privileges": ["files", "everything"]}, nonce="r1")


def test_a_case_with_no_input_is_refused():
    with pytest.raises(ValueError, match="input"):
        plan_case({k: v for k, v in CASE.items() if k != "input"}, nonce="r1")


# the server's engine, asked before the spend


def test_health_that_names_the_requested_engine_passes():
    health = {"active_provider": "openai_compatible", "active_model": "deepseek-test"}
    assert verify_health(health, model="deepseek-test", base_url="https://example.test/v1") == health


def test_health_that_names_another_model_raises_and_says_what_it_read():
    health = {"active_provider": "local_ollama", "active_model": "qwen3:8b"}
    with pytest.raises(HealthMismatch) as caught:
        verify_health(health, model="deepseek-test", base_url="https://example.test/v1")
    assert "qwen3:8b" in str(caught.value)
    assert "deepseek-test" in str(caught.value)


def test_a_health_answer_that_carries_no_model_raises_instead_of_passing():
    """A field the route stopped answering is not evidence that the engine is right."""
    with pytest.raises(HealthMismatch):
        verify_health({"status": "ok"}, model="deepseek-test", base_url="https://example.test/v1")


# what a run records


def _events() -> list[dict]:
    return [
        {"type": "tool_start", "tool": "tool_call", "call_id": "c1",
         "args": {"name": "create_plugin_scaffold", "arguments": "{}"}},
        {"type": "tool_done", "tool": "tool_call", "call_id": "c1", "status": "completed",
         "result": json.dumps({"bundle": "world-clock"})},
        {"type": "chunk", "data": "Built it. "},
        {"type": "chunk", "data": "Pick your cities."},
    ]


def test_a_turn_that_answered_is_recorded_with_its_tools_and_its_staged_bundles():
    record = run_record(CASE, _events(), staged=["world-clock"], engine_error="")
    assert record["case_id"] == "creation-02"
    assert record["tools"] == ["create_plugin_scaffold"]
    assert record["staged"] == ["world-clock"]
    assert record["answer_len"] == len("Built it. Pick your cities.")
    assert record["usable"] is True


def test_a_turn_that_never_answered_is_a_broken_run_and_not_a_verdict():
    """An engine that dies mid-turn says nothing about whether the case passes."""
    record = run_record(
        CASE, [{"type": "error", "msg": "engine timeout"}], staged=[], engine_error="engine timeout"
    )
    assert record["usable"] is False
    assert record["error"] == "engine timeout"


def test_an_empty_answer_with_no_tool_frame_is_a_broken_run():
    record = run_record(CASE, [], staged=[], engine_error="")
    assert record["usable"] is False


def test_the_record_holds_no_engine_key(tmp_path):
    """The key pays for the run and stays out of every artifact it writes.

    The redaction is the product's own (`core.redact`), because the field that leaks is the
    one the engine answers back: an HTTP error quoting the Authorization header.
    """
    secret = "sk-" + "b" * 32
    events = _events() + [{"type": "tool_done", "tool": "read_file", "call_id": "c2",
                           "status": "failed", "result": f"auth failed for {secret}"}]
    record = run_record(CASE, events, staged=[], engine_error=f"401 with key {secret}")
    body = json.dumps(record)
    assert secret not in body
    assert record["error"] != f"401 with key {secret}"


def test_the_tools_the_record_names_are_the_tools_the_transcript_carries():
    """One source answers "what ran", so the receipt and the graded transcript agree."""
    from evals.creation_transcript import build_transcript

    events = _events()
    record = run_record(CASE, events, staged=[], engine_error="")
    transcript = build_transcript(events)
    assert record["tools"] == ["create_plugin_scaffold"]
    for name in record["tools"]:
        assert f"[tool {name}]" in transcript


class _Spawned:
    """The child the driver asked for, recorded instead of started."""

    def __init__(self, seen: list, argv: list[str], kwargs: dict) -> None:
        self.argv = list(argv)
        self.kwargs = kwargs
        seen.append(self)

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        pass

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        pass


def test_the_server_script_is_named_by_a_path_the_child_can_resolve(tmp_path, monkeypatch):
    """A bare script name only resolves inside the checkout, and the child lives elsewhere.

    `boot_server` moves the cwd outside the lane on purpose: `get_workspace_dir()` follows
    the cwd, and the fallback it reaches while the cwd sits in a config root is a folder the
    read tools refuse. The interpreter therefore has to be handed `run_server.py` by a path
    that resolves from anywhere - a relative name makes python leave the process with 2
    before the health endpoint is ever tried, and the run pays for nothing.
    """
    from evals import creation_run

    seen: list[_Spawned] = []
    monkeypatch.setattr(
        creation_run.subprocess,
        "Popen",
        lambda argv, **kwargs: _Spawned(seen, argv, kwargs),
    )
    work = tmp_path / "run" / "work"
    log = tmp_path / "run" / "server.log"
    log.parent.mkdir(parents=True)

    proc = creation_run.boot_server({"PATH": "/usr/bin"}, 8795, work, log)

    assert work.is_dir(), "the child is asked for a folder that was never made"
    assert Path(proc.kwargs["cwd"]) == work
    script = Path(proc.argv[1])
    assert script.is_absolute(), f"{script} only resolves from the checkout"
    assert script.is_file()
    assert proc.argv[:1] == [creation_run.env_python()]


def test_the_grading_command_names_the_run_scoped_home(tmp_path, capsys, monkeypatch):
    """#161: the printer hands the grader the same home the run built its mounts in.

    A grading command without `--config` is refused by the runner (#161), so a printed
    command that omits it sends the operator into a refusal after paying for 24 turns.
    """
    from evals import creation_run

    printed: list[str] = []

    def fake_main_body(*args, **kwargs):  # pragma: no cover - not reached
        return 0

    monkeypatch.setattr(creation_run, "boot_server", lambda *a, **k: None, raising=False)
    # Render only the line under test through its own function, so the test does not pay
    # a server: build the same string the run prints.
    line = creation_run.grading_command(tmp_path, tmp_path / "cases.jsonl")
    assert "--config" in line
    assert str(tmp_path / "config") in line
    assert "--browser" in line


def test_the_endpoint_must_list_the_model_the_run_pays_for():
    """The health echo cannot prove the provider serves the tag; its /models can."""
    import http.server
    import threading

    from evals.creation_run import HealthMismatch, verify_endpoint_model

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802  the stdlib spells it this way
            body = b'{"data": [{"id": "served-model"}]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        assert verify_endpoint_model(base, model="served-model", key="k") == "served-model"
        with pytest.raises(HealthMismatch):
            verify_endpoint_model(base, model="absent-model", key="k")
    finally:
        server.shutdown()


def test_an_unreachable_endpoint_refuses_before_a_turn():
    from evals.creation_run import HealthMismatch, verify_endpoint_model

    with pytest.raises(HealthMismatch):
        verify_endpoint_model("http://127.0.0.1:9/v1", model="m", key="k", timeout=1.0)


# what one posted turn asks the server for


class _Stream:
    """The stream body `urlopen` answers with: bytes lines, and a context manager."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def __iter__(self):
        return iter(self._lines)


def test_a_posted_turn_sends_no_tool_budget_so_the_product_default_stands(monkeypatch):
    """The harness posts what a chat turn posts.

    `tool_budget: 16` cut every creation turn short of the product's 25
    (`core.chat.MAX_TOOL_ITERATIONS`), so cases ended on budget stops and compaction the
    harness had caused; the run then graded that chaos as the engine's breadth.
    """
    from evals import creation_run

    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data)
        return _Stream([b'data: {"type": "chunk", "data": "ok"}\n'])

    monkeypatch.setattr(creation_run.urllib.request, "urlopen", fake_urlopen)
    plan = plan_case(CASE, nonce="r1")

    events, approvals = creation_run.post_turn("http://127.0.0.1:9", plan, 5.0)

    assert "tool_budget" not in captured["body"]
    assert captured["body"]["message"] == CASE["input"]
    assert captured["body"]["mode"] == "creator"
    assert [event["data"] for event in events] == ["ok"]
    assert approvals == []
