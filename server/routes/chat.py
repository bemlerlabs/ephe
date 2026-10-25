"""server/routes/chat.py – POST /api/chat + POST /api/chat/stream (SSE)"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Awaitable
from typing import AsyncGenerator, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.observability import structured_log

from core.chat import OllamaNotReachableError, OllamaModelNotFoundError, OllamaModelBusyError, chat_with_tools
from core import trajectory
from core.ephe_plan import EphePlan
from core.persona import (
    ASK_MODE_GUARD,
    PAGE_OUTPUT_GUARD,
    PLAN_MODE_GUARD,
    COMPUTE_GUARD,
    needs_compute_guard,
    needs_page_guard,
)
from core.react import reflect, react_loop
from core.commands import (
    extract_learn_topic,
    extract_swarm_task,
    is_goal_command,
    is_learn_command,
    is_swarm_command,
    parse_goal_command,
)
from core.skills import SkillLoader, SkillLoadError
from core.artifact_detector import ArtifactDetector
from core.artifact_markers import ARTIFACT_MARKERS
from core.search_budget import search_budget_answer
from core.quality import (
    budget_note_is_unfinished,
    evaluate_quality,
    is_error_result,
    normalize_tool_result,
    result_decision,
    validate_artifact,
)
from core.model_provider import (
    DEFAULT_OLLAMA_BASE_URL,
    ModelProviderConfig,
    ProviderSetupError,
    get_active_provider,
)

logger = logging.getLogger(__name__)

# R37: tool budget of the coding class (/ephe). W18 parity: reference A max_turns=60.
EPHE_TOOL_BUDGET: int = 40


def _max_tool_iterations(request_budget: int | None, active_skill: object) -> int | None:
    """Order of task rounds: request > /ephe cap > settings control > core default.

    I3-8: the control only applies when somebody has set it
    (read_generation_explicit). Otherwise every normal chat would inherit the
    register default 10 — and R46 had made 25 the default, because 10
    cut real assignments off in the middle of the work.
    """
    if request_budget is not None:
        return request_budget
    if active_skill and getattr(active_skill, "trigger", "") == "/ephe":
        return EPHE_TOOL_BUDGET
    from core.engine_config import read_generation_explicit

    return read_generation_explicit().get("tool_budget")

# P1-B: per-turn character budget for the composed skill system block. The
# sidecar budgets (_SIDECAR_BUDGETS) cap only the individual parts; without this
# overall ceiling, e.g. deck-creator (5965 chars) plus the top-3 tools (~900)
# blows the context window of 4b/8K models -> silent truncation. A priority cap
# in _compose_extra_system enforces it. Default for large models (12000);
# small (4b/8K) via EPHE_MAX_CONTEXT_CHARS=6000.
_DEFAULT_MAX_CONTEXT_CHARS = 12000


def _max_context_chars() -> int:
    """P1-B: total character budget of the skill system block, env-overridable."""
    try:
        # An empty EPHE_MAX_CONTEXT_CHARS counts as unset, so the default cap stays in force.
        raw = int(os.environ.get("EPHE_MAX_CONTEXT_CHARS", "") or _DEFAULT_MAX_CONTEXT_CHARS)
        return raw if raw > 0 else _DEFAULT_MAX_CONTEXT_CHARS
    except (ValueError, TypeError):
        return _DEFAULT_MAX_CONTEXT_CHARS

router = APIRouter(tags=["Chat"])

# Idle heartbeat of the SSE stream: seconds without queue activity after which
# a comment line (: keepalive) flows. Well below the 60-s idle
# detector of the frontend reader (app/src/lib/stream.ts), so that silent phases
# (thinking without a reasoning stream, tool-call generation) do not
# choke the turn. Env override for tests.
def _stream_heartbeat_s() -> float:
    try:
        # An empty EPHE_STREAM_HEARTBEAT_S counts as unset, so the keepalive keeps its default.
        return float(os.environ.get("EPHE_STREAM_HEARTBEAT_S", "") or 20.0)
    except (ValueError, TypeError):
        return 20.0


STREAM_HEARTBEAT_S = _stream_heartbeat_s()

#: A running tool reports its place every 5 s.
PROGRESS_HEARTBEAT_SECONDS = 5.0

# I6 P2 (2026-09-08): SSE keepalive (s) while the server waits for a sandbox
# approval. Without bytes the frontend idle timeout (app/src/lib/stream.ts, 90s)
# would otherwise drop the stream as a misleading error.
SANDBOX_KEEPALIVE_SECONDS: float = 20.0

# Sentinel value, never a model: equality with it means "nothing was chosen — the active
# provider decides". Empty while EPHE_MODEL is unset; the product ships no tag
# (owner decision 2026-10-11).
DEFAULT_MODEL = os.environ.get("EPHE_MODEL", "")
def _resolve_skill_invocation(message: str):
    """Return (skill, stripped_message) for explicit slash or high-confidence natural skill requests."""
    stripped = (message or "").strip()
    if not stripped.startswith("/"):
        lowered = stripped.lower()
        if "notebooklm" in lowered or "notebook lm" in lowered or "quellen-notebook" in lowered:
            notebook_skill = SkillLoader().resolve_trigger("/notebook")
            if notebook_skill:
                return notebook_skill, stripped
        skill = SkillLoader().resolve_for_message(stripped)
        return skill, stripped
    parts = stripped.split(maxsplit=1)
    trigger = parts[0]
    skill = SkillLoader().resolve_trigger(trigger)
    if not skill:
        return None, message
    user_content = parts[1].strip() if len(parts) > 1 else stripped
    return skill, user_content


def new_turn_id() -> str:
    """The id of this chat turn — short enough for a surface, long enough for a chain."""
    return uuid.uuid4().hex[:12]


def _register_artifact_safely(
    path: str,
    kind: str,
    session_id: str,
    label: str = "",
    *,
    turn_id: str = "",
    call_id: str = "",
    args_hash: str = "",
) -> str:
    """R17 artifact hub: register real file outputs in the persistent library
    (versioning via artifact_store). Must NEVER disturb
    the stream — errors are discarded silently.

    Returns the artifact **id** ('' without registration). The surface attaches it
    to the file_result event, so cards go by the id and not by a
    path it would have to look up itself (A0).
    """
    try:
        from core.artifact_store import register_artifact

        row = register_artifact(
            path=path, kind=kind, session_id=session_id or "", topic=(label or "")[:120],
            turn_id=turn_id, call_id=call_id, args_hash=args_hash,
        )
        return row["id"] if row else ""
    except Exception:
        return ""


def _schedule_auto_memory(user_message: str, answer: str) -> None:
    """R19 auto-memory: store Q/A persistently after the turn ends (settings toggle
    memory_enabled). Fire-and-forget — must never block or disturb the stream."""
    try:
        from core.auto_memory import capture_enabled, maybe_store_turn

        # I6-7: the same switch as in the core — one decision, one reader.
        if not capture_enabled():
            return
        if not (user_message or "").strip() or not (answer or "").strip():
            return

        # Deliberately SYNCHRONOUS after the done event: the store was not safe to
        # touch from a second thread (to_thread crashed with "recursive_mutex lock
        # failed"). After done a short sync call is harmless (~ms) and the stream
        # does not die.
        maybe_store_turn(user_message, answer)
    except Exception:
        pass


def _observe_for_learning(session_id: str, user_message: str, answer: str, history) -> None:
    """R31 learning loop: after a finished turn, look for learnable patterns.
    Pure heuristics (no model call) + JSON bookkeeping; never disturbs a turn."""
    try:
        from core.learning_loop import record_turn_and_detect

        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})
        if answer:
            messages.append({"role": "assistant", "content": answer})
        record_turn_and_detect(session_id or "default", messages)
    except Exception:
        pass
    # Wave 7: the gap table (B2) — detected gaps persisted, status traceable.
    try:
        from core.knowledge_gap import detect_gaps, record_gaps

        if answer and "[[GAP:" in answer:
            record_gaps(detect_gaps(answer))
    except Exception:
        pass


# R33 (stress P1-1): server-side history for REST callers
# The 1000-message campaign proved /api/chat kept NO server-side history:
# REST callers had to replay their own `history` array, so the server-side
# compaction path was unreachable for them. Turns sent with a session_id are
# now mirrored into the session store under a `rest-` namespace (mirrors the
# `pwa-` sync of R30). Unregistered ids never enter the registry, so the
# mirror stays invisible to the session list while remaining loadable.

_REST_SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REST_NS = "rest-"
_REST_MAX_MESSAGES = 2000
_REST_MAX_CHARS = 64_000


def _store_id_for(session_id: str) -> str | None:
    """The file a turn belongs to: a registered session's own id, otherwise the
    `rest-` mirror. None when the caller sent no valid id.

    Write-through is the Wave 5D rule: the server store is authoritative for a
    session a surface created; the mirror stays for ids nobody registered.
    """
    sid = (session_id or "").strip()
    if not sid or not _REST_SID_RE.match(sid):
        return None
    try:
        from core import multi_session as ms

        if ms.get_session(sid) is not None:
            return sid
    except Exception:
        logger.debug("session lookup skipped", exc_info=True)
    return _REST_NS + sid


def _persist_rest_turn(session_id: str, user_message: str, answer: str) -> None:
    """Append one completed turn to the rest- mirror. Best effort — a broken
    store must never break the chat reply itself."""
    store_id = _store_id_for(session_id)
    if store_id is None:
        return
    try:
        from core import multi_session as ms

        msgs = ms.load_messages(store_id)
        if (user_message or "").strip():
            msgs.append({"role": "user", "content": user_message[:_REST_MAX_CHARS]})
        if (answer or "").strip():
            msgs.append({"role": "assistant", "content": answer[:_REST_MAX_CHARS]})
        if len(msgs) > _REST_MAX_MESSAGES:
            msgs = msgs[-_REST_MAX_MESSAGES:]
        ms.save_messages(store_id, msgs)
    except Exception:
        logger.debug("rest turn persistence skipped", exc_info=True)


def _load_rest_history(session_id: str) -> list[dict]:
    """Persisted turns for a REST caller that omitted `history` ([] when no
    session id, invalid id or nothing stored)."""
    store_id = _store_id_for(session_id)
    if store_id is None:
        return []
    try:
        from core import multi_session as ms

        return list(ms.load_messages(store_id))
    except Exception:
        return []


def _preserve_compaction(session_id: str) -> None:
    """R25 compaction v2: Q/A pairs outside the compaction window are
    persisted permanently checkpoint-based (source="compaction"). Fire-and-forget,
    0 cost when nothing is new (checkpoint logic in core.compaction_memory)."""
    try:
        from core.compaction_memory import preserve_compacted_pairs

        preserve_compacted_pairs(session_id or "")
    except Exception:
        pass


# W16 (2026-09-10): post-turn jobs run OFF-Loop in the dedicated worker
# Store access and ONNX embedding must never block the asyncio event loop. The old
# sync path ("the client is not thread-safe") is kept with ONE worker
# thread: all jobs serialise in that same thread, so there is
# never parallel access to the store from two threads — but the loop stays
# free for API pings/SSE while storing (measured: < 5 ms median).
_POST_TURN_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ephe-post-turn")
# The REST mirror has its own single worker since 2026-10-09: one thread keeps the
# read-modify-write of a session store serialised (two in parallel lose a turn to the
# last rename), while closing a stream never queues behind an earlier request's Chroma
# round trip.
_MIRROR_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ephe-rest-mirror")
_POST_TURN_TASKS: set[asyncio.Task] = set()


def _post_turn_worker(user_message: str, answer: str, session_id: str, history) -> None:
    """Runs the heavy post-turn jobs IN ORDER in the worker thread.

    The REST history mirror is deliberately not one of them any more. It used to sit
    third in this fire-and-forget chain, so a streamed turn was stored only if the
    detached asyncio task survived the response closing — and this store is exactly
    what the NEXT turn reads back (`_load_rest_history`). Losing it means Ephe forgets
    an answer the user already saw. `_mirror_rest_turn` writes it before the sentinel.
    """
    _schedule_auto_memory(user_message, answer)
    _observe_for_learning(session_id, user_message, answer, history)
    _preserve_compaction(session_id)


async def _mirror_rest_turn(user_message: str, answer: str, session_id: str) -> None:
    """Persist one completed turn and WAIT for it (a JSON write, off the loop)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        _MIRROR_EXECUTOR, _persist_rest_turn, session_id, user_message, answer,
    )


