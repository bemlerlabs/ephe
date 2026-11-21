"""Every install refusal carries the move that leaves it.

`core.plugin_install` is the one path a directory takes to becoming loadable, and its
answers are statuses: `local_trust_required`, `hash_mismatch`, `quarantined`, and so on. A
status and a reason say what happened; without the next command the reader is left to read
the source. The map below is that sentence, `next_step_for` is the one reader of it, and the
completeness check is over the statuses the module actually answers with — a new refusal
cannot ship without its move.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core import plugin_install

SOURCE = Path(plugin_install.__file__).read_text(encoding="utf-8")

#: The status every refusal answers with, read from the code that returns it. Two are not
#: answers and name no move: `extracted` is the success status, and `raised` is the audit
#: row written for an unexpected exception, which is re-raised after the row lands.
STATUS = re.compile(r'"status":\s*"([a-z_]+)"')
NOT_ANSWERS = {"extracted", "raised"}


def _statuses() -> set[str]:
    return {match.group(1) for match in STATUS.finditer(SOURCE)}


def test_the_status_extractor_finds_the_refusals():
    """The floor: if the pattern stops matching, the completeness check below would pass
    over an empty set."""
    found = _statuses()
    assert {"extracted", "quarantined", "local_trust_required", "hash_mismatch"} <= found


def test_every_refusal_status_has_a_next_step():
    missing = sorted(_statuses() - set(plugin_install.INSTALL_NEXT_STEPS) - NOT_ANSWERS)
    assert missing == [], (
        "install statuses with no move: "
        f"{missing}; add one sentence to INSTALL_NEXT_STEPS"
    )


def test_the_map_names_no_status_the_path_never_answers():
    """A sentence for a status nobody returns is dead text, and it hides the day the
    status is renamed."""
    extra = sorted(set(plugin_install.INSTALL_NEXT_STEPS) - _statuses() - NOT_ANSWERS)
    assert extra == []


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("local_trust_required", "--trust-local"),
        ("hash_mismatch", "sha256"),
        ("unknown_plugin", "plugin-marketplace.json"),
        ("downgrade_refused", "newer"),
        ("fetch_failed", "connection"),
    ],
)
def test_next_step_for_reads_the_map(status: str, expected: str) -> None:
    step = plugin_install.next_step_for({"status": status, "error": "x"})

    assert expected in step


def test_an_unknown_status_still_leaves_a_move() -> None:
    step = plugin_install.next_step_for({"status": "something_new"})

    assert "install" in step.lower()
