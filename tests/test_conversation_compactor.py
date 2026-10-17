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
