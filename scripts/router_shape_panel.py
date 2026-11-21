#!/usr/bin/env python3
"""Price the loop shapes a router would move onto the small local tier.

One row per shape, one column per arm. A shape is a mechanical loop step the router's
read-only branch claims: listing, classification, extractive summary, first-pass search,
field extraction, path arithmetic. Each has a checker that reads the answer, never a judge
model, and a negative control that proves the checker can fail.

The small arm is the tier under test. When it cannot produce one real turn the row is marked
`unreachable` and the big arm is not substituted for it — the router's own refusal rule, held
by the panel so a table cannot quietly become a single-arm table.

    python3 scripts/router_shape_panel.py                      # both arms
    python3 scripts/router_shape_panel.py --arm active         # the big tier only
    python3 scripts/router_shape_panel.py --json               # machine-readable

Wall-clock columns are environment readings and carry no budget: load is printed with them, and a
host running CI at load 20 is not a place to state a latency ceiling. Token columns come from
the provider's own usage block when it sends one, otherwise from the calibrated counter in
core.usage, and the row says which.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import NamedTuple

import ollama

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.model_config import ModelTier, get_model_config
from core.model_provider import (
    ModelProviderConfig,
    build_engine_provider,
    build_provider_client,
)
from core.usage import estimate_tokens

MAX_COMPLETION_TOKENS = 64
ARM_TIMEOUT_S = 120.0


class Arm(NamedTuple):
    model: str
    base_url: str


#: (id, instruction, payload, expected, checker, the wrong answer the checker must reject)
SHAPES: tuple[dict, ...] = (
    {
        "id": "listing",
        "kind": "listing",
        "instruction": "Return only the names that end with .json, one per line, sorted. "
        "No explanation.",
        "payload": "todos.json\nnotes/a.md\nledger.json\nreadme.md\ndata/x.csv\nledger.json.tmp\n",
        "expected": "ledger.json\ntodos.json",
        "wrong": "todos.json\nnotes/a.md\nledger.json",
    },
    {
        "id": "classify-tool-error",
        "kind": "classification",
        "instruction": "Classify this tool error as exactly one of missing-param, enum-mismatch, "
        "unknown-param. Answer with the label only.",
        "payload": "[TOOL-ERROR] read_file: required parameter 'path' was not given",
        "expected": "missing-param",
        "wrong": "enum-mismatch",
    },
    {
        "id": "extractive-rule",
        "kind": "summary",
        "instruction": "Which rule id applies to a refund for a booking older than 30 days? "
        "Answer with the id only.",
        "payload": "R1 confirmed bookings are fixed after 18:00 UTC on the start day. "
        "R2 a change to a fixed booking is refused. "
        "R3 refunds for bookings older than 30 days are paid as store credit only.",
        "expected": "R3",
        "wrong": "R2",
    },
    {
        "id": "first-pass-search",
        "kind": "search",
        "instruction": "Return a JSON array of the file names that mention invoices. Nothing else.",
        "payload": json.dumps(
            [
                "2026-03-invoice-001.pdf",
                "notes.md",
                "invoice-archive.tar",
                "budget.q4",
                "ledger.json",
                "readme.md",
                "quote-77.eml",
                "invoices",
                "photos.png",
                "config.yaml",
            ]
        ),
        "expected_array": [
            "2026-03-invoice-001.pdf",
            "invoice-archive.tar",
            "invoices",
        ],
        "wrong": "invoices",
    },
    {
        "id": "field-extract",
        "kind": "extraction",
        "instruction": "Return a JSON object with one key, total, holding the number as a string.",
        "payload": "total=1107 currency=EUR date=2026-10-11",
        "expected_object": {"total": "1107"},
        "wrong": '{"total": 1077}',
    },
    {
        "id": "path-arithmetic",
        "kind": "extraction",
        "instruction": "Normalise this workspace path: no leading ./, no .. segments. "
        "Answer with the path only.",
        "payload": "./notes/../report.md",
        # notes/.. cancels, so the normalised form is the bare report.md. Measured 2026-10-11:
        # this expectation first read notes/report.md and both arms "failed" a shape that was
        # the instrument's error, not the model's.
        "expected": "report.md",
        "wrong": "./notes/report.md",
    },
)


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _json_array(text: str) -> list[str] | None:
    match = re.search(r"\[[^\]]*\]", text or "", re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, list) else None


def check(shape: dict, answer: str) -> bool:
    """Deterministic, whitespace-tolerant, never a judge model."""
    text = (answer or "").strip()
    if "expected_array" in shape:
        got = _json_array(text)
        return got is not None and sorted(map(str, got)) == sorted(
            shape["expected_array"]
        )
    if "expected_object" in shape:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return False
        try:
            return json.loads(match.group(0)) == shape["expected_object"]
        except json.JSONDecodeError:
            return False
    if shape["kind"] == "listing":
        got = sorted(line.strip() for line in text.splitlines() if line.strip())
        return got == sorted(shape["expected"].splitlines())
    if shape["kind"] == "classification":
        return _first_line(text).lower().strip(".,`'\" ") == shape["expected"]
    if shape["id"] == "extractive-rule":
        return bool(re.search(rf"\b{shape['expected']}\b", text)) and not re.search(
            r"\bR[12]\b", text
        )
    return _first_line(text) == shape["expected"]


def checkers_hold() -> list[str]:
    """Names of shapes whose checker accepts a wrong answer — must stay empty."""
    broken = []
    for shape in SHAPES:
        if not check(
            shape,
            shape.get("expected")
            or json.dumps(shape.get("expected_array") or shape.get("expected_object")),
        ):
            broken.append(f"{shape['id']}:accepts-nothing")
        if check(shape, shape["wrong"]):
            broken.append(f"{shape['id']}:accepts-the-wrong-answer")
    return broken


def _prompt(shape: dict) -> list[dict]:
    return [
        {"role": "user", "content": f"{shape['instruction']}\n\n{shape['payload']}"}
    ]


def _content(response) -> str:
    if isinstance(response, dict):
        message = response.get("message") or {}
        return str(message.get("content") or "").strip()
    return str(getattr(getattr(response, "message", None), "content", "") or "").strip()


def _counts(response, measured_before: dict | None) -> tuple[int, int, bool]:
    """Prompt and completion counts, from the provider when the provider said them.

    The Ollama reply carries them on the response; the OpenAI-compatible path records its
    usage block into the turn's measured counter, so the delta over that counter is what the
    endpoint reported for this call.
    """
    if isinstance(response, dict):
        p = response.get("prompt_eval_count")
        c = response.get("eval_count")
        if p is not None and c is not None:
            return int(p), int(c), True
        usage = response.get("usage") or {}
        if usage.get("prompt_tokens") is not None:
            return (
                int(usage["prompt_tokens"]),
                int(usage.get("completion_tokens") or 0),
                True,
            )
    from core.tools.session_ctx import get_measured_usage

    after = get_measured_usage() or {"prompt_tokens": 0, "completion_tokens": 0}
    before = measured_before or {"prompt_tokens": 0, "completion_tokens": 0}
    delta = (
        int(after.get("prompt_tokens") or 0) - int(before.get("prompt_tokens") or 0),
        int(after.get("completion_tokens") or 0)
        - int(before.get("completion_tokens") or 0),
    )
    if delta[0] > 0 and delta[1] >= 0:
        return delta[0], delta[1], True
    return -1, -1, False


async def _one_call(client, model: str, shape: dict, *, local: bool) -> dict:
    messages = _prompt(shape)
    started = time.perf_counter()
    from core.tools.session_ctx import get_measured_usage

    measured_before = None if local else get_measured_usage()
    try:
        if local:
            response = await asyncio.wait_for(
                client.chat(model=model, messages=messages), timeout=ARM_TIMEOUT_S
            )
        else:
            response = await asyncio.wait_for(
                client.chat(model=model, messages=messages, stream=False),
                timeout=ARM_TIMEOUT_S,
            )
    except Exception as exc:  # noqa: BLE001 — any failure of the arm is the row it belongs to
        return {
            "status": "unreachable",
            "error": f"{type(exc).__name__}: {str(exc)[:120]}",
            "wall_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    wall_ms = round((time.perf_counter() - started) * 1000, 1)
    answer = _content(response)
    prompt_tokens, completion_tokens, provider_measured = _counts(
        response, measured_before
    )
    if not provider_measured:
        prompt_tokens = estimate_tokens("\n".join(m["content"] for m in messages))
        completion_tokens = estimate_tokens(answer)
    return {
        "status": "answered",
        "pass": check(shape, answer),
        "answer": answer[:160],
        "wall_ms": wall_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens_measured_by_provider": provider_measured,
    }


def run_arm(arm: str, cfg, shapes: list[dict], reps: int = 1) -> list[dict]:
    local = arm == "small"

    async def _sweep() -> list[dict]:
        # One client per loop: the async client binds to the loop it was built on, and a
        # fresh loop per shape would close it under the next call.
        client = (
            ollama.AsyncClient(host=cfg.base_url)
            if local
            else build_provider_client(cfg)
        )
        out = []
        for rep in range(reps):
            for shape in shapes:
                out.append(
                    {
                        "shape": shape["id"],
                        "rep": rep + 1,
                        "arm": arm,
                        "model": cfg.model,
                        **await _one_call(client, cfg.model, shape, local=local),
                    }
                )
        return out

    return asyncio.run(_sweep())


def summarise(rows: list[dict]) -> dict:
    answered = [r for r in rows if r["status"] == "answered"]
    walls = [r["wall_ms"] for r in answered]
    return {
        "arm": rows[0]["arm"] if rows else "?",
        "model": rows[0]["model"] if rows else "?",
        "rows": len(rows),
        "answered": len(answered),
        "unreachable": sum(1 for r in rows if r["status"] == "unreachable"),
        "passed": sum(1 for r in answered if r.get("pass")),
        "wall_ms_median": round(statistics.median(walls), 1) if walls else None,
        "wall_ms_max": round(max(walls), 1) if walls else None,
        "prompt_tokens_sum": sum(r.get("prompt_tokens", 0) for r in answered),
        "completion_tokens_sum": sum(r.get("completion_tokens", 0) for r in answered),
        "provider_measured_tokens": all(
            r.get("tokens_measured_by_provider", False) for r in answered
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", choices=("both", "small", "active"), default="both")
    ap.add_argument(
        "--reps",
        type=int,
        default=2,
        help="observations per shape per arm; one rep is an anecdote and grounds nothing",
    )
    ap.add_argument("--only", help="comma-separated shape ids")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--selftest", action="store_true", help="check the checkers and exit"
    )
    args = ap.parse_args(argv)

    broken = checkers_hold()
    if args.selftest:
        for line in broken:
            print(f"checker defect: {line}")
        return 1 if broken else 0
    if broken:
        print(f"panel refuses to run: {len(broken)} checker defect(s)", file=sys.stderr)
        return 2

    ids = {s.strip() for s in (args.only or "").split(",") if s.strip()}
    shapes = [s for s in SHAPES if not ids or s["id"] in ids]
    if not shapes:
        print(f"no shape matches --only={args.only}", file=sys.stderr)
        return 2

    arms: dict[str, object] = {}
    if args.arm in ("both", "small"):
        arms["small"] = _small_arm(get_model_config(ModelTier.FAST))
    if args.arm in ("both", "active"):
        arms["active"] = _active_arm()

    rows: list[dict] = []
    for arm, cfg in arms.items():
        rows.extend(run_arm(arm, cfg, shapes, reps=max(1, args.reps)))

    load = os.getloadavg()
    if args.json:
        print(
            json.dumps(
                {
                    "load1": round(load[0], 2),
                    "rows": rows,
                    "by_arm": [
                        summarise([r for r in rows if r["arm"] == a]) for a in arms
                    ],
                },
                indent=1,
            )
        )
        return 0

    print(
        f"host load 1-min {load[0]:.2f}   shapes {len(shapes)}   arms {','.join(arms)} "
        f"reps {max(1, args.reps)}"
    )
    print(
        f"{'shape':20}{'rep':5}{'arm':8}{'status':13}{'pass':6}{'wall_ms':10}{'pin':7}{'pout':6}"
        f"answer"
    )
    for r in rows:
        print(
            f"{r['shape']:20}{r['rep']:<5}{r['arm']:8}{r['status']:13}"
            f"{('yes' if r.get('pass') else ('no' if r['status'] == 'answered' else '-')):6}"
            f"{r['wall_ms']:10}{r.get('prompt_tokens', '-')!s:7}"
            f"{r.get('completion_tokens', '-')!s:6}"
            f"{(r.get('answer') or r.get('error', '')).replace(chr(10), ' | ')[:70]}"
        )
    print()
    for summary in (summarise([r for r in rows if r["arm"] == a]) for a in arms):
        print(
            f"arm {summary['arm']:7} model {summary['model']:22} answered {summary['answered']}/"
            f"{summary['rows']}  passed {summary['passed']}  unreachable {summary['unreachable']} "
            f"wall median {summary['wall_ms_median']} max {summary['wall_ms_max']}  "
            f"tokens in/out {summary['prompt_tokens_sum']}/{summary['completion_tokens_sum']} "
            f"({'provider' if summary['provider_measured_tokens'] else 'calibrated'} counter)"
        )
    return 0


def _small_arm(tier):
    """The tier's own endpoint and model, never the active engine's host."""
    config = get_model_config(tier.tier)
    return Arm(model=config.name, base_url=config.base_url)


def _active_arm():
    """The engine the user chose, from the shared resolution rather than the env default.

    `get_active_provider()` reads the env plus the process override a running server sets;
    in a standalone process it answers with the local default, which is not what the product
    would run. The resolution the CLI and the server share is the honest source.
    """
    from core.engine_config import resolve_engine_choice

    choice = resolve_engine_choice()
    if choice.provider == "openai_compatible":
        return build_engine_provider(choice.api_url, choice.model)
    return ModelProviderConfig(
        provider=choice.provider,
        model=choice.model,
        base_url=choice.api_url
        or os.environ.get("EPHE_LOCAL_OLLAMA_BASE_URL", "http://localhost:11434"),
        label=f"{choice.provider} (chosen)",
        offline_capable=True,
        requires_internet=False,
    )


if __name__ == "__main__":
    sys.exit(main())
