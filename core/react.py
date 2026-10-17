"""
◑ Ephe – ReAct / Reflexion Engine
core/react.py

ReAct = Reason + Act + Observe + Reflect

Flow:
  1. Generate an answer (via chat_with_tools – incl. tool calls) → stream LIVE
  2. Reflection: is the answer complete and correct? (exactly ONCE)
  3. If needs_revision=True: prepare the revision, run one more iteration
  4. The final answer is streamed and returned

Design decisions:
  - MAX_REVISIONS = 2 (hard safety limit, no infinite loop)
  - reflect() runs exactly ONCE — right after iteration 1
    (identical to the PWA /chat/stream pipeline: answer → reflection → revision → done)
  - All iterations stream LIVE (on_chunk in every pass)
  - on_step callback after every iteration for full transparency
  - reflect(): fail-safe (exception → needs_revision=False)
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from core.chat import (
    _native_thinking_kwargs,
    _resolve_provider,
    chat_with_tools,
)
from core.model_provider import ModelProviderConfig, build_provider_client

if TYPE_CHECKING:
    from core.tools.approval import ApprovalPolicy


# Constants

MAX_REVISIONS = 2

REFLEXION_SYSTEM_PROMPT = """You are a precise quality reviewer for AI agent answers.

Your task: judge whether a given answer is correct and complete.

Reply ONLY with:
  - A short assessment (1-2 sentences)
  - Exactly one of these lines:
      REVISION: YES  (if the answer is incomplete, wrong or misleading)
      REVISION: NO   (if the answer is correct and sufficiently complete)
  - If YES: one sentence of reasoning after "Reason: "

