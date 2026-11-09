"""The plugin bridge protocol: one request, one reply, both on the pipes that already exist.

core/sandbox/bridge.py

Task #23 exists because measurement closed the easy road. A confined plugin worker was
reading `200` from the host's own loopback API until `380bb9f0` gave it `(deny network*)` /
`--unshare-net`. The socket carried no identity: nothing in the request said which plugin
or which tool, no permission family was checked, and no audit row tied the call to the
mount that made it. A capability that needs the host arrives over the stdio pipes the
worker is already talking on. The host binds the plugin id, the tool, the declared family
and the fingerprint from the mount that started the worker. The child's line carries the
method and the arguments. A name the child types is ignored.

Three shapes cross, and only two kinds of line ever appear on the child's stdout:

    child -> host   {"bridge": 1, "id": 3, "method": "fetch", "args": {"url": "…"}}
    host  -> child  {"bridge": 1, "id": 3, "ok": true,  "result": {…}}
    host  -> child  {"bridge": 1, "id": 3, "ok": false, "code": "bridge_method_denied"}
    child -> host   {"ok": true, "result": …}                  # the tool's own answer

The result line is what `run_plugin_tool` classifies today, and it stays the only line the
classifier sees: the drain separates bridge traffic before anything reaches the bounded
buffer, so the protocol check, the output cap and the timeout story in #47 keep their exact
meaning. A tool that never calls the bridge produces byte-for-byte the stream it produced
before this file existed.

Why ids and a depth cap. The child asks and waits — one outstanding call at a time — so the
id is not for multiplexing; it is what lets the host say "this reply answers that request" and
let the child refuse an answer that arrived for something else. The depth cap is the reason a
plugin cannot turn the bridge into a second agent loop: one call in flight, and a call is
answered or refused before the next one is read.
"""
from __future__ import annotations

import json
from typing import Any

#: The version marker on every envelope. A reply without it is not from this protocol.
BRIDGE_VERSION = 1

#: Bytes one bridge payload may carry, in either direction. The worker's own output cap
#: covers the tool's answer; this covers what travels *through* the pipe while it works.
MAX_BRIDGE_BYTES = 64 * 1024

#: Refusals the child can act on. They are codes, not sentences: the plugin's author reads
#: the code, the human reads the audit row, and neither gets a string from the host to parse.
METHOD_UNKNOWN = "bridge_method_unknown"
METHOD_DENIED = "bridge_method_denied"
ARGS_INVALID = "bridge_args_invalid"
PAYLOAD_TOO_LARGE = "bridge_payload_too_large"
RATE_LIMITED = "bridge_call_limit"
INTERNAL = "bridge_internal"

BRIDGE_CODES = (
    METHOD_UNKNOWN,
    METHOD_DENIED,
    ARGS_INVALID,
    PAYLOAD_TOO_LARGE,
    RATE_LIMITED,
    INTERNAL,
)


def encode_request(call_id: int, method: str, args: dict[str, Any]) -> str:
    """One request line, terminated so the host's reader can see it whole."""
    return json.dumps(
        {"bridge": BRIDGE_VERSION, "id": int(call_id), "method": str(method), "args": args},
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"


def encode_reply(call_id: int, result: Any) -> str:
    return json.dumps(
        {"bridge": BRIDGE_VERSION, "id": int(call_id), "ok": True, "result": result},
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"


def encode_refusal(call_id: int, code: str, detail: str = "") -> str:
    return json.dumps(
        {"bridge": BRIDGE_VERSION, "id": int(call_id), "ok": False, "code": str(code),
         "detail": str(detail)[:200]},
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"


def is_bridge_line(line: str) -> bool:
    """Whether stdout carries a bridge request rather than the tool's answer.

    Deliberately cheap and deliberately total: a line that is not JSON, or is JSON without
    the marker, is the result line and goes to the buffer the classifier reads. A malformed
    request never reaches the dispatcher, so a plugin cannot make the host parse something it
    did not send.
    """
    if not line or not line.strip():
        return False
    if '"bridge"' not in line:
        return False
    try:
        payload = json.loads(line)
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("bridge") == BRIDGE_VERSION


def parse_request(line: str) -> dict[str, Any] | None:
    """The request envelope, or None for anything that is not one."""
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("bridge") != BRIDGE_VERSION:
        return None
    method = payload.get("method")
    args = payload.get("args")
    call_id = payload.get("id")
    if not isinstance(method, str) or not isinstance(args, dict):
        return None
    if not isinstance(call_id, int):
        return None
    return {"id": call_id, "method": method, "args": args}


def parse_reply(line: str) -> dict[str, Any] | None:
    """The reply envelope the child reads back, or None for anything else on stdin."""
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("bridge") != BRIDGE_VERSION:
        return None
    if not isinstance(payload.get("id"), int):
        return None
    return payload


class BridgeError(Exception):
    """A refusal the child can name. The code is the contract; the text is for the log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
