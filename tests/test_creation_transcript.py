"""Tests for the engine half of the creation eval (task #51e).

`evals/creation_runner.py` grades a transcript and a staging root that someone else
produced, and `evals/creation/rubric.md` names that someone as this work. These tests
prove the producer's two contracts without spending an engine:

* the transcript is the shape `core.plugin_golden.grade` reads — so a tool that fired is
  evidence and a tool that was only named in a sentence is not;
* the staging root a case is graded against holds the bundles that case's turn wrote, and
  nothing from the case before it, because `evals.creation_checks.staged_bundles` refuses
  a subject count other than one.

The stream is replayed as the `data:` lines the product's own SSE frame format produces,
so a change to what `/api/chat/stream` emits shows up here as a failing test rather than
as a receipt that quietly stops measuring anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from core.plugin_golden import grade

MARKER = "\n[EPHE-TOOL-EVENTS]\n"


def _frame(event: dict) -> str:
    """One SSE line exactly as the route writes it."""
    return f"data: {json.dumps(event, ensure_ascii=False)}"


def _scaffold_events(result: dict | None = None) -> list[dict]:
    """A turn that scaffolded one bundle: a start, a done, and an answer."""
    payload = {"bundle": "world-clock", "path": "/tmp/stage/plugins/world-clock"}
    return [
        {"type": "tool_start", "tool": "create_plugin_scaffold", "args": {"name": "world-clock"}},
        {
            "type": "tool_done",
            "tool": "create_plugin_scaffold",
            "status": "ok",
            "result": json.dumps(result if result is not None else payload),
        },
        {"type": "chunk", "data": "Built the world clock as a floating widget. "},
        {"type": "chunk", "data": "Pick your cities and it ticks every minute."},
    ]


# the transcript shape


def test_a_fired_tool_is_evidence_and_a_named_tool_is_not():
    """The split the marker exists for, proven on both halves of one transcript."""
    from evals.creation_transcript import build_transcript

    transcript = build_transcript(_scaffold_events())
    case = {
        "id": "creation-02",
        "category": "widget",
        "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]},
    }
    assert grade(case, transcript) is True

    # The same answer with no event line is the claim without the evidence, and must fail.
    claimed = "I used create_plugin_scaffold." + MARKER
    assert grade(case, claimed) is False


def test_the_answer_stays_before_the_marker_and_the_events_after_it():
    from evals.creation_transcript import build_transcript

    transcript = build_transcript(_scaffold_events())
    answer, _, events = transcript.partition(MARKER)
    assert "floating widget" in answer
    assert events.startswith("[tool create_plugin_scaffold]")
    # A `contains` case is graded on the answer half, so the answer must survive the fold.
    case = {"id": "x", "category": "widget", "expect": {"kind": "contains", "any": ["world clock"]}}
    assert grade(case, transcript) is True


def test_a_refused_call_carries_the_refusal_and_its_reason():
    from evals.creation_transcript import build_transcript

    refused = {
        "error": "plugin_tool_not_granted",
        "detail": "[TOOL-ERROR] refused: this bundle declares no tools",
    }
    events = [
        {"type": "tool_start", "tool": "write_plugin_source", "args": {"name": "x"}},
        {
            "type": "tool_done",
            "tool": "write_plugin_source",
            "status": "refused",
            "reason_code": "plugin_tool_not_granted",
            "result": json.dumps(refused),
        },
        {"type": "chunk", "data": "I cannot add code to a bundle without an approval."},
    ]
    transcript = build_transcript(events)
    case = {
        "id": "creation-21",
        "category": "utility",
        "expect": {
            "kind": "tool_refused",
            "any": ["write_plugin_source"],
            "reason": "plugin_tool_not_granted",
        },
    }
    assert grade(case, transcript) is True

    # A different reason must not pass: the case names the refusal it expects.
    other = dict(case["expect"], reason="sandbox_unavailable")
    assert grade({**case, "expect": other}, transcript) is False


def test_the_discovery_shim_does_not_hide_the_tool_behind_it():
    """The product reaches most tools through tool_search + tool_call.

    A `tool_call` that dispatches an inner tool contributes that tool even when the inner
    call emits no frames of its own, because the case names the tool it asked for.
    """
    from evals.creation_transcript import build_transcript

    events = [
        {"type": "tool_start", "tool": "tool_search", "args": {"query": "plugin scaffold"}},
        {"type": "tool_done", "tool": "tool_search", "status": "ok", "result": "create_plugin_scaffold"},
        {
            "type": "tool_start",
            "tool": "tool_call",
            "args": {"name": "create_plugin_scaffold", "arguments": {"name": "world-clock"}},
        },
        {
            "type": "tool_done",
            "tool": "tool_call",
            "status": "ok",
            "result": json.dumps({"bundle": "world-clock"}),
        },
        {"type": "chunk", "data": "Done."},
    ]
    transcript = build_transcript(events)
    assert "[tool create_plugin_scaffold]" in transcript
    case = {
        "id": "creation-02",
        "category": "widget",
        "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]},
    }
    assert grade(case, transcript) is True
    # The shim itself is not the subject of the case, so it is not an event line.
    assert "[tool tool_search]" not in transcript
    assert "[tool tool_call]" not in transcript


def test_a_turn_that_only_failed_produces_a_transcript_that_fails():
    """An error frame with no answer is a run row, not a crash in the producer."""
    from evals.creation_transcript import build_transcript

    events = [{"type": "error", "msg": "engine timeout"}]
    transcript = build_transcript(events)
    assert transcript.endswith(MARKER.strip("\n")) or MARKER in transcript
    case = {
        "id": "creation-02",
        "category": "widget",
        "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]},
    }
    assert grade(case, transcript) is False


def test_a_multiline_tool_result_stays_on_its_own_event_line():
    """`core.plugin_golden._events` reads one line per call, so a result is folded."""
    from evals.creation_transcript import build_transcript

    events = [
        {"type": "tool_start", "tool": "verify_plugin_bundle", "args": {"name": "world-clock"}},
        {
            "type": "tool_done",
            "tool": "verify_plugin_bundle",
            "status": "ok",
            "result": "manifest valid\nsurface files written",
        },
    ]
    lines = build_transcript(events).split(MARKER, 1)[1].splitlines()
    assert len(lines) == 1
    assert "manifest valid" in lines[0] and "surface files" in lines[0]


# the staging root a case is graded against


def _write_bundle(staging: Path, name: str) -> Path:
    bundle = staging / name
    (bundle / "ui").mkdir(parents=True)
    (bundle / "ephe-plugin.json").write_text(
        json.dumps({"id": name, "name": name, "version": "0.1.0"}), encoding="utf-8"
    )
    (bundle / "ui" / "index.html").write_text("<html></html>", encoding="utf-8")
    return bundle


def test_a_cases_staging_holds_only_the_bundles_that_cases_turn_wrote(tmp_path):
    from evals.creation_transcript import bundles_root, take_staged_bundles

    root = bundles_root(tmp_path)
    _write_bundle(root, "world-clock")
    _write_bundle(root, "countdown")

    dest = tmp_path / "runs" / "creation-02"
    names = take_staged_bundles(tmp_path, dest)
    assert sorted(names) == ["countdown", "world-clock"]
    assert sorted(p.name for p in dest.iterdir()) == ["countdown", "world-clock"]
    # The next case starts from an empty folder, so `staged_bundles` sees one subject.
    assert list(root.iterdir()) == []


def test_a_refused_turn_leaves_an_empty_staging_root(tmp_path):
    """The refusal cases expect `staging_empty`, which is only true of a clean folder."""
    from evals.creation_transcript import bundles_root, take_staged_bundles

    bundles_root(tmp_path)
    dest = tmp_path / "runs" / "creation-21"
    assert take_staged_bundles(tmp_path, dest) == []
    assert dest.exists() and list(dest.iterdir()) == []


def test_the_staging_folder_is_the_one_the_creator_tools_write_into(tmp_path, monkeypatch):
    """Read from the product's own path, so the producer cannot aim at the wrong folder."""
    from core.tools.creator_tools import bundles_root as product_bundles_root
    from evals.creation_transcript import bundles_root

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    assert bundles_root(tmp_path) == product_bundles_root(tmp_path)