async def run_post_turn_jobs(user_message: str, answer: str, session_id: str, history=None) -> None:
    """Run the heavy post-turn jobs in the dedicated worker executor (awaitable).

    The REST path awaits the future (semantics as before: memory is persisted
    after the answer), without blocking the loop. The history mirror is not part of
    this chain — every path calls `_mirror_rest_turn`, which it awaits."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        _POST_TURN_EXECUTOR, _post_turn_worker, user_message, answer, session_id, history,
    )


def _dispatch_post_turn_jobs(user_message: str, answer: str, session_id: str, history) -> None:
    """Fire-and-forget dispatch after the stream sentinel: the SSE generator
    closes at once, the Chroma round trips continue in the worker."""
    try:
        task = asyncio.create_task(run_post_turn_jobs(user_message, answer, session_id, history))
        _POST_TURN_TASKS.add(task)
        task.add_done_callback(_POST_TURN_TASKS.discard)
    except RuntimeError:
        # No running loop (direct call outside asyncio): finish synchronously.
        _post_turn_worker(user_message, answer, session_id, history)


def _compose_extra_system(skill, *, ask_mode: bool) -> str | None:
    """Deep audit 2026-09-13 (F2): compose system prompt + references + guard.

    Progressive disclosure: references/gold examples (reference_text/example_text)
    were parsed by the loader until now but never injected — which made the few-shot
    quality of the pack skills dead. Here they land in the active system block.
    Order: base prompt -> references -> gold example -> ask guard.
    """
    # P1-B: priority order for the overall cap. The base prompt and (in
    # ask_mode) the anti-hallucination guard are mandatory; the sidecars are
    # appended in importance order (few-shot example before reference) up to the
    # budget. Cuts at line boundaries so no list entry is severed mid-way.
    limit = _max_context_chars()
    # P1-B: the ask_mode guard is mandatory (anti-hallucination) and forced on
    # at the end; its room is reserved upfront in the optional budget so the
    # total never exceeds the ceiling.
    _reserve = (len(ASK_MODE_GUARD) + 2) if ask_mode else 0
    parts: list[str] = []
    used = 0

    def _fit(block: str, *, force: bool = False) -> None:
        nonlocal used
        if not block:
            return
        sep = 2 if parts else 0
        cap = limit - _reserve if not force else limit
        if force or used + sep + len(block) <= cap:
            parts.append(block)
            used += sep + len(block)
            return
        if not force:
            # over budget: cut the last piece at a line boundary
            room = (limit - _reserve) - used - sep
            if room <= 0:
                return
            cut = block[:room]
            nl = cut.rfind("\n")
            parts.append((cut[:nl] if nl > 0 else cut) + "\n…")
            used = limit

    base = skill.system_prompt if skill is not None else None
    if base:
        _fit(base, force=True)
    if skill is not None:
        # the few-shot example weighs more than the free reference -> first.
        _fit(f"## Example\n{skill.example_text}")
        _fit(f"## Reference\n{skill.reference_text}")
    elif not ask_mode:
        # P1-1: 0-hit fallback — the deterministic layer (trigger,
        # factory/artifact intent, tool name, phrase score) has no result.
        # A compact index gives the model the semantic choice
        # before the ask_mode guard effectively shuts the answer away.
        try:
            from core.skills import SkillLoader
            index = SkillLoader().build_skill_index()
            if index:
                _fit(f"## Skill-Index\n{index}")
        except Exception:
            pass
    if ask_mode:
        _fit(ASK_MODE_GUARD, force=True)
    return "\n\n".join(parts) if parts else None


#: The edit family for the edit-auto mode (B-9, design doc).
#: Admission criterion: the tool applies an artifact delivered by the model
#: 1:1 and deterministically — no reach back into
#: the react loop, no interpreter/probe semantics.
#:   - edit_file  : old->new as diff lines straight out of the prompt
#:   - write_file : complete file content, written 1:1 — therefore
#:                  family-capable (no patch/merge step needed)
#: Deliberately NOT admitted (they keep their own approval paths):
#:   - apply_patch: multi-hunk strictness + context-mismatch rules,
#:                  approving it as "edit" would never be equivalent there
#:   - run_shell  : process/network semantics, head-based memo instead of type memo
_EDIT_TOOL_NAMES = {"edit_file", "write_file"}
#: The read-only tools a Plan-mode turn still OFFERS the model. The enforcement set
#: lives in core (``core.tools.chat_gate.READ_ONLY_MODE_TOOLS``) and is a superset of
#: this one — it adds the deferred index and the forwarder, which are judged at the
#: call they execute. W10: this list is what the model SEES; it is not the guard.
_READ_ONLY_TOOL_NAMES = {"read_file", "file_search", "list_directory", "web_search", "ask_user"}


def _shell_segment_heads(command: str) -> list[str]:
    """First token of every shell segment — the memo keys of the run_shell approval.

    B-7: 'git status --short && npx -- vite' → ['git', 'npx']. Empty list for a
    command that cannot be parsed (then the normal dialog applies, no memo).
    """
    from core.tools._shell_validate import _shell_segments

    segments = _shell_segments(command or "")
    if segments is None:
        return []
    return [seg[0] for seg in segments if seg]


def _resolve_mode(mode: str) -> dict[str, bool]:
    """Split the UI mode string into the four boolean factors (hyphen/underscore tolerant).

    Old client 'agent' and empty → all factors False (not-ask, manual
    approval) — exactly the previous behaviour, backward compatible.
    """
    key = (mode or "").strip().lower().replace("-", "_")
    return {
        "ask": key == "ask",
        "plan": key == "plan",
        "edit_auto": key == "edit_auto",
        "full_access": key == "full_access",
    }


def _mode_context(mode: str, *, skill, message: str) -> tuple[str | None, list[str] | None, dict[str, bool]]:
    """Mode → (extra_system_prompt, allowed_tool_names, mode_flags).

    Used identically by BOTH chat routes (/chat and /chat/stream),
    so that ask/plan/edit-auto/full-access carry the same semantics on both
    paths: ask = no tools, plan = read-only inspection + plan guard,
    edit-auto = edit family auto-approved (via profile), full = autonomous.
    """
    flags = _resolve_mode(mode)
    ask_mode = flags["ask"]
    plan_mode = flags["plan"]
    extra_system = _compose_extra_system(skill, ask_mode=ask_mode)
    if needs_compute_guard(message):
        extra_system = f"{extra_system}\n\n{COMPUTE_GUARD}" if extra_system else COMPUTE_GUARD
    # #92: a request for a web page carries the design floors of the answer, because an
    # unstyled browser-default document is what the engine produces without them.
    if needs_page_guard(message):
        extra_system = f"{extra_system}\n\n{PAGE_OUTPUT_GUARD}" if extra_system else PAGE_OUTPUT_GUARD
    if plan_mode:
        extra_system = f"{extra_system}\n\n{PLAN_MODE_GUARD}" if extra_system else PLAN_MODE_GUARD
    if ask_mode:
        allowed_tools: list[str] | None = []
    elif plan_mode:
        base = skill.tools if (skill and skill.tools) else None
        allowed_tools = [t for t in (base or list(_READ_ONLY_TOOL_NAMES)) if t in _READ_ONLY_TOOL_NAMES]
    else:
        allowed_tools = skill.tools if skill else None
    return extra_system, allowed_tools, flags


def _publish_tool_mode(mode: str):
    """Make the mode readable where a tool is EXECUTED (W10), returning its reset token.

    ``_mode_context`` decides what the model is OFFERED — a list. A tool that arrives
    through the deferred bridge (``tool_search`` + ``tool_call``) is dispatched by NAME
    at execution time and never consults that list, so the same mode has to travel to
    ``execute_tool`` (``core.tools.chat_gate.mode_denial``). Every turn that resolves a
    mode publishes it here and hands the token back in its ``finally``.
    """
    from core.tools.session_ctx import set_current_mode

    return set_current_mode(mode)


# Pydantic Models

class ChatRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL
    history: list[dict] = []
    # R24/R25: session linkage (compaction checkpoint, artifacts) —
    # optional, old clients without the field land in the active session.
    session_id: str = ""
    # P4: mode parity with the stream route — identical semantics on /chat.
    mode: str = "agent"
    autonomous: bool = False


class ChatResponse(BaseModel):
    response: str
    model: str


class StreamRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL
    history: list[dict] = []
    autonomous: bool = False
    images: list[str] = []       # Base64-encoded images for 12B multimodal
    force_tier: str | None = None  # Optional: "offline" | "fast" | "power"
    session_id: str = ""         # R17 artifact hub: session linkage of the artifacts
    # W19: UI mode ("ask" | "edit_auto" | "plan" | "full_access"; "agent" = old client).
    # ask = fail-closed without tools + an anti-hallucination guard in the system prompt.
    mode: str = "agent"
    # N9b: per-request tool budget for the agent loop (L5 long-horizon tasks
    # need >10 calls). None = profile default (10); clamped to the hard
    # cap via clamp_tool_budget.
    tool_budget: int | None = None


class ApproveRequest(BaseModel):
    token: str
    approved: bool
    remember: bool = False


class AskAnswerRequest(BaseModel):
    """The answer to one pending `ask_user` (G1: the run that is awaiting it)."""

    token: str
    #: The chosen label, the typed text, or the comma-joined labels of a multi-select.
    #: Empty is refused by the endpoint: the empty string already means "nobody
    #: answered" on the waiting side, and a second meaning would blur the two.
    answer: str = ""

class SteerRequest(BaseModel):
    """A direction change for a turn that is already running.

    ``stop`` turns the steer into "end this at the next safe point" — the same
    message path, one flag: the loop takes it up at a round boundary, so nothing
    is cut off between a tool's side effect and its record.
    """

    text: str = ""
    session_id: str = ""
    turn_id: str = ""
    actor: str = "user"
    agent_id: str = ""
    stop: bool = False

# Request-scoped sandbox state (T-02 fix)
# ContextVar: every asyncio request gets its own sandbox dict.
# No leak between simultaneous requests, also with uvicorn --workers N.
from contextvars import ContextVar as _ContextVar

_sandbox_store: _ContextVar[dict | None] = _ContextVar('ephe_sandbox_store', default=None)


def get_sandbox() -> dict:
    """Returns the request-scoped sandbox state dict (creates it when needed)."""
    store = _sandbox_store.get()
    if store is None:
        store = {}
        _sandbox_store.set(store)
    return store


# App-wide token registry for cross-request sandbox approval
# (approve_sandbox runs in its own request context, hence no ContextVar)
_active_sandbox_events: dict[str, dict] = {}

#: How long a question is held open. A late click must not approve a call that has
#: already continued on its stated default; the endpoint answers 410 for a token that
#: was open and timed out, which is a different fact from an invented token (404).
APPROVAL_TTL_SECONDS = 300.0
_expired_sandbox_tokens: dict[str, float] = {}


def pending_approvals() -> list[dict]:
    """The approval waits nobody has answered yet, longest wait first.

    The fleet reads a run that stopped on a person's answer from here (`core/fleet.py`),
    because this is the only registry that can say it: the run is alive, its status is
    "running", and what is actually true is that it is idle and waiting. Each entry carries
    the session that asked, the tool, and when the question was put — without those three a
    wait cannot be attributed to a run or shown as a wait.
    """
    moment = time.time()
    rows: list[dict] = []
    for token, entry in _active_sandbox_events.items():
        if not isinstance(entry, dict) or entry.get("approved"):
            continue
        asked = entry.get("requested_at")
        rows.append(
            {
                "token": token,
                "session_id": str(entry.get("session_id") or ""),
                "tool": str(entry.get("tool") or ""),
                "waiting_seconds": max(0, int(moment - asked)) if isinstance(asked, (int, float)) else None,
            }
        )
    rows.sort(key=lambda row: -int(row.get("waiting_seconds") or 0))
    return rows

#: W-3: a hosted engine explains a 4xx in the response body — the unknown model
#: name, the exhausted quota, the refused key. The body is read bounded and the
#: sentence carries at most this many characters of the provider's own wording.
PROVIDER_DETAIL_LIMIT = 300

#: httpx's own `raise_for_status` wording: "Client error '400 Bad Request' for url …".
_PROVIDER_HTTPX_LINE = re.compile(r"(?:Client|Server) error '(\d{3})\b")
#: The wording core/model_provider.py writes for a non-streaming 4xx:
#: "400 Bad Request: {…}" — the status prefix, then the body after the colon.
_PROVIDER_STATUS_PREFIX = re.compile(r"^(\d{3})\b[^:]*:\s*(.*)\Z", re.S)

#: The keys a provider puts its human sentence under, most specific first.
_PROVIDER_MESSAGE_KEYS = ("message", "detail", "error_description", "error", "reason")

#: The next step each refused status leaves the reader. The status decides it: a
#: refused key is not fixed by waiting, and a 429 is not fixed by editing settings.
_PROVIDER_REFUSAL_MOVES = {
    "auth": "Check the key for this engine under Settings - Engine, then send the message again.",
    "rate_limit": "Wait a moment, then send the message again.",
    "other": "Check the engine's model name and settings, then send the message again.",
}

#: The clause the engine's own words arrive in. The bundles carry the same slot under
#: their own wording, and a test renders both against the sentence this file writes.
_PROVIDER_ANSWER_CLAUSE = " The engine answered: {detail}"

#: The class -> code table the readable surface keys on. A status picks the class, the
#: class picks the code, and a bundle holds the sentence for it — the pairing
#: `server/refusals.py` states for the routes, here for the one failing stream frame.
PROVIDER_REFUSAL_CODES = {
    "auth": "provider_key_refused",
    "rate_limit": "provider_rate_limited",
    "other": "provider_request_refused",
}


def _provider_detail_from_payload(payload: object) -> str | None:
    """The sentence a provider body holds, or None when it holds none."""
    if isinstance(payload, str):
        return payload.strip() or None
    if isinstance(payload, dict):
        for key in _PROVIDER_MESSAGE_KEYS:
            found = _provider_detail_from_payload(payload.get(key))
            if found:
                return found
        return None
    if isinstance(payload, list):
        for item in payload:
            found = _provider_detail_from_payload(item)
            if found:
                return found
    return None


def _provider_detail_from_body(body: str) -> str | None:
    """The provider's own sentence in a 4xx body, or None when the body has none.

    A JSON envelope donates the string under one of the known keys; a bare
    sentence is taken as is. The two lines this repo itself writes for an HTTP
    failure (httpx's and core/model_provider.py's) are unwrapped rather than
    echoed, so a reader never gets a URL or a bare code as the explanation.
    """
    text = (body or "").strip()
    if not text:
        return None
    prefixed = _PROVIDER_STATUS_PREFIX.match(text)
    if prefixed:
        text = prefixed.group(2).strip()
    if not text or _PROVIDER_HTTPX_LINE.match(text):
        return None
    start = 0 if text[:1] in "{[" else text.find("{")
    if start >= 0:
        try:
            payload = json.loads(text[start:])
        except (ValueError, TypeError):
            payload = None
        if payload is not None:
            return _provider_detail_from_payload(payload)
    if re.match(r"^\d{3}\b", text):
        return None
    return text


def _provider_http_status(exc: Exception) -> int | None:
    """The HTTP status a provider failure carries, or None.

    Read from the response an httpx.HTTPStatusError holds and from a status_code
    attribute, then from the two status lines this repo's HTTP failures are
    written with. A number that merely appears in an unrelated message is not a
    status — otherwise any error naming a port could wear a provider refusal.
    """
    for holder in (getattr(exc, "response", None), exc):
        status = getattr(holder, "status_code", None)
        if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
            return status
    raw = str(exc) or ""
    match = _PROVIDER_HTTPX_LINE.search(raw) or _PROVIDER_STATUS_PREFIX.match(raw)
    return int(match.group(1)) if match else None


def _bounded_provider_detail(exc: Exception) -> str:
    """The provider's own wording for a 4xx, one bounded line or the empty string.

    Taken from the response object when it holds one and from the message text
    otherwise; the reader never opens a socket itself. Whitespace is folded and
    the length is capped, so neither the bubble nor the model context receives an
    unbounded body.
    """
    response = getattr(exc, "response", None)
    for source in (getattr(response, "text", None), str(exc) or ""):
        if not isinstance(source, str):
            continue
        found = _provider_detail_from_body(source)
        if found:
            flat = " ".join(found.split())
            if len(flat) > PROVIDER_DETAIL_LIMIT:
                flat = flat[: PROVIDER_DETAIL_LIMIT - 3].rstrip() + "..."
            return flat
    return ""


def _provider_refusal_kind(status: int) -> str:
    """Which of the three refusals a 4xx status is."""
    from core.provider_errors import AUTH_STATUSES, RATE_LIMIT_STATUS

    if status in AUTH_STATUSES:
        return "auth"
    if status == RATE_LIMIT_STATUS:
        return "rate_limit"
    return "other"


def _provider_refusal_sentence(status: int, detail: str = "") -> str:
    """The refusal a 4xx gets, keeping the sentence the rest of the app reports.

    The wording before the clause comes from the one failure table
    (``core.provider_errors.classify_status``) — the same sentence the serve
    error body and the CLI show for this status — so the transport code stays
    what it already was and only the provider's explanation is added. Without an
    explanation the clause is dropped, which is the sentence that already shipped.
    """
    from core.provider_errors import classify_status

    move = _PROVIDER_REFUSAL_MOVES[_provider_refusal_kind(status)]
    sentence = f"{classify_status(status).message} {move}"
    return f"{sentence}{_PROVIDER_ANSWER_CLAUSE.format(detail=detail)}" if detail else sentence


def provider_refusal_frame(exc: Exception) -> dict:
    """``reason_code``/``reason_params`` for a provider 4xx, or an empty dict.

    A code travels only where the failure names something the surface can render:
    the engine's own words sit in the params, and a 4xx that carried none leaves the
    frame uncoded — the rule `tool_done` set in f5d88653, so neither key appears for
    a result that has no reason to give.
    """
    status = _provider_http_status(exc)
    if status is None or not 400 <= status < 500:
        return {}
    detail = _bounded_provider_detail(exc)
    if not detail:
        return {}
    return {
        "reason_code": PROVIDER_REFUSAL_CODES[_provider_refusal_kind(status)],
        "reason_params": {"status": status, "detail": detail},
    }


def _friendly_model_error_inner(exc: Exception, provider: ModelProviderConfig | None = None) -> str:
    """Return a user-facing model error that matches the offline-first setup story."""
    raw = str(exc)
    lower = raw.lower()
    active = provider or get_active_provider()

    if active.provider == "local_ollama" and any(
        marker in lower
        for marker in (
            "failed to connect",
            "connection",
            "connecterror",
            "refused",
            "socket",
            "not running",
        )
    ):
        return (
            "Local Ollama is not reachable right now. "
            "Start Ephe with `ephe start` or check with `ephe doctor`."
        )

    if active.provider == "local_ollama" and any(
        marker in lower
        for marker in ("not found", "does not exist", "nicht installiert", "missing", "not installed")
    ):
        return (
            f"Local model '{active.model}' is missing or not loadable. Start the repair with `ephe doctor` and then `ephe start`."
        )

    # Finding 2026-10-01 (F-T): OpenCode locks its free tier server-side to its
    # own client (FreeTierError, fingerprinting — community sources 09/2026
    # confirm: spoofing does not help). Word it honestly and with a way out,
    # instead of showing a bare 403.
    #
    # Decision (n19): the provider is named in the sentence below, and stays
    # named, because the sentence is about that provider's own server-side
    # restriction. Said without the name, the reader could not tell which
    # service refused the call nor where the way out lies. Data about a real
    # external service — quoted, so the next sweep does not re-open this.
    if "freetiererror" in lower or "free tier" in lower:
        return (
            "OpenCode allows its free models only inside the OpenCode client "
            "(provider-side restriction since 09/2026). Pick an OpenRouter "
            "':free' model in Engine settings, or use a paid engine — your "
            "call, never a hidden fallback."
        )

    if "api key expired" in lower:
        return (
            "Your API key for this engine has expired. Store a fresh one in "
            "EPHE_OPENAI_COMPAT_API_KEY or in ~/.ephe/engine.key, or paste it in "
            "Engine settings — the model choice stays untouched."
        )

    # W-3 (walkthrough): a hosted engine explains a 4xx in the body — the model
    # name it does not know, the quota that ran out, the key it refused. Without
    # this branch the mapper hands the reader the class name or a bare status and
    # the explanation is lost; the status it carries stays the one the failure
    # table reports.
    status = _provider_http_status(exc)
    if status is not None and 400 <= status < 500:
        return _provider_refusal_sentence(status, _bounded_provider_detail(exc))

    # P1c (deep audit 2026-09-16): never return an empty string — with an empty str(exc) and
    # a non-matching provider branch the fallback falls back to the class name
    # (analogous to _error_msg), so the stream error event never carries an empty msg.
    return raw or type(exc).__name__



def _friendly_model_error(exc: Exception, provider: ModelProviderConfig | None = None) -> str:
    """R23: secrets (API keys in URLs, tokens) are masked before the output."""
    from core.redact import redact

    return redact(_friendly_model_error_inner(exc, provider))


def _unreachable_engine_message(provider: ModelProviderConfig | None = None) -> str:
    """The engine-down sentence for the engine this turn was actually dialled.

    ``OllamaNotReachableError`` is the transport-down bucket of *every* provider —
    an OpenAI-compatible engine raises it too (a refused connect is a refused
    connect; test_wc22 pins that class for one). Its own text therefore cannot
    decide the sentence: only a turn against the local Ollama engine may be told
    to start Ollama, or the reader is sent to fix a machine the turn never used.
    """
    active = provider or get_active_provider()
    if getattr(active, "provider", "") == "local_ollama":
        return "Ollama not reachable — start it: ollama serve"
    base_url = getattr(active, "base_url", "") or "the configured endpoint"
    return f"Engine not reachable: {base_url}. Check the endpoint and the URL with `ephe doctor`."


def _error_msg(exc: Exception) -> str:
    """R37: error events are never empty — fallback to the exception class name."""
    msg = str(exc).strip()
    return msg if msg else type(exc).__name__


def sandbox_auto_approval_allowed(*, autonomous: bool) -> bool:
    """R37: the opt-in autonomous flag is respected.

    The default (autonomous=False) stays strict: the manual confirmation path.
    An explicitly set autonomous flag of the assignment (the composer mode,
    carries it, and nothing else does) passes the 1x confirmation per request on as auto-approve."""
    return bool(autonomous)


# Routes

def _ensure_engine_ready() -> None:
    """W19 B4: chat stays fail-closed in setup mode.

    When the server starts without an engine (the SETUP-MODE flag from run_server), no
    model answers — otherwise the silent local_ollama default would throw a newcomer
    a cryptic connection error instead of a clear hint. As soon as
    the user has chosen (the setup UI persists engine.json / env /
    session override), the chat is open again.
    """
    if (os.environ.get("EPHE_SETUP_MODE")) != "1":
        return
    from core.engine_config import load_engine_config
    from core.model_provider import has_explicit_provider

    if has_explicit_provider() or load_engine_config() is not None:
        return
    raise HTTPException(
        status_code=409,
        detail="No engine configured yet — pick one on the Setup page, or run `ephe configure`.",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Synchronous chat endpoint (waits for the complete answer)."""
    _ensure_engine_ready()
    from core.plugin_commands import expand_plugin_command

    request.message = expand_plugin_command(request.message)
    provider = get_active_provider()
    model = provider.model if request.model == DEFAULT_MODEL else request.model
    # R33 (P1-1): REST callers may omit `history` — the server then feeds back
    # the turns it persisted for this session id (rest- mirror). The
    # server-owned fallback goes through the deterministic compactor so long
    # REST sessions stay bounded (caller-provided history stays verbatim, the
    # streaming path compacts inside chat_with_tools).
    history_ctx = request.history
    if not history_ctx and request.session_id:
        try:
            from core.conversation_compactor import compact_history, window_threshold

            history_ctx = compact_history(
                _load_rest_history(request.session_id),
                threshold_tokens=window_threshold(model),
            )
        except Exception:
            history_ctx = []
    # P4: mode parity — identical ask/plan/edit-auto/full semantics as /chat/stream.
    rest_extra_system, rest_allowed_tools, _mode_flags = _mode_context(
        request.mode, skill=None, message=request.message
    )
    # W10: the same mode travels to the execution choke point, so a tool reached
    # outside the offer list (tool_call bridge) is refused there.
    _rest_mode_token = _publish_tool_mode(request.mode)
    # G7: the REST path records its provenance too, so "every run" holds and not
    # only the streaming one. A turn is opened only when a session names one —
    # without a session there is no past turn to open the facts from.
    _rest_turn_id = new_turn_id()
    _rest_turn_open = bool(request.session_id)
    if _rest_turn_open:
        trajectory.begin_turn(request.session_id, model, _rest_turn_id)
    try:
        response_text = await react_loop(
            question=request.message,
            model=model,
            context=history_ctx,
            provider_config=provider,
            allowed_tool_names=rest_allowed_tools,
            extra_system_prompt=rest_extra_system,
            session_id=request.session_id,
            turn_id=_rest_turn_id,
        )
        # W16: the heavy post-turn jobs run in the dedicated worker (off-loop) and the
        # future is awaited — the answer waits for the persistence as before, the loop
        # stays usable in the meantime. The history mirror is awaited first and on its
        # own worker, so both chat paths store the turn before it is reported done.
        await _mirror_rest_turn(request.message, response_text or "", request.session_id)
        await run_post_turn_jobs(request.message, response_text or "", request.session_id, history_ctx)
        return ChatResponse(response=response_text or "", model=model)
    except ProviderSetupError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OllamaNotReachableError:
        raise HTTPException(status_code=503, detail=_unreachable_engine_message(provider))
    except OllamaModelNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"model '{exc.model}' is not installed.")
    finally:
        from core.tools.session_ctx import reset_current_mode

        reset_current_mode(_rest_mode_token)
        if _rest_turn_open:
            trajectory.end_turn(request.session_id)


