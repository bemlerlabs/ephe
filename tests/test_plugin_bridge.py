"""Tasks #23 and #25: the plugin bridge — a confined worker asks, the host decides.

Why a bridge exists at all is a measurement. Until `380bb9f0` a plugin worker could open a
socket to the host's own loopback port and read the API as itself: the request carried no
plugin id, no permission family was consulted and nothing tied the call to the mount that
made it. The boundary closed the socket. This is what replaces it — a capability crosses the
worker's own stdio pipes inside an envelope the host can attribute, and it is granted against
what the manifest declared rather than what the plugin asks for.

The unit half drives `bridge_host.dispatch` with a recorded handler and pins the order the
refusals arrive in. The end-to-end half runs a real confined child (Seatbelt on this machine,
the same rail #9 and #47 proved live) through `run_plugin_tool` and asserts what the child
could see, what it could not, and which row the audit log got.
"""
from __future__ import annotations

import io
import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.sandbox import bridge, bridge_client, bridge_host
from core.sandbox.runner import run_plugin_tool
from core.sandbox.supervisor import BoundedBuffer, run_worker
from core.sandbox.worker_spec import build_spec
from core.tools.dynamic_registry import ToolDescriptor, fingerprint_for, served_tool_name

def _search_module():
    """The module behind the kernel tool.

    `core.tools.web_search` is the function: the package binds that name over the
    submodule. The module object stays in `sys.modules`, which is what a patch and
    the host handler both have to reach.
    """
    import importlib

    return importlib.import_module("core.tools.web_search")


PLUGIN_ID = "acme-research"
#: A method the tests offer through the table, so the dispatcher is driven without a network.
ECHO_FAMILY = "network"


def _identity(**over) -> bridge_host.BridgeIdentity:
    fields = {
        "plugin_id": PLUGIN_ID,
        "tool": "scout",
        "family": ECHO_FAMILY,
        "families": frozenset({ECHO_FAMILY}),
        "fingerprint": "deadbeef",
    }
    fields.update(over)
    return bridge_host.BridgeIdentity(**fields)


def _request(**over) -> dict:
    fields = {"method": "echo", "args": {"value": "hello"}}
    fields.update(over)
    return fields


@pytest.fixture()
def rails(monkeypatch):
    """A bridge with one recorded method, and every audit row the dispatcher wrote."""
    calls: list[dict] = []
    rows: list[dict] = []

    def _echo(args: dict) -> dict:
        calls.append(dict(args))
        return {"ok": True, "result": {"echo": args.get("value", "")}}

    monkeypatch.setitem(
        bridge_host.METHODS,
        "echo",
        bridge_host.Method(
            name="echo", required_family=ECHO_FAMILY, handler=_echo, required_args=("value",)
        ),
    )
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )
    return SimpleNamespace(calls=calls, rows=rows)


def _dispatch(payload: dict, identity=None, state=None) -> dict:
    return bridge_host.dispatch(payload, identity or _identity(), state or bridge_host.RunState())


# the envelope


def test_the_three_shapes_are_the_whole_wire():
    request = json.loads(bridge.encode_request(3, "fetch", {"url": "https://example.com"}))
    assert request == {
        "bridge": bridge.BRIDGE_VERSION,
        "id": 3,
        "method": "fetch",
        "args": {"url": "https://example.com"},
    }
    assert bridge.encode_request(3, "fetch", {}).endswith("\n")
    assert bridge.encode_request(3, "fetch", {}).count("\n") == 1

    ok = json.loads(bridge.encode_reply(3, {"status": 200}))
    assert ok["ok"] is True and ok["result"] == {"status": 200} and ok["id"] == 3

    no = json.loads(bridge.encode_refusal(3, bridge.METHOD_DENIED, "nope"))
    assert no["ok"] is False and no["code"] == bridge.METHOD_DENIED and no["id"] == 3


def test_a_result_line_is_never_read_as_a_request():
    assert bridge.is_bridge_line('{"ok": true, "result": {"echo": "hi"}}') is False
    assert bridge.is_bridge_line("") is False
    assert bridge.is_bridge_line("   \n") is False
    assert bridge.is_bridge_line("this bridge is a footbridge, not JSON") is False
    assert bridge.is_bridge_line('{"bridge": 99, "id": 1, "method": "x", "args": {}}') is False
    assert bridge.is_bridge_line('["bridge"]') is False
    assert bridge.is_bridge_line(bridge.encode_request(1, "echo", {})) is True


def test_a_request_that_is_not_an_envelope_parses_to_nothing():
    for line in (
        "not json at all",
        "{}",
        '{"bridge": 1, "method": "echo", "args": {}}',         # no id
        '{"bridge": 1, "id": "1", "method": "echo", "args": {}}',  # id is not an int
        '{"bridge": 1, "id": 1, "args": {}}',                  # no method
        '{"bridge": 1, "id": 1, "method": 7, "args": {}}',     # method is not text
        '{"bridge": 1, "id": 1, "method": "echo", "args": []}',  # args is not an object
    ):
        assert bridge.parse_request(line) is None, line
    assert bridge.parse_request('{"bridge": 1, "id": 2, "method": "echo", "args": {}}') == {
        "id": 2, "method": "echo", "args": {}
    }
    typed = (
        '{"bridge": 1, "id": 2, "method": "echo", "args": {}, '
        '"plugin_id": "someone-else", "family": "shell", "fingerprint": "ffff"}'
    )
    assert bridge.parse_request(typed) == {"id": 2, "method": "echo", "args": {}}


# the decision order


def test_a_method_nobody_registered_is_refused_before_anything_runs(rails):
    answer = _dispatch(_request(method="read_the_host_disk"))
    assert answer["ok"] is False and answer["code"] == bridge.METHOD_UNKNOWN
    for name in bridge_host.METHODS:
        assert name in answer["detail"]
    assert rails.calls == []
    row = rails.rows[0]
    assert row["kind"] == "bridge_call" and row["decision"] == "denied"
    assert row["tool"] == f"{PLUGIN_ID}:scout" and "cause=unregistered" in row["detail"]


def test_a_family_the_manifest_did_not_ask_for_is_refused(rails):
    """The grant comes from the mount; a family named in the arguments changes nothing."""
    identity = _identity(families=frozenset({"read"}), family="read")
    answer = _dispatch(
        _request(args={"value": "hello", "family": "network", "plugin_id": "someone-else"}),
        identity,
    )
    assert answer["ok"] is False and answer["code"] == bridge.METHOD_DENIED
    assert rails.calls == [], "a refused family must never reach the handler"
    detail = rails.rows[0]["detail"]
    assert f"code={bridge.METHOD_DENIED}" in detail and "cause=undeclared-family" in detail
    assert "declared=read" in detail, "the row names what the bundle was actually given"


def test_a_required_argument_that_is_not_there_is_refused(rails):
    for args in ({}, {"value": ""}, {"value": "   "}, {"value": None}):
        answer = _dispatch(_request(args=args))
        assert answer["ok"] is False and answer["code"] == bridge.ARGS_INVALID, args
    assert rails.calls == []


def test_the_call_budget_is_per_run_and_answers_with_a_number(rails):
    state = bridge_host.RunState()
    codes = [_dispatch(_request(), state=state).get("code", "ok") for _ in range(
        bridge_host.MAX_CALLS_PER_RUN + 2
    )]
    assert codes[: bridge_host.MAX_CALLS_PER_RUN] == ["ok"] * bridge_host.MAX_CALLS_PER_RUN
    assert codes[-2:] == [bridge.RATE_LIMITED, bridge.RATE_LIMITED]
    assert len(rails.calls) == bridge_host.MAX_CALLS_PER_RUN
    last = _dispatch(_request(), state=state)
    assert str(bridge_host.MAX_CALLS_PER_RUN) in last["detail"]


def test_a_handler_that_raises_reaches_the_child_as_a_class_name(rails, monkeypatch):
    def _boom(args):
        raise ValueError("the token at /Users/example/engine.key did not work")

    monkeypatch.setitem(
        bridge_host.METHODS, "echo",
        bridge_host.Method(name="echo", required_family=ECHO_FAMILY, handler=_boom,
                           required_args=("value",)),
    )
    answer = _dispatch(_request())
    assert answer["ok"] is False and answer["code"] == bridge.INTERNAL
    assert answer["detail"] == "ValueError", answer["detail"]
    assert "/Users" not in json.dumps(answer)


def test_an_answer_too_big_for_the_pipe_is_refused(rails, monkeypatch):
    monkeypatch.setitem(
        bridge_host.METHODS, "echo",
        bridge_host.Method(
            name="echo", required_family=ECHO_FAMILY,
            handler=lambda args: {"ok": True, "result": {"blob": "A" * (bridge.MAX_BRIDGE_BYTES + 10)}},
            required_args=("value",),
        ),
    )
    answer = _dispatch(_request())
    assert answer["ok"] is False and answer["code"] == bridge.PAYLOAD_TOO_LARGE
    assert str(bridge.MAX_BRIDGE_BYTES) in answer["detail"]