# the engine seam


def test_the_engine_environment_moves_the_key_from_its_file_into_the_child_env(tmp_path):
    from evals.creation_transcript import engine_environment

    key = (tmp_path / "engine.key").parent / "engine.key"
    key.write_text("sk-" + "0" * 32 + "\n", encoding="utf-8")
    env = engine_environment(
        key_file=key,
        config_dir=tmp_path / "config",
        base_url="https://api.deepseek.example/v1",
        model="deepseek-test",
        port=8801,
    )
    assert env["EPHE_MODEL_PROVIDER"] == "openai_compatible"
    assert env["EPHE_OPENAI_COMPAT_BASE_URL"] == "https://api.deepseek.example/v1"
    assert env["EPHE_OPENAI_COMPAT_MODEL"] == "deepseek-test"
    assert env["EPHE_CONFIG_DIR"] == str(tmp_path / "config")
    assert env["EPHE_OPENAI_COMPAT_API_KEY"] == key.read_text().strip()
    # The server's own port is what makes its loopback origin an allowed one, so the
    # harness that posts to it has to name the same number.
    assert env["EPHE_PORT"] == "8801"


def test_the_key_appears_in_no_other_variable_of_the_child_env(tmp_path):
    from evals.creation_transcript import engine_environment

    key = tmp_path / "engine.key"
    secret = "sk-" + "a" * 32
    key.write_text(secret + "\n", encoding="utf-8")
    env = engine_environment(
        key_file=key,
        config_dir=tmp_path / "config",
        base_url="https://api.deepseek.example/v1",
        model="deepseek-test",
        port=8801,
    )
    carriers = [name for name, value in env.items() if secret in str(value)]
    assert carriers == ["EPHE_OPENAI_COMPAT_API_KEY"]


