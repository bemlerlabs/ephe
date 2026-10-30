"""
◑ Ephe – Chat Engine

Async streaming wrapper around the Ollama Python client.
Includes Tool-Calling Loop for agentic workflows.

Designed to be called exclusively from @work workers (Textual / FastAPI).
No UI knowledge lives here – pure async Python.

Tool-Calling Architecture:
    1. Non-streaming call with tools → detect tool_calls (stream=False REQUIRED)
    2. Execute each tool via core.tools.execute_tool()
    3. Stream final answer (stream=True for smooth UX)

    stream=False for tool detection is REQUIRED.
    Known Ollama limit: tool calls break with stream=True.


Split (2026-10-11): the implementation lives in the core/chat_* modules
(chat_stream, chat_prompt, chat_context, chat_detect, chat_providers,
chat_tools). core/chat.py keeps the compatibility surface intact: every name
importers and tests use is re-exported below, and the names tests patch on
``core.chat`` (ollama, asyncio, build_provider_client, execute_tool,
_tool_detection_timeout, ...) stay bound here — the moved code reads them
back from this module at call time, so patching keeps working."""

from __future__ import annotations

import asyncio  # noqa: F401  # seam: tests patch core.chat.asyncio.sleep
from collections.abc import Callable

import ollama  # seam: tests patch core.chat.ollama.AsyncClient

from core.chat_context import (  # noqa: F401
    _TOOL_SCHEMA_CACHE,
    TOOL_SCHEMA_CACHE_TTL_SECONDS,
    _active_context_window,
    _budget_exhausted_note,
    _cached_tool_schemas,
    _cap_tool_result,
    _fit_messages_to_window,
    _has_uploaded_images,
    _tool_result_cap,
    _tools_for_messages,
)
from core.chat_detect import (  # noqa: F401
    _call_id,
    _detect_tool_calls,
    _finalize_budget_exhausted,
    _follow_up_with_retry,
    _parse_tool_calls,
    _stream_detect_openai,
)
from core.chat_prompt import (  # noqa: F401
    _OPEN_PLAN_NUDGE,
    DISABLE_NATIVE_THINKING_MODELS,
    NATIVE_THINKING_MODELS,
    THINK_CLOSE,
    THINK_OPEN,
    TOOL_DETECT_TIMEOUT_DEFAULT,
    TOOL_DETECT_TIMEOUT_LARGE_REASONING,
    TOOL_DETECT_TIMEOUT_SMALL_MODEL,
    _assemble_system_prompt_into,
    _continue_attempts,
    _looks_like_open_plan,
    _model_param_billions,
    _native_thinking_kwargs,
    _tool_detection_timeout,
    assemble_system_prompt,
    supports_native_thinking,
)
from core.chat_providers import (  # noqa: F401
    _engine_reachable,
    _format_model_size,
    _is_chat_model_option,
    _model_attr,
    _model_details,
    _resolve_provider,
    check_engine_connection,
    check_ollama_connection,
    list_local_model_options,
    list_local_models,
)
from core.chat_stream import (  # noqa: F401
    FIRST_CHUNK_TIMEOUT,
    EngineNotReachableError,
    OllamaModelBusyError,
    OllamaModelNotFoundError,
    OllamaNotReachableError,
    ThinkingStreamParser,
    _emit_final_answer,
    _stream_delay_seconds,
    send_message_safe,
    stream_response,
)
from core.chat_tools import _run_tool_loop  # noqa: F401
from core.conversation_compactor import compact_history  # noqa: F401
from core.loop_observability import (  # noqa: F401
    STOP_BUDGET,
    LoopCounters,
    LoopObserver,
    bind_observer,
    current_stop_reason,
    note_budget_exhausted,
    note_compaction,
    note_turn_end,
    reset_observer,
)
from core.corrections import CorrectionJournal  # noqa: F401
from core.feedback import FeedbackStore  # noqa: F401
from core.memory import Memory  # noqa: F401
from core.model_provider import (  # noqa: F401
    DEFAULT_OLLAMA_BASE_URL,
    ModelProviderConfig,
    ProviderChatResponse,
    ProviderFunctionCall,
    ProviderMessage,
    ProviderToolCall,
    _parse_json_arguments,
    build_engine_provider,
    build_provider_client,
    get_active_provider,
    resolve_active_with_failover,
)
from core.profile import load_profile  # noqa: F401
from core.quality import normalize_tool_result  # noqa: F401
from core.tools import (  # noqa: F401
    ShellConfirmationRequired,
    execute_confirmed_shell,
    execute_tool,
    get_tool_schemas,
)
from core.tools.approval import ApprovalPolicy  # noqa: F401
from core.tools.chat_gate import confirm_for_chat, denial_message  # noqa: F401
from core.tools.session_ctx import record_measured_usage  # noqa: F401
from core.types import Message  # noqa: F401
from core.usage import estimate_tokens, serialize_prompt  # noqa: F401