def _clip_tool_value(value: object) -> str:
    text = str(value)
    return text if len(text) <= 300 else text[:300] + "\u2026"


# Prefix → (file_type, base_label, activity_word, label_carries_filename), the
# registration table for "a tool-result line announces an artifact". The rows live
# once in core/artifact_markers; the frontend copy (app/src/lib/fileMarkers.ts) is
# pinned to them both ways by tests/test_artifact_marker_tables.py and the shared
# rows by tests/test_artifact_marker_single_source.py — a table that drifts
# silently is exactly how the W10 gap appeared. Shrinks the sevenfold if/elif chain
# of the file markers in on_tool_done down to one lookup; PDF carries 'PDF_PAGES:'
# in line 2 — only the 'PDF_FILE:' line is the path (a poisoned artifact path).
_FILE_RESULT_PREFIXES: tuple[tuple[str, str, str, str, bool], ...] = ARTIFACT_MARKERS

# Marker lookup: longest prefix first, so a shorter marker can never shadow a
# longer one that starts the same way on a result line.
_MARKER_BY_PREFIX: dict[str, tuple[str, str, str, str, bool]] = {
    row[0]: row for row in _FILE_RESULT_PREFIXES
}
_PREFIXES_LONGEST_FIRST: tuple[str, ...] = tuple(
    sorted(_MARKER_BY_PREFIX, key=len, reverse=True)
)


