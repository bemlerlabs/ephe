#!/usr/bin/env python3
"""Per-case calls-against-cap receipt for the live eval: was a miss the cap, or not?

`evals/live_eval.py` scores a turn on which tool fired and what the answer said. It does
not say how close a failing turn came to the loop's tool budget, so a miss the ceiling cut
off and a miss the turn chose for itself both read as one word. This module files the
missing column: for every case it names the rounds and calls the turn spent against the
cap and returns one verdict.

Verdicts:

* ``hit``             — the case scored correct.
* ``miss_at_cap``     — the loop ended on its own exhaustion note (or exactly at the ceiling).
* ``miss_not_at_cap`` — the turn finished on a final answer inside the budget, so the cap
                        is out of the picture; the miss is a choice, a wording miss, or a
                        term miss, and never the ceiling.
* ``miss_cap_unknown``— the record holds neither the round count nor the answer, so the two
                        misses cannot be told apart. The number is reported unknown, never
                        guessed: this is the state a run record leaves when it drops the
                        transcript the live runner already read.
* ``outcome_unknown`` — the record cannot even score the case (a refusal needs the answer
                        text for its required terms, which a trimmed row does not keep).
* ``error``           — the stream or the box failed; plumbing, not a product miss.

The cap is read from the product's own contract (`core.chat.clamp_tool_budget`) and the
cap-end signal from `core.run_record.stalled_by_budget`, so this instrument cannot drift
from what the loop enforces. The round count is the loop's own phase line, matched with
`core.run_evidence.ROUND_RE`. No literal from those modules is copied here.

The unit the cap binds is the **round** (one model response that may carry several tool
calls). The receipt reports three numbers per case so the reading stays honest:
``cap_rounds`` (the limit), ``rounds_used`` (the highest round the loop announced) and
``calls_fired`` (how many tool calls ran). A turn can hit the round cap with few calls, and
can fire many calls well short of it; the cap compares to ``rounds_used`` alone.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.run_evidence import ROUND_RE  # noqa: E402  (path bootstrap above)
from evals.live_eval import (  # noqa: E402
    DEFAULT_BASE,
    DEFAULT_TURN_TIMEOUT,
    FAMILY_METRIC,
    SUITE_ROOT,
    EngineUnavailable,
    _decide,
    active_engine,
    effective_tools,
    live_responder,
    parse_events,
    select_cases,
)
from scripts.eval_skills import (  # noqa: E402
    MULTI_STEP,
    REFUSAL,
    EvalCase,
    evaluate_cases,
    family_of,
    load_eval_cases,
)

#: The verdict a case lands in. Order is the reading order, not a severity.
HIT = "hit"
MISS_AT_CAP = "miss_at_cap"
MISS_NOT_AT_CAP = "miss_not_at_cap"
MISS_CAP_UNKNOWN = "miss_cap_unknown"
OUTCOME_UNKNOWN = "outcome_unknown"
ERROR = "error"
VERDICTS = (HIT, MISS_AT_CAP, MISS_NOT_AT_CAP, MISS_CAP_UNKNOWN, OUTCOME_UNKNOWN, ERROR)

#: How far below the core count the box must sit for a collection to be trusted as idle.
#: A measurement on a loaded box measures the box, not the product (contract rule 3).
IDLE_LOAD_FRACTION = 0.5


def cap_for(tool_budget: int | None) -> int:
    """The loop's round cap, from the product's own clamp.

    A ``None`` budget falls to the product default and a value above the platform ceiling
    is clamped to it, exactly as the surface clamps a request. Reading the contract here
    keeps a copied constant from aging away from what the loop enforces.
    """
    from core.chat import clamp_tool_budget

    return clamp_tool_budget(tool_budget)


def rounds_in_phase(text: str) -> int:
    """The round number the loop announces in its phase line, or 0 for any other line.

    The loop calls ``on_phase(f"Tool round {iteration}...")`` once per round and the stream
    forwards it as an ``activity`` event, so the transcript already carries the count the
    score drops. `core.run_evidence.ROUND_RE` is the loop's own pattern for that line.
    """
    match = ROUND_RE.match(text or "")
    return int(match.group(1)) if match else 0


def parse_transcript(events: Iterable) -> tuple[list[str], list[str], str, dict, int, str | None]:
    """Fired tool names, dispatch targets, answer text, event counts, highest round, error.

    Mirrors `evals.live_eval.parse_events` and adds the round count. The two are kept in
    lockstep by tests/test_call_cap_receipt.py, which asserts they agree on tools, answer,
    counts and error for the same transcript, so this reader cannot drift in silence.
    """
    tools: list[str] = []
    dispatched: list[str] = []
    answer: list[str] = []
    counts: dict[str, int] = {}
    rounds = 0
    error: str | None = None
    for event in events:
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
        elif kind == "activity":
            rounds = max(rounds, rounds_in_phase(str(event.get("cmd") or "")))
        elif kind == "error":
            error = str(event.get("msg") or "stream error")
    return tools, dispatched, "".join(answer), counts, rounds, error


def ended_at_cap(answer: str, rounds: int, cap: int) -> bool:
    """Whether the loop's own evidence says the turn ran out of budget (§2.4 ``stalled``)."""
    from core.run_record import stalled_by_budget

    return stalled_by_budget(answer, rounds, cap)


