"""D4b: Ephe's memory as an MCP server — one door, not a second brain.

Anyone already working with MCP agents (Claude, Cursor, a home-grown harness)
should be able to *use* Ephe's persistent memory without fattening a second
fact collection. The server speaks the same JSON-RPC that
`core/tools/mcp_client.py` speaks, over stdin/stdout — same facade, same scope,
no new store.

What the server is NOT: a write permission by default. An external agent that
quietly writes into the user's long-term memory is memory poisoning with
friendliness. Reading is the purpose of the server; **writing costs an explicit
opt-in** (`--allow-write` / `EPHE_MEMORY_MCP_WRITE=1`). And there is no bulk
option: no clear, no export — a shared door does not empty a memory.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.memory_mcp_server import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    handle_request,
    serve,
    tool_specs,
    writes_allowed,
)
from tests.subprocess_env import hermetic_env


class FakeMemory:
    """Fake facade: records calls and returns the shape of the real one."""

    def __init__(self, provider_kind: str = "kepta", stats: dict | None = None):
        self.provider_kind = provider_kind
        self.provider_reason = "decision record"
        self.collection_name = "ephe_memory_test"
        self.calls: list[tuple] = []
        self.rows = [
            {"id": "a1", "text": "Das Gateway läuft hinter nginx", "metadata": {"source": "chat"}, "score": 0.91},
            {"id": "b2", "text": "Zürich ist der Workspace-Standort", "metadata": {"source": "auto"}, "score": 0.62},
        ]
        self._stats = stats or {
            "total": 2,
            "deleted": 1,
            "vector_leg": False,
            "lexical_leg": True,
            "provider": provider_kind,
            "scope": "test",
        }

    def search(self, query: str, top_k: int = 15) -> list[dict]:
        self.calls.append(("search", query, top_k))
        needle = query.lower()
        return [r for r in self.rows if needle in r["text"].lower()][:top_k]

    def list_all(self, limit: int = 100) -> list[dict]:
        self.calls.append(("list_all", limit))
        return self.rows[:limit]

    def list_deleted(self, limit: int = 100) -> list[dict]:
        self.calls.append(("list_deleted", limit))
        return []

    def store(self, text, metadata=None, *, supersedes=None, **options) -> str:
        self.calls.append(("store", text, metadata, supersedes, options))
        return "new9" if supersedes is None else "corr9"

    def update(self, doc_id: str, text: str) -> None:
        self.calls.append(("update", doc_id, text))
        if doc_id not in {r["id"] for r in self.rows}:
            raise KeyError(doc_id)

    def delete(self, doc_id: str) -> None:
        self.calls.append(("delete", doc_id))
        if doc_id not in {r["id"] for r in self.rows}:
            raise KeyError(doc_id)

    def count(self) -> int:
        return len(self.rows)

    def provider_stats(self) -> dict:
        return dict(self._stats)


def _call(memory, name: str, arguments: dict, *, allow_write: bool = False) -> dict:
    resp = handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": name, "arguments": arguments}},
        memory=memory,
        allow_write=allow_write,
    )
    return resp


def _text(resp: dict) -> str:
    return "\n".join(c.get("text", "") for c in resp["result"]["content"])


class TestProtokoll:
    def test_initialize_names_the_server_and_shows_the_write_gate(self):
        resp = handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            memory=FakeMemory(),
            allow_write=False,
        )
        assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION
        assert resp["result"]["serverInfo"]["name"] == SERVER_NAME
        # A model reads the instructions before the first call: this is where it has
        # to say that writing is opt-in — otherwise the agent believes the memory is its own.
        assert "read-only" in resp["result"]["instructions"]

    def test_notifications_are_answered_with_nothing(self):
        assert handle_request(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            memory=FakeMemory(), allow_write=False,
        ) is None

    def test_an_unknown_tool_is_invalid_params_and_cannot_be_called(self):
        """Not even when writing is free: `memory_clear` does not exist."""
        for allow_write in (False, True):
            resp = handle_request(
                {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                 "params": {"name": "memory_clear", "arguments": {}}},
                memory=FakeMemory(), allow_write=allow_write,
            )
            assert resp["error"]["code"] == -32602

    def test_unknown_method_is_method_not_found(self):
        resp = handle_request(
            {"jsonrpc": "2.0", "id": 7, "method": "prompts/list", "params": {}},
            memory=FakeMemory(), allow_write=False,
        )
        assert resp["error"]["code"] == -32601

    def test_tools_list_exposes_memory_but_never_a_bulk_clear(self):
        names = {t["name"] for t in tool_specs()}
        assert names == {
            "memory_search", "memory_list", "memory_stats",
            "memory_store", "memory_update", "memory_delete",
        }
        for tool in tool_specs():
            assert tool["inputSchema"]["type"] == "object"
            assert tool["description"]

    def test_serve_answers_each_line_and_survives_garbage(self):
        stdin = "\n".join([
            "{not json",
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "memory_stats", "arguments": {}}}),
        ]) + "\n"
        out, err, code = _run_serve(stdin)
        assert code == 0
        lines = [json.loads(line) for line in out.strip().splitlines()]
        assert len(lines) == 3, "jede Anfrage genau eine Antwort — sonst hängt der Client"
        assert lines[0]["error"]["code"] == -32700
        assert [ln["id"] for ln in lines[1:]] == [1, 2]
        assert "Traceback" not in err

    def test_banner_goes_to_stderr_never_to_the_protocol(self, monkeypatch):
        import core.memory_mcp_server as mcp

        monkeypatch.setattr(mcp, "_default_memory", lambda scope=None: FakeMemory())
        out, err, code = _run_serve(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n",
            main=True,
        )
        assert code == 0
        assert "read-only" in err and "scope" in err
        assert all(line.lstrip().startswith("{") for line in out.strip().splitlines())


class TestSchreiben:
    def test_a_refused_write_leaves_a_trace_in_the_audit_log(self):
        from core.audit_log import tail

        mem = FakeMemory()
        resp = _call(mem, "memory_store", {"text": "Der Nutzer mag Python"})
        assert resp["result"]["isError"] is True
        assert "allow-write" in _text(resp)
        assert not any(c[0] == "store" for c in mem.calls)
        events = tail(kind="mcp_memory")
        assert events and events[0]["decision"] == "denied"

    def test_store_marks_the_source_so_the_ui_can_show_provenance(self):
        from core.audit_log import tail

        mem = FakeMemory()
        resp = _call(mem, "memory_store", {"text": "Der Nutzer mag Python"}, allow_write=True)
        # MCP: no isError field means success. Sending a flag per success would be
        # chatter; leaving it out is the contract.
        assert not resp["result"].get("isError")
        store_call = next(c for c in mem.calls if c[0] == "store")
        assert store_call[2]["source"] == "mcp"
        assert tail(kind="mcp_memory")[0]["decision"] == "allowed"

    def test_a_correction_supersedes_instead_of_standing_twice(self):
        mem = FakeMemory()
        resp = _call(mem, "memory_store",
                     {"text": "Zürich ist der Standort seit 2026", "supersedes": "b2"},
                     allow_write=True)
        store_call = next(c for c in mem.calls if c[0] == "store")
        assert store_call[3] == "b2"
        assert "corr9" in _text(resp)

    def test_type_and_tags_reach_the_provider(self):
        mem = FakeMemory()
        _call(mem, "memory_store",
              {"text": "Bevorzugt Vitest", "memory_type": "preference", "tags": ["testing"]},
              allow_write=True)
        store_call = next(c for c in mem.calls if c[0] == "store")
        assert store_call[4] == {"memory_type": "preference", "tags": ["testing"]}

    def test_blank_text_is_never_stored(self):
        mem = FakeMemory()
        resp = _call(mem, "memory_store", {"text": "   "}, allow_write=True)
        assert resp["result"]["isError"] is True
        assert not any(c[0] == "store" for c in mem.calls)

    def test_a_missing_id_reads_as_not_found_not_as_a_crash(self):
        mem = FakeMemory()
        for name, args in (("memory_delete", {"id": "zz"}), ("memory_update", {"id": "zz", "text": "neu"})):
            resp = _call(mem, name, args, allow_write=True)
            assert resp["result"]["isError"] is True
            assert "not found" in _text(resp).lower()
        assert "Traceback" not in _text(_call(mem, "memory_delete", {"id": "zz"}, allow_write=True))

    def test_mutating_tools_are_named_so_the_gate_has_a_domain(self):
        from core.memory_mcp_server import MUTATING_TOOLS

        assert MUTATING_TOOLS == {"memory_store", "memory_update", "memory_delete"}
        assert MUTATING_TOOLS <= {t["name"] for t in tool_specs()}


class TestLesen:
    def test_search_returns_ids_scores_and_text(self):
        mem = FakeMemory()
        resp = _call(mem, "memory_search", {"q": "gateway"})
        body = _text(resp)
        assert "a1" in body and "nginx" in body and "0.91" in body
        assert mem.calls[0] == ("search", "gateway", 5)

    def test_top_k_is_clamped_into_the_index(self):
        mem = FakeMemory()
        _call(mem, "memory_search", {"q": "gateway", "top_k": 10_000})
        assert mem.calls[0][2] <= 20

    def test_nothing_found_says_so_with_the_scope(self):
        mem = FakeMemory()
        resp = _call(mem, "memory_search", {"q": "kapitel 7"})
        assert "no memory entry" in _text(resp).lower()

    def test_list_carries_the_document_ids(self):
        body = _text(_call(FakeMemory(), "memory_list", {}))
        assert "a1" in body and "b2" in body

    def test_stats_name_the_brain_the_scope_and_the_write_mode(self):
        body = _text(_call(FakeMemory(), "memory_stats", {}))
        assert "kepta" in body and "ephe_memory_test" in body
        assert "read-only" in body

    def test_stats_report_a_chroma_bucket_without_lying_about_legs(self):
        body = _text(_call(FakeMemory(provider_kind="chroma"), "memory_stats", {}))
        assert "chroma" in body and "lexical" in body


class TestGrenzen:
    def test_write_opt_in_has_no_default(self, monkeypatch):
        monkeypatch.delenv("EPHE_MEMORY_MCP_WRITE", raising=False)
        assert writes_allowed() is False
        monkeypatch.setenv("EPHE_MEMORY_MCP_WRITE", "1")
        assert writes_allowed() is True
        for off in ("0", "", "false"):
            monkeypatch.setenv("EPHE_MEMORY_MCP_WRITE", off)
            assert writes_allowed() is False

    def test_read_only_flag_outranks_the_env(self, monkeypatch):
        """--read-only is the hand on the switch, the env is only the offer."""
        import core.memory_mcp_server as mcp

        monkeypatch.setenv("EPHE_MEMORY_MCP_WRITE", "1")
        monkeypatch.setattr(mcp, "_default_memory", lambda scope=None: FakeMemory())
        seen: dict = {}
        monkeypatch.setattr(mcp, "serve", lambda **kw: seen.update(kw) or 0)

        mcp.main(["--read-only"])
        assert seen["allow_write"] is False
        mcp.main([])
        assert seen["allow_write"] is True

    def test_the_server_never_binds_a_port(self):
        """Stdio only — a network listener would be a second, unsupervised entrance."""
        import core.memory_mcp_server as mcp
        import core.memory_mcp_tools as surface

        source = "\n".join(
            Path(module.__file__).read_text(encoding="utf-8") for module in (mcp, surface)
        )
        for token in ("socket", "HTTPServer", "uvicorn", "bind(", "listen("):
            assert token not in source, token

    def test_the_module_entry_drives_a_real_brain(self, tmp_path, monkeypatch):
        """Integration: `python -m core.memory_mcp_server` against a real Kepta brain.

        No mock, no client import: the line is the product path with which
        a user attaches Ephe's memory to a foreign agent.
        """
        import os
        import subprocess
        import sys

        env = hermetic_env(
            PATH=os.environ.get("PATH", ""),
            HOME=str(tmp_path),
            EPHE_CONFIG_DIR=str(tmp_path / "config"),
            EPHE_MEMORY_EMBEDDER="none",
            EPHE_MEMORY_MCP_WRITE="1",
            PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        )
        proc = subprocess.Popen(
            [sys.executable, "-m", "core.memory_mcp_server"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def ask(payload: dict) -> dict:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            assert line, f"Server hat geschlossen: {proc.stderr.read()[:400]}"
            return json.loads(line)

        try:
            init = ask({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            assert init["result"]["serverInfo"]["name"] == SERVER_NAME
            tools = ask({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            assert "memory_store" in {t["name"] for t in tools["result"]["tools"]}
            stored = ask({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "memory_store", "arguments": {"text": "Das Gateway läuft hinter nginx"}}})
            assert not stored["result"].get("isError"), stored["result"]
            found = ask({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "memory_search", "arguments": {"q": "nginx"}}})
            assert "nginx" in _text(found)
            # list and stats run over the same facade the search just used: their
            # keys (provider, entries, legs, write mode) have to survive contact
            # with the real provider as well as the fake above.
            listed = ask({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
                "name": "memory_list", "arguments": {}}})
            assert "nginx" in _text(listed)
            stats = ask({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {
                "name": "memory_stats", "arguments": {}}})
            assert "entries:" in _text(stats) and "write mode: enabled" in _text(stats)
            proc.stdin.close()
            assert proc.wait(timeout=10) == 0
        finally:
            # Every assert above used to end the test with the stdio server still reading
            # its pipe. It binds no port, but an orphaned child is the residue class the
            # :8765 guard exists for, and a failing test must not leave one behind.
            if proc.returncode is None:
                proc.kill()
            proc.wait(timeout=10)


class TestCli:
    def test_ephe_memory_mcp_forwards_the_same_flags(self, monkeypatch):
        """The CLI is only a mouth: the same flags, no second policy."""
        import ephe_cli

        from core import memory_mcp_server

        sent: list[list[str]] = []
        monkeypatch.setattr(memory_mcp_server, "main", lambda argv: sent.append(argv) or 0)

        args = ephe_cli.build_parser().parse_args(
            ["memory-mcp", "--allow-write", "--scope", "abc123"]
        )
        assert ephe_cli.cmd_memory_mcp(args) == 0
        assert sent == [["--allow-write", "--scope", "abc123"]]

        ephe_cli.cmd_memory_mcp(
            ephe_cli.build_parser().parse_args(["memory-mcp", "--read-only"])
        )
        assert sent[-1] == ["--read-only"]

    def test_the_subcommand_is_discoverable(self):
        import ephe_cli

        choices = next(
            action.choices for action in ephe_cli.build_parser()._actions
            if getattr(action, "choices", None) and "memory-mcp" in action.choices
        )
        assert "memory-mcp" in choices


def _run_serve(stdin_text: str, *, main: bool = False) -> tuple[str, str, int]:
    """Feeds lines into the pipe and returns (stdout, stderr, exit)."""
    import io
    import sys

    out, err = io.StringIO(), io.StringIO()
    if main:
        import core.memory_mcp_server as mcp

        real = (sys.stdin, sys.stdout, sys.stderr)
        sys.stdin, sys.stdout, sys.stderr = io.StringIO(stdin_text), out, err
        try:
            code = mcp.main([])
        finally:
            sys.stdin, sys.stdout, sys.stderr = real
        return out.getvalue(), err.getvalue(), code
    code = serve(
        memory=FakeMemory(),
        allow_write=False,
        stdin=io.StringIO(stdin_text),
        stdout=out,
    )
    return out.getvalue(), err.getvalue(), code
