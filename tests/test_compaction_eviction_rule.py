"""W7-8 — the compaction loss rule: a summary must never lose a decision.

The ledger fits its cap by priority (``_LEDGER_SECTIONS`` weights). A brute
tail cut of the rendered summary drops the LAST sections — the ones that carry
decisions, artifacts and open tasks — as soon as low-value "User preferences" /
"Project facts" text fills the cap. These tests force eviction (the uncapped
summary is several times the cap) and prove the high-value sections survive
while the low-value sections are the ones trimmed.

Contract-driven, per the W7 measurement rule: the fixture reads the keyword
vocabulary from ``_LEDGER_BUCKETS`` and the priority sets from the public
``LEDGER_*`` constants — no section header, keyword, cap or message threshold is
hard-coded, so a reweighting or a keyword rename moves the test with the code
instead of breaking it on a literal (the ``ed1c9c3b`` failure mode).
"""
from __future__ import annotations

import pytest

from core.conversation_compactor import (
    _LEDGER_BUCKETS,
    _LEDGER_SECTIONS,
    DEFAULT_MAX_MESSAGES,
    DEFAULT_MAX_SUMMARY_CHARS,
    DEFAULT_PROTECT_FIRST_N,
    DEFAULT_PROTECT_LAST_N,
    LEDGER_CATCH_ALL_SECTION,
    LEDGER_EVICTED_FIRST_SECTIONS,
    LEDGER_MUST_KEEP_SECTIONS,
    _build_working_memory,
    compact_history,
)

#: The keyword-bearing high-value sections — the ones that must survive the
#: flood. ``LEDGER_CATCH_ALL_SECTION`` is high-value by weight but carries no
#: keyword of its own and has its own boundary test below.
SURVIVING_SECTIONS = tuple(
    header for header in LEDGER_MUST_KEEP_SECTIONS if header != LEDGER_CATCH_ALL_SECTION
)

_SENTINEL = "SENTINEL-W78"


@pytest.fixture(autouse=True)
def _empty_assertion_ledger():
    """The ledger pre-fills from the registry's assertion ledger; keep it empty
    so the fixture below is the only thing that decides what the sections hold."""
    from core.tools.registry import reset_assertion_ledger

    reset_assertion_ledger()
    yield
    reset_assertion_ledger()


def _keyword(header: str) -> str:
    """The first registered keyword that lands a message in ``header``."""
    for bucket, words in _LEDGER_BUCKETS:
        if bucket == header:
            return words[0]
    raise AssertionError(f"no keyword group registered for {header!r}")


def _tag(header: str) -> str:
    """A whitespace-free token for ``header`` so the sentinel is a plain match."""
    return "".join(ch for ch in header if ch.isalnum())


def _sentinel(header: str) -> str:
    return f"{_SENTINEL}-{_tag(header)}"


def _section_body(text: str, header: str) -> str:
    """The rendered body of one section (up to the next section header)."""
    assert header in text, f"{header!r} is missing from the ledger"
    tail = text.split(header, 1)[1]
    cuts = [tail.find(other) for other, _weight in _LEDGER_SECTIONS if tail.find(other) > 0]
    return (tail[: min(cuts)] if cuts else tail).strip()


def _flooded_history() -> list[dict]:
    """Low-value text first (it is what fills the cap), then one sentinel per
    high-value section, then untouched recent turns."""
    history: list[dict] = [{"role": "system", "content": "Task context"}]
    for header in LEDGER_EVICTED_FIRST_SECTIONS:
        keyword = _keyword(header)
        for i in range(40):
            history.append({"role": "user", "content": f"{keyword} {i}: " + "filler text " * 14})
    for header in SURVIVING_SECTIONS:
        history.append({"role": "user", "content": f"{_keyword(header)}: {_sentinel(header)}"})
    for i in range(DEFAULT_PROTECT_LAST_N):
        history.append({"role": "user", "content": f"recent q {i}"})
        history.append({"role": "assistant", "content": f"recent a {i}"})
    return history


def _middle(history: list[dict]) -> list[dict]:
    return history[DEFAULT_PROTECT_FIRST_N : -DEFAULT_PROTECT_LAST_N]