def _emit_file_result_event(
    name: str,
    result: str,
    emit: Callable[[dict], None],
    session_id: str,
    *,
    call_id: str = "",
    args_hash: str = "",
    turn_id: str = "",
) -> None:
    """Marker-based file artifact events out of a tool result.

    A result may announce several artifacts, one marker per line: the deck tools
    return the deck plus its scorecard, manifest, QA, spec, ledger and preview in
    a single string. Every marker line is registered and emitted. The previous
    version matched only one marker at the very start of the result and returned,
    so such a result reached the workbench as one card out of seven.

    RENDER_QA_FILE and VISUAL_QA_FILE name the same file (deck_render writes one
    canonical QA report). Both markers still emit their event, but the library
    keeps one row per path — the second marker reuses the first row's id.
    """
    if not isinstance(result, str):
        return
    registered: dict[str, str] = {}
    matched = False
    for raw_line in result.splitlines():
        # The marker must open the line. Not stripped: a unified diff body puts a
        # space/+/- in front of every line, so a written file that happens to
        # contain a marker-looking line can never register a phantom artifact.
        prefix = next((p for p in _PREFIXES_LONGEST_FIRST if raw_line.startswith(p)), "")
        if not prefix:
            continue
        path = raw_line[len(prefix):].strip()
        if not path:
            continue
        matched = True
        file_type, base_label, activity_word, with_name = _MARKER_BY_PREFIX[prefix][1:]
        label = f"{base_label}: {path.split('/')[-1]}" if with_name else base_label
        if path in registered:
            artifact_id = registered[path]
        else:
            artifact_id = _register_artifact_safely(
                path, file_type, session_id, path.split('/')[-1],
                call_id=call_id, args_hash=args_hash, turn_id=turn_id,
            )
            registered[path] = artifact_id
        emit({"type": "file_result", "file_type": file_type, "path": path,
              "label": label, "id": artifact_id, "turn_id": turn_id})
        emit({"type": "activity", "cmd": f"{name} → {activity_word} saved ✅", "status": "done"})
    if not matched:
        emit({"type": "activity", "cmd": f"{name} → {result[:40]}", "status": "done"})


SILENT_ENGINE_TURN = (
    "Die Engine hat nichts zurückgegeben — kein Text, kein Werkzeuglauf, und "
    "sie hat nicht verraten, warum. Versuch es noch einmal; wenn es bleibt, "
    "sieh in den Einstellungen nach, welche Engine aktiv ist."
)


SILENT_AFTER_TOOLS_TURN = (
    "Die Werkzeuge sind durchgelaufen, aber zum Schluss hat die Engine nichts "
    "mehr gesagt. Was erzeugt wurde, liegt in der Werkbank — die Antwort selbst "
    "ist ausgeblieben. Versuch es noch einmal."
)


def silent_turn_message(answer: str, captured_tool_results: list) -> str | None:
    """Which honest message this turn needs — None when it has content.

    W8: the tool exception that applied here before was half the truth. A
    run that writes four files and then falls silent is just as mute for the user —
    only a different story, therefore also a different sentence.
    """
    if answer.strip():
        return None
    return SILENT_AFTER_TOOLS_TURN if captured_tool_results else SILENT_ENGINE_TURN


#: the two silent-turn sentences with the code the surface translates by
SILENT_TURN_CODES = {SILENT_ENGINE_TURN: "silent_engine_turn", SILENT_AFTER_TOOLS_TURN: "silent_after_tools_turn"}


def silent_turn_event(answer: str, captured_tool_results: list) -> dict | None:
    """The stream frame for a mute turn, or None when the turn has content.

    Same shape as `tool_done` since f5d88653: `reason_code` travels beside the sentence, never instead
    of it, so a surface that knows the code can render its own language and one that does not keeps
    reading `msg`.
    """
    msg = silent_turn_message(answer, captured_tool_results)
    if msg is None:
        return None
    return {"type": "error", "msg": msg, "reason_code": SILENT_TURN_CODES[msg]}


def _make_stream_callbacks(
    emit: Callable[[dict], None],
    first_chunks: list[str],
    captured_tool_results: list,
    session_id: str,
    turn_id: str = "",
    refused_tools: dict[str, int] | None = None,
) -> tuple[Callable, Callable, Callable, Callable, Callable]:
    """Creates the chat_with_tools callbacks of an SSE turn.

    All of them write into the same ``emit`` queue: ``first_chunks`` collects the
    token stream of the first answer, ``captured_tool_results`` the normalized
    tool results; ``_tool_t0`` carries the per-call start stamps (key
    ``(name, call_id)`` for same-named calls of one round).

    ``refused_tools`` is the shared outcome ledger of this turn: the handler counts a
    tool there when the user answered the approval dialog with "no", and ``on_tool_done``
    consumes one entry for that tool to send ``status: "failed"`` on its frame. It
    carries the refusals that arrive as a plain sentence — the shell path returns its
    own abort sentence and appends no reason code, so the frame would otherwise look
    like a successful run to every reader (walkthrough 2026-10-12, FINDINGS §medium).
    """
    _refused: dict[str, int] = refused_tools if refused_tools is not None else {}
    _tool_t0: dict[tuple[str, str], float] = {}
    # A0: the same key as the start stamp. A registered artifact can then
    # say out of which call it was born. core.redact.args_hash hashes the
    # UNREDACTED arguments — which is why the surface shows the call_id and never the
    # hash (16 hex digits without salt are, for a file name, a confession).
    _tool_args_hash: dict[tuple[str, str], str] = {}
    # P6: collect the reasoning text per thinking phase and, at the next hard
    # event (content chunk or tool start), write it as ONE thinking step with
    # its full text body into the trajectory.
    _thinking_buf: list[str] = []

    # Live progress: the round comes from the bound observer, the query from the call.
    _progress: dict[str, object] = {"tool": "", "started": 0.0, "task": None}

    def _round_state() -> tuple[int, int]:
        try:
            from core.loop_observability import current_observer

            observer = current_observer()
            if observer is None:
                return (0, 0)
            return (observer.counters.tool_rounds, observer.counters.budget_cap)
        except Exception:
            return (0, 0)

    def _progress_frame(phase: str, **extra: object) -> dict:
        round_no, cap = _round_state()
        started = float(_progress.get("started") or 0.0)
        elapsed = round((time.perf_counter() - started) * 1000) if started else 0
        return {
            "type": "progress",
            "turn_id": turn_id,
            "round": round_no,
            "round_cap": cap,
            "tool": _progress.get("tool") or "",
            "phase": phase,
            "elapsed_ms": elapsed,
            **{key: value for key, value in extra.items() if value not in (None, "")},
        }

    def _stop_beat() -> None:
        task = _progress.get("task")
        if task is not None:
            try:
                task.cancel()  # type: ignore[union-attr]
            except Exception:
                pass
        _progress["task"] = None

    def _start_beat() -> None:
        _stop_beat()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _beat() -> None:
            while True:
                await asyncio.sleep(PROGRESS_HEARTBEAT_SECONDS)
                emit(_progress_frame("tool_progress"))

        _progress["task"] = loop.create_task(_beat())

    def _providers_of(result: object) -> str:
        text = str(result or "")
        for line in text.splitlines()[:2]:
            if line.startswith("Providers: "):
                return line[len("Providers: "):][:160]
        return ""

    def _flush_thinking() -> None:
        if _thinking_buf:
            emit({"type": "thinking", "text": "".join(_thinking_buf)})
            _thinking_buf.clear()

    # #92: the plan is its own frame, so the reader watches the steps arrive and move
    # instead of waiting for a whole answer. Two sources, one shape: the checklist in the
    # answer text (the draft the user accepts) and the todo_list ledger (the state that
    # moves). A frame goes out only when the payload actually changed.
    _plan_gate = {"lines": 0, "payload": ""}

    def _emit_plan(plan: EphePlan | None) -> None:
        if plan is None:
            return
        payload = plan.as_dict()
        key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if key == _plan_gate["payload"]:
            return
        _plan_gate["payload"] = key
        emit({"type": "plan", **payload})

    def _plan_from_answer() -> None:
        text = "".join(first_chunks)
        # Counted per line segment: a step's first character arrives on a line that has no
        # terminator yet, and that is the moment the reader should see it.
        segments = text.count("\n") + (0 if text.endswith("\n") else 1)
        if segments == _plan_gate["lines"]:
            return
        _plan_gate["lines"] = segments
        _emit_plan(EphePlan.try_from_markdown(text))

    def on_chunk(chunk: str) -> None:
        _flush_thinking()
        first_chunks.append(chunk)
        emit({"type": "chunk", "data": chunk})
        _plan_from_answer()

    def on_thinking(chunk: str) -> None:
        # Thinking stream (AI-client parity): stream the reasoning text — the client
        # renders it collapsed ("Denkt nach…"); only the output is the content.  # language-gate: ignore (quoted product label, app/src/locales/de.json:26 thinkingNow)
        _thinking_buf.append(chunk)
        emit({"type": "thinking_chunk", "data": chunk})

    def on_tool_start(name: str, args: dict, call_id: str = "") -> None:
        # I6 P1-2: structured event for the persistent tool-stream lines.
        # W15-P3: key (name, call_id) — each same-named call gets its own start stamp.
        _flush_thinking()
        _tool_t0[(name, call_id)] = time.perf_counter()
        try:
            from core.redact import args_hash

            _tool_args_hash[(name, call_id)] = args_hash(args)
        except Exception:
            pass
        _query = str((args or {}).get("query") or "") if name == "web_search" else ""
        _progress.update({"tool": name, "started": time.perf_counter(), "query": _query})
        _start_beat()
        emit({"type": "tool_start", "tool": name, "call_id": call_id, "turn_id": turn_id,
              "args": {k: _clip_tool_value(v) for k, v in (args or {}).items()}})
        emit(_progress_frame("tool_start", query=_query))
        emit({"type": "activity", "cmd": f"{name}({json.dumps(args, ensure_ascii=False)[:60]})", "status": "running"})

    def on_tool_done(name: str, result: str, call_id: str = "") -> None:
        # I6 P1-2: tool_done delivers the frontend line result (shortened).
        _txt = result if len(result) <= 3000 else result[:3000] + "\u2026"
        # K3 Z08: runtime on the server-side timestamp (reference: audit).
        _t0 = _tool_t0.pop((name, call_id), None)
        _args_hash = _tool_args_hash.pop((name, call_id), "")
        _dur = round((time.perf_counter() - _t0) * 1000, 1) if _t0 is not None else None
        _extra: dict[str, object] = {"duration_ms": _dur} if _dur is not None else {}
        # A refusal that knows its reason carries it beside its sentence, in the
        # payload shape the reader route already uses. `result` stays the text every
        # client reads today; an uncoded result sends neither field.
        _code = getattr(result, "code", "") or ""
        if _code:
            _extra["reason_code"] = _code
            _extra["reason_params"] = dict(getattr(result, "params", {}) or {})
        # w10-12: the outcome, in the vocabulary the activity lines already use. Without
        # it every tool_done reached the client as "completed", so a refusal was painted
        # as a success (walkthrough 2026-10-12, FINDINGS §medium: "A deny is visibly
        # swallowed"). Three seams say "this call did not run": a reason code on the
        # result (the gate's `Denied`), the audit's own classifiers (`is_error_result` /
        # `result_decision` — a `[TOOL-DENIED]` sentence without a code still counts), and
        # the answer the user gave to the approval dialog, which is the only trace the
        # shell path leaves. One entry of the ledger is consumed per call.
        _pending_refusal = _refused.get(name, 0)
        if _pending_refusal:
            _refused[name] = _pending_refusal - 1
        _refused_result = is_error_result(result) or result_decision(result) == "blocked"
        _extra["status"] = (
            "failed" if (_code or _pending_refusal or _refused_result) else "completed"
        )
        _stop_beat()
        emit({"type": "tool_done", "tool": name, "call_id": call_id, "turn_id": turn_id, "result": _txt, **_extra})
        emit(_progress_frame(
            "tool_done",
            status=_extra.get("status"),
            providers=_providers_of(result),
            query=str(_progress.get("query") or ""),
        ))
        if name == "todo_list":
            # The ledger had no reader before #92: the plan card is how its four
            # statuses reach the user.
            from core.tools.todo_tools import get_todo

            _emit_plan(EphePlan.from_ledger(get_todo(session_id)))
        # K3 Z07: the stdout tail of terminal-like tools as its own frame — but a refused
        # call produced no tail. Echoing a refusal as `stdout` re-opened the call in the
        # client (the stdout upsert matched it and reset its status to pending), so the
        # refusal the frame above had just painted was swallowed a second time. A call
        # that did not run has no output to stream; the predicate is the same one above.
        _refused_call = bool(_code or _pending_refusal or _refused_result)
        if (
            name in ("run_shell", "task_output", "browser_evaluate")
            and _txt
            and not _refused_call
        ):
            emit({"type": "stdout", "tool": name, "data": _txt[:2000]})
        tool_result = normalize_tool_result(name, result)
        captured_tool_results.append(tool_result)
        _emit_file_result_event(
            name, result, emit, session_id, call_id=call_id, args_hash=_args_hash, turn_id=turn_id
        )
        for artifact in tool_result.artifacts:
            validation = validate_artifact(artifact)
            emit({
                "type": "artifact_check",
                "artifact_type": validation.artifact_type,
                "status": validation.status,
                "path": validation.path,
                "warnings": validation.warnings,
            })

    def on_phase(phase: str) -> None:
        emit({"type": "activity", "cmd": phase, "status": "running"})

    return on_chunk, on_thinking, on_tool_start, on_tool_done, on_phase


