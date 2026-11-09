"""Worker launcher: the confined child reads one request, imports the plugin, answers one line.

The child-side half of the #9 boundary. The backend never imports a plugin
module and never runs its callable; the child does, in a process the OS boundary
created. The launcher runs as `__main__` inside that child, so the plugin module is
a separate `sys.modules` entry there and nothing of it lands in the backend.

One JSON request arrives on stdin, one JSON response leaves on stdout:

    in  {"tool", "arguments", "state_dir", "entry_file", "callable"}
    out {"ok": true,  "result": <json>}
    out {"ok": false, "error":  "<class>"}

A tool that asks for the third argument may put bridge lines on stdout while it runs, and the
host answers each one on stdin before the next is read; the shape above is still the only
line the parent's classifier sees. See `core/sandbox/bridge_client.py` for what the child is
handed and why it cannot import it itself.

The error carries the exception class alone. A message or traceback can name a host
path, and the reply is surfaced to the model, so nothing that detailed crosses back.
"""
from __future__ import annotations

import importlib.util
import json
import sys


def _takes_bridge(handler) -> bool:
    """Whether one callable wants the third argument.

    Read off the signature rather than from a flag in the manifest: a tool that declares a
    parameter the host will not fill is a TypeError at the call, which is louder and earlier
    than a silent two-argument call that never gets an answer. `*args` counts as wanting it —
    a plugin that forwards its arguments onward should not be the one to miss the handle.
    """
    import inspect

    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return False
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD, parameter.VAR_POSITIONAL)
    ]
    return len(positional) >= 3


def _invoke(payload: dict) -> dict:
    entry_file = str(payload["entry_file"])
    callable_name = str(payload["callable"])
    arguments = payload.get("arguments") or {}
    state_dir = str(payload.get("state_dir") or "")
    spec = importlib.util.spec_from_file_location("plugin_entry", entry_file)
    if spec is None or spec.loader is None:
        raise ImportError("entry file could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules["plugin_entry"] = module
    spec.loader.exec_module(module)
    handler = getattr(module, callable_name)
    if _takes_bridge(handler):
        # The child cannot import host code — `import core` answers PermissionError behind
        # this boundary, measured — so the handle is handed in. `bridge_client` sits in the
        # launcher's own directory, which is the one piece of this repository the worker is
        # allowed to read, and it holds no capability: it writes a line and waits.
        from bridge_client import Bridge

        return {"ok": True, "result": handler(arguments, state_dir, Bridge())}
    return {"ok": True, "result": handler(arguments, state_dir)}


def main() -> int:
    request = sys.stdin.readline()
    if not request:
        response: dict = {"ok": False, "error": "empty request"}
    else:
        try:
            payload = json.loads(request)
            if not isinstance(payload, dict):
                raise TypeError("request must be an object")
            response = _invoke(payload)
        except SystemExit:
            raise  # a tool that exits for real is a nonzero process, kept distinct from a JSON error
        except BaseException as exc:  # noqa: BLE001 - only the class name leaves
            response = {"ok": False, "error": type(exc).__name__}
    try:
        line = json.dumps(response)
    except (TypeError, ValueError):
        line = json.dumps({"ok": False, "error": "unserializable result"})
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
