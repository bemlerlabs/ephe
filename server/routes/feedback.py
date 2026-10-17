"""server/routes/feedback.py – POST /api/feedback/thumbs_up + thumbs_down

PDCA #4: thumbs_down now also writes into CorrectionJournal, so the negative
feedback loop is closed.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.feedback import FeedbackStore
from core.corrections import CorrectionJournal

router = APIRouter(tags=["Feedback"])


def _get_store() -> FeedbackStore:
    """FeedbackStore with the configured base path (testable via ENV)."""
    base = os.environ.get("EPHE_FEEDBACK_DIR")
    return FeedbackStore(base_dir=Path(base)) if base else FeedbackStore()


def _get_journal() -> CorrectionJournal:
    """CorrectionJournal for the negative feedback loop."""
    return CorrectionJournal()


# Pydantic Models

class FeedbackRequest(BaseModel):
    prompt: str
    response: str
    reason: Optional[str] = None   # e.g. "Zu lang", "Falsch", "Nicht hilfreich" — verbatim reason values the UI sends  # language-gate: ignore (product values, app/src/locales/de.json:72; asserted in tests/test_pwa_visual.py:1000)


class FeedbackResponse(BaseModel):
    saved: bool
    # Only for a thumbs-down with a reason: did the correction journal receive the
    # improvement? None when no reason was sent at all — not a state we invent.
    journal: bool | None = None


# Routes

@router.post("/feedback/thumbs_up", response_model=FeedbackResponse)
async def thumbs_up(request: FeedbackRequest) -> FeedbackResponse:
    """Store a positive feedback example.
    Injected as few-shot context on every chat call.
    """
    store = _get_store()
    saved = store.thumbs_up(prompt=request.prompt, response=request.response)
    return FeedbackResponse(saved=saved)


@router.post("/feedback/thumbs_down", response_model=FeedbackResponse)
async def thumbs_down(request: FeedbackRequest) -> FeedbackResponse:
    """Store a negative feedback example.

    PDCA #4: closes the negative feedback loop:
      1. FeedbackStore.thumbs_down() → bad_examples/ (pre-existing)
      2. NEW: CorrectionJournal.add() → injected into the system prompt on the
         next chat call → Ephe improves itself
    """
    store = _get_store()
    saved = store.thumbs_down(prompt=request.prompt, response=request.response)

    # Close the negative loop: reason → CorrectionJournal
    journal: bool | None = None
    if request.reason:
        journal = False
        try:
            journal_store = _get_journal()
            correction_text = f"Avoid this in similar requests: {request.reason}"
            journal_store.add(
                wrong=request.prompt[:200],
                correct=correction_text,
            )
            journal = True
        except Exception:
            logging.getLogger("ephe").exception(
                "correction journal rejected the reason"
            )  # Fail-safe: the feedback is stored even when the journal fails

    return FeedbackResponse(saved=saved, journal=journal)
