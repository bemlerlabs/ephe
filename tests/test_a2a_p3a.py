"""P3-A tests: A2A task protocol lifecycle (core/a2a.py).

Covers the task_id lifecycle, terminal-state immutability, artifact ledger,
context grouping, and the best-effort JSON persistence roundtrip.
"""
from __future__ import annotations

import pathlib
import pytest

import core.a2a as a2a
from core.a2a import (
    A2AProtocol,
    AgentCard,
    STATUS_SUBMITTED,
    STATUS_WORKING,
    STATUS_INPUT_REQUIRED,
    STATUS_COMPLETED,
    STATUS_FAILED,
)


def _fresh() -> A2AProtocol:
    return A2AProtocol(persist=False)


def test_new_task_starts_submitted():
    p = _fresh()
    p.register(AgentCard(name="pdf-creator", tools=["create_pdf"]))
    task = p.new_task("pdf-creator", context_id="c1")
    assert task.status == STATUS_SUBMITTED
    assert task.id.startswith("task-")
    assert task.history[-1]["status"] == STATUS_SUBMITTED


def test_lifecycle_walks_to_completed():
    p = _fresh()
    task = p.new_task("deck-creator", context_id="c2")
    p.set_status(task.id, STATUS_WORKING)
    p.add_artifact(task.id, {"tool": "create_pptx_deck", "result": "PPTX_FILE: /tmp/d.pptx"})
    p.set_status(task.id, STATUS_COMPLETED)
    d = p.get(task.id)
    assert d["status"] == STATUS_COMPLETED
    assert [h["status"] for h in d["history"]] == [
        STATUS_SUBMITTED, STATUS_WORKING, STATUS_COMPLETED
    ]
    assert d["artifacts"][0]["tool"] == "create_pptx_deck"


def test_input_required_then_working_roundtrip():
    p = _fresh()
    task = p.new_task("translator", context_id="c3")
    p.set_status(task.id, STATUS_WORKING)
    p.set_status(task.id, STATUS_INPUT_REQUIRED)
    p.set_status(task.id, STATUS_WORKING)
    assert p.get(task.id)["status"] == STATUS_WORKING


def test_terminal_state_is_immutable():
    p = _fresh()
    task = p.new_task("help", context_id="c4")
    p.set_status(task.id, STATUS_COMPLETED)
    assert p.set_status(task.id, STATUS_WORKING)["status"] == STATUS_COMPLETED
    assert p.set_status(task.id, STATUS_FAILED)["status"] == STATUS_COMPLETED


def test_unknown_status_raises():
    p = _fresh()
    task = p.new_task("help")
    with pytest.raises(ValueError):
        p.set_status(task.id, "no-such-state")


def test_get_unknown_returns_none():
    assert _fresh().get("task-0000") is None


def test_tasks_grouped_by_context():
    p = _fresh()
    p.new_task("pdf-creator", context_id="shared")
    p.new_task("deck-creator", context_id="shared")
    p.new_task("translator", context_id="other")
    assert len(p.tasks_for_context("shared")) == 2
    assert len(p.tasks_for_context("other")) == 1


def test_card_registry_lookup():
    p = _fresh()
    p.register(AgentCard(name="pdf-creator", tools=["create_pdf"]))
    card = p.card("pdf-creator")
    assert card is not None and card.tools == ["create_pdf"]
    assert p.card("missing") is None


def test_persistence_roundtrip(tmp_path, monkeypatch):
    ledger = tmp_path / "a2a_ledger.json"
    monkeypatch.setattr(a2a, "A2A_LEDGER_FILE", ledger)
    p = A2AProtocol(persist=True)
    p.register(AgentCard(name="pdf-creator", tools=["create_pdf"]))
    task = p.new_task("pdf-creator", context_id="c9")
    p.set_status(task.id, STATUS_COMPLETED)
    assert ledger.exists()
    q = A2AProtocol(persist=True)
    q.load()
    reloaded = q.get(task.id)
    assert reloaded is not None and reloaded["status"] == STATUS_COMPLETED
    assert q.card("pdf-creator") is not None
