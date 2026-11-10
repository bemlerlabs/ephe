from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.test_tool_calling import _make_ollama_response


def test_given_short_history_when_compacted_then_history_is_unchanged():
    from core.conversation_compactor import compact_history

    history = [
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": "Hi"},
    ]

    assert compact_history(history, max_messages=8, keep_recent=4) == history


def test_given_long_history_when_compacted_then_working_memory_and_recent_turns_remain():
    """
    GIVEN a long conversation with project facts and decisions
    WHEN compact_history is called
    THEN older turns become a stable working-memory system message.
    """
    from core.conversation_compactor import compact_history

    history = []
    for i in range(18):
        history.append({"role": "user", "content": f"Projekt ephe-{i}: Entscheidung {i} und Aufgabe testen."})
        history.append({"role": "assistant", "content": f"Ich merke mir Entscheidung {i}. Nächster Schritt pytest."})

    compacted = compact_history(history, max_messages=12, keep_recent=6)

    # W18: first(1) + ledger(1) + recent(6) = 8
    assert len(compacted) == 8
    assert compacted[0]["role"] == "user"  # the protected first message
    assert compacted[1]["role"] == "system"  # the ledger
    assert "Conversation working memory" in compacted[1]["content"]
    assert "Entscheidung" in compacted[1]["content"]
    assert compacted[-1] == history[-1]
    assert compacted[-6:] == history[-6:]


def test_given_old_artifacts_preferences_and_tasks_when_compacted_then_working_memory_ledger_preserves_them():
    """
    GIVEN a long conversation contains user preferences, artifacts, decisions, and open tasks
    WHEN compact_history builds the context ledger
    THEN those stable facts survive in the compact system message.
    """
    from core.conversation_compactor import compact_history

    history = []
    for index in range(20):
        history.append({"role": "user", "content": f"Small talk {index}"})
    history.extend(
        [
            {"role": "user", "content": "Meine Präferenz: strikt lokal, keine Cloud."},
            {"role": "assistant", "content": "Entscheidung: Root-PWA auf Port 9876 bleibt Ziel."},
            {"role": "assistant", "content": "Artefakt erstellt: /work/Downloads/report.pdf"},
            {"role": "user", "content": "Nächster Schritt: PDF Skill testen und Findings fixen."},
        ]
    )
    for index in range(20):
        history.append({"role": "assistant", "content": f"Recent answer {index}"})

    compacted = compact_history(history, max_messages=12, keep_recent=4)
    # W18: index 0 = first (protected), index 1 = ledger
    ledger = compacted[1]["content"]

    assert "Working Memory Ledger" in ledger
    assert "strikt lokal" in ledger
    assert "Port 9876" in ledger
    assert "report.pdf" in ledger
    assert "PDF Skill testen" in ledger


@pytest.mark.asyncio
async def test_given_long_history_when_chat_runs_then_compacted_context_is_sent_to_model():
    """
    GIVEN a long chat history
    WHEN chat_with_tools performs tool detection
    THEN the model receives a compacted working-memory context instead of every old turn.
    """
    from core.chat import chat_with_tools

    history = []
    for i in range(20):
        history.append({"role": "user", "content": f"Projekt Alpha Entscheidung {i}"})
        history.append({"role": "assistant", "content": f"Notiert {i}"})
    pure_text = _make_ollama_response(content="OK", tool_calls=[])

    with patch("core.chat.ollama.AsyncClient") as MockClient:
        client = AsyncMock()
        client.chat = AsyncMock(return_value=pure_text)
        MockClient.return_value = client

        await chat_with_tools(
            model="gemma4:12b",
            history=history,
            on_chunk=lambda c: None,
        )

    sent_messages = client.chat.call_args_list[0].kwargs["messages"]
    # W18: the merged system prompt carries the ledger content (first protection +
    # ledger + recent). The ledger text is inside the merged system messages.
    merged_system = "\n".join(
        str(m.get("content", "")) for m in sent_messages if m.get("role") == "system"
    )
    assert "Conversation working memory" in merged_system
    assert len(sent_messages) < len(history)


# #102: the visible conversation may only shrink, and a system block stays whole.
#
# The handoff finding ("one Creator turn dropped the visible conversation from
# 12 to 67 messages during compaction") is measured here instead of repeated:
# the pair is the OUTPUT and the INPUT of one compaction, in that order.