async def _run_swarm_command(message: str, model: str, emit: Callable[[dict], None]) -> bool:
    """/swarm: the Swarm V2 pipeline. True = the turn ends here (done sent)."""
    swarm_task = extract_swarm_task(message)
    if not swarm_task:
        emit({"type": "chunk", "data": "💡 Usage: `/swarm <task>` — e.g. `/swarm Analyze 3 AI trends and summarize them`"})
        emit({"type": "done"})
        return True

    emit({"type": "thinking_start"})
    emit({"type": "swarm_status", "phase": "planning", "message": "🐝 Swarm V2 started — the manager is analysing the task…"})

    try:
        from core.swarm_v2 import run_swarm_v2

        result = await run_swarm_v2(task=swarm_task, model=model, on_event=emit)
        # stream the final synthesis as chunks
        if result.final:
            words = result.final.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                emit({"type": "chunk", "data": chunk})
    except OllamaNotReachableError:
        emit({"type": "error", "msg": _unreachable_engine_message()})
    except OllamaModelNotFoundError as exc:
        emit({"type": "error", "msg": _error_msg(exc)})
    except Exception as exc:
        emit({"type": "error", "msg": f"Swarm error: {exc}"})

    emit({"type": "done"})
    return True


async def _run_goal_command(
    message: str,
    model: str,
    emit: Callable[[dict], None],
    confirm: Callable[[str, dict], Awaitable[bool]],
) -> bool:
    """/goal: the goal loop of `ephe goal` (core/goal_loop.py). True = the turn ends here.

    The frames are the loop's own state, relayed in its own events: `goal_start`
    carries the goal, the check command and the turn budget; `goal_turn` names the
    round that starts; `goal_check` carries that round's verdict and its bounded
    output. A surface showing "the goal the loop works toward" reads the first one
    instead of guessing it from the first line of a message.

    The loop's tool calls — the check command included — pass the same approval gate
    as every other call in this turn: the headless CLI posture would be a hole
    through the gate this route owns.
    """
    spec = parse_goal_command(message)
    if not spec.task:
        emit({
            "type": "chunk",
            "data": (
                "💡 Usage: `/goal <target> [--check \"<cmd>\"] [--max-turns N]` — "
                f"e.g. `/goal make the failing test pass` (check: {spec.check})"
            ),
        })
        emit({"type": "done"})
        return True

    emit({"type": "thinking_start"})

    def relay(kind: str, **payload) -> None:
        emit({"type": kind, **payload})

    try:
        from core.goal_loop import GoalRunner
        from core.tools.approval import ApprovalPolicy

        runner = GoalRunner(
            model=model,
            check_command=spec.check,
            max_turns=spec.max_turns,
            on_event=relay,
            policy=ApprovalPolicy(auto_approve=False, interactive=False, on_confirm=confirm),
        )
        result = await runner.run(spec.task)
    except OllamaNotReachableError:
        emit({"type": "error", "msg": _unreachable_engine_message()})
        emit({"type": "done"})
        return True
    except OllamaModelNotFoundError as exc:
        emit({"type": "error", "msg": _error_msg(exc)})
        emit({"type": "done"})
        return True
    except Exception as exc:
        emit({"type": "error", "msg": f"Goal error: {exc}"})
        emit({"type": "done"})
        return True

    status = "GOAL OK" if result.success else "GOAL FAILED"
    emit({
        "type": "chunk",
        "data": f"\n**{status}** after {result.turns} turn(s) — check command: `{spec.check}`\n",
    })
    if result.check_output:
        emit({"type": "chunk", "data": f"\n```\n{result.check_output.strip()[:2000]}\n```\n"})
    emit({"type": "done"})
    return True


async def _run_learn_command(message: str, model: str, emit: Callable[[dict], None]) -> bool:
    """/learn: the skill-builder pipeline. True = the turn ends here (done sent)."""
    topic = extract_learn_topic(message)
    if not topic:
        emit({"type": "chunk", "data": "💡 Usage: `/learn <topic>` — e.g. `/learn How we structure FastAPI routes`"})
        emit({"type": "done"})
        return True

    emit({"type": "thinking_start"})

    def on_learn_chunk(chunk: str) -> None:
        emit({"type": "chunk", "data": chunk})

    def on_learn_phase(phase: str) -> None:
        emit({"type": "activity", "cmd": phase, "status": "running"})

    def on_learn_tool_start(name: str, args: dict, call_id: str = "") -> None:
        emit({"type": "activity", "cmd": f"{name}({json.dumps(args, ensure_ascii=False)[:60]})", "status": "running"})

    def on_learn_tool_done(name: str, result: str, call_id: str = "") -> None:
        emit({"type": "activity", "cmd": f"{name} → {result[:40]}", "status": "done"})

    try:
        from core.skill_builder import build_skill

        skill = await build_skill(
            topic=topic,
            model=model,
            on_phase=on_learn_phase,
            on_chunk=on_learn_chunk,
            on_tool_start=on_learn_tool_start,
            on_tool_done=on_learn_tool_done,
        )
        # Confirmation message
        emit({"type": "chunk", "data": f"\n\n✅ **New skill created:** `{skill.name}` ({skill.trigger})\n"})
        emit({"type": "chunk", "data": f"\n_{skill.description}_"})
        # Skill-created event → the frontend reloads the chips
        emit({"type": "skill_created", "skill": {
            "name": skill.name,
            "trigger": skill.trigger,
            "description": skill.description,
        }})
    except (SkillLoadError, ValueError) as exc:
        emit({"type": "chunk", "data": f"\n\n⚠️ Skill creation failed: {exc}"})

    emit({"type": "done"})
    return True