def test_an_allowed_call_is_audited_with_the_host_alone(rails, monkeypatch):
    async def _fake_fetch(url: str, **kw):
        return 200, "<html><body>the page said hello</body></html>", ""

    monkeypatch.setattr("core.net_guard.guarded_fetch", _fake_fetch)
    answer = _dispatch(
        {"method": "fetch",
         "args": {"url": "https://example.com/reports/quarterly?token=super-secret-value"}}
    )
    assert answer["ok"] is True, answer
    assert "hello" in answer["result"]["text"]
    detail = rails.rows[-1]["detail"]
    assert "target=example.com" in detail and "granted=yes" in detail
    assert "family=network" in detail and "fingerprint=deadbeef" in detail
    assert "super-secret-value" not in detail and "quarterly" not in detail, detail


def test_a_refusal_from_the_guard_crosses_as_a_code_and_names_the_host(rails, monkeypatch):
    """The guard is the only way out, and a no from it is a code the child can act on.

    Replacing `guarded_fetch` is the proof of the path: nothing else in this dispatcher can
    reach a socket, so the answer the child gets here is the guard's own refusal, and the
    audit row still says which host was asked while the query, token and all, stays out.
    """
    asked: list[str] = []

    async def _refused(url: str, **kw):
        asked.append(url)
        return 0, "[refused] the address is not public", "loopback is not reachable from here"

    monkeypatch.setattr("core.net_guard.guarded_fetch", _refused)
    answer = _dispatch(
        {"method": "fetch", "args": {"url": "http://127.0.0.1:8111/api/health?token=abc123"}}
    )
    assert answer["ok"] is False and answer["code"] == bridge.METHOD_DENIED
    assert asked == ["http://127.0.0.1:8111/api/health?token=abc123"]
    detail = rails.rows[-1]["detail"]
    assert "target=127.0.0.1:8111" in detail, detail
    assert "cause=handler" in detail, "the guard answered, the grant table did not"
    assert "abc123" not in detail and "health" not in detail, detail


def test_a_transport_that_did_not_complete_is_not_a_refusal(rails, monkeypatch):
    async def _failed(url: str, **kw):
        return 0, "connection refused", "name resolution failed"

    monkeypatch.setattr("core.net_guard.guarded_fetch", _failed)
    answer = _dispatch({"method": "fetch", "args": {"url": "https://example.com"}})
    assert answer["ok"] is False and answer["code"] == bridge.INTERNAL


def test_a_long_page_is_cut_to_the_pipe_it_travelled_through(rails, monkeypatch):
    async def _big(url: str, **kw):
        return 200, "text " * 40_000, ""

    monkeypatch.setattr("core.net_guard.guarded_fetch", _big)
    answer = _dispatch({"method": "fetch", "args": {"url": "https://example.com/page"}})
    assert answer["ok"] is True, answer
    result = answer["result"]
    assert result["truncated"] is True
    assert len(result["text"]) < 200_000
    line = bridge.encode_reply(1, result)
    assert len(line.encode("utf-8")) <= bridge.MAX_BRIDGE_BYTES, "the reply must fit the pipe"


def test_search_runs_the_host_function_and_keeps_the_query_out_of_the_audit(rails, monkeypatch):
    """The worker has no socket, so the query is answered by the kernel function.

    The audit row names the method and leaves the target empty. A query can be the thing
    the reader was looking up, and the trail is exported, so the words stay in the answer
    the child asked for and out of the row.
    """
    seen: list[tuple] = []

    async def _yes(query: str, max_results: int = 5) -> str:
        seen.append((query, max_results))
        return "Providers: stub 200\n\n[1] Notes"

    monkeypatch.setattr(_search_module(), "web_search", _yes)
    answer = _dispatch(
        {"method": "search", "args": {"query": "library release notes", "max_results": 4}}
    )
    assert answer["ok"] is True, answer
    assert answer["result"]["text"] == "Providers: stub 200\n\n[1] Notes"
    assert seen == [("library release notes", 4)]
    detail = rails.rows[-1]["detail"]
    assert "method=search" in detail and "target=n/a" in detail and "granted=yes" in detail
    assert "library release notes" not in detail, detail


def test_memory_add_keeps_the_body_out_of_the_row(rails, monkeypatch):
    """The store runs on the host. The audit row names the method and carries no body."""
    seen: list[tuple] = []

    async def _store(action, target, content="", old_text="", memory_type="", supersedes=""):
        seen.append((action, target, content, memory_type))
        from core.reason import outcome

        return outcome("memory_stored", "[memory] stored (1 entries)", count="1")

    monkeypatch.setattr("core.tools.state_tools.memory", _store)
    answer = _dispatch(
        {
            "method": "memory_add",
            "args": {
                "target": "memory",
                "content": "body-must-stay-out",
                "memory_type": "procedural",
            },
        },
        identity=_identity(family="memory", families=frozenset({"memory"})),
    )
    assert answer["ok"] is True, answer
    assert answer["result"]["happened"] is True
    assert answer["result"]["code"] == "memory_stored"
    assert seen == [("add", "memory", "body-must-stay-out", "procedural")]
    row = json.dumps(rails.rows[-1])
    assert "method=memory_add" in rails.rows[-1]["detail"]
    assert "target=n/a" in rails.rows[-1]["detail"]
    assert "body-must-stay-out" not in row


def test_a_known_memory_action_cannot_ride_the_check_method(rails, monkeypatch):
    called: list[str] = []

    async def _no(*_args, **_kwargs):
        called.append("ran")
        return "should not run"

    monkeypatch.setattr("core.tools.state_tools.memory", _no)
    answer = _dispatch(
        {"method": "memory_action", "args": {"action": "add", "target": "memory", "content": "secret-body"}},
        identity=_identity(family="memory", families=frozenset({"memory"})),
    )
    assert answer["ok"] is False and answer["code"] == bridge.METHOD_DENIED
    assert called == []
    assert "secret-body" not in json.dumps(rails.rows)


def test_search_without_the_network_family_never_starts(rails, monkeypatch):
    called: list[str] = []

    async def _no(query: str, max_results: int = 5) -> str:
        called.append(query)
        return "should not run"

    monkeypatch.setattr(_search_module(), "web_search", _no)
    answer = _dispatch(
        {"method": "search", "args": {"query": "secret-query-token"}},
        identity=_identity(families=frozenset({"read"})),
    )
    assert answer["ok"] is False and answer["code"] == bridge.METHOD_DENIED
    assert called == []
    assert "secret-query-token" not in json.dumps(rails.rows)


def test_a_blank_search_is_refused_before_any_backend(rails, monkeypatch):
    called: list[str] = []

    async def _no(query: str, max_results: int = 5) -> str:
        called.append(query)
        return "should not run"

    monkeypatch.setattr(_search_module(), "web_search", _no)
    answer = _dispatch({"method": "search", "args": {"query": "   "}})
    assert answer["ok"] is False and answer["code"] == bridge.ARGS_INVALID
    assert called == []


def test_a_search_every_backend_refused_crosses_as_the_status_line(rails, monkeypatch):
    from core.tools.base import WebSearchError

    async def _refused(query: str, max_results: int = 5) -> str:
        raise WebSearchError("Providers: brave 403")

    monkeypatch.setattr(_search_module(), "web_search", _refused)
    answer = _dispatch({"method": "search", "args": {"query": "market report"}})
    assert answer["ok"] is False and answer["code"] == bridge.INTERNAL
    assert answer["detail"] == "Providers: brave 403", answer["detail"]
    assert "market report" not in json.dumps(rails.rows)


def test_fetch_url_returns_the_kernel_sentence_and_keeps_the_prompt_out_of_the_row(
    rails, monkeypatch
):
    """The page tool already writes the sentence. The bridge carries it back.

    `prompt` is on the call when the worker sent it, and it is absent from the
    audit row. The row names the host, the way a fetch row does.
    """
    seen: list[tuple] = []

    async def _page(url: str, prompt: str = "") -> str:
        seen.append((url, prompt))
        return f"PAGE {url}"

    monkeypatch.setattr("core.tools.fetch_tools.fetch_url", _page)
    answer = _dispatch(
        {
            "method": "fetch_url",
            "args": {
                "url": "https://example.com/docs",
                "prompt": "prompt-must-stay-out",
            },
        }
    )
    assert answer["ok"] is True, answer
    assert answer["result"]["text"] == "PAGE https://example.com/docs"
    assert seen == [("https://example.com/docs", "prompt-must-stay-out")]
    detail = rails.rows[-1]["detail"]
    assert "method=fetch_url" in detail and "target=example.com" in detail
    assert "prompt-must-stay-out" not in detail, detail


