"""Intent routing through the decision layer.

The deterministic intent path in ``core.skills`` (factory regexes first, artifact
regexes second) resolves a goal but keeps no record of the goals that were
legal. This module runs the same rules and returns the decision layer's typed
``Decision`` for the outcome, so the option set, the chosen intent, the cost and
the reversal can be audited afterwards.

The regex decides; the record documents. No engine or local probability is
consulted, so a plain sentence never becomes a network round trip and no second
decision path appears beside the deterministic one
(``docs/EPHE_DECISION_LAYER_2026-10-10.md``).

The route keys are the skill triggers an intent resolves to, plus ``none`` for a
message that carries no artifact or factory intent. Enablement belongs to the
skill loader: an intent is detected whatever the state of its skill, so the
record names the goal the message asks for.
"""

from __future__ import annotations

from collections.abc import Mapping

from core import decisions
from core.decisions import Decision, DecisionError
from core.skills import _ARTIFACT_INTENTS, _FACTORY_INTENTS

#: A message with no artifact or factory vocabulary.
NO_INTENT = "none"

#: How a chosen intent reverses: the same message without the vocabulary falls to
#: the IDF skill score, and to the ask path when that is empty too.
DEFAULT_REVERSAL = "drop to the IDF skill score, then the ask path"

_DESCRIPTIONS: dict[str, str] = {
    "/factory": "a whole project or repository built from a brief",
    "/doc-factory": "a briefing or whitepaper document",
    "/pdf": "a PDF document",
    "/deck": "a slide deck",
    "/diagram": "a structure diagram such as a mind map or timeline",
    "/chart": "a data chart",
    "/svg": "an SVG graphic",
    "/xlsx": "a spreadsheet",
    "/docx": "a Word document",
    "/qr": "a QR code",
    "/image": "a generated image",
    NO_INTENT: "no artifact or factory request",
}

#: The legal intent set, factory first: the priority order ``detect_intent`` uses.
INTENT_TRIGGERS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [trigger for _, trigger in _FACTORY_INTENTS]
        + [trigger for _, trigger in _ARTIFACT_INTENTS]
    )
)
LEGAL_INTENTS: tuple[str, ...] = (*INTENT_TRIGGERS, NO_INTENT)


def detect_intent(message: str) -> str:
    """The deterministic intent of a message: a skill trigger, or ``none``.

    Factory patterns win over artifact patterns, matching
    ``SkillLoader.resolve_for_message``; the first matching pattern wins inside
    each group.
    """
    text = message or ""
    for pattern, trigger in _FACTORY_INTENTS:
        if pattern.search(text):
            return trigger
    for pattern, trigger in _ARTIFACT_INTENTS:
        if pattern.search(text):
            return trigger
    return NO_INTENT


class _IntentBackend:
    """A decision backend that returns the detected intent as a one-hot distribution.

    The intent is read from the regexes, so the decision layer records a choice
    instead of taking one. ``score`` is the only surface ``route`` uses.
    """

    name = "deterministic"

    def __init__(self, chosen: str) -> None:
        self._chosen = chosen

    def score(self, state: str, options) -> dict[str, float]:
        if self._chosen not in options:
            raise DecisionError(f"{self._chosen!r} is not among the legal intents")
        return {option: (1.0 if option == self._chosen else 0.0) for option in options}


def route_intent(message: str, *, reversal: str = DEFAULT_REVERSAL) -> Decision:
    """Records the deterministic intent of a message as a decision-layer ``Decision``.

    ``options`` are the legal intents plus ``none``, ``chosen`` is the detected
    intent, and ``backend`` is ``deterministic`` on every path.
    """
    text = message or ""
    routes: Mapping[str, str] = {
        label: _DESCRIPTIONS.get(label, label) for label in LEGAL_INTENTS
    }
    return decisions.route(
        text, routes, backend=_IntentBackend(detect_intent(text)), reversal=reversal
    )
