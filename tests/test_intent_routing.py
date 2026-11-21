"""Intent routing: a message's deterministic intent as a decision-layer record.

Given a message with artifact or factory vocabulary, ``route_intent`` names the
intent the deterministic path would take and attaches the option set that was
legal, so the routing is auditable after the fact (core/intent.py).
"""
from __future__ import annotations

import pytest

from core.decisions import Decision
from core.intent import (
    DEFAULT_REVERSAL,
    LEGAL_INTENTS,
    NO_INTENT,
    detect_intent,
    route_intent,
)
from core.skills import SkillLoader


def test_pdf_intent_is_routed_and_recorded():
    """GIVEN 'erstelle ein PDF' WHEN route_intent THEN verb route, chosen /pdf,
    deterministic backend."""
    decision = route_intent("erstelle ein PDF aus diesen Daten: a; b")  # language-gate: ignore (quoted German utterance under test)
    assert isinstance(decision, Decision)
    assert decision.verb == "route"
    assert decision.chosen == "/pdf"
    assert decision.backend == "deterministic"
    assert decision.confidence == 1.0
    assert decision.cost_seconds >= 0.0


def test_both_word_orders_share_the_intent():
    """GIVEN 'ein PDF erstellen' and 'erstelle ein PDF' WHEN detect_intent
    THEN both are /pdf (the table carries both orders)."""
    orders = ("Ein PDF erstellen mit den Zahlen.", "Erstelle ein PDF mit den Zahlen.")  # language-gate: ignore (quoted German word orders under test)
    assert [detect_intent(order) for order in orders] == ["/pdf", "/pdf"]


def test_factory_intent_outranks_artifact_intent():
    """GIVEN a message carrying both factory and artifact vocabulary
    WHEN detect_intent THEN the factory intent wins (priority order)."""
    msg = "Baue mir ein komplettes Projekt aus einem Briefing-PDF"  # language-gate: ignore (quoted German utterance under test)
    assert detect_intent(msg) == "/factory"


def test_diagram_intent_beats_generic_chart():
    """GIVEN 'Mindmap erstellen' WHEN detect_intent THEN /diagram rather than /chart."""
    assert detect_intent("Erstell eine Mindmap zum Projekt Phoenix.") == "/diagram"  # language-gate: ignore (quoted German utterance under test)


def test_plain_message_records_no_intent():
    """GIVEN a message with no artifact or factory vocabulary WHEN route_intent
    THEN chosen is none and none is a legal option."""
    decision = route_intent("Wie geht es dir heute?")  # language-gate: ignore (quoted German utterance under test)
    assert decision.chosen == NO_INTENT
    assert NO_INTENT in decision.options


def test_option_set_is_every_legal_intent_plus_none():
    """GIVEN any routed message WHEN the decision is read THEN options are the
    full legal intent set, so what else was possible is checkable."""
    decision = route_intent("erstelle ein PDF")  # language-gate: ignore (quoted German utterance under test)
    assert decision.options == LEGAL_INTENTS
    assert len(set(decision.options)) == len(decision.options)  # no duplicate intent in the legal set
    for trigger in LEGAL_INTENTS:
        if trigger != NO_INTENT:
            assert trigger.startswith("/")


def test_the_legal_set_covers_the_artifact_and_factory_targets():
    """GIVEN the shipped intent tables WHEN LEGAL_INTENTS is read THEN every
    target trigger is present (nine artifacts, two factory)."""
    artifacts = {"/pdf", "/deck", "/diagram", "/chart", "/svg", "/xlsx", "/docx", "/qr", "/image"}
    assert artifacts <= set(LEGAL_INTENTS)
    assert {"/factory", "/doc-factory"} <= set(LEGAL_INTENTS)


def test_reversal_is_named():
    """GIVEN a routed message WHEN the decision is read THEN the reversal names
    the fallback, so an auditor sees how the choice undoes."""
    assert route_intent("erstelle ein PDF").reversal == DEFAULT_REVERSAL  # language-gate: ignore (quoted German utterance under test)


def test_explicit_tool_name_is_not_an_intent():
    """GIVEN a message that names a tool but no artifact or factory noun
    WHEN detect_intent THEN none (the tool path belongs to the skill loader,
    never the intent path)."""
    msg = "Fuehre den Shell-Befehl mit run_shell aus und antworte."  # language-gate: ignore (quoted German utterance under test)
    assert detect_intent(msg) == NO_INTENT


def test_compound_word_does_not_fire_the_image_intent():
    """GIVEN 'Bildschirmfoto' (a compound and never the noun 'Bild') WHEN
    detect_intent THEN none (the word-boundary guard holds)."""
    assert detect_intent("Analysiere das Bildschirmfoto vom Fehler.") == NO_INTENT  # language-gate: ignore (quoted German utterance under test)


@pytest.mark.parametrize("message", [  # language-gate: ignore (German sample utterances under test)
    "erstelle ein PDF",  # language-gate: ignore (German sample utterance under test)
    "Baue mir ein Pitch-Deck ueber unser Startup.",  # language-gate: ignore (German sample utterance under test)
    "Erstell mir ein Diagramm vom Umsatz 2025.",  # language-gate: ignore (German sample utterance under test)
    "Schreib mir ein Word-Dokument zum Projekt.",  # language-gate: ignore (German sample utterance under test)
    "Erstell mir ein Bild von einem Fuchs im Wald.",  # language-gate: ignore (German sample utterance under test)
    "Baue mir ein komplettes Projekt aus einem Briefing",  # language-gate: ignore (German sample utterance under test)
])
def test_intent_agrees_with_the_skill_resolver(message):
    """GIVEN a message the skill loader routes onto its intent path
    WHEN the intent record is compared to the resolved skill
    THEN the chosen intent is the trigger of that skill."""
    skill = SkillLoader().resolve_for_message(message)
    assert skill is not None
    assert route_intent(message).chosen == skill.trigger
