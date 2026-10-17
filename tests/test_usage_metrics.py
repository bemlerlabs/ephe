"""P1-3: core/usage.py — honest token bookkeeping, pinned directly.

Coverage of the three SSOT paths:
  1. tokenizer_backend() switching (tiktoken BPE vs. calibrated heuristic)
  2. CJK calibration (factor ~1:1) against Latin (~4.2 characters/token)
  3. build_usage() flag matrix (usage_estimated only on a calibrated estimate)

All tests are offline and deterministic; tiktoken is injected per test via
sys.modules or removed, so both backend branches are hit for sure.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from core import usage as U


@pytest.fixture(autouse=True)
def _fresh_tokenizer():
    U.reset_tokenizer_cache()
    yield
    U.reset_tokenizer_cache()


# 1. Backend switching

def test_backend_is_calibrated_without_tiktoken():
    sys.modules["tiktoken"] = None  # not available
    U.reset_tokenizer_cache()
    assert U.tokenizer_backend() == U.CALIBRATED_BACKEND


def test_backend_is_bpe_with_tiktoken():
    fake = MagicMock()
    fake.get_encoding.return_value = MagicMock(encode=lambda s: list(range(len(s))))
    sys.modules["tiktoken"] = fake
    U.reset_tokenizer_cache()
    assert U.tokenizer_backend() == U.BPE_BACKEND


def test_estimate_uses_bpe_when_available():
    enc = MagicMock()
    enc.encode.return_value = [1, 2, 3, 4]  # 4 tokens
    fake = MagicMock()
    fake.get_encoding.return_value = enc
    sys.modules["tiktoken"] = fake
    U.reset_tokenizer_cache()
    assert U.estimate_tokens("hello world foo bar") == 4


# 2. CJK calibration (fallback path)

def test_latin_only_uses_4_2_ratio():
    sys.modules["tiktoken"] = None
    U.reset_tokenizer_cache()
    # 42 Latin characters / 4.2 = 10 tokens
    assert U.estimate_tokens("a" * 42) == 10


def test_cjk_counts_near_one_per_char():
    sys.modules["tiktoken"] = None
    U.reset_tokenizer_cache()
    # 40 CJK code points (0x4E00..0x9FFF) ≈ 40 tokens, not 40/4.2≈10
    cjk = "\u4e00" * 40
    assert U.estimate_tokens(cjk) == 40


def test_mixed_cjk_latin_sums_both_schaetzungen():
    sys.modules["tiktoken"] = None
    U.reset_tokenizer_cache()
    # 10 CJK (≈10) + 42 Latin (≈10) = 20
    assert U.estimate_tokens("\u4e00" * 10 + "a" * 42) == 20


def test_empty_string_is_zero():
    assert U.estimate_tokens("") == 0


# 3. build_usage() flag matrix

def test_build_usage_measured_is_not_estimated():
    sys.modules["tiktoken"] = None
    U.reset_tokenizer_cache()
    u = U.build_usage("prompt", "completion", prompt_tokens=5, completion_tokens=7)
    assert u["prompt_tokens"] == 5
    assert u["completion_tokens"] == 7
    assert u["total_tokens"] == 12
    assert u["usage_estimated"] is False


def test_build_usage_estimated_flag_when_no_measured_and_calibrated():
    sys.modules["tiktoken"] = None
    U.reset_tokenizer_cache()
    u = U.build_usage("prompt text", "completion text")
    assert u["usage_estimated"] is True  # calibrated estimate, never a plain 0


def test_build_usage_bpe_measured_side_not_flagged():
    enc = MagicMock()
    enc.encode.return_value = [1, 2, 3]
    fake = MagicMock()
    fake.get_encoding.return_value = enc
    sys.modules["tiktoken"] = fake
    U.reset_tokenizer_cache()
    # both sides counted via BPE → not marked as an estimate
    u = U.build_usage("abc", "def")
    assert u["usage_estimated"] is False


# 4. provider measurement extraction

def test_extract_measured_counts_ollama_native():
    assert U.extract_measured_counts({"prompt_eval_count": 11, "eval_count": 22}) == (11, 22)


def test_extract_measured_counts_openai_usage_frame():
    assert U.extract_measured_counts({"usage": {"prompt_tokens": 3, "completion_tokens": 4}}) == (3, 4)


def test_extract_measured_counts_absent_returns_none():
    assert U.extract_measured_counts({"choices": []}) is None
    assert U.extract_measured_counts("not-a-dict") is None


# 4. Wave 3: prompt-cache pass-through (cost/cache chip)

def test_build_usage_passes_measured_cached_tokens_through():
    """GIVEN a provider reports cached_tokens WHEN build_usage THEN the OpenAI shape
    prompt_tokens_details.cached_tokens — measured only, never guessed."""
    sys.modules["tiktoken"] = None
    U.reset_tokenizer_cache()
    u = U.build_usage("p", "c", prompt_tokens=100, completion_tokens=10, cached_tokens=40)
    assert u["prompt_tokens_details"]["cached_tokens"] == 40
    assert u["prompt_tokens"] == 100


def test_build_usage_omits_cached_block_when_missing():
    """GIVEN a provider reports no cache WHEN build_usage THEN no
    prompt_tokens_details (the chip stays off instead of claiming 0)."""
    sys.modules["tiktoken"] = None
    U.reset_tokenizer_cache()
    u = U.build_usage("p", "c", prompt_tokens=100, completion_tokens=10)
    assert "prompt_tokens_details" not in u


def test_record_measured_usage_accumulates_openai_cached():
    """GIVEN OpenAI usage with prompt_tokens_details WHEN record THEN
    cached_tokens accumulate (finding wave 3: the cache-chip data path)."""
    from core.tools.session_ctx import record_measured_usage, get_measured_usage, _MEASURED_USAGE

    _MEASURED_USAGE.set(None)  # the ContextVar is global per thread — test isolation
    record_measured_usage({"prompt_tokens": 100, "completion_tokens": 5,
                           "prompt_tokens_details": {"cached_tokens": 60}})
    record_measured_usage({"prompt_tokens": 50, "completion_tokens": 5,
                           "prompt_tokens_details": {"cached_tokens": 20}})
    m = get_measured_usage()
    assert m["prompt_tokens"] == 150
    assert m["cached_tokens"] == 80


def test_record_measured_usage_accumulates_anthropic_shim_cached():
    """GIVEN Anthropic shim usage (cache_read_input_tokens) WHEN record THEN
    cached accumulates."""
    from core.tools.session_ctx import record_measured_usage, get_measured_usage, _MEASURED_USAGE

    _MEASURED_USAGE.set(None)  # the ContextVar is global per thread — test isolation
    record_measured_usage({"prompt_tokens": 10, "completion_tokens": 1,
                           "cache_read_input_tokens": 7})
    m = get_measured_usage()
    assert m["cached_tokens"] == 7


def test_record_measured_usage_without_cache_stays_zero():
    """GIVEN Ollama nomenclature without a cache field WHEN record THEN cached 0."""
    from core.tools.session_ctx import record_measured_usage, get_measured_usage, _MEASURED_USAGE

    _MEASURED_USAGE.set(None)  # the ContextVar is global per thread — test isolation
    record_measured_usage({"prompt_eval_count": 9, "eval_count": 3})
    m = get_measured_usage()
    assert m["cached_tokens"] == 0