def _uncapped(history: list[dict]) -> str:
    """The ledger as it would render with no cap — the input the cap trims."""
    return _build_working_memory(_middle(history), max_chars=1_000_000_000)


def test_the_low_value_flood_fills_the_cap_so_eviction_is_forced():
    """The premise of every test below: the cap really binds and content is
    dropped. Without this the survival assertions would be vacuous."""
    history = _flooded_history()
    assert len(history) > DEFAULT_MAX_MESSAGES

    uncapped = _uncapped(history)
    ledger = compact_history(history)[1]["content"]

    assert len(uncapped) > DEFAULT_MAX_SUMMARY_CHARS  # the cap is a real constraint
    assert len(ledger) <= DEFAULT_MAX_SUMMARY_CHARS  # ... and it was applied
    assert len(ledger) < len(uncapped)  # ... and content was actually evicted


def test_decisions_artifacts_and_open_tasks_survive_the_flood():
    """The loss rule: no volume of preference/fact text evicts a decision."""
    ledger = compact_history(_flooded_history())[1]["content"]
    for header in SURVIVING_SECTIONS:
        assert _sentinel(header) in ledger, f"{header} lost its entry to the flood"


def test_high_value_sections_are_unclipped_while_low_value_sections_are_trimmed():
    """The mechanism, not just the outcome: the low-value sections absorb the
    eviction, so the high-value sections stay byte-identical to their uncapped
    form."""
    history = _flooded_history()
    uncapped = _uncapped(history)
    ledger = compact_history(history)[1]["content"]

    for header in SURVIVING_SECTIONS:
        assert _section_body(ledger, header) == _section_body(uncapped, header), (
            f"{header} was trimmed even though low-value text is the surplus"
        )
    for header in LEDGER_EVICTED_FIRST_SECTIONS:
        assert len(_section_body(ledger, header)) < len(_section_body(uncapped, header)), (
            f"{header} was not trimmed — the flood did not compete for the cap"
        )


def test_a_plain_tail_cut_would_lose_the_decisions_that_priority_sharing_keeps():
    """The regression pin: this is the pre-share failure mode. A brute
    ``full[:cap]`` drops the trailing high-value sections, so it loses every
    sentinel — while ``compact_history`` keeps all of them."""
    history = _flooded_history()
    naive_tail_cut = _uncapped(history)[:DEFAULT_MAX_SUMMARY_CHARS]

    for header in SURVIVING_SECTIONS:
        assert _sentinel(header) not in naive_tail_cut, (
            "fixture no longer forces the tail cut to reach the high-value sections"
        )
    ledger = compact_history(history)[1]["content"]
    for header in SURVIVING_SECTIONS:
        assert _sentinel(header) in ledger


def test_the_catch_all_keeps_an_implicit_decision_only_while_it_fits_its_share():
    """The documented boundary of the catch-all: it carries the high-value
    weight, but it has no priority of its own. A keyword-less decision in it
    survives while the section fits its share and is dropped once it overflows
    (the durable net, ``core.compaction_memory.preserve_compacted_pairs``, is the
    backstop for the dropped older entries)."""
    decision = f"Wir nehmen jetzt Postgres statt SQLite {_SENTINEL}-CATCH"  # language-gate: ignore (German decision fixture; the keyword list is German)

    small = [{"role": "system", "content": "Task context"}, {"role": "user", "content": decision}]
    for i in range(DEFAULT_MAX_MESSAGES):
        small.append({"role": "user", "content": f"recent q {i}"})
        small.append({"role": "assistant", "content": f"recent a {i}"})
    assert _SENTINEL + "-CATCH" in compact_history(small)[1]["content"]

    flooded = [{"role": "system", "content": "Task context"}, {"role": "user", "content": decision}]
    for i in range(60):
        flooded.append({"role": "user", "content": f"context {i}: " + "noise " * 30})
    for i in range(DEFAULT_MAX_MESSAGES):
        flooded.append({"role": "user", "content": f"recent q {i}"})
        flooded.append({"role": "assistant", "content": f"recent a {i}"})
    assert _SENTINEL + "-CATCH" not in compact_history(flooded)[1]["content"]
