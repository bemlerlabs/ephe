#!/usr/bin/env python3
"""The 162-case suite on the shipped surface, run once against the persisted engine.

`scripts/eval_skills.py` scores a responder dict, and `evals/eval_oracle.py` proves that
scorer with a deterministic echo. Neither reaches the product: both answer each case from
the declaration the case already carries, so the suite proves its schema and its scoring and
nothing about the engine. This module supplies the responder the suite was written for and
never had — a real turn through `POST /api/chat/stream`, the path a rep uses.

The mapping from the streamed turn onto the shape `evaluate_cases` expects is the logic here,
and it is the mapping the three families declare:

* tool-calling — the first fired tool is the answer, because the case names one request and
  one expected tool;
* refusal — the case's forbidden tool counts as fired wherever it sits in the sequence, in
  first position or later, so "the dangerous tool did not fire" stays the sharp signal;
* multi-step — the ordered fired names are the sequence, because a plan that lands the tools
  in the wrong order has not done the task.

The product reaches most tools through a progressive-disclosure shim (`tool_search`, then
`tool_call`; `core/tools/discovery.py`). Those three names are folded away before the sequence
is read: a case names the tool it wants and not the shim that fetched it, and a `tool_call`
that dispatches an inner tool contributes that tool even when the inner call emits no start
of its own.

Run metadata carries the number's context: the engine is read from `/api/health` and named,
the mode, the per-family case count and the wall time are recorded, and a note carries the
load the box was under while the run happened. An unreachable engine is a plumbing answer
rather than a score, and the runner says so with the numbers it does have.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval_skills import (
    FAMILIES,
    MULTI_STEP,
    REFUSAL,
    TOOL_CALLING,
    EvalCase,
    evaluate_cases,
    family_of,
    load_eval_cases,
)

#: The surface the suite runs against. EPHE_LIVE_PORT moves the port off the owner's :8765, so a
#: parallel run points at its own server (evals/call_cap_receipt.py imports this default).
DEFAULT_BASE = f"http://127.0.0.1:{os.environ.get('EPHE_LIVE_PORT') or '8765'}"
SUITE_ROOT = Path("evals/skills")
DEFAULT_TURN_TIMEOUT = 600.0

#: The accuracy key that carries each family, the same one evals/eval_oracle.py reports.
FAMILY_METRIC = {
    TOOL_CALLING: "tool_accuracy",
    REFUSAL: "refusal_accuracy",
    MULTI_STEP: "tool_sequence_accuracy",
}

#: The progressive-disclosure shim, mirrored from core/tools/discovery.py.META_TOOL_NAMES.
#: tests/test_live_eval.py asserts the two sets stay equal, so this copy cannot drift in silence.
META_TOOLS = frozenset({"tool_search", "tool_describe", "tool_call"})


class EngineUnavailable(RuntimeError):
    """The surface or its engine cannot answer, so there is no live run to score."""


def _engine_from_health(payload: dict) -> dict:
    """The active provider and model exactly as the health route reports them."""
    return {
        "provider": str(payload.get("active_provider") or ""),
        "model": str(payload.get("active_model") or ""),
    }


def active_engine(base: str = DEFAULT_BASE, seconds: float = 5.0) -> dict:
    with urllib.request.urlopen(f"{base}/api/health", timeout=seconds) as resp:
        return _engine_from_health(json.load(resp))


def effective_tools(names: list[str], dispatched: list[str]) -> list[str]:
    """The requested tools, still in firing order, with the discovery shim folded away.

    A case names the tool it wants, not the shim that fetched it, so tool_search,
    tool_describe and tool_call drop out. A tool_call still names its inner tool in its
    `name` argument, so a dispatch counts even when no start fires for the inner call — and
    it counts where it fired: the target takes its tool_call's position in the stream,
    because for the multi-step family that order is the metric. Appending every dispatch at
    the end rewrote a correct interleaved order and scored it wrong.

    A target that also fires a start of its own is counted once, at that start's position,
    so the shim can neither drop an inner tool nor double it.
    """
    ordered: list[str] = []
    seen = {name for name in names if name not in META_TOOLS}
    pending = list(dispatched)
    for name in names:
        if name not in META_TOOLS:
            ordered.append(name)
        elif name == "tool_call" and pending:
            target = pending.pop(0)
            if target not in META_TOOLS and target not in seen:
                seen.add(target)
                ordered.append(target)
    return ordered


def parse_events(lines: Iterable, on_confirm: Callable[[str], None] | None = None) -> tuple[list[str], list[str], str, dict, str | None]:
    """Fired tool names in order, tool_call dispatch targets, the answer text, counts, error.

    `on_confirm` receives the token of every pending `sandbox_confirm` while the read is
    paused on that line, so the caller can answer the prompt before the stream resumes.
    """
    tools: list[str] = []
    dispatched: list[str] = []
    answer: list[str] = []
    counts: dict[str, int] = {}
    error: str | None = None
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = str(event.get("type") or "")
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "tool_start":
            name = event.get("tool")
            if name:
                tools.append(str(name))
            args = event.get("args")
            if str(name) == "tool_call" and isinstance(args, dict) and args.get("name"):
                dispatched.append(str(args["name"]))
        elif kind == "chunk":
            answer.append(str(event.get("data") or ""))
        elif kind == "sandbox_confirm":
            token = event.get("token")
            if on_confirm and token:
                on_confirm(str(token))
        elif kind == "error":
            error = str(event.get("msg") or "stream error")
    return tools, dispatched, "".join(answer), counts, error


def _decide(base: str, token: str, approved: bool, timeout: float = 30.0) -> None:
    """Answer a pending sandbox prompt so the turn finishes with the tool left unrun."""
    body = json.dumps({"token": token, "approved": approved}).encode()
    request = urllib.request.Request(
        f"{base}/api/sandbox/approve",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
    except Exception:  # noqa: BLE001 — a missed decision leaves the turn to its own timeout
        pass


def stream_turn(
    base: str,
    case: EvalCase,
    model: str,
    *,
    mode: str = "agent",
    autonomous: bool = False,
    decline: bool = True,
    tool_budget: int | None = None,
    timeout: float = DEFAULT_TURN_TIMEOUT,
) -> dict:
    """One case through the stream route; the transcript yields which tools actually fired.

    A pending `sandbox_confirm` is denied before the read resumes, so a mutating tool is
    reached for and recorded and yet does not run. Selection is the thing being measured,
    and a suite whose refusal family says "run rm -rf on my Documents" must not delete a
    directory to learn whether the model declined it. The default policy is the manual
    approval path for the same reason; `--no-decline` with full access is for a box that
    can afford the side effects.

    `tool_budget` caps the agent loop's rounds per turn (None keeps the profile default),
    which bounds the wall time of a run whose engine loops on a denied tool.
    """
    payload = {
        "message": case.prompt,
        "history": [],
        "session_id": f"live-eval-{int(time.time() * 1000)}-{abs(hash(case.prompt)) % 100000}",
        "mode": mode,
        "model": model,
        "autonomous": autonomous,
    }
    if tool_budget is not None:
        payload["tool_budget"] = tool_budget
    request = urllib.request.Request(
        f"{base}/api/chat/stream",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    decision = (lambda token: _decide(base, token, approved=False)) if decline else None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            tools, dispatched, answer, counts, error = parse_events(resp, on_confirm=decision)
    except Exception as exc:  # noqa: BLE001 — a transport failure is a run row, never a tool hit
        return {
            "tools": [],
            "raw_tools": [],
            "dispatched": [],
            "answer": "",
            "counts": {},
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(time.perf_counter() - started, 2),
        }
    return {
        "tools": effective_tools(tools, dispatched),
        "raw_tools": tools,
        "dispatched": dispatched,
        "answer": answer,
        "counts": counts,
        "error": error,
        "elapsed_s": round(time.perf_counter() - started, 2),
    }


def duplicate_prompts(cases: Iterable[EvalCase]) -> list[str]:
    """The prompt texts claimed by more than one case, in the order they are first claimed.

    The prompt is what goes over the wire, so two cases that share one are two cases with
    one turn between them: the second is scored on the first's transcript, and one such pair
    can move a whole family's accuracy. A scored suite is meant to hold one prompt per case,
    so this is a defect in the suite and is named rather than papered over.
    """
    seen: dict[str, int] = {}
    for case in cases:
        seen[case.prompt] = seen.get(case.prompt, 0) + 1
    return [prompt for prompt, count in seen.items() if count > 1]


def live_responder(turn_fn: Callable[[EvalCase], dict]) -> Callable[[EvalCase], dict]:
    """Map each streamed turn onto the responder dict `evaluate_cases` scores.

    A case's turn is streamed once, so the cache holds that result and no case is charged
    twice. The cache is keyed by the case, never by its prompt text: two cases may share a
    prompt, and keying on it collapsed them onto one turn, so the second case was scored
    against the first's transcript. A repeated prompt from a different case is refused
    loudly instead, because a duplicated prompt in a scored suite is a defect in the suite
    and not something to cache over.

    For a refusal case the forbidden tool counts wherever it appears in the sequence, in
    first position or later; for every other single-tool case the first fired tool is it.
    """
    cache: dict[int, dict] = {}
    # `held` keeps every cached case alive: the key is the case object's identity, so a case
    # must outlive its entry or the identity could be recycled into a false hit.
    held: list[EvalCase] = []
    claimed: dict[str, EvalCase] = {}

    def responder(case: EvalCase) -> dict:
        key = id(case)
        if key not in cache:
            owner = claimed.get(case.prompt)
            if owner is not None:
                raise ValueError(
                    f"duplicate prompt in a scored suite: {case.prompt!r} is already scored "
                    f"under skill {owner.skill!r}, so this case would be scored on that "
                    f"case's turn; give each case its own prompt"
                )
            cache[key] = turn_fn(case)
            held.append(case)
            claimed[case.prompt] = case
        turn = cache[key]
        tools = list(turn.get("tools") or [])
        answer = str(turn.get("answer") or "")
        if case.expected_tools:
            return {"tools": tools, "answer": answer}
        if case.expect_refusal:
            fired = (
                case.forbidden_tool
                if (case.forbidden_tool and case.forbidden_tool in tools)
                else (tools[0] if tools else None)
            )
            return {"tool": fired, "answer": answer}
        return {"tool": tools[0] if tools else None, "answer": answer}

    return responder


def select_cases(cases: list[EvalCase], families: Iterable[str] | None, limit: int = 0) -> list[EvalCase]:
    """The cases of the requested families, with an optional per-family prefix cap."""
    wanted = [f for f in (list(families) if families else list(FAMILIES)) if f in FAMILIES]
    chosen: list[EvalCase] = []
    for family in wanted:
        group = [c for c in cases if family_of(c) == family]
        chosen.extend(group[:limit] if limit > 0 else group)
    return chosen


def wilson_interval(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for one family's rate, so a small family carries its width."""
    if total <= 0:
        return (0.0, 0.0)
    p = hits / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def run_live(
    base: str = DEFAULT_BASE,
    families: Iterable[str] | None = None,
    limit: int = 0,
    mode: str = "agent",
    autonomous: bool = False,
    decline: bool = True,
    tool_budget: int | None = None,
    note: str = "",
    timeout: float = DEFAULT_TURN_TIMEOUT,
    turn_fn: Callable[[EvalCase], dict] | None = None,
    engine: dict | None = None,
    verbose: bool = False,
) -> dict:
    """Drive the selected cases through the surface and score the streamed tool use."""
    cases = select_cases(load_eval_cases(REPO_ROOT / SUITE_ROOT), families, limit)
    if not cases:
        raise EngineUnavailable("no cases selected: check --family against the suite's families")
    # Refuse before a turn is streamed: a prompt two cases share means the second one would
    # be scored on the first's turn, so the run has no honest number to file.
    duplicated = duplicate_prompts(cases)
    if duplicated:
        raise ValueError(
            "duplicate prompt in the scored suite: "
            + "; ".join(repr(prompt) for prompt in duplicated)
            + " — each case needs its own prompt, or the second is scored on the first's turn"
        )
    resolved = dict(engine) if engine else active_engine(base)
    model = str(resolved.get("model") or "")

    if turn_fn is None:
        if not model:
            raise EngineUnavailable(f"{base} answers on /api/health but names no active model")

        def turn_fn(case: EvalCase) -> dict:  # type: ignore[misc]
            return stream_turn(base, case, model, mode=mode, autonomous=autonomous,
                               decline=decline, tool_budget=tool_budget, timeout=timeout)

    runs: list[dict] = []

    def record(case: EvalCase) -> dict:
        result = turn_fn(case)
        row = {
            "skill": case.skill,
            "family": family_of(case),
            "prompt": case.prompt,
            "expected": case.expected_tool or list(case.expected_tools),
            "forbidden_tool": case.forbidden_tool,
            "tools": list(result.get("tools") or []),
            "raw_tools": list(result.get("raw_tools") or result.get("tools") or []),
            "dispatched": list(result.get("dispatched") or []),
            "error": result.get("error"),
            "elapsed_s": result.get("elapsed_s"),
        }
        runs.append(row)
        if verbose:
            print(
                f"[{len(runs)}/{len(cases)}] {row['family']:<12} {row['prompt'][:44]!r} "
                f"-> {row['tools']} raw={row['raw_tools']} ({row['elapsed_s']}s)",
                flush=True,
            )
        return result

    started = time.perf_counter()
    scored = evaluate_cases(cases, live_responder(record))
    elapsed = round(time.perf_counter() - started, 1)

    by_family = scored["by_family"]
    per_family: dict[str, dict] = {}
    for family in FAMILIES:
        count = by_family.get(family, 0)
        if count <= 0:
            continue
        accuracy = scored[FAMILY_METRIC[family]]
        hits = round(accuracy * count)
        per_family[family] = {
            "cases": count,
            "hits": hits,
            "accuracy": round(accuracy, 4),
            "ci95": list(wilson_interval(hits, count)),
        }

    return {
        "base": base,
        "engine": resolved,
        "mode": mode,
        "autonomous": autonomous,
        "decline": decline,
        "tool_budget": tool_budget,
        "families": [f for f in (list(families) if families else list(FAMILIES)) if f in FAMILIES],
        "limit": limit,
        "note": note,
        "total": scored["total"],
        "by_family": by_family,
        "per_family": per_family,
        "term_accuracy": round(scored["term_accuracy"], 4),
        "elapsed_s": elapsed,
        "errors": sum(1 for r in runs if r["error"]),
        "runs": runs,
    }


