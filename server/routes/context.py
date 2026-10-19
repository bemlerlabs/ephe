"""server/routes/context.py – GET /api/context/budget (R25).

Honest context budget display: the backend counts the stored session history
and computes with the same ratio as the frontend meter
(4.2 chars/token, conservative) — no "felt" percentages.
"""
from __future__ import annotations

import os
import asyncio
from typing import Literal

from fastapi import APIRouter

router = APIRouter(tags=["Context"])

# Same constants as app/src/lib/contextMeter.ts (honest display)
CHARS_PER_TOKEN = 4.2
CONTEXT_WINDOW_TOKENS = 8192
COMPACTION_MAX_MESSAGES = 28  # core.conversation_compactor.DEFAULT_MAX_MESSAGES

REST_MIRROR_PREFIX = "rest-"  # server/routes/chat.py: PWA history mirror


def _engine_context_window() -> int | None:
    """Max model len of the active engine from the probe cache (nil when unknown).

    Reads only the cache that the model-provider route fills when the PWA downloads
    the engine list — no network here: the budget endpoint stays
    deterministic (testable) and offline-first. Ollama never delivers the field,
    and then only the env override or the legacy fallback is left.
    """
    try:
        from core.model_provider import get_active_provider
        from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

        active = get_active_provider()
        if active is None or active.provider != "openai_compatible" or not active.base_url:
            return None
        cached = _CONTEXT_WINDOW_CACHE.get((active.base_url, active.model))
        if cached:
            return cached
        # Cold probe cache (e.g. right after a restart): pull it once,
        # so the budget endpoint shows the same number as the provider route.
        from server.routes.model_provider import _active_context_window

        try:
            return asyncio.run(_active_context_window(active))
        except Exception:
            return None
    except Exception:
        return None


