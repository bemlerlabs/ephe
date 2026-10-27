"""P5: model trajectory + window-proportional compression.

Pins:
1. begin/record/end: steps are numbered, the usage step carries IN/OUT, and chunk
   and thinking types never fall into the picture (they are not created at all).
2. A running turn appears in get_turns with live steps (running); after end_turn it
   is in the history — newest first, steps truncated above the cap.
3. window_threshold: proportional to the window (80 %), with enabled/fixed env.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import trajectory  # noqa: E402
from core.conversation_compactor import (  # noqa: E402
    DEFAULT_THRESHOLD_TOKENS,
    compact_history,
    window_threshold,
)


def test_steps_numeriert_und_usage_achse(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s1", model="m")
    trajectory.record("s1", {"type": "thinking_start"})
    trajectory.record("s1", {"type": "tool_start", "cmd": "read_file"})
    trajectory.record("s1", {"type": "subagent_started", "agent_id": "subagent-1", "role": "scout"})
    trajectory.record(
        "s1",
        {"type": "usage", "usage": {"prompt_tokens": 120, "completion_tokens": 8}},
    )
    trajectory.end_turn("s1")

    turns = trajectory.get_turns("s1")
    assert len(turns) == 1
    steps = turns[0]["steps"]
    assert [s["n"] for s in steps] == [1, 2, 3, 4]
    assert steps[1]["title"] == "read_file"
    assert steps[2]["title"] == "subagent-1 · scout"
    assert steps[3]["usage"] == {"in": 120, "out": 8, "model": ""}


def test_running_turn_zeigt_live_und_kappung(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s2", model="m")
    trajectory.record("s2", {"type": "phase", "name": "plan", "status": "running"})
    live = trajectory.get_turns("s2")
    assert len(live) == 1 and live[0]["steps"][0]["type"] == "PHASE"

    for i in range(trajectory.MAX_STEPS_PER_TURN + 5):
        trajectory.record("s2", {"type": "activity", "cmd": f"cmd-{i}"})
    assert len(trajectory.get_turns("s2")[0]["steps"]) == trajectory.MAX_STEPS_PER_TURN


def test_turn_id_lebt_den_ganzen_turn(tmp_path, monkeypatch):
    """A3 backwards: the id has to be visible in the running turn, not only in the
    history — otherwise the replay view can only assign an order its files once the
    order is already over."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s6", model="m", turn_id="t-6")
    trajectory.record("s6", {"type": "done"})
    assert trajectory.get_turns("s6")[0]["turn_id"] == "t-6"
    trajectory.end_turn("s6")
    assert trajectory.get_turns("s6")[0]["turn_id"] == "t-6"
    # Older snapshots do not know the id — missing is empty, not guessed.
    trajectory.begin_turn("s7", model="m")
    trajectory.record("s7", {"type": "done"})
    trajectory.end_turn("s7")
    assert trajectory.get_turns("s7")[0]["turn_id"] == ""


def test_neustart_lädt_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s3", model="m")
    trajectory.record("s3", {"type": "done"})
    trajectory.end_turn("s3")

    trajectory.reset_for_test()
    assert len(trajectory.get_turns("s3")) == 1
    assert trajectory.get_turns("s3")[0]["steps"][0]["type"] == "DONE"


def test_textkoerper_user_thinking_assistant_tool_output(tmp_path, monkeypatch):
    """P6 (ref-12): USER-/reasoning/assistant/tool-output texts as the step text."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s4", model="m")
    trajectory.record("s4", {"type": "user", "text": "Analysiere das Repo"})
    trajectory.record("s4", {"type": "thinking", "text": "Ich untersuche zuerst die Struktur."})
    trajectory.record(
        "s4",
        {"type": "tool_done", "tool": "run_shell", "result": "3 Dateien gefunden"},
    )
    trajectory.record("s4", {"type": "assistant", "text": "Fertig, hier die Analyse."})
    trajectory.end_turn("s4")

    steps = trajectory.get_turns("s4")[0]["steps"]
    assert [s["type"] for s in steps] == ["USER", "THINKING", "TOOL_DONE", "ASSISTANT"]
    assert steps[0]["text"] == "Analysiere das Repo"
    assert steps[1]["text"] == "Ich untersuche zuerst die Struktur."
    # the tool name stays the title, the result goes into the text body
    assert steps[2]["title"] == "run_shell"
    assert steps[2]["text"] == "3 Dateien gefunden"
    assert steps[3]["text"] == "Fertig, hier die Analyse."


def test_textkoerper_gekappt_und_leerer_falls_ohne(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s5", model="m")
    trajectory.record("s5", {"type": "activity", "cmd": "ohne-koerper"})
    trajectory.record("s5", {"type": "user", "text": "x" * (trajectory.MAX_TEXT_CHARS + 500)})
    trajectory.end_turn("s5")

    steps = trajectory.get_turns("s5")[0]["steps"]
    assert "text" not in steps[0]
    assert len(steps[1]["text"]) == trajectory.MAX_TEXT_CHARS


def test_window_threshold_anteilig(monkeypatch):
    # A tier only carries a tag once the user configured one (2026-10-11), so the
    # table this lookup runs over is seeded with the fixture tag.
    import core.model_config as m
    from core.model_config import ModelTier

    monkeypatch.setattr(m, "TIER_MAP", {
        ModelTier.FAST: m.ModelConfig(name="gemma4:12b", tier=ModelTier.FAST),
    })
    monkeypatch.setenv("EPHE_CONTEXT_WINDOW", "10000")
    assert window_threshold("any-model") == 8000
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW")
    # without a probe/tier the documented legacy value 8192 applies → 80 % of it
    assert window_threshold("unbekannt-modell") == int(8192 * 0.8)
    # model-specific: the tier table gives 16384 for gemma4:12b → 13107
    assert window_threshold("gemma4:12b") == int(16384 * 0.8)


def test_token_schwelle_kompaktiert_vor_nachrichtengrenze():
    msgs = [{"role": "user", "content": "x" * 64}, {"role": "assistant", "content": "y" * 64}] * 10
    # few messages (<= 28), but above the mini threshold → compacted
    out = compact_history(msgs, threshold_tokens=60)
    assert len(out) < len(msgs)
    assert out[0] == msgs[0]
    assert out[1]["role"] == "system"  # the ledger
    assert out[-1] == msgs[-1]


def test_prose_step_title_is_one_sentence(tmp_path, monkeypatch):
    """F5: a narration step is titled by its first sentence; the paragraph
    stays the step body."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s-prose", model="m")
    trajectory.record(
        "s-prose",
        {
            "type": "text",
            "text": "Verify the file exists and check its content. Workspace is empty — no suite.",
        },
    )
    trajectory.end_turn("s-prose")

    steps = trajectory.get_turns("s-prose")[0]["steps"]
    assert steps[0]["title"] == "Verify the file exists and check its content."
    assert "Workspace is empty" not in steps[0]["title"]
