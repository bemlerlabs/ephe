"""The ask gate: the run pauses on a real question and goes on with the answer.

What this replaces: `core/persona.py` hands the model the `AskUserQuestion` JSON
block. The block lands in the finished answer text, `app/src/lib/askUserQuestion.ts`
parses it, and `AskUserQuestionCard` renders it. Two limits came with that
convention. The card sits behind `!m.streaming`
(`app/src/components/dashboard/bubble/assistantExtras.tsx`), so the question can only
appear after the turn is over. And a click sends the label as a NEW turn
(`handlePickOption` -> `handleSend`), so the run that asked never hears the answer.

Here the question is a tool call. The engine awaits it inside the running turn, the
SSE handler renders it while the turn is still open, and the answer arrives as this
tool's result — in context, in the same tool loop.

The waiting machinery is the sandbox approval gate (`server/routes/chat.py`,
`_sandbox_confirm`) with the same three parts: the dialog callback travels in a
ContextVar (`set_ask_cb`, the shape `core.vision.set_sandbox_confirm_cb` set up), the
pending ask is registered under a token in an app-wide dict, and one HTTP endpoint
resolves that token the way `POST /api/sandbox/approve` resolves a confirmation.

A missing answer is never a hang. Without a dialog callback (CLI, cron, a test) the
call returns the run's stated default at once, and the same happens when the dialog is
there and the human stays away past the timeout.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from core.reason import reason

#: Seconds a pending ask stays open before the turn continues on the stated default.
#: The reader's idle detector (`app/src/lib/stream.ts`) sees the route's keepalive
#: comments, so this number is a product decision rather than a transport limit: 180 s
#: is the order the approval dialog leaves a human at the keyboard.
ASK_TIMEOUT_SECONDS: float = 180.0

#: Raise the ceiling for a longer deliberation (EPHE_ASK_TIMEOUT_S). A malformed value
#: keeps the default, so a typo never removes the bound.
def _ask_timeout_s() -> float:
    try:
        value = float(os.environ.get("EPHE_ASK_TIMEOUT_S", "") or ASK_TIMEOUT_SECONDS)
    except ValueError:
        return ASK_TIMEOUT_SECONDS
    return value if value > 0 else ASK_TIMEOUT_SECONDS


#: The route's dialog: called with the question's keyword arguments, answered with the
#: human's text. Request-scoped, because every turn carries its own SSE stream.
AskCallback = Callable[..., Awaitable[str]]

_ask_cb_var: ContextVar[AskCallback | None] = ContextVar("ephe_ask_cb", default=None)


def set_ask_cb(cb: AskCallback | None) -> None:
    """Registers the request-scoped dialog callback (the SSE handler calls this)."""
    _ask_cb_var.set(cb)


def get_ask_cb() -> AskCallback | None:
    return _ask_cb_var.get()


#: token -> {"event", "answer", "question"}. App-wide, not request-scoped, for the same
#: reason `_active_sandbox_events` is a module global on the route: the answer arrives
#: on its own HTTP connection and has to find the waiting turn by token alone.
_ACTIVE_ASKS: dict[str, dict] = {}


def register_ask(question: str) -> tuple[str, dict]:
    """Opens a pending ask; the caller emits the frame and awaits `event`."""
    token = str(uuid.uuid4())
    entry: dict = {"event": asyncio.Event(), "answer": "", "question": question}
    _ACTIVE_ASKS[token] = entry
    return token, entry


def resolve_ask(token: str, answer: str) -> bool:
    """Wakes the waiting turn. False = unknown or already finished token."""
    entry = _ACTIVE_ASKS.get(token)
    if entry is None:
        return False
    entry["answer"] = answer
    entry["event"].set()
    return True


def discard_ask(token: str) -> None:
    """Drops a pending ask that can no longer be answered (turn cancelled, timeout)."""
    _ACTIVE_ASKS.pop(token, None)


def active_ask_count() -> int:
    """Live pending asks — the registry's own count, for the surface that reports it."""
    return len(_ACTIVE_ASKS)