def test_a_blank_fetch_url_returns_the_kernel_sentence(rails):
    """An empty URL is the kernel tool's own sentence, so the method lets it through."""
    answer = _dispatch({"method": "fetch_url", "args": {"url": ""}})
    assert answer["ok"] is True, answer
    assert "The URL is empty." in answer["result"]["text"]


def test_search_returns_the_line_the_kernel_function_writes(rails, monkeypatch):
    """Patching the backend leaves the formatter, the reach line and the deadline in place.

    A second copy of that formatting in the bridge would drift the day the kernel tool
    changed its sentence, and the model reads one sentence from either caller.
    """
    def _hit(query: str, max_results: int, backend: str) -> list[dict]:
        assert max_results == 2
        return [{"title": "Notes", "href": "http://127.0.0.1/secret", "body": "local"}]

    monkeypatch.setattr(_search_module(), "_one_backend", _hit)
    answer = _dispatch({"method": "search", "args": {"query": "local notes", "max_results": "2"}})
    assert answer["ok"] is True, answer
    text = answer["result"]["text"]
    assert "Reach:" in text and "127.0.0.1" in text and "Providers:" in text
    assert "local notes" not in rails.rows[-1]["detail"]


def test_a_multibyte_page_is_cut_without_cutting_a_character(rails, monkeypatch):
    async def _umlaut(url: str, **kw):
        return 200, "Ä" * 40_000, ""

    monkeypatch.setattr("core.net_guard.guarded_fetch", _umlaut)
    answer = _dispatch({"method": "fetch", "args": {"url": "https://example.com/page"}})
    text = answer["result"]["text"]
    assert set(text) == {"Ä"} and len(text) < 40_000
    assert len(bridge.encode_reply(1, answer["result"]).encode("utf-8")) <= bridge.MAX_BRIDGE_BYTES


# the child handle


class _Out:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        self.lines.append(text)

    def flush(self) -> None:
        pass


class _In:
    def __init__(self, *lines: str) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        return self._lines.pop(0) if self._lines else ""


def test_the_client_writes_one_line_and_waits_for_its_answer():
    out, inp = _Out(), _In(bridge.encode_reply(1, {"echo": "hi"}))
    assert bridge_client.Bridge(out, inp).call("echo", value="hi") == {"echo": "hi"}
    assert json.loads(out.lines[0]) == {
        "bridge": 1, "id": 1, "method": "echo", "args": {"value": "hi"}
    }


def test_the_host_said_no_becomes_an_exception_with_the_code():
    handle = bridge_client.Bridge(
        _Out(), _In(bridge.encode_refusal(1, bridge.METHOD_DENIED, "family missing"))
    )
    with pytest.raises(bridge_client.BridgeError) as caught:
        handle.call("echo")
    assert caught.value.code == bridge.METHOD_DENIED
    assert "family missing" in str(caught.value)


def test_an_answer_for_a_different_request_is_a_protocol_fault():
    handle = bridge_client.Bridge(_Out(), _In(bridge.encode_reply(7, {"echo": "hi"})))
    with pytest.raises(bridge_client.BridgeError) as caught:
        handle.call("echo")
    assert caught.value.code == bridge.INTERNAL


def test_a_pipe_that_goes_quiet_or_speaks_garbage_is_reported_as_such():
    for line, expected in (
        ("", "the host closed the bridge mid-call"),
        ("not json\n", "a protocol this worker does not speak"),
        ('{"ok": true}\n', "a protocol this worker does not speak"),
    ):
        with pytest.raises(bridge_client.BridgeError) as caught:
            bridge_client.Bridge(_Out(), _In(line)).call("echo")
        assert caught.value.code == bridge.INTERNAL
        assert expected in caught.value.detail


def test_fetch_is_a_call_by_another_name():
    out = _Out()
    bridge_client.Bridge(out, _In(bridge.encode_reply(1, {"status": 200}))).fetch(
        "https://example.com"
    )
    sent = json.loads(out.lines[0])
    assert sent["method"] == "fetch" and sent["args"] == {"url": "https://example.com"}


def test_search_is_a_call_by_another_name():
    out = _Out()
    bridge_client.Bridge(out, _In(bridge.encode_reply(1, {"text": "hi"}))).search(
        "library release", max_results=2
    )
    sent = json.loads(out.lines[0])
    assert sent["method"] == "search"
    assert sent["args"] == {"query": "library release", "max_results": 2}

    bare = _Out()
    bridge_client.Bridge(bare, _In(bridge.encode_reply(1, {"text": "hi"}))).search("only query")
    sent = json.loads(bare.lines[0])
    assert sent["args"] == {"query": "only query"}


def test_fetch_url_is_a_call_by_another_name():
    out = _Out()
    bridge_client.Bridge(out, _In(bridge.encode_reply(1, {"text": "page"}))).fetch_url(
        "https://example.com/docs", prompt="answer this"
    )
    sent = json.loads(out.lines[0])
    assert sent["method"] == "fetch_url"
    assert sent["args"] == {"url": "https://example.com/docs", "prompt": "answer this"}

    bare = _Out()
    bridge_client.Bridge(bare, _In(bridge.encode_reply(1, {"text": "page"}))).fetch_url(
        "https://example.com/docs"
    )
    sent = json.loads(bare.lines[0])
    assert sent["args"] == {"url": "https://example.com/docs"}


def test_memory_add_leaves_an_omitted_body_off_the_wire():
    out = _Out()
    bridge_client.Bridge(out, _In(bridge.encode_reply(1, {"text": "stored"}))).memory_add(
        "memory", content="body-on-the-wire", memory_type="procedural"
    )
    sent = json.loads(out.lines[0])
    assert sent["method"] == "memory_add"
    assert sent["args"] == {
        "target": "memory", "content": "body-on-the-wire", "memory_type": "procedural",
    }

    bare = _Out()
    bridge_client.Bridge(bare, _In(bridge.encode_reply(1, {"text": "stored"}))).memory_add(
        "memory"
    )
    sent = json.loads(bare.lines[0])
    assert sent["args"] == {"target": "memory"}


def test_browser_exec_leaves_an_omitted_session_off_the_wire():
    out = _Out()
    bridge_client.Bridge(out, _In(bridge.encode_reply(1, {"text": "ran"}))).browser_exec(
        "print(1)", session="parity", timeout_s=30
    )
    sent = json.loads(out.lines[0])
    assert sent["method"] == "browser_exec"
    assert sent["args"] == {"code": "print(1)", "session": "parity", "timeout_s": 30}

    bare = _Out()
    bridge_client.Bridge(bare, _In(bridge.encode_reply(1, {"text": "ran"}))).browser_exec(
        "print(1)"
    )
    sent = json.loads(bare.lines[0])
    assert sent["args"] == {"code": "print(1)"}

    scrolled = _Out()
    bridge_client.Bridge(scrolled, _In(bridge.encode_reply(1, {"text": "moved"}))).browser_scroll()
    sent = json.loads(scrolled.lines[0])
    assert sent["method"] == "browser_scroll"
    assert sent["args"] == {}


def test_analyze_image_leaves_an_omitted_question_off_the_wire():
    out = _Out()
    bridge_client.Bridge(out, _In(bridge.encode_reply(1, {"text": "a door"}))).analyze_image(
        "/tmp/shot.png", question="what is this", region=[1, 2, 3, 4]
    )
    sent = json.loads(out.lines[0])
    assert sent["method"] == "analyze_image"
    assert sent["args"] == {
        "path": "/tmp/shot.png",
        "question": "what is this",
        "region": [1, 2, 3, 4],
    }

    bare = _Out()
    bridge_client.Bridge(bare, _In(bridge.encode_reply(1, {"text": "a door"}))).analyze_image(
        "/tmp/shot.png"
    )
    sent = json.loads(bare.lines[0])
    assert sent["method"] == "analyze_image"
    assert sent["args"] == {"path": "/tmp/shot.png"}


def test_vision_type_leaves_an_omitted_enter_off_the_wire():
    out = _Out()
    bridge_client.Bridge(out, _In(bridge.encode_reply(1, {"text": "typed"}))).vision_type(
        "hello", press_enter=True
    )
    sent = json.loads(out.lines[0])
    assert sent["method"] == "vision_type"
    assert sent["args"] == {"text": "hello", "press_enter": True}

    bare = _Out()
    bridge_client.Bridge(bare, _In(bridge.encode_reply(1, {"text": "typed"}))).vision_type(
        "hello"
    )
    sent = json.loads(bare.lines[0])
    assert sent["method"] == "vision_type"
    assert sent["args"] == {"text": "hello"}

    clicked = _Out()
    bridge_client.Bridge(
        clicked, _In(bridge.encode_reply(1, {"text": "clicked"}))
    ).vision_click("the save button")
    sent = json.loads(clicked.lines[0])
    assert sent["method"] == "vision_click"
    assert sent["args"] == {"target_description": "the save button"}


