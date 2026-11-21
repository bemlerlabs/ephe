#!/usr/bin/env python3
"""Live smoke: /api/chat/stream → tool call → sandbox approval → result.

Stream contract (server/routes/chat.py): model_info, thinking_start/chunk,
activity, chunk, sandbox_confirm, done. The tool result goes back into the model
and appears in chunk/done — there is no tool_result event.
The model routes tools stochastically; hence up to 3 attempts until a
run_shell call arrives. The approval rule itself is unit-tested
(tests/test_approval.py, tests/test_run_shell_executes.py).
"""
import json
import os
import sys
import urllib.request

PROMPT = (
    "Führe exakt diesen Shell-Befehl mit dem run_shell Tool aus: "
    "echo SMOKE_OK. Rufe kein anderes Tool auf. Antworte danach mit der Ausgabe."
)
MAX_ATTEMPTS = int(sys.argv[1]) if len(sys.argv) > 1 else 3

token = os.environ.get("EPHE_SMOKE_TOKEN", "pre-auth-token")


def post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Ephe-Token": token,
        },
    )
    return urllib.request.urlopen(req, timeout=180)


def attempt() -> bool:
    resp = post(
        "http://127.0.0.1:8765/api/chat/stream",
        {"message": PROMPT, "use_web_search": False},
    )
    confirm = None
    tool_activity = None
    answer = ""
    done = False

    def consume(stream, stop_on_confirm):
        nonlocal confirm, tool_activity, answer, done
        for raw in stream:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            evt = json.loads(line[5:])
            t = evt.get("type")
            if t == "sandbox_confirm" and evt.get("tool") == "run_shell":
                confirm = evt
                if stop_on_confirm:
                    return
            elif t == "activity" and str(evt.get("cmd", "")).startswith("run_shell"):
                tool_activity = evt["cmd"]
            elif t == "chunk":
                answer += evt.get("data", "")
            elif t == "done":
                done = True

    consume(resp, stop_on_confirm=True)
    if confirm is None:
        print(f"  no run_shell sandbox_confirm — reply: {answer.strip()[:120]!r}")
        return False

    print("sandbox_confirm:", confirm["tool"], confirm["args"])
    ack = post(
        "http://127.0.0.1:8765/api/sandbox/approve",
        {"token": confirm["token"], "approved": True},
    )
    assert json.loads(ack.read()) == {"status": "ok"}, "approval not accepted"

    consume(resp, stop_on_confirm=False)
    print("tool activity:", tool_activity)
    print("final answer:", repr(answer.strip()[:200]))
    assert tool_activity, "no run_shell activity after approval"
    assert done, "stream did not end with done"
    assert "SMOKE_OK" in answer, "tool result SMOKE_OK missing from the final answer"
    return True


for i in range(1, MAX_ATTEMPTS + 1):
    print(f"attempt {i}/{MAX_ATTEMPTS}")
    if attempt():
        print("STREAM SMOKE OK (run_shell -> sandbox_confirm -> approve -> done with result)")
        sys.exit(0)
print(f"SMOKE FAILED: no run_shell tool call in {MAX_ATTEMPTS} attempts (model routing)")
sys.exit(1)