# Maximum tool-calling iterations to prevent infinite loops
# R43: coding sessions need more room than the old casual 5 — without the user
# having to push more in; hard cap = effective /ephe budget = 40.
# R46 (owner live audit 28.09.): the normal chat IS coding mode — 10 rounds
# cut real assignments ("arbeite alles ab") off in the middle of the work. Default 25  # language-gate: ignore (quoted German user utterance from the live audit, the assignment the old cap cut off)
# (still under the hard cap 40), /ephe stays at the cap.
MAX_TOOL_ITERATIONS: int = 25


# QD-015 Z2: the budget card's one click. The surface sends it as a new turn
# whose budget is the cap the turn ran on plus this many rounds.
CONTINUE_TURN_ROUNDS: int = 10


# R37: hard cap above all task classes; P2b consolidation: /ephe uses
# the same value (EPHE_TOOL_BUDGET=40), clamp_tool_budget clamps to this cap.
TOOL_BUDGET_HARD_CAP: int = 40


def clamp_tool_budget(max_tool_iterations: int | None) -> int:
    """R37: tool budget by task class — casual default 10, coding class
    (/ephe) up to the hard cap 40. Never 0, never above the cap."""
    return max(1, min(TOOL_BUDGET_HARD_CAP, int(max_tool_iterations or MAX_TOOL_ITERATIONS)))


def budget_continue_frame(cap: int | None) -> dict:
    """The frame that turns a cap end into an offer (QD-015 Z2).

    `cap` is the budget the turn actually ran on; the surface offers the next
    rounds as one click and sends the click as a new turn with cap + extra.
    """
    return {
        "type": "budget",
        "action": "continue_turn",
        "cap": clamp_tool_budget(cap),
        "extra": CONTINUE_TURN_ROUNDS,
    }


def _ollama_async_client():
    return ollama.AsyncClient()


