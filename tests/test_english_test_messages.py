"""The test suite says itself in English: assert messages, skip reasons, raised sentences.

`scripts/language_inventory.py:counts_for` scores every line of a file, literals included, so the
language gate had seen these sentences — it measured them into `scripts/language-baseline.json` and
judged growth from there. A German message under a file's baseline entry is free, and one that
predates the entry is free forever. Measured on 2026-11-23: 362 of them over 101 files, while the
ratchet read the same tree as clean. What was missing is not sight but a floor at zero, and a node
to point at.

`scripts/message_language.py` parses the file and reads those strings. This file proves the
instrument works and pins the state it enforces: zero. There is no baseline here, because a
baseline would freeze the German instead of removing it. German that is the product's own surface —
the refusal a user sees, a locale value, an answer the model gave in the language it was asked in —
is the subject of the test and stays, marked on the message's line with
`# language-gate: product German` and the reason; `scripts/message_language.py` reads that marker.

No German of its own lives here, same rule as `tests/test_language_gate.py`: every planted sentence
is assembled from the instrument's own marker list, which keeps this file clean under the rule it
checks and stops the fixture drifting away from the detector it exercises.

Given / When / Then, strictly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTRUMENT_PATH = REPO / "scripts" / "message_language.py"
INVENTORY_PATH = REPO / "scripts" / "language_inventory.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


messages = _load("message_language_under_test", INSTRUMENT_PATH)
inventory = _load("language_inventory_under_test", INVENTORY_PATH)

#: German for the probes, assembled rather than typed: a written-out sentence here would be a
#: finding under the very rule this file proves.
GERMAN = " ".join(inventory.MARKERS[:4])
GERMAN_WORDS = tuple(word for word in GERMAN.split() if word.lower() not in inventory.FALSE_FRIENDS)

CLEAN_SOURCE = '''
import pytest


def test_the_counter():
    assert 1 == 1, "the counter advanced"


def test_the_other():
    assert 2 == 2, "the other counter advanced"
'''


def _source_with(message: str, *, marker: str = "") -> str:
    """The clean file with its second assert carrying `message`, optionally marked on that line."""
    statement = f'assert 2 == 2, "{message}"'
    if marker:
        statement += f"  # {marker}"
    return CLEAN_SOURCE.replace('assert 2 == 2, "the other counter advanced"', statement)


def _tree_findings() -> list[messages.Finding]:
    found, read, unread, files = messages.scan(messages.test_paths(REPO), REPO)
    assert files > 500, f"the scan covered only {files} files — the suite is not reaching tests/"
    assert read > 2000, f"the scan read only {read} messages — it is looking at the wrong nodes"
    return found


def test_the_suite_says_itself_in_english() -> None:
    """
    GIVEN  every test file the checkout holds
    WHEN   each message the suite writes about itself is read
    THEN   none of them is German developer prose
    """
    findings = _tree_findings()
    assert not findings, (
        f"{len(findings)} message(s) speak German, first: "
        + "; ".join(f"{f.rel}:{f.line} {f.kind}: {f.quote}" for f in findings[:5])
        + " — rewrite the sentence in English, or mark the line with "
        "`# language-gate: product German` and the reason if the product says it"
    )


def test_the_scan_reads_the_messages_it_claims_to_cover() -> None:
    """A guard that stopped parsing still passes, so both halves of what it read are pinned.

    The two numbers are what this tree measured on 2026-11-23: 887 files, 2825 messages carrying a
    literal, 2324 built at runtime. `unread` staying above a thousand is the instrument's own limit
    made visible — a collapse to zero would mean the parser grew powers it does not have.
    """
    _, read, unread, files = messages.scan(messages.test_paths(REPO), REPO)
    assert files > 500, f"only {files} files reached"
    assert read > 2000, f"only {read} messages read"
    assert unread > 1000, f"only {unread} unread — the scan claims to see messages it cannot reach"


def test_a_german_assert_message_is_actually_found() -> None:
    """
    GIVEN  a file whose second assert answers in German
    WHEN   the instrument reads it
    THEN   exactly that message is reported, at its line, as an assert message
    """
    findings, read, _unread = messages.check("test_planted.py", _source_with(GERMAN))
    assert read == 2, read
    assert len(findings) == 1, findings
    assert findings[0].kind == "assert message" and findings[0].line == 10, findings[0]
    assert GERMAN_WORDS[0] in findings[0].quote, findings[0].quote


def test_a_german_skip_reason_is_actually_found() -> None:
    """The same sentence in a skip reason is a finding too — a red leg is read as a skip first."""
    source = CLEAN_SOURCE.replace(
        'assert 2 == 2, "the other counter advanced"',
        f"pytest.skip({GERMAN!r})",
    )
    findings, _read, _unread = messages.check("test_planted.py", source)
    assert [f.kind for f in findings] == ["pytest.skip text"], findings


def test_a_marked_product_fixture_is_accepted() -> None:
    """
    GIVEN  a message quoting what the product itself says, marked with a reason on its line
    WHEN   the instrument reads it
    THEN   it is not a finding — the German is the subject of the test
    """
    marked = _source_with(GERMAN, marker=f"{messages.MESSAGE_PRAGMA} (the refusal the product shows)")
    findings, _read, _unread = messages.check("test_planted.py", marked)
    assert findings == [], findings


def test_a_marker_without_a_reason_is_itself_a_finding() -> None:
    """An exemption nobody can read is how a rule gets overlooked, so the reason is mandatory."""
    bare = _source_with(GERMAN, marker=messages.MESSAGE_PRAGMA)
    findings, _read, _unread = messages.check("test_planted.py", bare)
    assert [f.kind for f in findings] == ["unexplained exemption"], findings


def test_a_hoisted_message_is_read_where_it_is_written() -> None:
    """`assert ok, msg` with the sentence one line above is the same developer voice, not an exemption."""
    hoisted = CLEAN_SOURCE.replace(
        'assert 2 == 2, "the other counter advanced"',
        f"meldung = {GERMAN!r}\n    assert 2 == 2, meldung",
    )
    findings, _read, _unread = messages.check("test_planted.py", hoisted)
    assert len(findings) == 1 and findings[0].kind == "assert message", findings


def test_a_file_the_scan_cannot_read_is_a_finding_not_a_skip() -> None:
    """A leg that passes because it parsed nothing would be the exact failure this rule prevents."""
    broken = messages.Finding("tests/test_broken.py", 0, "unparsable", "x")
    findings, _read, _unread = messages.check("tests/test_broken.py", "def test(:\n")
    assert len(findings) == 1 and findings[0].kind == broken.kind, findings
    findings, _read, _unread = messages.check_pairs([("tests/test_broken.py", None)])
    assert [f.kind for f in findings] == ["unreadable"], findings


def test_the_product_german_marker_is_the_one_the_instrument_reads() -> None:
    """A marker renamed on one side and not the other would exempt nothing at all."""
    assert messages.MESSAGE_PRAGMA == "language-gate: product German"
    assert messages.MESSAGE_PRAGMA not in inventory.PRAGMA


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
