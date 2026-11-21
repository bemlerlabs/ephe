"""A reload re-enters the one mount and never accepts a moved contract for the caller.

Task #15 already refuses a changed schema or description until the names are
acknowledged. A reload is the creator's path through that same transition, so
it has no acknowledge argument of its own.
"""
from __future__ import annotations

import pytest

from core.plugin_hot_reload import reload_bundle
from core.plugin_lifecycle_types import REFUSE_CHANGE, LifecycleError


class _Mount:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls: list[tuple[str, dict]] = []

    def mount(self, plugin_id: str, **kwargs):
        self.calls.append((plugin_id, kwargs))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_reload_mounts_without_acknowledging_anything() -> None:
    machine = _Mount({"phase": "mounted"})
    assert reload_bundle("countdown", lifecycle=machine) == {"phase": "mounted"}
    plugin_id, kwargs = machine.calls[0]
    assert plugin_id == "countdown"
    assert kwargs["acknowledge"] == ()
    assert kwargs["acknowledge_artifact"] is False
    assert kwargs["actor"] == "reload"


def test_a_changed_contract_stays_the_pin_refusal() -> None:
    refusal = LifecycleError(
        REFUSE_CHANGE,
        409,
        "the tool contract changed",
        data={"diff": [{"name": "tick", "fields": ["description"]}]},
    )
    machine = _Mount(refusal)
    with pytest.raises(LifecycleError) as caught:
        reload_bundle("countdown", lifecycle=machine)
    assert caught.value.code == REFUSE_CHANGE
    assert caught.value.data["diff"][0]["name"] == "tick"
    assert machine.calls[0][1]["acknowledge"] == ()
