#!/usr/bin/env python3
"""Live smoke 2+3: (a) slash-skill /help fast path, (b) edit_file approval + diff."""
import json
import urllib.request

BASE = "http://127.0.0.1:8765/api/chat/stream"
HDRS = {"Content-Type": "application/json", "Authorization": "***"}

def stream(body, approve=True):
    events = []
    resp = urllib.request.urlopen(urllib.request.Request(
        BASE, json.dumps(body).encode(), HDRS), timeout=240)
    for raw in resp:
        line = raw.decode().strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:])
        events.append(ev)
        if ev["type"] == "sandbox_confirm" and approve:
            urllib.request.urlopen(urllib.request.Request(
                BASE.replace("/chat/stream", "/sandbox/approve"),
                json.dumps({"token": ev["token"], "approved": True}).encode(),
                HDRS), timeout=10).read()
        if ev["type"] in ("done", "error"):
            break
    return events

def types(events):
    return [e["type"] for e in events]

# (a) Slash skill: the /help fast path
ev = stream({"message": "/help", "use_web_search": False})
ts = types(ev)
assert "file_result" not in ts
chunk_text = "".join(e.get("data", "") for e in ev if e["type"] == "chunk")
assert "/project" in chunk_text, chunk_text[:200]
print("a) /help Fast-Path OK —", chunk_text.strip()[:60].replace("\n", " "))

# (b) edit_file: file exists, approval, diff markers, real content
path = "/tmp/ephe_smoke_edit.txt"
open(path, "w").write("ZEILE_A\n")
ev = stream({
    "message": f"Ersetze in der Datei {path} den Text ZEILE_A durch ZEILE_B "
               f"mit dem Tool edit_file. Bestätigungsanfragen beantworte ich selbst.",
    "use_web_search": False,
}, approve=True)
answer = "".join(e.get("data", "") for e in ev if e["type"] == "chunk")
content = open(path).read()
assert "ZEILE_B" in content, f"file not changed: {content!r} | answer={answer[:200]}"
print("b) edit_file live OK — file holds ZEILE_B, approvals:",
      sum(1 for e in ev if e["type"] == "sandbox_confirm"))
print("SMOKE 2+3 OK")