def classify(*, outcome: bool | None, answer: str, rounds: int, cap: int, error: str | None) -> str:
    """One verdict from the case's score and its cap evidence.

    ``outcome`` is three-valued on purpose: True (scored correct), False (scored wrong) and
    None (the record cannot decide the score). A case the record cannot score is
    ``outcome_unknown``; a scored miss is only called ``miss_at_cap`` when the answer or the
    round count proves the ceiling, and ``miss_cap_unknown`` when neither is present.
    """
    if error:
        return ERROR
    if outcome is True:
        return HIT
    if outcome is None:
        return OUTCOME_UNKNOWN
    if not answer and rounds <= 0:
        return MISS_CAP_UNKNOWN
    return MISS_AT_CAP if ended_at_cap(answer, rounds, cap) else MISS_NOT_AT_CAP


def turn_from_events(events: Iterable) -> dict:
    """One turn as a dict: folded tools, raw names, answer, counts, rounds, error."""
    tools, dispatched, answer, counts, rounds, error = parse_transcript(events)
    return {
        "tools": effective_tools(tools, dispatched),
        "raw_tools": tools,
        "dispatched": dispatched,
        "answer": answer,
        "counts": counts,
        "rounds": rounds,
        "error": error,
    }


def _score(case: EvalCase, turn: dict) -> bool:
    """The case's hit under the suite's own scorer, so the receipt cannot re-define a hit.

    `live_eval.live_responder` maps the turn onto the shape `evaluate_cases` scores — the
    first fired tool for a single-tool case, the forbidden tool's presence for a refusal,
    the ordered names for a multi-step case — so the receipt and the live score agree.
    """
    responder = live_responder(lambda _case: turn)
    scored = evaluate_cases([case], responder)
    return scored[FAMILY_METRIC[family_of(case)]] == 1.0


def _receipt_row(case: EvalCase, turn: dict, cap: int) -> dict:
    """One case's line: what it spent against the cap and what the cap decided."""
    answer = str(turn.get("answer") or "")
    rounds = int(turn.get("rounds") or 0)
    error = turn.get("error")
    outcome = None if error else _score(case, turn)
    verdict = classify(outcome=outcome, answer=answer, rounds=rounds, cap=cap, error=error)
    return {
        "skill": case.skill,
        "family": family_of(case),
        "prompt": case.prompt,
        "cap_rounds": cap,
        "rounds_used": rounds,
        "calls_fired": int(turn.get("counts", {}).get("tool_start", 0)),
        "outcome": outcome,
        "verdict": verdict,
        "elapsed_s": turn.get("elapsed_s"),
        "error": error,
    }


def tally(rows: Iterable[dict]) -> dict:
    """Verdict counts over the rows, every verdict key present even at zero."""
    counts = {verdict: 0 for verdict in VERDICTS}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return counts


