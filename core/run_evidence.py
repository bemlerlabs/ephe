"""Ephe – core/run_evidence: measure a coding run while it happens (backlog item B1).

The fact-gathering half of the run record; the shape it fills in is owned by
``core/run_record.py``. Nothing here re-implements an existing source: tool events and
approval decisions come from the audit log the registry writes, token counts from the
measured block of ``core/usage.py`` (estimate flag kept), generation values from
``core/engine_config.py`` (the read path the provider itself uses), the round counter
from the loop's own phase line, the verifier from the goal loop's gated tool path.

The rules the collectors exist to keep: no engine is ever hardcoded (the endpoint is
read and stored as kind plus digest, never as a URL); the approval gate is only ever
READ — each tool event says whether it was consulted and how it decided, and an
ungated posture shows up as ``not-gated`` instead of silently looking like the agent
(§3.4.5); and every bounded field keeps the digest of the full value.
"""
from __future__ import annotations

import hashlib
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

from core.run_record import (
    DIFF_LIMIT, ENTRYPOINTS, GATE_POSTURES, TAIL_LIMIT, TOOL_EVENT_LIMIT,
    RunRecordError, bound, classify_failure, grouping_key, validate_record,
)

#: The ``[exit N]`` marker convention (core/tools/_shell_exec.py, core/tools/test_tools.py),
#: read the same way by the goal loop's deterministic check.
EXIT_RE = re.compile(r"\[exit\s+(-?\d+)\]")

#: The loop's own round phase, also matched by app/src/lib/activityLabels.ts — an
#: existing contract, so counting rounds here does not invent a second protocol.
ROUND_RE = re.compile(r"^Tool round\s+(\d+)")

#: Exception classes meaning "the engine did not answer", not "Ephe failed" — the rule
#: bench_option_b.py already applies so a throttled engine is never an agent failure.
ENGINE_ERROR_NAMES = (
    "OllamaNotReachableError", "OllamaModelNotFoundError", "APIConnectionError",
    "APITimeoutError", "APIStatusError", "ConnectionError", "ConnectTimeout",
    "ReadTimeout", "TimeoutError", "OSError",
)

#: How far back the audit log is scanned for this run's lines.
AUDIT_SCAN_LIMIT = 500


