"""W3-36 — compaction quality: what a summary must never lose (implicit decisions).

Two mechanisms stand between a decision and oblivion when a long history is
compacted:

1. the **working-memory ledger** (``conversation_compactor._build_working_memory``)
   — a keyword-bucketed summary capped at ``max_summary_chars`` (3600);
2. the **durable net** (``compaction_memory.preserve_compacted_pairs``) — a
   checkpoint-based copy of every discarded Q/A pair into long-term memory
   (``source="compaction"``).

The ledger is *lossy by design*: it truncates from the tail, so when the
low-value "User preferences"/"Project facts" buckets already fill the budget,
the high-value "Decisions"/"Artifacts"/"Open tasks" sections fall off. That is
only acceptable because the net is supposed to catch whatever the ledger drops.
These tests pin that contract, with implicit decisions (a commitment stated
*without* the magic keywords "entscheidung/decision/beschlossen/wir machen") as
the thing that must survive.
"""
from __future__ import annotations

import json

import pytest

from core import compaction_memory as cm
from core import conversation_compactor as cc
from core.conversation_compactor import _build_working_memory, compact_history

#: A decision stated without any keyword the ledger recognises.
IMPLICIT_DECISION_Q = "Wir nehmen jetzt Postgres statt SQLite fuer den Store"  # language-gate: ignore (German fixture under test)
IMPLICIT_DECISION_A = "Verstanden, wir wechseln auf Postgres. Alle Queries ziehen mit."  # language-gate: ignore (German fixture under test)

MAX_MESSAGES, KEEP_RECENT, PROTECT_FIRST_N = 28, 10, 1


def _history(pairs: int, *, keyword: str = "projekt") -> list[dict]:
    out: list[dict] = [{"role": "system", "content": "Aufgabe: Ephe bauen"}]
    for i in range(pairs):
        out.append({"role": "user", "content": f"Frage {i} {keyword}"})
        out.append({"role": "assistant", "content": f"Antwort {i} ausfuehrlich."})
    return out


def _decision_at(index: int, pairs: int = 20) -> list[dict]:
    """A history whose discarded window pairs, with ``index`` replaced by a decision."""
    out = _history(pairs)
    # out[1 + 2*index] is the user message of pair `index`.
    out[1 + 2 * index] = {"role": "user", "content": IMPLICIT_DECISION_Q}
    out[2 + 2 * index] = {"role": "assistant", "content": IMPLICIT_DECISION_A}
    return out


@pytest.fixture(autouse=True)
def _no_registry_assertions(monkeypatch):
    """The ledger pre-fills from the tool registry; tests need a fixed input."""
    import core.tools.registry as registry

    monkeypatch.setattr(registry, "get_assertions", lambda: [], raising=False)


# A. The contract: whatever the summary drops, the durable net keeps.


def test_every_pair_the_summary_discards_is_also_offered_to_the_durable_net(tmp_path):
    """The ledger may be lossy; the net must not be. The compactor's discarded
    pairs are a subset of the pairs preserve_compacted_pairs secures."""
    history = _history(20)
    summary_pairs: list[tuple[str, str]] = []
    compact_history(
        history, max_messages=MAX_MESSAGES, keep_recent=KEEP_RECENT,
        protect_first_n=PROTECT_FIRST_N, memory_sink=lambda u, a: summary_pairs.append((u, a)),
    )
    net_pairs: list[tuple[str, str]] = []
    cm.preserve_compacted_pairs(
        "s", messages=history, sink=lambda u, a: net_pairs.append((u, a)),
        path=tmp_path / "cp.json",
    )
    assert summary_pairs, "the fixture must actually discard something"
    assert all(pair in net_pairs for pair in summary_pairs)
    assert len(net_pairs) >= len(summary_pairs)


def test_the_net_window_covers_a_leading_user_message_the_summary_skips(tmp_path):
    """W18 protects the first message; the net's window starts at 0, so a decision
    sitting on that boundary is still secured even though the ledger never sees it."""
    history = [  # no leading system message → index 0 is a user turn
        {"role": "user", "content": IMPLICIT_DECISION_Q},
        {"role": "assistant", "content": IMPLICIT_DECISION_A},
        *_history(20)[1:],
    ]
    net_pairs: list[tuple[str, str]] = []
    cm.preserve_compacted_pairs(
        "s", messages=history, sink=lambda u, a: net_pairs.append((u, a)),
        path=tmp_path / "cp.json",
    )
    assert (IMPLICIT_DECISION_Q, IMPLICIT_DECISION_A) in net_pairs


# B. Implicit decisions: no keyword → the ledger's first dropped bucket,
#    so the net is the only thing that keeps them.


def test_an_implicitly_phrased_decision_lands_in_the_first_dropped_bucket():
    """Characterisation: a decision without the magic keywords is filed as plain
    context — the section the char cap trims first. Documents why the net matters."""
    ledger = _build_working_memory(
        [{"role": "user", "content": IMPLICIT_DECISION_Q}], max_chars=5000
    )
    assert "## Other relevant context" in ledger
    decisions_section = ledger.split("## Other relevant context")[0].split("## Decisions")[1]
    assert IMPLICIT_DECISION_Q not in decisions_section


def test_a_keyworded_decision_is_filed_under_decisions():
    """The control: with a keyword the ledger does classify it correctly."""
    ledger = _build_working_memory(
        [{"role": "user", "content": "Entscheidung: " + IMPLICIT_DECISION_Q}], max_chars=5000
    )
    decisions_section = ledger.split("## Decisions")[1].split("## Artifacts")[0]
    assert IMPLICIT_DECISION_Q in decisions_section


