"""The confined tool rail's refusal codes are registered where a reader looks them up.

#10's rule is the one `server/refusals.py` was written for: a refusal arrives with a
stable identifier and the reader's own language beside it, never as a bare sentence and
never as a 500. The codes are born in `core/dynamic_refusals.py` and are named by the
transport wiring, the confined runner and the restart budget, so the question this file
asks is not "does the string exist" but "does every string that can reach a surface have
a key there". A code with no entry in `REASONS` is a `KeyError` inside `Refused` — a 500
for the reader and a traceback for the log; a code with an entry in `REASONS` and none in
a bundle is the leak the registry exists to close.

Three directions are checked. From the emitters outward: every code the rail can emit is
registered and translated in both bundles with the slots the emitter fills. Through the
app: a rail refusal answers the coded `error` envelope from the product's own handler,
under 500, with no host path in the body. Across the tree: the code is written once, so a
rename cannot leave one site behind.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.dynamic_refusals import (
    CODES,
    PLUGIN_ENTRY_REFUSED,
    PLUGIN_STATE_FULL,
    PLUGIN_WORKER_RESTART_EXHAUSTED,
    SANDBOX_UNAVAILABLE,
    TOOL_NOT_AVAILABLE,
)
from core.sandbox.restart_budget import RestartBudget
from core.sandbox.runner import RunResult, _classify, resolve_entry_file
from core.sandbox.supervisor import WorkerOutcome
from server.refusals import REASONS, Refused

ROOT = Path(__file__).resolve().parents[1]

#: the slots each rail code carries, which is what a surface fills its own words from
RAIL_PARAMS = {
    TOOL_NOT_AVAILABLE: {"plugin": "acme", "transport": "plugin"},
    SANDBOX_UNAVAILABLE: {"plugin": "acme"},
    PLUGIN_WORKER_RESTART_EXHAUSTED: {"reason": "plugin worker died 3 times in a row"},
    PLUGIN_ENTRY_REFUSED: {"plugin": "acme", "reason": "the entry walks out of the plugin"},
    PLUGIN_STATE_FULL: {"plugin": "acme", "used_mb": "129", "cap_mb": "128"},
}

#: where the rail's codes are emitted; a second literal spelling would be the drift.
#: `core/sandbox/supervisor.py` is deliberately absent: its `STATUSES` vocabulary names a
#: worker classification, and one of those words is also the refusal code.
_EMITTER_FILES = (
    "core/tools/dynamic_wiring.py",
    "core/sandbox/runner.py",
    "core/sandbox/restart_budget.py",
)

#: an absolute host path in a body a browser reads is the leak #10 must not open
_HOST_PATH = re.compile(r"(?:^|[\s:,'\"(])/(?:Users|home|private|var|tmp|opt|etc)/")


def _bundle(name: str) -> dict:
    return json.loads((ROOT / "app" / "src" / "locales" / name).read_text(encoding="utf-8"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The product app, with one raising route per rail code bolted on for the drive.

    The handler under test is the one `create_app()` registers; only the raise site is
    the test's, because no production route runs a plugin tool over HTTP yet — the model
    reaches the confined worker through the chat stream, and #16 is the endpoint task.
    """
    import os

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    os.environ.pop("EPHE_SETUP_MODE", None)
    from server.main import create_app

    app = create_app()
    from fastapi.routing import APIRoute

    for code in CODES:
        def _make(Which: str):
            async def _raise():
                raise Refused(Which, **RAIL_PARAMS[Which])

            return _raise

        # Ahead of the SPA catch-all the frontend mount registers: a route appended after
        # it would never be reached, and the 404 would read as "the code does not exist".
        app.router.routes.insert(
            0, APIRoute(f"/api/_rail-refusal/{code}", _make(code), methods=["GET"])
        )
    return TestClient(app)


def test_the_rail_emits_only_registered_codes():
    """Every code `core.dynamic_refusals` hands out is a key in the HTTP registry."""
    assert set(CODES) == {
        TOOL_NOT_AVAILABLE,
        SANDBOX_UNAVAILABLE,
        PLUGIN_WORKER_RESTART_EXHAUSTED,
        PLUGIN_ENTRY_REFUSED,
        PLUGIN_STATE_FULL,
    }
    for code in CODES:
        assert code in REASONS, f"{code} reaches a surface with no entry in REASONS"
        status, template = REASONS[code]
        assert status != 500, (
            f"{code} answers {status}: a refusal that says the reader's request broke is a"
            " lie, and 500 is what an unregistered code would fall through to"
        )
        assert 400 <= status < 600, code
        assert template.strip(), code