def new_turn_id(entrypoint: str) -> str:
    """Run identity and audit filter in one: every tool line of this run carries it."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{entrypoint}-{stamp}-{uuid.uuid4().hex[:8]}"


def _run_cli(argv: list[str], timeout: float) -> str | None:
    """Stdout of a read-only helper binary; None when it is absent or silent."""
    binary = shutil.which(argv[0])
    if not binary:
        return None
    try:
        done = subprocess.run([binary, *argv[1:]], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return (done.stdout or "").strip() or None


def runtime_versions() -> dict:
    """Runner toolchain — §3.3 pins node and npm per session instead of assuming them."""
    return {
        "python": sys.version.split()[0],
        "node": _run_cli(["node", "--version"], 5.0),
        "npm": _run_cli(["npm", "--version"], 10.0),
        "platform": platform.system().lower() or None,
        "machine": platform.machine().lower() or None,
    }


def git_commit(worktree: str | None) -> str | None:
    """Commit of the tree the run worked in (§3.4.2) — read-only, None without a repo."""
    if not worktree:
        return None
    out = _run_cli(["git", "-C", str(worktree), "rev-parse", "HEAD"], 10.0)
    return out if out and re.fullmatch(r"[0-9a-f]{40}", out) else None


def worktree_diff(worktree: str | None) -> str | None:
    """Tracked changes against HEAD; None without a repo.

    Deliberately the worktree state and not a before/after delta: §5 forbids a run
    against a contaminated tree, and the honest way to show what the diff means is to
    name its base (``artifact.diff_source``).
    """
    if not worktree or not shutil.which("git"):
        return None
    try:
        done = subprocess.run(
            ["git", "-C", str(worktree), "diff", "--no-color", "--", "."],
            capture_output=True, text=True, timeout=20.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def endpoint_identity(api_url: str | None) -> dict:
    """The engine endpoint without the endpoint: kind, loopback or not, digest (§3.4.1)."""
    url = (api_url or "").strip()
    if not url:
        return {"kind": "none", "is_loopback": None, "url_hash": None}
    host = re.sub(r"^[a-z]+://", "", url).split("/")[0].split(":")[0].lower()
    return {
        "kind": "openai_compatible" if "://" in url else "custom_ollama",
        "is_loopback": host in ("127.0.0.1", "localhost", "::1", "[::1]"),
        "url_hash": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
    }


def decoding_as_sent() -> dict:
    """The generation values as they go out, from the reader the provider itself uses.

    §2.5: the bench manifest used to ASSERT a temperature its payload never carried.
    This records the effective value of the same read path (env → engine.json →
    default) that core/model_provider.py writes into the request, and states openly
    that the endpoint does not report the value it applied — that cell stays null
    instead of being filled with the number we hoped for.
    """
    from core.engine_config import read_generation_values

    values = read_generation_values()
    return {
        "as_sent": {
            "temperature": values.get("temperature"),
            "top_p": values.get("top_p"),
            "max_tokens": values.get("max_tokens"),
        },
        "as_applied": None,
        "as_applied_reported": False,
    }


def budget_cap() -> int:
    """The tool-round ceiling the loop applies to this run (§2.4 ``stalled``)."""
    from core.chat import clamp_tool_budget

    return clamp_tool_budget(None)


def token_accounting(measured: dict | None, prompt_text: str, completion_text: str) -> dict:
    """Measured-first, estimated-fallback counts, keeping the estimate flag (§2.6).

    ``tokenizer`` carries the counter that priced an estimated side — the name
    ``build_usage`` recorded — so the record names the counter beside the numbers it
    produced. Null when the provider measured both sides and no counter ran.
    """
    from core.usage import build_usage

    block = build_usage(
        prompt_text, completion_text,
        prompt_tokens=(measured or {}).get("prompt_tokens"),
        completion_tokens=(measured or {}).get("completion_tokens"),
        cached_tokens=(measured or {}).get("cached_tokens") or None,
    )
    have_in = (measured or {}).get("prompt_tokens") is not None
    have_out = (measured or {}).get("completion_tokens") is not None
    source = "measured" if (have_in and have_out) else ("mixed" if (have_in or have_out) else "estimated")
    if not measured and not prompt_text and not completion_text:
        source = "none"
    return {
        "in": int(block["prompt_tokens"]), "out": int(block["completion_tokens"]),
        "total": int(block["total_tokens"]), "estimated": bool(block["usage_estimated"]),
        "source": source, "tokenizer": block.get("tokenizer"),
    }


def gate_state(name: str, posture: str, denied: bool) -> tuple[bool, str]:
    """Was the approval gate consulted for this tool, and how did it decide?

    The audit proves the negative: the registry returns BEFORE executing when the gate
    denies, so a denial leaves an ``approval`` line and no ``tool_exec`` line, and a
    ``tool_exec`` line for a gated name means the gate let it through.
    """
    from core.tools.approval import chat_tool_requires_confirm, classify_tool

    if denied:
        return True, "denied"
    if posture == "chat-gate":
        return (False, "auto-approved") if not chat_tool_requires_confirm(name) else (True, "approved")
    if posture == "cli-policy":
        return (True, "auto-approved" if classify_tool(name).auto_approve_by_default else "approved")
    return False, "not-gated"


def tool_events(turn_id: str, posture: str, limit: int = TOOL_EVENT_LIMIT) -> tuple[list[dict], bool]:
    """This run's tool and approval lines, in order, out of the audit log.

    Filtered by the run's own turn id, so a line another writer produced (the owner's
    running server shares the same file) can never join the record.
    """
    from core.audit_log import tail

    if not turn_id:
        return [], False
    rows = [
        line for line in reversed(tail(limit=AUDIT_SCAN_LIMIT))
        if line.get("turn_id") == turn_id and line.get("kind") in ("tool_exec", "approval")
    ]
    denied = {
        (str(line.get("tool", "")), str(line.get("args_hash", "")))
        for line in rows
        if line.get("kind") == "approval" and line.get("decision") == "denied"
    }
    events: list[dict] = []
    for index, line in enumerate(rows, start=1):
        name = str(line.get("tool", ""))
        is_denial = line.get("kind") == "approval" and (name, str(line.get("args_hash", ""))) in denied
        consulted, decision = gate_state(name, posture, is_denial)
        events.append({
            "seq": index, "ts": str(line.get("ts", "")), "kind": str(line.get("kind", "")),
            "tool": name, "args_hash": str(line.get("args_hash", "")),
            "duration_ms": line.get("duration_ms"), "status": str(line.get("status", "")),
            "decision": str(line.get("decision", "")),
            "approval_consulted": consulted, "approval_decision": decision,
        })
    return (events[:limit], len(events) > limit)


async def run_verifier(command: str) -> str:
    """Run a declared verifier through the same gated tool path the goal loop uses.

    The posture mirrors core/goal_loop.py (auto-approve, non-interactive): passing the
    command on the command line is the consent, the gate still runs, and its decision
    is recorded — the record shows the gate rather than stepping around it.
    """
    from core.tools.approval import ApprovalPolicy
    from core.tools.registry import execute_tool

    return await execute_tool(
        "run_shell", {"command": command},
        ApprovalPolicy(auto_approve=True, interactive=False),
    )


def verifier_verdict(output: str | None, exit_code: int | None) -> bool | None:
    """Did the verifier pass? The goal loop's own deterministic rule, not a new one.

    ``core/goal_loop._check_passed`` is the verdict the goal loop already acts on (a
    ``[exit N]`` marker, an ``N failed`` line, a rejection prefix), so the record and
    the loop can never disagree about the same output. An explicit exit marker wins
    when the tool reported one; without any signal at all the verdict is None, which
    means "not measured" and never "failed".
    """
    if exit_code is not None:
        return exit_code == 0
    if output is None:
        return None
    from core.goal_loop import _check_passed

    return _check_passed(output)


def _split_exception(text: str) -> tuple[str, str]:
    """(engine_error, runner_error) — an unanswered engine is not a broken harness."""
    name = (text or "").split(":")[0].strip()
    return (name, "") if name in ENGINE_ERROR_NAMES else ("", text)


def active_worktree() -> str | None:
    """The Ephe workspace the tools resolve relative paths against (never hardcoded)."""
    from core.engine_config import get_workspace_dir

    try:
        return get_workspace_dir() or None
    except Exception:
        return None


class RunRecorder:
    """Collects one run while it happens and builds the record afterwards.

    The caller passes ``turn_id`` into the agent loop (that is what ties the audit
    lines to this run), forwards the loop's phase callback to ``on_phase``, and hands
    the answer plus whatever verifier evidence it holds to ``build``.
    """

    def __init__(
        self, *, entrypoint: str, task: str, provider: str, model: str, turn_id: str,
        api_url: str | None = None, gate_posture: str = "chat-gate", rep: int = 0,
        repetitions: int | None = None, worktree: str | None = None,
    ) -> None:
        if entrypoint not in ENTRYPOINTS:
            raise RunRecordError(f"unknown entrypoint {entrypoint!r}")
        if gate_posture not in GATE_POSTURES:
            raise RunRecordError(f"unknown gate posture {gate_posture!r}")
        self.entrypoint, self.task = entrypoint, task
        self.provider, self.model, self.api_url = provider, model, api_url
        self.turn_id, self.gate_posture = turn_id, gate_posture
        self.rep, self.repetitions = int(rep), repetitions
        self.worktree = worktree or active_worktree()
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._t0 = time.monotonic()
        self._rounds = 0
        self._round_seen = False

    def on_phase(self, text: str) -> None:
        """Take the round count from the loop's own phase line, never from a guess."""
        match = ROUND_RE.match(str(text or ""))
        if match:
            self._round_seen = True
            self._rounds = max(self._rounds, int(match.group(1)))

    def build(
        self, *, answer: str = "", measured_usage: dict | None = None,
        verifier_command: str | None = None, verifier_output: str | None = None,
        solved: bool | None = None, turns: int | None = None, exception: str | None = None,
        compaction_fired: bool | None = None, needed_fact_predates: bool = False,
    ) -> dict:
        """Assemble the record. Every argument is evidence the caller actually holds."""
        found = EXIT_RE.search(verifier_output or "")
        exit_code = int(found.group(1)) if found else None
        if verifier_command and solved is None:
            solved = verifier_verdict(verifier_output, exit_code)

        diff = bound(worktree_diff(self.worktree), DIFF_LIMIT)
        commit = git_commit(self.worktree)
        tail = bound(verifier_output, TAIL_LIMIT)
        events, events_truncated = tool_events(self.turn_id, self.gate_posture)
        cap = budget_cap()
        engine_error, runner_error = _split_exception(exception or "")
        decoding = decoding_as_sent()
        failure_class, evidence = classify_failure(
            solved=solved, diff_present=(None if diff["text"] is None else bool(diff["text"])),
            answer=answer, rounds=self._rounds,
            cap=cap, verifier_exit=exit_code, engine_error=engine_error,
            runner_error=runner_error, compaction_fired=compaction_fired,
            needed_fact_predates=needed_fact_predates,
        )
        key, inputs = grouping_key(
            entrypoint=self.entrypoint, task=self.task, worktree=self.worktree,
            commit=commit, provider=self.provider, model=self.model,
            as_sent=decoding["as_sent"],
        )
        return validate_record({
            "schema": 1,
            "run_id": self.turn_id,
            "entrypoint": self.entrypoint,
            "started_at": self.started_at,
            "identity": {
                "task": self.task, "worktree": self.worktree, "git_commit": commit,
                "engine": {
                    "provider": self.provider, "model": self.model,
                    "endpoint": endpoint_identity(self.api_url), "decoding": decoding,
                },
                "runtime": runtime_versions(),
            },
            "outcome": {
                "solved": solved,
                "solved_basis": "verifier" if verifier_command else "no_verifier",
                "verifier": {
                    "command": verifier_command, "exit_code": exit_code, "turns": turns,
                    "tail": tail["text"], "tail_truncated": tail["truncated"],
                    "tail_sha256": tail["sha256"],
                },
                "error": exception,
            },
            "effort": {
                "tool_rounds": self._rounds,
                "tool_rounds_source": "phase" if self._round_seen else "not-reported",
                "budget_cap": cap, "tool_events": events,
                "tool_events_truncated": events_truncated,
                "tokens": token_accounting(measured_usage, self.task, answer),
                "wall_seconds": round(time.monotonic() - self._t0, 3),
            },
            "artifact": {
                "diff": diff["text"], "diff_sha256": diff["sha256"],
                "diff_truncated": diff["truncated"], "diff_bytes": diff["bytes"],
                "diff_source": "worktree-vs-head",
            },
            "failure": {"class": failure_class, "evidence": evidence},
            "determinism": {
                "rep": self.rep, "repetitions": self.repetitions,
                "grouping_key": key, "grouping_inputs": inputs,
            },
        })


__all__ = [
    "EXIT_RE", "ROUND_RE", "ENGINE_ERROR_NAMES", "RunRecorder", "active_worktree",
    "budget_cap", "decoding_as_sent", "endpoint_identity", "gate_state", "git_commit",
    "new_turn_id", "run_verifier", "runtime_versions", "token_accounting",
    "tool_events", "verifier_verdict", "worktree_diff",
]