def test_the_codes_the_child_raises_are_the_codes_the_host_answers_with():
    """One vocabulary, checked from both ends so neither half can rename on its own."""
    for name in ("METHOD_UNKNOWN", "METHOD_DENIED", "ARGS_INVALID", "PAYLOAD_TOO_LARGE",
                 "RATE_LIMITED", "INTERNAL", "BRIDGE_VERSION"):
        assert getattr(bridge_client, name) == getattr(bridge, name), name


# the drain


class _Pipe:
    """The few bytes of a `Popen.stdin` the drain uses."""

    def __init__(self) -> None:
        self.writes: list[str] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.closed:
            raise ValueError("write on a closed pipe")
        self.writes.append(data.decode("utf-8"))

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _Proc:
    def __init__(self) -> None:
        self.stdin = _Pipe()


def _drain(text: str, dispatch):
    from core.sandbox.supervisor import _drain_with_bridge

    proc = _Proc()
    buffer = BoundedBuffer(4096)
    lock = threading.Lock()
    _drain_with_bridge(io.BytesIO(text.encode("utf-8")), buffer, proc, dispatch, lock)
    return proc, buffer


def test_a_request_past_the_byte_ceiling_is_answered_and_never_parsed():
    blob = "A" * (bridge.MAX_BRIDGE_BYTES + 4096)
    seen: list[dict] = []
    text = '{"bridge":1,"id":1,"method":"echo","args":{"blob":"' + blob + '"}}\n'
    proc, buffer = _drain(text, lambda payload: seen.append(payload) or {"ok": True, "result": 1})
    assert seen == [], "the dispatcher must not be handed a line the drain could not bound"
    assert any(bridge.PAYLOAD_TOO_LARGE in w for w in proc.stdin.writes), proc.stdin.writes
    assert '"blob"' in buffer.render(), "the tail stays in the buffer the classifier reads"


def test_the_bridge_shuts_when_the_answer_arrives():
    """The answer line closes stdin, so a tool that reads on gets the EOF the plain path gave."""
    proc, buffer = _drain('{"ok": true, "result": 1}\n', lambda p: {"ok": True})
    assert proc.stdin.closed is True
    assert '"result"' in buffer.render()


def test_a_request_the_parser_rejected_still_gets_an_answer():
    """Silence here would park the child on a read until the wall clock kills the run."""
    seen: list[dict] = []
    proc, _buffer = _drain('{"bridge":1,"oops":true}\n', lambda p: seen.append(p) or {"ok": True})
    assert seen == []
    assert any(bridge.ARGS_INVALID in w for w in proc.stdin.writes), proc.stdin.writes


# end to end, confined


BRIDGE_BODY = """
def run(arguments, state_dir, bridge):
    answer = bridge.call("echo", value=arguments.get("unit", ""))
    return {"echoed": answer.get("echo"), "state": bool(state_dir)}
"""

DENIED_BODY = """
def run(arguments, state_dir, bridge):
    try:
        bridge.call("echo", value="anything")
    except Exception as exc:
        return {"code": getattr(exc, "code", ""), "type": type(exc).__name__}
    return {"code": ""}
"""

PLAIN_BODY = """
def run(arguments, state_dir):
    return {"unit": arguments.get("unit", ""), "state": bool(state_dir)}
"""


def _descriptor(families: set[str], *, entry: str = "handlers:run") -> ToolDescriptor:
    name = served_tool_name(PLUGIN_ID, "scout")
    schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "A confined fixture tool.",
            "parameters": {"type": "object", "properties": {"unit": {"type": "string"}}},
        },
    }
    return ToolDescriptor(
        name=name, plugin_id=PLUGIN_ID, schema=schema, transport="plugin", entry=entry,
        tool_family=sorted(families)[0] if families else "read",
        families=frozenset(families), fingerprint=fingerprint_for(schema),
    )


def _plugin(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "plugin"
    root.mkdir(exist_ok=True)
    (root / "handlers.py").write_text(body, encoding="utf-8")
    return root


def _echo_handler(calls: list):
    def _echo(args: dict) -> dict:
        calls.append(dict(args))
        return {"ok": True, "result": {"echo": args.get("value", "").upper()}}

    return _echo


@pytest.fixture()
def echo_rail(monkeypatch):
    """The test method in the real table, its handler calls counted, audit rows collected."""
    calls: list[dict] = []
    rows: list[dict] = []
    monkeypatch.setitem(
        bridge_host.METHODS, "echo",
        bridge_host.Method(name="echo", required_family=ECHO_FAMILY,
                           handler=_echo_handler(calls), required_args=("value",)),
    )
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )
    return SimpleNamespace(calls=calls, rows=rows)


def _bridge_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["kind"] == "bridge_call"]


def test_a_confined_worker_searches_through_the_host(tmp_path, monkeypatch):
    """One real child asks for a search. The host function runs, and the query stays out of the row.

    The patch sits in this process, which is where the drain calls `web_search`. The child
    only writes the request line. A query that showed up in the audit row would have crossed
    a boundary the export of that row is not allowed to cross.
    """
    seen: list[tuple] = []

    async def _yes(query: str, max_results: int = 5) -> str:
        seen.append((query, max_results))
        return "one row"

    monkeypatch.setattr(_search_module(), "web_search", _yes)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )
    body = (
        "def run(arguments, state_dir, bridge):\n"
        "    page = bridge.search(arguments['query'], max_results=3)\n"
        "    return {'text': page['text']}\n"
    )
    root = _plugin(tmp_path, body)
    result = run_plugin_tool(
        _descriptor({ECHO_FAMILY}), {"query": "secret-query-token"}, root, timeout_seconds=30.0
    )
    assert result.status == "ok", result.text
    assert json.loads(result.text) == {"text": "one row"}
    assert seen == [("secret-query-token", 3)]
    detail = _bridge_rows(rows)[0]["detail"]
    assert "method=search" in detail and "secret-query-token" not in detail, detail


