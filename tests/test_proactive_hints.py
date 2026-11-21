"""
Proactive hints — GWT, 3 levels of depth.

GIVEN: the system prompt contains a rule for proactive memory hints
WHEN:  the prompt is checked for the keywords it must carry
THEN:  a clear instruction exists that Ephe proactively points at memory

GIVEN: memory holds relevant entries on a topic
WHEN:  get_context_injection() is called
THEN:  the context block carries a hint intro for the model

GIVEN: an empty memory store
WHEN:  get_context_injection() is called
THEN:  an empty string (no false-positive hint)
"""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _hermetic_memory_backend(tmp_path, monkeypatch):
    """Neither the machine's model files nor the real `~/.ephe` may decide these cases.

    The vector leg is materialised from model files this checkout does not carry:
    EmbeddingGemma under `~/.ephe/models` (which honours `EPHE_CONFIG_DIR`) and the
    MiniLM fallback under `~/.cache/chroma/onnx_models`. On a developer laptop one of
    them is present, so a query that only *means* the same thing still clears the
    similarity floor; on a clean runner neither is, `get_embedder()` returns None and
    retrieval is the lexical and entity legs alone. Left alone the outcome would be a
    property of the machine, not of the code.

    The documented kill switch pins the vector leg off here, and an empty config root
    keeps the injection policy (`memory.inject_min_score`) from being read out of the
    real `~/.ephe`. Each case then states which legs it exercises.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "lexical")


# Angle 1: the system prompt carries the proactive rule

class TestProactiveHintSystemPromptPerspective:
    """GIVEN the system prompt, WHEN inspected, THEN proactive memory hint rule exists."""

    def test_given_system_prompt_when_checked_then_has_proactive_hint_rule(self):
        """
        GIVEN: EPHE_SYSTEM_PROMPT is loaded
        WHEN:  the prompt is checked for proactive hint logic
        THEN:  at least one rule instructs Ephe to point at memory on its own
        """
        from core.chat import assemble_system_prompt

        # R28: the prompt is assembled (identity block + persona + guidelines)
        EPHE_SYSTEM_PROMPT = assemble_system_prompt(model="test-model")

        # Angle 1: the keyword "previously" or "noted" is present
        has_proactive = any(kw in EPHE_SYSTEM_PROMPT.lower() for kw in [
            "previously", "noted", "proactive", "mentioned before",
            "you already", "remember", "context"
        ])
        assert has_proactive, (
            "THEN: Prompt muss proaktive Hinweis-Regel enthalten, got:\n"
            + EPHE_SYSTEM_PROMPT[:300]
        )

        # Angle 2: the rule names what it targets
        assert "memory" in EPHE_SYSTEM_PROMPT.lower() or "context" in EPHE_SYSTEM_PROMPT.lower(), (
            "THEN: Prompt soll Memory-Kontext explizit ansprechen"
        )

        # Angle 3: the rule sits in its own section
        assert "\n" in EPHE_SYSTEM_PROMPT, "THEN: Prompt muss mehrzeilig strukturiert sein"


# Angle 2: memory context injection has a hint intro

class TestProactiveHintMemoryInjectionPerspective:
    """GIVEN memory entries, WHEN context injected, THEN hint prefix present."""

    def test_given_memory_entries_when_context_injected_then_hint_prefix_present(self, tmp_path):
        """
        GIVEN: the memory store has one entry on a topic
        WHEN:  get_context_injection() is called with a related query
        THEN:  the return value contains a context block (not empty)
        """
        from core.memory import Memory

        mem = Memory(persist_dir=str(tmp_path / "chroma"), collection_name="test_proactive")
        mem.store("Der Nutzer arbeitet an einem KI-Assistenten namens Ephe.", {"source": "test"})

        # Angle 1: the context block is not empty for a relevant query
        ctx = mem.get_context_injection("Ephe KI-Assistent")
        assert len(ctx.strip()) > 0, "THEN: Kontext-Block muss Inhalt haben"

        # Angle 2: the context contains the stored text
        assert "Ephe" in ctx or "KI" in ctx or "Assistent" in ctx, (
            f"THEN: Kontext muss relevante Daten enthalten, got: {ctx[:200]}"
        )

        # Angle 3: the context has a structured intro
        first_line = ctx.strip().split("\n")[0]
        assert len(first_line) > 5, "THEN: Erster Block muss Einleitungs-Header haben"

    def test_given_empty_memory_when_context_injected_then_empty_string(self, tmp_path, monkeypatch):
        """
        GIVEN: the memory store is empty
        WHEN:  get_context_injection() is called
        THEN:  an empty string — no false positive
        """
        from core.memory import Memory

        # Empty config root -> no legacy migration into the tmp collection.
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        mem = Memory(persist_dir=str(tmp_path / "chroma2"), collection_name="test_empty")

        ctx = mem.get_context_injection("beliebiger Query")

        # Angle 1: empty when nothing was stored
        assert ctx == "", (
            f"THEN: Leerer Memory muss leeren String zurückgeben, got: '{ctx[:100]}'"
        )

        # Angle 2: no whitespace-only output
        assert ctx.strip() == "", "THEN: Kein Whitespace-only Output"

        # Angle 3: no crash on an empty store
        # (the test itself is the proof — no exception)


# Angle 3: proactive wording in the context prefix

class TestProactiveHintContextPrefixPerspective:
    """GIVEN memory with entries, WHEN prefix inspected, THEN it signals prior knowledge."""

    def test_given_memory_with_entries_when_prefix_read_then_signals_prior_knowledge(self, tmp_path):
        """
        GIVEN: memory has entries
        WHEN:  the prefix of the context block is read
        THEN:  the wording signals "said earlier / already known"
        """
        from core.memory import Memory

        mem = Memory(persist_dir=str(tmp_path / "chroma3"), collection_name="test_prefix")
        mem.store("Lieblingsfarbe des Nutzers ist Blau.", {"source": "test"})

        # The query names its topic in words rather than alluding to it: with the embedding
        # model absent (an offline runner, no `~/.ephe/models` copy) retrieval is the lexical
        # and entity legs alone, and "Farbe" by itself never clears the similarity floor.
        ctx = mem.get_context_injection("Lieblingsfarbe des Nutzers")

        # Angle 1: present and structured
        assert len(ctx) > 0, "THEN: Kontext muss Inhalt haben"

        # Angle 2: contains marker words that signal prior knowledge
        ctx_lower = ctx.lower()
        has_prior_signal = any(kw in ctx_lower for kw in [
            "memory", "context", "known", "remember", "earlier",
            "erinnerung", "kontext", "bekannt", "früher", "already"
        ])
        assert has_prior_signal, (
            f"THEN: Kontext-Block soll Prior Knowledge signalisieren, got:\n{ctx[:300]}"
        )