async def _sandbox_confirm(
    name: str,
    args: dict,
    emit: Callable[[dict], None],
    emit_raw: Callable[[str], None],
    request: "StreamRequest",
) -> bool:
    """Sandbox approval handler: profile/auto/ask → bool (approved)."""
    from core.audit_log import audit_event
    from core.security_config import load_security_config

    # R2-B: the global profile is the ceiling over every mode-auto path. Before,
    # autonomous/edit_auto/full_access ran through BEFORE load_security_config()
    # was read — so the privacy-page control had no reader, and the page claimed
    # something the code did not hold: „Streng — immer fragen"  # language-gate: ignore (quoted product label, app/src/locales/de.json:674 profileStrict)
    profile = load_security_config().approval_profile
    mode_auto = profile != "strict"

    if mode_auto and sandbox_auto_approval_allowed(autonomous=request.autonomous):
        audit_event("approval", tool=name, args=args, decision="auto", status="autonomous")
        return True
    # P4: edit-auto — apply the edit family without asking; the rest
    # (run_shell, web_search, …) keeps running through the profile/ask.
    if mode_auto and _resolve_mode(request.mode)["edit_auto"] and name in _EDIT_TOOL_NAMES:
        audit_event("approval", tool=name, args=args, decision="auto", status="edit_auto")
        return True
    # B-7: 'full access' = run-through — every approval auto, without a dialog.
    if mode_auto and _resolve_mode(request.mode)["full_access"]:
        audit_event("approval", tool=name, args=args, decision="auto", status="full_access")
        return True

    # R23: session profile — „Für diese Sitzung merken" allows repetitions  # language-gate: ignore (quoted product label, app/src/locales/de.json:56 remember)
    # of the same tool without asking again. run_shell (NEVER_REMEMBER) excepted:
    # per command HEAD (B-7 head memo), not per tool TYPE.
    from core.security_config import (
        remember_shell_heads,
        remember_tool,
        session_auto_approved,
        shell_head_auto_approved,
    )

    session_key = request.session_id or ""
    rememberable = profile in ("session", "full")
    shell_heads: list[str] = []
    if name == "run_shell":
        shell_heads = _shell_segment_heads(str((args or {}).get("command", "") or ""))
        if shell_head_auto_approved(session_key, shell_heads, profile):
            audit_event("approval", tool=name, args=args, decision="session-approved", status="remembered")
            return True
    if session_auto_approved(session_key, name, profile):
        audit_event("approval", tool=name, args=args, decision="session-approved", status="remembered")
        return True

    token = str(uuid.uuid4())
    event = asyncio.Event()
    # T-02: _active_sandbox_events is app-wide (cross-request) so that
    # approve_sandbox() finds the token. get_sandbox() is for request-internal state.
    _active_sandbox_events[token] = {
        "event": event,
        "approved": False,
        # Fleet (G2): who is waiting, on what, and since when. The three fields are what
        # pending_approvals() hands to `/api/workspaces`, and without them a run that is
        # alive and idle on a person's answer is indistinguishable from one that is working.
        "session_id": request.session_id or "",
        "tool": name,
        "requested_at": time.time(),
    }
    confirm_payload: dict = {
        "type": "sandbox_confirm", "token": token, "tool": name, "args": args,
        "rememberable": rememberable,
    }
    # Wave B1: a real unified-diff preview for the edit family (additive,
    # optional — old clients ignore the field; read-only, fail-soft).
    from core.tools.file_ops import approval_preview_diff

    preview = approval_preview_diff(name, args)
    if preview:
        confirm_payload["diff"] = preview
    emit(confirm_payload)
    audit_event("approval", tool=name, args=args, decision="requested", status="awaiting-user")
    # I6 P2: a sign of life during the approval wait — the stream stays
    # byte-active, the idle timeout must not fire as "no answer".
    async def _keepalive() -> None:
        while True:
            await asyncio.sleep(SANDBOX_KEEPALIVE_SECONDS)
            emit_raw(": keepalive\n\n")

    _ka_task = asyncio.create_task(_keepalive())
    res: dict = {"approved": False}
    expired = False
    try:
        await asyncio.wait_for(event.wait(), timeout=APPROVAL_TTL_SECONDS)
        # Fetch the value BEFORE the finally removes the entry — the entry is
        # only registered during the waiting time.
        res = _active_sandbox_events.get(token, res)
    except asyncio.TimeoutError:
        # The run continues on the gate default after the approval window.
        expired = True
        res = {"approved": False}
        audit_event("approval", tool=name, args=args, decision="denied", status="expired")
    finally:
        _ka_task.cancel()
        # W15-P1: even on CancelledError (stop button) remove the entry without residue —
        # no lease in the app-wide registry dict.
        _active_sandbox_events.pop(token, None)
        if expired:
            _expired_sandbox_tokens[token] = time.time()
            cutoff = time.time() - APPROVAL_TTL_SECONDS
            for stale in [key for key, at in _expired_sandbox_tokens.items() if at < cutoff]:
                _expired_sandbox_tokens.pop(stale, None)
    decided = "approved" if res["approved"] else "denied"
    audit_event("approval", tool=name, args=args, decision=decided,
                status="remembered" if res.get("remember") else "user")
    if res["approved"] and res.get("remember") and rememberable:
        remember_tool(session_key, name)
        if name == "run_shell":
            remember_shell_heads(session_key, shell_heads)
    return res["approved"]


async def _ask_confirm(
    *,
    question: str,
    options: list[str],
    recommendation: str,
    default: str,
    multi_select: bool,
    timeout_seconds: float,
    emit: Callable[[dict], None],
    emit_raw: Callable[[str], None],
) -> str:
    """Ask dialog: emit the question, await the human, return the answer text.

    The shape of `_sandbox_confirm` above, because that is the one wait this server
    already owns: a token into an app-wide registry, one SSE frame out, and an SSE
    comment every SANDBOX_KEEPALIVE_SECONDS so the reader's idle detector reads a
    thinking human as a live stream. The answer arrives on its own connection
    through `POST /api/ask/answer` and wakes the very turn that asked.

    Returns "" when nobody answered in time — the empty string IS the timeout signal,
    and `core.tools.ask_gate.ask_user` turns it into the stated-default sentence the
    run continues on. A silent hang would leave both sides waiting for each other.
    """
    from core.audit_log import audit_event
    from core.tools.ask_gate import discard_ask, register_ask

    token, entry = register_ask(question)
    emit({
        "type": "ask_user",
        "token": token,
        "question": question,
        "options": options,
        "recommendation": recommendation,
        "default": default,
        "multiSelect": multi_select,
        "timeout_s": timeout_seconds,
    })
    try:
        audit_event("ask", tool="ask_user", decision="requested", status="awaiting-user")
    except Exception:
        pass

    async def _keepalive() -> None:
        while True:
            await asyncio.sleep(SANDBOX_KEEPALIVE_SECONDS)
            emit_raw(": keepalive\n\n")

    _ka_task = asyncio.create_task(_keepalive())
    answered = False
    try:
        await asyncio.wait_for(entry["event"].wait(), timeout=timeout_seconds)
        answered = True
    except asyncio.TimeoutError:
        # The turn goes on with the default it named with the question, and the frame
        # says so before it does — the client renders the timeout, so a reader who
        # comes back later can see which value their turn used.
        emit({
            "type": "ask_timeout",
            "token": token,
            "timeout_s": timeout_seconds,
            "default": default,
        })
    finally:
        _ka_task.cancel()
        # Even on CancelledError (stop button) the registry entry goes: a token nobody
        # waits for any more must not answer a later, unrelated turn.
        discard_ask(token)

    _answer = str(entry.get("answer") or "")
    try:
        audit_event(
            "ask",
            tool="ask_user",
            decision="answered" if answered else "timeout",
            status="user" if answered else "no-answer",
        )
    except Exception:
        pass
    return _answer


