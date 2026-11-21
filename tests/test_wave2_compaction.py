"""Wave 2 / B4 — compaction stays model-derived and single-entry.

The wave asked to prove the trigger before offering a setting. It is: `window_threshold`
is 80 % of the effective window of the active model, so a knob would only restate a
number the model already carries. The finding is pinned here, together with the demand
that the existing action stays the only entry point.
"""
from __future__ import annotations

import core.conversation_compactor as compactor
from core.settings_schema import SCHEMA


class TestTheThresholdIsModelDerived:
    def test_a_small_window_compacts_earlier_than_a_large_one(self, monkeypatch):
        windows = {"small": 8192, "large": 262_144}
        monkeypatch.setattr(
            "core.model_config.resolve_context_window",
            lambda model: (windows.get(model, 0), "test"),
        )
        assert compactor.window_threshold("small") == int(8192 * 0.8)
        assert compactor.window_threshold("large") == int(262_144 * 0.8)

    def test_an_unknown_model_falls_back_to_the_documented_threshold(self, monkeypatch):
        monkeypatch.setattr(
            "core.model_config.resolve_context_window", lambda model: (0, "none")
        )
        assert compactor.window_threshold("") == compactor.DEFAULT_THRESHOLD_TOKENS

    def test_there_is_no_compaction_threshold_setting(self):
        # The stop condition of S0: a knob here would be a number the model already
        # answers. If this ever fails, the finding was overturned on purpose. A
        # memory-dedupe threshold is a different field and stays out of this claim.
        assert [key for key in SCHEMA if "compact" in key or "window_threshold" in key] == []