Be strict but fair. Short answers that fully answer the question are OK.
"I don't know" is ALWAYS bad when tools are available.
"""


# Data Classes

@dataclass
class ReflexionResult:
    """Result of one reflection step.

    P2-12 (deep audit 2026-09-13): `status` separates 'ok' (clear parser
    signal), 'no_revision' (clear no) and 'provider_error' (exception/empty
    output). Before this every provider failure collapsed into the same
    needs_revision=False as 'the answer is good' — the consumer could no longer
    tell a failure apart from quality-OK.
    """
    needs_revision: bool
    reason: str = ""
    status: str = "ok"


@dataclass
class ReActStep:
    """A single step in the ReAct loop (for the on_step callback)."""
    iteration: int
    answer: str
    reflexion: ReflexionResult
    was_revised: bool = False


# reflect()

async def reflect(
    response: str,
    question: str,
    model: str,
    provider_config: ModelProviderConfig | None = None,
    api_url: str | None = None,
) -> ReflexionResult:
    """
    Rates an answer through a separate LLM call.

    No tool calling — pure text output.
    Fail-safe: any error → needs_revision=False (still emit the answer).

    Args:
        response: the answer to rate
        question: the original question
        model:    Ollama model

    Returns:
        ReflexionResult(needs_revision=bool, reason=str)
    """
    provider = _resolve_provider(model, provider_config, api_url)
    try:
        client = build_provider_client(provider)
    except Exception:
        return ReflexionResult(needs_revision=False, reason="", status="provider_error")

    prompt = (
        f"Frage: {question}\n\nAnswer to evaluate:\n{response}\n\nIs this answer correct and complete?"
    )

    try:
        raw = await asyncio.wait_for(
            client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": REFLEXION_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                stream=False,
                **_native_thinking_kwargs(model),
            ),
            timeout=30.0,
        )
        content: str = raw.message.content or ""
    except Exception:
        return ReflexionResult(needs_revision=False, reason="", status="provider_error")

    return _parse_reflexion(content)


def _parse_reflexion(content: str) -> ReflexionResult:
    """
    Reads the REVISION flag out of the model's answer.
    Expects 'REVISION: YES' or 'REVISION: NO' (EN prompt) —
    also tolerates 'REVISION: JA'/'NEIN' (DE variant).
    Falls back to needs_revision=False when there is no clear signal.

    Fix E1: the parser used to match only 'JA' (DE) while the prompt returns
    'YES' (EN) → a revision always came back as needs_revision=False.
    Now: both formats are recognised.
    """
    upper = content.upper()

    has_revision = (
        "REVISION: YES" in upper or "REVISION:YES" in upper
        or "REVISION: JA" in upper or "REVISION:JA" in upper
    )

    if has_revision:
        reason_match = re.search(
            r"(?:Reason|Grund):\s*(.+)", content, re.IGNORECASE
        )
        reason = reason_match.group(1).strip() if reason_match else content[:120].strip()
        return ReflexionResult(needs_revision=True, reason=reason, status="ok")

    if not content.strip():
        return ReflexionResult(needs_revision=False, reason="", status="provider_error")
    return ReflexionResult(needs_revision=False, reason="", status="no_revision")


# react_loop()

async def react_loop(
    question: str,
    model: str,
    context: list[dict] | None = None,
    on_step: Callable[[ReActStep], None] | None = None,
    on_chunk: Callable[[str], None] | None = None,
    on_revision: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    on_phase: Callable[[str], None] | None = None,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_done: Callable[[str, str], None] | None = None,
    provider_config: ModelProviderConfig | None = None,
    api_url: str | None = None,
    approval_policy: "ApprovalPolicy | None" = None,
    on_tool_confirm: Callable[[str, dict], object] | None = None,
    allowed_tool_names: "list[str] | None" = None,
    extra_system_prompt: str | None = None,
    session_id: str = "",
    turn_id: str = "",
) -> str:
    """
    ReAct loop with reflection-based self-correction.

    GUARANTEES:
      - always terminates (max 2 iterations: answer + 1 revision)
      - the answer streams LIVE (on_chunk during generation) —
        the user sees every sentence as soon as it is produced, NOT only after
        the reflect() roundtrip
      - on_revision(reason) is called before a revision so the
        consumer (TUI/PWA) can reset its answer view
      - reflect() runs exactly ONCE (after iteration 1) —
        PWA /chat/stream semantics: no second reflection roundtrip
      - all exceptions (OllamaNotReachable, OllamaModelNotFound, Shell) propagate

    Flow (live-streaming standard, identical to the PWA /chat/stream pipeline):
      Iteration 1:
        a) chat_with_tools() → stream the answer LIVE via on_chunk
        b) reflect() → needs_revision?
        c) yes → on_revision(reason), build the revision context, iteration 2
        d) no → stop (the answer is already visible)
      Iteration 2 (only with a revision):
        a) chat_with_tools() → stream the improved answer LIVE
        b) do NOT call reflect() again (PWA: no second reflection)

    Args:
        question:      user question (last element of the history)
        model:         Ollama model
        context:       history WITHOUT the current question
        on_step:       callback after every iteration (transparency)
        on_chunk:      LIVE streaming callback for the answer (all iterations)
        on_revision:   callback BEFORE a revision streams (consumer reset)
        on_tool_start: tool start callback (all iterations)
        on_tool_done:  tool done callback (all iterations)
        turn_id:       run id the audit lines of this run carry (B1); empty = as before

    Returns:
        The best generated answer as a string.

    Raises:
        OllamaNotReachableError:   Ollama not reachable
        OllamaModelNotFoundError:  model not installed
        ShellConfirmationRequired: shell needs user confirmation
    """
    history: list[dict] = list(context or [])
    history.append({"role": "user", "content": question})

    # on_chunk=None (e.g. the synchronous /chat route, the scheduler): a no-op instead of a crash.
    # chat_with_tools expects a callable on_chunk (required parameter).
    live_chunk: Callable[[str], None] = on_chunk if on_chunk is not None else (lambda _c: None)

    last_answer = ""
    reflected_once = False
    max_iterations = MAX_REVISIONS + 1  # hard safety limit

    for iteration in range(1, max_iterations + 1):
        # LLM call (LIVE streaming)
        # on_chunk/on_thinking/on_phase: visible in EVERY pass — the
        # internal thinking and the answer are the agent process, not batch output.
        answer = await chat_with_tools(
            model=model,
            history=history,
            on_chunk=live_chunk,
            on_thinking=on_thinking,
            on_phase=on_phase,
            on_tool_start=on_tool_start,
            on_tool_done=on_tool_done,
            api_url=api_url,
            provider_config=provider_config,
            approval_policy=approval_policy,
            on_tool_confirm=on_tool_confirm,
            allowed_tool_names=allowed_tool_names,
            extra_system_prompt=extra_system_prompt,
            # B1: the run record filters the audit log by this id — every tool and
            # approval line of the turn carries it, no caller-side guessing.
            # G7: session_id names the turn the injected memories are recorded on.
            session_id=session_id,
            turn_id=turn_id,
        )

        last_answer = answer or ""

        # Reflection: exactly ONCE (PWA /chat/stream semantics)
        # Answer → reflection → (revision) → done. NO second reflect()
        # roundtrip: the answer is already visible LIVE, a second
        # LLM call would be a ~8s gap without visible progress.
        if not reflected_once:
            reflected_once = True
            reflexion = await reflect(
                response=last_answer,
                question=question,
                model=model,
                api_url=api_url,
                provider_config=provider_config,
            )
        else:
            # Revision iteration (or safety end): no 2nd reflection.
            reflexion = ReflexionResult(needs_revision=False, reason="")

        step = ReActStep(
            iteration=iteration,
            answer=last_answer,
            reflexion=reflexion,
            was_revised=(iteration > 1),
        )
        if on_step is not None:
            on_step(step)

        if not reflexion.needs_revision:
            # The answer is good — it is already visible LIVE. Stop.
            break

        # Prepare the revision
        # Consumer reset: the TUI clears its answer accumulator with this
        # before the (improved) revision streams — like the PWA
        # "revision" event. WITHOUT this call iteration 2 would append to iteration 1
        # and the user would see the answer twice.
        if on_revision is not None:
            on_revision(reflexion.reason)

        history.append({"role": "assistant", "content": last_answer})
        # This message is the newest turn of the thread and it is written by us, so it decides what
        # the revision answers and in which language. Measured 2026-10-11 in
        # ~/.ephe/trajectory.json, turn 62c693670866: a German first answer was followed by an English
        # revision, and the critique text also read as a fresh request ("no question or task from
        # you"), which is why it names itself and points back at the user's own last request.
        history.append({
            "role": "user",
            "content": (
                "[System-generated critique of your own previous answer — not a message from the "
                "user, and not a new request.]\n"
                f"Your answer was incomplete or faulty.\nCritique: {reflexion.reason}\n\n"
                "Provide an improved, complete answer to the user's own last request, in the language "
                "that request is written in."
            ),
        })

    return last_answer