@router.post("/chat/stream")
async def chat_stream(
    request: StreamRequest, http_request: Request = None  # type: ignore[assignment]
) -> StreamingResponse:
    """
    Transparent streaming via SSE.

    Event types (every line: data: <JSON>\n\n):
      {"type": "chunk",    "data": "..."}          → token straight to the AI bubble
      {"type": "thinking_start"}                   → Progress UI without raw reasoning
      {"type": "activity", "cmd": "...", "status": "running|done"} → terminal feed
      {"type": "reflect",  "status": "running|done", "needs_revision": bool}
      {"type": "revision", "reason": "..."}         → reset the bubble, new answer
      {"type": "error",    "msg": "..."}            → error display
      {"type": "done"}                              → remove the cursor

    Flow:
      1. Stream the first answer IMMEDIATELY (no buffering → cursor visible)
      2. Reflection → activity event in the terminal
      3. If needs_revision: revision event + stream the revised answer
      4. done
    """
    _ensure_engine_ready()
    from core.plugin_commands import expand_plugin_command

    request.message = expand_plugin_command(request.message)
    # WH-50: the id the observability middleware already put on the response
    # header and the request log — the SSE error envelope reports the same one,
    # so a streamed failure correlates with the server's log line. Direct
    # in-process callers (tests) pass no Request, so the id stays empty there.
    request_id = getattr(getattr(http_request, "state", None), "rid", "") or ""
    # R33 (P1-1): REST callers may omit `history` — fall back to the turns the
    # server persisted for this session id (rest- mirror). PWA callers always
    # send their own history and are unaffected.
    hist = list(request.history) or _load_rest_history(request.session_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        # C1: the stream's own clock. `last_frame_type` names the frame the
        # generator was on when it closed — the yield in flight is more useful
        # for a drop than the last one that provably left the process.
        _stream_t0 = time.perf_counter()
        _last_keepalive = _stream_t0
        _last_frame_type = ""
        _saw_sentinel = False
        try:
            _provider_name = get_active_provider().provider
        except Exception:
            _provider_name = ""
        queue: asyncio.Queue[tuple[str, object] | None] = asyncio.Queue()
        # P5: one trajectory per turn — steps out of the SSE events (chunk detail
        # stays outside, only statuses/tools/usage become steps).
        # A3: one id for the whole assignment. It is born here, because here
        # is the beginning — trajectory, artifact index and audit read the same one.
        turn_id = new_turn_id()
        # TL-2: child process groups are registered per run so a cancel can kill them.
        from core.tools.cancel_scope import enter_run, kill_run

        enter_run(turn_id)
        # RL-1: open the run ledger and emit its first snapshot.
        from core.run import ledger as run_ledger

        run_ledger.start(turn_id, request_id)
        queue.put_nowait(
            ("event", {"type": "run_snapshot", **run_ledger.snapshot(turn_id)})
        )
        trajectory.begin_turn(request.session_id, request.model, turn_id)
        # P6 (ref-12): the user prompt is the first step of the turn — with
        # the full text as its `text` body, so the trajectory view can show the
        # USER section like the reference renderer model does.
        try:
            trajectory.record(request.session_id, {"type": "user", "text": request.message})
        except Exception:
            pass

        # W7-1: the failover note reaches the transcript as well as the audit line at
        # the end of the turn. The note is set inside chat_with_tools (the resolution
        # happens there), so it is announced lazily on the first event after it exists:
        # the reader sees which engine served the turn before the answer frames arrive.
        _failover_announced = False

        def _announce_failover() -> None:
            nonlocal _failover_announced
            if _failover_announced:
                return
            try:
                from core.tools.session_ctx import get_failover_note
                note = get_failover_note()
            except Exception:
                return
            if not note:
                return
            _failover_announced = True
            _frame = {"type": "failover", "note": note}
            queue.put_nowait(("event", _frame))
            try:
                trajectory.record(request.session_id, _frame)
            except Exception:
                pass

        turn_failure: list[str] = []

        def emit(event: dict) -> None:
            _announce_failover()
            # SEC-1: redact the event before it leaves the process.
            from core.redact import redact_deep

            event = redact_deep(event)  # type: ignore[assignment]
            etype = event.get("type")
            if etype == "error":
                turn_failure.append(str(event.get("reason_code") or "error"))
            # RL-1: write the ledger line before the frame leaves the process.
            try:
                from core.run import ledger as run_ledger

                line = run_ledger.record_event(event)
            except Exception:
                line = None
            if etype == "error":
                # WH-50: one id across all three legs — the same request id goes
                # into the SSE error envelope and the correlated log line.
                if request_id and "request_id" not in event:
                    event = {**event, "request_id": request_id}
                structured_log(
                    "error", "stream_error", request_id=request_id or None,
                    scope="chat", session_id=request.session_id,
                    message=event.get("msg"),
                )
            queue.put_nowait(("event", event))
            if line is not None and etype != "done":
                # A compact phase frame; done closes the stream, so no phase follows it.
                queue.put_nowait(
                    (
                        "event",
                        {
                            "type": "run_phase",
                            "run_id": line["run_id"],
                            "phase": line["phase"],
                            "seq": line["seq"],
                            "kind": line["kind"],
                        },
                    )
                )
            try:
                if etype not in ("chunk", "thinking_chunk", "model_info"):
                    trajectory.record(request.session_id, event)
            except Exception:
                pass

        def emit_raw(comment: str) -> None:
            # SSE comment line (': …') — invisible to the parser, but it resets
            # the idle detection of the frontend reader.
            queue.put_nowait(("raw", comment))

        # R36-S: sub-agent event bridge — spawn_agent routes its live events
        # (started/tool/done) into exactly this SSE stream. Request-scoped
        # ContextVar, which is why it is set HERE; core code stays transport-agnostic.
        from core.tools.subagent_tool import subagent_emit_var

        subagent_emit_var.set(emit)

        # N1 steering: the turn's inbox for direction changes. Registered under
        # its session because POST /chat/steer runs in its own request task and
        # sees nothing of this one's context; bound as a contextvar here, before
        # the run task is created, so the loop inside finds it (the observer and
        # the subagent bridge use the same seam).
        from core.steering import (
            SteeringChannel,
            bind_channel,
            register_turn,
            unregister_turn,
        )

        steer_channel = SteeringChannel(
            turn_id=turn_id,
            session_id=request.session_id,
            on_steer=emit,
        )
        bind_channel(steer_channel)
        register_turn(steer_channel)

        async def run() -> None:
            # W19 bench hardening: EVERYTHING in the run body lives in the try — an exception
            # before the previous try (skill/provider resolution) would have killed the task
            # silently: no error, no done, and the SSE generator would have
            # waited on the queue forever (a client hang without a diagnosis).
            _done_sent = False
            # W32: turn observability — start stamp + counters set early,
            # so the finally entry is complete even on an early exception.
            _turn_t0 = time.perf_counter()
            captured_tool_results: list = []
            active_provider: ModelProviderConfig | None = None
            model = request.model
            # W10: reset token of the tool-side mode — set inside the try, restored in the
            # finally below, so a mode never leaks past its own turn.
            _mode_token = None
            try:
                messages = list(hist)
                # Build images into the user message (12B multimodal)
                active_skill, user_content = _resolve_skill_invocation(request.message)
                user_msg: dict = {"role": "user", "content": user_content}
                if request.images:
                    user_msg["images"] = request.images
                messages.append(user_msg)

                # Determine the model via the hybrid router
                # force_tier set → the router returns the forced tier
                # model == DEFAULT_MODEL → the router decides automatically
                # model set explicitly → stays unchanged (override)
                active_provider = get_active_provider()

                async def _resolve_model() -> None:
                    """Resolve model/provider and send model_info to the frontend."""
                    nonlocal active_provider, model
                    if request.force_tier:
                        from core.model_router import get_router
                        active_config = await get_router().resolve(
                            force_tier=request.force_tier
                        )
                        model = active_config.name
                        active_provider = ModelProviderConfig(
                            provider="local_ollama",
                            model=model,
                            base_url=DEFAULT_OLLAMA_BASE_URL,
                            label="Local Ollama",
                            offline_capable=True,
                            requires_internet=False,
                        )
                        # Tier-Info an Frontend senden
                        emit({"type": "model_info",
                              "tier": active_config.tier.value,
                              "model": model,
                              "provider": "local_ollama"})
                    elif request.model == DEFAULT_MODEL:
                        model = active_provider.model
                        emit({"type": "model_info",
                              "tier": "provider",
                              "model": model,
                              "provider": active_provider.provider,
                              "offline_capable": active_provider.offline_capable,
                              "requires_internet": active_provider.requires_internet})
                    else:
                        model = request.model

                await _resolve_model()

                # /swarm: Swarm V2 Pipeline
                if is_swarm_command(request.message):
                    if await _run_swarm_command(request.message, model, emit):
                        _done_sent = True
                        return

                # /learn: Skill-Builder-Pipeline
                if is_learn_command(request.message):
                    if await _run_learn_command(request.message, model, emit):
                        _done_sent = True
                        return

                # Sandbox Handler
                # w10-12: the turn's refusal ledger — the answer this callback gets is
                # the only place the server LEARNS that the user said no, and the tool
                # that then does not run carries no reason code of its own.
                _refused_tools: dict[str, int] = {}

                async def _sandbox_cb(name: str, args: dict) -> bool:
                    _approved = await _sandbox_confirm(name, args, emit, emit_raw, request)
                    if not _approved:
                        _refused_tools[name] = _refused_tools.get(name, 0) + 1
                    return _approved

                # T-03: a ContextVar setter instead of monkey-patching
                from core.vision import (
                    set_sandbox_confirm_cb,
                    set_vision_learning_cb,
                    set_vision_learned_success_cb,
                )

                set_sandbox_confirm_cb(_sandbox_cb)

                async def _vision_learning_cb(target: str) -> None:
                    emit({"type": "vision_learning", "target": target})
                set_vision_learning_cb(_vision_learning_cb)

                async def _vision_learned_success_cb(target: str) -> None:
                    emit({"type": "vision_learned_success", "target": target})
                set_vision_learned_success_cb(_vision_learned_success_cb)

                async def _shell_confirm_cb(command: str) -> bool:
                    return await _sandbox_cb("run_shell", {"command": command})

                # G1 ask gate: the run pauses on a question here. The callback travels in
                # a ContextVar (core/tools/ask_gate.set_ask_cb) exactly as the sandbox
                # confirmation above does, so core stays transport-agnostic and a turn
                # without a stream (CLI, cron) simply gets no dialog.
                from core.tools.ask_gate import set_ask_cb

                async def _ask_cb(
                    *,
                    question: str,
                    options: list[str],
                    recommendation: str,
                    default: str,
                    multi_select: bool,
                    timeout_seconds: float,
                ) -> str:
                    return await _ask_confirm(
                        question=question,
                        options=options,
                        recommendation=recommendation,
                        default=default,
                        multi_select=multi_select,
                        timeout_seconds=timeout_seconds,
                        emit=emit,
                        emit_raw=emit_raw,
                    )

                set_ask_cb(_ask_cb)

                # W19: ask mode = fail-closed Q&A — no fast-path artifact, no
                # tools, an anti-hallucination guard in the system prompt (P0 from the
                # live audit: "hello.txt angelegt ✅" hallucinated without tool access).
                # P4: shared mode context → identical semantics as /chat (non-stream).
                extra_system, allowed_tools, mode_flags = _mode_context(
                    request.mode, skill=active_skill, message=request.message
                )
                ask_mode = mode_flags["ask"]
                plan_mode = mode_flags["plan"]
                # W10: publish the mode to the EXECUTION choke point. The offer list
                # above is what the model sees; a write that arrives through the
                # deferred bridge (tool_search + tool_call) never consults it.
                _mode_token = _publish_tool_mode(request.mode)

                # /goal: the autonomous goal loop. It runs tools (the check command),
                # so it refuses in ask and plan mode rather than acting behind a mode
                # that promises no tool run, and its calls go through _sandbox_cb —
                # the same gate every other call in this turn passes.
                if is_goal_command(request.message):
                    if ask_mode or plan_mode:
                        emit({
                            "type": "chunk",
                            "data": (
                                "⚠️ `/goal` runs tools, so it does not start in ask or "
                                "plan mode. Switch the composer to a mode that may act "
                                "and send it again."
                            ),
                        })
                        emit({"type": "done"})
                        _done_sent = True
                        return
                    if await _run_goal_command(request.message, model, emit, _sandbox_cb):
                        _done_sent = True
                        return

                # R36: the deterministic skill fast path is REMOVED — every
                # request runs through the agent path (model loop with real,
                # approval-gated tools). The matched skill only still acts as
                # system-prompt guidance; direct template answers no longer
                # exist (B13: prompt-echo titles, ignored target paths).

                # Phase 1: stream the first answer immediately
                first_chunks: list[str] = []
                captured_tool_results = []

                # The `turn` event carries the same id, so surface and index
                # speak about one number.
                emit({"type": "turn", "turn_id": turn_id, "session_id": request.session_id})
                on_chunk, on_thinking, on_tool_start, on_tool_done, on_phase = _make_stream_callbacks(
                    emit, first_chunks, captured_tool_results, request.session_id, turn_id,
                    refused_tools=_refused_tools,
                )

                def _emit_usage_frame() -> None:
                    # N7/N8a: usage frame into the SSE stream (SoA parity: a real
                    # token axis per turn). build_usage is the SSOT: counts measured by the
                    # provider (N8a: stream_options.include_usage=true on the
                    # OpenAI-compatible endpoint, Ollama final chunk) fit through
                    # and make the calibrated estimate unnecessary; without
                    # a measurement the documented heuristic stays, with a
                    # usage_estimated flag — never silent zeroes.
                    # Must lie BEFORE `done` (contract: done is the last data event).
                    try:
                        from core.usage import build_usage as _bu, serialize_prompt as _sp
                        from core.tools.session_ctx import get_measured_usage as _gmu

                        _measured = _gmu() or {}
                        _chunks_u = first_chunks if "first_chunks" in locals() else []
                        _usage_block = _bu(
                            _sp(messages),
                            "".join(_chunks_u),
                            prompt_tokens=_measured.get("prompt_tokens"),
                            completion_tokens=_measured.get("completion_tokens"),
                            # Wave 3: measured prompt-cache hit
                            # (0/None = the provider reports nothing → chip off).
                            cached_tokens=_measured.get("cached_tokens") or None,
                        )
                        emit({"type": "usage", "usage": _usage_block})
                        # Wave 3 (usage dashboard): content-free accounting —
                        # only numbers (d/h/in/out/cached/est), never content.
                        # Fail-open: a ledger error may never
                        # block the stream.
                        try:
                            from core.usage_ledger import record_usage as _rec

                            _rec(
                                in_tokens=_usage_block.get("prompt_tokens") or 0,
                                out_tokens=_usage_block.get("completion_tokens") or 0,
                                cached_tokens=_usage_block.get("prompt_tokens_details", {}).get(
                                    "cached_tokens"
                                )
                                or 0,
                                estimated=bool(_usage_block.get("usage_estimated")),
                            )
                        except Exception:
                            pass
                    except Exception:
                        pass

                # Send the thinking event IMMEDIATELY → the user sees what is happening
                emit({"type": "thinking_start"})

                engine_answer = await chat_with_tools(
                    model=model,
                    history=messages,
                    on_chunk=on_chunk,
                    on_thinking=on_thinking,
                    on_tool_start=on_tool_start,
                    on_tool_done=on_tool_done,
                    on_phase=on_phase,
                    provider_config=active_provider,
                    allowed_tool_names=allowed_tools,
                    extra_system_prompt=extra_system,
                    on_shell_confirm=_shell_confirm_cb,
                    on_tool_confirm=_sandbox_cb,
                    max_tool_iterations=_max_tool_iterations(request.tool_budget, active_skill),
                    session_id=request.session_id,
                    turn_id=turn_id,
                )

                first_answer = "".join(first_chunks)
                if not first_answer.strip():
                    _budget_answer = search_budget_answer(captured_tool_results)
                    if _budget_answer:
                        first_answer = _budget_answer
                        emit({"type": "chunk", "data": _budget_answer})
                if not first_answer.strip() and engine_answer and engine_answer.strip():
                    # W8, path 2: _emit_final_answer returns the text as
                    # a return value without streaming it (to avoid a double
                    # output). The value was thrown away — a turn with
                    # content arrived as an empty bubble.
                    first_answer = engine_answer
                    emit({"type": "chunk", "data": engine_answer})
                # P6: the final first answer as an ASSISTANT step with its full
                # text body (trajectory USER/reasoning/output parity).
                emit({"type": "assistant", "text": first_answer})
                silent_event = silent_turn_event(first_answer, captured_tool_results)
                if silent_event:
                    # W1-R3: a throttled free-tier answer arrived as an empty
                    # bubble — no text, no tool, no message. The
                    # surface was not allowed to act as if nothing had happened.
                    emit(silent_event)

                # Deterministic local quality check
                skill_quality_passed = False
                if active_skill:
                    emit({"type": "quality_check", "status": "running", "skill": active_skill.name})
                    if budget_note_is_unfinished(first_answer):
                        # R37: a cap end is unfinished by definition — fail, never pseudo-complete.
                        emit({
                            "type": "quality_check",
                            "status": "fail",
                            "skill": active_skill.name,
                            "issues": ["unfinished: tool budget exhausted — no final answer"],
                            "warnings": [],
                        })
                    else:
                        quality_report = evaluate_quality(
                            answer=first_answer,
                            skill=active_skill,
                            tool_results=captured_tool_results,
                            question=user_content,
                        )
                        emit({
                            "type": "quality_check",
                            "status": quality_report.status,
                            "skill": active_skill.name,
                            "issues": quality_report.issues,
                            "warnings": quality_report.warnings,
                        })
                        skill_quality_passed = quality_report.status == "passed"

                # Artifact detection
                _detector    = ArtifactDetector()
                _artifacts   = _detector.detect(first_answer)
                if _artifacts:
                    # Bubble text without code (a placeholder instead)
                    clean_text = _detector.extract_text(first_answer)
                    emit({"type": "replace_text", "text": clean_text})
                    for art in _artifacts:
                        emit({"type": "artifact", "artifact": art.to_dict()})

                if active_skill and skill_quality_passed:
                    _emit_usage_frame()
                    emit({"type": "done"})
                    _done_sent = True
                    return

                # Wave 7: the knowledge-gap loop (B1: autonomous up to budget)
                # Markers in the answer text ([[GAP: ...]]) → autonomous research via
                # web_search/fetch_url, sources appended under the answer.
                # No user dialog as long as at least one source delivers;
                # only with broken research (no hit/timeout) does the
                # marker stay visible as a hint. Budget: max 3 research runs.
                try:
                    from core.knowledge_gap import detect_gaps, resolve_gaps, format_research_block
                    _gap_items = detect_gaps(first_answer)
                    if _gap_items:
                        _gap_res = await resolve_gaps(_gap_items)
                        _block = format_research_block(_gap_res)
                        for _g in _gap_res:
                            emit({
                                "type": "gap",
                                "topic": _g.get("topic", ""),
                                "status": _g.get("status", ""),
                                "sources": _g.get("sources", []),
                            })
                        if _block:
                            first_answer = first_answer + "\n\n" + _block
                            emit({"type": "replace_text", "text": first_answer})
                except Exception:
                    pass

                # Phase 2: Reflexion
                emit({"type": "reflect", "status": "running"})
                reflexion = await reflect(
                    response=first_answer,
                    question=request.message,
                    model=model,
                    provider_config=active_provider,
                )
                emit({"type": "reflect", "status": "done", "needs_revision": reflexion.needs_revision})

                if not reflexion.needs_revision:
                    _emit_usage_frame()
                    emit({"type": "done"})
                    _done_sent = True
                    return

                # Phase 3: Revision
                emit({"type": "revision", "reason": reflexion.reason[:200]})

                messages.append({"role": "assistant", "content": first_answer})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your answer was incomplete.\n"
                        f"Critique: {reflexion.reason}\n\n"
                        f"Please give an improved, complete answer."
                    ),
                })

                rev_chunks: list[str] = []

                def on_chunk_rev(chunk: str) -> None:
                    rev_chunks.append(chunk)
                    emit({"type": "chunk", "data": chunk})

                await chat_with_tools(
                    model=model,
                    history=messages,
                    on_chunk=on_chunk_rev,
                    on_thinking=on_thinking,
                    on_tool_start=on_tool_start,
                    on_tool_done=on_tool_done,
                    on_phase=on_phase,
                    provider_config=active_provider,
                    allowed_tool_names=allowed_tools,
                    extra_system_prompt=extra_system,
                    on_shell_confirm=_shell_confirm_cb,
                    on_tool_confirm=_sandbox_cb,
                    max_tool_iterations=_max_tool_iterations(request.tool_budget, active_skill),
                    session_id=request.session_id,
                    turn_id=turn_id,
                )
                # P6: the revised answer as its own ASSISTANT step.
                if rev_chunks:
                    emit({"type": "assistant", "text": "".join(rev_chunks)})

            except ProviderSetupError as exc:
                emit({"type": "progress", "phase": "engine_error", "tool": "", "turn_id": turn_id, "elapsed_ms": 0})
                emit({"type": "error", "msg": _error_msg(exc)})
            except OllamaNotReachableError:
                emit({"type": "progress", "phase": "engine_error", "tool": "", "turn_id": turn_id, "elapsed_ms": 0})
                # The class is the transport-down bucket of every provider, so the
                # sentence asks which engine this turn was pointed at (a remote
                # engine named as Ollama sends the reader to the wrong machine).
                emit({"type": "error", "msg": _unreachable_engine_message(active_provider)})
            except OllamaModelBusyError as exc:
                emit({"type": "progress", "phase": "engine_error", "tool": "", "turn_id": turn_id, "elapsed_ms": 0})
                emit({"type": "error", "msg": f"⏳ Model busy — please retry (timeout after {exc.timeout:.0f}s)"})
            except OllamaModelNotFoundError as exc:
                emit({"type": "progress", "phase": "engine_error", "tool": "", "turn_id": turn_id, "elapsed_ms": 0})
                emit({"type": "error", "msg": f"model '{exc.model}' is not installed"})
            except Exception as exc:
                # W19 hardening: active_provider can be None (an error BEFORE the
                # resolution) — the fallback may never throw itself, otherwise
                # the task dies silently again.
                try:
                    emit(
                        {
                            "type": "error",
                            "msg": _friendly_model_error(exc, active_provider),
                            **provider_refusal_frame(exc),
                        }
                    )
                except Exception:
                    emit({"type": "error", "msg": _error_msg(exc)})
            finally:
                # N1: a steer the turn never read is reported before the turn
                # closes. The loop reports its own leftovers, so this covers the
                # paths that never return to it — a provider error out of the
                # middle of a round is exactly that.
                steer_channel.announce_unlanded(0)
                # W10: the tool-side mode never outlives its turn — this finally wraps the
                # whole body, so both chat_with_tools calls reset it.
                if _mode_token is not None:
                    try:
                        from core.tools.session_ctx import reset_current_mode

                        reset_current_mode(_mode_token)
                    except Exception:
                        pass
                # N7/N8a: usage frame (SSOT via _emit_usage_frame) — must lie
                # BEFORE `done` (contract: done is the last data event) and
                # before the sentinel (queue.put_nowait(None)), otherwise the
                # generator closes the stream without the frame.
                try:
                    if not _done_sent:
                        if "_emit_usage_frame" in locals():
                            _emit_usage_frame()
                except Exception:
                    pass
                if not _done_sent:
                    emit({"type": "done"})
                # Trajectory: close with `done` as the last step (the rest
                # mirror is written by the post-turn worker, and this step leaves it there).
                try:
                    trajectory.record(request.session_id, {"type": "done"})
                    trajectory.end_turn(request.session_id)
                except Exception:
                    pass
                # W32: observability per turn — duration + mode + tool count into the audit.
                # "was the work done?" can therefore be read per instance straight from the log.
                try:
                    from core.audit_log import audit_event as _ae_turn
                    from core.tools.session_ctx import get_failover_note
                    _fo = get_failover_note()
                    _ae_turn(
                        "turn",
                        tool=(active_skill.name if active_skill else ""),
                        status="ok",
                        duration_ms=round((time.perf_counter() - _turn_t0) * 1000, 1),
                        detail=(
                            f"mode={request.mode or 'default'} "
                            f"tools={len(captured_tool_results)}"
                            + (f" failover={_fo}" if _fo else "")
                        ),
                    )
                except Exception:
                    pass
                # W15-P6: close the stream directly after `done` — a post comment
                # (invisible to the parser, resets the idle detection) +
                # the sentinel. The heavy post-turn jobs run afterwards; the client
                # stream does not hang on the Chroma/registry round trips.
                _chunks = first_chunks if "first_chunks" in locals() else []
                # The history mirror is awaited BEFORE the sentinel: the next turn
                # reads its history from this store, and the fire-and-forget chain
                # could drop the write when the response closed (a streamed answer the
                # assistant then never saw again). One JSON write, on its own worker,
                # so this does not wait for Chroma.
                try:
                    await _mirror_rest_turn(request.message, "".join(_chunks), request.session_id)
                except Exception:
                    logger.debug("rest mirror skipped", exc_info=True)
                emit_raw(": post\n\n")
                queue.put_nowait(None)
                # R19/R25 + W16: the heavy post-turn jobs continue after the
                # sentinel as ONE worker job (dedicated thread) —
                # the generator closes at once, the client does not wait for
                # Chroma/registry round trips.
                try:
                    _dispatch_post_turn_jobs(
                        request.message, "".join(_chunks), request.session_id, hist,
                    )
                except Exception:
                    pass

        task = asyncio.create_task(run())

        cancelled = False
        try:
            while True:
                # Idle heartbeat: long thinking/tool-generation phases without
                # events (remote engines do not always stream reasoning, and
                # during tool-call generation no chunks flow at all) made the 60-s
                # idle detector of the frontend reader fire. SSE comment lines are
                # invisible to the parser but reset the idle clock — the same
                # mechanic as the post-turn comment further down. The error it
                # raises there reads "Streamabbruch vor dem done-Event".  # language-gate: ignore (message thrown by app/src/lib/stream.ts:164)
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=STREAM_HEARTBEAT_S)
                except asyncio.TimeoutError:
                    _last_frame_type = "keepalive"
                    _last_keepalive = time.perf_counter()
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    _saw_sentinel = True
                    break
                kind, payload = item
                if kind == "raw":
                    _last_frame_type = "keepalive" if str(payload).startswith(": keepalive") else "comment"
                    if _last_frame_type == "keepalive":
                        _last_keepalive = time.perf_counter()
                    yield str(payload)
                else:
                    _last_frame_type = str(payload.get("type") or "") if isinstance(payload, dict) else ""
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            # the client dropped the connection (send button, label "Stopp")  # language-gate: ignore (quoted product label, app/src/locales/de.json:17 stop)
            cancelled = True
            task.cancel()
            raise
        finally:
            # The turn is over; a steer arriving now would change nothing.
            kill_run(turn_id)
            try:
                run_ledger.finish(
                    "cancelled" if cancelled else ("error" if turn_failure else "complete"),
                    turn_failure[0] if turn_failure else "",
                )
            except Exception:
                pass
            # C1: one content-free line per stream close, before the await below —
            # a generator closed by GeneratorExit never resumes past it.
            try:
                _close_ms = round((time.perf_counter() - _stream_t0) * 1000)
                _heartbeat_ms = round((time.perf_counter() - _last_keepalive) * 1000)
                run_ledger.record_stream_close(
                    close_code=(
                        "client_cancel" if cancelled
                        else "stream_end" if _saw_sentinel
                        else "client_gone"
                    ),
                    last_frame_type=_last_frame_type,
                    elapsed_ms=_close_ms,
                    last_heartbeat_ms=_heartbeat_ms,
                    provider=_provider_name,
                    cancelled=cancelled or not _saw_sentinel,
                )
            except Exception:
                pass
            steer_channel.close()
            unregister_turn(steer_channel)
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@router.post("/chat/steer")
async def chat_steer(req: SteerRequest) -> dict:
    """Change the direction of a turn that is already running.

    The steer is queued here and the loop takes it up at its next round boundary,
    so ``queued`` in this answer means the running turn holds it — not that the
    model has read it yet. The transcript tells the two apart: a steer that lands
    writes a line naming its round and who changed it, and one the turn ends
    without taking up is written as unlanded.

    404 when no turn of this session is running. A direction change has no other
    target, and answering 200 here would put the text somewhere the user is not
    watching.
    """
    from core.steering import resolve_turn

    channel = resolve_turn(session_id=req.session_id, turn_id=req.turn_id)
    if channel is None:
        raise HTTPException(404, "no running turn for this session")
    if not req.text.strip() and not req.stop:
        raise HTTPException(400, "a direction change needs text, or stop=true")
    steer = channel.request(
        req.text,
        actor=req.actor,
        agent_id=req.agent_id,
        stop=req.stop,
    )
    if steer is None:
        raise HTTPException(429, "this turn has too many pending direction changes")
    return {
        "status": "queued",
        "turn_id": channel.turn_id,
        "seq": steer.seq,
        "stop": steer.stop,
        "queued": channel.queued,
    }


