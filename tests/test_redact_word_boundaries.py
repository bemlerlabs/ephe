"""A receipt line offers the mask no word boundary to stand on (R23, F-2).

A receipt line is assembled, not typed: `f"actor={actor}{value}"` leaves a value
directly behind a letter, and a German sentence glues its next word to the value's
tail. `_KEY_LITERALS` asked for a `\\b` at both ends, so a token with no word edge
on the left or on the right came through the mask untouched. The tokens below are
assembled at run time, so the tree carries no complete credential shape for
`secret_scan` to read as a leak; what the tests describe is the boundary.
"""
from __future__ import annotations

import time

import pytest

from core.redact import redact

#: Invented, never a key: only its shape matters here.
_TOKEN = "sk-proj-" + "invent00A1b2C3d4E5f6G7h8"
#: What a receipt line may hold on either side of a value it interpolated.
_SURROUNDINGS = [
    ("", ""),
    ("actor=ops", ""),
    ("2026", ""),
    ("upload_", ""),
    ("", "wurde"),
    ("", "_note"),
    ("", "übergabe"),
    ("ops", "wurde"),
]


@pytest.mark.parametrize("lead, trail", _SURROUNDINGS)
def test_a_token_with_a_letter_or_a_word_on_either_side_is_masked(lead, trail):
    """GIVEN the token glued to its neighbours WHEN redacted THEN no value survives."""
    out = redact(lead + _TOKEN + trail)
    assert _TOKEN not in out
    assert "***" in out


def test_a_glued_token_at_the_end_of_a_receipt_line_is_masked():
    """The finding, as a line: the value sits behind a letter and before the break."""
    line = "tool=write_file actor=ops" + _TOKEN + "\n"
    out = redact(line)
    assert _TOKEN not in out
    assert out.endswith("\n"), "the line break is not part of the secret"


def test_the_mask_of_a_glued_token_is_stable_under_a_second_pass():
    """GIVEN an already redacted line WHEN redacted again THEN the bytes do not move."""
    once = redact("actor=ops" + _TOKEN + "wurde\n")
    assert redact(once) == once


def test_a_large_line_is_masked_in_one_pass():
    """The pattern carries no suffix assertion, so a long line costs one scan.

    The budget is deliberately loose: what it rules out is a suffix assertion that
    makes the engine shorten the body at every candidate position.
    """
    line = ("actor=ops" + _TOKEN + "wurde /tmp/out ") * 20000
    started = time.monotonic()
    out = redact(line)
    span = time.monotonic() - started
    assert _TOKEN not in out
    assert span < 5.0, f"a {len(line)} character line took {span:.2f}s"


# The two directions a delimiter-free token has to satisfy at once: a key survives
# being glued to prose, and an ordinary compound that happens to contain the prefix
# stays a word. The shape alone cannot tell them apart, so the rule reads the body:
# a key body is long and carries digits, a dictionary compound is not.

def _invented_key() -> str:
    """An invented key, assembled at runtime so no key-shaped literal sits in the tree."""
    return "-".join(["sk" + "-4f2b9c1e", "7a3d", "4e21", "9c6b", "8a1f0d2e5b73"])


def test_a_hyphenated_key_behind_a_letter_is_masked():
    """A receipt line interpolates values, so a key can sit directly behind a letter."""
    value = _invented_key()
    out = redact(f"actor=ops{value}")
    assert value not in out
    assert "4f2b9c1e" not in out


def test_an_ordinary_compound_containing_the_prefix_stays_a_word():
    """A compound that merely contains the prefix is a file name and stays untouched."""
    for name in (
        "docs/task-admin-configuration.md",
        "docs/risk-assessment-report.pdf",
        "mask-settings",
        "disk-usage",
        "task-runner",
    ):
        assert redact(name) == name, name


def test_an_all_letter_key_is_still_masked():
    """A key body carries no digit in every vendor shape, so length alone has to reach it."""
    letter_key = "sk-" + "b" * 32
    assert "bbbbbbbb" not in redact(letter_key)


def test_a_bare_key_with_digits_is_still_masked():
    bare = "sk-" + "4f2b9c1e" + "7a3d4e219c6b8a1f0d2e5b73"
    assert "4f2b9c1e" not in redact(bare)