def _talk_history(count: int) -> list[dict]:
    """A plain conversation: alternating user/assistant, ending on an answer."""
    history = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"turn {index}: the decision {index} stays pending"})
    return history


def _creator_history(tool_calls: int) -> list[dict]:
    """One Creator turn on the wire: the ask, the tool block, its answers."""
    calls = [{"id": f"call_{i}", "function": {"name": "write_file", "arguments": "{}"}} for i in range(tool_calls)]
    return [
        {"role": "user", "content": "Creator: baue das Plugin"},
        {"role": "assistant", "content": "", "tool_calls": calls},
        *({"role": "tool", "content": f"result {i} ok"} for i in range(tool_calls)),
    ]


def test_the_reported_12_to_67_pair_is_the_compaction_output_and_input():
    """GIVEN the 67 messages of a long conversation WHEN compacted
    THEN the visible conversation is 12 — the two numbers of the handoff, reversed."""
    from core.conversation_compactor import compact_history

    history = _talk_history(67)
    compacted = compact_history(history)

    assert len(history) == 67
    assert len(compacted) == 12  # first(1) + ledger(1) + recent(10)
    assert len(compacted) <= len(history)


def test_a_12_message_conversation_is_not_compacted_and_not_inflated():
    """GIVEN the 12 visible messages of the handoff WHEN compacted
    THEN they come back unchanged — the threshold is 28, so nothing runs."""
    from core.conversation_compactor import compact_history

    history = _talk_history(12)
    assert compact_history(history) == history


def test_no_history_shape_makes_compaction_grow_the_visible_conversation():
    """GIVEN 120 seeded conversation shapes (tool blocks, system rows, ledgers)
    WHEN compacted THEN the count never rises."""
    import random

    from core.conversation_compactor import compact_history

    def shape(rng: random.Random) -> list[dict]:
        history: list[dict] = []
        while len(history) < rng.randint(0, 80):
            kind = rng.choice(("user", "assistant", "system", "ledger", "block"))
            if kind == "block":
                calls = rng.randint(1, 6)
                history.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": f"c{len(history)}_{i}", "function": {"name": "f", "arguments": "{}"}}
                        for i in range(calls)
                    ],
                })
                history.extend({"role": "tool", "content": f"r{i}"} for i in range(calls))
                continue
            content = f"{kind} message {len(history)} " + "x" * rng.randint(0, 40)
            if kind == "ledger":
                history.append({"role": "system", "content": "Working Memory Ledger for Ephe.\n## Decisions\n- old"})
                continue
            history.append({"role": kind, "content": content})
        return history

    rng = random.Random(102)
    for _case in range(120):
        history = shape(rng)
        compacted = compact_history(history)
        assert len(compacted) <= len(history), f"{len(compacted)} > {len(history)}"


def test_a_system_block_in_the_middle_survives_whole():
    """GIVEN a skill prompt that arrives as a system row inside the history
    WHEN compacted THEN it is still there, byte for byte, and the count still falls."""
    from core.conversation_compactor import compact_history

    skill = "SKILL PROMPT: the deck job writes one file and validates it.\n" * 20
    history = _talk_history(30)
    history.insert(5, {"role": "system", "content": skill})

    compacted = compact_history(history)

    assert len(compacted) <= len(history)
    assert any(m.get("content") == skill for m in compacted)


def test_a_creator_tool_block_is_never_split_and_never_invents_messages():
    """GIVEN a Creator turn whose whole tail is one atomic tool block
    WHEN compacted THEN the block stays complete and no message is added."""
    from core.conversation_compactor import compact_history

    history = _creator_history(65)
    compacted = compact_history(history)

    assert len(history) == 67
    assert len(compacted) <= len(history)
    for index, message in enumerate(compacted):
        if not message.get("tool_calls"):
            continue
        answers = 0
        cursor = index + 1
        while cursor < len(compacted) and compacted[cursor].get("role") == "tool":
            answers += 1
            cursor += 1
        assert answers == len(message["tool_calls"]), "a tool block was cut"
    # No answer without the block that opened it: an orphan is the 400 the wire refuses.
    assert all(
        any(earlier.get("tool_calls") for earlier in compacted[:index])
        for index, message in enumerate(compacted)
        if message.get("role") == "tool"
    )