@router.post("/sandbox/approve")
async def approve_sandbox(req: ApproveRequest):
    """Takes sandbox confirmations (y/n) from the UI.

    This endpoint works with the app-wide _active_sandbox_events
    registry; the request-scoped get_sandbox() never sees these tokens.
    Tokens are registered by _sandbox_cb() and resolved here. R23: `remember` marks
    „Für diese Sitzung merken“ (only in effect when the event is  # language-gate: ignore (quoted product label, app/src/locales/de.json:56 remember)
    rememberable — the decision is made by _sandbox_cb when it wakes up).
    """
    if req.token in _active_sandbox_events:
        entry = _active_sandbox_events[req.token]
        asked = entry.get("requested_at") if isinstance(entry, dict) else None
        if isinstance(asked, (int, float)) and time.time() - asked > APPROVAL_TTL_SECONDS:
            _active_sandbox_events.pop(req.token, None)
            _expired_sandbox_tokens[req.token] = time.time()
            raise HTTPException(
                410, "the approval window expired; the run continued on its default"
            )
        entry["approved"] = req.approved
        entry["remember"] = bool(getattr(req, "remember", False))
        entry["event"].set()
        return {"status": "ok"}
    if req.token in _expired_sandbox_tokens:
        raise HTTPException(
            410, "the approval window expired; the run continued on its default"
        )
    raise HTTPException(404, "sandbox token not found or expired")


@router.post("/ask/answer")
async def answer_ask(req: AskAnswerRequest):
    """Takes the text answer to a pending `ask_user` (G1).

    One contract with /sandbox/approve above: the token is the handle, the answer
    wakes the turn that is awaiting exactly this one, and an unknown or already
    finished token answers 404. That second case is not an error in the turn — the
    wait may have ended in its timeout, or the stop button may have cancelled it, and
    the run has continued on its stated default by then.
    """
    from core.tools.ask_gate import resolve_ask

    answer = (req.answer or "").strip()
    if not answer:
        raise HTTPException(422, "an ask answer needs text; an unanswered run reaches its timeout")
    if resolve_ask(req.token, answer):
        return {"status": "ok"}
    raise HTTPException(404, "ask token not found or expired")
