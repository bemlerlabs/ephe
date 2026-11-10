"""evals/creation_run.py — the creation eval's engine half: 24 Creator turns, one server.

`evals/creation_runner.py` grades what it is handed and `evals/creation_transcript.py`
folds frames into the shapes that grader reads. This module is the part that pays: it boots
one Ephe server on a loopback port with one engine, runs every case's turn against it, and
writes the transcripts, the per-case staging roots and the run records the receipt is built
from.

The decisions around the spend are the ones worth testing, so they live in functions that
need no server: what a case turns into, whether the server is talking to the engine the
command line named, and what one turn's record says about itself. An engine that dies
mid-turn produces a broken run row, which is a different thing from a case that failed, and
the receipt keeps them apart.

Run it with:

    ./.venv/bin/python evals/creation_run.py --out <dir> --key-file <file> \
        --base-url <url> --model <name>

and grade the result with the command it prints at the end.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.redact import redact
from core.tools.creator_guard import CREATOR_MODE, PRIVILEGES
from evals.creation_transcript import (
    build_transcript,
    engine_environment,
    take_staged_bundles,
    tool_events,
)

ENGINE_PROVIDER = "openai_compatible"
_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


class HealthMismatch(RuntimeError):
    """The server is not talking to the engine this run is about to pay for."""


@dataclass
class CasePlan:
    """One case as the turn it asks for."""

    case_id: str
    session_id: str
    mode: str
    privileges: list[str]
    message: str
    tools: list[str] = field(default_factory=list)


def plan_case(case: dict, nonce: str) -> CasePlan:
    """The turn a case line describes, refused when it describes something else.

    A creation case runs in Creator mode with the privileges its own line grants. Running
    it in another mode would grade the engine in a mode it was never in, and the rubric
    says so; a privilege the guard does not know would be stored and then answer nothing.
    """
    case_id = str(case.get("id") or "")
    if not case_id:
        raise ValueError("case has no id")
    mode = str(case.get("mode") or "")
    if mode != CREATOR_MODE:
        raise ValueError(f"{case_id}: mode is {mode!r}, a creation case runs as {CREATOR_MODE!r}")
    if "input" not in case or not str(case["input"]).strip():
        raise ValueError(f"{case_id}: input is missing or empty")
    privileges = [str(p) for p in (case.get("privileges") or [])]
    unknown = [p for p in privileges if p not in PRIVILEGES]
    if unknown:
        raise ValueError(f"{case_id}: privilege {unknown[0]!r} is not one the guard knows")
    session_id = f"{case_id}-{nonce}"[:64]
    if not set(session_id) <= _ID_CHARS:
        raise ValueError(f"{case_id}: session id {session_id!r} is not a store name")
    return CasePlan(
        case_id=case_id,
        session_id=session_id,
        mode=mode,
        privileges=privileges,
        message=str(case["input"]),
        tools=[str(t) for t in (case.get("tools") or [])],
    )


def verify_health(health: dict, *, model: str, base_url: str) -> dict:
    """The server's own answer about its engine, refused when it is not the one asked for.

    `/api/health` reports what the running process is actually addressing, which is the
    only place a stale persisted choice, a wrong endpoint or a key the provider rejects
    shows up before 24 turns are spent. A payload that carries no model is a refusal: a
    field the route stopped answering is not evidence that the engine is right.
    """
    seen_model = str(health.get("active_model") or "")
    seen_provider = str(health.get("active_provider") or "")
    if not seen_model:
        raise HealthMismatch(
            f"health carried no active_model (keys: {sorted(health)[:8]}); "
            f"the run asked for {model!r} at {base_url}"
        )
    if seen_model != model or seen_provider != ENGINE_PROVIDER:
        raise HealthMismatch(
            f"the server answers {seen_provider}/{seen_model!r}, this run pays for "
            f"{ENGINE_PROVIDER}/{model!r} at {base_url}"
        )
    return health


def run_record(case: dict, events: list[dict], *, staged: list[str], engine_error: str) -> dict:
    """What one turn did, in the fields the receipt quotes — and nothing the engine said.

    `usable` is the run's own health, not the case's verdict: a turn that answered nothing
    and ran nothing says the engine or the harness failed, and grading it would report that
    as a capability that is missing. The record is redacted as one serialized object because
    the text that leaks is the text an HTTP error quotes back.
    """
    answer = "".join(
        str(e.get("data") or "") for e in events if e.get("type") == "chunk"
    )
    names = [name for name, _ in tool_events(events)]
    error = engine_error or next(
        (str(e.get("msg") or "") for e in events if e.get("type") == "error"), ""
    )
    record = {
        "case_id": case.get("id"),
        "category": case.get("category", "unknown"),
        "answer_len": len(answer.strip()),
        "tools": sorted(set(names)),
        "failed_calls": sum(1 for _, line in tool_events(events) if "[tool-error" in line),
        "asked_user": sum(1 for e in events if e.get("type") == "ask_user"),
        "staged": list(staged),
        "error": error,
        "usable": bool(not engine_error and (len(answer.strip()) or names)),
    }
    return json.loads(redact(json.dumps(record, ensure_ascii=False)))


def _headers(base: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "Origin": base}


def put_consent(base: str, session_id: str, privileges: list[str]) -> dict:
    body = json.dumps({"session_id": session_id, "privileges": privileges}).encode()
    req = urllib.request.Request(
        base + "/api/creator/consent", data=body, headers=_headers(base), method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        return {"http_error": exc.code, "body": exc.read()[:300].decode("utf-8", "replace")}


def post_turn(base: str, plan: CasePlan, timeout: float) -> tuple[list[dict], list[str]]:
    """One turn over the shipped stream route, with every approval answered yes.

    The harness answers the sandbox dialog because the run is measuring what the engine
    builds when it is allowed to, and a turn that stopped at the dialog would be recorded as
    a tool that never fired.
    """
    body = json.dumps(
        {
            "message": plan.message,
            "history": [],
            "session_id": plan.session_id,
            "mode": plan.mode,
            "tool_budget": 16,
        }
    ).encode()
    req = urllib.request.Request(base + "/api/chat/stream", data=body, headers=_headers(base))
    events: list[dict] = []
    approvals: list[str] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            if event.get("type") == "sandbox_confirm" and event.get("token"):
                token = str(event["token"])
                approvals.append(token)
                answer = json.dumps({"token": token, "approved": True, "remember": True}).encode()
                try:
                    urllib.request.urlopen(
                        urllib.request.Request(
                            base + "/api/sandbox/approve", data=answer, headers=_headers(base)
                        ),
                        timeout=30,
                    )
                except Exception as exc:  # noqa: BLE001 — a dialog that cannot be answered is a run row
                    events.append({"type": "error", "msg": f"approve failed: {type(exc).__name__}"})
    return events, approvals


def boot_server(env: dict[str, str], port: int, work: Path, log: Path) -> subprocess.Popen:
    """A server whose working directory is the run's own folder.

    `core.engine_config.get_workspace_dir()` falls back to the config root when the process
    sits in the source checkout, and that root is off-limits to the read tools, so a server
    started from the lane writes a project it then cannot read back.
    """
    work.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as handle:
        return subprocess.Popen(
            [env_python(), str(ROOT / "run_server.py"), "--host", "127.0.0.1", "--port", str(port)],
            cwd=work,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )


def env_python() -> str:
    return str(ROOT / ".venv" / "bin" / "python")


def wait_for_health(base: str, proc: subprocess.Popen, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with {proc.returncode}")
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=5) as resp:
                return json.load(resp)
        except (OSError, ValueError):
            # Anything that is not a health document yet means the process is still booting.
            time.sleep(1.0)
    raise RuntimeError("health never answered")


def grading_command(out: Path, cases: Path) -> str:
    """The one command that grades this run, carrying the run's own home.

    The runner refuses `--browser` without `--config` (#161), so a printed command that
    left the home out would send the operator into a refusal after the turns were paid.
    """
    return (
        f"./.venv/bin/python evals/creation_runner.py --cases {cases} "
        f"--staging {out / 'staging.json'} --transcripts {out / 'transcripts.json'} "
        f"--config {out / 'config'} --browser"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="where the run and its artifacts go")
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/creation/cases.jsonl")
    parser.add_argument("--only", action="append", default=[], help="run one case id (repeatable)")
    parser.add_argument("--key-file", type=Path, required=True, help="one-line engine key; read, never printed")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, default=8795)
    parser.add_argument("--timeout", type=float, default=420.0, help="per turn")
    args = parser.parse_args(argv)

    from evals.creation_runner import load_cases

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    config = out / "config"
    config.mkdir(parents=True, exist_ok=True)
    nonce = time.strftime("%d%H%M%S", time.localtime())
    cases = [c for c in load_cases(args.cases) if not args.only or c["id"] in args.only]
    plans = [plan_case(case, nonce) for case in cases]
    env = engine_environment(
        key_file=args.key_file,
        config_dir=config,
        base_url=args.base_url,
        model=args.model,
        port=args.port,
    )
    base = f"http://127.0.0.1:{args.port}"
    env.pop("EPHE_LIVE_PORT", None)
    env.pop("EPHE_WORKSPACE", None)
    proc = boot_server(env, args.port, out / "work", out / "server.log")
    transcripts: dict[str, str] = {}
    staging: dict[str, str] = {}
    records: list[dict] = []
    code = 0
    try:
        verify_health(wait_for_health(base, proc, 120.0), model=args.model, base_url=args.base_url)
        for case, plan in zip(cases, plans):
            consent = put_consent(base, plan.session_id, plan.privileges)
            engine_error = ""
            if "http_error" in consent:
                engine_error = f"consent refused: {consent['http_error']}"
            events: list[dict] = []
            try:
                if not engine_error:
                    events, _ = post_turn(base, plan, args.timeout)
            except Exception as exc:  # noqa: BLE001  a lost turn still owes a run row
                engine_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            dest = out / "runs" / plan.case_id
            staged = take_staged_bundles(config, dest)
            transcripts[plan.case_id] = build_transcript(events)
            staging[plan.case_id] = str(dest)
            records.append(
                run_record(case, events, staged=staged, engine_error=engine_error)
            )
            print(
                f"{plan.case_id:14s} tools={len(records[-1]['tools'])} "
                f"failed={records[-1]['failed_calls']} staged={len(staged)} "
                f"answer={records[-1]['answer_len']} usable={records[-1]['usable']}"
            )
    except (HealthMismatch, RuntimeError) as exc:
        print(f"run refused: {exc}", file=sys.stderr)
        code = 2
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()

    (out / "transcripts.json").write_text(
        json.dumps(transcripts, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "staging.json").write_text(
        json.dumps(staging, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "runs.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    unusable = [r["case_id"] for r in records if not r["usable"]]
    print(f"turns={len(records)} unusable={len(unusable)}" + (f" {unusable}" if unusable else ""))
    print(f"grade it: {grading_command(out, args.cases)}")
    return code or (1 if unusable and len(unusable) == len(records) else 0)


if __name__ == "__main__":
    raise SystemExit(main())
