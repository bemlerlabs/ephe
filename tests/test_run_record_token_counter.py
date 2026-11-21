"""The run record names the token counter that priced its block.

Wave 4 made the counter an explicit, recorded choice: ``core/usage.build_usage`` names
the counter whenever one priced a side. The run record is the other half of that record,
and its ``effort.tokens`` block used to drop the name. These tests pin the carry —
``core/run_evidence.token_accounting`` names the same counter, the schema in
``core/run_record`` accepts exactly that key, and a name this build cannot price with is
refused.

Both counter paths run with tiktoken injected by a stand-in and removed again, so the
file is offline and machine-independent.
"""
from __future__ import annotations

import sys
import types

import pytest

from core import run_record as R
from core import usage as U
from core.run_evidence import RunRecorder, new_turn_id, token_accounting
from core.run_record import RunRecordError, validate_record


class _FakeEncoding:
    """Deterministic BPE stand-in: one token per four characters."""

    def encode(self, text: str) -> list[int]:
        return [] if not text else list(range(max(1, len(text) // 4)))


class _FakeTiktoken(types.ModuleType):
    def get_encoding(self, name: str):
        assert name == "cl100k_base"
        return _FakeEncoding()


@pytest.fixture(autouse=True)
def _clean_counter(monkeypatch):
    monkeypatch.delenv(U.COUNTER_ENV, raising=False)
    U.reset_tokenizer_cache()
    yield
    U.reset_tokenizer_cache()


def _bpe(monkeypatch, present: bool) -> None:
    monkeypatch.setitem(sys.modules, "tiktoken", _FakeTiktoken("tiktoken") if present else None)
    U.reset_tokenizer_cache()


def _record(tmp_path) -> dict:
    recorder = RunRecorder(
        entrypoint="code", task="make the failing test in tests/test_x.py green",
        provider="local_ollama", model="gemma4:12b", turn_id=new_turn_id("code"),
        api_url=None, gate_posture="chat-gate", worktree=str(tmp_path),
    )
    return recorder.build(answer="ok")


# The block token_accounting returns names the counter that priced a side.

def test_an_estimated_block_names_the_calibrated_counter(monkeypatch):
    _bpe(monkeypatch, present=False)
    block = token_accounting(None, "prompt text", "answer text")
    assert block["tokenizer"] == U.CALIBRATED_BACKEND
    assert block["tokenizer"] == U.tokenizer_backend()
    assert block["source"] == "estimated"


def test_an_estimated_block_names_the_bpe_counter(monkeypatch):
    _bpe(monkeypatch, present=True)
    block = token_accounting(None, "prompt text", "answer text")
    assert block["tokenizer"] == U.BPE_BACKEND
    assert block["tokenizer"] == U.tokenizer_backend()


def test_a_measured_block_names_no_counter():
    measured = {"prompt_tokens": 9, "completion_tokens": 4}
    block = token_accounting(measured, "prompt text", "answer text")
    assert block["tokenizer"] is None
    assert block["source"] == "measured"


def test_the_filled_block_matches_the_schema_keys():
    block = token_accounting(None, "prompt text", "answer text")
    assert set(block) == set(R._TOKENS)
    assert "tokenizer" in R._TOKENS


# The record carries the name end to end, and the schema keeps the key known while the
# whitelist stays closed: a foreign name, or a second unknown key, is refused.

def test_the_record_carries_the_counter_name(tmp_path, monkeypatch):
    _bpe(monkeypatch, present=False)
    record = _record(tmp_path)
    assert record["effort"]["tokens"]["tokenizer"] == U.tokenizer_backend()
    assert record["effort"]["tokens"]["estimated"] is True


def test_a_foreign_counter_name_is_refused(tmp_path):
    record = _record(tmp_path)
    record["effort"]["tokens"]["tokenizer"] = "made-up-counter"
    with pytest.raises(RunRecordError, match=r"effort\.tokens\.tokenizer"):
        validate_record(record)


def test_the_key_is_known_and_the_whitelist_stays_closed(tmp_path):
    record = _record(tmp_path)
    record["effort"]["tokens"]["counter"] = True
    with pytest.raises(RunRecordError, match="unknown key"):
        validate_record(record)


def test_a_block_with_no_counter_names_null_and_still_validates(tmp_path):
    record = _record(tmp_path)
    record["effort"]["tokens"]["tokenizer"] = None
    assert validate_record(record) is record