@pytest.mark.parametrize(
    ("body", "code"),
    [(None, "missing"), ("", "empty"), ("one\ntwo\n", "multiline")],
)
def test_a_key_that_is_not_exactly_one_line_is_refused(tmp_path, body, code):
    from evals.creation_transcript import engine_environment

    key = tmp_path / "engine.key"
    if body is not None:
        key.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        engine_environment(
            key_file=key,
            config_dir=tmp_path / "config",
            base_url="https://api.deepseek.example/v1",
            model="deepseek-test",
            port=8801,
        )


def test_a_persisted_engine_choice_in_the_config_root_is_refused(tmp_path):
    """`resolve_engine_choice` reads engine.json before the env, so a stale file there
    would answer a different engine than the run claims — the run says so instead."""
    from evals.creation_transcript import engine_environment

    key = tmp_path / "engine.key"
    key.write_text("sk-" + "0" * 32 + "\n", encoding="utf-8")
    config = tmp_path / "config"
    config.mkdir()
    (config / "engine.json").write_text(json.dumps({"provider": "local_ollama"}), encoding="utf-8")
    with pytest.raises(ValueError, match="engine.json"):
        engine_environment(
            key_file=key,
            config_dir=config,
            base_url="https://api.deepseek.example/v1",
            model="deepseek-test",
            port=8801,
        )


def test_the_engine_environment_owns_an_empty_builtin_plugin_root(tmp_path):
    """The run's environment names the checkout in no variable that answers a catalog:
    the builtin plugin root points into the run's own config folder and stays empty, so a
    graded turn cannot list the developer's working tree as installed plugins."""
    from evals.creation_transcript import engine_environment

    key = tmp_path / "engine.key"
    key.write_text("sk-" + "0" * 32 + "\n", encoding="utf-8")
    config = tmp_path / "config"
    env = engine_environment(
        key_file=key,
        config_dir=config,
        base_url="https://api.deepseek.example/v1",
        model="deepseek-test",
        port=8801,
    )
    builtin = Path(env["EPHE_BUILTIN_PLUGINS_ROOT"])
    assert builtin == config / "builtin-plugins"
    assert builtin.is_dir()
    assert list(builtin.iterdir()) == []