def test_an_implicit_decision_is_still_offered_to_the_net(tmp_path):
    """The guarantee: even keyword-less, the discarded decision pair reaches the net."""
    seen: list[tuple[str, str]] = []
    cm.preserve_compacted_pairs(
        "s", messages=_decision_at(7), sink=lambda u, a: seen.append((u, a)),
        path=tmp_path / "cp.json",
    )
    assert any(IMPLICIT_DECISION_Q in u for u, _ in seen)


def test_the_ledger_keeps_a_decision_when_preferences_fill_the_cap():
    filler = [
        {"role": "user", "content": f"Meine Praeferenz {i}: " + "offline-first lokal " * 12}
        for i in range(30)
    ]
    history = [
        {"role": "system", "content": "Aufgabe"},
        *filler,
        {"role": "user", "content": IMPLICIT_DECISION_Q},
        {"role": "assistant", "content": IMPLICIT_DECISION_A},
        *_history(20)[1:],
    ]
    ledger = compact_history(
        history, max_messages=MAX_MESSAGES, keep_recent=KEEP_RECENT,
        protect_first_n=PROTECT_FIRST_N, max_summary_chars=3600,
    )[1]["content"]
    assert IMPLICIT_DECISION_Q in ledger


# C. The durable net never silently skips an un-stored decision.


def test_the_checkpoint_records_a_proof_for_the_pairs_it_counts(tmp_path):
    checkpoint = tmp_path / "cp.json"
    cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )
    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert data["s"] == 15
    proof = data["__fingerprints__"]["s"]
    assert isinstance(proof, str) and len(proof) == 64


def test_a_decision_inserted_before_a_stale_checkpoint_is_still_secured(tmp_path):
    """Append-only is an assumption rather than a law. A decision re-surfaced at
    the front of a session that already has a checkpoint must be stored even
    though its index is below the stale counter."""
    checkpoint = tmp_path / "cp.json"
    cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )  # checkpoint = 15
    mutated = [
        {"role": "user", "content": IMPLICIT_DECISION_Q},
        {"role": "assistant", "content": IMPLICIT_DECISION_A},
        *_history(20),
    ]
    seen: list[tuple[str, str]] = []
    cm.preserve_compacted_pairs(
        "s", messages=mutated, sink=lambda u, a: seen.append((u, a)), path=checkpoint
    )
    assert any(IMPLICIT_DECISION_Q in u for u, _ in seen), "the new decision was silently skipped"


def test_a_shrunken_window_re_derives_instead_of_skipping(tmp_path):
    """If the discarded window is now shorter than the stored count, the count
    cannot be trusted — the run re-derives rather than skipping everything."""
    checkpoint = tmp_path / "cp.json"
    cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )  # 15 pairs
    stored = cm.preserve_compacted_pairs(
        "s", messages=_history(16), sink=lambda u, a: True, path=checkpoint
    )  # 16 pairs → 11 discarded
    assert stored == 11


def test_a_legacy_counter_without_a_fingerprint_is_re_derived_not_trusted(tmp_path):
    checkpoint = tmp_path / "cp.json"
    checkpoint.write_text(json.dumps({"s": 15}), encoding="utf-8")
    seen: list[str] = []
    stored = cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=lambda u, a: seen.append(u), path=checkpoint
    )
    assert stored == 15  # re-derived; the store's dedupe absorbs true duplicates


def test_a_hand_edited_fingerprint_does_not_preserve_a_skip(tmp_path):
    checkpoint = tmp_path / "cp.json"
    cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )
    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    data["__fingerprints__"]["s"] = "0" * 64  # foreign writer / corruption
    checkpoint.write_text(json.dumps(data), encoding="utf-8")
    stored = cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )
    assert stored == 15


def test_a_verified_checkpoint_still_costs_nothing(tmp_path):
    """The fast path is preserved: an unchanged history re-secures nothing."""
    checkpoint = tmp_path / "cp.json"
    history = _history(20)
    assert cm.preserve_compacted_pairs(
        "s", messages=history, sink=lambda u, a: True, path=checkpoint
    ) == 15
    assert cm.preserve_compacted_pairs(
        "s", messages=history, sink=lambda u, a: True, path=checkpoint
    ) == 0


# D. An outage stops the frontier *before* the decision, never past it.


def test_an_outage_does_not_advance_the_frontier_past_a_decision(tmp_path):
    checkpoint = tmp_path / "cp.json"
    decision_index = 7

    def flaky(user_text: str, assistant_text: str):
        if IMPLICIT_DECISION_Q in user_text:
            raise RuntimeError("store down at the decision")
        return True

    cm.preserve_compacted_pairs(
        "s", messages=_decision_at(decision_index), sink=flaky, path=checkpoint
    )
    # The checkpoint stopped at the decision, never beyond it.
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["s"] == decision_index

    recovered: list[str] = []
    cm.preserve_compacted_pairs(
        "s", messages=_decision_at(decision_index),
        sink=lambda u, a: recovered.append(u), path=checkpoint,
    )
    assert any(IMPLICIT_DECISION_Q in u for u in recovered), "the decision was lost across the outage"


def test_a_deliberate_refusal_advances_so_the_frontier_never_stalls(tmp_path):
    """A store-side refusal ('duplicate') is a decision and never an outage — it
    must advance the checkpoint, or the same turn would be retried forever."""
    checkpoint = tmp_path / "cp.json"
    calls: list[str] = []

    def refusing(user_text: str, assistant_text: str):
        calls.append(user_text)
        return {"stored": False, "reason": "duplicate"}

    cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=refusing, path=checkpoint
    )
    assert len(calls) == 15
    assert cm.preserve_compacted_pairs(
        "s", messages=_history(20), sink=refusing, path=checkpoint
    ) == 0