def _resolve_window() -> tuple[int, str]:
    """Context window biggest to smallest: env override > engine probe > tier > legacy.

    The EPHE_CONTEXT_WINDOW override always wins (manual correction).
    Without a probe the tier table in `core.model_config` carries (P0-1: the real
    windows of the shipped model classes); only for an unknown model does
    the documented 8192 fallback remain (offline-first).
    """
    raw = (os.environ.get("EPHE_CONTEXT_WINDOW") or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value, "env"
    probed = _engine_context_window()
    if probed and probed > 0:
        return probed, "engine"
    model = ""
    try:
        from core.model_provider import get_active_provider

        model = get_active_provider().model or ""
    except Exception:
        pass
    from core.model_config import context_window_for_model

    tier_window = context_window_for_model(model)
    if tier_window:
        return tier_window, "tier"
    return CONTEXT_WINDOW_TOKENS, "legacy"


@router.get("/context/budget")
def context_budget(session_id: str = "") -> dict:
    """Context occupancy of the session (real message count + estimate ratio).

    DD-07: the PWA persists its history in the `rest-<id>` mirror (only the
    REST route writes along). The browser never has a native session file —
    without the mirror fallback the meter would always count zero.
    """
    from core.conversation_compactor import DEFAULT_MAX_MESSAGES
    from core.multi_session import active_session_id, load_messages

    sid = session_id or active_session_id()
    messages: list[dict] = []
    counted_via = "native"
    if sid:
        messages = load_messages(sid)
        if not messages and not sid.startswith(REST_MIRROR_PREFIX):
            mirrored = load_messages(f"{REST_MIRROR_PREFIX}{sid}")
            if mirrored:
                messages = mirrored
                counted_via = "rest_mirror"

    stages_payload = context_stages()
    char_count = sum(len(str(m.get("content", "") or "")) for m in messages)
    # W16: the same counting path as core.usage — exact BPE with tiktoken, otherwise
    # the calibrated 4.2 heuristic; the per-message count is the SSOT (sum).
    from core.usage import estimate_tokens as _estimate, tokenizer_backend as _backend

    estimated_tokens = sum(_estimate(str(m.get("content", "") or "")) for m in messages)
    window, window_source = _resolve_window()
    percent = round(estimated_tokens / window * 100, 2) if window else 0.0

    return {
        "session_id": sid or "",
        "message_count": len(messages),
        "char_count": char_count,
        "estimated_tokens": estimated_tokens,
        "window_tokens": window,
        "window_source": window_source,
        "counted_via": counted_via,
        "tokenizer": _backend(),
        "percent": percent,
        "compaction_threshold": DEFAULT_MAX_MESSAGES,
        "compaction_active": len(messages) > DEFAULT_MAX_MESSAGES,
        "breakdown": _breakdown(stages_payload),
        "stages": stages_payload["stages"],
    }


def _breakdown(stages_payload: dict | None = None) -> list[dict]:
    """Category shares of the context window (reference parity, 1:1 pattern).

    Each category carries its share of the estimated tokens; the sum stays
    below 100 % because the remainder is unlabeled gaps. The numbers are real,
    not felt: history from load_messages(), the prompt from the stages, the
    tool/skill lines from the registry lengths.
    """
    cats: list[dict] = []
    try:
        hist = sum(len(str(m.get("content", "") or "")) for m in _all_messages())
    except Exception:
        hist = 0
    try:
        stages = stages_payload if stages_payload is not None else context_stages()
        prompt_chars = int(stages.get("total_chars", 0) or 0)
    except Exception:
        prompt_chars = 0
    try:
        from core.tools.registry import get_tool_schemas

        def _desc_len(d: dict) -> int:
            inner = d.get("function") or {}
            return len(str(inner.get("description", "") or d.get("description", "") or ""))

        tool_chars = sum(_desc_len(d) for d in get_tool_schemas())
    except Exception:
        tool_chars = 0
    try:
        from core.skills import SkillLoader

        skill_chars = sum(len(str(getattr(sk, "description", "") or "")) for sk in SkillLoader().load_all())
    except Exception:
        skill_chars = 0
    try:
        from core.mcp_config import load_mcp_servers

        mcp_names, _ = load_mcp_servers()
        mcp_chars = sum(len(n) for n in mcp_names)
    except Exception:
        mcp_chars = 0
    total = hist + prompt_chars + tool_chars + skill_chars + mcp_chars
    meta_chars = 0  # gaps/digits from the meta context (line numbers, IDs)
    for name, chars in (
        ("Messages", hist),
        ("MCP tools", mcp_chars),
        ("System tools", tool_chars),
        ("System prompt", prompt_chars),
        ("Skills", skill_chars),
        ("Meta context", meta_chars),
    ):
        if chars and total:
            cats.append({"name": name, "percent": round(chars / total * 100, 1)})
    return cats


def _all_messages() -> list[dict]:
    from core.multi_session import active_session_id, load_messages

    sid = active_session_id()
    return load_messages(sid) if sid else []


@router.get("/context/stages")
def context_stages() -> dict:
    """R29 transparency: the assembled system prompt stage by stage.

    Each stage reports its name, char count and a head preview — so the user
    can see exactly what voice is speaking into the model (identity, persona,
    tool guidelines, workspace rules, profile, memory, corrections, feedback).
    Nothing here is secret; refusing to show it is what competitors do.
    """
    stages: list[dict] = []

    def add(name: str, text: str | None) -> None:
        body = (text or "").strip()
        if body:
            stages.append({"name": name, "chars": len(body), "preview": body[:220]})

    model = ""
    try:
        from core.model_provider import get_active_provider

        model = get_active_provider().model or ""
    except Exception:
        pass

    try:
        from core.persona import build_identity_block, build_tool_guidelines, load_persona

        add("identity", build_identity_block(model or "unknown"))
        add("persona", load_persona())
        add("tool_guidelines", build_tool_guidelines())
    except Exception:
        pass

    try:
        from core.chat_prompt import custom_instructions_block

        add("custom_instructions", custom_instructions_block())
    except Exception:
        pass

    try:
        from dataclasses import asdict

        from core.workspace_rules import DENIED, UNREADABLE, read_workspace_rules

        rules = read_workspace_rules()
        if rules.text:
            add("workspace_rules", rules.text)
        # A refused or unreadable file did not speak, but the surface has to say it
        # was seen and why it stayed out; a stage with 0 chars carries that report.
        noteworthy = any(entry.status in (DENIED, UNREADABLE) for entry in rules.files)
        if noteworthy and not any(s["name"] == "workspace_rules" for s in stages):
            stages.append({"name": "workspace_rules", "chars": 0, "preview": ""})
        if rules.files and any(s["name"] == "workspace_rules" for s in stages):
            for stage in stages:
                if stage["name"] == "workspace_rules":
                    stage["files"] = [asdict(entry) for entry in rules.files]
    except Exception:
        pass

    try:
        from core.profile import load_profile

        add("user_profile", load_profile().to_context_string())
    except Exception:
        pass

    try:
        from core.corrections import CorrectionJournal
        from core.feedback import FeedbackStore

        add("corrections", CorrectionJournal().to_context_string())
        add("feedback", FeedbackStore().to_few_shot_string())
    except Exception:
        pass

    try:
        # W3-38: the date left the identity block (byte-stable prefix); it is
        # its own trailing block now, so the stage list mirrors the assembly.
        from core.persona import build_date_block

        add("date", build_date_block())
    except Exception:
        pass

    total = sum(s["chars"] for s in stages)
    return {"stages": stages, "total_chars": total}
