"""evals/creation_offer_probe.py — what the engine is actually handed, without spending a turn.

`evals/creation_run.py` pays an engine to build things. Before that money is spent it is worth
knowing what a Creator turn *sends*: the tool array the model is offered, the mode the route
put it in, the consent the session holds. Those are the three things a live case can silently
run around, and a model that was never offered `create_plugin_scaffold` produces a transcript
that looks like a capability that is missing.

So this runs the real server against a local OpenAI-compatible stub that keeps every request
it is given and answers with one scripted reply. No key, no quota, no opinion - it prints the
request and lets the reader judge it.

    ./.venv/bin/python evals/creation_offer_probe.py [--message TEXT] [--privileges files,code]

Exit is 0 when the Creator calls the grant covers are all in the array the stub was handed.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tools.creator_tools import CREATOR_TOOL_SCHEMAS
from evals.creation_run import (
    boot_server,
    put_consent,
    verify_health,
    wait_for_health,
)
from evals.creation_transcript import engine_environment

# Read from the schemas that offer the calls, so the probe cannot pass on a list the
# product has outgrown.
CREATOR_CALLS = sorted(str(entry["function"]["name"]) for entry in CREATOR_TOOL_SCHEMAS)
PROBE_KEY = "sk-" + "0" * 32
PROBE_MODEL = "probe-model"


class _Stub(BaseHTTPRequestHandler):
    """An engine that writes down what it was asked for and answers once."""

    requests: ClassVar[list[dict]] = []
    model = PROBE_MODEL

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json({"data": [{"id": type(self).model}]})
            return
        self._json({"error": {"message": "probe stub serves /models only"}}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._json({"error": {"message": "probe stub reads JSON only"}}, 400)
            return
        type(self).requests.append(payload)
        if not payload.get("stream"):
            self._json(
                {
                    "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": "probe answer"},
                         "finish_reason": "stop"}
                    ]
                }
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in (
            {"choices": [{"index": 0, "delta": {"content": "probe answer"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ):
            self.wfile.write(b"data: " + json.dumps(frame).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")

    def _json(self, body: dict, status: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args) -> None:
        return


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def start_stub(model: str) -> tuple[ThreadingHTTPServer, str, type]:
    handler = type("BoundStub", (_Stub,), {"requests": [], "model": model})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1", handler


def offer_of(requests: list[dict]) -> list[str]:
    """The names in the array of the first call the turn made."""
    if not requests:
        return []
    return [str(t.get("function", {}).get("name")) for t in (requests[0].get("tools") or [])]


def covered_calls(privileges: list[str] | tuple[str, ...] = ()) -> list[str]:
    """The Creator calls the stated grant covers, read from the guard that refuses them.

    The probe used to answer "which of the five are absent" against every name, so a
    turn holding `code` alone read as defective for the four `files` calls the guard
    is *supposed* to withhold. The answer here is the `judge` ruling the tool loop
    refuses on, so the probe cannot drift from the gate it is measuring.
    """
    from core.tools.creator_guard import judge

    held = frozenset(str(p) for p in (privileges or ()))
    return sorted(name for name in CREATOR_CALLS if judge(name)[0] in held)


def describe(requests: list[dict], privileges: list[str] | tuple[str, ...] = ()) -> dict:
    first = requests[0] if requests else {}
    names = offer_of(requests)
    covered = covered_calls(privileges)
    system = next(
        (str(m.get("content") or "") for m in (first.get("messages") or []) if m.get("role") == "system"),
        "",
    )
    return {
        "calls": len(requests),
        "offered": names,
        "creator_offered": sorted(n for n in names if n in CREATOR_CALLS),
        # Every one of the five that is absent: the reading a live case is judged by,
        # and the one a grant can never satisfy for names it does not buy.
        "creator_missing": sorted(n for n in CREATOR_CALLS if n not in names),
        # The defect: a call the grant *does* cover, and the array still does not carry.
        "creator_covered": covered,
        "creator_missing_from_grant": [n for n in covered if n not in names],
        "system_chars": len(system),
        "system_head": system[:400],
        "model": first.get("model"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="where the probe server's own files go")
    parser.add_argument("--message", default="Make a floating countdown timer widget.")
    parser.add_argument("--privileges", default="files,code", help="comma-separated creator privileges")
    parser.add_argument("--port", type=int, default=8796, help="the Ephe server's port")
    parser.add_argument("--json", action="store_true", help="print the reading as one JSON object")
    args = parser.parse_args(argv)

    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} already holds a probe; choose a fresh --out")
    out.mkdir(parents=True)
    key_file = out / "probe.key"
    key_file.write_text(PROBE_KEY + "\n", encoding="utf-8")
    key_file.chmod(0o600)

    stub, stub_url, handler = start_stub(PROBE_MODEL)
    env = engine_environment(
        key_file=key_file,
        config_dir=out / "config",
        base_url=stub_url,
        model=PROBE_MODEL,
        port=args.port,
    )
    env.pop("EPHE_LIVE_PORT", None)
    env.pop("EPHE_WORKSPACE", None)
    base = f"http://127.0.0.1:{args.port}"
    proc = boot_server(env, args.port, out / "work", out / "server.log")
    privileges = [p for p in args.privileges.split(",") if p]
    code = 0
    try:
        verify_health(wait_for_health(base, proc, 120.0), model=PROBE_MODEL, base_url=stub_url)
        consent = put_consent(base, "offer-probe-1", privileges)
        if "http_error" in consent:
            raise SystemExit(f"consent refused: {consent['http_error']} {consent.get('body', '')[:200]}")
        _run_turn(base, args.message)
        reading = describe(handler.requests, privileges)
        reading["privileges"] = privileges
        (out / "offer.json").write_text(json.dumps(reading, indent=1), encoding="utf-8")
        (out / "requests.json").write_text(
            json.dumps(handler.requests, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        if args.json:
            print(json.dumps(reading, indent=1))
        else:
            print(f"engine calls kept : {reading['calls']}")
            print(f"array size         : {len(reading['offered'])}")
            print(f"creator in array   : {', '.join(reading['creator_offered']) or '(none)'}")
            print(f"creator missing    : {', '.join(reading['creator_missing']) or '(none)'}")
            print(
                "covered and absent : "
                f"{', '.join(reading['creator_missing_from_grant']) or '(none)'}"
            )
            print(f"model addressed    : {reading['model']}")
            print(f"system prompt head : {reading['system_head'][:220]}")
            print(f"full reading       : {out / 'offer.json'}")
            print(f"the request itself : {out / 'requests.json'}")
        code = 0 if not reading["creator_missing_from_grant"] and reading["calls"] else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        stub.shutdown()
        stub.server_close()
    return code


def _run_turn(base: str, message: str) -> None:
    body = json.dumps(
        {"message": message, "history": [], "session_id": "offer-probe-1", "mode": "creator", "tool_budget": 1}
    ).encode()
    req = urllib.request.Request(
        base + "/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json", "Origin": base},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        for _ in resp:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