async def chat_with_tools(
    *,
    model: str,
    history: list[Message],
    on_chunk: Callable[[str], None],
    on_thinking: Callable[[str], None] | None = None,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_done: Callable[[str, str], None] | None = None,
    on_phase: Callable[[str], None] | None = None,
    on_loading_hint: Callable[[], None] | None = None,
    provider_config: ModelProviderConfig | None = None,
    api_url: str | None = None,
    allowed_tool_names: list[str] | None = None,
    extra_system_prompt: str | None = None,
    on_shell_confirm: Callable[[str], object] | None = None,
    on_tool_confirm: Callable[[str, dict], object] | None = None,
    max_tool_iterations: int | None = None,
    approval_policy: ApprovalPolicy | None = None,
    session_id: str = "",
    turn_id: str = "",
    loop_observer: LoopObserver | None = None,
    sol_turn: object | None = None,
) -> str:
    """
    Tool-enabled chat with automatic tool execution.

    Flow:
        1. Non-streaming call with tool schemas → detect tool calls
        2. Execute tools (max MAX_TOOL_ITERATIONS iterations)
        3. Emit the final answer as text via on_chunk

        stream=False for tool detection is REQUIRED.
    Known Ollama limit: tool calls break with stream=True.

    Args:
        model:          Ollama model name
        history:        conversation history (role/content dicts)
        on_chunk:       callback for every text token of the final answer
        on_tool_start:  callback when a tool starts (name, args)
        on_tool_done:   callback when a tool finishes (name, result)
        on_loading_hint: callback when the model loads too long

    Raises:
        OllamaNotReachableError:    Ollama cannot be reached
        OllamaModelNotFoundError:   model not present locally
        ShellConfirmationRequired:  the shell tool needs user confirmation
    """
    provider = _resolve_provider(model, provider_config, api_url)
    # A1: the birthplace of the output tools assigns per session. A contextvar
    # instead of a parameter through 40 tool signatures; it is set at the one
    # place that executes the tools. No reset needed — an asyncio task gets
    # a copy of the context, the next request does not see this.
    from core.artifact_workbench import set_artifact_session, set_artifact_turn

    set_artifact_session(session_id)
    set_artifact_turn(turn_id)
    # R44: failover chain — if the active engine cannot be reached, the
    # turn falls back to the next candidate in the chain (local_ollama); the reason
    # lands in the session_ctx failover note for the kind=turn audit.
    provider = await resolve_active_with_failover(provider)
    client = build_provider_client(provider)
    # P0-2: set the active session key for the tool loop (stateful
    # tools — execute_code/todo_list — index their registers with it).
    from core.tools.session_ctx import set_current_session

    set_current_session(session_id)
    # N8a: count anew per turn — the tool loop accumulates across all
    # model calls; an old value from the previous turn may not flow in.
    from core.tools.session_ctx import _MEASURED_USAGE as _MU_RESET
    _MU_RESET.set(None)
    # Compaction deliberately WITHOUT a memory sink (no Chroma in the TTFT path);
    # the memory preservation of the discarded pairs runs checkpoint-based
    # AFTER the answer (routes/chat.py → compaction_memory, R25).
    # P5-2: window-proportional threshold — 80 % of the effective window.
    from core.conversation_compactor import window_threshold as _comp_th

    # W1-7: the turn's counters live on the observer, bound for this task so the
    # tool loop and the window trims reach it without a parameter through every
    # signature. A caller may pass its own instance and read the counters after.
    budget_cap = clamp_tool_budget(max_tool_iterations)
    observer = loop_observer if loop_observer is not None else LoopObserver(turn_id=turn_id)
    observer.set_budget_cap(budget_cap)
    observer_token = bind_observer(observer)

    from core.sol.session import close_sol_turn, open_sol_turn, task_from
    # SOL: a caller that wants the learned rules passes its own turn (`.learned`).
    sol, sol_token = open_sol_turn(sol_turn)  # type: ignore[arg-type]
    turn_ok = False

    try:
        history_in = list(history)
        messages: list = compact_history(history_in, threshold_tokens=_comp_th(model))
        note_compaction("history", len(history_in) - len(messages))
        tools = _tools_for_messages(messages, allowed_tool_names=allowed_tool_names)

        # System prompt (R28) + steps 1–3, each in its own helper.
        # G7: session/turn travel into the assembler so the memories injected
        # here are recorded on this very run.
        _assemble_system_prompt_into(
            messages,
            model,
            extra_system_prompt,
            allowed_tool_names,
            session_id=session_id,
            turn_id=turn_id,
        )

        # Step 1: tool detection (stream=False – mandatory!)
        from core.model_capability import (
            ANSWER_ONLY_PHASE,
            is_answer_only,
            looks_like_tool_rejection,
            note_rejection,
        )

        # S3 capability guard: an array this (endpoint, model) already refused is not
        # offered again in this process. Unknown is not false — a model nobody refused
        # keeps exactly today's array.
        if tools and is_answer_only(provider.base_url, model):
            tools = []
        try:
            response, model, detection_streamed = await _detect_tool_calls(
                client=client,
                provider=provider,
                model=model,
                messages=messages,
                tools=tools,
                on_chunk=on_chunk,
                on_thinking=on_thinking,
                on_phase=on_phase,
            )
        except Exception as exc:
            # The refusal of an array is a fact about the model, not about the request:
            # remember it and ask the same messages without one, so the first turn a
            # tool-less engine is given does not end in its 400.
            if not tools or not looks_like_tool_rejection(str(exc)):
                raise
            note_rejection(provider.base_url, model)
            tools = []
            if on_phase:
                on_phase(ANSWER_ONLY_PHASE)
            response, model, detection_streamed = await _detect_tool_calls(
                client=client,
                provider=provider,
                model=model,
                messages=messages,
                tools=tools,
                on_chunk=on_chunk,
                on_thinking=on_thinking,
                on_phase=on_phase,
            )
        if response is None:
            raise OllamaNotReachableError()

        # Step 2: tool-calling loop (hard-limited by budget + error budget)
        _iteration, detection_streamed, response = await _run_tool_loop(
            client=client,
            provider=provider,
            model=model,
            messages=messages,
            tools=tools,
            response=response,
            detection_streamed=detection_streamed,
            on_chunk=on_chunk,
            on_thinking=on_thinking,
            on_tool_start=on_tool_start,
            on_tool_done=on_tool_done,
            on_phase=on_phase,
            on_shell_confirm=on_shell_confirm,
            on_tool_confirm=on_tool_confirm,
            approval_policy=approval_policy,
            budget_cap=budget_cap,
            turn_id=turn_id,
        )
        # Out of budget? The loop names its reason, so a turn that answered on its
        # last allowed round is not read as an exhausted budget — the round count
        # alone cannot tell a spent cap from a model that chose to stop.
        if current_stop_reason() == STOP_BUDGET:
            note_budget_exhausted()
            # I6 P1-2 / R37: no raw system marker any more — the text IS the answer
            # and appears in the chat stream that way (with 'unfinished' status, never pseudo-complete).
            # R44: before the note, ONE tool-less finalize round — a real
            # conclusion instead of a bare system line.
            turn_ok = True
            return await _finalize_budget_exhausted(
                client=client,
                provider=provider,
                model=model,
                messages=messages,
                tools=tools,
                on_chunk=on_chunk,
                on_phase=on_phase,
                budget_cap=budget_cap,
            )

        # Step 3: emit the final answer (parse thinking tags)
        turn_ok = True
        return await _emit_final_answer(
            response=response,
            detection_streamed=detection_streamed,
            on_chunk=on_chunk,
            on_thinking=on_thinking,
            on_phase=on_phase,
        )
    finally:
        note_turn_end()
        reset_observer(observer_token)
        close_sol_turn(sol, sol_token, ok=turn_ok, task=task_from(history))  # type: ignore[arg-type]
        # P1-4: close the upstream connection explicitly — a client disconnect
        # should leave no socket hanging in the loop. Ollama/httpx: aclose(),
        # OpenAI client: close(); stub clients in tests without either are tolerated.
        closer = getattr(client, "aclose", None) or getattr(client, "close", None)
        if callable(closer):
            try:
                result = closer()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                pass
