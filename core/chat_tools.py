"""The tool-calling loop of the chat engine.

Runs parsed tool calls under the approval gate with result capping, evidence
lines and budget accounting. Split from core/chat.py; the facade re-exports
_run_tool_loop and resolves the patched seams for this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace

from core.chat_context import (
    _active_context_window,
    _cap_tool_result,
    _fit_messages_to_window,
)
from core.chat_detect import (
    _call_id,
    _follow_up_with_retry,
    _parse_tool_calls,
    _stream_detect_openai,
    engine_tool_call_ids,
)
from core.chat_prompt import (
    _OPEN_PLAN_NUDGE,
    _continue_attempts,
    _looks_like_open_plan,
    _native_thinking_kwargs,
)
from core.chat_stream import OllamaNotReachableError
from core.loop_observability import (
    BUDGET_LOW_WATER,
    STOP_ANSWER,
    STOP_BUDGET,
    STOP_REPAIR,
    STOP_STALL,
    STOP_STEERED,
    note_budget_low,
    note_compaction,
    note_stop,
    note_tool_round,
)
from core.quality import normalize_tool_result
from core.redact import redact


def _redact_result(result: object) -> str:
    """Redacts a tool result while keeping a gate denial's code and params.

    `Denied` is a str subclass; a plain `redact()` returns a new str and would drop
    `code`, which the card reads to paint a refusal as a refusal.
    """
    masked = redact(str(result))
    code = getattr(result, "code", "")
    if not code:
        return masked
    from core.tools.chat_gate import Denied

    return Denied(masked, code, getattr(result, "params", None))
from core.steering import (
    MAX_REOPEN_PER_TURN,
    current_channel,
    take_up,
)
from core.tools import ShellConfirmationRequired
from core.tools.approval import ApprovalPolicy, request_approval
from core.tools.chat_gate import confirm_for_chat, denial_message


from core._chat_tools_results import (  # noqa: F401  (facade: callers and tests read these names here)
    CIRCLING_ERROR_RUN,
    CIRCLING_TARGET_REPEATS,
    WEB_UNTRUSTED_TOOLS,
    _META_FORWARD_LIMIT,
    _META_FORWARD_TOOL,
    _PATH_ARG_KEYS,
    _STALL_ERROR_RUN,
    _STALL_TARGET_REPEAT,
    _Stall,
    _StallMessage,
    _StallResponse,
    _ToolLoopStallGuard,
    _UNRESOLVED_ORIGIN,
    _UNTRUSTED_EVIDENCE,
    _VALUE_ARG_KEYS,
    _finalize_stalled,
    _finalize_steer_stop,
    _steer_stop_note,
    _tool_loop_stall_note,
    fence_tool_output,
    is_untrusted_tool,
    tool_call_target,
    untrusted_origin_tool,
)


def _announce_tool_round(iteration: int, budget_cap: int) -> None:
    """Count one executed round and warn once as the budget nears its end.

    The budget is the turn's hard limit, so it is observed at both ends: the
    round is counted (per-round ``rounds_remaining`` in the counter trace) and,
    when the rounds left first drop to ``BUDGET_LOW_WATER``, a one-shot warning
    marks the turn as nearly out — well before the exhausted event.
    """
    note_tool_round(iteration)
    remaining = budget_cap - iteration
    if 0 < remaining <= BUDGET_LOW_WATER:
        note_budget_low(remaining)




async def _model_follow_up(
    *,
    client: object,
    provider: object,
    model: str,
    messages: list,
    tools: list,
    on_chunk: Callable[[str], None],
    on_thinking: Callable[[str], None] | None,
    on_phase: Callable[[str], None] | None,
    idle_timeout: float,
) -> object:
    """One follow-up model call on the running messages, per provider.

    Only the cadence differs: an OpenAI-compatible engine streams the answer as
    it detects it (so the caller must mark the answer as already streamed), the
    native path answers in one frame. Every round of the loop shares this call,
    which is what keeps a steered round and an ordinary round from drifting apart.
    """
    if provider.provider == "openai_compatible":
        return await _follow_up_with_retry(
            lambda: _stream_detect_openai(
                client,
                model=model,
                messages=messages,
                tools=tools,
                on_chunk=on_chunk,
                on_thinking=on_thinking,
                idle_timeout=idle_timeout,
            ),
            on_phase=on_phase,
        )
    return await _follow_up_with_retry(
        lambda: client.chat(
            model=model,
            messages=messages,
            tools=tools,
            stream=False,
            **_native_thinking_kwargs(model),
        ),
        on_phase=on_phase,
    )


def _wants_more_tools(response: object) -> bool:
    """True when the last message still carries tool calls.

    A model that answered stopped on its own; one that still asked for tools had the
    turn ended for it. That difference is what makes a cap that bound the turn a
    distinct fact from the model's own stop.
    """
    return bool(getattr(getattr(response, "message", None), "tool_calls", None))


async def _run_tool_loop(
    *,
    client: object,
    provider: object,
    model: str,
    messages: list,
    tools: list,
    response: object,
    detection_streamed: bool,
    on_chunk: Callable[[str], None],
    on_thinking: Callable[[str], None] | None,
    on_tool_start: Callable | None,
    on_tool_done: Callable | None,
    on_phase: Callable[[str], None] | None,
    on_shell_confirm: Callable | None,
    on_tool_confirm: Callable | None,
    approval_policy: ApprovalPolicy | None,
    budget_cap: int,
    turn_id: str = "",
) -> tuple[int, bool, object]:
    """Step 2: tool-calling loop (parallel SAFE phase + sequential
    approval phase), hard-limited by ``budget_cap`` and the
    error-round budget (``MAX_REPAIRS_PER_STEP``).

    Returns ``(iteration, detection_streamed, response)`` — ``response`` is the
    final answer without further tool calls (for output step 3).
    """
    from core.chat import (  # seam: tests patch these on core.chat
        _tool_detection_timeout,
        execute_confirmed_shell,
        execute_tool,
    )
    iteration = 0
    # P1-8: the declared repair budget from core.ephe_plan is hard
    # enforced here; on exhaustion the loop aborts honestly.
    from core.ephe_plan import MAX_REPAIRS_PER_STEP

    consecutive_error_rounds = 0
    stall_guard = _ToolLoopStallGuard()
    stalled: _Stall | None = None
    TOOL_DETECT_TIMEOUT = _tool_detection_timeout(model)

    # Rounds run while there is work and no stop. Every pass re-checks the two
    # ends, because a steer taken up at the end of one adds a round to the next.
    steer_rounds = 0
    while True:
        while (
            hasattr(response, "message")
            and hasattr(response.message, "tool_calls")
            and response.message.tool_calls
            and iteration < budget_cap
            and consecutive_error_rounds <= MAX_REPAIRS_PER_STEP
        ):
            iteration += 1
            _announce_tool_round(iteration, budget_cap)
            if on_phase:
                on_phase(f"Tool round {iteration}…")
            messages.append(response.message)

            # 1) Parse all tool calls (index-stable); _parse_tool_calls creates the
            # call-IDs once per call, so start and done carry the same id (W15-P3).
            parsed, call_ids = _parse_tool_calls(response, turn_id, on_tool_start, iteration)
            engine_ids = engine_tool_call_ids(response)

            # 2) SAFE tools (read-only) in parallel, the rest sequentially with an approval gate.
            safe_names: set[str] = set()
            try:
                from core.tools.approval import SAFE_TOOLS as _SAFE_SET
                safe_names = set(_SAFE_SET)
            except Exception:
                pass

            safe_calls = [(i, n, a) for i, n, a in parsed if n in safe_names]
            other_calls = [(i, n, a) for i, n, a in parsed if n not in safe_names]
            results: dict[int, str] = {}

            if safe_calls:
                if on_phase:
                    on_phase(f"Executing {len(safe_calls)} read-only tool(s) in parallel…")
                # P0-1: tuple-indexed assignment — the tuple index ``i`` is the
                # only source of truth for the position in ``parsed``.
                coros = [
                    (i, execute_tool(n, a, policy=approval_policy))
                    for i, n, a in safe_calls
                ]
                done = await asyncio.gather(*[c for _, c in coros], return_exceptions=True)
                for (i, _), res in zip(coros, done):
                    if isinstance(res, Exception):
                        results[i] = f"[TOOL-ERROR] {type(res).__name__}: {res}"
                    else:
                        results[i] = str(res)

            for idx, name, args in other_calls:
                if name == "run_shell":
                    command = args.get("command", "")
                    # P1a: pass the model cwd through, so the shell round runs in
                    # the same directory as the execute_tool path.
                    shell_cwd = args.get("cwd")
                    if approval_policy is not None:
                        decision = await request_approval(name, args, approval_policy)
                        if not decision.approved:
                            result = decision.report
                        else:
                            try:
                                result = await execute_confirmed_shell(command, confirmed=True, cwd=shell_cwd)
                            except Exception as tool_exc:
                                result = f"[TOOL-ERROR] {type(tool_exc).__name__}: {tool_exc}"
                    else:
                        if on_shell_confirm is None:
                            raise ShellConfirmationRequired(command)
                        maybe_approved = on_shell_confirm(command)
                        approved = await maybe_approved if hasattr(maybe_approved, "__await__") else bool(maybe_approved)
                        try:
                            result = await execute_confirmed_shell(command, confirmed=bool(approved), cwd=shell_cwd)
                        except Exception as tool_exc:
                            result = f"[TOOL-ERROR] {type(tool_exc).__name__}: {tool_exc}"
                else:
                    # approval_policy is None means: the gate sits here (it is not inside
                    # execute_tool). The same gate applies in tool_call (chat_gate), so
                    # the meta router is no shortcut past it.
                    approved, denial = (
                        await confirm_for_chat(name, args, on_confirm=on_tool_confirm)
                        if approval_policy is None else (True, "")
                    )
                    if approved:
                        result = await execute_tool(name, args, policy=approval_policy)
                    else:
                        result = denial
                results[idx] = result

            # 3) Append the results to the history in their original order.
            round_had_error = False
            round_stall: _Stall | None = None
            for idx, name, args in parsed:
                # P1-9: cap before it enters the message array.
                result = _cap_tool_result(results.get(idx, "[TOOL-NO-RESULT]"))
                # SEC-1: the one result that feeds the model, the tool card and the
                # audit row is redacted here, before any of the three sees it.
                result = _redact_result(result)
                # E2: web/MCP output is third-party content — it enters the context
                # fenced as untrusted data (fence_tool_output).
                external = untrusted_origin_tool(name, args) is not None
                engine_result = fence_tool_output(name, args, result)
                # W15-P3: done with the same call-ID as the start stamp.
                if on_tool_done is not None:
                    on_tool_done(name, result, call_ids.setdefault(idx, _call_id(turn_id, idx, iteration)))
                normalized_result = normalize_tool_result(name, result)
                if external and normalized_result.status != "error":
                    # The evidence block is a system message; external content must
                    # not surface in it outside the fence.
                    normalized_result = replace(
                        normalized_result,
                        summary=_UNTRUSTED_EVIDENCE,
                        evidence=[],
                        artifacts=[],
                        warnings=[],
                    )
                if normalized_result.status == "error":
                    round_had_error = True
                trip = stall_guard.record(
                    name, args, is_error=normalized_result.status == "error"
                )
                if trip is not None and round_stall is None:
                    round_stall = trip
                answer = {"role": "tool", "content": engine_result}
                # TL-1: every result names the call it answers. The engine's id is
                # the wire identity; our own deterministic id is the fallback, so a
                # provider can never correlate positionally again.
                answer["tool_call_id"] = engine_ids.get(idx) or call_ids[idx]
                messages.append(answer)
                messages.append({
                    "role": "system",
                    "content": redact(
                        "Tool evidence summary:\n"
                        f"- tool: {normalized_result.tool}\n"
                        f"- status: {normalized_result.status}\n"
                        f"- summary: {normalized_result.summary}\n"
                        f"- artifacts: {normalized_result.artifacts}\n"
                        f"- warnings: {normalized_result.warnings}"
                    ),
                })

            # P1-8: spend/rescue the error-round budget (one success resets it).
            if round_had_error:
                consecutive_error_rounds += 1
            else:
                consecutive_error_rounds = 0

            # The circling guard answers a different question than the repair
            # budget: not "did the last round fail" but "has this target ever
            # worked". A trip ends the turn before the follow-up call.
            if round_stall is not None:
                stalled = round_stall
                break

            # Steering lands here and nowhere else. Every tool result of this round
            # is in `messages` by now, so a direction change cannot come to rest
            # between a tool's side effect and the record of it. A steer that asks
            # for a stop ends the turn at this same boundary — which is the whole
            # difference between this and the cancel it replaces.
            taken = take_up(messages, boundary=iteration)
            for steer in taken:
                if steer.stop:
                    note_stop(STOP_STEERED)
                    return _finalize_steer_stop(
                        steer=steer,
                        boundary=iteration,
                        messages=messages,
                        on_chunk=on_chunk,
                    )

            if on_phase:
                on_phase("Processing results…")
            # W15-P2: re-overflow protection per round before the follow-up.
            dropped = _fit_messages_to_window(messages, _active_context_window(model))
            note_compaction("window", dropped)
            try:
                response = await _model_follow_up(
                    client=client,
                    provider=provider,
                    model=model,
                    messages=messages,
                    tools=tools,
                    on_chunk=on_chunk,
                    on_thinking=on_thinking,
                    on_phase=on_phase,
                    idle_timeout=TOOL_DETECT_TIMEOUT,
                )
                # Only a streaming engine (openai_compatible) has this answer on the
                # wire already; a native engine's text is still only in the response.
                detection_streamed = provider.provider == "openai_compatible"
            except Exception as exc:
                exc_str = str(exc).lower()
                if any(kw in exc_str for kw in ("connection", "connect", "refused")):
                    raise OllamaNotReachableError() from exc
                raise
        # N9c: nudge for plans broken off mid-way (the plan-then-stop pattern).
        # The model sometimes declares "Step 1: ..." as text and then
        # emits no tool_calls block -> the loop ends too early. Nudge it on as
        # often as `chat.continue_attempts` says (I6-3; 0 switches it off).
        continue_attempts = _continue_attempts()
        nudge_used = 0
        while (
            nudge_used < continue_attempts
            and iteration < budget_cap
            and hasattr(response, "message")
            and not getattr(response.message, "tool_calls", None)
            and _looks_like_open_plan(getattr(response.message, "content", "") or "")
            and stalled is None
        ):
            nudge_used += 1
            messages.append({"role": "assistant", "content": response.message.content})
            messages.append({"role": "user", "content": _OPEN_PLAN_NUDGE})
            dropped = _fit_messages_to_window(messages, _active_context_window(model))
            note_compaction("window", dropped)
            try:
                response = await _model_follow_up(
                    client=client,
                    provider=provider,
                    model=model,
                    messages=messages,
                    tools=tools,
                    on_chunk=on_chunk,
                    on_thinking=on_thinking,
                    on_phase=on_phase,
                    idle_timeout=TOOL_DETECT_TIMEOUT,
                )
            except Exception as exc:
                exc_str = str(exc).lower()
                if any(kw in exc_str for kw in ("connection", "connect", "refused")):
                    raise OllamaNotReachableError() from exc
                raise
            # After the nudge: if tool calls are present again, let the normal loop
            # continue — which is why the while condition is checked again.
            while (
                hasattr(response, "message")
                and getattr(response.message, "tool_calls", None)
                and iteration < budget_cap
                and consecutive_error_rounds <= MAX_REPAIRS_PER_STEP
            ):
                iteration += 1
                _announce_tool_round(iteration, budget_cap)
                if on_phase:
                    on_phase(f"Tool round {iteration}… (nudge {nudge_used})")
                messages.append(response.message)
                parsed_n, call_ids_n = _parse_tool_calls(response, turn_id, on_tool_start, iteration)
                engine_ids_n = engine_tool_call_ids(response)
                safe_names_n: set[str] = set()
                try:
                    from core.tools.approval import SAFE_TOOLS as _SAFE_SET_N
                    safe_names_n = set(_SAFE_SET_N)
                except Exception:
                    safe_names_n = set()
                results_n: dict[int, object] = {}
                round_had_error_n = False
                round_stall_n: _Stall | None = None
                for idx, name, args in parsed_n:
                    if name in safe_names_n:
                        try:
                            results_n[idx] = await execute_tool(name, args, policy=approval_policy)
                        except Exception as tool_exc:
                            results_n[idx] = f"[TOOL-ERROR] {type(tool_exc).__name__}: {tool_exc}"
                    else:
                        approved = True if approval_policy is not None else False
                        if approval_policy is None and on_tool_confirm is not None:
                            try:
                                maybe_approved = on_tool_confirm(name, args)
                                approved = (
                                    await maybe_approved
                                    if hasattr(maybe_approved, "__await__")
                                    else bool(maybe_approved)
                                )
                            except Exception:
                                approved = False
                        if not approved:
                            results_n[idx] = denial_message(name)
                        else:
                            try:
                                results_n[idx] = await execute_tool(name, args, policy=approval_policy)
                            except Exception as tool_exc:
                                results_n[idx] = f"[TOOL-ERROR] {type(tool_exc).__name__}: {tool_exc}"
                for idx, name, args in parsed_n:
                    result = _cap_tool_result(results_n.get(idx, "[TOOL-NO-RESULT]"))
                    result = _redact_result(result)
                    # E2: fence external content in the nudge path too.
                    external_n = untrusted_origin_tool(name, args) is not None
                    engine_result_n = fence_tool_output(name, args, result)
                    if on_tool_done is not None:
                        on_tool_done(
                            name, result, call_ids_n.setdefault(idx, _call_id(turn_id, idx, iteration))
                        )
                    normalized_result = normalize_tool_result(name, result)
                    if external_n and normalized_result.status != "error":
                        normalized_result = replace(
                            normalized_result,
                            summary=_UNTRUSTED_EVIDENCE,
                            evidence=[],
                            artifacts=[],
                            warnings=[],
                        )
                    if normalized_result.status == "error":
                        round_had_error_n = True
                    trip_n = stall_guard.record(
                        name, args, is_error=normalized_result.status == "error"
                    )
                    if trip_n is not None and round_stall_n is None:
                        round_stall_n = trip_n
                    answer_n = {"role": "tool", "content": engine_result_n}
                    answer_n["tool_call_id"] = engine_ids_n.get(idx) or call_ids_n[idx]
                    messages.append(answer_n)
                    messages.append({
                        "role": "system",
                        "content": redact(
                            "Tool evidence summary:\n"
                            f"- tool: {normalized_result.tool}\n"
                            f"- status: {normalized_result.status}\n"
                            f"- summary: {normalized_result.summary}\n"
                            f"- artifacts: {normalized_result.artifacts}\n"
                            f"- warnings: {normalized_result.warnings}"
                        ),
                    })
                if round_had_error_n:
                    consecutive_error_rounds += 1
                else:
                    consecutive_error_rounds = 0
                if round_stall_n is not None:
                    stalled = round_stall_n
                    break
                dropped = _fit_messages_to_window(messages, _active_context_window(model))
                note_compaction("window", dropped)
                try:
                    response = await _model_follow_up(
                        client=client,
                        provider=provider,
                        model=model,
                        messages=messages,
                        tools=tools,
                        on_chunk=on_chunk,
                        on_thinking=on_thinking,
                        on_phase=on_phase,
                        idle_timeout=TOOL_DETECT_TIMEOUT,
                    )
                except Exception as exc:
                    exc_str = str(exc).lower()
                    if any(kw in exc_str for kw in ("connection", "connect", "refused")):
                        raise OllamaNotReachableError() from exc
                    raise
        if stalled is not None:
            break
        # A steer that arrived while the model was writing its answer is worth an
        # answer that follows it: the turn re-opens for it and spends the same
        # round budget as any other round. The steered call's own tool calls then
        # run through the round loops above, which is why this sits at their end.
        if (
            _wants_more_tools(response)
            or iteration >= budget_cap
            or steer_rounds >= MAX_REOPEN_PER_TURN
        ):
            break
        reopens = take_up(messages, boundary=iteration)
        if not reopens:
            break
        stop_steer = next((steer for steer in reopens if steer.stop), None)
        if stop_steer is not None:
            note_stop(STOP_STEERED)
            return _finalize_steer_stop(
                steer=stop_steer,
                boundary=iteration,
                messages=messages,
                on_chunk=on_chunk,
            )
        steer_rounds += 1
        iteration += 1
        _announce_tool_round(iteration, budget_cap)
        if on_phase:
            on_phase("Direction change taken up…")
        dropped = _fit_messages_to_window(messages, _active_context_window(model))
        note_compaction("window", dropped)
        try:
            response = await _model_follow_up(
                client=client,
                provider=provider,
                model=model,
                messages=messages,
                tools=tools,
                on_chunk=on_chunk,
                on_thinking=on_thinking,
                on_phase=on_phase,
                idle_timeout=TOOL_DETECT_TIMEOUT,
            )
            detection_streamed = provider.provider == "openai_compatible"
        except Exception as exc:
            exc_str = str(exc).lower()
            if any(kw in exc_str for kw in ("connection", "connect", "refused")):
                raise OllamaNotReachableError() from exc
            raise
    # Whatever the turn ends without taking up is said out loud: a direction change
    # the model never read must not come back looking like one it followed.
    _turn_channel = current_channel()
    if _turn_channel is not None:
        _turn_channel.announce_unlanded(iteration)
    if stalled is not None:
        note_stop(STOP_STALL)
        return _finalize_stalled(
            stall=stalled,
            iteration=iteration,
            messages=messages,
            on_chunk=on_chunk,
        )
    if _wants_more_tools(response):
        # Still asking for tools after the loop ended: the cap or the repair budget
        # stopped it, not the model. The cap is the outer ceiling, so it names the
        # turn when both are reached.
        note_stop(STOP_BUDGET if iteration >= budget_cap else STOP_REPAIR)
    else:
        note_stop(STOP_ANSWER)
    return iteration, detection_streamed, response
