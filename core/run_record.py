"""Ephe – core/run_record: the run-record contract (backlog item B1).

docs/CODING_AGENT_VS_PI_DESIGN.md §3.5: the two coding entry points printed prose and
accepted no machine-readable flag, so no claim about a run could be audited from a
file — only from somebody's terminal memory. This module is the shape of that file:
the versioned schema, the §2.4 failure taxonomy and the reader that refuses every
shape it does not know. ``core/run_evidence.py`` is the counterpart that measures
the facts and fills the shape in.

The policy mirrors the repo's ratchet baselines (``scripts/language_gate.py``,
``tests/home-isolation-baseline.json``): a version, an explicit key whitelist per
level, and no exemption list. A field an auditor cannot name is exactly what must
not be dropped quietly, so an unknown key is an error rather than a warning.

Two invariants carry the honesty of a run file:

  * a failure class only ever comes from a named signal (the loop's budget marker, a
    compaction event, the engine's own error, the verifier's reported exit) — never
    from a non-zero exit code alone;
  * every bounded field keeps the sha256 of the FULL value, so a truncated diff is
    provably truncated: ``validate_record`` re-derives the digest and fails when the
    flag and the hash disagree.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = 1
POLICY = "run-record"

#: Bounded fields. A kept value always ships with the digest of the full text.
DIFF_LIMIT = 20_000
TAIL_LIMIT = 2_000
TOOL_EVENT_LIMIT = 60

#: §2.4 taxonomy. The two classes of a failure outside the agent (an engine that did
#: not answer, a runner that threw) are ``engine_degraded`` and ``harness_error`` —
#: they are the verifier-external row and must never be filed as ``wrong_code``.
FAILURE_CLASSES = (
    "wrong_code", "refused", "refused_correctly", "stalled", "lost_context",
    "engine_degraded", "harness_error", "false_claim",
)
ENTRYPOINTS = ("code", "goal", "run")
SOLVED_BASES = ("verifier", "no_verifier")
ENDPOINT_KINDS = ("local_ollama", "custom_ollama", "openai_compatible", "none")
GATE_POSTURES = ("cli-policy", "chat-gate", "none")
APPROVAL_DECISIONS = ("approved", "denied", "auto-approved", "not-gated")
USAGE_SOURCES = ("measured", "estimated", "mixed", "none")

#: Narrow, visible marker list for §2.4 ``false_claim``: the final text asserts the
#: work is done while the verifier says it is not. A broader list would turn a
#: headline number into a vocabulary test, so it stays short and named. German
#: spellings are included because the product answers in German — the claim has to be
#: catchable in the language the agent actually writes.
SUCCESS_CLAIM_RE = re.compile(
    r"(all (the )?(tests|checks) (pass|passed|are green|green)"
    r"|tests? (pass|passed|are green)"
    r"|every test (passes|passed)"
    r"|alle (tests|checks) ((sind|laufen|gehen) )?(gruen|grün|green|durch))",
    re.IGNORECASE,
)

_TOP = ("schema", "run_id", "entrypoint", "started_at", "identity", "outcome",
        "effort", "artifact", "failure", "determinism")
_IDENTITY = ("task", "worktree", "git_commit", "engine", "runtime")
_ENGINE = ("provider", "model", "endpoint", "decoding")
_ENDPOINT = ("kind", "is_loopback", "url_hash")
_DECODING = ("as_sent", "as_applied", "as_applied_reported")
_RUNTIME = ("python", "node", "npm", "platform", "machine")
_OUTCOME = ("solved", "solved_basis", "verifier", "error")
_VERIFIER = ("command", "exit_code", "tail", "tail_truncated", "tail_sha256", "turns")
_EFFORT = ("tool_rounds", "tool_rounds_source", "budget_cap", "tool_events",
           "tool_events_truncated", "tokens", "wall_seconds")
_EVENT = ("seq", "ts", "kind", "tool", "args_hash", "duration_ms", "status",
          "decision", "approval_consulted", "approval_decision")
_TOKENS = ("in", "out", "total", "estimated", "source", "tokenizer")
_ARTIFACT = ("diff", "diff_sha256", "diff_truncated", "diff_bytes", "diff_source")
_FAILURE = ("class", "evidence")
_DETERMINISM = ("rep", "repetitions", "grouping_key", "grouping_inputs")


class RunRecordError(ValueError):
    """The record is not trustworthy — read that as an error, never as a partial run."""


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def bound(text: str | None, limit: int) -> dict:
    """Bounded copy of ``text`` plus the digest of the FULL value.

    The invariant a reader can check: ``truncated`` is exactly
    ``sha256(kept) != sha256(full)``. A shortened diff with a matching digest is not
    a shorter diff — it is a different file, and that is what the gate catches.
    """
    if text is None:
        return {"text": None, "sha256": None, "truncated": False, "bytes": 0}
    body = text if isinstance(text, str) else str(text)
    kept = body if len(body) <= limit else body[:limit]
    return {
        "text": kept,
        "sha256": sha256_hex(body),
        "truncated": sha256_hex(kept) != sha256_hex(body),
        "bytes": len(body.encode("utf-8", "surrogatepass")),
    }


def claims_success(text: str | None) -> bool:
    return bool(text) and bool(SUCCESS_CLAIM_RE.search(text or ""))


def stalled_by_budget(answer: str, rounds: int, cap: int) -> bool:
    """§2.4 ``stalled``: the loop's own exhaustion note, not a round-count guess.

    The note is written by the loop itself (core/chat.py), so matching it is reading
    evidence. The round comparison is the fallback for a run that stopped exactly at
    the ceiling without ever getting to the note.
    """
    from core.chat import _budget_exhausted_note

    if answer and _budget_exhausted_note(cap) in answer:
        return True
    return bool(cap) and rounds >= cap


def classify_failure(
    *,
    solved: bool | None,
    diff_present: bool | None,
    answer: str,
    rounds: int,
    cap: int,
    verifier_exit: int | None,
    engine_error: str = "",
    runner_error: str = "",
    compaction_fired: bool | None = None,
    needed_fact_predates: bool = False,
) -> tuple[str | None, dict]:
    """One §2.4 class from named evidence, or ``None`` when nothing is provable.

    The order IS the audit trail: a runner that threw is not the agent's failure, an
    engine that did not answer is not ``wrong_code``, and without a verifier no
    verdict may be claimed at all (§2.2 counts the verifier, not the answer text).
    ``lost_context`` needs the compaction event AND the predating fact — §2.4 says
    the verdict requires the event and never a guess, so a run in which compaction
    was not observed can never be filed as lost context.

    ``diff_present`` is three-valued on purpose: True (a diff was seen), False (an
    empty diff in a git tree, i.e. §2.4 ``refused``) and None (no git tree, so the
    artifact cannot be observed at all). That last case is recorded in the evidence
    instead of being quietly called a refusal.
    """
    evidence = {
        "solved": solved,
        "verifier_exit": verifier_exit,
        "diff_present": diff_present,
        "diff_observable": diff_present is not None,
        "tool_rounds": rounds,
        "budget_cap": cap,
        "stalled_by_budget": False,
        "success_claim": claims_success(answer),
        "engine_error": engine_error or None,
        "runner_error": runner_error or None,
        "compaction_fired": compaction_fired,
        "needed_fact_predates": bool(needed_fact_predates) if compaction_fired else False,
    }
    if solved is True:
        return None, evidence
    if runner_error:
        return "harness_error", evidence
    if engine_error:
        return "engine_degraded", evidence
    if solved is None:
        return None, evidence
    evidence["stalled_by_budget"] = stalled_by_budget(answer, rounds, cap)
    if evidence["stalled_by_budget"]:
        return "stalled", evidence
    if compaction_fired and needed_fact_predates:
        return "lost_context", evidence
    if evidence["success_claim"] and solved is False:
        return "false_claim", evidence
    if diff_present is False:
        return "refused", evidence
    return "wrong_code", evidence


def grouping_key(
    *, entrypoint: str, task: str, worktree: str | None, commit: str | None,
    provider: str, model: str, as_sent: dict,
) -> tuple[str, dict]:
    """A pass^k grouping key: identical for every repetition of one task, rep excluded.

    The inputs sit next to the key so a reader can tell which run coordinates were
    folded into it — a hash nobody can undo is not an audit trail.
    """
    inputs = {
        "entrypoint": entrypoint,
        "task": task,
        "worktree": worktree,
        "git_commit": commit,
        "provider": provider,
        "model": model,
        "temperature": as_sent.get("temperature"),
        "top_p": as_sent.get("top_p"),
        "max_tokens": as_sent.get("max_tokens"),
        "schema": SCHEMA,
    }
    canonical = json.dumps(inputs, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16], inputs


def _reject_unknown(raw: dict, allowed: tuple[str, ...], label: str) -> None:
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise RunRecordError(
            f"{label}: unknown key(s) {', '.join(unknown)} — schema {SCHEMA} has no exemption list"
        )
    missing = [key for key in allowed if key not in raw]
    if missing:
        raise RunRecordError(f"{label}: missing key(s) {', '.join(missing)}")


def _section(raw: object, label: str, allowed: tuple[str, ...]) -> dict:
    if not isinstance(raw, dict):
        raise RunRecordError(f"{label}: expected an object, got {type(raw).__name__}")
    _reject_unknown(raw, allowed, label)
    return raw


def _check_bounded(text: object, digest: object, truncated: object, label: str) -> None:
    if text is None:
        if digest is not None or truncated:
            raise RunRecordError(f"{label}: an absent value carries no digest and is never truncated")
        return
    if not isinstance(text, str) or not isinstance(digest, str):
        raise RunRecordError(f"{label}: a bounded value needs the text and the sha256 of the FULL value")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RunRecordError(f"{label}: {digest!r} is not a sha256")
    if bool(truncated) != (sha256_hex(text) != digest):
        raise RunRecordError(f"{label}: truncation flag {truncated!r} contradicts the recorded digest")


def validate_record(raw: dict) -> dict:
    """The schema gate: version, whitelist per level, enums, truncation invariant.

    Fails loudly and by name. A corrupt or foreign run file is not coerced into
    shape — an auditor reading it must never be handed a number the run never had.
    """
    if not isinstance(raw, dict):
        raise RunRecordError(f"record must be an object, got {type(raw).__name__}")
    if raw.get("schema") != SCHEMA:
        raise RunRecordError(f"record schema {raw.get('schema')!r}, this reader speaks {SCHEMA}")
    _reject_unknown(raw, _TOP, "record")
    if raw["entrypoint"] not in ENTRYPOINTS:
        raise RunRecordError(f"unknown entrypoint {raw['entrypoint']!r}")
    if not isinstance(raw["run_id"], str) or not raw["run_id"]:
        raise RunRecordError("run_id must be a non-empty string")

    identity = _section(raw["identity"], "identity", _IDENTITY)
    if not isinstance(identity["task"], str) or not identity["task"]:
        raise RunRecordError("identity.task: the task text is the record's subject")
    if identity["git_commit"] is not None and not re.fullmatch(r"[0-9a-f]{40}", str(identity["git_commit"])):
        raise RunRecordError("identity.git_commit: not a commit hash")
    engine = _section(identity["engine"], "identity.engine", _ENGINE)
    if engine["provider"] not in ENDPOINT_KINDS:
        raise RunRecordError(f"identity.engine.provider: unknown engine {engine['provider']!r}")
    endpoint = _section(engine["endpoint"], "identity.engine.endpoint", _ENDPOINT)
    if endpoint["kind"] not in ENDPOINT_KINDS:
        raise RunRecordError(f"identity.engine.endpoint.kind: unknown {endpoint['kind']!r}")
    if endpoint["url_hash"] is not None and not re.fullmatch(r"[0-9a-f]{16}", str(endpoint["url_hash"])):
        raise RunRecordError("identity.engine.endpoint.url_hash: not a 16-hex digest")
    _section(engine["decoding"], "identity.engine.decoding", _DECODING)
    _section(identity["runtime"], "identity.runtime", _RUNTIME)

    outcome = _section(raw["outcome"], "outcome", _OUTCOME)
    if outcome["solved"] is not None and not isinstance(outcome["solved"], bool):
        raise RunRecordError("outcome.solved: true, false or null — nothing else")
    if outcome["solved_basis"] not in SOLVED_BASES:
        raise RunRecordError(f"outcome.solved_basis: unknown {outcome['solved_basis']!r}")
    if outcome["solved"] is None and outcome["solved_basis"] != "no_verifier":
        raise RunRecordError("outcome.solved: null is only honest without a verifier")
    verifier = _section(outcome["verifier"], "outcome.verifier", _VERIFIER)
    _check_bounded(verifier["tail"], verifier["tail_sha256"], verifier["tail_truncated"], "outcome.verifier")

    effort = _section(raw["effort"], "effort", _EFFORT)
    for key in ("tool_rounds", "budget_cap"):
        if not isinstance(effort[key], int) or isinstance(effort[key], bool) or effort[key] < 0:
            raise RunRecordError(f"effort.{key}: expected a non-negative integer")
    if isinstance(effort["wall_seconds"], bool) or not isinstance(effort["wall_seconds"], (int, float)):
        raise RunRecordError("effort.wall_seconds: expected a number")
    tokens = _section(effort["tokens"], "effort.tokens", _TOKENS)
    if tokens["source"] not in USAGE_SOURCES:
        raise RunRecordError(f"effort.tokens.source: unknown {tokens['source']!r}")
    if not isinstance(tokens["estimated"], bool):
        raise RunRecordError("effort.tokens.estimated: the estimate flag is not optional")
    # The counter names are owned by core/usage.py and imported here so this schema does
    # not spell them again. Null is honest when both sides were measured: no counter ran.
    from core.usage import BPE_BACKEND, CALIBRATED_BACKEND

    if tokens["tokenizer"] not in (None, BPE_BACKEND, CALIBRATED_BACKEND):
        raise RunRecordError(
            f"effort.tokens.tokenizer: {tokens['tokenizer']!r} is not a counter name this build knows"
        )
    if not isinstance(effort["tool_events"], list):
        raise RunRecordError("effort.tool_events: expected a list")
    for event in effort["tool_events"]:
        _section(event, "effort.tool_events[]", _EVENT)
        if event["approval_decision"] not in APPROVAL_DECISIONS:
            raise RunRecordError(f"tool event approval_decision: unknown {event['approval_decision']!r}")

    artifact = _section(raw["artifact"], "artifact", _ARTIFACT)
    _check_bounded(artifact["diff"], artifact["diff_sha256"], artifact["diff_truncated"], "artifact")
    if not isinstance(artifact["diff_bytes"], int) or artifact["diff_bytes"] < 0:
        raise RunRecordError("artifact.diff_bytes: expected a non-negative byte count")

    failure = _section(raw["failure"], "failure", _FAILURE)
    if failure["class"] is not None and failure["class"] not in FAILURE_CLASSES:
        raise RunRecordError(f"failure.class {failure['class']!r} is not a §2.4 taxonomy value")
    if not isinstance(failure["evidence"], dict):
        raise RunRecordError("failure.evidence: every class names the signal it was taken from")

    determinism = _section(raw["determinism"], "determinism", _DETERMINISM)
    if not isinstance(determinism["rep"], int) or determinism["rep"] < 0:
        raise RunRecordError("determinism.rep: expected a non-negative repetition index")
    if not re.fullmatch(r"[0-9a-f]{16}", str(determinism["grouping_key"])):
        raise RunRecordError("determinism.grouping_key: not a 16-hex grouping key")
    return raw


def dump_record(record: dict) -> str:
    """The one JSON object a run produces — the shape ``validate_record`` accepts."""
    return json.dumps(validate_record(record), indent=2, ensure_ascii=False)


def write_record(record: dict, path: str | Path) -> Path:
    """Write the validated record; an untrustworthy record never reaches disk."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_record(record) + "\n", encoding="utf-8")
    return target


def load_record(path: str | Path) -> dict:
    """Read a run file and refuse every shape that could hide a lie."""
    return validate_record(json.loads(Path(path).expanduser().read_text(encoding="utf-8")))


__all__ = [
    "SCHEMA", "FAILURE_CLASSES", "GATE_POSTURES", "DIFF_LIMIT", "TAIL_LIMIT",
    "TOOL_EVENT_LIMIT", "RunRecordError", "bound", "claims_success", "classify_failure",
    "dump_record", "grouping_key", "load_record", "sha256_hex", "stalled_by_budget",
    "validate_record", "write_record",
]
