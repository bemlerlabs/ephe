"""The probe reads a captured engine request and states what it proves.

`evals/creation_offer_probe.py` is the instrument that answered why a live Creator turn
built a loose file: it reads the array and the system prompt out of the request the product
actually sent. Two ways it can lie are worth a test each — a turn that reached no engine at
all must not read as "the array is missing names", and the verdict has to come from the
first call of the turn, which is the one that carries the offer.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.creation_offer_probe import CREATOR_CALLS, describe, offer_of


def _request(tool_names: list[str], system: str = "IDENTITY:\n- You are Ephe.") -> dict:
    return {
        "model": "probe-model",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": n}} for n in tool_names],
    }


def test_no_request_kept_reads_as_a_turn_that_never_reached_the_engine():
    """A run that never called the engine has no array to judge, and says so with zero calls."""
    reading = describe([])
    assert reading["calls"] == 0
    assert reading["creator_missing"] == sorted(CREATOR_CALLS)
    assert reading["model"] is None


def test_the_offer_is_read_from_the_first_call_of_the_turn():
    """The later rounds of a turn carry the same array, so the first one is the offer."""
    requests = [
        _request(["create_plugin_scaffold", "write_file"]),
        _request(["create_plugin_scaffold", "write_file", "read_file"]),
    ]
    assert offer_of(requests) == ["create_plugin_scaffold", "write_file"]
    assert describe(requests)["offered"] == ["create_plugin_scaffold", "write_file"]


def test_the_reading_separates_the_names_the_mode_promised_from_the_rest_of_the_array():
    """Two lists, because the defect is a name that is offered and a prompt that never says so."""
    reading = describe([_request([*CREATOR_CALLS, "write_file", "read_file"], system="no mode text")])
    assert reading["creator_offered"] == sorted(CREATOR_CALLS)
    assert reading["creator_missing"] == []
    assert reading["system_chars"] == len("no mode text")
    assert reading["system_head"] == "no mode text"