def _echo_turn(case: EvalCase) -> dict:
    """A stand-in responder echoing what a case declares, for a model-free wiring check."""
    answer = " ".join(case.required_terms)
    if case.expected_tools:
        return {"tools": list(case.expected_tools), "answer": answer, "error": None, "elapsed_s": 0.0}
    if case.expect_refusal:
        return {"tools": [], "answer": answer, "error": None, "elapsed_s": 0.0}
    return {
        "tools": [case.expected_tool] if case.expected_tool else [],
        "answer": answer,
        "error": None,
        "elapsed_s": 0.0,
    }


def summary(result: dict) -> str:
    engine = result["engine"]
    lines = [
        f"surface   {result['base']}  mode={result['mode']}  autonomous={result['autonomous']}  "
        f"decline={result['decline']}  tool_budget={result.get('tool_budget')}",
        f"engine    {engine.get('provider')} / {engine.get('model')}",
        f"cases     {result['total']}  by_family {result['by_family']}  "
        f"errors {result['errors']}  wall {result['elapsed_s']}s",
    ]
    for family, entry in result["per_family"].items():
        lo, hi = entry["ci95"]
        lines.append(
            f"  {family:<12} n={entry['cases']:<4} hits={entry['hits']:<4} "
            f"accuracy={entry['accuracy']:.4f}  95% CI [{lo}, {hi}]"
        )
    lines.append(f"terms     {result['term_accuracy']:.4f}")
    if result.get("note"):
        lines.append(f"note      {result['note']}")
    return "\n".join(lines)


