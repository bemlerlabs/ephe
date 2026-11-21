"""A plugin route refusal names the code, the reason and the move — on every branch.

Driving the plugin routes left three dead ends: a bundle the install does not address
answered `{"code": "plugin_unknown"}` with no sentence (the envelope then put the code
where the message goes), a switch that failed its lifecycle gate carried the code and the
detail but no step, and the same-origin guard answered a header requirement with no way to
meet it. This file pins the vocabulary the routes now share: one map of codes to the move
they leave, carried in the response envelope beside the sentence.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_lifecycle_types
from server.refusals import NEXT_STEPS, REASONS, Refused

#: The refusal codes the plugin routes answer with, pinned against the registry.
PLUGIN_CODES = {
    "plugin_unknown",
    "plugin_state_name",
    "plugin_state_full",
    "plugin_ui_unavailable",
    "plugin_ui_unauthorized",
    "plugin_ui_asset_refused",
    "plugin_entry_refused",
    "tool_not_available",
    "sandbox_unavailable",
    "tool_failed",
    "invalid_request",
}

#: The lifecycle codes a switch or a mount refuses with, pinned against the module.
LIFECYCLE_CODES = {
    "invalid_request",
    "unknown_plugin",
    "stale_state",
    "signature_denied",
    "dependency_blocked",
    "dependency_cycle",
    "idempotency_conflict",
    "dependents_enabled",
    "not_cancellable",
    "state_write_failed",
    plugin_lifecycle_types.REFUSE_MANIFEST,
    plugin_lifecycle_types.REFUSE_CONFLICT,
    plugin_lifecycle_types.REFUSE_CHANGE,
    plugin_lifecycle_types.REFUSE_ARTIFACT,
    plugin_lifecycle_types.REFUSE_REGISTRY,
}


def test_every_plugin_route_code_carries_a_next_step():
    """GIVEN the coded refusals the plugin routes raise
    WHEN the registry is read
    THEN each has a sentence and a move — a code alone is half an answer."""
    for code in sorted(PLUGIN_CODES):
        assert code in REASONS, code
        assert str(NEXT_STEPS.get(code) or "").strip(), f"{code}: no next step"


def test_every_lifecycle_code_carries_a_next_step():
    """The switch is refused with these codes; the route frames each with a move."""
    for code in sorted(LIFECYCLE_CODES):
        step = plugin_lifecycle_types.next_step_for(code)
        assert str(step).strip(), f"{code}: no next step"
        assert step != plugin_lifecycle_types.next_step_for("a_code_nobody_uses"), code


def test_an_unknown_lifecycle_code_still_leaves_a_move():
    step = plugin_lifecycle_types.next_step_for("something_new")

    assert "retry" in step.lower() or "again" in step.lower()


def test_a_coded_refusal_exposes_the_move_on_the_exception() -> None:
    """The handler reads one attribute; a code with no move stays empty, never raises."""
    assert Refused("plugin_unknown").next == NEXT_STEPS["plugin_unknown"]
    assert Refused("tool_failed").next == NEXT_STEPS["tool_failed"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from core import audit_log, plugin_runtime
    from server.main import create_app

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    plugin_runtime.invalidate_ownership_cache()
    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client
    plugin_runtime.invalidate_ownership_cache()


def test_an_unknown_bundle_is_a_sentence_and_a_move(client):
    """GIVEN a bundle id the install does not hold
    WHEN a plugin route addresses it
    THEN the body carries the code, a sentence and the move — the code is not the message."""
    response = client.get("/api/plugins/not-installed/state")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["reason_code"] == "plugin_unknown"
    assert error["message"] == REASONS["plugin_unknown"][1]
    assert error["next"] == NEXT_STEPS["plugin_unknown"]


def test_the_same_origin_guard_says_which_header_to_send(client):
    """GIVEN a mutation without the XHR marker
    WHEN the guard refuses it
    THEN the body names the header and the move that satisfies it."""
    response = client.put(
        "/api/plugins/web-research/enabled",
        json={"enabled": False},
        headers={"X-Requested-With": ""},
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["detail"]["code"] == "unauthorized"
    assert "X-Requested-With" in error["message"]
    assert "X-Requested-With" in error["next"]


def test_a_lifecycle_refusal_carries_the_code_the_reason_and_the_move(client):
    """GIVEN a switch for a bundle the lifecycle does not know
    WHEN the route answers
    THEN the detail holds the code, the reason and the move."""
    response = client.put("/api/plugins/not-installed/enabled", json={"enabled": True})

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["detail"]["code"] == "unknown_plugin"
    assert error["detail"]["detail"]
    assert error["next"] == plugin_lifecycle_types.next_step_for("unknown_plugin")