def test_the_shipped_research_bundle_asks_the_host_for_both_sentences(monkeypatch):
    """The handlers that ship are the ones the child runs.

    The patch sits in this process, where the drain calls the kernel tools. The
    child only writes the request. A query or a prompt in the audit row would
    have crossed a boundary the export of that row is not allowed to cross.
    """
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "web-research"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    by_name = {item.name: item for item in descriptors_for(manifest)}
    seen_search: list[tuple] = []
    seen_page: list[tuple] = []

    async def _yes(query: str, max_results: int = 5) -> str:
        seen_search.append((query, max_results))
        return "one row"

    async def _page(url: str, prompt: str = "") -> str:
        seen_page.append((url, prompt))
        return f"PAGE {url}"

    monkeypatch.setattr(_search_module(), "web_search", _yes)
    monkeypatch.setattr("core.tools.fetch_tools.fetch_url", _page)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    searched = run_plugin_tool(
        by_name["web_search"],
        {"query": "secret-query-token", "max_results": 3},
        root,
        timeout_seconds=30.0,
    )
    assert searched.status == "ok", searched.text
    assert searched.text == "one row"
    assert seen_search == [("secret-query-token", 3)]
    search_detail = _bridge_rows(rows)[-1]["detail"]
    assert "method=search" in search_detail and "secret-query-token" not in search_detail

    fetched = run_plugin_tool(
        by_name["fetch_url"],
        {"url": "https://example.com/docs", "prompt": "prompt-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert fetched.status == "ok", fetched.text
    assert fetched.text == "PAGE https://example.com/docs"
    assert seen_page == [("https://example.com/docs", "prompt-must-stay-out")]
    fetch_detail = _bridge_rows(rows)[-1]["detail"]
    assert "method=fetch_url" in fetch_detail and "target=example.com" in fetch_detail
    assert "prompt-must-stay-out" not in fetch_detail, fetch_detail


def test_the_shipped_memory_bundle_asks_the_host_and_keeps_the_body_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel tool. The child
    only writes the request. A memory body in the bridge row would have crossed a
    boundary the export of that row is not allowed to cross.
    """
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for
    from core.reason import outcome, reason

    root = Path(__file__).resolve().parents[1] / "plugins" / "memory"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    by_name = {item.name: item for item in descriptors_for(manifest)}
    seen: list[tuple] = []

    async def _store(action, target, content="", old_text="", memory_type="", supersedes=""):
        seen.append((action, content, memory_type, supersedes))
        if action == "add" and not str(content).strip():
            return reason("memory_add_needs_content", "[memory] add needs 'content'")
        return outcome("memory_stored", "[memory] stored (1 entries)", count="1")

    monkeypatch.setattr("core.tools.state_tools.memory", _store)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )
    stored = run_plugin_tool(
        by_name["memory"],
        {
            "action": "add",
            "target": "memory",
            "content": "body-must-stay-out",
            "memory_type": "procedural",
        },
        root,
        timeout_seconds=30.0,
    )
    assert stored.status == "ok", stored.text
    assert stored.text == "[memory] stored (1 entries)"
    assert getattr(stored.text, "happened", None) is True
    assert getattr(stored.text, "code", None) == "memory_stored"
    assert seen == [("add", "body-must-stay-out", "procedural", "")]
    detail = _bridge_rows(rows)[-1]["detail"]
    assert "method=memory_add" in detail and "body-must-stay-out" not in json.dumps(_bridge_rows(rows)[-1])

    empty = run_plugin_tool(
        by_name["memory"],
        {"action": "add", "target": "memory", "content": ""},
        root,
        timeout_seconds=30.0,
    )
    assert empty.text == "[memory] add needs 'content'"
    assert getattr(empty.text, "happened", None) is False
    assert getattr(empty.text, "code", None) == "memory_add_needs_content"


def test_the_shipped_browser_bundle_asks_the_host_and_keeps_the_action_out(monkeypatch):
    """The handlers that ship are the ones the child runs.

    The patch sits in this process, where the drain calls the kernel tools. The child
    only writes the request. Typed text, a script and a code block in the bridge row
    would have crossed a boundary the export of that row is not allowed to cross.
    A navigation row keeps the host.
    """
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "browser-use"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    by_name = {item.name: item for item in descriptors_for(manifest)}
    seen: dict[str, list] = {"go": [], "type": [], "exec": []}

    async def _go(url: str) -> str:
        seen["go"].append(url)
        return "arrived"

    async def _type(text: str) -> str:
        seen["type"].append(text)
        return "typed"

    async def _exec(code: str, session: str = "default", timeout_s: int = 120) -> str:
        seen["exec"].append((code, session, timeout_s))
        return "ran"

    monkeypatch.setattr("core.tools.browser_tools.browser_go", _go)
    monkeypatch.setattr("core.tools.browser_tools.browser_type", _type)
    monkeypatch.setattr("core.tools.browser_tools.browser_exec", _exec)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    opened = run_plugin_tool(
        by_name["browser_go"],
        {"url": "https://example.com/secret-path?token=stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert opened.status == "ok", opened.text
    assert opened.text == "arrived"
    assert seen["go"] == ["https://example.com/secret-path?token=stay-out"]
    go_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=browser_go" in go_row and "target=example.com" in go_row
    assert "secret-path" not in go_row and "stay-out" not in go_row

    typed = run_plugin_tool(
        by_name["browser_type"],
        {"text": "typed-text-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert typed.status == "ok", typed.text
    assert typed.text == "typed"
    assert seen["type"] == ["typed-text-must-stay-out"]
    type_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=browser_type" in type_row
    assert "typed-text-must-stay-out" not in type_row

    ran = run_plugin_tool(
        by_name["browser_exec"],
        {"code": "code-must-stay-out", "session": "parity-shared"},
        root,
        timeout_seconds=30.0,
    )
    assert ran.status == "ok", ran.text
    assert ran.text == "ran"
    assert seen["exec"] == [("code-must-stay-out", "parity-shared", 120)]
    exec_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=browser_exec" in exec_row
    assert "code-must-stay-out" not in exec_row and "parity-shared" not in exec_row


def _vision_bundle():
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "vision"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    return root, {item.name: item for item in descriptors_for(manifest)}


def test_the_shipped_vision_bundle_asks_the_host_and_keeps_the_action_out(monkeypatch):
    """The handlers that ship are the ones the child runs.

    The patch sits in this process, where the drain calls the kernel functions.
    The child only writes the request. A target description or a typed string in
    the bridge row would have crossed a boundary the export of that row is not
    allowed to cross.
    """
    root, by_name = _vision_bundle()
    seen: dict[str, list] = {"click": [], "type": []}

    async def _click(target_description: str) -> str:
        seen["click"].append(target_description)
        return "clicked"

    async def _type(text: str, press_enter: bool = False) -> str:
        seen["type"].append((text, press_enter))
        return "typed"

    monkeypatch.setattr("core.vision.vision_click", _click)
    monkeypatch.setattr("core.vision.vision_type", _type)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    clicked = run_plugin_tool(
        by_name["vision_click"],
        {"target_description": "Save-button-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert clicked.status == "ok", clicked.text
    assert clicked.text == "clicked"
    assert seen["click"] == ["Save-button-must-stay-out"]
    click_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=vision_click" in click_row
    assert "target=n/a" in click_row
    assert "Save-button-must-stay-out" not in click_row

    typed = run_plugin_tool(
        by_name["vision_type"],
        {"text": "typed-text-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert typed.status == "ok", typed.text
    assert typed.text == "typed"
    assert seen["type"] == [("typed-text-must-stay-out", False)]
    type_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=vision_type" in type_row
    assert "typed-text-must-stay-out" not in type_row

    entered = run_plugin_tool(
        by_name["vision_type"],
        {"text": "with-enter", "press_enter": True},
        root,
        timeout_seconds=30.0,
    )
    assert entered.status == "ok", entered.text
    assert seen["type"][-1] == ("with-enter", True)


def test_a_missing_desktop_callback_raises_through_the_worker(monkeypatch):
    """No callback is the kernel's own raise, including from the drain thread."""
    from core.vision import SandboxConfirmationRequired, check_sandbox

    root, by_name = _vision_bundle()

    async def _click(target_description: str) -> str:
        await check_sandbox("vision_click", {"target_description": target_description})
        return "clicked"

    monkeypatch.setattr("core.vision.vision_click", _click)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )
    with pytest.raises(SandboxConfirmationRequired) as excinfo:
        run_plugin_tool(
            by_name["vision_click"],
            {"target_description": "Save-button-must-stay-out"},
            root,
            timeout_seconds=30.0,
        )
    assert excinfo.value.tool_name == "vision_click"
    click_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=vision_click" in click_row
    assert "Save-button-must-stay-out" not in click_row


def test_execute_tool_surfaces_a_missing_desktop_callback(monkeypatch):
    """The turn's execute path raises the kernel's own confirmation.

    The worker runs on another thread so the chat loop can keep serving the
    dialog. That hop still has to deliver the raise, and the description stays
    out of the message the caller reads.
    """
    import asyncio

    from core.tools.registry import execute_tool
    from core.vision import SandboxConfirmationRequired, check_sandbox

    async def _click(target_description: str) -> str:
        await check_sandbox("vision_click", {"target_description": target_description})
        return "clicked"

    monkeypatch.setattr("core.vision.vision_click", _click)

    async def _run():
        await execute_tool(
            "vision_click", {"target_description": "Save-button-must-stay-out"}
        )

    with pytest.raises(SandboxConfirmationRequired) as excinfo:
        asyncio.run(_run())
    assert excinfo.value.tool_name == "vision_click"
    assert "Save-button-must-stay-out" not in str(excinfo.value)


def test_a_refused_desktop_call_keeps_the_abort_sentence(monkeypatch):
    """A no from the callback is the sentence the kernel already writes."""
    from core.vision import check_sandbox, set_sandbox_confirm_cb

    root, by_name = _vision_bundle()

    async def _click(target_description: str) -> str:
        await check_sandbox("vision_click", {"target_description": target_description})
        return "clicked"

    async def _deny(name: str, args: dict) -> bool:
        return False

    monkeypatch.setattr("core.vision.vision_click", _click)
    set_sandbox_confirm_cb(_deny)
    try:
        refused = run_plugin_tool(
            by_name["vision_click"],
            {"target_description": "Save-button-must-stay-out"},
            root,
            timeout_seconds=30.0,
        )
    finally:
        set_sandbox_confirm_cb(None)
    assert refused.text == (
        "[tool-error 'vision_click': Action aborted by User Intervention]"
    )
    assert "Save-button-must-stay-out" not in refused.text


def test_the_desktop_callback_runs_on_the_caller_loop(monkeypatch):
    """The callback is awaited on the loop that published it.

    A private loop in the drain thread would leave a dialog waiting on the
    chat loop with nobody to answer it.
    """
    import asyncio

    from core.vision import check_sandbox, set_sandbox_confirm_cb

    root, by_name = _vision_bundle()
    seen: dict[str, object] = {}

    async def _click(target_description: str) -> str:
        await check_sandbox("vision_click", {"target_description": target_description})
        seen["target"] = target_description
        return "clicked"

    async def _approve(name: str, args: dict) -> bool:
        seen["loop"] = asyncio.get_running_loop()
        seen["name"] = name
        seen["target_arg"] = args["target_description"]
        return True

    monkeypatch.setattr("core.vision.vision_click", _click)

    async def _main():
        loop = asyncio.get_running_loop()
        seen["caller"] = loop
        token = bridge_host.bind_caller_loop(loop)
        set_sandbox_confirm_cb(_approve)
        try:
            return await asyncio.to_thread(
                run_plugin_tool,
                by_name["vision_click"],
                {"target_description": "Save-button-must-stay-out"},
                root,
                timeout_seconds=30.0,
            )
        finally:
            bridge_host.reset_caller_loop(token)
            set_sandbox_confirm_cb(None)

    result = asyncio.run(_main())
    assert result.status == "ok", result.text
    assert result.text == "clicked"
    assert seen["loop"] is seen["caller"]
    assert seen["name"] == "vision_click"
    assert seen["target"] == "Save-button-must-stay-out"
    assert seen["target_arg"] == "Save-button-must-stay-out"


def test_the_shipped_image_read_asks_the_host_and_keeps_the_path_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel function.
    A path or a question in the bridge row would have crossed a boundary the
    export of that row is not allowed to cross.
    """
    root, by_name = _vision_bundle()
    seen: dict[str, list] = {"calls": []}

    async def _read(path: str, question: str = "Describe this image in detail.", region=None):
        seen["calls"].append((path, question, region))
        return "a red door"

    monkeypatch.setattr("core.tools.system_tools.analyze_image", _read)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    plain = run_plugin_tool(
        by_name["analyze_image"],
        {"path": "/tmp/shot-must-stay-out.png"},
        root,
        timeout_seconds=30.0,
    )
    assert plain.status == "ok", plain.text
    assert plain.text == "a red door"
    assert seen["calls"] == [
        ("/tmp/shot-must-stay-out.png", "Describe this image in detail.", None)
    ]
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=analyze_image" in row
    assert "target=n/a" in row
    assert "shot-must-stay-out" not in row
    assert "Describe this image" not in row

    asked = run_plugin_tool(
        by_name["analyze_image"],
        {
            "path": "/tmp/shot-must-stay-out.png",
            "question": "question-must-stay-out",
            "region": [0, 0, 8, 8],
        },
        root,
        timeout_seconds=30.0,
    )
    assert asked.status == "ok", asked.text
    assert seen["calls"][-1] == (
        "/tmp/shot-must-stay-out.png",
        "question-must-stay-out",
        [0, 0, 8, 8],
    )
    asked_row = json.dumps(_bridge_rows(rows)[-1])
    assert "question-must-stay-out" not in asked_row
    assert "shot-must-stay-out" not in asked_row


def test_a_refused_image_path_keeps_the_kernel_sentence(monkeypatch):
    """A path the kernel refuses comes back as the sentence it already raises."""
    root, by_name = _vision_bundle()
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )
    refused = run_plugin_tool(
        by_name["analyze_image"],
        {"path": "/no/such/image-must-stay-out.png", "question": "question-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert refused.status == "ok", refused.text
    assert refused.text.startswith("[tool-error 'analyze_image': ")
    assert "image-must-stay-out.png" in refused.text
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=analyze_image" in row
    assert "target=n/a" in row
    assert "image-must-stay-out" not in row
    assert "question-must-stay-out" not in row


def _code_shell_bundle():
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "code-shell"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    return root, {item.name: item for item in descriptors_for(manifest)}


def test_the_shipped_shell_asks_the_host_and_keeps_the_command_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel function.
    A command in the bridge row would have crossed a boundary the export of
    that row is not allowed to cross.
    """
    root, by_name = _code_shell_bundle()
    seen: dict[str, list] = {"calls": []}

    async def _shell(command: str, run_in_background: bool = False, cwd: str | None = None) -> str:
        seen["calls"].append((command, run_in_background, cwd))
        return "ran"

    monkeypatch.setattr("core.tools._shell_exec.run_shell", _shell)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    plain = run_plugin_tool(
        by_name["run_shell"],
        {"command": "command-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert plain.status == "ok", plain.text
    assert plain.text == "ran"
    assert seen["calls"] == [("command-must-stay-out", False, None)]
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=run_shell" in row
    assert "target=n/a" in row
    assert "command-must-stay-out" not in row

    asked = run_plugin_tool(
        by_name["run_shell"],
        {"command": "command-must-stay-out", "cwd": "cwd-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert asked.status == "ok", asked.text
    assert seen["calls"][-1] == ("command-must-stay-out", False, "cwd-must-stay-out")
    asked_row = json.dumps(_bridge_rows(rows)[-1])
    assert "command-must-stay-out" not in asked_row
    assert "cwd-must-stay-out" not in asked_row


def _documents_bundle():
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "documents"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    return root, {item.name: item for item in descriptors_for(manifest)}


def test_the_shipped_document_asks_the_host_and_keeps_the_body_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel function.
    A body in the bridge row would have crossed a boundary the export of
    that row is not allowed to cross.
    """
    root, by_name = _documents_bundle()
    seen: dict[str, list] = {"calls": []}

    async def _pdf(
        title: str,
        content: str,
        filename: str = "ephe_dokument.pdf",
        template: str = "report",
        document: bool = False,
    ) -> str:
        seen["calls"].append({
            "title": title,
            "content": content,
            "filename": filename,
            "template": template,
            "document": document,
        })
        return "PDF_FILE:out.pdf"

    monkeypatch.setattr("core.tools.pdf_tools.create_pdf", _pdf)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    plain = run_plugin_tool(
        by_name["create_pdf"],
        {"title": "Q3 brief", "content": "body-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert plain.status == "ok", plain.text
    assert plain.text == "PDF_FILE:out.pdf"
    assert seen["calls"] == [{
        "title": "Q3 brief",
        "content": "body-must-stay-out",
        "filename": "ephe_dokument.pdf",
        "template": "report",
        "document": False,
    }]
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=create_pdf" in row
    assert "target=n/a" in row
    assert "body-must-stay-out" not in row
    assert "Q3 brief" not in row

    asked = run_plugin_tool(
        by_name["create_pdf"],
        {
            "title": "Q3 brief",
            "content": "body-must-stay-out",
            "document": True,
            "filename": "path-must-stay-out.pdf",
        },
        root,
        timeout_seconds=30.0,
    )
    assert asked.status == "ok", asked.text
    assert seen["calls"][-1]["document"] is True
    assert seen["calls"][-1]["filename"] == "path-must-stay-out.pdf"
    asked_row = json.dumps(_bridge_rows(rows)[-1])
    assert "body-must-stay-out" not in asked_row
    assert "path-must-stay-out" not in asked_row


def _spreadsheets_bundle():
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "spreadsheets"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    return root, {item.name: item for item in descriptors_for(manifest)}


def test_the_shipped_sheet_asks_the_host_and_keeps_the_rows_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel function.
    A row in the bridge row would have crossed a boundary the export of
    that row is not allowed to cross.
    """
    root, by_name = _spreadsheets_bundle()
    seen: dict[str, list] = {"calls": []}

    async def _xlsx(title, data, filename="ephe_tabelle.xlsx", path=None, formats=None):
        seen["calls"].append({
            "title": title,
            "data": data,
            "filename": filename,
            "path": path,
            "formats": formats,
        })
        return "XLSX_FILE:out.xlsx"

    monkeypatch.setattr("core.tools.office_tools.create_xlsx", _xlsx)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    plain = run_plugin_tool(
        by_name["create_xlsx"],
        {"title": "Expenses", "data": [["Item", "Amount"], ["Rent", "row-must-stay-out"], ["Total", "=SUM(B2:B2)"]]},
        root,
        timeout_seconds=30.0,
    )
    assert plain.status == "ok", plain.text
    assert plain.text == "XLSX_FILE:out.xlsx"
    assert seen["calls"] == [{
        "title": "Expenses",
        "data": [["Item", "Amount"], ["Rent", "row-must-stay-out"], ["Total", "=SUM(B2:B2)"]],
        "filename": "ephe_tabelle.xlsx",
        "path": None,
        "formats": None,
    }]
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=create_xlsx" in row
    assert "target=n/a" in row
    assert "row-must-stay-out" not in row
    assert "=SUM(B2:B2)" not in row

    asked = run_plugin_tool(
        by_name["create_xlsx"],
        {
            "title": "Expenses",
            "data": [["Item"], ["row-must-stay-out"]],
            "path": "path-must-stay-out",
            "formats": {"Amount": "currency"},
        },
        root,
        timeout_seconds=30.0,
    )
    assert asked.status == "ok", asked.text
    assert seen["calls"][-1]["path"] == "path-must-stay-out"
    assert seen["calls"][-1]["formats"] == {"Amount": "currency"}
    asked_row = json.dumps(_bridge_rows(rows)[-1])
    assert "row-must-stay-out" not in asked_row
    assert "path-must-stay-out" not in asked_row


def _presentations_bundle():
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "presentations"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    return root, {item.name: item for item in descriptors_for(manifest)}


def test_the_shipped_deck_asks_the_host_and_keeps_the_slides_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel function.
    A slide, a note and a path in the bridge row would have crossed the export.
    """
    root, by_name = _presentations_bundle()
    seen: dict[str, list] = {"deck": [], "svg": []}

    async def _deck(topic, **kwargs):
        seen["deck"].append({"topic": topic, **kwargs})
        return "PPTX_DECK_FILE:out.pptx"

    async def _svg(svg_code, filename="ephe_grafik.svg"):
        seen["svg"].append({"svg_code": svg_code, "filename": filename})
        return "SVG_FILE:out.svg"

    monkeypatch.setattr("core.tools.deck_tools.create_pptx_deck", _deck)
    monkeypatch.setattr("core.tools.system_tools.create_svg", _svg)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    slides = [{
        "title": "Q3 review",
        "claim": "slide-must-stay-out",
        "speaker_note": "note-must-stay-out",
    }]
    plain = run_plugin_tool(
        by_name["create_pptx_deck"],
        {"topic": "Q3 review", "slides": slides},
        root,
        timeout_seconds=30.0,
    )
    assert plain.status == "ok", plain.text
    assert plain.text == "PPTX_DECK_FILE:out.pptx"
    assert seen["deck"] == [{"topic": "Q3 review", "slides": slides}]
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=create_pptx_deck" in row
    assert "target=n/a" in row
    assert "slide-must-stay-out" not in row
    assert "note-must-stay-out" not in row

    asked = run_plugin_tool(
        by_name["create_pptx_deck"],
        {
            "topic": "Q3 review",
            "slides": slides,
            "template_path": "path-must-stay-out",
            "enterprise_grade": False,
        },
        root,
        timeout_seconds=30.0,
    )
    assert asked.status == "ok", asked.text
    assert seen["deck"][-1]["template_path"] == "path-must-stay-out"
    assert seen["deck"][-1]["enterprise_grade"] is False
    asked_row = json.dumps(_bridge_rows(rows)[-1])
    assert "slide-must-stay-out" not in asked_row
    assert "path-must-stay-out" not in asked_row

    drawn = run_plugin_tool(
        by_name["create_svg"],
        {"svg_code": "drawing-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert drawn.status == "ok", drawn.text
    assert seen["svg"] == [{"svg_code": "drawing-must-stay-out", "filename": "ephe_grafik.svg"}]
    drawn_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=create_svg" in drawn_row
    assert "drawing-must-stay-out" not in drawn_row


def _image_studio_bundle():
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "image-studio"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    return root, {item.name: item for item in descriptors_for(manifest)}


def test_the_shipped_picture_asks_the_host_and_keeps_the_prompt_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel function.
    A prompt in the bridge row would have crossed the export.
    """
    from core.sandbox.runner import RunResult, execute

    root, by_name = _image_studio_bundle()
    seen: list[dict] = []

    async def _picture(prompt, **kwargs):
        seen.append({"prompt": prompt, **kwargs})
        return "PNG_FILE:out.png"

    monkeypatch.setattr("core.tools.image_tools.generate_image", _picture)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    plain = run_plugin_tool(
        by_name["generate_image"],
        {"prompt": "prompt-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert plain.status == "ok", plain.text
    assert plain.text == "PNG_FILE:out.png"
    assert seen == [{"prompt": "prompt-must-stay-out"}]
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=generate_image" in row
    assert "target=n/a" in row
    assert "prompt-must-stay-out" not in row

    asked = run_plugin_tool(
        by_name["generate_image"],
        {
            "prompt": "prompt-must-stay-out",
            "filename": "name-must-stay-out.png",
            "size": "512x512",
        },
        root,
        timeout_seconds=30.0,
    )
    assert asked.status == "ok", asked.text
    assert seen[-1]["filename"] == "name-must-stay-out.png"
    assert seen[-1]["size"] == "512x512"
    asked_row = json.dumps(_bridge_rows(rows)[-1])
    assert "prompt-must-stay-out" not in asked_row
    assert "name-must-stay-out" not in asked_row

    blank = run_plugin_tool(
        by_name["generate_image"],
        {},
        root,
        timeout_seconds=30.0,
    )
    assert blank.status == "ok", blank.text
    assert seen[-1]["prompt"] == ""
    assert "filename" not in seen[-1]
    assert "size" not in seen[-1]

    captured: dict[str, float] = {}

    def _capture(descriptor, arguments, plugin_dir, timeout_seconds=20.0, budget=None):
        captured["timeout"] = timeout_seconds
        return RunResult("ok", "answer", "PNG_FILE:out.png")

    monkeypatch.setattr("core.sandbox.runner.run_plugin_tool", _capture)
    text = execute(by_name["generate_image"], {"prompt": "orb"})
    assert text == "PNG_FILE:out.png"
    assert captured["timeout"] == bridge_host.picture_call_timeout_seconds()
    assert captured["timeout"] == 220.0


def _voice_bundle():
    from core.plugin_manifest import load_manifest
    from core.plugin_tools_contract import descriptors_for

    root = Path(__file__).resolve().parents[1] / "plugins" / "voice"
    manifest, error = load_manifest(root)
    assert error is None and manifest is not None
    return root, {item.name: item for item in descriptors_for(manifest)}


def test_the_shipped_voice_asks_the_host_and_keeps_the_speech_out(monkeypatch):
    """The handler that ships is the one the child runs.

    The patch sits in this process, where the drain calls the kernel function.
    Spoken text or a transcript in the bridge row would have crossed the export.
    """
    from core.sandbox.runner import RunResult, execute

    root, by_name = _voice_bundle()
    seen: list[str] = []

    def _speak(text: str) -> str:
        seen.append(text)
        return "WAV_FILE:out.wav"

    monkeypatch.setattr("core.voice_synth.synthesize_local", _speak)
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )

    plain = run_plugin_tool(
        by_name["synthesize"],
        {"text": "speech-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert plain.status == "ok", plain.text
    assert plain.text == "WAV_FILE:out.wav"
    assert seen == ["speech-must-stay-out"]
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=synthesize" in row
    assert "target=n/a" in row
    assert "speech-must-stay-out" not in row

    def _hear(name: str) -> str:
        seen.append(name)
        return "heard-must-stay-out"

    monkeypatch.setattr("core.voice_synth.transcribe_file", _hear)
    heard = run_plugin_tool(
        by_name["transcribe"],
        {"name": "clip.wav"},
        root,
        timeout_seconds=30.0,
    )
    assert heard.status == "ok", heard.text
    assert heard.text == "heard-must-stay-out"
    assert seen[-1] == "clip.wav"
    heard_row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=transcribe" in heard_row
    assert "heard-must-stay-out" not in heard_row
    assert "clip.wav" not in heard_row

    captured: dict[str, float] = {}

    def _capture(descriptor, arguments, plugin_dir, timeout_seconds=20.0, budget=None):
        captured["timeout"] = timeout_seconds
        return RunResult("ok", "answer", "WAV_FILE:out.wav")

    monkeypatch.setattr("core.sandbox.runner.run_plugin_tool", _capture)
    text = execute(by_name["synthesize"], {"text": "orb"})
    assert text == "WAV_FILE:out.wav"
    assert captured["timeout"] == bridge_host.voice_call_timeout_seconds()
    assert captured["timeout"] == 110.0


def test_list_directory_joins_the_names(monkeypatch):
    root, by_name = _code_shell_bundle()

    async def _list(path: str) -> list[str]:
        assert path == "/tmp/dir-must-stay-out"
        return ["a.txt", "b.txt"]

    monkeypatch.setattr("core.tools.file_ops.list_directory", _list)
    listed = run_plugin_tool(
        by_name["list_directory"],
        {"path": "/tmp/dir-must-stay-out"},
        root,
        timeout_seconds=30.0,
    )
    assert listed.status == "ok", listed.text
    assert listed.text == "a.txt\nb.txt"


def test_a_refused_file_path_keeps_the_kernel_sentence(monkeypatch):
    """A path the kernel refuses comes back as the sentence it already raises."""
    root, by_name = _code_shell_bundle()
    rows: list[dict] = []
    monkeypatch.setattr(
        "core.audit_log.audit_event", lambda kind, **kw: rows.append({"kind": kind, **kw})
    )
    refused = run_plugin_tool(
        by_name["read_file"],
        {"path": "/no/such/file-must-stay-out.txt"},
        root,
        timeout_seconds=30.0,
    )
    assert refused.status == "ok", refused.text
    assert refused.text.startswith("[tool-error 'read_file': ")
    assert "file-must-stay-out.txt" in refused.text
    row = json.dumps(_bridge_rows(rows)[-1])
    assert "method=read_file" in row
    assert "target=n/a" in row
    assert "file-must-stay-out" not in row


def test_a_confined_worker_reaches_the_host_only_through_its_pipes(tmp_path, echo_rail):
    """One real Seatbelt child, one request line out, one answer line back, one result read.

    The status is the proof of the separation: the drain never fed a bridge line to the
    classifier, so `run_plugin_tool` still reads its answer as a single JSON object. A leaked
    request line in that buffer would answer `protocol_error`.
    """
    root = _plugin(tmp_path, BRIDGE_BODY)
    result = run_plugin_tool(
        _descriptor({ECHO_FAMILY}), {"unit": "hello"}, root, timeout_seconds=30.0
    )
    assert result.status == "ok", result.text
    assert json.loads(result.text) == {"echoed": "HELLO", "state": True}
    assert echo_rail.calls == [{"value": "hello"}]
    row = _bridge_rows(echo_rail.rows)[0]
    assert row["decision"] == "allowed" and row["tool"] == f"{PLUGIN_ID}:scout"
    assert row["status"] == "ok"


def test_a_confined_worker_with_a_memory_cap_still_finds_its_bridge(tmp_path, echo_rail):
    """The capped form starts through a bootstrap, and that form has to reach the same pipes."""
    root = _plugin(tmp_path, BRIDGE_BODY)
    result = run_plugin_tool(
        _descriptor({ECHO_FAMILY}), {"unit": "capped"}, root,
        timeout_seconds=30.0, memory_cap_mb=1024,
    )
    assert result.status == "ok", result.text
    assert json.loads(result.text)["echoed"] == "CAPPED"


def test_a_family_the_bundle_never_declared_denies_the_worker_too(tmp_path, echo_rail):
    """The same child, the same call, a manifest that did not ask for the family."""
    root = _plugin(tmp_path, DENIED_BODY)
    result = run_plugin_tool(
        _descriptor({"read"}), {"unit": "hello"}, root, timeout_seconds=30.0
    )
    assert result.status == "ok", result.text
    payload = json.loads(result.text)
    assert payload == {"code": bridge.METHOD_DENIED, "type": "BridgeError"}
    assert echo_rail.calls == [], "the capability was granted to nobody"
    row = _bridge_rows(echo_rail.rows)[0]
    assert row["decision"] == "denied" and "declared=read" in row["detail"]
    assert "cause=undeclared-family" in row["detail"]


def test_a_tool_that_never_asks_sees_the_stream_it_always_saw(tmp_path, echo_rail):
    """No bridge line, no call, and the answer is still exactly one JSON object."""
    root = _plugin(tmp_path, PLAIN_BODY)
    result = run_plugin_tool(_descriptor({"read"}), {"unit": "x"}, root, timeout_seconds=30.0)
    assert result.status == "ok", result.text
    assert json.loads(result.text) == {"unit": "x", "state": True}
    assert _bridge_rows(echo_rail.rows) == []


def test_a_handle_the_tool_never_uses_changes_nothing(tmp_path):
    """A three-argument callable that never calls the bridge runs the plain run.

    Nothing is written to its stdin beyond the request, and nothing waits for a reply that
    will not come: the drain ends on the answer line the launcher writes, the same line a
    tool without a handle would write. The classification is the statement — a held pipe
    would answer `timeout` against the spec's 30 s.
    """
    body = (
        "def run(arguments, state_dir, bridge):\n"
        "    return {'ok': True}\n"
    )
    root = _plugin(tmp_path, body)
    result = run_plugin_tool(_descriptor({ECHO_FAMILY}), {}, root, timeout_seconds=30.0)
    assert result.status == "ok", result.text


def test_a_malformed_request_from_a_real_child_is_answered(tmp_path):
    """A child writes bytes that look like a request, and the host answers with a code."""
    from core import mcp_sandbox

    if mcp_sandbox.platform_boundary() == "unavailable":
        pytest.skip("no OS boundary on this machine — the confined child cannot start")
    entry = tmp_path / "plugin"
    entry.mkdir()
    script = entry / "tool.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdin.readline()\n"
        'sys.stdout.write(\'{"bridge": 1, "oops": true}\\n\')\n'
        "sys.stdout.flush()\n"
        "reply = sys.stdin.readline()\n"
        "sys.stdout.write(json.dumps({'ok': True, 'result': json.loads(reply)}) + '\\n')\n",
        encoding="utf-8",
    )
    spec, error = build_spec(plugin_id="w23", plugin_dir=entry, entry="tool.py",
                             timeout_seconds=30.0)
    assert error == "", error
    seen: list[dict] = []
    outcome = run_worker(
        spec,
        protocol_check=lambda text: text.startswith("{"),
        stdin_payload="{}\n",
        bridge_dispatch=lambda payload: seen.append(payload) or {"ok": True, "result": 1},
    )
    assert outcome.status == "ok", outcome.note + outcome.stdout
    assert seen == [], "a line the parser cannot read is refused before any dispatcher sees it"
    reply = json.loads(outcome.stdout)
    assert reply["result"]["code"] == bridge.ARGS_INVALID


# what the author reads


def test_the_sdk_documentation_carries_the_table_the_dispatcher_has():
    """A code, a budget or a ceiling that lives in only one of the two files is a defect.

    The plugin author reads `docs/PLUGIN_SDK.md` and the child reads these modules, so the
    document is opened here and compared against the code. A rename on either side fails in
    this test rather than in somebody else's bundle.
    """
    doc = (
        Path(__file__).resolve().parents[1] / "docs" / "PLUGIN_SDK.md"
    ).read_text(encoding="utf-8")
    section = doc.split("### 3a.")[1].split("## 4.")[0]
    listed = re.findall(r"^\| `(bridge_[a-z_]+)` \|", section, re.MULTILINE)
    assert set(listed) == set(bridge.BRIDGE_CODES), listed
    assert len(listed) == len(bridge.BRIDGE_CODES), "a code documented twice is a stale row"
    assert "`bridge_call`" in section, "the audit row the host writes is named for the reader"
    assert str(bridge_host.MAX_CALLS_PER_RUN) in section
    assert "64 KiB" in section and bridge.MAX_BRIDGE_BYTES == 64 * 1024
    assert "`fetch(url)`" in section and "`search(query" in section
    assert "`fetch_url(url" in section
    assert "`memory_add`" in section and "`memory_action(action" in section
    assert "`browser_go(url)`" in section and "`browser_exec(code" in section
    assert "`vision_click(target_description)`" in section
    assert "`vision_type(text, press_enter=None)`" in section
    assert "`analyze_image(path" in section
    assert "The path and the question stay out of the row" in section
    assert "`run_shell(command" in section
    assert "`read_file(path" in section
    assert "`scaffold_project(target_dir" in section
    assert "The command, the path and the file body stay out of the row" in section
    assert "`create_pdf(title" in section
    assert "`create_docx(title" in section
    assert "`verify_artifact(path" in section
    assert "The body, the path and the source text stay out of the row" in section
    assert "`create_xlsx(title" in section
    assert "`generate_chart(chart_type" in section
    assert "The rows, the labels and the path stay out of the row" in section
    assert "`create_pptx_deck(topic" in section
    assert "`create_pitch_deck(topic" in section
    assert "`qa_pptx_deck(pptx_path" in section
    assert "`create_svg(svg_code" in section
    assert "The slide text, the notes and the path stay out of the row" in section
    assert "`generate_image(prompt" in section
    assert "The prompt stays out of the row" in section
    assert "`synthesize(text" in section
    assert "`transcribe(name" in section
    assert "The spoken text and the transcript stay out of the row" in section
    assert "no entry body" in section
    assert "Typed text, a script and a code block stay out of the row" in section
    assert "The target description and the typed text stay out of the row" in section
    assert set(bridge_host.METHODS) == {
        "fetch", "search", "fetch_url",
        "memory_add", "memory_replace", "memory_remove", "memory_list", "memory_action",
        "browser_go", "browser_screenshot", "browser_click", "browser_type",
        "browser_press", "browser_scroll", "browser_evaluate", "browser_exec",
        "vision_click", "vision_type", "analyze_image",
        "run_shell", "read_file", "write_file", "edit_file", "list_directory",
        "file_search", "load_workspace", "analyze_project", "run_tests",
        "run_linter", "format_code", "scaffold_project",
        "create_pdf", "create_docx", "create_qrcode", "extract_pdf_text",
        "build_document", "export_source_brief", "create_source_notebook",
        "query_source_notebook", "verify_artifact",
        "create_xlsx", "generate_chart",
        "create_pptx_deck", "create_pitch_deck", "inspect_pptx_template",
        "edit_pptx_template", "qa_pptx_deck", "create_diagram", "create_svg",
        "generate_image",
        "synthesize", "transcribe",
    }