def collect_turn(
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
    """One case through the surface, keeping the whole transcript the score throws away.

    The read is incremental so a pending ``sandbox_confirm`` is answered before the stream
    resumes, and the round phase line is kept for the receipt. `evals.live_eval._decide`
    answers the prompt, so a mutating tool is recorded and never runs.
    """
    payload = {
        "message": case.prompt,
        "history": [],
        "session_id": f"cap-receipt-{int(time.time() * 1000)}-{abs(hash(case.prompt)) % 100000}",
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
    events: list[dict] = []
    decision = (lambda token: _decide(base, token, approved=False)) if decline else None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                events.append(event)
                if event.get("type") == "sandbox_confirm" and decision:
                    token = event.get("token")
                    if token:
                        decision(str(token))
    except Exception as exc:  # noqa: BLE001 — a transport failure is a row, never a hit
        turn = turn_from_events(events)
        turn["error"] = f"{type(exc).__name__}: {exc}"
        turn["elapsed_s"] = round(time.perf_counter() - started, 2)
        return turn
    turn = turn_from_events(events)
    turn["elapsed_s"] = round(time.perf_counter() - started, 2)
    return turn


def conditions(base: str = DEFAULT_BASE) -> dict:
    """The box and the surface as they are right now, so a number can carry its context."""
    try:
        load = [round(value, 2) for value in os.getloadavg()]
    except OSError:
        load = []
    cpu = os.cpu_count() or 1
    engine = None
    listening = False
    try:
        with urllib.request.urlopen(f"{base}/api/health", timeout=3) as resp:
            payload = json.load(resp)
        engine = {"provider": str(payload.get("active_provider") or ""),
                  "model": str(payload.get("active_model") or "")}
        listening = True
    except Exception:  # noqa: BLE001 — an absent surface is a condition, not an error
        pass
    idle = bool(load) and load[0] < cpu * IDLE_LOAD_FRACTION
    return {
        "surface": base,
        "surface_listening": listening,
        "engine": engine,
        "loadavg": load,
        "ncpu": cpu,
        "idle": idle,
        "idle_rule": f"1-minute load must sit below {IDLE_LOAD_FRACTION} of the {cpu} cores",
    }


def collect(
    base: str = DEFAULT_BASE,
    families: Iterable[str] | None = None,
    limit: int = 0,
    mode: str = "agent",
    autonomous: bool = False,
    decline: bool = True,
    tool_budget: int | None = None,
    note: str = "",
    timeout: float = DEFAULT_TURN_TIMEOUT,
    engine: dict | None = None,
) -> dict:
    """Drive the selected cases and file one receipt row per case, cap named on every row."""
    cases = select_cases(load_eval_cases(REPO_ROOT / SUITE_ROOT), families, limit)
    if not cases:
        raise EngineUnavailable("no cases selected: check --family against the suite's families")
    resolved = dict(engine) if engine else active_engine(base)
    model = str(resolved.get("model") or "")
    if not model:
        raise EngineUnavailable(f"{base} answers on /api/health but names no active model")
    cap = cap_for(tool_budget)

    rows: list[dict] = []
    for case in cases:
        turn = collect_turn(base, case, model, mode=mode, autonomous=autonomous,
                            decline=decline, tool_budget=tool_budget, timeout=timeout)
        rows.append(_receipt_row(case, turn, cap))

    return {
        "instrument": "evals/call_cap_receipt.py",
        "measured": True,
        "surface": base,
        "engine": resolved,
        "mode": mode,
        "autonomous": autonomous,
        "decline": decline,
        "tool_budget": tool_budget,
        "cap_rounds": cap,
        "families": sorted({row["family"] for row in rows}),
        "cases": len(rows),
        "note": note,
        "verdicts": tally(rows),
        "rows": rows,
    }


def receipt_from_record(record: dict) -> dict:
    """Audit a saved live-eval record, naming what it can and cannot say about the cap.

    The live runner keeps the fired tools and the case declaration but drops the answer and
    the round phase line, so a miss in an existing record is ``miss_cap_unknown`` by
    construction: the receipt reports that honestly instead of guessing the ceiling.
    """
    cap = cap_for(record.get("tool_budget"))
    rows: list[dict] = []
    for row in record.get("runs") or []:
        family = row.get("family")
        outcome = _score_row(family, row)
        rounds = int(row.get("rounds") or 0)
        answer = str(row.get("answer") or "")
        verdict = classify(outcome=outcome, answer=answer, rounds=rounds, cap=cap,
                           error=row.get("error"))
        rows.append({
            "skill": row.get("skill"),
            "family": family,
            "prompt": row.get("prompt"),
            "cap_rounds": cap,
            "rounds_used": rounds if "rounds" in row else None,
            "calls_fired": len(row.get("raw_tools") or row.get("tools") or []),
            "outcome": outcome,
            "verdict": verdict,
            "elapsed_s": row.get("elapsed_s"),
            "error": row.get("error"),
        })
    return {
        "instrument": "evals/call_cap_receipt.py",
        "measured": True,
        "source": "record",
        "engine": record.get("engine"),
        "tool_budget": record.get("tool_budget"),
        "cap_rounds": cap,
        "cases": len(rows),
        "cap_end_observable": False,
        "reason": ("the record keeps tools but drops the answer and the round phase line, so "
                   "a scored miss here cannot be separated from a cap end"),
        "verdicts": tally(rows),
        "rows": rows,
    }


def _score_row(family: str | None, row: dict) -> bool | None:
    """The case outcome a trimmed run row can still decide, or None when it cannot.

    A tool-calling case is the first folded tool against the expected name; a multi-step
    case is the folded sequence against the declared order. A refusal needs the answer's
    required terms, and a trimmed row keeps no answer, so it is None rather than a guess.
    """
    tools = list(row.get("tools") or [])
    if family == MULTI_STEP:
        return tools == list(row.get("expected") or [])
    if family == REFUSAL:
        return None
    expected = row.get("expected")
    if isinstance(expected, list):
        expected = expected[0] if expected else ""
    fired = tools[0] if tools else None
    return bool(expected) and fired == expected


def not_measured_receipt(*, why: str, cond: dict, command: str) -> dict:
    """The receipt a task files when there is no number to file (contract rule 3)."""
    return {
        "instrument": "evals/call_cap_receipt.py",
        "measured": False,
        "why_not": why,
        "conditions": cond,
        "next_command": command,
    }


def summary(receipt: dict) -> str:
    """A short human read of a receipt, measured or not."""
    if not receipt.get("measured"):
        cond = receipt.get("conditions") or {}
        return "\n".join([
            "call-cap receipt: NOT MEASURED",
            f"  why      {receipt.get('why_not')}",
            f"  surface  {cond.get('surface')}  listening={cond.get('surface_listening')}  "
            f"engine={cond.get('engine')}",
            f"  load     {cond.get('loadavg')} on {cond.get('ncpu')} cores  idle={cond.get('idle')}",
            f"  next     {receipt.get('next_command')}",
        ])
    lines = [
        f"call-cap receipt: {receipt.get('source', 'live')}  cases={receipt['cases']}  "
        f"cap_rounds={receipt['cap_rounds']}  engine={receipt.get('engine')}",
    ]
    for verdict, count in receipt["verdicts"].items():
        lines.append(f"  {verdict:<18} {count}")
    if receipt.get("reason"):
        lines.append(f"  reason   {receipt['reason']}")
    for row in receipt["rows"]:
        if row["verdict"] in (MISS_AT_CAP, MISS_NOT_AT_CAP, MISS_CAP_UNKNOWN):
            lines.append(
                f"  - {row['verdict']:<18} rounds={row['rounds_used']}/{row['cap_rounds']} "
                f"calls={row['calls_fired']} {row['family']} {str(row['prompt'])[:40]!r}"
            )
    return "\n".join(lines)


def _selftest() -> int:
    """Model-free: prove the classification and the transcript reader, without a surface."""
    def line(event: dict) -> dict:
        return event

    transcript = [
        line({"type": "model_info", "model": "m"}),
        line({"type": "activity", "cmd": "Tool round 1…", "status": "running"}),
        line({"type": "tool_start", "tool": "read_file", "args": {"path": "a"}}),
        line({"type": "chunk", "data": "hello "}),
        line({"type": "activity", "cmd": "Tool round 2… (nudge 1)", "status": "running"}),
        line({"type": "tool_start", "tool": "tool_call", "args": {"name": "web_search"}}),
        line({"type": "chunk", "data": "world"}),
    ]
    tools, dispatched, answer, counts, rounds, error = parse_transcript(transcript)
    # Reader agrees with the live runner's own reader on the shared surface.
    ref_tools, ref_dispatched, ref_answer, ref_counts, ref_error = parse_events(
        ["data: " + json.dumps(event) for event in transcript]
    )
    checks = {
        "tools": tools == ref_tools == ["read_file", "tool_call"],
        "dispatched": dispatched == ref_dispatched == ["web_search"],
        "answer": answer == ref_answer == "hello world",
        "counts": counts == ref_counts,
        "error": error == ref_error is None,
        "rounds": rounds == 2,
        "phase_non_line": rounds_in_phase("Processing results…") == 0,
    }

    cap = cap_for(40)
    from core.chat import TOOL_BUDGET_HARD_CAP, clamp_tool_budget
    from core.chat_context import _budget_exhausted_note

    checks["cap_contract_none"] = cap_for(None) == clamp_tool_budget(None)
    checks["cap_contract_hard"] = cap_for(999) == TOOL_BUDGET_HARD_CAP
    checks["stall_note"] = ended_at_cap(_budget_exhausted_note(cap), 1, cap) is True
    checks["stall_rounds"] = ended_at_cap("", cap, cap) is True

    note = _budget_exhausted_note(cap)
    checks["verdict_hit"] = classify(outcome=True, answer="done", rounds=1, cap=cap, error=None) == HIT
    checks["verdict_at_cap"] = classify(outcome=False, answer=note, rounds=3, cap=cap, error=None) == MISS_AT_CAP
    checks["verdict_not_at_cap"] = classify(outcome=False, answer="an answer", rounds=2, cap=cap, error=None) == MISS_NOT_AT_CAP
    checks["verdict_unknown"] = classify(outcome=False, answer="", rounds=0, cap=cap, error=None) == MISS_CAP_UNKNOWN
    checks["verdict_outcome_unknown"] = classify(outcome=None, answer="", rounds=0, cap=cap, error=None) == OUTCOME_UNKNOWN
    checks["verdict_error"] = classify(outcome=False, answer="x", rounds=1, cap=cap, error="boom") == ERROR

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'ok ' if ok else 'FAIL'} {name}")
    print(f"call-cap receipt selftest: {'ok' if not failed else 'FAILED (' + ', '.join(failed) + ')'}")
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="File a per-case calls-against-cap receipt for the live eval")
    parser.add_argument("--collect", action="store_true",
                        help="drive the suite through the surface and file the receipt")
    parser.add_argument("--from-record", type=Path, default=None,
                        help="audit a live-eval --json-out record instead of running")
    parser.add_argument("--selftest", action="store_true",
                        help="no model: prove the classification and the transcript reader")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--family", action="append", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--tool-budget", type=int, default=None,
                        help="cap the loop's rounds per turn (default: profile value)")
    parser.add_argument("--mode", default="agent")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--no-decline", action="store_true")
    parser.add_argument("--note", default="", help="the load and conditions this run happened under")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TURN_TIMEOUT)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--force", action="store_true",
                        help="collect on a box that the idle rule says is busy")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.from_record is not None:
        receipt = receipt_from_record(json.loads(args.from_record.read_text(encoding="utf-8")))
    else:
        cond = conditions(args.base)
        command = (
            "python -m evals.call_cap_receipt --collect "
            f"--family tool-calling --family refusal --limit 12 --tool-budget 40 "
            f"--base {args.base} --json-out <run>.json"
        )
        if not args.force and not cond["idle"]:
            receipt = not_measured_receipt(
                why=("the box is not idle: a measurement on a loaded box measures the box, "
                     "not the product (contract rule 3)"),
                cond=cond, command=command)
            print(summary(receipt))
            if args.json_out:
                args.json_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                print(f"call-cap receipt: wrote {args.json_out}")
            return 3
        if not cond["surface_listening"]:
            receipt = not_measured_receipt(
                why=("no surface answers on the base: the live path has nowhere to run, "
                     "so there is no number to file"),
                cond=cond, command=command)
            print(summary(receipt))
            if args.json_out:
                args.json_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                print(f"call-cap receipt: wrote {args.json_out}")
            return 2
        try:
            receipt = collect(base=args.base, families=args.family, limit=args.limit,
                              mode=args.mode, note=args.note, timeout=args.timeout,
                              autonomous=args.auto, decline=not args.no_decline,
                              tool_budget=args.tool_budget)
        except EngineUnavailable as exc:
            receipt = not_measured_receipt(why=f"no run — {exc}", cond=cond, command=command)
            print(summary(receipt))
            if args.json_out:
                args.json_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            return 2

    print(summary(receipt))
    if args.json_out:
        args.json_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"call-cap receipt: wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