def _selftest() -> int:
    result = run_live(engine={"provider": "selftest", "model": ""}, turn_fn=_echo_turn)
    print(summary(result))
    ok = bool(result["per_family"]) and all(
        entry["accuracy"] == 1.0 for entry in result["per_family"].values()
    )
    print(f"live-eval selftest: {'ok' if ok else 'FAILED'} — every selected family at 1.0 under the echo")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drive the eval suite through /api/chat/stream")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--family", action="append", default=None,
                        help=f"repeatable; one of {', '.join(FAMILIES)} (default: all three)")
    parser.add_argument("--limit", type=int, default=0,
                        help="per-family case cap; 0 runs each selected family whole")
    parser.add_argument("--tool-budget", type=int, default=None,
                        help="cap the agent loop's rounds per turn (default: profile value)")
    parser.add_argument("--mode", default="agent",
                        help="UI mode; the manual approval path is the default for a safe run")
    parser.add_argument("--auto", action="store_true",
                        help="autonomous approval — only on a box that can afford the side effects")
    parser.add_argument("--no-decline", action="store_true",
                        help="approve sandbox prompts instead of denying them (side effects run)")
    parser.add_argument("--note", default="", help="the load and conditions this run happened under")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TURN_TIMEOUT)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true", help="print one line per case as it runs")
    parser.add_argument("--selftest", action="store_true",
                        help="no model: score the suite against an echoing stand-in")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    try:
        result = run_live(base=args.base, families=args.family, limit=args.limit,
                          mode=args.mode, note=args.note, timeout=args.timeout,
                          autonomous=args.auto, decline=not args.no_decline,
                          tool_budget=args.tool_budget, verbose=args.verbose)
    except EngineUnavailable as exc:
        print(f"live-eval: no run — {exc}")
        return 2

    print(summary(result))
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"live-eval: wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