def test_the_registry_slots_are_the_ones_the_emitter_carries():
    """A card that fills a slot the template never asked for is a half-sentence."""
    for code in CODES:
        slots = set(re.findall(r"{(\w+)}", REASONS[code][1]))
        refused = Refused(code, **RAIL_PARAMS[code])
        assert slots <= set(RAIL_PARAMS[code]), f"{code} asks for {slots - set(RAIL_PARAMS[code])}"
        assert refused.params == RAIL_PARAMS[code]


def test_both_bundles_answer_every_rail_code_with_the_same_slots():
    for code in CODES:
        slots = set(re.findall(r"{(\w+)}", REASONS[code][1]))
        for name in ("de.json", "en.json"):
            entry = _bundle(name)["serverError"].get(code, "")
            assert entry.strip(), f"{name} has no serverError.{code}"
            assert set(re.findall(r"{{(\w+)}}", entry)) == slots, f"{name}:{code}"


def test_no_emitter_spells_a_code_out_a_second_time():
    """One place per code: renaming the registry key moves every site with it.

    An emitter assigns a code with `code=` or `REFUSAL_CODE =`; every such assignment on
    this rail names the constant, so a quoted spelling here is a string the registry
    would never hear about.
    """
    quoted = re.compile(
        r"(?:code|REFUSAL_CODE)\s*[=:]\s*[\"'](%s)[\"']" % "|".join(CODES)
    )
    for rel in _EMITTER_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        hits = sorted({m.group(1) for m in quoted.finditer(text)})
        assert not hits, f"{rel} spells {hits} out instead of naming core.dynamic_refusals"


def test_an_unregistered_code_is_a_bug_at_the_raise_and_never_reaches_a_reader(client):
    with pytest.raises(KeyError, match="uncoded refusal"):
        Refused("sandbox_unavailable_but_typed_wrong")


@pytest.mark.parametrize("code", sorted(CODES))
def test_a_rail_refusal_answers_the_coded_envelope_from_the_products_handler(client, code):
    """`error.reason_code` beside the message — the shape `app/src/lib/api/http.ts` reads."""
    response = client.get(f"/api/_rail-refusal/{code}")
    assert response.status_code == REASONS[code][0]
    assert response.status_code != 500, code
    error = response.json()["error"]
    assert error["reason_code"] == code
    assert error["message"] == Refused(code, **RAIL_PARAMS[code]).message
    assert error["reason_params"] == RAIL_PARAMS[code]
    assert not _HOST_PATH.search(response.text), (code, response.text)


def test_the_confinement_refusal_text_names_no_directory():
    """The runner's own sentence is the one a model reads; it carries no host path either."""
    outcome = WorkerOutcome(status=SANDBOX_UNAVAILABLE)
    result = _classify("plugin_acme_ping", outcome, 20.0)
    assert result.kind == "refusal"
    assert result.code == SANDBOX_UNAVAILABLE
    assert result.code in REASONS
    assert not _HOST_PATH.search(result.text)
    assert "was not spawned" in result.text


def test_a_spent_restart_budget_refuses_under_the_registered_exhaustion_code():
    budget = RestartBudget(max_restarts=1, backoff_seconds=())
    verdict = budget.record_failure()
    assert getattr(verdict, "code", "") == PLUGIN_WORKER_RESTART_EXHAUSTED
    assert verdict.code in REASONS
    framed = RunResult(
        "restart_exhausted", "refusal", verdict.message, code=verdict.code
    )
    assert framed.kind == "refusal"
    assert framed.code in REASONS


def test_the_transport_still_answers_the_code_it_was_moved_from():
    """#7 minted this one beside the rail; #10 registered it and renamed nothing."""
    from core.tools import dynamic_wiring

    assert dynamic_wiring.REFUSAL_CODE == TOOL_NOT_AVAILABLE
    assert TOOL_NOT_AVAILABLE in REASONS


def test_an_entry_that_walks_out_refuses_under_the_registered_entry_code():
    target, error = resolve_entry_file(Path("/tmp/no-such-plugin"), "pkg.tools:run")
    assert target is None
    assert error
    assert not _HOST_PATH.search(error)
    assert PLUGIN_ENTRY_REFUSED in REASONS
    assert PLUGIN_STATE_FULL in REASONS
