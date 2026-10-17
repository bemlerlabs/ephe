"""Ephe – session context for tool-side state (P0-2).

A module-global dict carries the active session key through the
tool loop. ContextVar instead of a module variable, because several sessions in the same
process can interleave (core/multi_session.py): each async task
sees its own value, and ``asyncio.to_thread`` propagates it into the
worker thread (copy_context).

Read path: tools fetch the key via ``get_current_session()``
and index their state registers with it. No additional tool argument
needed — the registry schemas stay unchanged.
"""
from __future__ import annotations

from contextvars import ContextVar, Token

_CURRENT_SESSION: ContextVar[str] = ContextVar("ephe_current_session", default="")

# P1a (Deep-Audit 2026-09-16): the active approval policy, so the meta router
# (tool_call) does not bypass the approval gate. execute_tool is the only
# choke point with a policy argument; it sets it here, tool_call reads it and
# carries it into the inner execute_tool call. ContextVar because several
# sessions interleave in the same process (analogous to _CURRENT_SESSION).
_CURRENT_POLICY: ContextVar[object] = ContextVar("ephe_current_policy", default=None)


def set_current_session(session_id: str) -> Token:
    """Sets the active session key; returns the reset token."""
    token = _CURRENT_SESSION.set((session_id or "").strip() or "default")
    return token


def get_current_session() -> str:
    """Active session key (if none: 'default')."""
    return _CURRENT_SESSION.get() or "default"


def set_current_policy(policy: object) -> None:
    """Store the active approval policy (only when not None — otherwise spare the default)."""
    if policy is not None:
        _CURRENT_POLICY.set(policy)


def get_current_policy() -> object:
    """Active approval policy (if none: None => gate behaviour as before)."""
    return _CURRENT_POLICY.get()


# W10 (walkthrough finding, plan mode wrote a file): the active MODE as the tool
# side sees it. The offer filter (server/routes/chat.py) hides tools from the model,
# but the deferred bridge (tool_search + tool_call) dispatches by NAME at execution
# time and never sees an offer list — so the mode's promise has to be readable where
# the call is executed. Set per turn by the chat routes; '' (no mode) means no
# constraint, the same default every non-chat caller (CLI, swarm, sub-agent) gets.
_CURRENT_MODE: ContextVar[str] = ContextVar("ephe_current_mode", default="")


def set_current_mode(mode: str) -> Token:
    """Sets the active UI mode; returns the reset token (empty string = no constraint)."""
    return _CURRENT_MODE.set((mode or "").strip().lower().replace("-", "_"))


def get_current_mode() -> str:
    """Active UI mode ('ask' | 'plan' | 'edit_auto' | 'full_access' | '')."""
    return _CURRENT_MODE.get() or ""


def reset_current_mode(token: Token) -> None:
    """Restores the mode that was active before ``set_current_mode``."""
    _CURRENT_MODE.reset(token)


# R44 (Deep-Audit 2026-09-16): failover reason (e.g. 'openai_compatible→local_ollama'),
# set when the active engine was unreachable and a later chain-
# candidate won. ContextVar so the turn audit entry sees it.
_FAILOVER_NOTE: ContextVar[str] = ContextVar("ephe_failover_note", default="")


def set_failover_note(note: str) -> None:
    """Store the failover reason (empty string => no failover in this turn)."""
    _FAILOVER_NOTE.set(note or "")


def get_failover_note() -> str:
    """Active failover reason (if none: empty string)."""
    return _FAILOVER_NOTE.get() or ""


# N8a (2026-09-23): provider-measured token counts per turn. The
# OpenAI-compatible stream delivers a usage block in the last frame (only when
# stream_options.include_usage is set); non-streaming answers carry it
# directly. ContextVar because one turn can consist of several model calls
# (tool loop) and billing is the sum of all calls — not the last one.
_MEASURED_USAGE: ContextVar[dict | None] = ContextVar("ephe_measured_usage", default=None)


def record_measured_usage(usage: object) -> None:
    """Accumulate the provider usage block (Ollama and OpenAI nomenclature).

    Silently ignores non-dict values and empty blocks — the
    read path distinguishes via the usage_estimated flag in core.usage.
    Since Wave 3 (cost monitor/cache chip) the measured
    cache hit is counted too: OpenAI ``prompt_tokens_details.cached_tokens``
    and Anthropic shim ``cache_read_input_tokens`` — never guessed, only
    measured (if the field is missing, cached_tokens stays 0).
    """
    if not isinstance(usage, dict):
        return
    p_raw = usage.get("prompt_tokens", usage.get("prompt_eval_count"))
    c_raw = usage.get("completion_tokens", usage.get("eval_count"))
    details = usage.get("prompt_tokens_details")
    cached_raw = usage.get("cache_read_input_tokens")
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        cached_raw = details.get("cached_tokens")
    if p_raw is None and c_raw is None:
        return
    try:
        p, c = int(p_raw or 0), int(c_raw or 0)
    except (TypeError, ValueError):
        return
    try:
        cached = int(cached_raw or 0)
    except (TypeError, ValueError):
        cached = 0
    cur = _MEASURED_USAGE.get() or {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
    _MEASURED_USAGE.set(
        {
            "prompt_tokens": int(cur.get("prompt_tokens") or 0) + p,
            "completion_tokens": int(cur.get("completion_tokens") or 0) + c,
            "cached_tokens": int(cur.get("cached_tokens") or 0) + cached,
        }
    )


def get_measured_usage() -> dict | None:
    """Accumulated measured counts of the turn (None when none was measured)."""
    return _MEASURED_USAGE.get()