def parse_options(options: str) -> list[str]:
    """The offered labels, one per line or separated by ';' or '|' (the todo_list shape)."""
    raw = (options or "").replace(";", "\n").replace("|", "\n")
    return [label.strip() for label in raw.splitlines() if label.strip()]


def _continuation(why: str, default: str, recommendation: str) -> str:
    """The sentence a run reads when it has to go on without an answer.

    It names the reason, so the answer the human reads later owns the assumption the
    turn acted on. A run without a stated default is told to name its own.
    """
    stated = (default or recommendation or "").strip()
    if stated:
        return f"[ask_user] {why}. Continuing with: \"{stated}\""
    return (
        f"[ask_user] {why}. No default was stated, so the run continues without a "
        "decision — name the assumption you act on as an assumption."
    )


async def ask_user(
    question: str,
    options: str = "",
    recommendation: str = "",
    default: str = "",
    multi_select: bool = False,
    timeout_seconds: float | None = None,
) -> str:
    """Pauses the run and asks the human a question.

    Args:
        question: what to ask, in one sentence.
        options: offered answers, one per line (or ';'/'|' separated).
        recommendation: the label to mark as the recommended one.
        default: what the run does when nobody answers in time.
        multi_select: allow more than one option.
        timeout_seconds: how long to wait (default: ASK_TIMEOUT_SECONDS).

    Returns:
        The answer, or a sentence naming why the run continues without one.
    """
    question = (question or "").strip()
    if not question:
        return reason(
            "ask_user_needs_question",
            "[ask_user] A question is required — 0 characters were passed, so nothing was asked.",
        )

    cb = _ask_cb_var.get()
    if cb is None:
        # No dialog in this process: the run answers with what it stated itself, so a
        # CLI, a cron turn or a test continues instead of parking on an Event nobody sets.
        return _continuation("no interactive channel is attached to this turn", default, recommendation)

    timeout = _ask_timeout_s() if timeout_seconds is None else float(timeout_seconds)
    try:
        answer = await cb(
            question=question,
            options=parse_options(options),
            recommendation=(recommendation or "").strip(),
            default=(default or "").strip(),
            multi_select=bool(multi_select),
            timeout_seconds=timeout,
        )
    except asyncio.CancelledError:
        # The stop button cancels the turn; the tool call ends with it.
        raise
    except Exception as exc:  # a broken dialog must not take the turn down
        return _continuation(
            f"the question could not be delivered ({type(exc).__name__})", default, recommendation
        )

    answer = (answer or "").strip()
    if not answer:
        return _continuation(f"nobody answered within {timeout:g}s", default, recommendation)
    return f'[ask_user] The user answered: "{answer}"'


ASK_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Asks the human a question and WAITS for the answer inside this turn: the answer "
                "comes back as this tool's result, so the run continues with it in context. Use it "
                "when the decision is the user's (which of two paths, a value only they have) and "
                "the turn cannot honestly go on without it. Do not use it for a choice you can "
                "answer from the task itself. Pass `default` whenever the question has a safe "
                "continuation — nobody may answer, and the turn then runs on with that value."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question, one sentence, in the user's language.",
                    },
                    "options": {
                        "type": "string",
                        "description": (
                            "Offered answers, one per line (or ';'/'|' separated). Empty = free text."
                        ),
                    },
                    "recommendation": {
                        "type": "string",
                        "description": "The label to mark as recommended (may be a 1-based number).",
                    },
                    "default": {
                        "type": "string",
                        "description": (
                            "What the run does when the answer does not come in time — stated to "
                            "the user with the question and used as the continuation value."
                        ),
                    },
                    "multi_select": {
                        "type": "boolean",
                        "description": "Allow more than one option to be chosen.",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": (
                            f"Seconds to wait before continuing on `default` "
                            f"(default {ASK_TIMEOUT_SECONDS:g})."
                        ),
                    },
                },
                "required": ["question"],
            },
        },
    },
]
