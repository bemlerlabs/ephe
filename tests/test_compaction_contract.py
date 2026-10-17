"""G8: Compaction-Contract parity — the backend is the Single Source of Truth.

Shared fixture (used together with the Vitest parity test):
    app/fixtures/compaction/sample-history.json   (Input)
    app/fixtures/compaction/expected-ledger.json (Golden: ledger summary as a string)

The client (app/src/lib/compact.ts) has to produce the same ledger summary from
the same fixture (its own Vitest run: compact.parity.test.ts).

W18 parity (reference-A config.yaml:85-94): protect_first_n=1, protect_last_n=10.
The output structure is [protected first message, ledger, last 10].

Regenerate the golden whenever `core/conversation_compactor.py` changes:
    python3 -c "import json,pathlib;from core.conversation_compactor import compact_history;\
h=json.loads(pathlib.Path('app/fixtures/compaction/sample-history.json').read_text());\
pathlib.Path('app/fixtures/compaction/expected-ledger.json').write_text(json.dumps(compact_history(h)[1]['content']))"
"""
from __future__ import annotations

import json
from pathlib import Path

from core.conversation_compactor import compact_history

FIXTURES = Path(__file__).parent.parent / "app" / "fixtures" / "compaction"
HISTORY = json.loads((FIXTURES / "sample-history.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((FIXTURES / "expected-ledger.json").read_text(encoding="utf-8"))

MAX_MESSAGES, KEEP_RECENT, PROTECT_FIRST_N = 28, 10, 1


def test_given_shared_fixture_when_compacted_then_ledger_matches_golden():
    """The backend result has to match the golden file exactly (self-check)."""
    compacted = compact_history(
        HISTORY, max_messages=MAX_MESSAGES, keep_recent=KEEP_RECENT,
        protect_first_n=PROTECT_FIRST_N,
    )
    # W18: index 0 = protected first message, index 1 = ledger
    assert compacted[1]["role"] == "system"
    assert compacted[1]["content"] == GOLDEN


def test_given_shared_fixture_when_compacted_then_structure_is_one_ledger_plus_recent():
    """Structure parity: 1 protected first message + 1 ledger + exactly the last 10 turns."""
    compacted = compact_history(
        HISTORY, max_messages=MAX_MESSAGES, keep_recent=KEEP_RECENT,
        protect_first_n=PROTECT_FIRST_N,
    )
    assert len(compacted) == PROTECT_FIRST_N + 1 + KEEP_RECENT
    assert compacted[1]["role"] == "system"
    assert compacted[2:] == HISTORY[-KEEP_RECENT:]
    assert compacted[0] == HISTORY[0]


def test_given_shared_fixture_when_compacted_then_ledger_hits_summary_cap():
    """The fixture is deliberately > 3600 characters → the cap kicks in (otherwise the
    golden match would be trivial)."""
    compacted = compact_history(
        HISTORY, max_messages=MAX_MESSAGES, keep_recent=KEEP_RECENT,
        protect_first_n=PROTECT_FIRST_N,
    )
    assert len(compacted[1]["content"]) == 3600
