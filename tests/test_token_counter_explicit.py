"""The token counter is a named choice, recorded where the run can read it.

``estimate_tokens`` used to follow tiktoken whenever the interpreter happened to
carry it, so one fixture priced at 2407 tokens through the heuristic and 33
through BPE, moving every window-fitting boundary. The counter now has a name
(``EPHE_TOKEN_COUNTER``) and the name that ran is written back: a usage block
names the counter whenever one priced a side, and the budget path reports it.

Both counter paths are pinned here, with tiktoken injected by a stand-in and
removed again, so the tests are offline and machine-independent.
"""
from __future__ import annotations

import sys
import types

import pytest

from core import usage as U

#: 43 characters: the stand-in BPE counter returns 10, the 4.2 ratio returns 11 —
#: one fixture the two counters price apart.
_TWO_COUNTERS_APART = "a" * 43
_BPE_COUNT = 10
_CALIBRATED_COUNT = 11


class _FakeEncoding:
    """Deterministic BPE stand-in: one token per four characters."""

    def encode(self, text: str) -> list[int]:
        if not text:
            return []
        return list(range(max(1, len(text) // 4)))


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


def _bpe_present(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", _FakeTiktoken("tiktoken"))
    U.reset_tokenizer_cache()


def _bpe_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    U.reset_tokenizer_cache()


# The setting names the counter.

def test_unset_setting_is_auto():
    assert U.counter_setting() == U.COUNTER_AUTO


def test_auto_follows_the_interpreter_either_way(monkeypatch):
    _bpe_present(monkeypatch)
    assert U.tokenizer_backend() == U.BPE_BACKEND
    _bpe_absent(monkeypatch)
    assert U.tokenizer_backend() == U.CALIBRATED_BACKEND


def test_explicit_calibrated_ignores_an_importable_tiktoken(monkeypatch):
    _bpe_present(monkeypatch)
    monkeypatch.setenv(U.COUNTER_ENV, "calibrated")
    U.reset_tokenizer_cache()
    assert U.counter_setting() == U.CALIBRATED_BACKEND
    assert U.tokenizer_backend() == U.CALIBRATED_BACKEND
    assert U.estimate_tokens(_TWO_COUNTERS_APART) == _CALIBRATED_COUNT


def test_explicit_tiktoken_uses_the_bpe_counter(monkeypatch):
    _bpe_present(monkeypatch)
    monkeypatch.setenv(U.COUNTER_ENV, "tiktoken")
    U.reset_tokenizer_cache()
    assert U.counter_setting() == U.BPE_BACKEND
    assert U.tokenizer_backend() == U.BPE_BACKEND
    assert U.estimate_tokens(_TWO_COUNTERS_APART) == _BPE_COUNT


def test_explicit_tiktoken_without_the_module_keeps_the_fallback(monkeypatch):
    _bpe_absent(monkeypatch)
    monkeypatch.setenv(U.COUNTER_ENV, "tiktoken")
    U.reset_tokenizer_cache()
    assert U.counter_setting() == U.BPE_BACKEND          # the request stands
    assert U.tokenizer_backend() == U.CALIBRATED_BACKEND  # the counter that ran
    assert U.estimate_tokens(_TWO_COUNTERS_APART) == _CALIBRATED_COUNT


def test_unknown_setting_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv(U.COUNTER_ENV, "cl100k")
    assert U.counter_setting() == U.COUNTER_AUTO


# The choice is recorded with the usage block.

def test_estimated_block_records_the_calibrated_counter(monkeypatch):
    _bpe_absent(monkeypatch)
    block = U.build_usage("p" * 42, "a" * 84)
    assert block["tokenizer"] == U.CALIBRATED_BACKEND
    assert block["tokenizer"] == U.tokenizer_backend()
    assert block["usage_estimated"] is True


def test_estimated_block_records_the_bpe_counter(monkeypatch):
    _bpe_present(monkeypatch)
    block = U.build_usage("p" * 42, "a" * 84)
    assert block["tokenizer"] == U.BPE_BACKEND
    assert block["tokenizer"] == U.tokenizer_backend()
    assert block["usage_estimated"] is False


def test_the_recorded_name_tracks_an_explicit_setting(monkeypatch):
    _bpe_present(monkeypatch)
    monkeypatch.setenv(U.COUNTER_ENV, "calibrated")
    U.reset_tokenizer_cache()
    block = U.build_usage("prompt text", "answer text")
    assert block["tokenizer"] == U.CALIBRATED_BACKEND
    assert block["tokenizer"] == U.tokenizer_backend()


def test_fully_measured_block_names_no_counter(monkeypatch):
    _bpe_present(monkeypatch)
    block = U.build_usage("prompt", "answer", prompt_tokens=9, completion_tokens=4)
    assert "tokenizer" not in block
    assert block["usage_estimated"] is False
