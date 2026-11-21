"""K3: the TUI footer carries the swarm count and the audit chain's verdict.

Both cells say only what the run actually produced: no wave spawned → no chip,
the chain never checked → no seal. The wiring is asserted at the source line
because the footer is inline in a 1,800-line Textual app with no standalone
render.
"""

from __future__ import annotations

from pathlib import Path

from ui.widgets import agents_label, seal_label

APP = Path("ui/app.py").read_text(encoding="utf-8")


def test_the_count_names_active_of_total() -> None:
    assert agents_label(2, 3) == "◈ 2/3"
    assert agents_label(0, 3) == "◈ 0/3"


def test_no_wave_means_no_chip() -> None:
    assert agents_label(0, 0) == ""


def test_the_seal_reports_the_chain_state() -> None:
    assert seal_label(None) == ""
    assert seal_label([]) == "⛓ ok"
    assert seal_label(["break at line 3"]) == "⛓ 1 broken"


def test_the_swarm_passes_its_bridge_into_the_pipeline() -> None:
    assert "run_swarm_v2(" in APP
    assert "on_event=on_swarm_event" in APP
    assert 'kind == "swarm_created"' in APP


def test_every_finished_turn_refreshes_the_seal() -> None:
    assert APP.count("self._refresh_seal(status)") >= 2
    assert "from core.audit_log import verify_chain" in APP
